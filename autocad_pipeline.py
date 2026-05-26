# -*- coding: utf-8 -*-
# AUTOCAD PIPELINE — DP + ARC-FITTER para DXF
# ============================================================
# Mismo algoritmo que macro_PIPELINE_v1:
#   PASO 1 — Douglas-Peucker: reduce puntos
#   PASO 2 — Arc-Fitter: convierte a LWPOLYLINE con bulge
#
# Entrada:  cualquier DXF (LWPOLYLINE, POLYLINE, LINE, SPLINE, ARC, CIRCLE)
# Salida:   DXF con LWPOLYLINE (lineas=bulge0, arcos=bulge!=0)
# Uso:      py -3 autocad_pipeline.py entrada.dxf [salida.dxf]
# ============================================================

import ezdxf
import math
import sys
import os
import traceback
import time

TOL_DP    = 0.01      # Douglas-Peucker: reduccion de puntos
TOL_ARCO  = 0.01      # Arc-Fitter: tolerancia arcos
TOL_LINEA = 0.00001   # Arc-Fitter: rectas exactas
RADIO_MAX = 5000.0
SUFIJO    = "_ARC"

def log(msg):
    print(msg, flush=True)

# ══════════════════════════════════════════════════════════════
# UTILIDADES GEOMETRICAS 2D
# ══════════════════════════════════════════════════════════════

def dist2d(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)

def dist_punto_linea(pt, p0, p1):
    """Distancia perpendicular de pt a la linea p0-p1"""
    dx = p1[0]-p0[0]; dy = p1[1]-p0[1]
    length = math.sqrt(dx*dx + dy*dy)
    if length < 1e-12:
        return dist2d(pt, p0)
    return abs(dy*pt[0] - dx*pt[1] + p1[0]*p0[1] - p1[1]*p0[0]) / length

def circulo_3pts(p0, pm, p1):
    """Centro y radio del circulo por tres puntos. Retorna (cx,cy,r) o None."""
    ax = pm[0]-p0[0]; ay = pm[1]-p0[1]
    bx = p1[0]-p0[0]; by = p1[1]-p0[1]
    det = ax*by - ay*bx
    if abs(det) < 1e-10:
        return None
    d0 = ax*ax+ay*ay
    d1 = bx*bx+by*by
    cx = (d0*by - d1*ay) / (2.0*det)
    cy = (d1*ax - d0*bx) / (2.0*det)
    r  = math.sqrt(cx*cx + cy*cy)
    return (p0[0]+cx, p0[1]+cy, r)

def angulo_normalizado(a):
    while a < 0:        a += 2*math.pi
    while a >= 2*math.pi: a -= 2*math.pi
    return a

def calcular_bulge(p0, pm, p1):
    """
    Calcula el bulge DXF para el arco p0 -> pm -> p1.
    Positivo = CCW, Negativo = CW
    bulge = tan(angulo_central / 4)
    """
    circ = circulo_3pts(p0, pm, p1)
    if circ is None:
        return None
    cx, cy, r = circ

    a0 = math.atan2(p0[1]-cy, p0[0]-cx)
    a1 = math.atan2(p1[1]-cy, p1[0]-cx)
    am = math.atan2(pm[1]-cy,  pm[0]-cx)

    # Delta CCW desde a0 hasta a1
    delta_ccw = angulo_normalizado(a1 - a0)
    # Posicion relativa de am en el recorrido CCW desde a0
    am_rel = angulo_normalizado(am - a0)

    if am_rel <= delta_ccw + 1e-9:
        # El arco va CCW
        theta = delta_ccw
        sign  = 1
    else:
        # El arco va CW
        theta = 2*math.pi - delta_ccw
        sign  = -1

    if theta < 1e-9 or theta > 2*math.pi - 1e-9:
        return None

    return math.tan(theta / 4.0) * sign

# ══════════════════════════════════════════════════════════════
# PASO 1 — DOUGLAS-PEUCKER
# ══════════════════════════════════════════════════════════════

def douglas_peucker(pts, tol):
    if len(pts) <= 2:
        return list(pts)
    max_d = 0.0; max_i = 0
    p0 = pts[0]; p1 = pts[-1]
    for i in range(1, len(pts)-1):
        d = dist_punto_linea(pts[i], p0, p1)
        if d > max_d:
            max_d = d; max_i = i
    if max_d > tol:
        izq = douglas_peucker(pts[:max_i+1], tol)
        der = douglas_peucker(pts[max_i:],   tol)
        return izq[:-1] + der
    return [pts[0], pts[-1]]

def reducir_puntos(pts_orig, tol, es_cerrada):
    if es_cerrada and len(pts_orig) > 2:
        if dist2d(pts_orig[0], pts_orig[-1]) < tol * 2:
            pts = pts_orig[:-1]
        else:
            pts = list(pts_orig)
    else:
        pts = list(pts_orig)

    if len(pts) < 2:
        return None

    # Tres pasadas igual que v28
    resultado = douglas_peucker(pts, tol * 2)
    if len(resultado) > 4:
        resultado = douglas_peucker(resultado, tol)
        if len(resultado) > 4:
            resultado = douglas_peucker(resultado, tol * 0.5)

    if es_cerrada and len(resultado) >= 2:
        resultado = resultado + [resultado[0]]
    return resultado

# ══════════════════════════════════════════════════════════════
# PASO 2 — ARC-FITTER
# ══════════════════════════════════════════════════════════════

def es_recta(pts, tol):
    if len(pts) <= 2:
        return True
    p0 = pts[0]; p1 = pts[-1]
    for pt in pts[1:-1]:
        if dist_punto_linea(pt, p0, p1) > tol:
            return False
    return True

def intentar_arco(pts_zona, tol):
    """
    Intenta ajustar un arco a pts_zona.
    Retorna bulge (float) si valido, None si no.
    """
    if len(pts_zona) < 3:
        return None
    if es_recta(pts_zona, tol):
        return None

    p0 = pts_zona[0]
    pm = pts_zona[len(pts_zona) // 2]
    p1 = pts_zona[-1]

    circ = circulo_3pts(p0, pm, p1)
    if circ is None:
        return None
    cx, cy, r = circ

    if r > RADIO_MAX or r < 0.001:
        return None

    # Verificar que TODOS los puntos estan sobre el circulo
    for pt in pts_zona:
        if abs(math.sqrt((pt[0]-cx)**2 + (pt[1]-cy)**2) - r) > tol:
            return None

    # Filtrar cuasi-rectas (radio gigante, sagitta minima)
    cuerda = dist2d(p0, p1)
    if cuerda > 0.1 and r > 1000.0:
        chord_mid = ((p0[0]+p1[0])/2, (p0[1]+p1[1])/2)
        sagitta = dist2d(pm, chord_mid)
        if sagitta / cuerda < 0.005:
            return None

    return calcular_bulge(p0, pm, p1)

def arc_fitting(pts, tol_arco, tol_linea):
    """
    Retorna lista de segmentos: (p_start, p_end, bulge)
    bulge=0.0  -> linea recta
    bulge!=0.0 -> arco
    """
    segmentos = []
    n = len(pts)
    if n < 2:
        return segmentos

    i = 0
    while i < n - 1:
        if i >= n - 2:
            segmentos.append((pts[i], pts[n-1], 0.0))
            break

        MAX_PTS = 150

        # Recta mas larga con tolerancia exacta
        j_recta = i + 1
        for j in range(min(n-1, i+MAX_PTS), i+1, -1):
            if es_recta(pts[i:j+1], tol_linea):
                j_recta = j
                break

        # Arco mas largo
        mejor_bulge = None; j_arco = -1
        if not es_recta(pts[i:min(i+6, n)], tol_arco):
            for j in range(min(n-1, i+MAX_PTS), i+2, -1):
                if es_recta(pts[i:j+1], tol_arco):
                    continue
                bulge = intentar_arco(pts[i:j+1], tol_arco)
                if bulge is not None:
                    mejor_bulge = bulge; j_arco = j
                    break

        # Arco gana solo si llega mucho mas lejos
        if mejor_bulge is not None and j_arco > j_recta + 5:
            segmentos.append((pts[i], pts[j_arco], mejor_bulge))
            i = j_arco
        else:
            segmentos.append((pts[i], pts[j_recta], 0.0))
            i = j_recta

    return segmentos

# ══════════════════════════════════════════════════════════════
# EXTRACCION DE PUNTOS DESDE ENTIDADES DXF
# ══════════════════════════════════════════════════════════════

def extraer_puntos(entity):
    """Extrae lista de puntos 2D (x,y) de la entidad DXF."""
    tipo = entity.dxftype()
    pts = []

    if tipo == 'LWPOLYLINE':
        for v in entity.get_points(format='xy'):
            pts.append((v[0], v[1]))
        if entity.closed and len(pts) > 1:
            pts.append(pts[0])

    elif tipo == 'POLYLINE':
        for v in entity.vertices:
            loc = v.dxf.location
            pts.append((loc.x, loc.y))
        if entity.is_closed and len(pts) > 1:
            pts.append(pts[0])

    elif tipo == 'LINE':
        s = entity.dxf.start; e = entity.dxf.end
        pts = [(s.x, s.y), (e.x, e.y)]

    elif tipo == 'SPLINE':
        try:
            for p in entity.flattening(0.01):
                pts.append((p[0], p[1]))
        except:
            for p in entity.control_points:
                pts.append((p[0], p[1]))

    elif tipo == 'ARC':
        cx = entity.dxf.center.x; cy = entity.dxf.center.y
        r  = entity.dxf.radius
        a0 = math.radians(entity.dxf.start_angle)
        a1 = math.radians(entity.dxf.end_angle)
        if a1 <= a0: a1 += 2*math.pi
        n = max(8, int((a1-a0) * r / 0.5))
        for k in range(n+1):
            a = a0 + (a1-a0)*k/n
            pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))

    elif tipo == 'CIRCLE':
        cx = entity.dxf.center.x; cy = entity.dxf.center.y
        r  = entity.dxf.radius
        n = max(16, int(2*math.pi*r / 0.5))
        for k in range(n+1):
            a = 2*math.pi*k/n
            pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))

    return pts

def es_cerrada_entidad(entity):
    tipo = entity.dxftype()
    if tipo == 'LWPOLYLINE': return entity.closed
    if tipo == 'POLYLINE':   return entity.is_closed
    if tipo == 'CIRCLE':     return True
    return False

# ══════════════════════════════════════════════════════════════
# PIPELINE COMPLETO POR ENTIDAD
# ══════════════════════════════════════════════════════════════

def procesar_entidad(entity):
    """
    Retorna (segmentos, n_orig, n_dp, n_segs, n_lin, n_arc)
    o None si falla.
    """
    pts = extraer_puntos(entity)
    n_orig = len(pts)
    if n_orig < 2:
        return None, n_orig, 0, 0, 0, 0

    # Filtrar entidades muy cortas
    largo_approx = sum(dist2d(pts[i], pts[i+1]) for i in range(len(pts)-1))
    if largo_approx < 0.5:
        return None, n_orig, 0, 0, 0, 0

    es_cerrada = es_cerrada_entidad(entity)

    # PASO 1: Douglas-Peucker
    pts_reducidos = reducir_puntos(pts, TOL_DP, es_cerrada)
    if not pts_reducidos or len(pts_reducidos) < 2:
        return None, n_orig, 0, 0, 0, 0
    n_dp = len(pts_reducidos)

    # Quitar duplicado final antes de arc_fitting
    pts_arc = pts_reducidos
    if es_cerrada and len(pts_reducidos) > 2:
        if dist2d(pts_reducidos[0], pts_reducidos[-1]) < TOL_ARCO:
            pts_arc = pts_reducidos[:-1]

    # PASO 2: Arc-Fitting
    segmentos = arc_fitting(pts_arc, TOL_ARCO, TOL_LINEA)
    if not segmentos:
        return None, n_orig, n_dp, 0, 0, 0

    n_lin  = sum(1 for s in segmentos if s[2] == 0.0)
    n_arco = sum(1 for s in segmentos if s[2] != 0.0)

    return segmentos, n_orig, n_dp, len(segmentos), n_lin, n_arco

def segmentos_a_vertices(segmentos, es_cerrada):
    """
    Convierte segmentos a vertices para LWPOLYLINE.
    Formato ezdxf: lista de (x, y, start_width, end_width, bulge)
    """
    if not segmentos:
        return []

    vertices = []
    for p0, p1, bulge in segmentos:
        vertices.append((p0[0], p0[1], 0.0, 0.0, bulge))

    if not es_cerrada:
        # Agregar punto final (sin arco)
        p1_last = segmentos[-1][1]
        vertices.append((p1_last[0], p1_last[1], 0.0, 0.0, 0.0))

    return vertices

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

TIPOS_SOPORTADOS = {'LWPOLYLINE', 'POLYLINE', 'LINE', 'SPLINE', 'ARC', 'CIRCLE'}

def main():
    log("=" * 65)
    log("AUTOCAD PIPELINE  |  DP + ARC-FITTER  ->  LWPOLYLINE con bulge")
    log(f"TOL_DP={TOL_DP}mm  |  TOL_ARCO={TOL_ARCO}mm  |  TOL_LINEA={TOL_LINEA}mm")
    log("=" * 65)

    if len(sys.argv) < 2:
        log("")
        log("USO:")
        log("  py -3 autocad_pipeline.py entrada.dxf")
        log("  py -3 autocad_pipeline.py entrada.dxf salida.dxf")
        log("")
        log("Tipos soportados: LWPOLYLINE, POLYLINE, LINE, SPLINE, ARC, CIRCLE")
        log("Salida: LWPOLYLINE con bulge (lineas + arcos)")
        sys.exit(0)

    input_file = sys.argv[1]
    if len(sys.argv) >= 3:
        output_file = sys.argv[2]
    else:
        base, ext = os.path.splitext(input_file)
        output_file = base + SUFIJO + (ext if ext else ".dxf")

    log(f"Entrada : {input_file}")
    log(f"Salida  : {output_file}")
    log("-" * 65)

    # Leer DXF
    try:
        doc_in = ezdxf.readfile(input_file)
        log(f"DXF version: {doc_in.dxfversion}")
    except Exception as e:
        log(f"ERROR leyendo archivo: {e}")
        sys.exit(1)

    msp_in = doc_in.modelspace()

    # Crear DXF de salida con misma version
    doc_out = ezdxf.new(dxfversion=doc_in.dxfversion)
    msp_out = doc_out.modelspace()

    # Copiar capas con sufijo _ARC
    capas_creadas = set()
    def asegurar_capa(nombre):
        dst = nombre + SUFIJO
        if dst not in capas_creadas:
            if dst not in doc_out.layers:
                doc_out.layers.add(dst, color=5)   # color 5 = azul en AutoCAD
            capas_creadas.add(dst)
        return dst

    t0 = time.time()
    n_total = 0; n_ok = 0; n_fallo = 0; n_skip = 0
    tot_orig = 0; tot_dp = 0; tot_segs = 0; tot_lin = 0; tot_arc = 0

    for entity in msp_in:
        tipo = entity.dxftype()
        if tipo not in TIPOS_SOPORTADOS:
            continue

        n_total += 1
        layer_orig = getattr(entity.dxf, 'layer', '0')

        try:
            segmentos, n_orig, n_dp, n_segs, n_lin, n_arc = procesar_entidad(entity)

            if segmentos is None:
                if n_orig < 2:
                    log(f"  SKIP [{tipo:12}] {layer_orig} — sin puntos suficientes")
                elif n_orig > 0 and n_dp == 0:
                    log(f"  SKIP [{tipo:12}] {layer_orig} — demasiado corto")
                else:
                    log(f"  FAIL [{tipo:12}] {layer_orig} — pts={n_orig} dp={n_dp}")
                n_fallo += 1
                continue

            es_cerrada = es_cerrada_entidad(entity)
            vertices = segmentos_a_vertices(segmentos, es_cerrada)

            if len(vertices) < 2:
                log(f"  FAIL [{tipo:12}] {layer_orig} — vertices insuficientes")
                n_fallo += 1
                continue

            dst_layer = asegurar_capa(layer_orig)

            # Crear LWPOLYLINE en el DXF de salida
            lw = msp_out.add_lwpolyline(
                vertices,
                format='xyseb',
                close=es_cerrada,
                dxfattribs={'layer': dst_layer, 'color': 5}
            )

            n_ok += 1
            tot_orig += n_orig; tot_dp  += n_dp
            tot_segs += n_segs; tot_lin += n_lin; tot_arc += n_arc

            red_dp  = (1 - n_dp / n_orig) * 100 if n_orig else 0
            red_seg = (1 - n_segs / n_dp)  * 100 if n_dp   else 0
            log(f"  OK  [{tipo:12}] {layer_orig:25} | "
                f"{n_orig}pts->{n_dp}pts({red_dp:.0f}%)->"
                f"{n_segs}segs({n_lin}L+{n_arc}A)")

        except Exception as e:
            log(f"  ERR [{tipo:12}] {layer_orig}: {e}")
            traceback.print_exc()
            n_fallo += 1

    # Guardar resultado
    try:
        doc_out.saveas(output_file)
    except Exception as e:
        log(f"\nERROR guardando: {e}")
        sys.exit(1)

    elapsed = time.time() - t0
    r1 = (1 - tot_dp   / tot_orig) * 100 if tot_orig else 0
    r2 = (1 - tot_segs / tot_dp)   * 100 if tot_dp   else 0

    log("")
    log("=" * 65)
    log("RESUMEN FINAL")
    log("=" * 65)
    log(f"Entidades procesadas : {n_ok}/{n_total}  |  Fallos/skip: {n_fallo}")
    log(f"Puntos orig -> DP    : {tot_orig} -> {tot_dp}  ({r1:.1f}% reduccion)")
    log(f"Segmentos DP -> segs : {tot_dp} -> {tot_segs}  ({r2:.1f}% reduccion)")
    log(f"Lineas: {tot_lin}  |  Arcos: {tot_arc}")
    log(f"Tiempo: {elapsed:.2f}s")
    log(f"Guardado en: {output_file}")
    log("=" * 65)

if __name__ == '__main__':
    main()

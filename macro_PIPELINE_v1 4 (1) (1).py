# -*- coding: utf-8 -*-
# MACRO PIPELINE v1
# ============================================================
# PIPELINE COMPLETO EN UN SOLO PASO:
#   PASO 1 - Douglas-Peucker (v28): reduce puntos de la original
#   PASO 2 - Arc-Fitter (v36b EXACTA): convierte a lineas+arcos
#   RESULTADO: curva original -> PolyCurve (lineas+arcos) en _ARC
#
# Tolerancias:
#   TOL_DP    = 0.01mm  — reduccion de puntos (v28)
#   TOL_ARCO  = 0.01mm  — ajuste de arcos (v36b)
#   TOL_LINEA = 0.00001mm — rectas exactas (v36b)
#
# Capas destino: [capa]_ARC  (color azul)
# ============================================================

import rhinoscriptsyntax as rs
import Rhino.Geometry as rg
import scriptcontext as sc
import Rhino
import math
import time

TOL_DP     = 0.01       # Douglas-Peucker: reduccion de puntos
TOL_ARCO   = 0.01       # Arc-Fitter: tolerancia arcos
TOL_LINEA  = 0.00001    # Arc-Fitter: rectas exactas
RADIO_MAX  = 5000.0
SUFIJO_DST = "_ARC"

def msg(texto):
    print(texto)
    Rhino.RhinoApp.Wait()

# ══════════════════════════════════════════════════════════════
# PASO 1 — DOUGLAS-PEUCKER (de v28)
# ══════════════════════════════════════════════════════════════

def extraer_puntos(crv):
    if isinstance(crv, rg.PolylineCurve):
        pts = [crv.Point(i) for i in range(crv.PointCount)]
        if len(pts) >= 2: return pts
    try:
        ok, pl = crv.TryGetPolyline()
        if ok and pl is not None and pl.Count >= 2:
            return [pl[i] for i in range(pl.Count)]
    except: pass
    if isinstance(crv, rg.PolyCurve):
        pts = []
        for si in range(crv.SegmentCount):
            seg = crv.SegmentCurve(si)
            if seg is None: continue
            if isinstance(seg, rg.PolylineCurve):
                s0 = 0 if si == 0 else 1
                for k in range(s0, seg.PointCount):
                    pts.append(seg.Point(k))
            else:
                largo = seg.GetLength()
                n = max(3, int(largo / 0.5))
                dom = seg.Domain
                s0 = 0 if si == 0 else 1
                for k in range(s0, n + 1):
                    pts.append(seg.PointAt(dom.ParameterAt(k / float(n))))
        if len(pts) >= 2: return pts
    largo = crv.GetLength()
    n = max(30, min(1000, int(largo / 0.3)))
    dom = crv.Domain
    return [crv.PointAt(dom.ParameterAt(i / float(n))) for i in range(n + 1)]

def douglas_peucker(pts, tol):
    if len(pts) <= 2: return list(pts)
    linea = rg.Line(pts[0], pts[-1])
    max_d = 0.0; max_i = 0
    for i in range(1, len(pts) - 1):
        d = linea.DistanceTo(pts[i], True)
        if d > max_d: max_d = d; max_i = i
    if max_d > tol:
        izq = douglas_peucker(pts[:max_i + 1], tol)
        der = douglas_peucker(pts[max_i:], tol)
        return izq[:-1] + der
    return [pts[0], pts[-1]]

def reducir_puntos(pts_orig, tol, es_cerrada):
    """Paso 1: DP puro — reduce puntos manteniendo forma exacta"""
    if es_cerrada and len(pts_orig) > 2:
        if pts_orig[0].DistanceTo(pts_orig[-1]) < tol * 2:
            pts = pts_orig[:-1]
        else:
            pts = list(pts_orig)
    else:
        pts = list(pts_orig)
    if len(pts) < 2: return None

    # Pasada 1: tolerancia amplia
    resultado = douglas_peucker(pts, tol * 2)
    # Pasada 2: refinar
    if len(resultado) > 4:
        resultado = douglas_peucker(resultado, tol)
        # Pasada 3: afinar
        if len(resultado) > 4:
            resultado = douglas_peucker(resultado, tol * 0.5)

    if es_cerrada and len(resultado) >= 2:
        resultado = resultado + [resultado[0]]
    return resultado

# ══════════════════════════════════════════════════════════════
# PASO 2 — ARC-FITTER (de v36b EXACTA)
# ══════════════════════════════════════════════════════════════

def circulo_3pts(p0, p1, p2):
    ax = p1.X-p0.X; ay = p1.Y-p0.Y
    bx = p2.X-p0.X; by = p2.Y-p0.Y
    det = ax*by - ay*bx
    if abs(det) < 1e-10: return None
    d0 = ax*ax+ay*ay; d1 = bx*bx+by*by
    cx = (d0*by-d1*ay)/(2.0*det)
    cy = (d1*ax-d0*bx)/(2.0*det)
    return (p0.X+cx, p0.Y+cy, math.sqrt(cx*cx+cy*cy))

def es_recta(pts_zona, tol):
    if len(pts_zona) <= 2: return True
    linea = rg.Line(pts_zona[0], pts_zona[-1])
    for pt in pts_zona[1:-1]:
        if linea.DistanceTo(pt, True) > tol: return False
    return True

def arco_valido(arco_crv, pts_zona, tol):
    for pt in pts_zona:
        ok, t = arco_crv.ClosestPoint(pt)
        if not ok: return False
        if pt.DistanceTo(arco_crv.PointAt(t)) > tol: return False
    return True

def intentar_arco(pts_zona, tol):
    if len(pts_zona) < 3: return None
    if es_recta(pts_zona, tol): return None
    p0 = pts_zona[0]
    pm = pts_zona[len(pts_zona) // 2]
    p1 = pts_zona[-1]
    circ = circulo_3pts(p0, pm, p1)
    if circ is None: return None
    cx, cy, radio = circ
    if radio > RADIO_MAX: return None
    for pt in pts_zona:
        if abs(math.sqrt((pt.X-cx)**2+(pt.Y-cy)**2) - radio) > tol:
            return None
    try:
        arc = rg.Arc(p0, pm, p1)
        if not arc.IsValid or arc.Radius < 0.001 or arc.Radius > RADIO_MAX:
            return None
        ac = rg.ArcCurve(arc)
        if ac is None: return None
        if not arco_valido(ac, pts_zona, tol): return None
        cuerda = p0.DistanceTo(p1)
        if cuerda > 0.1:
            t_mid_check = ac.Domain.ParameterAt(0.5)
            pt_mid_arc  = ac.PointAt(t_mid_check)
            sagitta = rg.Line(p0, p1).DistanceTo(pt_mid_arc, True)
            if sagitta/cuerda < 0.005 and arc.Radius > 1000.0: return None
        try:
            t_mid = ac.Domain.ParameterAt(0.5)
            pm2 = ac.PointAt(t_mid)
            arc2 = rg.Arc(p0, pm2, p1)
            if arc2.IsValid and arc2.Radius > 0.001 and arc2.Radius <= RADIO_MAX:
                ac2 = rg.ArcCurve(arc2)
                if ac2 and arco_valido(ac2, pts_zona, tol): return ac2
        except: pass
        return ac
    except: return None

def arc_fitting(pts, tol_arco, tol_linea):
    """Paso 2: prioriza rectas EXACTAS, luego arcos donde aplica"""
    segmentos = []
    n = len(pts)
    if n < 2: return segmentos
    i = 0
    while i < n - 1:
        if i >= n - 2:
            segmentos.append(rg.LineCurve(pts[i], pts[n-1]))
            break
        MAX_PTS = 150
        # Recta mas larga con tolerancia muy baja
        j_recta = i + 1
        for j in range(min(n-1, i+MAX_PTS), i+1, -1):
            if es_recta(pts[i:j+1], tol_linea):
                j_recta = j; break
        # Arco mas largo
        mejor_arco = None; j_arco = -1
        if not es_recta(pts[i:min(i+6, n)], tol_arco):
            for j in range(min(n-1, i+MAX_PTS), i+2, -1):
                if es_recta(pts[i:j+1], tol_arco): continue
                arco = intentar_arco(pts[i:j+1], tol_arco)
                if arco is not None:
                    mejor_arco = arco; j_arco = j; break
        # Arco solo si llega mucho mas lejos
        if mejor_arco is not None and j_arco > j_recta + 5:
            segmentos.append(mejor_arco); i = j_arco
        else:
            segmentos.append(rg.LineCurve(pts[i], pts[j_recta])); i = j_recta
    return segmentos

def construir_polycurve(segmentos, es_cerrada, tol):
    if not segmentos: return None
    pc = rg.PolyCurve()
    pc.Append(segmentos[0])
    for k in range(1, len(segmentos)):
        seg = segmentos[k]
        p_prev = pc.PointAtEnd
        p_next = seg.PointAtStart
        if p_prev.DistanceTo(p_next) > 0.0001:
            p_end = seg.PointAtEnd
            if isinstance(seg, rg.LineCurve):
                seg = rg.LineCurve(p_prev, p_end)
            elif isinstance(seg, rg.ArcCurve):
                try:
                    t_mid = seg.Domain.ParameterAt(0.5)
                    pm = seg.PointAt(t_mid)
                    arc2 = rg.Arc(p_prev, pm, p_end)
                    seg = rg.ArcCurve(arc2) if arc2.IsValid else rg.LineCurve(p_prev, p_end)
                except:
                    seg = rg.LineCurve(p_prev, p_end)
        pc.Append(seg)
    if es_cerrada:
        p_last = pc.PointAtEnd; p_first = pc.PointAtStart
        if p_last.DistanceTo(p_first) > tol * 0.1:
            pc.Append(rg.LineCurve(p_last, p_first))
    return pc

# ══════════════════════════════════════════════════════════════
# PIPELINE COMPLETO — v28 + v36b en una sola funcion
# ══════════════════════════════════════════════════════════════

def procesar_curva(crv_orig):
    """
    Pipeline completo:
    1. Extraer puntos
    2. Douglas-Peucker (reducir)
    3. Arc-Fitting (lineas + arcos)
    Retorna: (curva_final, n_orig, n_pts_dp, n_segs_arc, n_lineas, n_arcos)
    """
    # Extraer puntos
    pts_orig = extraer_puntos(crv_orig)
    if pts_orig is None or len(pts_orig) < 2:
        return None, 0, 0, 0, 0, 0

    es_cerrada = crv_orig.IsClosed
    n_orig = len(pts_orig)

    # PASO 1: Douglas-Peucker
    pts_reducidos = reducir_puntos(pts_orig, TOL_DP, es_cerrada)
    if pts_reducidos is None or len(pts_reducidos) < 2:
        return None, n_orig, 0, 0, 0, 0
    n_dp = len(pts_reducidos)

    # Quitar duplicado final para arc_fitting
    pts_para_arc = pts_reducidos[:-1] if (es_cerrada and
        len(pts_reducidos) > 2 and
        pts_reducidos[0].DistanceTo(pts_reducidos[-1]) < TOL_ARCO) \
        else pts_reducidos

    # PASO 2: Arc-Fitting
    segmentos = arc_fitting(pts_para_arc, TOL_ARCO, TOL_LINEA)
    if not segmentos:
        return None, n_orig, n_dp, 0, 0, 0

    n_lineas = sum(1 for s in segmentos if isinstance(s, rg.LineCurve))
    n_arcos  = sum(1 for s in segmentos if isinstance(s, rg.ArcCurve))

    crv_final = construir_polycurve(segmentos, es_cerrada, TOL_ARCO)
    if crv_final is None:
        return None, n_orig, n_dp, 0, 0, 0

    return crv_final, n_orig, n_dp, len(segmentos), n_lineas, n_arcos

# ══════════════════════════════════════════════════════════════
# MACRO PRINCIPAL
# ══════════════════════════════════════════════════════════════

def macro():
    msg("="*65)
    msg("MACRO PIPELINE v1 | DP + ARC-FITTER")
    msg("TOL_DP={:.4f}mm | TOL_ARCO={:.4f}mm | TOL_LINEA={:.6f}mm".format(
        TOL_DP, TOL_ARCO, TOL_LINEA))
    msg("Entrada: cualquier capa | Salida: [capa]{}".format(SUFIJO_DST))
    msg("="*65)

    sel_ids = rs.GetObjects("Selecciona objetos a procesar", preselect=True)
    if not sel_ids: msg("Nada seleccionado."); return

    capas_sel = sorted(set(rs.ObjectLayer(o) for o in sel_ids if rs.ObjectLayer(o)))
    n_capas = len(capas_sel)
    msg("Capas a procesar: {}".format(n_capas))
    msg("-"*65)

    inicio_total = time.time()
    resumen = []

    for idx, capa in enumerate(capas_sel, 1):
        objs_capa  = rs.ObjectsByLayer(capa) or []
        curvas_ids = []
        for o in objs_capa:
            try:
                if rs.IsCurve(o):
                    c = rs.coercecurve(o)
                    if c and c.GetLength() > 0.5: curvas_ids.append(o)
            except: pass

        if not curvas_ids:
            msg("[{:>2}/{}] {} -- sin curvas".format(idx, n_capas, capa))
            continue

        dst = capa + SUFIJO_DST
        if not rs.IsLayer(dst): rs.AddLayer(dst, (0, 180, 255))

        n_proc=0; tot_o=0; tot_dp=0; tot_segs=0
        tot_lin=0; tot_arc=0
        inicio_capa = time.time()
        n_curvas = len(curvas_ids)

        for ci, cid in enumerate(curvas_ids, 1):
            try:
                crv_orig = rs.coercecurve(cid)
                if not crv_orig: continue

                crv_final, n_orig, n_dp, n_segs, n_lin, n_arc = procesar_curva(crv_orig)

                if crv_final is None:
                    msg("  [{}/{}] FALLO".format(ci, n_curvas))
                    Rhino.RhinoApp.Wait(); continue

                nid = sc.doc.Objects.AddCurve(crv_final)
                if nid:
                    rs.ObjectLayer(nid, dst)
                    rs.ObjectColor(nid, (0, 180, 255))
                    n_proc  += 1
                    tot_o   += n_orig
                    tot_dp  += n_dp
                    tot_segs+= n_segs
                    tot_lin += n_lin
                    tot_arc += n_arc

                red_dp = (1 - n_dp/float(n_orig))*100 if n_orig else 0
                msg("  [{}/{}] {}pts -> {}pts DP ({:.0f}%) -> {}segs ({}L+{}A)".format(
                    ci, n_curvas, n_orig, n_dp, red_dp, n_segs, n_lin, n_arc))

            except Exception as e:
                msg("  [{}/{}] ERROR: {}".format(ci, n_curvas, e))
            Rhino.RhinoApp.Wait()

        sc.doc.Views.Redraw()
        if n_proc == 0:
            msg("[{:>2}/{}] {} -- FALLO total".format(idx, n_capas, capa)); continue

        tiempo = time.time() - inicio_capa
        red_dp  = (1 - tot_dp/float(tot_o))*100 if tot_o else 0
        red_seg = (1 - tot_segs/float(tot_dp))*100 if tot_dp else 0
        msg("[{:>2}/{}] {} | {} crvs | {}pts->{}pts({:.0f}%)->{}segs({:.0f}%) | {}L+{}A | {:.1f}s".format(
            idx, n_capas, capa, n_proc,
            tot_o, tot_dp, red_dp,
            tot_segs, red_seg,
            tot_lin, tot_arc, tiempo))
        msg("")
        resumen.append((capa, n_proc, tot_o, tot_dp, tot_segs, tot_lin, tot_arc))

    sc.doc.Views.Redraw()
    if not resumen: msg("\nNo se proceso ninguna capa."); return

    msg("")
    msg("="*65)
    msg("RESUMEN FINAL")
    msg("="*65)
    msg("{:<25} {:>5} {:>8} {:>7} {:>6} {:>5} {:>5}".format(
        "Capa","Crvs","Pts orig","Pts DP","Segs","Lin","Arc"))
    msg("-"*65)
    tc=to=tdp=ts=tl=ta=0
    for (capa,nc,no,ndp,ns,nl,na) in resumen:
        tc+=nc; to+=no; tdp+=ndp; ts+=ns; tl+=nl; ta+=na
        msg("{:<25} {:>5} {:>8} {:>7} {:>6} {:>5} {:>5}".format(
            capa[:25], nc, no, ndp, ns, nl, na))
    msg("-"*65)
    r1=(1-tdp/float(to))*100 if to else 0
    r2=(1-ts/float(tdp))*100 if tdp else 0
    msg("TOTAL  Crvs:{}  {}pts->{}pts({:.0f}%)->{}segs({:.0f}%)  {}L+{}A  {:.1f}s".format(
        tc, to, tdp, r1, ts, r2, tl, ta, time.time()-inicio_total))
    msg("="*65)
    msg("Rectas: exactas (TOL_LINEA={:.6f}mm)".format(TOL_LINEA))
    msg("Arcos:  TOL_ARCO={:.4f}mm".format(TOL_ARCO))
    msg("Resultado en: [capa]{}".format(SUFIJO_DST))

macro()

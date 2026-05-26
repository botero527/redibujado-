# -*- coding: utf-8 -*-
# MACRO PIPELINE v2
# ============================================================
# PIPELINE COMPLETO EN UN SOLO PASO:
#   PASO 1 - Douglas-Peucker: reduce puntos de la original
#   PASO 2 - Arc-Fitter: convierte a lineas + arcos
#   RESULTADO: curva original -> PolyCurve (lineas+arcos) en _ARC
#
# Mejoras v2 vs v1:
#   - LSQ circle fit (Kasa): ajusta el circulo a TODOS los puntos
#     de la ventana, mucho mas robusto que el ajuste por 3 puntos
#   - Fallback a 3 puntos si LSQ falla la validacion
#   - Umbral de ventaja del arco: +5 -> +1
#     (arco gana si cubre 2+ puntos mas que la mejor recta)
#   - Midpoint sobre el circulo ajustado (CW/CCW correcto)
#   - Sagitta check eliminada (rechazaba arcos planos validos)
#   - RADIO_MAX: 5000 -> 50000 para piezas grandes
#   - MAX_PTS: 150 -> 250 para ventanas de arco mas largas
#
# Tolerancias (identicas a v1):
#   TOL_DP    = 0.01mm  — reduccion de puntos
#   TOL_ARCO  = 0.01mm  — ajuste de arcos
#   TOL_LINEA = 0.00001mm — rectas exactas
#
# Capas destino: [capa]_ARC  (color azul)
# ============================================================

import rhinoscriptsyntax as rs
import Rhino.Geometry as rg
import scriptcontext as sc
import Rhino
import math
import time

TOL_DP     = 0.01
TOL_ARCO   = 0.01
TOL_LINEA  = 0.00001
RADIO_MAX  = 50000.0
SUFIJO_DST = "_ARC"

def msg(texto):
    print(texto)
    Rhino.RhinoApp.Wait()

# ══════════════════════════════════════════════════════════════
# PASO 1 — DOUGLAS-PEUCKER
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
    if es_cerrada and len(pts_orig) > 2:
        if pts_orig[0].DistanceTo(pts_orig[-1]) < tol * 2:
            pts = pts_orig[:-1]
        else:
            pts = list(pts_orig)
    else:
        pts = list(pts_orig)
    if len(pts) < 2: return None

    resultado = douglas_peucker(pts, tol * 2)
    if len(resultado) > 4:
        resultado = douglas_peucker(resultado, tol)
        if len(resultado) > 4:
            resultado = douglas_peucker(resultado, tol * 0.5)

    if es_cerrada and len(resultado) >= 2:
        resultado = resultado + [resultado[0]]
    return resultado

# ══════════════════════════════════════════════════════════════
# PASO 2 — ARC-FITTER v2
# ══════════════════════════════════════════════════════════════

def lsq_circle_fit(pts):
    """
    Ajuste de circulo por minimos cuadrados (metodo Kasa).
    Minimiza sum((xi-cx)^2 + (yi-cy)^2 - r^2)^2.
    Sistema: M*[A,B,C]^T = b  donde A=2cx, B=2cy, C=r^2-cx^2-cy^2
    Ecuacion por punto: xi^2+yi^2 = A*xi + B*yi + C
    """
    n = len(pts)
    if n < 3: return None

    sx=sy=sxx=syy=sxy=sx3=sy3=sxy2=sx2y = 0.0
    for p in pts:
        x, y = p.X, p.Y
        sx+=x; sy+=y; sxx+=x*x; syy+=y*y; sxy+=x*y
        sx3+=x*x*x; sy3+=y*y*y; sxy2+=x*y*y; sx2y+=x*x*y

    # M = [[sxx,sxy,sx],[sxy,syy,sy],[sx,sy,n]]
    # b = [sx3+sxy2, sy3+sx2y, sxx+syy]
    a00=sxx;    a01=sxy;    a02=sx
    a10=sxy;    a11=syy;    a12=sy
    a20=sx;     a21=sy;     a22=float(n)
    b0=sx3+sxy2; b1=sy3+sx2y; b2=sxx+syy

    try:
        if abs(a00) < 1e-12: return None
        f=a10/a00; a11-=f*a01; a12-=f*a02; b1-=f*b0
        f=a20/a00; a21-=f*a01; a22-=f*a02; b2-=f*b0
        if abs(a11) < 1e-12: return None
        f=a21/a11; a22-=f*a12; b2-=f*b1
        if abs(a22) < 1e-12: return None
        C  = b2/a22
        B  = (b1 - a12*C)/a11
        A  = (b0 - a01*B - a02*C)/a00
        cx = A/2.0; cy = B/2.0
        r2 = C + cx*cx + cy*cy
        if r2 <= 1e-10: return None
        return (cx, cy, math.sqrt(r2))
    except:
        return None
        
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

def _construir_arco_desde_circulo(cx, cy, radio, p0, p1, pm_data):
    """Dado un circulo ajustado, construye ArcCurve de p0 a p1 pasando
    por el lado correcto (CW vs CCW) segun pm_data."""
    a0 = math.atan2(p0.Y-cy, p0.X-cx)
    a1 = math.atan2(p1.Y-cy, p1.X-cx)
    ad = math.atan2(pm_data.Y-cy, pm_data.X-cx)

    # Angulo medio CCW y CW desde a0 hasta a1
    diff_ccw = (a1 - a0) % (2*math.pi)
    diff_cw  = (a0 - a1) % (2*math.pi)
    am_ccw = a0 + diff_ccw / 2.0
    am_cw  = a0 - diff_cw  / 2.0

    def ang_dist(a, b):
        d = abs(a-b) % (2*math.pi)
        return min(d, 2*math.pi - d)

    am = am_ccw if ang_dist(am_ccw, ad) <= ang_dist(am_cw, ad) else am_cw
    z_mid = (p0.Z + p1.Z) / 2.0
    pm = rg.Point3d(cx + radio*math.cos(am), cy + radio*math.sin(am), z_mid)

    arc = rg.Arc(p0, pm, p1)
    if not arc.IsValid or arc.Radius < 0.001 or arc.Radius > RADIO_MAX:
        return None
    ac = rg.ArcCurve(arc)
    return ac

def intentar_arco(pts_zona, tol):
    """
    v2: intenta LSQ sobre todos los puntos, con fallback a 3 puntos.
    Ambas opciones pasan la misma validacion de tolerancia.
    """
    if len(pts_zona) < 3: return None
    if es_recta(pts_zona, tol): return None

    p0     = pts_zona[0]
    p1     = pts_zona[-1]
    pm_idx = len(pts_zona) // 2
    pm_dat = pts_zona[pm_idx]

    # Candidatos: LSQ primero, luego 3-puntos como fallback
    candidatos = []
    c_lsq = lsq_circle_fit(pts_zona)
    if c_lsq is not None: candidatos.append(c_lsq)
    c_3pt = circulo_3pts(p0, pm_dat, p1)
    if c_3pt is not None: candidatos.append(c_3pt)

    for (cx, cy, radio) in candidatos:
        if radio > RADIO_MAX or radio < 0.001: continue

        # Todos los puntos dentro de tolerancia del circulo
        valido = True
        for pt in pts_zona:
            if abs(math.sqrt((pt.X-cx)**2 + (pt.Y-cy)**2) - radio) > tol:
                valido = False; break
        if not valido: continue

        try:
            ac = _construir_arco_desde_circulo(cx, cy, radio, p0, p1, pm_dat)
            if ac is None: continue
            if not arco_valido(ac, pts_zona, tol): continue
            return ac
        except:
            continue

    return None

def arc_fitting(pts, tol_arco, tol_linea):
    """
    v2: umbral arco +5 -> +1
    Arco gana si cubre 2 o mas puntos extra respecto a la mejor recta.
    """
    segmentos = []
    n = len(pts)
    if n < 2: return segmentos
    i = 0
    MAX_PTS = 250

    while i < n - 1:
        if i >= n - 2:
            segmentos.append(rg.LineCurve(pts[i], pts[n-1]))
            break

        # Recta mas larga (tolerancia exacta)
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

        # v2: umbral reducido (+5 -> +1)
        if mejor_arco is not None and j_arco > j_recta + 1:
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
# PIPELINE COMPLETO
# ══════════════════════════════════════════════════════════════

def procesar_curva(crv_orig):
    pts_orig = extraer_puntos(crv_orig)
    if pts_orig is None or len(pts_orig) < 2:
        return None, 0, 0, 0, 0, 0

    es_cerrada = crv_orig.IsClosed
    n_orig = len(pts_orig)

    pts_reducidos = reducir_puntos(pts_orig, TOL_DP, es_cerrada)
    if pts_reducidos is None or len(pts_reducidos) < 2:
        return None, n_orig, 0, 0, 0, 0
    n_dp = len(pts_reducidos)

    pts_para_arc = pts_reducidos[:-1] if (es_cerrada and
        len(pts_reducidos) > 2 and
        pts_reducidos[0].DistanceTo(pts_reducidos[-1]) < TOL_ARCO) \
        else pts_reducidos

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
    msg("MACRO PIPELINE v2 | DP + ARC-FITTER LSQ")
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
    msg("Arcos:  LSQ + fallback 3pts, TOL_ARCO={:.4f}mm".format(TOL_ARCO))
    msg("Resultado en: [capa]{}".format(SUFIJO_DST))

macro()

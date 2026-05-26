

import rhinoscriptsyntax as rs
import Rhino.Geometry as rg
import scriptcontext as sc
import Rhino
import math
import time

TOL_DP     = 0.01
TOL_ARCO   = 0.01
TOL_LINEA  = 0.00001
TOL_FUSION = 0.01       # tolerancia para fusionar segmentos post-proceso
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
# PASO 2 — ARC-FITTER (igual a v2, LSQ corregido)
# ══════════════════════════════════════════════════════════════

def lsq_circle_fit(pts):
    """
    Ajuste LSQ de circulo (metodo Kasa).
    Sistema: M*[A,B,C]^T = b  (A=2cx, B=2cy)
    """
    n = len(pts)
    if n < 3: return None
    sx=sy=sxx=syy=sxy=sx3=sy3=sxy2=sx2y = 0.0
    for p in pts:
        x,y = p.X, p.Y
        sx+=x; sy+=y; sxx+=x*x; syy+=y*y; sxy+=x*y
        sx3+=x*x*x; sy3+=y*y*y; sxy2+=x*y*y; sx2y+=x*x*y
    a00=sxx; a01=sxy; a02=sx
    a10=sxy; a11=syy; a12=sy
    a20=sx;  a21=sy;  a22=float(n)
    b0=sx3+sxy2; b1=sy3+sx2y; b2=sxx+syy
    try:
        if abs(a00)<1e-12: return None
        f=a10/a00; a11-=f*a01; a12-=f*a02; b1-=f*b0
        f=a20/a00; a21-=f*a01; a22-=f*a02; b2-=f*b0
        if abs(a11)<1e-12: return None
        f=a21/a11; a22-=f*a12; b2-=f*b1
        if abs(a22)<1e-12: return None
        C=b2/a22; B=(b1-a12*C)/a11; A=(b0-a01*B-a02*C)/a00
        cx=A/2.0; cy=B/2.0
        r2=C+cx*cx+cy*cy
        if r2<=1e-10: return None
        return (cx, cy, math.sqrt(r2))
    except: return None

def circulo_3pts(p0, p1, p2):
    ax=p1.X-p0.X; ay=p1.Y-p0.Y
    bx=p2.X-p0.X; by=p2.Y-p0.Y
    det=ax*by-ay*bx
    if abs(det)<1e-10: return None
    d0=ax*ax+ay*ay; d1=bx*bx+by*by
    cx=(d0*by-d1*ay)/(2.0*det)
    cy=(d1*ax-d0*bx)/(2.0*det)
    return (p0.X+cx, p0.Y+cy, math.sqrt(cx*cx+cy*cy))

def es_recta(pts_zona, tol):
    if len(pts_zona)<=2: return True
    linea=rg.Line(pts_zona[0], pts_zona[-1])
    for pt in pts_zona[1:-1]:
        if linea.DistanceTo(pt, True)>tol: return False
    return True

def arco_valido(arco_crv, pts_zona, tol):
    for pt in pts_zona:
        ok,t=arco_crv.ClosestPoint(pt)
        if not ok: return False
        if pt.DistanceTo(arco_crv.PointAt(t))>tol: return False
    return True

def _arco_desde_circulo(cx, cy, radio, p0, p1, pm_data):
    a0=math.atan2(p0.Y-cy, p0.X-cx)
    a1=math.atan2(p1.Y-cy, p1.X-cx)
    ad=math.atan2(pm_data.Y-cy, pm_data.X-cx)
    diff_ccw=(a1-a0)%(2*math.pi)
    diff_cw =(a0-a1)%(2*math.pi)
    am_ccw=a0+diff_ccw/2.0
    am_cw =a0-diff_cw /2.0
    def ang_dist(a,b):
        d=abs(a-b)%(2*math.pi); return min(d,2*math.pi-d)
    am=am_ccw if ang_dist(am_ccw,ad)<=ang_dist(am_cw,ad) else am_cw
    z_mid=(p0.Z+p1.Z)/2.0
    pm=rg.Point3d(cx+radio*math.cos(am), cy+radio*math.sin(am), z_mid)
    arc=rg.Arc(p0,pm,p1)
    if not arc.IsValid or arc.Radius<0.001 or arc.Radius>RADIO_MAX: return None
    return rg.ArcCurve(arc)

def intentar_arco(pts_zona, tol):
    if len(pts_zona)<3: return None
    if es_recta(pts_zona, tol): return None
    p0=pts_zona[0]; p1=pts_zona[-1]; pm_idx=len(pts_zona)//2
    candidatos=[]
    c=lsq_circle_fit(pts_zona)
    if c: candidatos.append(c)
    c3=circulo_3pts(p0, pts_zona[pm_idx], p1)
    if c3: candidatos.append(c3)
    for (cx,cy,radio) in candidatos:
        if radio>RADIO_MAX or radio<0.001: continue
        valido=True
        for pt in pts_zona:
            if abs(math.sqrt((pt.X-cx)**2+(pt.Y-cy)**2)-radio)>tol:
                valido=False; break
        if not valido: continue
        try:
            ac=_arco_desde_circulo(cx,cy,radio,p0,p1,pts_zona[pm_idx])
            if ac is None: continue
            if not arco_valido(ac, pts_zona, tol): continue
            return ac
        except: continue
    return None

def arc_fitting(pts, tol_arco, tol_linea):
    segmentos=[]; n=len(pts)
    if n<2: return segmentos
    i=0; MAX_PTS=250
    while i<n-1:
        if i>=n-2:
            segmentos.append(rg.LineCurve(pts[i],pts[n-1])); break
        j_recta=i+1
        for j in range(min(n-1,i+MAX_PTS),i+1,-1):
            if es_recta(pts[i:j+1],tol_linea):
                j_recta=j; break
        mejor_arco=None; j_arco=-1
        if not es_recta(pts[i:min(i+6,n)],tol_arco):
            for j in range(min(n-1,i+MAX_PTS),i+2,-1):
                if es_recta(pts[i:j+1],tol_arco): continue
                arco=intentar_arco(pts[i:j+1],tol_arco)
                if arco is not None:
                    mejor_arco=arco; j_arco=j; break
        if mejor_arco is not None and j_arco>j_recta+1:
            segmentos.append(mejor_arco); i=j_arco
        else:
            segmentos.append(rg.LineCurve(pts[i],pts[j_recta])); i=j_recta
    return segmentos

# ══════════════════════════════════════════════════════════════
# PASO 3 — FUSION DE SEGMENTOS (novedad v3)
# ══════════════════════════════════════════════════════════════

def fusionar_lineas(segmentos, tol):
    """
    Fusiona runs de LineCurve consecutivas colineales en una sola linea.
    Ejemplo: line(A-B) + line(B-C) + line(C-D) colineales -> line(A-D)
    Usa tol para decidir si los puntos intermedios estan en la linea.
    """
    if not segmentos: return segmentos
    result = []
    i = 0
    while i < len(segmentos):
        if not isinstance(segmentos[i], rg.LineCurve):
            result.append(segmentos[i]); i += 1; continue

        # Acumular todos los puntos del run de lineas consecutivas
        pts_run = [segmentos[i].PointAtStart]
        j = i
        while j < len(segmentos) and isinstance(segmentos[j], rg.LineCurve):
            pts_run.append(segmentos[j].PointAtEnd)
            j += 1

        # Solo una linea en el run -> pasar directo
        if j - i == 1:
            result.append(segmentos[i]); i += 1; continue

        # Greedy: desde cada punto de inicio, extender lo mas posible
        p_idx = 0
        while p_idx < len(pts_run) - 1:
            best = p_idx + 1
            for end in range(len(pts_run)-1, p_idx, -1):
                if es_recta(pts_run[p_idx:end+1], tol):
                    best = end; break
            result.append(rg.LineCurve(pts_run[p_idx], pts_run[best]))
            p_idx = best
        i = j

    return result

def fusionar_arcos(segmentos, tol):
    """
    Fusiona pares de ArcCurve consecutivos que pertenecen al mismo circulo.
    Dos arcos se pueden fusionar si tienen el mismo centro y radio (dentro de tol).
    """
    if not segmentos: return segmentos
    changed = True
    result = list(segmentos)
    while changed:
        changed = False
        nuevo = []
        i = 0
        while i < len(result):
            if (i < len(result)-1 and
                isinstance(result[i],   rg.ArcCurve) and
                isinstance(result[i+1], rg.ArcCurve)):
                arc0 = result[i].Arc
                arc1 = result[i+1].Arc
                mismo_radio  = abs(arc0.Radius - arc1.Radius) < tol * 2
                mismo_centro = arc0.Center.DistanceTo(arc1.Center) < tol * 5
                if mismo_radio and mismo_centro:
                    try:
                        p0 = result[i].PointAtStart
                        pm = result[i].PointAt(result[i].Domain.ParameterAt(0.5))
                        p1 = result[i+1].PointAtEnd
                        p_join = result[i].PointAtEnd   # punto de union
                        arc_new = rg.Arc(p0, pm, p1)
                        if arc_new.IsValid and arc_new.Radius > 0.001:
                            ac_new = rg.ArcCurve(arc_new)
                            # Verificar que el punto de union sigue dentro de tol
                            ok, t = ac_new.ClosestPoint(p_join)
                            if ok and p_join.DistanceTo(ac_new.PointAt(t)) <= tol * 2:
                                nuevo.append(ac_new)
                                i += 2; changed = True; continue
                    except: pass
            nuevo.append(result[i]); i += 1
        result = nuevo
    return result

def fusionar_segmentos(segmentos, tol):
    """Aplica fusion de lineas y luego de arcos."""
    segs = fusionar_lineas(segmentos, tol)
    segs = fusionar_arcos(segs, tol)
    return segs

# ══════════════════════════════════════════════════════════════
# ENSAMBLADO FINAL
# ══════════════════════════════════════════════════════════════

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
                    pm    = seg.PointAt(t_mid)
                    arc2  = rg.Arc(p_prev, pm, p_end)
                    seg   = rg.ArcCurve(arc2) if arc2.IsValid else rg.LineCurve(p_prev, p_end)
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
        return None, 0, 0, 0, 0, 0, 0, 0

    es_cerrada = crv_orig.IsClosed
    n_orig = len(pts_orig)

    # PASO 1: Douglas-Peucker
    pts_reducidos = reducir_puntos(pts_orig, TOL_DP, es_cerrada)
    if pts_reducidos is None or len(pts_reducidos) < 2:
        return None, n_orig, 0, 0, 0, 0, 0, 0
    n_dp = len(pts_reducidos)

    pts_para_arc = pts_reducidos[:-1] if (es_cerrada and
        len(pts_reducidos) > 2 and
        pts_reducidos[0].DistanceTo(pts_reducidos[-1]) < TOL_ARCO) \
        else pts_reducidos

    # PASO 2: Arc-Fitting
    segmentos = arc_fitting(pts_para_arc, TOL_ARCO, TOL_LINEA)
    if not segmentos:
        return None, n_orig, n_dp, 0, 0, 0, 0, 0
    n_segs_pre = len(segmentos)

    # PASO 3: Fusion
    segmentos = fusionar_segmentos(segmentos, TOL_FUSION)
    n_segs = len(segmentos)
    n_lineas = sum(1 for s in segmentos if isinstance(s, rg.LineCurve))
    n_arcos  = sum(1 for s in segmentos if isinstance(s, rg.ArcCurve))

    crv_final = construir_polycurve(segmentos, es_cerrada, TOL_ARCO)
    if crv_final is None:
        return None, n_orig, n_dp, n_segs_pre, 0, 0, 0, 0

    return crv_final, n_orig, n_dp, n_segs_pre, n_segs, n_lineas, n_arcos, 0

# ══════════════════════════════════════════════════════════════
# MACRO PRINCIPAL
# ══════════════════════════════════════════════════════════════

def macro():
    msg("="*65)
    msg("MACRO PIPELINE v3 | DP + ARC-FITTER LSQ + FUSION")
    msg("TOL_DP={:.4f} | TOL_ARCO={:.4f} | TOL_FUSION={:.4f}mm".format(
        TOL_DP, TOL_ARCO, TOL_FUSION))
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
            msg("[{:>2}/{}] {} -- sin curvas".format(idx, n_capas, capa)); continue

        dst = capa + SUFIJO_DST
        if not rs.IsLayer(dst): rs.AddLayer(dst, (0, 180, 255))

        n_proc=0; tot_o=0; tot_dp=0; tot_pre=0; tot_segs=0
        tot_lin=0; tot_arc=0
        inicio_capa = time.time()
        n_curvas = len(curvas_ids)

        for ci, cid in enumerate(curvas_ids, 1):
            try:
                crv_orig = rs.coercecurve(cid)
                if not crv_orig: continue

                res = procesar_curva(crv_orig)
                crv_final = res[0]
                n_orig, n_dp, n_pre, n_segs, n_lin, n_arc = res[1], res[2], res[3], res[4], res[5], res[6]

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
                    tot_pre += n_pre
                    tot_segs+= n_segs
                    tot_lin += n_lin
                    tot_arc += n_arc

                red_dp  = (1-n_dp /float(n_orig))*100 if n_orig else 0
                red_fus = (1-n_segs/float(n_pre)) *100 if n_pre  else 0
                msg("  [{}/{}] {}pts->{}pts({:.0f}%)->{}segs->{}segs({:.0f}%) [{}L+{}A]".format(
                    ci, n_curvas, n_orig, n_dp, red_dp, n_pre, n_segs, red_fus, n_lin, n_arc))

            except Exception as e:
                msg("  [{}/{}] ERROR: {}".format(ci, n_curvas, e))
            Rhino.RhinoApp.Wait()

        sc.doc.Views.Redraw()
        if n_proc == 0:
            msg("[{:>2}/{}] {} -- FALLO total".format(idx, n_capas, capa)); continue

        tiempo = time.time() - inicio_capa
        red_dp  = (1-tot_dp  /float(tot_o))  *100 if tot_o   else 0
        red_arc = (1-tot_pre /float(tot_dp)) *100 if tot_dp  else 0
        red_fus = (1-tot_segs/float(tot_pre))*100 if tot_pre else 0
        msg("[{:>2}/{}] {} | {}crvs | pts:{}->{} ({:.0f}%) | arc:{} ({:.0f}%) | fus:{} ({:.0f}%) | {}L+{}A | {:.1f}s".format(
            idx, n_capas, capa, n_proc,
            tot_o, tot_dp, red_dp,
            tot_pre, red_arc,
            tot_segs, red_fus,
            tot_lin, tot_arc, tiempo))
        msg("")
        resumen.append((capa, n_proc, tot_o, tot_dp, tot_pre, tot_segs, tot_lin, tot_arc))

    sc.doc.Views.Redraw()
    if not resumen: msg("\nNo se proceso ninguna capa."); return

    msg("")
    msg("="*65)
    msg("RESUMEN FINAL")
    msg("="*65)
    msg("{:<22} {:>4} {:>7} {:>6} {:>6} {:>6} {:>4} {:>4}".format(
        "Capa","Crv","PtsOrig","PtsDP","SegsAF","SegsFus","Lin","Arc"))
    msg("-"*65)
    tc=to=tdp=tpre=ts=tl=ta=0
    for (capa,nc,no,ndp,npre,ns,nl,na) in resumen:
        tc+=nc; to+=no; tdp+=ndp; tpre+=npre; ts+=ns; tl+=nl; ta+=na
        msg("{:<22} {:>4} {:>7} {:>6} {:>6} {:>6} {:>4} {:>4}".format(
            capa[:22], nc, no, ndp, npre, ns, nl, na))
    msg("-"*65)
    r1=(1-tdp /float(to))  *100 if to   else 0
    r2=(1-tpre/float(tdp)) *100 if tdp  else 0
    r3=(1-ts  /float(tpre))*100 if tpre else 0
    msg("TOTAL  Crvs:{}  pts:{}->{} ({:.0f}%)  AF:{} ({:.0f}%)  Fus:{} ({:.0f}%)  {}L+{}A  {:.1f}s".format(
        tc, to, tdp, r1, tpre, r2, ts, r3, tl, ta, time.time()-inicio_total))
    msg("="*65)
    msg("DP={:.4f} | Arco={:.4f} | Fusion={:.4f}mm".format(TOL_DP, TOL_ARCO, TOL_FUSION))

macro()

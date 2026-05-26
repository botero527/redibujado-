# -*- coding: utf-8 -*-
# AUTOCAD REDIBUJA v3 — DP + ARC-FITTER interactivo
# Conecta a AutoCAD abierto, el usuario selecciona, se redibuja.

import sys, math, time, traceback
import win32com.client
from win32com.client import VARIANT
import pythoncom

# ═══════════════════════════════════════════════════
# CONSOLA CON COLORES (ANSI en Windows 10+)
# ═══════════════════════════════════════════════════
import os
os.system("")  # habilita ANSI en Windows

R  = "\033[91m"; G  = "\033[92m"; Y  = "\033[93m"
B  = "\033[94m"; C  = "\033[96m"; W  = "\033[97m"
DIM= "\033[2m";  RST= "\033[0m";  BLD= "\033[1m"

def log(msg=""):          print(msg, flush=True)
def ok(msg):              print(f"  {G}OK{RST}  {msg}", flush=True)
def err(msg):             print(f"  {R}ERR{RST} {msg}", flush=True)
def warn(msg):            print(f"  {Y}!!!{RST} {msg}", flush=True)
def info(msg):            print(f"  {C}---{RST} {msg}", flush=True)
def skip(msg):            print(f"  {DIM}SKP {msg}{RST}", flush=True)
def header(msg):          print(f"\n{BLD}{C}{msg}{RST}", flush=True)
def sep():                print(f"{DIM}{'-'*65}{RST}", flush=True)

# ═══════════════════════════════════════════════════
# TOLERANCIAS (editables en tiempo de ejecucion)
# ═══════════════════════════════════════════════════
class Config:
    TOL_DP    = 0.05   # Douglas-Peucker mm (mas alto = menos puntos, mas rapido)
    TOL_ARCO  = 0.05   # Ajuste de arcos mm
    TOL_LINEA = 0.001  # Rectas exactas mm
    RADIO_MAX = 5000.0
    COLOR     = 5      # azul AutoCAD
    SUFIJO    = "_ARC"
    ORIG_LAYER= "_ORIGINAL"

cfg = Config()

def pedir_float(prompt, default):
    try:
        v = input(f"  {Y}{prompt}{RST} [{default}]: ").strip()
        return float(v) if v else default
    except: return default

def mostrar_config():
    log(f"  TOL_DP    = {C}{cfg.TOL_DP}{RST} mm  (reduccion de puntos)")
    log(f"  TOL_ARCO  = {C}{cfg.TOL_ARCO}{RST} mm  (tolerancia arcos)")
    log(f"  TOL_LINEA = {C}{cfg.TOL_LINEA}{RST} mm  (rectas exactas)")

def menu_tolerancias():
    header("CONFIGURAR TOLERANCIAS")
    log(f"  Valores actuales:")
    mostrar_config()
    log()
    cfg.TOL_DP    = pedir_float("TOL_DP    mm", cfg.TOL_DP)
    cfg.TOL_ARCO  = pedir_float("TOL_ARCO  mm", cfg.TOL_ARCO)
    cfg.TOL_LINEA = pedir_float("TOL_LINEA mm", cfg.TOL_LINEA)
    log()
    log(f"  {G}Tolerancias actualizadas.{RST}")

# ═══════════════════════════════════════════════════
# GEOMETRIA 2D
# ═══════════════════════════════════════════════════

def dist2d(a, b):
    return math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2)

def dist_linea(pt, p0, p1):
    dx=p1[0]-p0[0]; dy=p1[1]-p0[1]; L=math.sqrt(dx*dx+dy*dy)
    if L<1e-12: return dist2d(pt,p0)
    return abs(dy*pt[0]-dx*pt[1]+p1[0]*p0[1]-p1[1]*p0[0])/L

def circulo_3pts(p0,pm,p1):
    ax=pm[0]-p0[0]; ay=pm[1]-p0[1]
    bx=p1[0]-p0[0]; by=p1[1]-p0[1]
    det=ax*by-ay*bx
    if abs(det)<1e-10: return None
    d0=ax*ax+ay*ay; d1=bx*bx+by*by
    cx=(d0*by-d1*ay)/(2*det); cy=(d1*ax-d0*bx)/(2*det)
    return (p0[0]+cx, p0[1]+cy, math.sqrt(cx*cx+cy*cy))

def ang_norm(a):
    while a<0: a+=2*math.pi
    while a>=2*math.pi: a-=2*math.pi
    return a

def calcular_bulge(p0,pm,p1):
    circ=circulo_3pts(p0,pm,p1)
    if circ is None: return None
    cx,cy,r=circ
    a0=math.atan2(p0[1]-cy,p0[0]-cx)
    a1=math.atan2(p1[1]-cy,p1[0]-cx)
    am=math.atan2(pm[1]-cy,pm[0]-cx)
    d_ccw=ang_norm(a1-a0); am_r=ang_norm(am-a0)
    if am_r<=d_ccw+1e-9: theta=d_ccw;  sign=1
    else:                 theta=2*math.pi-d_ccw; sign=-1
    if theta<1e-9 or theta>2*math.pi-1e-9: return None
    return math.tan(theta/4)*sign

# ═══════════════════════════════════════════════════
# NURBS / DE BOOR — evaluacion exacta del spline
# ═══════════════════════════════════════════════════

def nurbs_span(n, p, t, U):
    if t >= U[n+1]: return n
    lo,hi=p,n+1; mid=(lo+hi)//2
    while t<U[mid] or t>=U[mid+1]:
        if t<U[mid]: hi=mid
        else:        lo=mid
        mid=(lo+hi)//2
    return mid

def nurbs_basis(i, t, p, U):
    N=[0.0]*(p+1); N[0]=1.0
    left=[0.0]*(p+1); right=[0.0]*(p+1)
    for j in range(1,p+1):
        left[j]=t-U[i+1-j]; right[j]=U[i+j]-t
        saved=0.0
        for r in range(j):
            denom=right[r+1]+left[j-r]
            temp=(N[r]/denom) if abs(denom)>1e-15 else 0.0
            N[r]=saved+right[r+1]*temp; saved=left[j-r]*temp
        N[j]=saved
    return N

def nurbs_pt(t, P, W, U, p):
    n=len(P)-1
    span=nurbs_span(n,p,t,U)
    N=nurbs_basis(span,t,p,U)
    wx=wy=ws=0.0
    for j in range(p+1):
        idx=span-p+j; w=W[idx]
        ws+=N[j]*w; wx+=N[j]*w*P[idx][0]; wy+=N[j]*w*P[idx][1]
    if ws<1e-12: return (P[span][0],P[span][1])
    return (wx/ws, wy/ws)

def evaluar_spline_com(ent, verbose=False):
    """
    Evalua el NURBS via de Boor usando Knots + GetControlPoint.
    Soporta rational (con Weights) y polynomial (sin Weights, W=1).
    """
    try:
        U = list(ent.Knots)
        p = int(ent.Degree)
        is_rat = False
        try:    is_rat = bool(ent.IsRational)
        except: pass

        # Weights: solo disponibles en rational. Polynomial = todos 1.0
        W = []
        try:
            W = list(ent.Weights)
        except:
            pass  # polynomial spline — sin pesos

        # Conteo real desde knot vector: n_cp = len(U) - p - 1
        n_cp_k = len(U) - p - 1

        if not W or len(W) < 2:
            W = [1.0] * n_cp_k
            is_rat = False

        # Usar len(W) si coincide aprox, sino confiar en knots
        n_cp = len(W) if abs(len(W) - n_cp_k) <= 1 else n_cp_k
        W = (W + [1.0]*n_cp)[:n_cp]  # pad/truncar

        P = []
        for i in range(n_cp):
            try:
                cp = ent.GetControlPoint(i)
                P.append((cp[0], cp[1]))
            except:
                break

        if len(P) < 2:
            if verbose: warn(f"  Solo {len(P)} CPs disponibles")
            return []

        n_cp = min(len(P), len(W))
        P = P[:n_cp]; W = W[:n_cp]

        # Ajustar knots si no coinciden
        m_ok = n_cp + p   # len(U) esperado = n_cp + p + 1 - 1... = n + p + 1 con n=n_cp-1
        if len(U) != n_cp + p + 1:
            if verbose: warn(f"  Knots {len(U)} != esperado {n_cp+p+1} — re-ajustando n_cp desde knots")
            n_cp2 = len(U) - p - 1
            if n_cp2 < 2: return []
            n_cp = min(n_cp, n_cp2)
            P = P[:n_cp]; W = W[:n_cp]

        n = n_cp - 1
        t0 = U[p]; t1 = U[n+1]
        if t1 <= t0:
            if verbose: warn(f"  Dominio invalido: t0={t0} t1={t1}")
            return []

        if verbose:
            info(f"  Spline: {'racional' if is_rat else 'polinomial'}  grado={p}  CPs={n_cp}  knots={len(U)}")
            info(f"  Dominio: [{t0:.4f}, {t1:.4f}]")

        # Sampleo: 16 puntos por segmento entre knots unicos (doble que antes)
        knots_u = sorted(set(U))
        N_seg = 16
        pts_raw = []
        for ki in range(len(knots_u)-1):
            ta = max(knots_u[ki], t0)
            tb = min(knots_u[ki+1], t1)
            if tb <= ta: continue
            for k in range(N_seg + 1):
                t = ta + (tb - ta) * k / N_seg
                t = max(t0, min(t1 - 1e-12, t))
                pts_raw.append(nurbs_pt(t, P, W, U, p))

        # Limpiar duplicados
        limpio = [pts_raw[0]] if pts_raw else []
        for pt in pts_raw[1:]:
            if dist2d(pt, limpio[-1]) > 1e-6:
                limpio.append(pt)

        if verbose:
            info(f"  Puntos muestreados: {len(pts_raw)} -> {len(limpio)} unicos")
            if limpio:
                xs=[p[0] for p in limpio]; ys=[p[1] for p in limpio]
                info(f"  BBox: X[{min(xs):.2f}, {max(xs):.2f}]  Y[{min(ys):.2f}, {max(ys):.2f}]")

        return limpio

    except Exception as e:
        err(f"NURBS eval: {e}")
        traceback.print_exc()
        return []

# ═══════════════════════════════════════════════════
# DOUGLAS-PEUCKER
# ═══════════════════════════════════════════════════

def dp(pts, tol):
    if len(pts)<=2: return list(pts)
    md=0; mi=0; p0=pts[0]; p1=pts[-1]
    for i in range(1,len(pts)-1):
        d=dist_linea(pts[i],p0,p1)
        if d>md: md=d; mi=i
    if md>tol:
        return dp(pts[:mi+1],tol)[:-1]+dp(pts[mi:],tol)
    return [pts[0],pts[-1]]

def reducir_pts(pts, tol, cerrada):
    if cerrada and len(pts)>2 and dist2d(pts[0],pts[-1])<tol*2:
        pts=pts[:-1]
    if len(pts)<2: return None
    r=dp(pts,tol*2)
    if len(r)>4: r=dp(r,tol)
    if len(r)>4: r=dp(r,tol*0.5)
    if cerrada: r=r+[r[0]]
    return r

# ═══════════════════════════════════════════════════
# ARC-FITTER
# ═══════════════════════════════════════════════════

def es_recta(pts, tol):
    if len(pts)<=2: return True
    p0=pts[0]; p1=pts[-1]
    for pt in pts[1:-1]:
        if dist_linea(pt,p0,p1)>tol: return False
    return True

def intentar_arco(pts_z, tol):
    if len(pts_z)<3 or es_recta(pts_z,tol): return None
    p0=pts_z[0]; pm=pts_z[len(pts_z)//2]; p1=pts_z[-1]

    # Sagitta real: maxima desviacion de los puntos intermedios respecto a la cuerda p0-p1
    # Si es muy pequeña, no vale la pena hacer un arco (seria una recta con ruido)
    sagitta_real = max(dist_linea(pt, p0, p1) for pt in pts_z[1:-1]) if len(pts_z)>2 else 0
    MIN_SAGITTA_ABS   = tol * 4          # minimo 4x la tolerancia del arco en mm
    MIN_SAGITTA_RATIO = 0.008            # minimo 0.8% de la cuerda
    cuerda = dist2d(p0, p1)
    if sagitta_real < MIN_SAGITTA_ABS: return None
    if cuerda > 1.0 and sagitta_real / cuerda < MIN_SAGITTA_RATIO: return None

    circ=circulo_3pts(p0,pm,p1)
    if circ is None: return None
    cx,cy,r=circ
    if r>cfg.RADIO_MAX or r<0.001: return None
    for pt in pts_z:
        if abs(math.sqrt((pt[0]-cx)**2+(pt[1]-cy)**2)-r)>tol: return None

    bulge=calcular_bulge(p0,pm,p1)
    if bulge is None: return None
    # Rechazar arcos > 180° — crean loops en AutoCAD
    if abs(bulge) > 1.0: return None
    return bulge

def arc_fit(pts):
    segs=[]; n=len(pts); i=0
    tol_a=cfg.TOL_ARCO; tol_l=cfg.TOL_LINEA
    while i<n-1:
        if i>=n-2: segs.append((pts[i],pts[n-1],0.0)); break
        MAX=150
        jl=i+1
        for j in range(min(n-1,i+MAX),i+1,-1):
            if es_recta(pts[i:j+1],tol_l): jl=j; break
        ba=None; ja=-1
        if not es_recta(pts[i:min(i+6,n)],tol_a):
            for j in range(min(n-1,i+MAX),i+2,-1):
                if es_recta(pts[i:j+1],tol_a): continue
                b=intentar_arco(pts[i:j+1],tol_a)
                if b is not None: ba=b; ja=j; break
        if ba is not None and ja>jl+1:
            segs.append((pts[i],pts[ja],ba)); i=ja
        else:
            segs.append((pts[i],pts[jl],0.0)); i=jl
    return segs

# ═══════════════════════════════════════════════════
# LEER PUNTOS DE CUALQUIER ENTIDAD COM
# ═══════════════════════════════════════════════════

def leer_entidad(ent, verbose=False):
    """Retorna (pts_2d, es_cerrada) o ([], False) si no soportada."""
    tipo = ent.EntityName.upper()
    pts=[]; cerrada=False

    if 'SPLINE' in tipo:
        try: cerrada=bool(ent.Closed)
        except: pass

        # 1) FitPoints: estan SOBRE la curva (mejor opcion)
        n_fit = 0
        try:
            fp=list(ent.FitPoints)
            n_fit = len(fp)//3
            if len(fp)>=6:
                pts=[(fp[i],fp[i+1]) for i in range(0,len(fp)-2,3)]
                if verbose: info(f"  FitPoints: {n_fit} pts (sobre la curva)")
        except: pass

        # 2) Si no hay FitPoints: evaluar NURBS real con de Boor
        if len(pts)<2:
            if verbose: info(f"  FitPoints: {n_fit} — usando evaluacion NURBS")
            pts=evaluar_spline_com(ent, verbose=verbose)

    elif 'LWPOLYLINE' in tipo or ('POLYLINE' in tipo and 'SPLINE' not in tipo):
        coords=list(ent.Coordinates); nv=len(coords)//2
        pts=[(coords[i*2],coords[i*2+1]) for i in range(nv)]
        try: cerrada=bool(ent.Closed)
        except: pass
        if cerrada and len(pts)>1: pts.append(pts[0])

    elif tipo=='ACDBLINE':
        s=ent.StartPoint; e=ent.EndPoint
        pts=[(s[0],s[1]),(e[0],e[1])]

    elif 'ARC' in tipo and 'SPLINE' not in tipo:
        cx,cy=ent.Center[0],ent.Center[1]; r=ent.Radius
        a0=ent.StartAngle; a1=ent.EndAngle
        if a1<a0: a1+=2*math.pi
        n=max(8,int((a1-a0)*r/0.3))
        pts=[(cx+r*math.cos(a0+(a1-a0)*k/n), cy+r*math.sin(a0+(a1-a0)*k/n)) for k in range(n+1)]

    elif 'CIRCLE' in tipo:
        cx,cy=ent.Center[0],ent.Center[1]; r=ent.Radius
        n=max(16,int(2*math.pi*r/0.3))
        pts=[(cx+r*math.cos(2*math.pi*k/n), cy+r*math.sin(2*math.pi*k/n)) for k in range(n+1)]
        cerrada=True

    else:
        skip(f"tipo no soportado: {tipo}")

    return pts, cerrada

# ═══════════════════════════════════════════════════
# CREAR LWPOLYLINE EN AUTOCAD
# ═══════════════════════════════════════════════════

def crear_lwpoly(mspace, segs, cerrada, capa, color):
    if not segs: return None
    verts=[s[0] for s in segs]
    if not cerrada: verts.append(segs[-1][1])
    flat=[]
    for v in verts: flat+=list(v)
    arr=VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8, flat)
    try:
        lw=mspace.AddLightWeightPolyline(arr)
        lw.Closed=cerrada; lw.Layer=capa; lw.Color=color
        for i,(p0,p1,bulge) in enumerate(segs):
            if abs(bulge)>1e-10: lw.SetBulge(i,bulge)
        lw.Update()
        return lw
    except Exception as e:
        err(f"crear LWPOLYLINE: {e}"); return None

# ═══════════════════════════════════════════════════
# PROCESAR UNA ENTIDAD
# ═══════════════════════════════════════════════════

def procesar(ent, mspace, doc):
    tipo=ent.EntityName; capa=getattr(ent.dxf if hasattr(ent,'dxf') else ent,'Layer','0')
    try: capa=ent.Layer
    except: capa='0'

    # No procesar entidades ya en _ORIGINAL
    if cfg.ORIG_LAYER.upper() in capa.upper():
        skip(f"[{tipo}] {capa} — ya es _ORIGINAL, saltando"); return None

    # No re-procesar LWPOLYLINEs que ya son resultado _ARC (solo si NO son splines)
    sufijo_up = cfg.SUFIJO.upper()
    if capa.upper().endswith(sufijo_up) and 'LWPOLYLINE' in tipo.upper():
        skip(f"[{tipo}] {capa} — ya es LWPOLYLINE _ARC procesada, saltando"); return None

    pts, cerrada = leer_entidad(ent)
    n_orig=len(pts)
    if n_orig<2:
        skip(f"[{tipo}] {capa} — sin puntos"); return None

    largo=sum(dist2d(pts[i],pts[i+1]) for i in range(len(pts)-1))
    if largo<0.5:
        skip(f"[{tipo}] {capa} — muy corto ({largo:.2f}mm)"); return None

    # Paso 1: DP
    red=reducir_pts(pts, cfg.TOL_DP, cerrada)
    if not red or len(red)<2:
        err(f"[{tipo}] {capa} — DP sin resultado"); return None
    n_dp=len(red)

    # Quitar duplicado final para arc_fit
    arc_pts=red
    if cerrada and len(red)>2 and dist2d(red[0],red[-1])<cfg.TOL_ARCO:
        arc_pts=red[:-1]

    # Paso 2: Arc-fit
    segs=arc_fit(arc_pts)
    if not segs:
        err(f"[{tipo}] {capa} — arc_fit sin resultado"); return None

    n_lin=sum(1 for s in segs if s[2]==0.0)
    n_arc=sum(1 for s in segs if s[2]!=0.0)

    # Crear capa destino — no doblar el sufijo si ya lo tiene
    sufijo_up = cfg.SUFIJO.upper()
    if capa.upper().endswith(sufijo_up):
        capa_dst = capa          # ya tiene _ARC, redibujar en la misma capa
    else:
        capa_dst = capa + cfg.SUFIJO
    try: doc.Layers.Add(capa_dst)
    except: pass

    nueva=crear_lwpoly(mspace, segs, cerrada, capa_dst, cfg.COLOR)
    if nueva is None: return None
    # Original queda intacta en su capa — la nueva queda encima

    r1=(1-n_dp/n_orig)*100 if n_orig else 0
    ok(f"[{tipo:20}] {capa:22} | {n_orig}→{n_dp}pts({r1:.0f}%) → {len(segs)}segs ({n_lin}L+{n_arc}A)")
    return (n_orig, n_dp, len(segs), n_lin, n_arc)

# ═══════════════════════════════════════════════════
# MAIN — MENU INTERACTIVO
# ═══════════════════════════════════════════════════

def main():
    os.system("title REDIBUJA AutoCAD — DP + Arc-Fitter")

    header("REDIBUJA AutoCAD  v3  |  DP + ARC-FITTER")
    sep()
    log(f"  Convierte SPLINE / LWPOLYLINE / ARC / CIRCLE / LINE")
    log(f"  a LWPOLYLINE limpia con lineas + arcos (bulge)")
    log(f"  Original: queda intacta en su capa — la nueva se dibuja encima")
    sep()
    mostrar_config()

    # Conectar AutoCAD
    log()
    info("Conectando a AutoCAD...")
    try:
        acad=win32com.client.GetActiveObject("AutoCAD.Application")
        doc=acad.ActiveDocument
        ok(f"Conectado: {W}{doc.Name}{RST}")
    except Exception as e:
        err(f"No se pudo conectar: {e}")
        err("Asegurate de tener AutoCAD abierto con un dibujo.")
        input("\n  ENTER para salir...")
        sys.exit(1)

    mspace=doc.ModelSpace

    while True:
        log()
        sep()
        log(f"  {BLD}MENU{RST}")
        log(f"  {Y}1{RST} — Seleccionar en AutoCAD y redibujar")
        log(f"  {Y}2{RST} — Usar seleccion actual en AutoCAD")
        log(f"  {Y}3{RST} — Cambiar tolerancias (actual: DP={cfg.TOL_DP} ARCO={cfg.TOL_ARCO})")
        log(f"  {Y}5{RST} — {C}DIAGNOSTICO{RST}: inspeccionar 1 entidad seleccionada")
        log(f"  {Y}4{RST} — Deshacer ultimo (restaurar _ORIGINAL)")
        log(f"  {Y}0{RST} — Salir")
        sep()

        op=input(f"  {BLD}Opcion > {RST}").strip()

        if op=='0':
            log(f"\n  {G}Hasta luego.{RST}\n"); break

        elif op=='3':
            menu_tolerancias()

        elif op=='4':
            deshacer(doc, mspace)

        elif op=='5':
            diagnostico(doc)

        elif op in ('1','2'):
            entidades=[]

            if op=='1':
                log()
                log(f"  {BLD}>>> Ve a AutoCAD, SELECCIONA las piezas a redibujar,{RST}")
                log(f"  {BLD}    luego vuelve aqui y presiona ENTER.{RST}")
                log(f"  {DIM}    (SPLINE, LWPOLYLINE, ARC, CIRCLE, LINE){RST}")
                input()

            try:
                ss=doc.ActiveSelectionSet
                for i in range(ss.Count):
                    entidades.append(ss.Item(i))
                info(f"{len(entidades)} entidades capturadas")
            except Exception as e:
                err(f"Leyendo seleccion: {e}"); continue

            if not entidades:
                warn("Nada seleccionado."); continue

            # Preview: mostrar que tipos hay
            tipos={}
            for e in entidades:
                t=e.EntityName; tipos[t]=tipos.get(t,0)+1
            info("Tipos: " + "  ".join(f"{t}x{n}" for t,n in tipos.items()))
            log()
            sep()

            t0=time.time()
            n_ok=n_fail=0
            tot_o=tot_dp=tot_s=tot_l=tot_a=0

            for ent in entidades:
                try:
                    res=procesar(ent, mspace, doc)
                    if res:
                        n_ok+=1
                        no,nd,ns,nl,na=res
                        tot_o+=no; tot_dp+=nd; tot_s+=ns; tot_l+=nl; tot_a+=na
                    else:
                        n_fail+=1
                except Exception as e:
                    err(f"[{ent.EntityName}]: {e}")
                    traceback.print_exc()
                    n_fail+=1

            try: doc.Regen(1)
            except: pass

            sep()
            dt=time.time()-t0
            r1=(1-tot_dp/tot_o)*100   if tot_o  else 0
            r2=(1-tot_s/tot_dp)*100   if tot_dp else 0
            log(f"  {G}{BLD}RESULTADO:{RST}  OK={G}{n_ok}{RST}  Fallos={R}{n_fail}{RST}  Tiempo={dt:.1f}s")
            log(f"  Puntos  : {tot_o} → {tot_dp} ({r1:.0f}% reduccion DP)")
            log(f"  Segs    : {tot_dp} → {tot_s} ({r2:.0f}% reduccion arc-fit)")
            log(f"  Lineas  : {tot_l}   Arcos: {tot_a}")
            log(f"  {DIM}Original intacta en su capa — borra la original manualmente si todo OK{RST}")

        else:
            warn("Opcion invalida.")

def diagnostico(doc):
    """Inspecciona la primera entidad seleccionada en detalle."""
    header("DIAGNOSTICO — inspeccionar entidad")
    log()
    log(f"  {BLD}>>> Selecciona UNA entidad en AutoCAD y presiona ENTER{RST}")
    input()
    try:
        ss = doc.ActiveSelectionSet
        if ss.Count == 0:
            warn("Nada seleccionado."); return
        ent = ss.Item(0)
    except Exception as e:
        err(f"Leyendo seleccion: {e}"); return

    tipo = ent.EntityName
    capa = getattr(ent, 'Layer', '?')
    header(f"Entidad: {tipo}  |  Capa: {capa}")

    # Info basica
    if 'Spline' in tipo:
        try: log(f"  IsRational  : {ent.IsRational}")
        except: pass
        try: log(f"  IsPeriodic  : {ent.IsPeriodic}")
        except: pass
        try: log(f"  Closed      : {ent.Closed}")
        except: pass
        try: log(f"  Degree      : {ent.Degree}")
        except: pass
        try: log(f"  n CPs (attr): {ent.NumberOfControlPoints}")
        except: pass
        try:
            W = list(ent.Weights)
            log(f"  n Weights   : {len(W)}  (primeros 3: {W[:3]})")
        except Exception as e:
            log(f"  Weights     : no disponible ({e})")
        try:
            U = list(ent.Knots)
            log(f"  n Knots     : {len(U)}  (primeros 6: {[round(k,3) for k in U[:6]]})")
        except: pass
        try:
            fp = list(ent.FitPoints)
            n_fp = len(fp)//3
            log(f"  FitPoints   : {n_fp} puntos {'(disponibles)' if n_fp>0 else '(vacios)'}")
        except Exception as e:
            log(f"  FitPoints   : error — {e}")

    log()
    info("Evaluando puntos...")
    pts, cerrada = leer_entidad(ent, verbose=True)
    log(f"  Puntos extraidos: {len(pts)}  cerrada={cerrada}")
    if len(pts) >= 2:
        largo = sum(dist2d(pts[i], pts[i+1]) for i in range(len(pts)-1))
        log(f"  Largo aprox: {largo:.2f} mm")

    if len(pts) < 2:
        warn("No se pudieron extraer puntos."); return

    log()
    info(f"Aplicando DP (TOL_DP={cfg.TOL_DP})...")
    red = reducir_pts(pts, cfg.TOL_DP, cerrada)
    n_dp = len(red) if red else 0
    log(f"  Despues DP: {n_dp} puntos  ({(1-n_dp/len(pts))*100:.0f}% reduccion)")

    if not red or n_dp < 2:
        warn("DP elimino demasiados puntos — sube TOL_DP o revisa la curva."); return

    arc_pts = red
    if cerrada and len(red)>2 and dist2d(red[0],red[-1])<cfg.TOL_ARCO:
        arc_pts = red[:-1]

    log()
    info(f"Aplicando Arc-Fit (TOL_ARCO={cfg.TOL_ARCO}, TOL_LINEA={cfg.TOL_LINEA})...")
    segs = arc_fit(arc_pts)
    n_lin = sum(1 for s in segs if s[2]==0.0)
    n_arc = sum(1 for s in segs if s[2]!=0.0)
    log(f"  Segmentos: {len(segs)}  ({n_lin} lineas + {n_arc} arcos)")

    if n_arc == 0 and n_lin > 6:
        warn("0 arcos detectados — puede que la tolerancia sea muy alta")
        warn(f"Prueba TOL_ARCO mas chico, actual={cfg.TOL_ARCO}")
    if n_dp < 5 and n_lin == n_dp - 1:
        warn("DP muy agresivo — muy pocos puntos para detectar arcos")
        warn(f"Prueba TOL_DP mas chico, actual={cfg.TOL_DP}")

    log()
    log(f"  {G}{BLD}Resumen:{RST}  {len(pts)}pts -{G}DP{RST}-> {n_dp}pts -{C}ARC{RST}-> {len(segs)}segs ({n_lin}L+{n_arc}A)")

def deshacer(doc, mspace):
    """Mueve entidades de _ORIGINAL de vuelta a su capa original y borra _ARC."""
    header("DESHACER")
    warn("Esta funcion mueve entidades de _ORIGINAL de vuelta.")
    warn("No esta implementado automaticamente — hazlo manual en AutoCAD:")
    info("1. Selecciona todo en capa _ORIGINAL")
    info("2. Cambia su capa a la original")
    info("3. Borra las entidades _ARC")
    info("4. O usa Ctrl+Z en AutoCAD directamente.")

if __name__ == '__main__':
    main()

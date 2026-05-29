# DOCUMENTACIÓN COMPLETA — REDIBUJA AutoCAD v3
### DP + Arc-Fitter | Guía para programadores

---

## ÍNDICE
1. [¿Qué hace el proyecto?](#1-qué-hace-el-proyecto)
2. [Archivos del proyecto](#2-archivos-del-proyecto)
3. [¿Cómo funciona el .bat?](#3-cómo-funciona-el-bat)
4. [¿Cómo se conecta Python a AutoCAD?](#4-cómo-se-conecta-python-a-autocad)
5. [Arquitectura del código](#5-arquitectura-del-código)
6. [Módulo 1 — Consola con colores](#6-módulo-1--consola-con-colores)
7. [Módulo 2 — Configuración (Config)](#7-módulo-2--configuración-config)
8. [Módulo 3 — Geometría 2D](#8-módulo-3--geometría-2d)
9. [Módulo 4 — NURBS / Evaluación de Splines](#9-módulo-4--nurbs--evaluación-de-splines)
10. [Módulo 5 — Douglas-Peucker](#10-módulo-5--douglas-peucker)
11. [Módulo 6 — Arc-Fitter](#11-módulo-6--arc-fitter)
12. [Módulo 7 — Leer entidades de AutoCAD](#12-módulo-7--leer-entidades-de-autocad)
13. [Módulo 8 — Crear LWPOLYLINE](#13-módulo-8--crear-lwpolyline)
14. [Módulo 9 — Unir fragmentos](#14-módulo-9--unir-fragmentos)
15. [Módulo 10 — Pipeline completo](#15-módulo-10--pipeline-completo)
16. [Módulo 11 — Menú interactivo (main)](#16-módulo-11--menú-interactivo-main)
17. [Flujo completo de ejecución](#17-flujo-completo-de-ejecución)
18. [Tips de programador](#18-tips-de-programador)

---

## 1. ¿Qué hace el proyecto?

En AutoCAD, una pieza de vidrio puede estar dibujada como una **SPLINE** (curva matemática suave) con cientos de puntos de control. Cuando el fabricante la manda a una máquina CNC, esa máquina no entiende splines — solo entiende **líneas rectas** y **arcos de círculo**.

Este programa convierte automáticamente cualquier curva de AutoCAD en una **LWPOLYLINE** (polilínea ligera) compuesta por el mínimo número posible de segmentos de línea y arcos, manteniendo una tolerancia de error menor a 0.05mm.

**Entrada:** SPLINE / LWPOLYLINE / ARC / CIRCLE / LINE (cualquier entidad de AutoCAD)  
**Salida:** LWPOLYLINE nueva en un layer `NOMBRE_ARC`, con líneas + arcos codificados como "bulge"

El proceso tiene **3 etapas**:
```
Entidad AutoCAD
    ↓  [Leer puntos]
Lista de puntos 2D (X,Y)
    ↓  [Douglas-Peucker]
Lista reducida (mismo shape, menos puntos)
    ↓  [Arc-Fitter]
Lista de segmentos (línea o arco)
    ↓  [Crear LWPOLYLINE]
Nueva entidad en AutoCAD
```

---

## 2. Archivos del proyecto

```
redibujado/
├── autocad_redibuja.py      ← Código principal (TODO está aquí)
├── REDIBUJA_AUTOCAD.bat     ← Lanzador — doble clic para ejecutar
├── autocad_pipeline.py      ← Versión alternativa que lee archivos .DXF
                               (no requiere AutoCAD abierto, secundaria)
└── DOCUMENTACION_PROYECTO.md ← Este archivo
```

### ¿Qué archivo depende de qué?

| Archivo | Depende de | Requiere |
|---|---|---|
| `REDIBUJA_AUTOCAD.bat` | `autocad_redibuja.py` | Python instalado (`py -3`) |
| `autocad_redibuja.py` | `win32com.client` | AutoCAD abierto + pywin32 |
| `autocad_pipeline.py` | `ezdxf` | Solo Python (sin AutoCAD) |

### Instalar dependencias
```bash
pip install pywin32   # para win32com (conectar a AutoCAD)
pip install ezdxf     # para autocad_pipeline.py (opcional)
```

---

## 3. ¿Cómo funciona el .bat?

```bat
@echo off                          ← No mostrar cada comando en consola
chcp 65001 > nul                   ← Cambiar consola a UTF-8 (para tildes/ñ)
title REDIBUJA AutoCAD - DP + Arc-Fitter   ← Título de la ventana
color 0B                           ← Fondo negro (0), texto cyan brillante (B)
set PYTHONIOENCODING=utf-8         ← Python también usará UTF-8
py -3 "%~dp0autocad_redibuja.py"   ← Ejecutar el script
if errorlevel 1 (                  ← Si Python devolvió error...
    echo ERROR al ejecutar...      ← Mostrar mensaje
    pause                          ← Esperar tecla antes de cerrar
)
```

**Tip clave:** `%~dp0` es una variable especial de BAT que significa "la carpeta donde está este .bat". Así no importa desde dónde lo ejecutes — siempre encuentra el `.py` junto a él.

**`py -3`** busca cualquier Python 3.x instalado. Alternativas: `python`, `python3`.

**`color 0B`**: el primer dígito es el fondo (0=negro), el segundo es el texto (B=cyan). Otros: A=verde brillante, C=rojo, E=amarillo.

---

## 4. ¿Cómo se conecta Python a AutoCAD?

AutoCAD expone una **API COM** (Component Object Model) — un sistema de Windows que permite que cualquier programa se comunique con otro mediante objetos. Es como una interfaz de control remoto.

```python
import win32com.client

# Buscar AutoCAD ya abierto (no lanza uno nuevo)
acad = win32com.client.GetActiveObject("AutoCAD.Application")

# Acceder al documento activo
doc = acad.ActiveDocument

# Acceder al espacio del modelo (donde están los objetos dibujados)
mspace = doc.ModelSpace
```

**¿Qué es `"AutoCAD.Application"`?** Es el "ProgID" — un nombre registrado en Windows. Cuando AutoCAD se instala, se registra en el sistema operativo con ese nombre para que otros programas puedan encontrarlo.

**`GetActiveObject` vs `CreateObject`:**
- `GetActiveObject` → conecta a uno que YA está corriendo (lo que usamos)
- `CreateObject` → lanzaría un AutoCAD nuevo (no lo queremos)

**¿Por qué `win32com`?** Es la librería de Python que habla el protocolo COM de Windows. También se puede usar `comtypes`, pero `win32com` (parte de `pywin32`) es más popular.

---

## 5. Arquitectura del código

El archivo está dividido en módulos lógicos separados por comentarios `# ═══...`. Cada módulo es independiente del anterior, lo que facilita entender y modificar una parte sin romper las demás.

```
[Config]           → constantes globales
[Consola]          → funciones de impresión con color
[Geometría 2D]     → matemática pura (distancias, círculos, ángulos)
[NURBS/de Boor]    → evaluación de curvas spline
[Douglas-Peucker]  → reducción de puntos
[Arc-Fitter]       → detección de arcos
[Leer entidades]   → interfaz con AutoCAD (entrada)
[Crear LWPOLY]     → interfaz con AutoCAD (salida)
[Unir fragmentos]  → manejo de geometría "explotada"
[Pipeline]         → orquesta todos los pasos anteriores
[Main/Menú]        → interfaz de usuario
```

---

## 6. Módulo 1 — Consola con colores

```python
import os
os.system("")   # ← TRUCO: activa el soporte ANSI en Windows
```

**¿Por qué `os.system("")`?** Windows 10+ soporta códigos ANSI de color en la consola, pero solo después de que al menos UNA llamada al sistema los active. Este comando vacío lo activa sin hacer nada más.

```python
R  = "\033[91m"   # Rojo brillante
G  = "\033[92m"   # Verde brillante
Y  = "\033[93m"   # Amarillo
B  = "\033[94m"   # Azul
C  = "\033[96m"   # Cyan
W  = "\033[97m"   # Blanco brillante
DIM= "\033[2m"    # Texto apagado/dim
RST= "\033[0m"    # Reset — vuelve al color normal
BLD= "\033[1m"    # Negrita
```

**`\033`** es el carácter Escape en octal. Los códigos ANSI siempre empiezan con `ESC[`. Cuando la terminal los ve, no los imprime — cambia el color. El número después del `[` indica qué color:
- 9x = colores brillantes (90-97)
- 3x = colores normales (30-37)

```python
def ok(msg):   print(f"  {G}OK{RST}  {msg}", flush=True)
#                          ↑verde        ↑reset
```

**`flush=True`**: Python por defecto acumula la salida en un buffer y la imprime en lotes. Con `flush=True` fuerza impresión inmediata — importante para ver el progreso en tiempo real.

---

## 7. Módulo 2 — Configuración (Config)

```python
class Config:
    TOL_DP    = 0.05    # mm — tolerancia Douglas-Peucker
    TOL_ARCO  = 0.05    # mm — tolerancia del arc-fitter
    TOL_LINEA = 0.001   # mm — para detectar rectas "exactas"
    RADIO_MAX = 5000.0  # mm — radio máximo de un arco válido
    COLOR     = 5       # índice de color AutoCAD (5=azul)
    SUFIJO    = "_ARC"  # se agrega al nombre del layer de destino
    ORIG_LAYER= "_ORIGINAL"  # layer de backup (para no reprocesar)

cfg = Config()   # instancia global — todos acceden a cfg.TOL_DP etc.
```

**¿Por qué usar una clase en vez de variables globales sueltas?**  
Agrupa todo en un namespace. `cfg.TOL_DP` es más claro que `TOL_DP` suelto, y es fácil pasar `cfg` como objeto a funciones si hace falta.

**¿Por qué los valores actuales?**
- `TOL_DP = 0.05mm`: el DP elimina puntos que desvían menos de 0.05mm de la línea recta entre sus vecinos. Con 0.05mm en una pieza de vidrio (que mide metros) es prácticamente imperceptible.
- `TOL_ARCO = 0.05mm`: el arc-fitter acepta un arco si todos sus puntos están a menos de 0.05mm del círculo ajustado.
- `TOL_LINEA = 0.001mm`: para declarar que algo es una recta EXACTA, usamos una tolerancia mucho más estricta (casi cero).
- `RADIO_MAX = 5000mm`: un arco de radio > 5 metros es prácticamente una recta. Lo rechazamos para evitar arcos "fantasma" en rectas casi perfectas.

---

## 8. Módulo 3 — Geometría 2D

### `dist2d(a, b)` — distancia entre dos puntos
```python
def dist2d(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)
```
Teorema de Pitágoras. `a` y `b` son tuplas `(x, y)`.

### `dist_linea(pt, p0, p1)` — distancia de un punto a una recta
```python
def dist_linea(pt, p0, p1):
    dx = p1[0]-p0[0]
    dy = p1[1]-p0[1]
    L  = math.sqrt(dx*dx + dy*dy)
    if L < 1e-12: return dist2d(pt, p0)   # p0==p1, evita división por cero
    return abs(dy*pt[0] - dx*pt[1] + p1[0]*p0[1] - p1[1]*p0[0]) / L
```
Esta es la fórmula de distancia punto-recta usando el **producto vectorial**. La fórmula general de una recta `Ax + By + C = 0` es:
- `A = dy`, `B = -dx`, `C = p1.x*p0.y - p1.y*p0.x`
- `distancia = |A*x + B*y + C| / sqrt(A² + B²)`

Es fundamental para Douglas-Peucker.

### `circulo_3pts(p0, pm, p1)` — círculo que pasa por 3 puntos
```python
def circulo_3pts(p0, pm, p1):
    # Traduce a coordenadas relativas a p0
    ax=pm[0]-p0[0]; ay=pm[1]-p0[1]
    bx=p1[0]-p0[0]; by=p1[1]-p0[1]
    det = ax*by - ay*bx          # determinante — es 0 si son colineales
    if abs(det) < 1e-10: return None
    d0 = ax*ax+ay*ay; d1 = bx*bx+by*by
    cx = (d0*by - d1*ay) / (2*det)
    cy = (d1*ax - d0*bx) / (2*det)
    return (p0[0]+cx, p0[1]+cy, math.sqrt(cx*cx+cy*cy))
```
**Lógica:** El centro de un círculo equidista de los 3 puntos. Hay dos ecuaciones (las mediatrices de p0-pm y p0-p1) con dos incógnitas (cx, cy). Se resuelve el sistema con el determinante de la matriz 2x2.

Si `det ≈ 0`, los 3 puntos son colineales (están en línea recta) — no forman un círculo.

### `calcular_bulge(p0, pm, p1)` — el valor más importante del proyecto
```python
def calcular_bulge(p0, pm, p1):
    circ = circulo_3pts(p0, pm, p1)
    cx, cy, r = circ
    a0 = math.atan2(p0[1]-cy, p0[0]-cx)   # ángulo de p0 desde el centro
    a1 = math.atan2(p1[1]-cy, p1[0]-cx)   # ángulo de p1 desde el centro
    am = math.atan2(pm[1]-cy, pm[0]-cx)   # ángulo de pm desde el centro
    d_ccw = ang_norm(a1-a0)               # arco CCW de p0 a p1
    am_r  = ang_norm(am-a0)               # posición de pm en ese arco
    # Si pm está dentro del arco CCW → arco es CCW (positivo)
    if am_r <= d_ccw+1e-9: theta=d_ccw;  sign=1
    else:                  theta=2*math.pi-d_ccw; sign=-1
    return math.tan(theta/4) * sign
```

**¿Qué es el bulge?** Es la forma en que AutoCAD codifica arcos dentro de una LWPOLYLINE. Para cada vértice de la polilínea:
- `bulge = 0` → el segmento siguiente es una **línea recta**
- `bulge ≠ 0` → el segmento siguiente es un **arco**

La fórmula es: `bulge = tan(θ/4)` donde θ es el ángulo central del arco.

| bulge | significado |
|---|---|
| `0` | línea recta |
| `1` | semicírculo (180°) en sentido CCW |
| `-1` | semicírculo en sentido CW |
| `0.414` | arco de 90° CCW |
| `> 1` | arco > 180° (crea bucle — rechazado) |

**CCW** = Counter-ClockWise = sentido antihorario  
**CW** = ClockWise = sentido horario

---

## 9. Módulo 4 — NURBS / Evaluación de Splines

Este es el módulo más técnico. AutoCAD almacena las splines como curvas **NURBS** (Non-Uniform Rational B-Spline). El problema: los **puntos de control** de una NURBS NO están sobre la curva, son solo "imanes" que la atraen. Para obtener puntos SOBRE la curva hay que evaluar matemáticamente.

### Estructura de una NURBS
Una NURBS queda definida por:
- **P** = puntos de control `[(x0,y0), (x1,y1), ...]`
- **W** = pesos `[w0, w1, ...]` (para NURBS racionales, afectan la atracción)
- **U** = vector de knots `[u0, u1, u2, ...]` (parámetros donde la curva "se dobla")
- **p** = grado (normalmente 3 para cúbicas)

La fórmula para obtener un punto de la curva en el parámetro `t` es:
```
C(t) = Σ(Ni,p(t) * wi * Pi) / Σ(Ni,p(t) * wi)
```
donde `Ni,p(t)` son las funciones base B-spline.

### `nurbs_span(n, p, t, U)` — encontrar el intervalo del knot
```python
def nurbs_span(n, p, t, U):
    if t >= U[n+1]: return n
    lo, hi = p, n+1
    mid = (lo+hi)//2
    while t < U[mid] or t >= U[mid+1]:
        if t < U[mid]: hi = mid
        else:          lo = mid
        mid = (lo+hi)//2
    return mid
```
Búsqueda binaria para encontrar el índice `i` tal que `U[i] <= t < U[i+1]`. Solo los `p+1` puntos de control alrededor de ese intervalo influyen en el punto (eso es lo eficiente de las B-splines — soporte local).

### `nurbs_basis(i, t, p, U)` — funciones base B-spline
```python
def nurbs_basis(i, t, p, U):
    N = [0.0]*(p+1); N[0] = 1.0
    left  = [0.0]*(p+1)
    right = [0.0]*(p+1)
    for j in range(1, p+1):
        left[j]  = t - U[i+1-j]
        right[j] = U[i+j] - t
        saved = 0.0
        for r in range(j):
            denom = right[r+1] + left[j-r]
            temp  = (N[r]/denom) if abs(denom)>1e-15 else 0.0
            N[r]  = saved + right[r+1]*temp
            saved = left[j-r]*temp
        N[j] = saved
    return N
```
Algoritmo de Cox-de Boor en su forma triangular. Calcula las `p+1` funciones base de grado `p` en el punto `t`. Es uno de los algoritmos numéricos más estables para esto.

### `evaluar_spline_com(ent)` — leer la spline de AutoCAD
```python
U = list(ent.Knots)          # vector de knots desde AutoCAD
p = int(ent.Degree)          # grado del spline
W = list(ent.Weights)        # pesos (solo rational)
# Si es polynomial (sin pesos):
W = [1.0] * (len(U) - p - 1)
# Obtener puntos de control:
P = [ent.GetControlPoint(i) for i in range(n_cp)]
```

**Truco importante:** `ent.NumberOfControlPoints` a veces devuelve un número incorrecto (off-by-one bug de AutoCAD COM). La forma correcta de saber cuántos CPs hay es: `n_cp = len(U) - p - 1`. Esta es la relación matemática entre el vector de knots, el grado y el número de puntos de control.

**Splines racionales vs polinomiales:**
- **Racional** (`IsRational=True`): tiene pesos distintos → `.Weights` disponible
- **Polinomial** (`IsRational=False`): todos los pesos = 1.0 → `.Weights` lanza excepción

Por eso lo envolvemos en `try/except` y asignamos pesos = 1.0 si falla.

**Muestreo adaptativo:**
```python
knots_u = sorted(set(U))   # knots únicos (sin repetidos)
N_seg = 16                  # 16 puntos por intervalo entre knots
for ki in range(len(knots_u)-1):
    # Muestrea 16 puntos uniformes en cada segmento del knot
```
Entre cada par de knots consecutivos, la curva es una porción suave. Muestreamos 16 puntos por segmento → densidad suficiente para luego aplicar DP.

---

## 10. Módulo 5 — Douglas-Peucker

El algoritmo **Douglas-Peucker** (DP) es el corazón de la reducción de puntos. Dado un conjunto de puntos que aproximan una curva, elimina los que "no aportan" — los que están muy cerca de la línea recta entre sus vecinos.

### `dp(pts, tol)` — algoritmo recursivo

```python
def dp(pts, tol):
    if len(pts) <= 2: return list(pts)   # caso base: ya no hay nada que eliminar
    
    md = 0; mi = 0
    p0 = pts[0]; p1 = pts[-1]
    
    # Encontrar el punto más alejado de la línea p0-p1
    for i in range(1, len(pts)-1):
        d = dist_linea(pts[i], p0, p1)
        if d > md: md = d; mi = i
    
    if md > tol:
        # El punto más alejado supera la tolerancia → DIVIDIR ahí
        izquierda = dp(pts[:mi+1], tol)   # recursión en la mitad izquierda
        derecha   = dp(pts[mi:],   tol)   # recursión en la mitad derecha
        return izquierda[:-1] + derecha   # unir (sin duplicar el punto del medio)
    else:
        # Ningún punto supera tol → todos son "superfluos", guardar solo extremos
        return [pts[0], pts[-1]]
```

**Visualización del algoritmo:**
```
Puntos: A . . . . B . . C . . . . . D
         ↑ p0                       ↑ p1

Paso 1: ¿Qué punto se aleja más de la línea A-D?
        → C (se aleja 0.3mm > tol=0.05mm) → dividir en C

Paso 2: Recursión en A...C y C...D
        En A...C: ninguno se aleja más de 0.05mm → guardar solo A,C
        En C...D: igual → guardar solo C,D

Resultado: A, C, D  (de 8 puntos a 3)
```

### `reducir_pts(pts, tol, cerrada)` — 3 pasadas
```python
def reducir_pts(pts, tol, cerrada):
    r = dp(pts, tol*2)          # 1a pasada: tolerancia doble (agresiva)
    if len(r) > 4: r = dp(r, tol)      # 2a pasada: tolerancia exacta
    if len(r) > 4: r = dp(r, tol*0.5)  # 3a pasada: más fina
    return r
```

**¿Por qué 3 pasadas?** Con una sola pasada, DP puede preservar puntos que parecen importantes individualmente pero que en conjunto son redundantes. La primera pasada con `tol*2` hace una reducción rápida; las siguientes refinan. Viene del script original de Rhino.

---

## 11. Módulo 6 — Arc-Fitter

Este módulo toma los puntos reducidos por DP y los convierte en segmentos de línea o arco.

### `es_recta(pts, tol)`
```python
def es_recta(pts, tol):
    if len(pts) <= 2: return True
    p0=pts[0]; p1=pts[-1]
    for pt in pts[1:-1]:
        if dist_linea(pt, p0, p1) > tol: return False
    return True
```
Todos los puntos intermedios deben estar a menos de `tol` de la línea p0-p1.

### `intentar_arco(pts_z, tol)` — el filtro más importante
```python
def intentar_arco(pts_z, tol):
    if len(pts_z)<3 or es_recta(pts_z,tol): return None
    p0=pts_z[0]; p1=pts_z[-1]
    
    # 1) Encontrar la sagitta (máxima desviación del arco)
    sagitta_real = 0; pm_idx = len(pts_z)//2
    for idx in range(1, len(pts_z)-1):
        d = dist_linea(pts_z[idx], p0, p1)
        if d > sagitta_real:
            sagitta_real = d; pm_idx = idx
    pm = pts_z[pm_idx]   # ← punto de máxima desviación (no el del medio)
    
    # 2) Filtros de calidad
    MIN_SAGITTA_ABS   = tol * 4       # mínimo absoluto de curvatura
    MIN_SAGITTA_RATIO = 0.008         # mínimo 0.8% de la cuerda
    cuerda = dist2d(p0, p1)
    if sagitta_real < MIN_SAGITTA_ABS: return None   # demasiado plano
    if cuerda>1.0 and sagitta_real/cuerda < MIN_SAGITTA_RATIO: return None
    
    # 3) Rechazar curvas en S (puntos en ambos lados de la cuerda)
    lados = [math.copysign(1, (p1[0]-p0[0])*(pt[1]-p0[1]) 
                              -(p1[1]-p0[1])*(pt[0]-p0[0]))
             for pt in pts_z[1:-1]]
    if len(set(lados)) > 1: return None   # curva en S → no es arco
    
    # 4) Ajustar círculo y verificar que TODOS los puntos queden sobre él
    circ = circulo_3pts(p0, pm, p1)
    cx, cy, r = circ
    if r > cfg.RADIO_MAX or r < 0.001: return None
    for pt in pts_z:
        if abs(math.sqrt((pt[0]-cx)**2+(pt[1]-cy)**2)-r) > tol: return None
    
    # 5) Calcular bulge
    bulge = calcular_bulge(p0, pm, p1)
    if abs(bulge) > 0.9999: return None   # rechazar arcos >= 180°
    return bulge
```

**La sagitta** es la distancia desde el punto medio de la cuerda hasta el arco — mide qué tan "curvo" es el arco. Si es muy pequeña, el arco es casi una recta y el error de redibujarlo como línea es despreciable.

**¿Por qué `pm` es el punto de máxima desviación y no el del medio?** Si `pm` cae en una zona de inflexión (curva en S), el círculo ajustado sería incorrecto. El punto de máxima desviación siempre está en la "cima" del arco.

**Check de lados:** El producto vectorial `(p1-p0) × (pt-p0)` es positivo si `pt` está a la izquierda de la recta p0→p1, negativo si está a la derecha. Si hay puntos en ambos lados → es una curva en S, no un arco único.

### `arc_fit(pts)` — el algoritmo greedy
```python
def arc_fit(pts):
    segs=[]; n=len(pts); i=0
    tol_a=cfg.TOL_ARCO; tol_l=cfg.TOL_LINEA
    while i < n-1:
        MAX = 150   # máximo de puntos a cubrir por un segmento
        
        # Buscar la LÍNEA más larga desde pts[i]
        jl = i+1
        for j in range(min(n-1, i+MAX), i+1, -1):   # busca de atrás hacia adelante
            if es_recta(pts[i:j+1], tol_l): jl=j; break
        
        # Buscar el ARCO más largo desde pts[i]
        ba=None; ja=-1
        if not es_recta(pts[i:min(i+6,n)], tol_a):   # si los primeros puntos no son recta
            for j in range(min(n-1, i+MAX), i+2, -1):
                if es_recta(pts[i:j+1], tol_a): continue   # un arco no es una recta
                b = intentar_arco(pts[i:j+1], tol_a)
                if b is not None: ba=b; ja=j; break
        
        # El arco gana si cubre MÁS puntos que la línea (al menos 2 más)
        if ba is not None and ja > jl+1:
            segs.append((pts[i], pts[ja], ba)); i=ja
        else:
            segs.append((pts[i], pts[jl], 0.0)); i=jl
    return segs
```

**Estrategia greedy (voraz):** Desde cada posición `i`, intentar cubrir la mayor cantidad de puntos posible con un solo segmento (ya sea línea o arco). Avanzar al final del segmento y repetir.

**¿Por qué buscar de atrás hacia adelante?** Queremos el segmento MÁS LARGO posible. Si buscamos de adelante, encontramos el primero que funciona (puede ser corto). Buscando de atrás, encontramos el más largo directamente.

**La condición `ja > jl+1`:** El arco solo "gana" si cubre al menos 2 puntos más que la mejor línea. Si un arco cubre 5 puntos y la línea cubre 4, preferimos la línea (más simple). El arco debe justificar su mayor complejidad cubriendo significativamente más puntos.

---

## 12. Módulo 7 — Leer entidades de AutoCAD

```python
def leer_entidad(ent, verbose=False):
    tipo = ent.EntityName.upper()
```

El `EntityName` de AutoCAD devuelve el tipo interno:
- `"AcDbSpline"` → spline
- `"AcDbPolyline"` o `"AcDbLWPolyline"` → polilínea
- `"AcDbLine"` → línea recta
- `"AcDbArc"` → arco
- `"AcDbCircle"` → círculo

**Para SPLINE** — dos estrategias (FitPoints > NURBS):
```python
# Opción 1: FitPoints (si existen) — están SOBRE la curva
fp = list(ent.FitPoints)   # lista plana [x0,y0,z0, x1,y1,z1, ...]
pts = [(fp[i], fp[i+1]) for i in range(0, len(fp)-2, 3)]   # cada 3 valores
```
Los FitPoints son puntos que el usuario usó para definir la spline. Están exactamente sobre la curva — son la mejor fuente de datos.

```python
# Opción 2: NURBS (si no hay FitPoints)
pts = evaluar_spline_com(ent, verbose=verbose)
```

**Para LWPOLYLINE:**
```python
coords = list(ent.Coordinates)   # lista plana [x0,y0, x1,y1, ...]
pts = [(coords[i*2], coords[i*2+1]) for i in range(len(coords)//2)]
```
Importante: `Coordinates` no incluye el bulge. Si la polilínea tiene arcos (bulge), al leerla solo obtenemos los vértices, no los arcos → el arc-fitter los re-detectará.

**Para ARC:**
```python
cx,cy = ent.Center[0], ent.Center[1]
r = ent.Radius
a0 = ent.StartAngle; a1 = ent.EndAngle
n = max(8, int((a1-a0)*r/0.3))   # puntos cada 0.3mm de arco
pts = [(cx+r*math.cos(a0+(a1-a0)*k/n), cy+r*math.sin(...)) for k in range(n+1)]
```
Un arco se muestrea en puntos. La densidad `r/0.3` asegura al menos un punto cada 0.3mm.

---

## 13. Módulo 8 — Crear LWPOLYLINE

```python
def crear_lwpoly(mspace, segs, cerrada, capa, color):
    # 1) Extraer todos los vértices
    verts = [s[0] for s in segs]              # punto de inicio de cada segmento
    if not cerrada: verts.append(segs[-1][1]) # + punto final del último
    
    # 2) Aplanar en lista 1D [x0,y0, x1,y1, ...]
    flat = []
    for v in verts: flat += list(v)
    
    # 3) Convertir a VARIANT (tipo que AutoCAD COM entiende)
    arr = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)
    #                      ↑ array              ↑ double (64 bits)
    
    # 4) Crear la polilínea
    lw = mspace.AddLightWeightPolyline(arr)
    lw.Closed = cerrada
    lw.Layer = capa
    lw.Color = color
    
    # 5) Asignar bulges (arcos)
    for i, (p0, p1, bulge) in enumerate(segs):
        if abs(bulge) > 1e-10:      # solo si es arco (bulge ≠ 0)
            lw.SetBulge(i, bulge)   # índice del vértice + valor bulge
    
    lw.Update()   # forzar actualización visual en AutoCAD
```

**¿Qué es `VARIANT`?** El protocolo COM de Windows tiene sus propios tipos de datos. Python usa sus tipos nativos (`list`, `float`), pero AutoCAD espera tipos COM. `VARIANT` es el envoltorio que hace la conversión:
- `pythoncom.VT_ARRAY` = "esto es un array"
- `pythoncom.VT_R8` = "de números reales de 64 bits (double)"

**`SetBulge(i, bulge)`:** Le dice a AutoCAD que el segmento que comienza en el vértice `i` es un arco con ese valor de bulge. Solo los segmentos con `abs(bulge) > 0` son arcos; los demás son líneas automáticamente.

---

## 14. Módulo 9 — Unir fragmentos

Cuando una pieza está "explotada" (por ejemplo, un contorno dividido en 50 segmentos pequeños, uno por entidad), `unir_cadenas` los junta en orden.

```python
TOL_UNION = 1.0   # mm — si dos extremos están a menos de 1mm, se consideran conectados

def unir_cadenas(lista_pts_cerrada):
    frags  = [list(p) for p, _ in lista_pts_cerrada]  # copia de cada fragmento
    cerr   = [c for _, c in lista_pts_cerrada]
    usados = [False] * n   # registro de qué fragmentos ya se incorporaron
    cadenas = []
    
    for i0 in range(n):
        if usados[i0]: continue
        cadena = list(frags[i0])
        usados[i0] = True
        
        # Extender la cadena por el FINAL
        while True:
            p_fin = cadena[-1]
            for j in range(n):
                if usados[j]: continue
                if dist2d(frags[j][0], p_fin) < TOL_UNION:
                    cadena.extend(frags[j][1:])        # conecta normal
                    usados[j] = True; break
                elif dist2d(frags[j][-1], p_fin) < TOL_UNION:
                    cadena.extend(reversed(frags[j])[1:])  # conecta invertido
                    usados[j] = True; break
```

**Soporte de reversión:** Si el fragmento j tiene su `inicio` cerca del `final` de la cadena → se conecta normal. Si el `final` de j está cerca del `final` de la cadena → j se invierte antes de conectar. Esto maneja fragmentos que están al revés.

**Detección de cadena cerrada:**
```python
es_cerrada = dist2d(cadena[0], cadena[-1]) < TOL_UNION * 2
if es_cerrada and dist2d(cadena[0], cadena[-1]) > 1e-6:
    cadena.append(cadena[0])   # cerrar explícitamente
```

---

## 15. Módulo 10 — Pipeline completo

```python
def pipeline_pts(pts, cerrada, capa, mspace, doc, n_orig_display=None):
    # Paso 1: filtro de longitud mínima
    largo = sum(dist2d(pts[i], pts[i+1]) for i in range(len(pts)-1))
    if largo < 0.5: return None   # menos de 0.5mm → ignorar
    
    # Paso 2: Douglas-Peucker
    red = reducir_pts(pts, cfg.TOL_DP, cerrada)
    
    # Paso 3: Arc-Fit
    segs = arc_fit(arc_pts)
    
    # Paso 4: Determinar capa destino
    capa_dst = capa if capa.upper().endswith("_ARC") else capa + "_ARC"
    doc.Layers.Add(capa_dst)   # crear layer si no existe
    
    # Paso 5: Crear entidad en AutoCAD
    nueva = crear_lwpoly(mspace, segs, cerrada, capa_dst, cfg.COLOR)
    
    return (n_orig, n_dp, len(segs), n_lin, n_arc)
```

### `procesar_grupo` — manejo inteligente por capa
```python
def procesar_grupo(ents, mspace, doc):
    # Si hay 1 sola entidad: pipeline directo
    if len(lista_pc) == 1:
        res = pipeline_pts(...)
    else:
        # Múltiples entidades en la misma capa → intentar unir
        cadenas = unir_cadenas(lista_pc)
        for pts_c, cerrada_c in cadenas:
            res = pipeline_pts(pts_c, cerrada_c, ...)
```

La lógica de agrupación por capa es clave:
```python
from collections import defaultdict
por_capa = defaultdict(list)
for ent in entidades:
    por_capa[ent.Layer].append(ent)
```
`defaultdict(list)` crea automáticamente una lista vacía para cada clave nueva — no hay que verificar si la clave existe antes de hacer `.append()`.

---

## 16. Módulo 11 — Menú interactivo (main)

```python
def main():
    # Conectar AutoCAD
    acad = win32com.client.GetActiveObject("AutoCAD.Application")
    doc  = acad.ActiveDocument
    mspace = doc.ModelSpace
    
    while True:
        op = input("Opcion > ")
        
        if op == '1':
            # El usuario va a AutoCAD, selecciona, vuelve y presiona ENTER
            input()   # esperar ENTER
            ss = doc.ActiveSelectionSet   # capturar lo seleccionado
            
        elif op == '2':
            # Usar selección ya hecha
            ss = doc.ActiveSelectionSet
        
        elif op == '3':
            # Cambiar tolerancias
            menu_tolerancias()
        
        elif op == '5':
            # Diagnóstico detallado de 1 entidad
            diagnostico(doc)
```

**`doc.ActiveSelectionSet`:** AutoCAD mantiene el conjunto de entidades seleccionadas actualmente. Este comando lo captura en Python. Si el usuario presionó `Ctrl+A` en AutoCAD antes de volver al script, aquí estarán todas las entidades.

**`doc.Regen(1)`:** Fuerza a AutoCAD a re-renderizar el dibujo. El `1` es la constante `acActiveViewport` — regenerar solo el viewport activo.

---

## 17. Flujo completo de ejecución

```
Usuario doble-clica REDIBUJA_AUTOCAD.bat
    ↓
Windows ejecuta: py -3 autocad_redibuja.py
    ↓
Python importa win32com, se conecta a AutoCAD.Application
    ↓
Muestra menú → usuario elige opción 1 o 2
    ↓
Lee doc.ActiveSelectionSet → lista de entidades COM
    ↓
Agrupa entidades por ent.Layer → defaultdict
    ↓
Para cada capa:
    ├─ 1 entidad → procesar()
    │      ↓ leer_entidad() → pts[]
    │      ↓ pipeline_pts()
    └─ N entidades → procesar_grupo()
           ↓ leer_entidad() para cada una
           ↓ unir_cadenas() → cadenas continuas
           ↓ pipeline_pts() para cada cadena
    ↓
pipeline_pts():
    ↓ reducir_pts() → DP 3 pasadas
    ↓ arc_fit() → segs [(p0,p1,bulge), ...]
    ↓ doc.Layers.Add(capa+"_ARC")
    ↓ crear_lwpoly() → mspace.AddLightWeightPolyline()
    ↓ SetBulge(i, bulge) para cada arco
    ↓ lw.Update()
    ↓
doc.Regen(1)  → AutoCAD actualiza la pantalla
Muestra estadísticas
```

---

## 18. Tips de programador

### Tip 1: Divide el código en módulos con responsabilidad única
Cada función hace UNA cosa. `dist_linea` solo calcula una distancia. `arc_fit` solo detecta segmentos. `crear_lwpoly` solo crea la entidad. Así cuando algo falla, sabes exactamente dónde buscar.

### Tip 2: Usa nombres descriptivos, no comentarios
```python
# MAL:
def f(a, b, t):
    # calcula si todos los puntos de a están a menos de t de la recta a[0]-a[-1]
    ...

# BIEN:
def es_recta(pts, tol):
    ...
```
El código bien nombrado se lee como prosa. Los comentarios son para el POR QUÉ, no el QUÉ.

### Tip 3: El manejo de errores debe ser específico
```python
# MAL — silencia TODOS los errores:
try:
    W = list(ent.Weights)
except:
    W = []

# BIEN — documenta qué error esperas:
try:
    W = list(ent.Weights)
except Exception:
    pass   # polynomial spline — no tiene pesos, es esperado
```

### Tip 4: `flush=True` en output de progreso
Siempre que imprimas progreso de un proceso largo, usa `flush=True`. Sin esto, Python puede acumular toda la salida y mostrarla al final — inútil para ver el progreso en tiempo real.

### Tip 5: Las interfaces COM son inestables — defensividad
```python
try:    capa = ent.Layer
except: capa = '0'   # fallback seguro
```
Las APIs COM (AutoCAD, Excel, Word) pueden lanzar excepciones por razones oscuras. Siempre protege cada acceso a propiedades de objetos COM.

### Tip 6: Búsqueda greedy con búsqueda inversa
En `arc_fit` buscamos "el segmento más largo que funcione". La forma eficiente:
```python
for j in range(MAX, i+1, -1):   # de mayor a menor
    if funciona(pts[i:j+1]): 
        mejor = j; break   # el primer que funciona desde atrás = el más largo
```
Si buscáramos de adelante hacia atrás, tendríamos que recorrer todo.

### Tip 7: defaultdict elimina el "inicializar si no existe"
```python
# Sin defaultdict:
if capa not in por_capa:
    por_capa[capa] = []
por_capa[capa].append(ent)

# Con defaultdict(list):
por_capa[capa].append(ent)   # crea la lista automáticamente si no existe
```

### Tip 8: Separación entre lógica y efecto
`pipeline_pts` aplica la matemática y TAMBIÉN crea la entidad en AutoCAD. Idealmente serían dos funciones separadas (una que procesa, otra que dibuja). Pero para proyectos pequeños, la separación práctica entre "cálculo" y "creación en AutoCAD" en funciones distintas ya es suficiente.

### Tip 9: Testear con datos conocidos
Para verificar `calcular_bulge`: un semicírculo de 90° debe dar `bulge = tan(90°/4) = tan(22.5°) ≈ 0.414`. Puedes verificarlo en Python:
```python
import math
p0 = (1, 0)
pm = (0, 1)   # 90° CCW
p1 = (-1, 0)
print(calcular_bulge(p0, pm, p1))   # debe dar ≈ 1.0 (180°)
```

### Tip 10: Las tolerancias son tradeoffs
| Parámetro | Más alto → | Más bajo → |
|---|---|---|
| `TOL_DP` | Menos puntos, posible deformación | Más puntos, más fiel |
| `TOL_ARCO` | Menos arcos (más líneas), más rápido | Más arcos, más exacto |
| `TOL_LINEA` | Líneas "más flexibles" (pueden curvar un poco) | Solo rectas perfectas |
| `MIN_SAGITTA_ABS` | Menos falsos arcos | Puede perder arcos reales muy suaves |

Los valores actuales (0.05mm) están calibrados para piezas de vidrio de 1-3m donde 0.05mm es indistinguible visualmente y cumple tolerancias de fabricación.

---

## Glosario técnico

| Término | Definición |
|---|---|
| **LWPOLYLINE** | LightWeight Polyline — polilínea "ligera" de AutoCAD, eficiente en memoria. Puede contener líneas y arcos (vía bulge). |
| **Bulge** | Valor numérico en cada vértice de una LWPOLYLINE. `0` = línea, `tan(θ/4)` = arco de ángulo θ. |
| **NURBS** | Non-Uniform Rational B-Spline — tipo de curva matemática suave. "Rational" = tiene pesos. "Non-uniform" = los knots no están igualmente espaciados. |
| **Knot vector** | Lista de parámetros que definen dónde la curva NURBS "se dobla" o tiene continuidad reducida. |
| **Sagitta** | Distancia desde el punto medio de la cuerda de un arco hasta el arco mismo. Mide la "altura" de la curva. |
| **Douglas-Peucker** | Algoritmo de simplificación de polilíneas. Garantiza que el resultado no se aleja más de `tol` de ningún punto original. |
| **COM** | Component Object Model — protocolo de Microsoft para comunicación entre aplicaciones. AutoCAD, Excel, Word lo usan. |
| **Greedy** | Estrategia de algoritmo que toma siempre la mejor opción local en cada paso, sin backtracking. |
| **FitPoints** | Puntos que el usuario dibujó sobre la curva al crear la spline en AutoCAD. Están SOBRE la curva (a diferencia de los puntos de control). |
| **de Boor** | Algoritmo numérico estable para evaluar una curva B-spline o NURBS en un parámetro dado. |

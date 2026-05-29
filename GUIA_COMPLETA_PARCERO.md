# GUÍA COMPLETA — REDIBUJA AUTOCAD
## Todo lo que necesitás saber, explicado como entre parceros 🧠

---

> **¿Para quién es esto?** Para vos, que querés entender QUÉ hace este código, POR QUÉ funciona así, y cómo convertirlo en una herramienta que le podés dar a cualquier cliente sin que tenga que tocar ni una línea de código.

---

## PRIMERO LO PRIMERO — ¿Qué hace este proyecto en una frase?

Agarra cualquier curva de AutoCAD (spline, arco, polilínea, lo que sea), la convierte al **mínimo número posible de segmentos** (líneas rectas + arcos) sin que se deforme, y la deja en un layer aparte limpio y listo para fabricación.

Es básicamente un **"limpiador inteligente de geometría"** para AutoCAD.

---

## EL PANORAMA GENERAL — cómo encajan las piezas

```
REDIBUJA_AUTOCAD.bat
    └── llama a → autocad_redibuja.py
                      └── se conecta a → AutoCAD (ya abierto)
                                              └── lee entidades seleccionadas
                                              └── crea nuevas entidades limpias
```

Hay otro archivo `autocad_pipeline.py` que hace lo mismo pero leyendo archivos `.DXF` directamente sin AutoCAD abierto. Es la versión alternativa para cuando no tenés AutoCAD corriendo.

---

## PARTE 1 — EL ARCHIVO .BAT (el lanzador)

```bat
@echo off
```
**¿Qué hace?** Le dice a Windows: "no me muestres cada comando que ejecutás en la consola". Sin esto, verías algo feo como `C:\Users\...\py -3 autocad_redibuja.py` antes de cada cosa. Con `@echo off` solo ves el output de Python.

```bat
chcp 65001 > nul
```
**¿Qué hace?** `chcp` = "Change Code Page". La consola de Windows por defecto usa la página de códigos 850 o 1252 (Latin), que no soporta todos los caracteres. `65001` es UTF-8, que soporta tildes, ñ, emojis, todo. El `> nul` tira el output del comando (un mensaje de confirmación) a la basura para que no aparezca.

**Tip de programador:** Siempre que hagas scripts en Windows que muestren texto con tildes o caracteres especiales, ponele `chcp 65001` al principio del .bat.

```bat
title REDIBUJA AutoCAD - DP + Arc-Fitter
```
Cambia el título de la ventana de la consola. Solo cosmético, pero hace que el usuario sepa en qué ventana está.

```bat
color 0B
```
El primer dígito es el fondo, el segundo es el texto. Valores posibles:
```
0=Negro  1=Azul  2=Verde  3=Cyan  4=Rojo  5=Magenta
6=Amarillo  7=Blanco  8-F = versiones brillantes
```
`0B` = fondo negro, texto cyan brillante. Se ve pro.

```bat
set PYTHONIOENCODING=utf-8
```
Variable de entorno que le dice a Python: "usá UTF-8 cuando imprimás cosas". Sin esto, Python puede tirar `UnicodeEncodeError` cuando intentás imprimir caracteres con tilde en Windows.

```bat
py -3 "%~dp0autocad_redibuja.py"
```
Acá está el corazón del .bat:
- `py -3` = ejecutar Python 3 (el launcher de Python en Windows)
- `%~dp0` = la carpeta donde está este .bat. Es magia de BAT:
  - `%0` = el path completo del .bat
  - `~d` = solo la unidad (C:)
  - `~p` = solo la ruta (\\Users\\bla\\)
  - `~dp` = unidad + ruta = `C:\Users\bla\`
  - El resultado: sin importar desde dónde ejecutes el .bat, siempre encuentra el .py al lado suyo.

```bat
if errorlevel 1 (
    echo ERROR al ejecutar...
    pause
)
```
Si Python termina con un código de error (algo falló), muestra el mensaje y pausa antes de cerrar. Sin el `pause`, la ventana se cerraría en un segundo y no verías el error.

**Tip:** En Python, cuando el script se cierra normalmente devuelve `0`. Si lanza una excepción no manejada, devuelve `1`. `errorlevel 1` atrapa eso.

---

## PARTE 2 — LAS IMPORTACIONES (las primeras líneas del .py)

```python
import sys, math, time, traceback
```
Librerías que vienen con Python (no hay que instalar nada):
- `sys` — para `sys.exit(1)` (cerrar el programa con error)
- `math` — para `sqrt`, `cos`, `sin`, `atan2`, `pi`, `tan`... toda la matemática
- `time` — para `time.time()` (medir cuánto tarda el procesamiento)
- `traceback` — para `traceback.print_exc()` (mostrar el stack trace completo cuando hay un error, como el "rastro" que deja una excepción)

```python
import win32com.client
from win32com.client import VARIANT
import pythoncom
```
Estas SÍ hay que instalar (`pip install pywin32`). Son las que permiten hablar con AutoCAD:
- `win32com.client` — el cliente COM de Windows. COM = Component Object Model, el protocolo que usa Windows para que programas se hablen entre sí.
- `VARIANT` — un tipo de dato especial de COM. AutoCAD no entiende listas de Python, entiende VARIANTs.
- `pythoncom` — constantes de bajo nivel de COM (como `VT_ARRAY`, `VT_R8`).

```python
import os
os.system("")
```
`os` viene con Python. El `os.system("")` con string vacío es un truco: ejecuta un comando vacío en la consola de Windows, lo cual activa el soporte de colores ANSI que normalmente está desactivado. Sin esto, los `\033[92m` aparecerían literalmente como texto raro en vez de cambiar el color.

---

## PARTE 3 — LOS COLORES ANSI

```python
R  = "\033[91m"   # Rojo brillante
G  = "\033[92m"   # Verde brillante
Y  = "\033[93m"   # Amarillo
B  = "\033[94m"   # Azul
C  = "\033[96m"   # Cyan
W  = "\033[97m"   # Blanco
DIM= "\033[2m"    # Apagado/dim
RST= "\033[0m"    # Reset — vuelve al color normal
BLD= "\033[1m"    # Negrita
```

`\033` es el carácter "Escape" en notación octal. Los códigos ANSI siempre empiezan con `ESC[` seguido de un número y la letra `m`. La terminal los interpreta como instrucciones de color, no los imprime.

```python
def ok(msg):   print(f"  {G}OK{RST}  {msg}", flush=True)
```

Esto imprime `  OK  mensaje` donde "OK" sale en verde. El `{RST}` después de "OK" resetea el color para que el mensaje de después salga normal.

**¿Por qué `flush=True`?**
Python acumula el output en un buffer interno y lo vacía en lotes (más eficiente). Pero si tenés un proceso que tarda 10 segundos y querés ver el progreso en tiempo real, `flush=True` fuerza que cada `print` aparezca inmediatamente. Sin esto, verías todo junto al final.

**Tip de programador:** Esto es un patrón clásico de "logger mínimo". En proyectos grandes se usa `logging.getLogger()`, pero para scripts de consola, estas funciones simples son perfectas y mucho más livianas.

---

## PARTE 4 — LA CONFIGURACIÓN (clase Config)

```python
class Config:
    TOL_DP    = 0.05
    TOL_ARCO  = 0.05
    TOL_LINEA = 0.001
    RADIO_MAX = 5000.0
    COLOR     = 5
    SUFIJO    = "_ARC"
    ORIG_LAYER= "_ORIGINAL"

cfg = Config()
```

**¿Por qué una clase y no variables sueltas?**
Porque agrupa todo en un "contenedor". Cuando en cualquier parte del código escribís `cfg.TOL_DP`, queda claro que es una configuración global, no una variable local de la función. También es fácil pasarla como parámetro si algún día lo necesitás.

**¿Qué significa cada valor?**

| Variable | Valor | Significado real |
|---|---|---|
| `TOL_DP` | 0.05mm | El DP puede saltarse puntos que desvían menos de esto |
| `TOL_ARCO` | 0.05mm | Un arco es válido si todos sus puntos quedan a menos de esto del círculo |
| `TOL_LINEA` | 0.001mm | Una recta "exacta" permite esta desviación máxima |
| `RADIO_MAX` | 5000mm | Si el radio del arco es mayor a 5 metros, probablemente es casi una recta |
| `COLOR` | 5 | Índice de color de AutoCAD (5 = azul) |
| `SUFIJO` | `"_ARC"` | El layer destino = layer original + este sufijo |
| `ORIG_LAYER` | `"_ORIGINAL"` | Si una entidad está en este layer, no la reprocesamos |

**Por qué estos números específicamente:** Una pieza de vidrio típica mide 1-3 metros. 0.05mm en 1000mm es el 0.005% — imperceptible visualmente y dentro de cualquier tolerancia de fabricación. Si subirás a 0.5mm, empezarías a ver pequeñas deformaciones.

---

## PARTE 5 — GEOMETRÍA 2D (la matemática base)

### `dist2d` — distancia entre dos puntos
```python
def dist2d(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)
```
Teorema de Pitágoras puro. `a` y `b` son tuplas `(x, y)`. `a[0]` es X, `a[1]` es Y.

**Tip:** En Python, `**2` es elevar al cuadrado. `math.sqrt` es raíz cuadrada. Así que esto es literalmente `√((x2-x1)² + (y2-y1)²)`.

---

### `dist_linea` — distancia de un punto a una recta
```python
def dist_linea(pt, p0, p1):
    dx = p1[0]-p0[0]
    dy = p1[1]-p0[1]
    L  = math.sqrt(dx*dx + dy*dy)
    if L < 1e-12: return dist2d(pt, p0)
    return abs(dy*pt[0] - dx*pt[1] + p1[0]*p0[1] - p1[1]*p0[0]) / L
```

Esta es la fórmula de distancia punto-recta. Visualmente:

```
         pt
          *
         /|
        / |← esta distancia es lo que calculamos
       /  |
p0 *------* p1
```

La fórmula matemática viene de que cualquier recta se puede escribir como `Ax + By + C = 0`, y la distancia de un punto `(x0,y0)` a esa recta es `|Ax0 + By0 + C| / √(A²+B²)`.

Si `p0 == p1` (línea degenerada, longitud cero), `L` sería 0 y dividiríamos por cero. Por eso el `if L < 1e-12` devuelve la distancia al punto directamente.

**`1e-12`** = 0.000000000001. Usamos este número en vez de `0` porque con aritmética de punto flotante, dos puntos "iguales" pueden tener una diferencia de `1e-15` por errores de redondeo. `1e-12` es suficientemente pequeño para ser "cero" en el contexto de milímetros.

---

### `circulo_3pts` — el círculo que pasa por 3 puntos
```python
def circulo_3pts(p0, pm, p1):
    ax=pm[0]-p0[0]; ay=pm[1]-p0[1]
    bx=p1[0]-p0[0]; by=p1[1]-p0[1]
    det = ax*by - ay*bx
    if abs(det) < 1e-10: return None
    d0 = ax*ax+ay*ay
    d1 = bx*bx+by*by
    cx = (d0*by - d1*ay) / (2*det)
    cy = (d1*ax - d0*bx) / (2*det)
    return (p0[0]+cx, p0[1]+cy, math.sqrt(cx*cx+cy*cy))
```

Por 3 puntos no colineales pasa exactamente un círculo. La idea:
1. Trasladar todo para que `p0` quede en el origen (coordenadas relativas)
2. Plantear el sistema: el centro `(cx,cy)` equidista de los 3 puntos
3. Eso da 2 ecuaciones lineales → resolver con determinantes (regla de Cramer)

Si `det ≈ 0`, los 3 puntos están en línea recta → no forman un círculo → devolvemos `None`.

El retorno es `(centro_x, centro_y, radio)`.

---

### `calcular_bulge` — el valor más importante del proyecto

El **bulge** es la forma que tiene AutoCAD de codificar arcos dentro de una polilínea. Cada vértice de la polilínea puede tener un bulge que define cómo llegar al siguiente vértice:

```
bulge = 0    → línea recta al siguiente punto
bulge = 1    → semicírculo (180°) en sentido antihorario
bulge = -1   → semicírculo en sentido horario
bulge = 0.414 → arco de 90° antihorario
```

La fórmula es: **`bulge = tan(θ/4)`** donde θ es el ángulo central del arco.

```
Si θ = 180° → bulge = tan(45°) = 1.0
Si θ = 90°  → bulge = tan(22.5°) ≈ 0.414
Si θ = 60°  → bulge = tan(15°) ≈ 0.268
```

El signo (+/-) indica la dirección:
- Positivo = antihorario (CCW)
- Negativo = horario (CW)

```python
def calcular_bulge(p0, pm, p1):
    circ = circulo_3pts(p0, pm, p1)
    cx, cy, r = circ
    a0 = math.atan2(p0[1]-cy, p0[0]-cx)   # ángulo de p0 visto desde el centro
    a1 = math.atan2(p1[1]-cy, p1[0]-cx)   # ángulo de p1 visto desde el centro
    am = math.atan2(pm[1]-cy, pm[0]-cx)   # ángulo de pm visto desde el centro
    d_ccw = ang_norm(a1-a0)               # ¿cuánto arco CCW hay de p0 a p1?
    am_r  = ang_norm(am-a0)               # ¿dónde cae pm en ese arco?
    if am_r <= d_ccw+1e-9:
        theta=d_ccw;  sign=1   # pm está dentro del arco CCW → es CCW
    else:
        theta=2*math.pi-d_ccw; sign=-1   # pm está en el arco CW → es CW
    return math.tan(theta/4) * sign
```

`math.atan2(y, x)` devuelve el ángulo de un punto `(x,y)` respecto al origen, en radianes. Siempre usar `atan2(y,x)` y no `atan(y/x)` porque `atan2` maneja todos los cuadrantes correctamente.

---

## PARTE 6 — NURBS / EVALUACIÓN DE SPLINES (la parte más dura)

### ¿Qué es una NURBS y por qué es complicado?

Cuando dibujás una spline en AutoCAD, internamente se guarda como una **NURBS** (Non-Uniform Rational B-Spline). Una NURBS tiene:

- **Puntos de control (P):** "imanes" que atraen la curva pero que generalmente NO están sobre ella
- **Pesos (W):** qué tan fuerte atrae cada imán (solo en NURBS "racionales")
- **Vector de knots (U):** lista de parámetros donde la curva "cambia de comportamiento"
- **Grado (p):** normalmente 3 (cúbica)

```
    P1                P3
     *                *
      \              /
       \    curva   /
        \  /‾‾‾‾\ /
         \/      X
         /\      /\
        /  \    /  \
       *    \  /    *
      P0    \/    P4
             P2 ← punto de control, NO está en la curva
```

Para obtener un punto real sobre la curva, hay que evaluar la ecuación:
```
C(t) = Σ(Ni,p(t) × wi × Pi) / Σ(Ni,p(t) × wi)
```

Las `Ni,p(t)` son las **funciones base B-spline** — números entre 0 y 1 que dicen cuánto "influye" cada punto de control en el parámetro `t`.

### `nurbs_span` — búsqueda binaria del intervalo

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

Dado un parámetro `t`, busca en qué "intervalo" del vector de knots cae. La magia de las B-splines es el **soporte local**: en el parámetro `t`, solo influyen los `p+1` puntos de control del intervalo donde cae `t`. No hay que calcular todos.

La búsqueda binaria es O(log n) — mucho más rápida que recorrer todo el vector.

### `nurbs_basis` — las funciones base (algoritmo de Cox-de Boor)

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

Calcula las `p+1` funciones base en el punto `t`. El algoritmo parte de grado 0 (funciones constantes) y sube de grado usando una recurrencia triangular. Es numéricamente estable — diseñado específicamente para no acumular errores de punto flotante.

### `evaluar_spline_com` — leer y evaluar la spline de AutoCAD

```python
U = list(ent.Knots)           # vector de knots
p = int(ent.Degree)           # grado
try:    W = list(ent.Weights) # pesos (rational)
except: W = []                # polynomial → no tiene pesos

# Número real de puntos de control: siempre len(U) - p - 1
n_cp_k = len(U) - p - 1
```

**Trampa importante:** `ent.NumberOfControlPoints` en la API COM de AutoCAD a veces devuelve un número incorrecto (bug conocido, off-by-one). La forma correcta de saber cuántos CPs hay es matemáticamente: `n_cp = len(U) - p - 1`. Esta relación es inviolable en cualquier B-spline válida.

**Spline racional vs polinomial:**
- Si `ent.IsRational = True` → tiene pesos diferentes → `.Weights` devuelve la lista
- Si `ent.IsRational = False` → todos los pesos son 1.0 → `.Weights` lanza excepción

Por eso el `try/except`: si falla, asignamos todos los pesos a 1.0.

**¿Por qué muestrear 16 puntos por intervalo?**
```python
knots_u = sorted(set(U))   # knots únicos (sin repetidos)
N_seg = 16
for ki in range(len(knots_u)-1):
    for k in range(N_seg + 1):
        t = ta + (tb-ta) * k / N_seg
        pts_raw.append(nurbs_pt(t, P, W, U, p))
```
Entre cada par de knots, la curva es una porción suave. 16 puntos es suficiente densidad para que luego DP pueda hacer su trabajo correctamente. Con menos puntos, DP podría "perderse" curvas muy pronunciadas.

### ¿Y cuándo hay FitPoints?

```python
fp = list(ent.FitPoints)   # [x0,y0,z0, x1,y1,z1, ...] lista plana 3D
pts = [(fp[i], fp[i+1]) for i in range(0, len(fp)-2, 3)]
```

Los FitPoints son los puntos que el usuario usó para DIBUJAR la spline en AutoCAD. Están garantizados sobre la curva. Son mejores que evaluar NURBS porque son exactos. Si existen, los usamos directamente. Si no, recurrimos a la evaluación NURBS.

---

## PARTE 7 — DOUGLAS-PEUCKER (la reducción de puntos)

### La idea visual

Tenés 100 puntos describiendo una curva. Muchos son "redundantes" — si los eliminás, la curva sigue viéndose igual. ¿Cuáles eliminás?

```
Antes (9 puntos):
A . . B . C . . . D

Si trazás la recta A→D, ¿qué punto se aleja más?
→ C (se aleja 2mm de la recta A-D)

Si tol = 0.05mm, 2mm > 0.05mm → C es importante, no lo eliminamos
→ Dividimos en A...C y C...D, y recursamos

En A...C: todos los puntos intermedios se alejan menos de 0.05mm de A-C
→ Los eliminamos, guardamos solo A y C

En C...D: igual → guardamos solo C y D

Resultado: A, C, D (de 9 puntos a 3, sin error visible)
```

### El código

```python
def dp(pts, tol):
    if len(pts) <= 2: return list(pts)   # caso base
    
    md=0; mi=0
    p0=pts[0]; p1=pts[-1]
    
    # Encontrar el punto más alejado de la línea p0→p1
    for i in range(1, len(pts)-1):
        d = dist_linea(pts[i], p0, p1)
        if d > md: md=d; mi=i
    
    if md > tol:
        # El punto más alejado supera tol → dividir recursivamente
        return dp(pts[:mi+1], tol)[:-1] + dp(pts[mi:], tol)
    else:
        # Ningún punto supera tol → todos son superfluos
        return [pts[0], pts[-1]]
```

**La recursión:** `pts[:mi+1]` es todo lo que está antes del punto más importante (incluido), `pts[mi:]` es desde ese punto en adelante. Los unimos con `[:-1]` para no duplicar el punto del medio.

**¿Por qué 3 pasadas?**
```python
r = dp(pts, tol*2)          # primera pasada: tolerancia doble (agresiva)
if len(r) > 4: r = dp(r, tol)       # segunda: tolerancia exacta
if len(r) > 4: r = dp(r, tol*0.5)   # tercera: más fina
```
Una sola pasada puede dejar puntos que en combinación son redundantes. Tres pasadas convergen mejor. El `if len(r) > 4` evita procesar curvas ya muy simples.

**Garantía matemática de DP:** El resultado NUNCA se aleja más de `tol` de ningún punto original. Es una garantía, no una heurística.

---

## PARTE 8 — ARC-FITTER (convertir puntos a líneas y arcos)

### La idea

Después del DP, tenés digamos 40 puntos. Ahora querés representarlos con el menor número de segmentos posibles, donde cada segmento puede ser:
- Una **línea recta** (bulge=0)
- Un **arco de círculo** (bulge≠0)

La estrategia es **greedy (voraz)**: desde cada posición, cubrí la mayor cantidad de puntos posibles con un solo segmento.

### `es_recta`
```python
def es_recta(pts, tol):
    if len(pts) <= 2: return True
    p0=pts[0]; p1=pts[-1]
    for pt in pts[1:-1]:
        if dist_linea(pt, p0, p1) > tol: return False
    return True
```
Simple: si todos los puntos intermedios están a menos de `tol` de la línea `p0→p1`, es una recta.

### `intentar_arco` — el filtro más importante
```python
def intentar_arco(pts_z, tol):
```

Esta función recibe un grupo de puntos y pregunta: **¿se puede representar todo esto con un solo arco?**

**Paso 1: Calcular la sagitta**
```python
sagitta_real = 0; pm_idx = len(pts_z)//2
for idx in range(1, len(pts_z)-1):
    d = dist_linea(pts_z[idx], p0, p1)
    if d > sagitta_real:
        sagitta_real = d; pm_idx = idx
pm = pts_z[pm_idx]
```

La **sagitta** es la distancia máxima de los puntos intermedios a la cuerda `p0→p1`. Mide qué tan "curvo" es el grupo de puntos.

Usamos el punto de **máxima desviación** (no el del medio) porque si pm cae en una zona de inflexión (curva en S), el círculo calculado sería incorrecto.

**Paso 2: Filtros**
```python
if sagitta_real < tol * 4: return None      # muy plano → es una recta
if cuerda>1.0 and sagitta_real/cuerda < 0.008: return None   # 0.8% mínimo
```

Si la sagitta es menor a 4× la tolerancia, la "curvatura" es tan pequeña que mejor dibujarlo como línea recta. El error visual sería mínimo y la línea es más simple.

**Paso 3: Verificar que no es una curva en S**
```python
lados = [math.copysign(1, (p1[0]-p0[0])*(pt[1]-p0[1]) 
                          -(p1[1]-p0[1])*(pt[0]-p0[0]))
         for pt in pts_z[1:-1]]
if len(set(lados)) > 1: return None
```

El **producto vectorial** `(p1-p0) × (pt-p0)` es positivo si `pt` está a la izquierda de la recta `p0→p1`, negativo si está a la derecha. Si hay puntos en ambos lados → es una curva en S (cambia de lado) → no se puede representar como un solo arco.

`math.copysign(1, x)` devuelve `+1.0` o `-1.0` según el signo de `x`.

`set(lados)` elimina duplicados. Si `len == 1`, todos son del mismo signo → mismo lado → es un arco válido.

**Paso 4: Ajustar el círculo y verificar TODOS los puntos**
```python
circ = circulo_3pts(p0, pm, p1)
cx, cy, r = circ
if r > cfg.RADIO_MAX or r < 0.001: return None
for pt in pts_z:
    if abs(math.sqrt((pt[0]-cx)**2+(pt[1]-cy)**2)-r) > tol: return None
```

El círculo pasa por `p0`, `pm`, `p1`. Pero hay que verificar que TODOS los demás puntos también queden sobre ese círculo (dentro de la tolerancia). Si alguno no queda → el grupo no es un arco → `return None`.

**Paso 5: Calcular el bulge y filtro final**
```python
bulge = calcular_bulge(p0, pm, p1)
if abs(bulge) > 0.9999: return None   # rechazar arcos >= 180°
return bulge
```

Arcos de 180° o más crean geometría extraña en AutoCAD (bucles). Rechazamos cualquier bulge >= 1.

### `arc_fit` — el algoritmo greedy completo
```python
def arc_fit(pts):
    segs=[]; n=len(pts); i=0
    while i < n-1:
        MAX = 150   # máximo de puntos a "saltar" de un golpe
        
        # Buscar la LÍNEA más larga posible desde pts[i]
        jl = i+1
        for j in range(min(n-1, i+MAX), i+1, -1):   # de atrás hacia adelante
            if es_recta(pts[i:j+1], tol_l):
                jl=j; break
        
        # Buscar el ARCO más largo posible desde pts[i]
        ba=None; ja=-1
        if not es_recta(pts[i:min(i+6,n)], tol_a):   # si ya los primeros no son recta
            for j in range(min(n-1, i+MAX), i+2, -1):
                if es_recta(pts[i:j+1], tol_a): continue
                b = intentar_arco(pts[i:j+1], tol_a)
                if b is not None: ba=b; ja=j; break
        
        # El arco gana solo si cubre 2+ puntos más que la línea
        if ba is not None and ja > jl+1:
            segs.append((pts[i], pts[ja], ba)); i=ja
        else:
            segs.append((pts[i], pts[jl], 0.0)); i=jl
    return segs
```

**¿Por qué buscar de atrás hacia adelante?**
Queremos el segmento más LARGO. Si buscás de adelante, el primer que encuentres (el más corto que funciona) ya termina el loop. Buscando de atrás, el primero que encontrás ES el más largo.

**La condición `ja > jl+1`:**
El arco solo "gana" si cubre al menos 2 puntos más que la mejor línea. Así evitamos reemplazar una línea de 5 puntos por un arco de 6 puntos (la ganancia es mínima y añade complejidad).

---

## PARTE 9 — LEER ENTIDADES DE AUTOCAD

```python
def leer_entidad(ent, verbose=False):
    tipo = ent.EntityName.upper()
```

`EntityName` es como el "tipo" de la entidad en AutoCAD:
```
"AcDbSpline"    → spline
"AcDbPolyline"  → polilínea (varios tipos)
"AcDbLine"      → línea recta
"AcDbArc"       → arco
"AcDbCircle"    → círculo
```

El `.upper()` es por seguridad — a veces AutoCAD devuelve "AcDbSpline" con mayúsculas distintas.

**Para LINE:**
```python
elif tipo == 'ACDBLINE':
    s = ent.StartPoint; e = ent.EndPoint
    pts = [(s[0],s[1]), (e[0],e[1])]
```
Una línea recta son solo 2 puntos. `StartPoint` y `EndPoint` son arrays 3D `[x,y,z]` — tomamos solo `[0]` y `[1]` (X e Y).

**Para ARC:**
```python
cx,cy = ent.Center[0], ent.Center[1]
r = ent.Radius
a0 = ent.StartAngle; a1 = ent.EndAngle
n = max(8, int((a1-a0)*r/0.3))   # un punto cada 0.3mm de arco
pts = [(cx+r*cos(a), cy+r*sin(a)) for ...]
```
Un arco se muestrea en puntos. La cantidad de puntos depende del radio y el ángulo — más grande o más cerrado → más puntos para capturar bien la curvatura.

**Para CIRCLE:**
```python
n = max(16, int(2*math.pi*r/0.3))   # perímetro / 0.3mm
```
Un círculo es un arco completo. Lo muestreamos con la misma densidad.

---

## PARTE 10 — CREAR LA LWPOLYLINE

```python
def crear_lwpoly(mspace, segs, cerrada, capa, color):
    verts = [s[0] for s in segs]
    if not cerrada: verts.append(segs[-1][1])
    flat = []
    for v in verts: flat += list(v)
    arr = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flat)
    lw = mspace.AddLightWeightPolyline(arr)
```

**¿Qué es `VARIANT`?**
AutoCAD COM no entiende listas de Python. Entiende el tipo COM `VARIANT`. El `VT_ARRAY | VT_R8` significa "un array de doubles (números de 64 bits)". Es el único formato que acepta `AddLightWeightPolyline`.

`|` acá es un OR a nivel de bits (bitwise OR), no un "o" lógico. Combina dos flags en uno.

```python
for i, (p0, p1, bulge) in enumerate(segs):
    if abs(bulge) > 1e-10:
        lw.SetBulge(i, bulge)
```

`enumerate(segs)` recorre la lista dando `(índice, elemento)`. Los bulges se asignan por índice de vértice. Solo los que son != 0 se asignan (los cero son líneas por defecto).

```python
lw.Update()
```
Fuerza a AutoCAD a actualizar la entidad visualmente. Sin esto, podrías ver la polilínea "fantasma" hasta que movieras el mouse.

---

## PARTE 11 — UNIR FRAGMENTOS EXPLOTADOS

Cuando una pieza está "explotada" en AutoCAD (un contorno dividido en 50 pedazos sueltos, uno por entidad), hay que unirlos antes de procesar.

```python
TOL_UNION = 1.0   # si dos extremos están a menos de 1mm, los conectamos
```

```python
def unir_cadenas(lista_pts_cerrada):
    frags  = [...]   # copia de cada fragmento
    usados = [False] * n
    cadenas = []
    
    for i0 in range(n):
        cadena = list(frags[i0])
        usados[i0] = True
        
        # Extender por el FINAL
        while True:
            p_fin = cadena[-1]
            for j in range(n):
                if usados[j]: continue
                if dist2d(frags[j][0], p_fin) < TOL_UNION:
                    cadena.extend(frags[j][1:])   # conectar normal
                    usados[j] = True; break
                elif dist2d(frags[j][-1], p_fin) < TOL_UNION:
                    cadena.extend(reversed(frags[j])[1:])   # conectar invertido
                    usados[j] = True; break
```

**¿Qué es "explotado"?** Cuando el usuario hace `EXPLODE` en AutoCAD sobre un bloque o grupo, lo divide en sus partes individuales. Un rectángulo se convierte en 4 líneas sueltas. Una pieza compleja puede quedar en 50+ fragmentos.

El algoritmo de unión es greedy: empieza con un fragmento y busca cuál se conecta a su extremo. Soporta inversión (si el fragmento está "al revés", lo da vuelta antes de conectar).

Al final verifica si la cadena resultante es cerrada:
```python
es_cerrada = dist2d(cadena[0], cadena[-1]) < TOL_UNION * 2
```

---

## PARTE 12 — EL PIPELINE COMPLETO

```python
def pipeline_pts(pts, cerrada, capa, mspace, doc, n_orig_display=None):
    # 1. Filtro de longitud mínima
    largo = sum(dist2d(pts[i], pts[i+1]) for i in range(len(pts)-1))
    if largo < 0.5: return None
    
    # 2. Douglas-Peucker
    red = reducir_pts(pts, cfg.TOL_DP, cerrada)
    
    # 3. Arc-Fit
    segs = arc_fit(arc_pts)
    
    # 4. Layer destino
    sufijo_up = cfg.SUFIJO.upper()
    capa_dst = capa if capa.upper().endswith(sufijo_up) else capa + cfg.SUFIJO
    doc.Layers.Add(capa_dst)   # crear si no existe, ignorar error si ya existe
    
    # 5. Crear LWPOLYLINE
    nueva = crear_lwpoly(mspace, segs, cerrada, capa_dst, cfg.COLOR)
    
    return (n_orig, n_dp, len(segs), n_lin, n_arc)
```

Y la agrupación por capa:
```python
from collections import defaultdict
por_capa = defaultdict(list)
for ent in entidades:
    por_capa[ent.Layer].append(ent)
```

`defaultdict(list)` es un diccionario que crea automáticamente una lista vacía para cada clave nueva. Sin esto tendrías que escribir `if capa not in por_capa: por_capa[capa] = []` antes de cada `.append()`.

---

## PARTE 13 — EL MENÚ INTERACTIVO

```python
while True:
    op = input(f"  Opcion > ").strip()
    
    if op == '0': break
    elif op == '1':
        input()   # esperá que el usuario seleccione en AutoCAD y presione ENTER
        ss = doc.ActiveSelectionSet
    elif op == '2':
        ss = doc.ActiveSelectionSet   # usar lo que ya está seleccionado
```

`input()` sin mensaje solo espera que el usuario presione ENTER. Esto pausa el script mientras el usuario va a AutoCAD y selecciona lo que quiere procesar.

`doc.ActiveSelectionSet` captura exactamente lo que está seleccionado en AutoCAD en ese momento — el equivalente a preguntar "¿qué está resaltado ahora mismo?".

```python
try: doc.Regen(1)
except: pass
```
`Regen` actualiza el render de AutoCAD. El `1` es la constante `acActiveViewport`. El `try/except` es porque a veces falla sin razón y no es crítico.

---

## PARTE 14 — CÓMO DISTRIBUIR ESTO A CLIENTES SIN CÓDIGO

Acá viene lo bueno. Querés que el cliente solo haga doble clic y listo, sin Python, sin instalar nada raro.

### Opción 1 (RECOMENDADA): Compilar a .exe con PyInstaller

**¿Qué hace PyInstaller?** Empaqueta tu script Python + el intérprete de Python + todas las librerías en un solo `.exe` que corre en cualquier Windows, sin Python instalado.

**Paso a paso:**

```bash
# 1. Instalar PyInstaller
pip install pyinstaller

# 2. Ir a la carpeta del proyecto
cd "c:\Users\abotero\OneDrive - AGP GROUP\Documentos\redibujado"

# 3. Compilar
pyinstaller --onefile --console autocad_redibuja.py
```

Flags importantes:
- `--onefile` → todo en un solo .exe (más limpio para distribuir)
- `--console` → mantiene la ventana de consola visible (necesario porque es interactivo)
- Sin `--console` → ventana negra invisible, el usuario no puede escribir nada

El .exe queda en `dist\autocad_redibuja.exe`.

**Para win32com hay un paso extra:**
```bash
pyinstaller --onefile --console \
  --hidden-import win32com \
  --hidden-import win32com.client \
  --hidden-import pythoncom \
  --hidden-import pywintypes \
  autocad_redibuja.py
```

Las librerías COM a veces no se detectan automáticamente → hay que declararlas con `--hidden-import`.

**El .bat para el cliente quedaría así:**
```bat
@echo off
chcp 65001 > nul
title REDIBUJA AutoCAD
"%~dp0autocad_redibuja.exe"
pause
```
Sin `py -3`, sin Python, directo al .exe.

**Lo que le entregás al cliente:**
```
📁 REDIBUJA_CLIENTE/
├── autocad_redibuja.exe    ← el ejecutable (puede pesar 30-50MB)
└── REDIBUJA_AUTOCAD.bat    ← doble clic para ejecutar
```

---

### Opción 2 (más simple): Instalar Python silenciosamente

Si querés evitar el .exe grande, podés hacer un instalador que instale Python automáticamente:

```bat
@echo off
:: Verificar si Python está instalado
py -3 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python no encontrado. Instalando...
    :: Descargar e instalar Python silenciosamente
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe' -OutFile '%TEMP%\python_install.exe'"
    "%TEMP%\python_install.exe" /quiet InstallAllUsers=1 PrependPath=1
    echo Python instalado.
)

:: Instalar dependencias
py -3 -m pip install pywin32 --quiet

:: Ejecutar
py -3 "%~dp0autocad_redibuja.py"
```

Desventaja: necesita internet, y la primera vez tarda.

---

### Opción 3 (la más pro): Instalador con NSIS o Inno Setup

Herramientas gratuitas que crean instaladores `.exe` con wizard (siguiente, siguiente, finalizar). Le podés poner logo, nombre de empresa, todo.

Con **Inno Setup** (gratuito, innosetup.com):
1. Definís qué archivos incluir (el .exe compilado, el .bat)
2. Definís accesos directos, carpeta de instalación
3. Generás el instalador → un solo `.exe` de setup

El cliente hace doble clic en `Setup_REDIBUJA.exe`, instala como cualquier programa de Windows, y aparece en el menú de inicio.

---

### Requisito inevitable: AutoCAD

De todas formas, el cliente SIEMPRE necesita **AutoCAD instalado y abierto**. El script se conecta a AutoCAD vía COM — sin AutoCAD corriendo, no hay nada a qué conectarse.

Si el cliente no tiene AutoCAD, la alternativa sería usar `autocad_pipeline.py` que lee archivos `.DXF` directamente con `ezdxf` — ahí sí no necesita AutoCAD. Pero pierde la interactividad de seleccionar directamente en el dibujo.

---

## RESUMEN DEL FLUJO COMPLETO

```
1. Cliente abre AutoCAD con su pieza
2. Doble clic en REDIBUJA_AUTOCAD.bat (o .exe)
   → Python arranca
   → Se conecta a AutoCAD via COM (win32com)
   → Muestra menú
3. Cliente elige opción 1
   → Va a AutoCAD, selecciona las piezas (Ctrl+A o manual)
   → Vuelve a la consola, presiona ENTER
4. Python lee doc.ActiveSelectionSet
   → Para cada entidad: leer puntos (FitPoints o NURBS)
   → Agrupar por layer (defaultdict)
   → Para cada grupo: unir fragmentos si hay varios
   → Para cada cadena unida: DP + Arc-Fit
   → Crear LWPOLYLINE nueva en layer NOMBRE_ARC
5. doc.Regen(1) → AutoCAD actualiza pantalla
6. Cliente ve la nueva polilínea limpia encima de la original
7. Si está bien, borra la original manualmente
```

---

## TIPS FINALES DE PROGRAMADOR

**1. Las tolerancias son tradeoffs**
```
TOL_DP más alto   = menos puntos, posible pérdida de forma
TOL_DP más bajo   = más puntos, más fiel pero más pesado
TOL_ARCO más alto = menos arcos (más líneas), más simple
TOL_ARCO más bajo = más arcos, más exacto pero más complejo
```

**2. Defensividad con COM**
Siempre envolvé el acceso a propiedades de objetos AutoCAD en `try/except`. La API COM es inestable y puede fallar por razones oscuras. `try: capa = ent.Layer; except: capa = '0'` es el patrón correcto.

**3. `flush=True` en output de progreso**
Sin esto el usuario ve todo junto al final. Con esto ve cada entidad procesada en tiempo real.

**4. Búsqueda inversa para el greedy**
`for j in range(MAX, i+1, -1)` busca desde el máximo hacia abajo. El primero que funciona es el más largo. Buscar de adelante hacia atrás te daría el más corto que funciona.

**5. `defaultdict` > diccionario con check**
`defaultdict(list)` elimina el boilerplate de verificar si la clave existe antes de hacer `.append()`.

**6. Nombres en el código = documentación viva**
`es_recta(pts, tol)` es más claro que `check(data, t)`. El nombre bien elegido hace que el código se lea como una frase en inglés/español.

**7. Separar entrada, proceso y salida**
- `leer_entidad` = entrada (leer de AutoCAD)
- `pipeline_pts` = proceso (matemática pura)
- `crear_lwpoly` = salida (escribir a AutoCAD)

Así podés testear el proceso sin necesitar AutoCAD.

**8. Las funciones pequeñas son tus amigas**
`dist2d`, `dist_linea`, `es_recta` son funciones de 3-5 líneas cada una. Fáciles de entender, fáciles de testear, reutilizables en cualquier parte. Un buen programador prefiere 20 funciones pequeñas a 1 función de 100 líneas.

**9. Los números mágicos merecen nombres**
```python
# MAL:
if sagitta < tol * 4:

# BIEN:
MIN_SAGITTA_ABS = tol * 4   # mínimo 4x tolerancia para ser arco real
if sagitta < MIN_SAGITTA_ABS:
```

**10. Testear casos extremos**
- ¿Qué pasa con una entidad de 2 puntos? → la función lo maneja con `if len(pts) <= 2`
- ¿Qué pasa si el denominador es cero? → `if abs(det) < 1e-10: return None`
- ¿Qué pasa si AutoCAD no está abierto? → `try: acad = GetActiveObject(...); except: sys.exit(1)`

Siempre preguntate "¿qué pasa si el input es raro?" antes de dar el código por terminado.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convertidor de option files  WE9 / PES5 / WE9LE  ->  PES6  (PC)
==============================================================

Arrastra el option file de WE9/PES5 sobre el .exe (o elígelo en la ventana) y se genera un
option file de PES6 con:
  * los jugadores (datos, atributos, habilidades, nacionalidad, apariencia aproximada),
  * las plantillas de selecciones, clásicos y clubes,
  * los clubes "Team A..R" de PES6 renombrados con el nombre que tenían en WE9.

Todo se escribe sobre una BASE de PES6 (por defecto, el option file virgen incluido en la carpeta
"datos"); el archivo de WE9 y la base nunca se modifican. El resultado se verifica antes de darse
por bueno: si algo falla, no se deja ningún archivo de salida.

Solo biblioteca estándar de Python (tkinter para la ventana).
"""
import csv, io, json, os, re, struct, sys, threading, unicodedata, hashlib, queue, traceback
from collections import Counter

VERSION = "1.0"
NOMBRE_SALIDA = "KONAMI-WIN32PES6OPT"

# --------------------------------------------------------------------------------------
#  Localización de datos (funciona tanto en .py como dentro del .exe de PyInstaller)
# --------------------------------------------------------------------------------------
def carpeta_base():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

def ruta_datos(nombre):
    return os.path.join(carpeta_base(), "datos", nombre)

def base_por_defecto():
    """La base de PES6 incluida, si esta (no se distribuye en el repo publico: son datos de Konami).
    Sin ella, el usuario elige su propio option file virgen de PES6."""
    ruta = ruta_datos("base_pes6_virgen.bin")
    return ruta if os.path.isfile(ruta) else ""

class ErrorConversion(Exception):
    """Error previsto: se muestra al usuario sin traza."""

# --------------------------------------------------------------------------------------
#  Tablas (generadas desde los fuentes de PESEditor y PES-Editor-5) y constantes
# --------------------------------------------------------------------------------------
def _huella(lista):
    return hashlib.sha256(json.dumps(lista).encode()).hexdigest()[:16]

with open(ruta_datos("tablas.json"), encoding="utf-8") as _f:
    TAB = json.load(_f)
for _k in ("keypc", "key5", "key6"):
    if _huella(TAB[_k]) != TAB["fp"][_k]:
        raise SystemExit("Las tablas de cifrado estan danadas (huella %s)." % _k)
ALLCOLS = TAB["ALLCOLS"]
T5 = {c: tuple(v) for c, v in TAB["T5"].items()}
T6 = {c: tuple(v) for c, v in TAB["T6"].items()}
NAT5 = {int(k): v for k, v in TAB["NAT5"].items()}
NAT6 = {int(k): v for k, v in TAB["NAT6"].items()}
NAT6_INV = {v: k for k, v in NAT6.items()}
NAT6_FREE = NAT6_INV["Free Nationality"]
NAC5, NAC6 = TAB["NAC5"], TAB["NAC6"]            # selecciones 0..56 de cada juego, por nombre
HAIR = (0, 45, 0, 0x7FF)
FACETYPE, FACE, SKIN6 = tuple(TAB["S6"]["faceType"]), tuple(TAB["S6"]["face"]), tuple(TAB["S6"]["skin"])
SKIN5, FT5 = (0, 43, 1, 3), (0, 55, 0, 3)
FLAG_NAME, FLAG_SHIRT, FLAG_CALL, FLAG_ABIL, CALLNAME = (0, 3, 0, 1), (0, 3, 1, 1), (0, 3, 2, 1), (0, 40, 4, 1), (0, 1, 0, 0xFFFF)
FIRST_EDIT = 32768

GAMES = {
    "pes5": dict(length=1250304, keylen=367, style=5, keypc=bytes(TAB["keypc"]), key=TAB["key5"],
                 block=[12, 5144, 9508, 14044, 36872, 657712, 803608, 822940, 969192, 1228568, 1250316],
                 size=[4948, 1232, 4520, 22816, 620000, 145880, 19320, 146240, 259364, 21016],
                 c1=1815549477, c2=0x6C371625, base=36872, baseE=14044),
    "pes6": dict(length=1191936, keylen=446, style=6, keypc=bytes(TAB["keypc"]), key=TAB["key6"],
                 block=[12, 5144, 9544, 14288, 37116, 657956, 751472, 763804, 911144, 1170520],
                 size=[4844, 1268, 4730, 22816, 620000, 93501, 12320, 147328, 259364, 21032],
                 c1=0x7AB3684C, c2=0x7AB3684C, base=37116, baseE=14288),
}
SQ = {
    "pes5": dict(n23=74, slot23=664054, slot32=667458, num23=657712, num32=659414),
    "pes6": dict(n23=73, slot23=664372, slot32=667730, num23=657956, num32=659635),
}

# --------------------------------------------------------------------------------------
#  Cifrado del option file (capa XOR de 256 bytes + palabras de 32 bits por bloque + checksums)
# --------------------------------------------------------------------------------------
def xor_pc(buf, g):
    kp = g["keypc"]
    return bytearray(b ^ kp[i & 255] for i, b in enumerate(buf))

def _palabras(buf, ini, tam):
    n = tam // 4
    return list(struct.unpack_from("<%dI" % n, buf, ini)), n

def checksums(buf, g):
    return [sum(_palabras(buf, g["block"][i], g["size"][i])[0]) & 0xFFFFFFFF for i in range(10)]

def checksums_guardados(buf, g):
    return [struct.unpack_from("<I", buf, g["block"][i] - 8)[0] for i in range(10)]

def descifrar(buf, g):
    key, kl, c1, c2 = g["key"], g["keylen"], g["c1"], g["c2"]
    for i in range(1, 10):
        w, n = _palabras(buf, g["block"][i], g["size"][i])
        for k in range(n):
            w[k] = (((w[k] - key[k % kl]) + c1) & 0xFFFFFFFF) ^ c2
        struct.pack_into("<%dI" % n, buf, g["block"][i], *w)

def cifrar(buf, g):
    key, kl, c1, c2 = g["key"], g["keylen"], g["c1"], g["c2"]
    for i in range(1, 10):
        w, n = _palabras(buf, g["block"][i], g["size"][i])
        for k in range(n):
            if g["style"] == 5:
                w[k] = (key[k % kl] + ((w[k] ^ c2) - c1)) & 0xFFFFFFFF
            else:
                w[k] = (key[k % kl] + ((w[k] ^ c2) - c2)) & 0xFFFFFFFF
        struct.pack_into("<%dI" % n, buf, g["block"][i], *w)

def poner_checksums(buf, g):
    cs = checksums(buf, g)
    for i in range(10):
        struct.pack_into("<I", buf, g["block"][i] - 8, cs[i])

def cargar_of(datos, juego):
    """Devuelve (buffer en claro, checksums_ok, config). No modifica 'datos'."""
    g = GAMES[juego]
    if len(datos) != g["length"]:
        raise ErrorConversion("El tamano es %d bytes y deberia ser %d." % (len(datos), g["length"]))
    buf = xor_pc(datos, g)
    ok = checksums(buf, g) == checksums_guardados(buf, g)
    descifrar(buf, g)
    return buf, ok, g

def guardar_of(buf, g):
    b = bytearray(buf)
    cifrar(b, g)
    poner_checksums(b, g)
    return bytes(xor_pc(b, g))

# --------------------------------------------------------------------------------------
#  Registro de jugador, nombres, plantillas
# --------------------------------------------------------------------------------------
def rec(juego, idx):
    g = GAMES[juego]
    return g["base"] + idx * 124 if idx < FIRST_EDIT else g["baseE"] + (idx - FIRST_EDIT) * 124

def getraw(buf, juego, idx, t):
    _, off, sh, mask = t
    a = rec(juego, idx) + 48 + off
    return (((buf[a] << 8) | buf[a - 1]) >> sh) & mask

def setraw(buf, juego, idx, t, v):
    _, off, sh, mask = t
    a = rec(juego, idx) + 48 + off
    old = ((buf[a] << 8) | buf[a - 1]) & (0xFFFF & ~(mask << sh))
    v = ((v & mask) << sh) | old
    buf[a - 1] = v & 0xFF
    buf[a] = (v >> 8) & 0xFF

def getname(buf, juego, idx):
    a = rec(juego, idx)
    raw = bytes(buf[a:a + 32]); i = 0
    while i < 30 and not (raw[i] == 0 and raw[i + 1] == 0):
        i += 2
    return raw[:i].decode("utf-16le", "replace")

def setname(buf, juego, idx, nombre):
    a = rec(juego, idx)
    b = nombre.encode("utf-16le")[:30]
    buf[a:a + 32] = b + b"\x00" * (32 - len(b))

def get_bits(buf, juego, idx, p, w):
    a = rec(juego, idx) + 48; v = 0
    for k in range(w):
        v |= ((buf[a + ((p + k) // 8)] >> ((p + k) % 8)) & 1) << k
    return v

def set_bits(buf, juego, idx, p, w, v):
    a = rec(juego, idx) + 48
    for k in range(w):
        q = a + ((p + k) // 8); bit = (p + k) % 8
        buf[q] = (buf[q] & ~(1 << bit)) | (((v >> k) & 1) << bit)

def indices_jugadores(juego):
    n = 5000 if juego == "pes5" else 4784
    return list(range(1, n)) + list(range(FIRST_EDIT, FIRST_EDIT + 184))

def dir_plantilla(juego, t):
    q = SQ[juego]
    if t < q["n23"]:
        return q["slot23"] + t * 46, q["num23"] + t * 23, 23
    c = t - q["n23"]
    return q["slot32"] + c * 64, q["num32"] + c * 32, 32

def get_plantilla(buf, juego, t):
    sl, nm, size = dir_plantilla(juego, t)
    return [buf[sl + 2 * k] | (buf[sl + 2 * k + 1] << 8) for k in range(size)], [buf[nm + k] for k in range(size)]

def set_plantilla(buf, juego, t, ids, nums):
    sl, nm, size = dir_plantilla(juego, t)
    for k in range(size):
        buf[sl + 2 * k] = ids[k] & 0xFF
        buf[sl + 2 * k + 1] = (ids[k] >> 8) & 0xFF
        buf[nm + k] = nums[k] & 0xFF

def orden5(buf, t):                       # orden permutado del plantel en WE9
    j = t if t < 64 else t - 10
    a = 670512 + 628 * j + 6232
    return list(buf[a:a + 32])

def pos6(buf, t):                         # posiciones de los 11 titulares de la formacion 0 en PES6
    a = 677202 + 138 + 364 * t
    return list(buf[a:a + 11])

def nombre_club(buf, juego, j):
    a = (803608 + 140 * j) if juego == "pes5" else (751472 + 88 * j)
    raw = bytes(buf[a:a + 49]); i = raw.find(0)
    return (raw if i < 0 else raw[:i]).decode("utf-8", "replace")

# --------------------------------------------------------------------------------------
#  Algoritmo hungaro (11x11) en Python puro
# --------------------------------------------------------------------------------------
def hungaro(coste):
    n = len(coste); INF = float("inf")
    u = [0.0] * (n + 1); v = [0.0] * (n + 1); p = [0] * (n + 1); way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i; j0 = 0
        minv = [INF] * (n + 1); usado = [False] * (n + 1)
        while True:
            usado[j0] = True; i0 = p[j0]; delta = INF; j1 = 0
            for j in range(1, n + 1):
                if not usado[j]:
                    cur = coste[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur; way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]; j1 = j
            for j in range(n + 1):
                if usado[j]:
                    u[p[j]] += delta; v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]; p[j0] = p[j1]; j0 = j1
            if j0 == 0:
                break
    res = [0] * n
    for j in range(1, n + 1):
        res[p[j] - 1] = j - 1
    return [(i, res[i]) for i in range(n)]

# --------------------------------------------------------------------------------------
#  Apariencia: tablas y reglas
# --------------------------------------------------------------------------------------
PHYS = [(91, 0, -1, "ancho de cabeza"), (105, 0, -6, "largo de cuello"), (105, 4, -6, "pecho"), (106, 0, -6, "brazo"),
        (106, 4, -6, "cintura"), (107, 0, -6, "pierna"), (107, 4, -6, "pantorrilla"), (108, 0, -4, "largo de pierna"),
        (108, 4, 1, "altura de hombros"), (109, 0, 1, "ancho de hombros")]
ACC = [(94, -5, "color de pelo/patron/ojo1"), (95, -1, "barba/gorra"), (96, 0, "manga/color de barba"),
       (98, -5, "muneca/collar"), (99, 0, "pulsera/calzoncillo")]
RESET_BYTES = [90, 97, 100, 102, 103, 104, 110] + list(range(115, 124))
DEFAULT_HAIR = 108

def leer_peinados(ruta):
    xs, ys = [], []
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            xs.append(int(r["peinado_we9"])); ys.append(int(r["peinado_pes6"]))
    if not xs:
        raise ErrorConversion("La tabla de peinados especiales esta vacia.")
    z = sorted(zip(xs, ys))
    return [a for a, _ in z], [b for _, b in z]

class Peinados:
    def __init__(self, xs, ys, especiales6):
        import bisect
        self.bisect, self.xs, self.ys, self.esp = bisect, xs, ys, especiales6

    def snap(self, y):
        k = self.bisect.bisect_left(self.esp, y)
        c = [self.esp[j] for j in (k - 1, k) if 0 <= j < len(self.esp)]
        return min(c, key=lambda v: abs(v - y))

    def predecir(self, x):
        xs, ys = self.xs, self.ys
        if x in xs:
            return self.snap(ys[xs.index(x)])
        k = self.bisect.bisect_left(xs, x)
        if k == 0:
            y = ys[0] + (x - xs[0])
        elif k == len(xs):
            y = ys[-1] + (x - xs[-1])
        else:
            x0, x1, y0, y1 = xs[k - 1], xs[k], ys[k - 1], ys[k]
            y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        return self.snap(round(y))

# --------------------------------------------------------------------------------------
#  Reglas de plantillas
# --------------------------------------------------------------------------------------
ROLE_COL = {0: "GK  0", 2: "CWP  2", 3: "CBT  3", 4: "SB  4", 5: "DMF  5", 6: "WB  6", 7: "CMF  7",
            8: "SMF  8", 9: "AMF  9", 10: "WF 10", 11: "SS  11", 12: "CF  12"}

def rol_de(sel):
    if sel == 0: return 0
    if sel in (1, 2, 3, 6, 7): return 3
    if sel in (4, 5): return 2
    if sel in (8, 9): return 4
    if 10 <= sel <= 14: return 5
    if sel in (15, 16): return 6
    if 17 <= sel <= 21: return 7
    if sel in (22, 23): return 8
    if 24 <= sel <= 28: return 9
    if sel in (29, 30): return 10
    if 31 <= sel <= 35: return 11
    if 36 <= sel <= 40: return 12
    return 7

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)

def camiseta_ascii(nombre):
    return unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().upper()[:15]

def leer_clubes(ruta):
    """Devuelve [(equipo_WE9, equipo_PES6, etiqueta, criterio)] desde un CSV (por nombre de columna)."""
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    req = {"equipo_WE9", "equipo_PES6"}
    if not filas or not req <= set(filas[0].keys()):
        raise ErrorConversion("La tabla de clubes debe tener las columnas 'equipo_WE9' y 'equipo_PES6'.")
    out = []
    for r in filas:
        try:
            t5, t6 = int(r["equipo_WE9"]), int(r["equipo_PES6"])
        except ValueError:
            raise ErrorConversion("Tabla de clubes: hay valores no numericos en equipo_WE9/equipo_PES6.")
        if not (74 <= t5 < 212 and 73 <= t6 < 213):
            raise ErrorConversion("Tabla de clubes: equipo fuera de rango (WE9 74..211, PES6 73..212): %d -> %d." % (t5, t6))
        out.append((t5, t6, "%s -> %s" % (r.get("nombre_WE9", t5), r.get("nombre_PES6", t6)), r.get("criterio", "")))
    return out

# --------------------------------------------------------------------------------------
#  CONVERSION
# --------------------------------------------------------------------------------------
def convertir(ruta_we9, ruta_base, ruta_clubes, ruta_peinados, carpeta_salida,
              apariencia=True, renombrar_team=True, log=print, escribir=True):
    """Convierte y verifica. Devuelve un diccionario con el resumen. Lanza ErrorConversion si algo falla."""
    # ---- 0) lectura y validacion de entradas
    if not ruta_base:
        raise ErrorConversion("Falta el option file base de PES6. Elegi un KONAMI-WIN32PES6OPT virgen "
                              "(el que crea el juego al empezar sin datos editados).")
    for ruta, nombre in ((ruta_we9, "option file de WE9/PES5"), (ruta_base, "base de PES6"),
                         (ruta_clubes, "tabla de clubes"), (ruta_peinados, "tabla de peinados")):
        if not os.path.isfile(ruta):
            raise ErrorConversion("No se encuentra %s: %s" % (nombre, ruta))
    if os.path.abspath(os.path.join(carpeta_salida, NOMBRE_SALIDA)) in (os.path.abspath(ruta_we9), os.path.abspath(ruta_base)):
        raise ErrorConversion("La salida coincide con un archivo de entrada. Elige otra carpeta de salida.")
    d5 = open(ruta_we9, "rb").read()
    d6 = open(ruta_base, "rb").read()
    if len(d5) == GAMES["pes6"]["length"]:
        raise ErrorConversion("El archivo de origen parece un option file de PES6, no de WE9/PES5.")
    try:
        b5, ok5, _ = cargar_of(d5, "pes5")
    except ErrorConversion as e:
        raise ErrorConversion("Option file de WE9/PES5: %s" % e)
    if not ok5:
        raise ErrorConversion("Los checksums del option file de WE9/PES5 no son validos: el archivo esta danado o no es de WE9/PES5.")
    try:
        b6, ok6, g6 = cargar_of(d6, "pes6")
    except ErrorConversion as e:
        raise ErrorConversion("Base de PES6: %s" % e)
    if not ok6:
        raise ErrorConversion("Los checksums de la base de PES6 no son validos.")
    orig6 = bytearray(b6)
    log("Entradas validadas (tamano y checksums).")

    # ---- constantes de apariencia sacadas de la base de PES6 (una sola vez, antes de escribir)
    reales6 = range(1, 4784)
    ED = list(range(FIRST_EDIT, FIRST_EDIT + 184))
    moda = lambda vals: Counter(vals).most_common(1)[0][0]
    RB = lambda b, i: orig6[rec("pes6", i) + b]
    zero_ok = sum(1 for i in reales6 if getraw(orig6, "pes6", i, FACETYPE) == 0 and getraw(orig6, "pes6", i, HAIR) == 0)
    OBS_BYTE = {rb: {RB(rb, i) for i in reales6} for rb, _, _ in ACC}
    DEF_BYTE = {rb: moda([RB(rb, i) for i in ED]) for rb in [a[0] for a in ACC] + RESET_BYTES}
    OBS_NIB = {(rb, sh): {get_bits(orig6, "pes6", i, (rb - 48) * 8 + sh, 4) for i in reales6} for rb, sh, _, _ in PHYS}
    DEF_NIB = {(rb, sh): moda([get_bits(orig6, "pes6", i, (rb - 48) * 8 + sh, 4) for i in ED]) for rb, sh, _, _ in PHYS}
    HI = {rb: moda([RB(rb, e) & 0xF0 for e in ED]) for rb in (91, 109)}
    HI93 = moda([RB(93, e) & 0xF8 for e in ED])
    esp6 = sorted({getraw(orig6, "pes6", i, HAIR) for i in reales6 if getraw(orig6, "pes6", i, HAIR) >= 1026})
    xs, ys = leer_peinados(ruta_peinados)
    peinados = Peinados(xs, ys, esp6)

    # ---- 1) emparejamiento de equipos
    inv6 = {v: k for k, v in enumerate(NAC6)}
    team_map = []
    for t in range(57):
        if NAC5[t] in inv6:
            team_map.append((t, inv6[NAC5[t]], "Seleccion %s" % NAC5[t], "mismo pais"))
    omitidas = [(t, NAC5[t]) for t in range(57) if NAC5[t] not in inv6]
    intactas = [(t, NAC6[t]) for t in range(57) if NAC6[t] not in set(NAC5)]
    for t5, t6, n in [(57, 62, "Classic Argentina"), (58, 63, "Classic Brazil"), (59, 57, "Classic England"),
                      (60, 58, "Classic France"), (61, 59, "Classic Germany"), (62, 60, "Classic Italy"),
                      (63, 61, "Classic Netherlands"), (64, 64, "Japan 1")]:
        team_map.append((t5, t6, n, "clasico/Japon por nombre"))
    for k in range(7):
        team_map.append((66 + k, 65 + k, "Edited National %d" % (k + 1), "por posicion"))
    team_map.append((73, 72, "Edited", "por posicion"))
    team_map += leer_clubes(ruta_clubes)
    if len({m[0] for m in team_map}) != len(team_map) or len({m[1] for m in team_map}) != len(team_map):
        raise ErrorConversion("La tabla de clubes repite equipos de origen o de destino.")
    dest6 = {m[1] for m in team_map}
    log("Equipos emparejados: %d." % len(team_map))

    # ---- 2) plantillas efectivas de WE9 (con el orden permutado aplicado)
    def efectiva5(t):
        ids, nums = get_plantilla(b5, "pes5", t)
        if t < 64 or 74 <= t < 212:
            o = orden5(b5, t); size = len(ids)
            ids = [ids[o[k]] if o[k] < size else 0 for k in range(size)]
            nums = [nums[o[k]] if o[k] < size else 255 for k in range(size)]
        return ids, nums
    plantillas5 = {m[0]: efectiva5(m[0]) for m in team_map}
    R = {i for ids, _ in plantillas5.values() for i in ids if i}

    # ---- 3) asignacion de huecos de jugador en PES6
    P = set()
    for t in range(213):
        if t in dest6:
            continue
        P.update(i for i in get_plantilla(b6, "pes6", t)[0] if i)
    con_nombre = [i for i in indices_jugadores("pes5") if getname(b5, "pes5", i)]
    Q = [i for i in con_nombre if i not in R]
    LIMITE = 4413
    usable = lambda s: 1 <= s <= LIMITE and s not in P
    slotmap, ocupados = {}, set()

    def identidad(lista):
        pend = []
        for i in sorted(lista):
            if i >= FIRST_EDIT or (usable(i) and i not in ocupados):
                slotmap[i] = i; ocupados.add(i)
            else:
                pend.append(i)
        return pend
    pend = identidad(sorted(R))
    pool = [s for s in range(1, LIMITE + 1) if usable(s) and s not in ocupados and s not in R]
    for i in pend:
        s = pool.pop(0); slotmap[i] = s; ocupados.add(s)
    pendQ = identidad(Q)
    pool = [s for s in range(1, LIMITE + 1) if usable(s) and s not in ocupados]
    descartados = []
    for i in pendQ:
        if pool:
            s = pool.pop(0); slotmap[i] = s; ocupados.add(s)
        else:
            descartados.append(i)
    log("Jugadores en plantillas: %d | libres con nombre: %d | sin hueco (descartados): %d" % (len(R), len(Q), len(descartados)))

    # ---- 4) jugadores
    avisos = []
    stats = Counter(); ap_rows = {}
    for i5, i6 in slotmap.items():
        nombre = getname(b5, "pes5", i5)
        setname(b6, "pes6", i6, nombre[:15])
        a5, a6 = rec("pes5", i5), rec("pes6", i6)
        camis = bytes(b5[a5 + 32:a5 + 48])
        if not camis.strip(b"\x00"):
            s = camiseta_ascii(nombre).encode("ascii"); camis = s + b"\x00" * (16 - len(s))
        b6[a6 + 32:a6 + 48] = camis
        for c in ALLCOLS:
            v = getraw(b5, "pes5", i5, T5[c])
            if c == "NATIONALITY":
                nm = NAT5.get(v, "?")
                if nm in NAT6_INV:
                    v = NAT6_INV[nm]
                else:
                    v = NAT6_FREE; avisos.append("%s: nacionalidad %s no existe en PES6 -> Free Nationality" % (nombre, nm))
            elif c == "REGISTERED POSITION" and v == 13:
                v = 12
            setraw(b6, "pes6", i6, T6[c], v)
        setraw(b6, "pes6", i6, CALLNAME, 0xCDCD)
        for fl in (FLAG_NAME, FLAG_SHIRT, FLAG_CALL, FLAG_ABIL):
            setraw(b6, "pes6", i6, fl, 1)
        for k in (FACETYPE, FACE):
            setraw(b6, "pes6", i6, k, 0)                      # sin cara real ni especial heredada
        if not apariencia:
            continue
        h5 = getraw(b5, "pes5", i5, HAIR); ft5 = getraw(b5, "pes5", i5, FT5)
        if h5 == 0:
            h6 = 0 if (ft5 == 0 and zero_ok >= 10) else DEFAULT_HAIR; regla = "cero"
        elif h5 < 1026:
            h6 = h5; regla = "estandar"
        else:
            h6 = peinados.predecir(h5); regla = "especial"
        setraw(b6, "pes6", i6, HAIR, h6)
        sk = getraw(b5, "pes5", i5, SKIN5); setraw(b6, "pes6", i6, SKIN6, sk)
        stats["peinado " + regla] += 1; ap_rows[i5] = (h5, h6, regla, sk)
        for rb in RESET_BYTES:
            b6[a6 + rb] = DEF_BYTE[rb]
        for rb in (91, 109):
            b6[a6 + rb] = (b6[a6 + rb] & 0x0F) | HI[rb]
        b6[a6 + 93] = (b6[a6 + 93] & 0x07) | HI93
        for rb, sh, d, nm in PHYS:
            v = get_bits(b5, "pes5", i5, (rb - 48) * 8 + sh + d, 4)
            if v in OBS_NIB[(rb, sh)]:
                stats["complexion copiada"] += 1
            else:
                v = DEF_NIB[(rb, sh)]; stats["complexion -> defecto"] += 1
            set_bits(b6, "pes6", i6, (rb - 48) * 8 + sh, 4, v)
        for rb, d, nm in ACC:
            v = get_bits(b5, "pes5", i5, (rb - 48) * 8 + d, 8)
            if v in OBS_BYTE[rb]:
                stats["accesorio copiado"] += 1
            else:
                v = DEF_BYTE[rb]; stats["accesorio -> defecto"] += 1
            b6[a6 + rb] = v
    log("Jugadores escritos: %d." % len(slotmap))

    # ---- 5) plantillas y titulares segun la formacion de PES6
    fuera_de_rol = 0; reordenados = 0
    for t5, t6, etiqueta, crit in team_map:
        ids, nums = plantillas5[t5]
        ids = [slotmap.get(i, 0) if i else 0 for i in ids]
        nums = [n if ids[k] else 255 for k, n in enumerate(nums)]
        if t6 < 64 or 73 <= t6 < 213:
            pos = pos6(b6, t6); n = 11
            coste = [[0.0] * n for _ in range(n)]
            for a in range(n):
                p = ids[a]
                for j in range(n):
                    if not p:
                        continue
                    r = rol_de(pos[j])
                    ok = getraw(b6, "pes6", p, T6[ROLE_COL[r]]) == 1
                    reg = getraw(b6, "pes6", p, T6["REGISTERED POSITION"])
                    coste[a][j] = (0 if ok else 10) + (0 if reg == r or (r == 3 and reg in (2, 3)) else 1) + 0.001 * abs(a - j)
            nuevos, nnums = ids[:], nums[:]
            for a, j in hungaro(coste):
                nuevos[j] = ids[a]; nnums[j] = nums[a]
            fuera_de_rol += sum(1 for j in range(n) if nuevos[j] and getraw(b6, "pes6", nuevos[j], T6[ROLE_COL[rol_de(pos[j])]]) != 1)
            reordenados += 1
            ids, nums = nuevos, nnums
        set_plantilla(b6, "pes6", t6, ids, nums)

    # ---- 6) renombrar Team A..R con el nombre de WE9
    renombrados = []
    if renombrar_team:
        club_map = {t6 - 73: t5 - 74 for t5, t6, _, _ in team_map if t6 >= 73}
        for j in range(140):
            a6 = 751472 + 88 * j
            if not re.fullmatch(r"Team [A-R]", nombre_club(orig6, "pes6", j)) or j not in club_map:
                continue
            a5 = 803608 + 140 * club_map[j]
            nm = bytes(b5[a5:a5 + 49]); ab = bytes(b5[a5 + 73:a5 + 76])
            nm = nm[:48] + b"\x00" * (49 - len(nm[:48]))
            antes = nombre_club(orig6, "pes6", j)
            b6[a6:a6 + 49] = nm; b6[a6 + 49:a6 + 52] = ab; b6[a6 + 56] = 1
            renombrados.append((j, antes, nombre_club(b6, "pes6", j), ab.decode("latin-1")))
    for p in (45, 46, 5938, 5939):
        b6[p] = 1

    # ---- 7) guardar en memoria y verificar ANTES de escribir nada
    salida = guardar_of(b6, g6)
    chk, ok, _ = cargar_of(salida, "pes6")
    if not ok:
        raise ErrorConversion("Verificacion fallida: los checksums del archivo generado no son validos.")
    ck = set()
    for i in range(10):
        a = g6["block"][i] - 8; ck.update(range(a, a + 4))
    if any(chk[i] != b6[i] for i in range(len(b6)) if i not in ck):
        raise ErrorConversion("Verificacion fallida: el archivo generado no coincide con lo previsto.")
    errores = 0
    for t5, t6, etiqueta, crit in team_map:
        ids6 = [i for i in get_plantilla(chk, "pes6", t6)[0] if i]
        n5 = sorted(getname(b5, "pes5", i)[:15] for i in plantillas5[t5][0] if i and i in slotmap)
        if n5 != sorted(getname(chk, "pes6", i) for i in ids6):
            errores += 1; log("ERROR: plantilla distinta en %s" % etiqueta)
        if len(ids6) != len(set(ids6)):
            errores += 1; log("ERROR: jugador repetido en %s" % etiqueta)
    esperado = set()
    for i6 in slotmap.values():
        a = rec("pes6", i6); esperado.update(range(a, a + 124))
    for t5, t6, _, _ in team_map:
        sl, nm, size = dir_plantilla("pes6", t6)
        esperado.update(range(sl, sl + 2 * size)); esperado.update(range(nm, nm + size))
    esperado.update((45, 46, 5938, 5939))
    for j, _, _, _ in renombrados:
        a6 = 751472 + 88 * j; esperado.update(range(a6, a6 + 52)); esperado.add(a6 + 56)
    fuera = sum(1 for i in range(len(b6)) if b6[i] != orig6[i] and i not in esperado)
    if errores or fuera:
        raise ErrorConversion("Verificacion fallida: %d errores de plantilla y %d bytes modificados fuera de lo previsto. No se genero ningun archivo." % (errores, fuera))
    log("Verificacion correcta: checksums validos, plantillas iguales a las de WE9 y ningun byte fuera de lo previsto.")

    resumen = {
        "equipos": len(team_map), "referenciados": len(R), "libres_con_nombre": len(Q), "descartados": len(descartados),
        "transferidos": len(slotmap), "protegidos": len(P), "movidos": sum(1 for k, v in slotmap.items() if k != v),
        "avisos_nacionalidad": len(avisos), "fuera_de_rol": fuera_de_rol, "reordenados": reordenados,
        "selecciones_omitidas": omitidas, "selecciones_intactas": intactas, "renombrados": [(o, n, ab) for _, o, n, ab in renombrados],
        "apariencia": dict(stats), "salida": None,
    }
    if not escribir:
        return resumen

    # ---- 8) escribir salida e informes (solo si todo salio bien)
    os.makedirs(carpeta_salida, exist_ok=True)
    ruta_of = os.path.join(carpeta_salida, NOMBRE_SALIDA)
    with open(ruta_of, "wb") as f:
        f.write(salida)
    resumen["salida"] = ruta_of
    with open(os.path.join(carpeta_salida, "reporte_jugadores.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["indice_WE9", "nombre", "estado", "indice_PES6"])
        for k, v in sorted(slotmap.items()):
            w.writerow([k, getname(b5, "pes5", k), "transferido" if k == v else "transferido (otro hueco)", v])
        for k in descartados:
            w.writerow([k, getname(b5, "pes5", k), "NO transferido: sin hueco libre", ""])
    with open(os.path.join(carpeta_salida, "reporte_equipos.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["equipo_WE9", "equipo_PES6", "descripcion", "criterio"])
        for fila in team_map:
            w.writerow(fila)
    if apariencia:
        with open(os.path.join(carpeta_salida, "reporte_apariencia.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["indice_WE9", "nombre", "peinado_WE9", "peinado_PES6", "regla_peinado", "piel"])
            for k, (h5, h6, regla, sk) in sorted(ap_rows.items()):
                w.writerow([k, getname(b5, "pes5", k), h5, h6, regla, sk])
    with open(os.path.join(carpeta_salida, "registro.txt"), "w", encoding="utf-8") as f:
        f.write("Convertidor WE9/PES5 -> PES6, version %s\n\n" % VERSION)
        for k, v in resumen.items():
            f.write("%s: %s\n" % (k, v))
        if avisos:
            f.write("\nAvisos de nacionalidad:\n" + "\n".join(avisos) + "\n")
    return resumen

# --------------------------------------------------------------------------------------
#  Interfaz de linea de comandos y ventana
# --------------------------------------------------------------------------------------
def texto_resumen(r):
    l = ["Equipos con plantilla: %d" % r["equipos"], "Jugadores transferidos: %d" % r["transferidos"],
         "Jugadores sin hueco (no transferidos): %d" % r["descartados"],
         "Titulares fuera de su rol natural: %d de %d equipos reordenados" % (r["fuera_de_rol"], r["reordenados"]),
         "Selecciones de WE9 sin equivalente en PES6: " + (", ".join(n for _, n in r["selecciones_omitidas"]) or "ninguna"),
         "Clubes renombrados: %d" % len(r["renombrados"])]
    if r["salida"]:
        l.append("Archivo generado: %s" % r["salida"])
    return "\n".join(l)

def salida_por_defecto(ruta_we9):
    return os.path.join(os.path.dirname(os.path.abspath(ruta_we9)), "convertido_PES6")

def main_cli(args):
    import argparse
    p = argparse.ArgumentParser(description="Convierte un option file de WE9/PES5 a PES6.")
    p.add_argument("origen", help="option file de WE9/PES5/WE9LE")
    p.add_argument("--base", default=base_por_defecto(), help="option file virgen de PES6 (KONAMI-WIN32PES6OPT)")
    p.add_argument("--clubes", default=ruta_datos("clubes_we9_a_pes6.csv"))
    p.add_argument("--peinados", default=ruta_datos("peinados_especiales.csv"))
    p.add_argument("--salida", default=None)
    p.add_argument("--sin-apariencia", action="store_true")
    p.add_argument("--sin-renombrar", action="store_true")
    p.add_argument("--solo-verificar", action="store_true", help="convierte y verifica en memoria, sin escribir archivos")
    p.add_argument("--cli", action="store_true")
    a = p.parse_args(args)
    try:
        r = convertir(a.origen, a.base, a.clubes, a.peinados, a.salida or salida_por_defecto(a.origen),
                      apariencia=not a.sin_apariencia, renombrar_team=not a.sin_renombrar, escribir=not a.solo_verificar)
    except ErrorConversion as e:
        print("ERROR:", e); return 1
    print("\n" + texto_resumen(r)); return 0

def main_gui(archivo_inicial=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES
        raiz = TkinterDnD.Tk(); dnd = True
    except Exception:
        raiz = tk.Tk(); dnd = False
    raiz.title("Convertidor WE9 / PES5  ->  PES6   v%s" % VERSION)
    raiz.geometry("780x560")
    v_origen = tk.StringVar(value=archivo_inicial or "")
    v_base = tk.StringVar(value=base_por_defecto())
    v_clubes = tk.StringVar(value=ruta_datos("clubes_we9_a_pes6.csv"))
    v_pein = tk.StringVar(value=ruta_datos("peinados_especiales.csv"))
    v_sal = tk.StringVar(value=salida_por_defecto(archivo_inicial) if archivo_inicial else "")
    v_ap = tk.BooleanVar(value=True); v_team = tk.BooleanVar(value=True)
    cola = queue.Queue()

    def fila(r, texto, var, tipos=None, carpeta=False):
        ttk.Label(raiz, text=texto).grid(row=r, column=0, sticky="w", padx=8, pady=3)
        e = ttk.Entry(raiz, textvariable=var, width=70); e.grid(row=r, column=1, padx=4)
        def examinar():
            ruta = filedialog.askdirectory() if carpeta else filedialog.askopenfilename(filetypes=tipos or [("Todos", "*.*")])
            if ruta:
                var.set(ruta)
                if var is v_origen and not v_sal.get():
                    v_sal.set(salida_por_defecto(ruta))
        ttk.Button(raiz, text="Examinar...", command=examinar).grid(row=r, column=2, padx=6)
        return e
    e0 = fila(0, "Option file de WE9/PES5:", v_origen)
    fila(1, "Option file virgen de PES6:", v_base)
    fila(2, "Tabla de clubes (CSV):", v_clubes, [("CSV", "*.csv")])
    fila(3, "Tabla de peinados (CSV):", v_pein, [("CSV", "*.csv")])
    fila(4, "Carpeta de salida:", v_sal, carpeta=True)
    ttk.Checkbutton(raiz, text="Incluir apariencia aproximada (peinado, piel, complexion, accesorios)", variable=v_ap).grid(row=5, column=1, sticky="w")
    ttk.Checkbutton(raiz, text="Renombrar los clubes Team A..R con el nombre que tenian en WE9", variable=v_team).grid(row=6, column=1, sticky="w")
    area = tk.Text(raiz, height=17, width=95, state="disabled"); area.grid(row=8, column=0, columnspan=3, padx=8, pady=6)
    estado = ttk.Label(raiz, text="Arrastra el option file de WE9 sobre la ventana o elige el archivo." if dnd else "Elige el option file de WE9/PES5 (o arrastralo sobre el icono del programa).")
    estado.grid(row=9, column=0, columnspan=3, sticky="w", padx=8)

    def escribir_log(msg):
        area.configure(state="normal"); area.insert("end", msg + "\n"); area.see("end"); area.configure(state="disabled")

    def trabajo(solo_verificar):
        try:
            r = convertir(v_origen.get(), v_base.get(), v_clubes.get(), v_pein.get(), v_sal.get(),
                          apariencia=v_ap.get(), renombrar_team=v_team.get(), log=lambda m: cola.put(("log", m)),
                          escribir=not solo_verificar)
            cola.put(("ok", r))
        except ErrorConversion as e:
            cola.put(("error", str(e)))
        except Exception:
            cola.put(("error", "Error inesperado:\n" + traceback.format_exc()))

    def lanzar(solo_verificar=False):
        if not v_origen.get():
            messagebox.showwarning("Falta el archivo", "Elige primero el option file de WE9/PES5."); return
        if not v_sal.get():
            v_sal.set(salida_por_defecto(v_origen.get()))
        area.configure(state="normal"); area.delete("1.0", "end"); area.configure(state="disabled")
        boton.configure(state="disabled"); boton2.configure(state="disabled"); estado.configure(text="Convirtiendo, espera unos segundos...")
        threading.Thread(target=trabajo, args=(solo_verificar,), daemon=True).start()
        raiz.after(150, revisar)

    def revisar():
        try:
            while True:
                tipo, dato = cola.get_nowait()
                if tipo == "log":
                    escribir_log(dato)
                elif tipo == "ok":
                    escribir_log("\n" + texto_resumen(dato))
                    boton.configure(state="normal"); boton2.configure(state="normal")
                    estado.configure(text="Listo." if dato["salida"] else "Verificacion correcta (no se escribio ningun archivo).")
                    if dato["salida"]:
                        messagebox.showinfo("Conversion terminada", "Archivo generado:\n%s\n\nHaz copia de seguridad de tu option file de PES6 antes de usarlo." % dato["salida"])
                    return
                elif tipo == "error":
                    escribir_log("\nERROR: " + dato)
                    boton.configure(state="normal"); boton2.configure(state="normal")
                    estado.configure(text="La conversion se detuvo. No se genero ningun archivo.")
                    messagebox.showerror("No se pudo convertir", dato); return
        except queue.Empty:
            pass
        raiz.after(150, revisar)

    boton = ttk.Button(raiz, text="Convertir", command=lambda: lanzar(False)); boton.grid(row=7, column=1, sticky="e", pady=6)
    boton2 = ttk.Button(raiz, text="Solo verificar", command=lambda: lanzar(True)); boton2.grid(row=7, column=2, pady=6)
    if dnd:
        def soltar(ev):
            ruta = raiz.tk.splitlist(ev.data)[0]
            v_origen.set(ruta); v_sal.set(salida_por_defecto(ruta))
        raiz.drop_target_register(DND_FILES); raiz.dnd_bind("<<Drop>>", soltar)
    if archivo_inicial:
        raiz.after(300, lambda: lanzar(False))      # arrastrado sobre el .exe: convierte directamente
    raiz.mainloop()
    return 0

if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv and (argv[0] in ("-h", "--help") or "--cli" in argv or "--solo-verificar" in argv):
        sys.exit(main_cli([a for a in argv if a != "--cli"]))
    candidato = argv[0] if argv and not argv[0].startswith("--") else None
    sys.exit(main_gui(candidato))

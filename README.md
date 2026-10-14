# Convertidor de option files WE9 / PES5 / WE9LE → PES6 (PC)

Pasa tu base de datos editada de **Winning Eleven 9 / PES5 / WE9 Liveware Evolution** a **PES6**: jugadores, plantillas
de selecciones y clubes, y una apariencia aproximada. Escribe un option file de PES6 válido (cifrado y checksums
correctos) **sin usar ningún editor**. Nunca modifica los archivos de entrada.

Nació para llevar a PES6 un option file de WE9 editado durante años con cientos de jugadores *fantasy*. Una conversión
completa (4459 jugadores, 207 equipos) **se probó en el juego** y funciona.

---

## Uso

1. Bajá `Convertidor_WE9_a_PES6.exe` desde **Releases** (o corré `python we9_a_pes6.py`).
2. Arrastrá tu option file de WE9 (`KONAMI-WIN32WE9UOPT` o `KONAMI-WIN32WE9KOPT`) sobre el exe, o abrilo y elegilo con
   *Examinar…*.
3. En *Option file virgen de PES6* elegí un `KONAMI-WIN32PES6OPT` **virgen**: el que crea el juego al empezar, sin datos
   editados. No viene incluido porque son datos de Konami.
4. Se crea `convertido_PES6\` junto a tu archivo:

| Archivo | Contenido |
|---|---|
| `KONAMI-WIN32PES6OPT` | el option file de PES6, con el nombre exacto que espera el juego |
| `reporte_jugadores.csv` | qué jugador fue a qué hueco y cuáles no entraron |
| `reporte_equipos.csv` | qué equipo de WE9 fue a qué equipo de PES6 |
| `reporte_apariencia.csv` | peinado y piel convertidos |
| `registro.txt` | resumen y avisos |

5. Hacé copia de tu option file de PES6 y copiá el nuevo a la carpeta de partidas del juego.

También se puede usar por consola: `python we9_a_pes6.py ORIGEN --base PES6_VIRGEN [--salida CARPETA]
[--sin-apariencia] [--solo-verificar]`.

## Qué transfiere

- **Jugadores**: nombre, nombre de camiseta, los 46 atributos, posiciones, las 23 habilidades especiales que existen en
  los dos juegos, pie, lado, edad, altura, peso, nacionalidad (convertida **por nombre**, porque los índices cambian
  entre juegos) y estilos.
- **Plantillas** de selecciones, clásicos, Japón, editados y clubes. Los **titulares se reordenan** según la formación
  de PES6 con una asignación óptima (algoritmo húngaro), para que cada uno quede en un puesto que sabe jugar.
- **Apariencia aproximada**:
  - peinado: los estándar se copian; los especiales, con una tabla de equivalencias interpolada;
  - piel, complexión y accesorios, cuando el valor existe en PES6;
  - cara genérica, para no heredar una cara real del hueco.
- **Clubes "Team A…R"** de PES6 (la Bundesliga sin licencia) renombrados con el nombre que tenían en WE9.

## Cómo funciona (resumen)

1. **Valida** tamaños y checksums de los dos archivos.
2. **Descifra** los dos formatos. Las dos capas de cifrado y las tablas salen de los editores comunitarios PESEditor y
   PES-Editor-5, y se verifican por huella.
3. **Empareja equipos**:
   - selecciones por el país más frecuente de su plantilla, porque PES6 intercala países nuevos;
   - clubes con `datos/clubes_we9_a_pes6.csv`: primero por nombre, después por posición dentro de cada liga
     (es editable).
4. **Asigna huecos** de jugador en PES6, protegiendo Liga Máster, jóvenes y los equipos que no se tocan (índices ≥ 4414).
5. **Escribe campo a campo**. Nunca copia registros en bruto: los mismos datos están en bits distintos en WE9 y en PES6.
6. **Verifica antes de guardar**: checksums, plantillas iguales a las de WE9, sin jugadores repetidos y **ningún byte
   cambiado fuera de lo previsto**. Si algo falla, no deja ningún archivo y explica el motivo.

La documentación completa del formato (cifrado, bloques, registro de jugador, apariencia, plantillas, nacionalidades)
está en el repo **we-espia**: `docs/OPTION_FILES.md` y `docs/option-files/PROYECTO_conversor_we9_pes6.md`.

## Archivos editables (`datos/`)

| Archivo | Para qué |
|---|---|
| `clubes_we9_a_pes6.csv` | emparejamiento de clubes (columnas `equipo_WE9`, `equipo_PES6`), con los intercambios ya revisados |
| `peinados_especiales.csv` | equivalencias de peinados especiales (`peinado_we9`, `peinado_pes6`) |
| `tablas.json` | cifrado, campos de jugador y nacionalidades (generado; no tocar) |
| `base_pes6_virgen.bin` | (opcional, no incluido) tu option file virgen de PES6; si está, se usa por defecto |

## Limitaciones conocidas

- Los jugadores de WE9 que no están en ninguna plantilla emparejada y no caben en PES6 no se transfieren (quedan
  listados en `reporte_jugadores.csv`).
- Selecciones de WE9 sin equivalente en PES6 (Marruecos, Senegal, Venezuela, China) se omiten.
- La apariencia es aproximada: no se trasladan caras reales ni rostros especiales.
- No se copian escudos, camisetas, formaciones ni nombres de clubes (salvo Team A…R).
- Las habilidades que existen solo en WE9 se pierden.

## Desarrollo

- Un solo archivo, `we9_a_pes6.py`, con biblioteca estándar de Python (tkinter para la ventana). Sin numpy: el húngaro
  es propio.
- Pruebas: `python tests\test_conversion.py RUTA\KONAMI-WIN32WE9UOPT` (y `tests\prueba_ventana_simulada.py`).
- Exe portable: `compilar_exe.bat` (PyInstaller, `Convertidor_WE9_a_PES6.spec`). Algunos antivirus marcan los exe de
  PyInstaller; es un falso positivo.

## Repos relacionados

- **Convertidor-WE9-WE9LE**: pasa option files entre WE9 y WE9 Liveware Evolution.
- **we-espia**: lector en vivo de partidos y librería de option files (`optionfile.py`).

## Licencia

MIT. PES, Winning Eleven y KONAMI son marcas de Konami. Proyecto de fans, sin relación con Konami.

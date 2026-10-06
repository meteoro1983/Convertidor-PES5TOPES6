# Convertidor de option files WE9 / PES5 → PES6 (PC)

Pasa jugadores (datos, atributos, habilidades, nacionalidad), plantillas de selecciones y clubes, y una
apariencia aproximada de un option file de **Winning Eleven 9 / PES5** a uno de **PES6**, con cifrado y
checksums correctos y sin necesidad de ningún editor. Nunca modifica los archivos de entrada.

## Uso
1. Descargá `Convertidor_WE9_a_PES6.exe` desde **Releases** (o corré `python we9_a_pes6.py`).
2. Elegí tu option file de WE9 (`KONAMI-WIN32WE9UOPT` / `...KOPT`) y **tu option file virgen de PES6**
   (`KONAMI-WIN32PES6OPT`, el que crea el juego al empezar sin datos editados). Por derechos de Konami,
   el repositorio no incluye ninguno.
3. Se crea `convertido_PES6\` con el nuevo option file y los reportes. Más detalle en `LEEME.txt`.

Tablas generadas a partir de los editores comunitarios PESEditor (PES6) y PES-Editor-5 (PES5/WE9).
Pruebas: `python tests\test_conversion.py RUTA\KONAMI-WIN32WE9UOPT`.

Licencia: MIT. PES, Winning Eleven y KONAMI son marcas de Konami; proyecto de fans, sin relación con Konami.

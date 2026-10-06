"""Pruebas del convertidor. Uso:  python tests/test_conversion.py RUTA_AL_OPTION_FILE_DE_WE9
Compara contra los valores de referencia de la conversion verificada (WE9 del usuario + PES6 virgen incluido)."""
import importlib.util, os, shutil, sys, tempfile, unittest
AQUI = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("conv", os.path.join(AQUI, "..", "we9_a_pes6.py"))
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
WE9 = sys.argv.pop(1) if len(sys.argv) > 1 else os.environ.get("WE9_OF", "")
BASE, CLUBES, PEIN = C.ruta_datos("base_pes6_virgen.bin"), C.ruta_datos("clubes_we9_a_pes6.csv"), C.ruta_datos("peinados_especiales.csv")

class Cripto(unittest.TestCase):
    def test_huellas_y_ida_y_vuelta(self):
        self.assertEqual((len(C.TAB["keypc"]), len(C.TAB["key5"]), len(C.TAB["key6"])), (256, 367, 446))
        for ruta, juego in ((BASE, "pes6"), (WE9, "pes5")):
            if not os.path.isfile(ruta): continue
            datos = open(ruta, "rb").read()
            buf, ok, g = C.cargar_of(datos, juego)
            self.assertTrue(ok)
            self.assertEqual(C.guardar_of(buf, g), datos)

class Errores(unittest.TestCase):
    def conv(self, origen, **kw):
        d = tempfile.mkdtemp()
        try:
            return C.convertir(origen, kw.get("base", BASE), CLUBES, PEIN, os.path.join(d, "out"), log=lambda m: None)
        finally: shutil.rmtree(d, ignore_errors=True)
    def test_tamano_incorrecto(self):
        f = tempfile.NamedTemporaryFile(delete=False); f.write(b"x" * 1000); f.close()
        with self.assertRaises(C.ErrorConversion): self.conv(f.name)
    def test_origen_es_pes6(self):
        with self.assertRaises(C.ErrorConversion) as cm: self.conv(BASE)
        self.assertIn("PES6", str(cm.exception))
    @unittest.skipUnless(os.path.isfile(WE9), "falta el option file de WE9")
    def test_checksum_roto(self):
        d = bytearray(open(WE9, "rb").read()); d[700000] ^= 1
        f = tempfile.NamedTemporaryFile(delete=False); f.write(d); f.close()
        with self.assertRaises(C.ErrorConversion): self.conv(f.name)
    @unittest.skipUnless(os.path.isfile(WE9), "falta el option file de WE9")
    def test_salida_igual_a_entrada(self):
        d = tempfile.mkdtemp(); shutil.copy(BASE, os.path.join(d, C.NOMBRE_SALIDA))
        with self.assertRaises(C.ErrorConversion):
            C.convertir(WE9, os.path.join(d, C.NOMBRE_SALIDA), CLUBES, PEIN, d, log=lambda m: None)

@unittest.skipUnless(os.path.isfile(WE9), "falta el option file de WE9")
class Referencia(unittest.TestCase):
    def test_conversion_completa(self):
        d = tempfile.mkdtemp()
        r = C.convertir(WE9, BASE, CLUBES, PEIN, d, log=lambda m: None)
        self.assertEqual((r["equipos"], r["referenciados"], r["libres_con_nombre"], r["descartados"], r["transferidos"]), (207, 4315, 764, 620, 4459))
        self.assertEqual((r["protegidos"], r["movidos"], r["avisos_nacionalidad"], r["reordenados"]), (138, 287, 7, 198))
        self.assertEqual(r["apariencia"]["peinado estandar"], 3332); self.assertEqual(r["apariencia"]["peinado especial"], 1072); self.assertEqual(r["apariencia"]["peinado cero"], 55)
        self.assertEqual([n for _, n in r["selecciones_omitidas"]], ["Morocco", "Senegal", "Venezuela", "China"])
        datos = open(r["salida"], "rb").read(); buf, ok, g = C.cargar_of(datos, "pes6"); self.assertTrue(ok)
        nombres = [C.nombre_club(buf, "pes6", j) for j in range(122, 140)]
        self.assertEqual(nombres[:3], ["Domstadt", "Alm", "Stahlstadt"]); self.assertIn("Wolfsburg", nombres)
        # el origen y la base no se modifican
        self.assertEqual(open(BASE, "rb").read(), open(C.ruta_datos("base_pes6_virgen.bin"), "rb").read())
        shutil.rmtree(d, ignore_errors=True)
    def test_determinismo(self):
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
        C.convertir(WE9, BASE, CLUBES, PEIN, a, log=lambda m: None); C.convertir(WE9, BASE, CLUBES, PEIN, b, log=lambda m: None)
        self.assertEqual(open(os.path.join(a, C.NOMBRE_SALIDA), "rb").read(), open(os.path.join(b, C.NOMBRE_SALIDA), "rb").read())
    def test_sin_apariencia_ni_renombrado(self):
        d = tempfile.mkdtemp()
        r = C.convertir(WE9, BASE, CLUBES, PEIN, d, apariencia=False, renombrar_team=False, log=lambda m: None)
        self.assertEqual(r["apariencia"], {}); self.assertEqual(r["renombrados"], [])
        buf, ok, _ = C.cargar_of(open(r["salida"], "rb").read(), "pes6"); self.assertEqual(C.nombre_club(buf, "pes6", 122), "Team A")

if __name__ == "__main__":
    unittest.main(verbosity=2)

"""
Tests de Importación Tabular Estricta
=====================================
Verifica que la importación tabular admita comas decimales europeas pero rechace
valores corruptos o no numéricos mediante ValueError descriptivo sin generar ceros espurios.
"""

import unittest
from pathlib import Path
import tempfile

from core.models import Platform


class TestTabularImportStrict(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.plat = Platform(id="TEST_PLAT", name="Plataforma de Prueba")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_with_comma_decimals(self):
        # Archivo con coma decimal europea (ej: 1,25)
        content = """Sensor\tX1_m\tX2_m\tX3_m\talpha_deg\tbeta_deg\tgamma_deg
GPS1\t1,250\t-0,500\t0,750\t0,0\t0,0\t0,0
"""
        tsv_path = Path(self.temp_dir.name) / "sensors_comma.tsv"
        tsv_path.write_text(content, encoding="utf-8")

        sensors = self.plat.import_sensors_from_table(tsv_path)
        self.assertEqual(len(sensors), 1)
        s = sensors[0]
        self.assertAlmostEqual(s.lever_arm_b[0], 1.250)
        self.assertAlmostEqual(s.lever_arm_b[1], -0.500)
        self.assertAlmostEqual(s.lever_arm_b[2], 0.750)

    def test_import_rejects_corrupted_numbers(self):
        # Archivo con valor corrupto (ej: '1.2.3' o 'oops')
        content = """Sensor\tX1_m\tX2_m\tX3_m
GPS1\t1.250\tcorrupt_val\t0.750
"""
        tsv_path = Path(self.temp_dir.name) / "sensors_bad.tsv"
        tsv_path.write_text(content, encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            self.plat.import_sensors_from_table(tsv_path)

        # Debe mencionar la fila, el nombre o el campo
        err_msg = str(ctx.exception)
        self.assertTrue("campo 'x2'" in err_msg or "corrupt_val" in err_msg)


if __name__ == "__main__":
    unittest.main()

"""
PyGSN - Test Harmonization Suite (Tarea AZ)
===========================================
Valida la homogeneización y paridad matemática completa entre los tres contextos:
1. Contexto API (Scripts en Python llamando directamente al motor de Project).
2. Contexto CLI (Sesión interactiva desacoplada mediante CLIEngine).
3. Contexto GUI (Verificación de delegación correcta sin acoplamientos).
"""

import unittest
from pathlib import Path
import tempfile
import numpy as np

from core.models import Platform, Sensor, SensorType, ReferenceSystem
from core.project import Project
from core.cli_engine import CLIEngine


class TestHarmonizationAZ(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = Path(__file__).resolve().parent.parent / "data" / "calibracion_rig_multisensor.csv"
        self.assertTrue(self.csv_path.exists(), "El dataset interno CSV calibracion_rig_multisensor.csv debe existir.")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pure_api_workflow_end_to_end(self):
        """
        Verifica el ciclo de vida completo mediante la API de Python:
        Creación de proyecto -> Configuración SRT -> Chasis -> Importación CSV -> Solver -> Reporte -> Persistencia.
        """
        # 1. Crear proyecto
        proj = Project(name="Mision API Test", ellipsoid_name="GRS80")

        # 2. Configurar SRT ETRS89
        srt = ReferenceSystem(
            id="SRT_01",
            name="ETRS89 / UTM 30N",
            ellipsoid="GRS80",
            utm_zone=30,
            utm_hemisphere="N",
            geoid_undulation_N=50.0166,
            magnetic_declination_deg=-0.700,
            is_active=True
        )
        proj.add_reference_system(srt, set_active=True)

        # 3. Crear plataforma y chasis
        plat = Platform(id="PLAT_02", name="PLA2", platform_type="VEHICLE", length_m=1.25, width_m=1.0, height_m=0.5)
        plat.chassis_polygon = [
            [-0.5, -0.5], [-0.5, 0.5], [0.5, 0.5], [0.75, 0.25], [0.75, -0.25], [0.5, -0.5]
        ]
        plat.chassis_center_b = np.array([0.25, 0.0, 0.0])
        proj.add_platform(plat, set_active=True)

        # 4. Importar sensores y observables desde el CSV interno
        imported = proj.import_sensors_from_table(self.csv_path)
        self.assertEqual(len(imported), 7)
        self.assertIn("REC2", plat.sensors)
        self.assertIn("INS", plat.sensors)

        # 5. Resolver georreferenciación multipunto (SVD Kabsch + INS)
        sol = proj.solve_georeferencing(method="SVD+INS")
        self.assertIsNotNone(sol)

        # 6. Validar que la plataforma activa tiene pose_e calculada
        self.assertIsNotNone(plat.pose_e)
        pose = plat.pose_e
        self.assertEqual(pose.ref_system_id, "SRT_01")
        self.assertEqual(pose.method, "SVD+INS")

        # Actitud GNSS y PLA origin
        roll_g, pitch_g, yaw_g = sol.attitude_gnss_deg
        self.assertAlmostEqual(roll_g, 1.972285, places=4)
        self.assertAlmostEqual(pitch_g, -1.926075, places=4)
        self.assertAlmostEqual(yaw_g, 112.274661, places=4)

        # Coordenadas PLA
        lat_d = float(np.degrees(sol.pla_origin_lat_rad))
        lon_d = float(np.degrees(sol.pla_origin_lon_rad))
        self.assertAlmostEqual(lat_d, 39.481424, places=5)
        self.assertAlmostEqual(lon_d, -0.335465, places=5)
        self.assertAlmostEqual(sol.pla_origin_h_ellip, 55.8463, places=3)

        # UTM PLA
        self.assertAlmostEqual(pose.utm_easting_m, 729171.093, places=2)
        self.assertAlmostEqual(pose.utm_northing_m, 4373592.487, places=2)

        # 7. Validar propagación a sensores (CAM1 y CAM2 deben tener georef)
        self.assertIsNotNone(plat.sensors["CAM1"].georef)
        self.assertIsNotNone(plat.sensors["CAM2"].georef)
        self.assertAlmostEqual(plat.sensors["CAM1"].georef.utm_zone, 30)

        # 8. Exportar informe técnico TXT
        rep_path = Path(self.temp_dir.name) / "informe_test.txt"
        rep_text = proj.export_report(output_path=rep_path, author="Ingeniero PyGSN")
        self.assertTrue(rep_path.exists())
        self.assertIn("INFORME TÉCNICO DE GEORREFERENCIACIÓN Y TRANSFORMACIÓN MULTISENSOR", rep_text)
        self.assertIn("Cb2n", rep_text)
        self.assertIn("REC2", rep_text)

        # 9. Guardar y recargar .pygsn (Persistencia de pose_e y georef)
        pygsn_path = Path(self.temp_dir.name) / "proyecto_test.pygsn"
        proj.save(pygsn_path)
        self.assertTrue(pygsn_path.exists())

        loaded_proj = Project.load(pygsn_path)
        self.assertEqual(loaded_proj.name, "Mision API Test")
        self.assertIsNotNone(loaded_proj.platform.pose_e)
        self.assertAlmostEqual(loaded_proj.platform.pose_e.lat_deg, lat_d, places=6)
        self.assertAlmostEqual(loaded_proj.platform.pose_e.utm_easting_m, 729171.093, places=2)

    def test_pure_cli_engine_workflow_end_to_end(self):
        """
        Verifica el ciclo de vida completo mediante comandos de texto en CLIEngine:
        project new -> srt add -> chassis box/poly -> import table -> solve -> residuals -> diag -> report -> save.
        """
        output_buffer = []
        engine = CLIEngine(
            project=Project(name="Test Init"),
            stdout_callback=lambda txt: output_buffer.append(txt)
        )

        # 1. Crear proyecto limpio
        self.assertTrue(engine.execute('project new "Mision CLI Test" GRS80 30 50.0166 -0.700'))
        self.assertEqual(engine.project.name, "Mision CLI Test")

        # 2. Configurar chasis por comandos CLI
        self.assertTrue(engine.execute("chassis box 1.25 1.0 0.5"))
        self.assertTrue(engine.execute("chassis poly S (-0.5,-0.5) (-0.5,0.5) (0.5,0.5) (0.75,0.25) (0.75,-0.25) (0.5,-0.5)"))
        self.assertTrue(engine.project.platform.has_dimensions)
        self.assertEqual(len(engine.project.platform.chassis_polygon), 6)

        # 3. Importar sensores desde CSV interno
        csv_str = str(self.csv_path).replace("\\", "/")
        self.assertTrue(engine.execute(f"import table {csv_str}"))
        self.assertEqual(len(engine.project.platform.sensors), 7)

        # 4. Resolver georreferenciación
        self.assertTrue(engine.execute("solve SVD+INS"))
        self.assertIsNotNone(engine.last_solution)
        self.assertIsNotNone(engine.project.platform.pose_e)

        # Validar precisión idéntica
        pose = engine.project.platform.pose_e
        self.assertAlmostEqual(pose.utm_easting_m, 729171.093, places=2)
        self.assertAlmostEqual(pose.utm_northing_m, 4373592.487, places=2)

        # 5. Ejecutar comandos de análisis
        self.assertTrue(engine.execute("residuals"))
        self.assertTrue(engine.execute("diag"))

        # 6. Exportar informe y guardar proyecto
        rep_out = str(Path(self.temp_dir.name) / "informe_cli.txt").replace("\\", "/")
        pygsn_out = str(Path(self.temp_dir.name) / "mision_cli.pygsn").replace("\\", "/")
        self.assertTrue(engine.execute(f"report {rep_out}"))
        self.assertTrue(engine.execute(f"project save {pygsn_out}"))

        self.assertTrue(Path(rep_out).exists())
        self.assertTrue(Path(pygsn_out).exists())

        # Recargar y validar
        reloaded = Project.load(pygsn_out)
        self.assertEqual(reloaded.name, "Mision CLI Test")
        self.assertIsNotNone(reloaded.platform.pose_e)


if __name__ == "__main__":
    unittest.main()

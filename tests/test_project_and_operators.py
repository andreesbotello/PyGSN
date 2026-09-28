"""
PyGSN - Project and Operators Unit Tests
========================================
Validacion rigurosa del sistema de proyectos, mallas 3D de chasis y pipeline de operadores.
"""

import unittest
from pathlib import Path
import tempfile
import numpy as np

from core.models import Platform, Sensor, SensorType
from core.assets import VehicleMesh
from core.project import Project
from core.operators import (
    GeoreferencingOperator, TrajectoryKinematicsOperator, ReportingOperator
)


class TestProjectAndAssets(unittest.TestCase):
    def test_vehicle_mesh_projections(self):
        """Verifica la proyeccion ortogonal 2D en las 3 vistas tecnicas CAD."""
        mesh = VehicleMesh.create_box_vehicle(length_m=4.0, width_m=1.8, height_m=1.5)
        self.assertGreater(mesh.num_vertices, 10)
        self.assertGreater(mesh.num_edges, 10)

        # Proyecciones
        top_pts = mesh.project_top()
        side_pts = mesh.project_side()
        front_pts = mesh.project_front()

        self.assertEqual(top_pts.shape, (mesh.num_vertices, 2))
        self.assertEqual(side_pts.shape, (mesh.num_vertices, 2))
        self.assertEqual(front_pts.shape, (mesh.num_vertices, 2))

        # Rango en X (longitudinal) debe estar acotado a [-2, 2]
        self.assertAlmostEqual(np.max(top_pts[:, 0]), 2.0, places=3)
        self.assertAlmostEqual(np.min(top_pts[:, 0]), -2.0, places=3)

    def test_project_save_and_load(self):
        """Verifica el ciclo completo de guardado y carga de un archivo de proyecto .pygsn."""
        plat = Platform(name="Test Rover", length_m=2.0, width_m=1.0, height_m=0.8)
        plat.add_sensor(Sensor(code="REC1", name="Antena GNSS", sensor_type=SensorType.GNSS,
                               lever_arm_b=np.array([1.0, 0.2, -0.5])))
        mesh = VehicleMesh.create_box_vehicle(length_m=2.0, width_m=1.0, height_m=0.8)

        proj = Project(
            name="Proyecto Test Rover",
            description="Test de serializacion de proyecto",
            platform=plat,
            asset=mesh
        )

        with tempfile.NamedTemporaryFile(suffix=".pygsn", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            proj.save(tmp_path)
            self.assertTrue(tmp_path.exists())

            loaded_proj = Project.load(tmp_path)
            self.assertEqual(loaded_proj.name, "Proyecto Test Rover")
            self.assertEqual(loaded_proj.platform.name, "Test Rover")
            self.assertIn("REC1", loaded_proj.platform.sensors)
            np.testing.assert_allclose(
                loaded_proj.platform.sensors["REC1"].lever_arm_b,
                np.array([1.0, 0.2, -0.5])
            )
            self.assertEqual(loaded_proj.asset.num_vertices, mesh.num_vertices)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


class TestOperatorPipeline(unittest.TestCase):
    def setUp(self):
        # Cargar proyecto de prueba estandar
        proj_path = Path(r"c:\Users\bryan\Desktop\UPV\S3\2_Sensores\PyGSN\data\proyecto_vehiculo_multisensor.pygsn")
        if proj_path.exists():
            self.project = Project.load(proj_path)
        else:
            self.project = Project(name="Default Project")

        self.obs_path = Path(r"c:\Users\bryan\Desktop\UPV\S3\2_Sensores\PyGSN\data\observaciones_sensores.txt")

    def test_georeferencing_operator(self):
        """Verifica la ejecucion del operador de georreferenciacion sobre el proyecto."""
        if not self.obs_path.exists():
            self.skipTest("Archivo de observaciones no encontrado")

        op = GeoreferencingOperator()
        res = op.execute(self.project, observations=self.obs_path)

        self.assertTrue(res.success)
        self.assertIn("C_b_n", res.data)
        self.assertIn("r_pla_e", res.data)
        self.assertIn("attitude_gnss_deg", res.data)

        # Verificar ortonormalidad de C_b^n
        Cb2n = res.data["C_b_n"]
        np.testing.assert_allclose(Cb2n.T @ Cb2n, np.eye(3), atol=1e-10)

    def test_trajectory_kinematics_operator(self):
        """Verifica la integracion cinematica desde comandos b-frame hasta e-frame."""
        op = TrajectoryKinematicsOperator()
        res = op.execute(self.project)

        self.assertTrue(res.success)
        self.assertIn("pos_ned", res.data)
        self.assertIn("pos_geodetic", res.data)
        self.assertIn("pos_ecef", res.data)

        times = res.data["time"]
        pos_ned = res.data["pos_ned"]
        pos_ecef = res.data["pos_ecef"]

        self.assertEqual(len(times), len(pos_ned))
        self.assertEqual(len(times), len(pos_ecef))
        self.assertGreater(len(times), 5)

        # Distancia recorrida mayor a 0
        total_dist = np.linalg.norm(pos_ned[-1] - pos_ned[0])
        self.assertGreater(total_dist, 10.0)

    def test_reporting_operator(self):
        """Verifica que el ReportingOperator genere el informe tecnico correctamente."""
        if not self.obs_path.exists():
            self.skipTest("Archivo de observaciones no encontrado")

        geo_op = GeoreferencingOperator()
        geo_res = geo_op.execute(self.project, observations=self.obs_path)
        self.assertTrue(geo_res.success)

        rep_op = ReportingOperator()
        rep_res = rep_op.execute(
            self.project,
            georeferencing_result=geo_res.data["georeferencing_result"]
        )

        self.assertTrue(rep_res.success)
        self.assertIn("report_text", rep_res.data)
        report = rep_res.data["report_text"]
        self.assertIn("INFORME", report)
        self.assertIn("SECCIÓN 1", report)


if __name__ == "__main__":
    unittest.main()

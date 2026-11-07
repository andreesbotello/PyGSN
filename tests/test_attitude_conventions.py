"""
PyGSN - Attitude and Frame Convention Regression Tests
======================================================
- Cb2n en el integrador de trayectorias (rumbo NED correcto).
- Coherencia de la trayectoria NED con la trayectoria ECEF.
- Matriz Cb2e persistida en PlatformPose (ambos métodos) y reproducción de sensores.
- Convención IGRF/WMM de la declinación magnética y migración de proyectos antiguos.
- Extracción de pitch cerca de +-90 deg.
"""

import math
import unittest
from pathlib import Path

import numpy as np

from core.rotations import (
    attitude_to_dcm, dcm_to_attitude, magnetic_to_geodetic_north_matrix, chain_ins_attitude_matrix,
    e_to_n_matrix
)
from core.operators.kinematics_operator import TrajectoryKinematicsOperator
from core.georeferencing import solve_multisensor_georeferencing, create_reference_platform
from core.models import ReferenceSystem, Platform, DECLINATION_CONVENTION
from core.project import Project

DATA = Path(__file__).resolve().parents[1] / "data"


class TestTrajectoryAttitudeConvention(unittest.TestCase):
    def _run(self, yaw_deg, n=10, dt=1.0, v=5.0):
        op = TrajectoryKinematicsOperator()
        cmds = [{"dt": dt, "vel_b": [v, 0.0, 0.0], "attitude_deg": [0.0, 0.0, yaw_deg]}] * n
        res = op.execute(None, initial_geodetic=(math.radians(40.0), math.radians(-3.0), 100.0), commands=cmds)
        self.assertTrue(res.success)
        return res

    def test_heading_east(self):
        ned = self._run(90.0).data["pos_ned"][-1]
        self.assertGreater(ned[1], 49.9)            # +Este
        self.assertLess(abs(ned[0]), 1e-3)          # sin componente Norte

    def test_heading_northeast(self):
        ned = self._run(45.0).data["pos_ned"][-1]
        self.assertGreater(ned[0], 0.0)
        self.assertAlmostEqual(ned[0], ned[1], delta=1e-3)

    def test_ned_consistent_with_ecef(self):
        res = self._run(30.0, n=50)
        ecef = res.data["pos_ecef"]
        lat0, lon0, _ = res.data["pos_geodetic"][0]
        ned_from_ecef = (ecef - ecef[0]) @ e_to_n_matrix(lat0, lon0).T
        np.testing.assert_allclose(res.data["pos_ned"], ned_from_ecef, atol=1e-9)


class TestPersistedBodyToEarthMatrix(unittest.TestCase):
    def setUp(self):
        self.plat = create_reference_platform()
        self.plat.import_sensors_from_table(DATA / "calibracion_rig_multisensor.csv")
        self.srt = ReferenceSystem(id="SRT_T", name="T", geoid_undulation_N=50.0166,
                                   magnetic_declination_deg=0.7, utm_zone=30)
        self.sol = solve_multisensor_georeferencing(self.plat, reference_system=self.srt)

    def test_dcm_b2e_both_methods(self):
        for method, Cb2n in (("SVD+INS", self.sol.Cb2n_gnss), ("INS", self.sol.Cb2n_ins)):
            self.plat.apply_georeferencing_solution(self.sol, self.srt, method_str=method)
            C = np.array(self.plat.pose_e.dcm_b2e)
            np.testing.assert_allclose(C @ C.T, np.eye(3), atol=1e-12)
            self.assertAlmostEqual(np.linalg.det(C), 1.0, places=12)
            Cn2e = e_to_n_matrix(self.sol.pla_origin_lat_rad, self.sol.pla_origin_lon_rad).T
            np.testing.assert_allclose(C, Cn2e @ Cb2n, atol=1e-12)
            # La matriz persistida reproduce las coordenadas propagadas de cada sensor
            for code, s in self.plat.sensors.items():
                if s.georef is None:
                    continue
                r = self.plat.pose_e.ecef + C @ s.lever_arm_b
                np.testing.assert_allclose(r, s.georef.ecef, atol=1e-9)


class TestDeclinationConvention(unittest.TestCase):
    def test_true_heading_is_magnetic_plus_D(self):
        D = 2.5
        C = magnetic_to_geodetic_north_matrix(math.radians(D)) @ attitude_to_dcm(0.0, 0.0, math.radians(100.0))
        _, _, yaw = dcm_to_attitude(C)
        self.assertAlmostEqual(math.degrees(yaw), 102.5, places=10)

    def test_chain_ins_uses_igrf(self):
        C = chain_ins_attitude_matrix(0.0, 0.0, math.radians(10.0), declination_rad=math.radians(-1.0))
        self.assertAlmostEqual(math.degrees(dcm_to_attitude(C)[2]), 9.0, places=10)

    def test_reference_system_roundtrip_and_legacy_migration(self):
        rs = ReferenceSystem(id="A", magnetic_declination_deg=0.7)
        d = rs.to_dict()
        self.assertEqual(d["magnetic_declination_convention"], DECLINATION_CONVENTION)
        self.assertAlmostEqual(ReferenceSystem.from_dict(d).magnetic_declination_deg, 0.7)
        legacy = dict(d)
        legacy.pop("magnetic_declination_convention")
        legacy["magnetic_declination_deg"] = -0.7      # delta antiguo (Cmn2gn = R3(delta))
        with self.assertLogs("core.models", level="WARNING"):
            self.assertAlmostEqual(ReferenceSystem.from_dict(legacy).magnetic_declination_deg, 0.7)
        bad = dict(d, magnetic_declination_convention="DESCONOCIDA")
        with self.assertRaises(ValueError):
            ReferenceSystem.from_dict(bad)

    def test_project_config_legacy_migration(self):
        proj = Project(name="P")
        proj.config["mag_declination_deg"] = 1.0
        data = proj.to_dict()
        self.assertAlmostEqual(Project.from_dict(data).config["mag_declination_deg"], 1.0)
        data["config"].pop("declination_convention")
        with self.assertLogs("core.models", level="WARNING"):
            self.assertAlmostEqual(Project.from_dict(data).config["mag_declination_deg"], -1.0)


class TestEulerExtractionNearVertical(unittest.TestCase):
    def test_pitch_near_90(self):
        for k in range(1, 9):
            p = 90.0 - 10.0 ** (-k)
            C = attitude_to_dcm(math.radians(1.0), math.radians(p), math.radians(30.0))
            self.assertAlmostEqual(math.degrees(dcm_to_attitude(C)[1]), p, places=11)


if __name__ == "__main__":
    unittest.main()

"""
PyGSN - Body Frame Reorientation Tests
======================================
El chasis materializa el b-frame (FRD, orientación 0,0,0). Solo se admiten reorientaciones de
k * 90 deg, que transforman de forma rígida y exacta chasis, lever-arms, boresights y pose.
"""

import copy
import unittest
from pathlib import Path

import numpy as np

from core.models import Platform, Sensor, SensorType, ReferenceSystem
from core.rotations import sensor_to_body_matrix, attitude_to_dcm
from core.validation import ValidationError
from core.georeferencing import solve_multisensor_georeferencing, create_reference_platform

DATA = Path(__file__).resolve().parents[1] / "data"


def _make_platform() -> Platform:
    p = Platform(name="rig", length_m=4.5, width_m=1.8, height_m=1.5)
    p.has_dimensions = True
    p.chassis_center_b = [0.3, -0.1, -0.6]
    p.ensure_polygon()
    p.add_sensor(Sensor(code="CAM", name="cam", sensor_type=SensorType.CAMERA,
                        lever_arm_b=np.array([1.2, -0.3, -1.1]), boresight_deg=(0.2, 0.5, -1.3)))
    p.add_sensor(Sensor(code="GNSS", name="ant", sensor_type=SensorType.GNSS,
                        lever_arm_b=np.array([-0.4, 0.4, -1.5])))
    return p


def _state(p: Platform):
    return (np.array(p.chassis_polygon, dtype=float), np.array(p.chassis_center_b, dtype=float),
            (p.length_m, p.width_m, p.height_m),
            {c: (s.lever_arm_b.copy(), sensor_to_body_matrix(*np.radians(s.boresight_deg))) for c, s in p.sensors.items()})


class TestBodyFrameReorientation(unittest.TestCase):
    def assertSameState(self, a, b, atol=1e-12):
        np.testing.assert_allclose(a[0], b[0], atol=atol)
        np.testing.assert_allclose(a[1], b[1], atol=atol)
        np.testing.assert_allclose(a[2], b[2], atol=atol)
        for code in a[3]:
            np.testing.assert_allclose(a[3][code][0], b[3][code][0], atol=atol)
            np.testing.assert_allclose(a[3][code][1], b[3][code][1], atol=atol)

    def test_rejects_non_quarter_turns(self):
        p = _make_platform()
        for ang in (30.0, 45.0, 89.9, float("nan")):
            with self.subTest(ang=ang):
                with self.assertRaises(ValidationError):
                    p.rotate_plane(ang, "S")

    def test_inverse_restores_exactly(self):
        for plane in ("S", "F", "L"):
            for ang in (90.0, 180.0, 270.0, -90.0):
                with self.subTest(plane=plane, ang=ang):
                    # Planta rectangular: también invertible en giros de 90 deg sobre Xb/Yb
                    # (con planta no rectangular la huella pasa a su rectángulo envolvente).
                    p = _make_platform()
                    ref = _state(p)
                    p.rotate_plane(ang, plane)
                    p.rotate_plane(-ang, plane)
                    self.assertSameState(_state(p), ref)

    def test_four_quarter_turns_identity(self):
        for plane in ("S", "F", "L"):
            p = _make_platform()
            ref = _state(p)
            for _ in range(4):
                p.rotate_plane(90.0, plane)
            self.assertSameState(_state(p), ref)

    def test_frontal_quarter_turn_swaps_width_height(self):
        p = _make_platform()
        p.rotate_plane(90.0, "F")
        self.assertAlmostEqual(p.length_m, 4.5, places=12)
        self.assertAlmostEqual(p.width_m, 1.5, places=12)
        self.assertAlmostEqual(p.height_m, 1.8, places=12)

    def test_rigid_transform_of_sensors(self):
        p = _make_platform()
        A = p.rotate_plane(90.0, "S")
        np.testing.assert_allclose(p.sensors["CAM"].lever_arm_b, A @ np.array([1.2, -0.3, -1.1]), atol=1e-15)
        Cs2b_new = sensor_to_body_matrix(*np.radians(p.sensors["CAM"].boresight_deg))
        np.testing.assert_allclose(Cs2b_new, A @ sensor_to_body_matrix(*np.radians((0.2, 0.5, -1.3))), atol=1e-12)
        # Las distancias entre sensores (geometría rígida) se conservan
        d = np.linalg.norm(p.sensors["CAM"].lever_arm_b - p.sensors["GNSS"].lever_arm_b)
        self.assertAlmostEqual(d, np.linalg.norm(np.array([1.6, -0.7, 0.4])), places=12)

    def test_georeferenced_pose_is_preserved_physically(self):
        plat = create_reference_platform()
        plat.import_sensors_from_table(DATA / "calibracion_rig_multisensor.csv")
        srt = ReferenceSystem(id="S1", name="S1", geoid_undulation_N=50.0, magnetic_declination_deg=0.7)
        sol = solve_multisensor_georeferencing(plat, reference_system=srt)
        plat.apply_georeferencing_solution(sol, srt, method_str="SVD+INS")
        before = {c: plat.pose_e.ecef + np.array(plat.pose_e.dcm_b2e) @ s.lever_arm_b for c, s in plat.sensors.items()}
        A = plat.rotate_plane(90.0, "S")
        for c, s in plat.sensors.items():
            after = plat.pose_e.ecef + np.array(plat.pose_e.dcm_b2e) @ s.lever_arm_b
            np.testing.assert_allclose(after, before[c], atol=1e-9)
        # Actitud del nuevo b-frame: Cb2n' = Cb2n A^T
        Cb2n_new = attitude_to_dcm(*np.radians(plat.pose_e.attitude_rpy_deg))
        np.testing.assert_allclose(Cb2n_new, sol.Cb2n_gnss @ A.T, atol=1e-12)


if __name__ == "__main__":
    unittest.main()

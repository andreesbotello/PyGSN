"""
PyGSN Unit Tests - Practica 1 Validation
=======================================
Pruebas unitarias para validar las transformaciones y la resolucion completa
de la Practica 1 frente a las soluciones oficiales del curso.
"""

import unittest
import numpy as np

from core.geodesy import GRS80, geodetic_to_ecef, ecef_to_geodetic, dms_to_rad, rad_to_dms
from core.rotations import (
    R1, R2, R3, attitude_to_dcm, dcm_to_attitude, sensor_to_body_matrix,
    magnetic_to_geodetic_north_matrix, e_to_n_matrix
)
from core.alignment import kabsch_orthogonal_procrustes
from core.solver_p1 import create_default_p1_platform, solve_practica_1


class TestPractica1(unittest.TestCase):

    def setUp(self):
        self.platform = create_default_p1_platform()
        self.gnss_obs = {
            "REC2": (dms_to_rad(39, 28, 53.133637, 1), dms_to_rad(0, 20, 7.650964, -1), np.float64(55.8670)),
            "REC3": (dms_to_rad(39, 28, 53.109885, 1), dms_to_rad(0, 20, 7.663129, -1), np.float64(55.8290)),
            "REC4": (dms_to_rad(39, 28, 53.143535, 1), dms_to_rad(0, 20, 7.680928, -1), np.float64(55.8830)),
            "REC5": (dms_to_rad(39, 28, 53.119474, 1), dms_to_rad(0, 20, 7.693816, -1), np.float64(55.8660)),
        }
        self.ins_attitude = (1.195278, -1.189671, 111.269874)

    def test_geodesy_conversions(self):
        """Validar conversion ida y vuelta Geodesicas <-> ECEF a nivel sub-milimetrico."""
        lat = dms_to_rad(39, 28, 53.133637, 1)
        lon = dms_to_rad(0, 20, 7.650964, -1)
        h = np.float64(55.8670)

        xyz = geodetic_to_ecef(lat, lon, h, GRS80)
        lat_back, lon_back, h_back = ecef_to_geodetic(xyz, GRS80)

        self.assertAlmostEqual(lat, lat_back, places=11)
        self.assertAlmostEqual(lon, lon_back, places=11)
        self.assertAlmostEqual(h, h_back, places=4)

    def test_rotations_consistency(self):
        """Validar consistencia de Cb2n y extraccion de actitud."""
        r_in = np.radians(1.9722853163)
        p_in = np.radians(-1.9260752052)
        y_in = np.radians(112.2746608597)

        Cb2n = attitude_to_dcm(r_in, p_in, y_in)
        r_out, p_out, y_out = dcm_to_attitude(Cb2n)

        self.assertAlmostEqual(float(r_in), float(r_out), places=9)
        self.assertAlmostEqual(float(p_in), float(p_out), places=9)
        self.assertAlmostEqual(float(y_in), float(y_out), places=9)

    def test_p1_complete_solution(self):
        """Validar resultados de la Practica 1 frente a valores de referencia 2025."""
        sol = solve_practica_1(
            platform=self.platform,
            gnss_observations=self.gnss_obs,
            ins_attitude_deg=self.ins_attitude,
            magnetic_declination_deg=-0.700,
            geoid_undulation_N=50.0166
        )

        # 1. Actitud GNSS estimada
        roll_g, pitch_g, yaw_g = sol.attitude_gnss_deg
        self.assertAlmostEqual(roll_g, 1.9722853, places=5)
        self.assertAlmostEqual(pitch_g, -1.9260752, places=5)
        self.assertAlmostEqual(yaw_g, 112.2746609, places=5)

        # 2. Origen PLA en ECEF
        # 2025: X=4929476.0865, Y=-28862.2158, Z=4033747.4246
        self.assertAlmostEqual(sol.pla_origin_ecef[0], 4929476.0865, delta=0.001)
        self.assertAlmostEqual(sol.pla_origin_ecef[1], -28862.2158, delta=0.001)
        self.assertAlmostEqual(sol.pla_origin_ecef[2], 4033747.4246, delta=0.001)

        # 3. Actitud total con INS
        # 2025: Roll=1.3758265 deg, Pitch=-1.6984938 deg, Yaw=114.8282640 deg
        r_ins_tot, p_ins_tot, y_ins_tot = sol.attitude_ins_total_deg
        self.assertAlmostEqual(r_ins_tot, 1.3758265, places=5)
        self.assertAlmostEqual(p_ins_tot, -1.6984938, places=5)
        self.assertAlmostEqual(y_ins_tot, 114.8282640, places=5)

        # 4. Residuales 2a vs 2b (REC2 dE ~ -0.0098, dN ~ +0.0229)
        dE_rec2, dN_rec2, dH_rec2 = sol.diff_2a_2b_utm["REC2"]
        self.assertAlmostEqual(dE_rec2, -0.0098, delta=0.0005)
        self.assertAlmostEqual(dN_rec2, 0.0229, delta=0.0005)


if __name__ == "__main__":
    unittest.main()

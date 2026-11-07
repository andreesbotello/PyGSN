"""
PyGSN - Attitude Uncertainty and Projection Guard Tests
=======================================================
- Covarianza analítica de la actitud Kabsch frente a Monte Carlo.
- Regresión de sigma0, sigmas y consistencia GNSS-INS con el dataset interno.
- Sección de incertidumbre en el informe técnico.
- Aviso UTM fuera de huso y continuidad en el antimeridiano.
"""

import math
import unittest
from pathlib import Path

import numpy as np

from core.rotations import attitude_to_dcm, dcm_to_attitude
from core.alignment import kabsch_orthogonal_procrustes
from core.georeferencing import (
    compute_attitude_uncertainty, solve_multisensor_georeferencing, create_reference_platform
)
from core.models import ReferenceSystem
from core.reporting import generate_georeferencing_report
from core import geodesy
from core.geodesy import utm_projection, GRS80

DATA = Path(__file__).resolve().parents[1] / "data"


class TestAttitudeCovariance(unittest.TestCase):
    def test_analytic_matches_monte_carlo(self):
        rng = np.random.default_rng(12345)
        B = np.array([[0.4, -0.4, -0.015], [0.4, 0.4, -0.015], [-0.4, -0.4, -0.015], [-0.4, 0.4, -0.015]]).T
        C = attitude_to_dcm(math.radians(1.0), math.radians(-2.0), math.radians(37.0))
        sigma = 0.005
        codes = ["A", "B", "C", "D"]
        arms = {c: B[:, i] for i, c in enumerate(codes)}
        rpy_mc, s0_list, s_rpy = [], [], []
        for _ in range(2000):
            obs = C @ B + rng.normal(0.0, sigma, B.shape)
            R, *_ = kabsch_orthogonal_procrustes(B, obs)
            vec = {c: obs[:, i] for i, c in enumerate(codes)}
            unc = compute_attitude_uncertainty(arms, vec, codes, R)
            s0_list.append(unc.sigma0_m)
            s_rpy.append(unc.sigma_rpy_deg)
            rpy_mc.append(np.degrees(dcm_to_attitude(R)))
        rpy_mc = np.array(rpy_mc)
        mc_std = np.std(rpy_mc, axis=0)
        # Sigma analítica evaluada con el sigma verdadero (escala la media de sigma0^2)
        scale = sigma / math.sqrt(np.mean(np.square(s0_list)))
        analytic = np.sqrt(np.mean(np.square(np.array(s_rpy)), axis=0)) * scale
        np.testing.assert_allclose(analytic, mc_std, rtol=0.10)
        # sigma0 insesgado: E[sigma0^2] = sigma^2
        self.assertAlmostEqual(math.sqrt(np.mean(np.square(s0_list))), sigma, delta=0.05 * sigma)


class TestDatasetUncertaintyRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plat = create_reference_platform()
        plat.import_sensors_from_table(DATA / "calibracion_rig_multisensor.csv")
        cls.srt = ReferenceSystem(id="S1", name="S1", geoid_undulation_N=50.0166, magnetic_declination_deg=0.7)
        cls.sol = solve_multisensor_georeferencing(plat, reference_system=cls.srt)

    def test_values(self):
        unc = self.sol.attitude_uncertainty
        self.assertIsNotNone(unc)
        self.assertEqual(unc.dof, 6)
        self.assertAlmostEqual(unc.sigma0_m * 1e3, 8.84, delta=0.01)
        self.assertAlmostEqual(unc.sigma_rpy_deg[2], 0.448, delta=0.002)
        self.assertAlmostEqual(unc.gnss_ins_diff_deg[2], -2.5536, delta=1e-3)
        self.assertGreater(unc.gnss_ins_ratio[2], 5.5)
        self.assertEqual(unc.gnss_ins_significant, (False, False, True))
        # Sensores: CAM1 (brazo ~0.7 m) con incertidumbre mayor que el centroide
        self.assertGreater(max(unc.sensor_sigma_ned_m["CAM1"]), max(unc.sensor_sigma_ned_m["CENT"]))

    def test_report_section(self):
        txt = generate_georeferencing_report(self.sol, author="t", project="t", doc_id="t")
        self.assertIn("SECCIÓN 6", txt)
        self.assertIn("sigma0 = 8.84 mm", txt)


class TestUtmGuards(unittest.TestCase):
    def test_out_of_zone_warning(self):
        geodesy._zones_warned.discard(31)
        with self.assertLogs("core.geodesy", level="WARNING"):
            utm_projection(math.radians(40.0), math.radians(3.0 + 4.5), zone=31, hemisphere="N", ell=GRS80)

    def test_antimeridian_continuity(self):
        # Huso 60 (MC +177 deg): lon = -179.5 deg está a dlon = +3.5 deg (no a -356.5 deg).
        # Por simetría respecto al MC debe reflejar exactamente el punto a dlon = -3.5 deg.
        e_a, n_a, _ = utm_projection(math.radians(10.0), math.radians(-179.5), zone=60, hemisphere="N", ell=GRS80)
        e_b, n_b, _ = utm_projection(math.radians(10.0), math.radians(173.5), zone=60, hemisphere="N", ell=GRS80)
        self.assertAlmostEqual(e_a - 500000.0, 500000.0 - e_b, places=6)
        self.assertAlmostEqual(n_a, n_b, places=6)
        self.assertGreater(e_a, 500000.0)


if __name__ == "__main__":
    unittest.main()

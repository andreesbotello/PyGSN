"""
PyGSN - Math Battery Unit Tests
===============================
Banco de pruebas unitarias exhaustivo para la Batería Matemática Pura de PyGSN:
- Validaciones y protecciones angulares universales (normalize_angle, safe_division, Gimbal Lock)
- Álgebra de rotaciones (R1, R2, R3, Ce2n, attitude_to_dcm, chain_ins_attitude_matrix, audit_dcm_condition)
- Geodesia computacional (radii_of_curvature, Geodetic <-> ECEF, UTM directa/inversa, parse_coordinate_string)
- Cinemática pura (propagate_lever_arm_ecef, geodetic_navigation_rates, transformaciones 2D/3D)
- Pipeline matemático puro de georreferenciación (10 etapas atómicas y paridad con fachada)
"""

import math
import unittest
import numpy as np

from core.validation import (
    ValidationError, CollinearGeometryError, validate_finite,
    normalize_angle_pi, normalize_angle_2pi, normalize_angle_deg_180, normalize_angle_deg_360,
    validate_attitude_angles, validate_safe_division, validate_antenna_geometry
)
from core.rotations import (
    R1, R2, R3, e_to_n_matrix, n_to_e_matrix,
    attitude_to_dcm, dcm_to_attitude, dcm_to_euler,
    chain_ins_attitude_matrix, audit_dcm_condition, reorthonormalize_dcm
)
from core.geodesy import (
    GRS80, WGS84, radii_of_curvature, geodetic_to_ecef, ecef_to_geodetic,
    utm_projection, utm_inverse, utm_meridian_convergence, grid_bearing,
    parse_coordinate_string, ellipsoidal_to_orthometric, orthometric_to_ellipsoidal
)
from core.kinematics import (
    propagate_lever_arm_ecef, solve_origin_from_centroid_ecef,
    geodetic_navigation_rates, rotate_polygon_2d, scale_polygon_2d,
    compute_polygon_2d_bounds, compute_utm_bounding_box_points
)
from core.georeferencing import (
    solve_georeferencing_pipeline, solve_multisensor_georeferencing,
    gnss_observations_to_ecef, compute_navigation_centroid, project_ecef_to_nframe,
    solve_attitude_kabsch, solve_pla_origin_ecef, solve_attitude_ins_chain,
    create_reference_platform
)


class TestMathBatteryValidation(unittest.TestCase):
    """Pruebas de la capa de protección y validación universal."""

    def test_normalize_angle_pi(self):
        # Ángulos dentro de rango
        self.assertAlmostEqual(float(normalize_angle_pi(0.5)), 0.5, places=12)
        self.assertAlmostEqual(float(normalize_angle_pi(-0.5)), -0.5, places=12)
        # Giros mayores a 2*pi (> 360 deg)
        two_pi = 2.0 * np.pi
        self.assertAlmostEqual(float(normalize_angle_pi(two_pi + 0.3)), 0.3, places=12)
        self.assertAlmostEqual(float(normalize_angle_pi(-two_pi - 0.3)), -0.3, places=12)
        self.assertAlmostEqual(float(normalize_angle_pi(4.0 * two_pi + 1.2)), 1.2, places=12)
        # Fronteras exactas pi
        self.assertAlmostEqual(abs(float(normalize_angle_pi(np.pi))), np.pi, places=10)

    def test_normalize_angle_2pi(self):
        two_pi = 2.0 * np.pi
        self.assertAlmostEqual(float(normalize_angle_2pi(0.0)), 0.0, places=12)
        self.assertAlmostEqual(float(normalize_angle_2pi(two_pi)), 0.0, places=12)
        self.assertAlmostEqual(float(normalize_angle_2pi(-0.5)), two_pi - 0.5, places=12)
        self.assertAlmostEqual(float(normalize_angle_2pi(3.0 * two_pi + 1.5)), 1.5, places=12)

    def test_normalize_angle_deg(self):
        self.assertAlmostEqual(normalize_angle_deg_180(190.0), -170.0, places=10)
        self.assertAlmostEqual(normalize_angle_deg_180(-200.0), 160.0, places=10)
        self.assertAlmostEqual(normalize_angle_deg_360(-30.0), 330.0, places=10)
        self.assertAlmostEqual(normalize_angle_deg_360(730.0), 10.0, places=10)

    def test_validate_safe_division(self):
        self.assertAlmostEqual(float(validate_safe_division(10.0, 2.0)), 5.0, places=12)
        self.assertAlmostEqual(float(validate_safe_division(10.0, 0.0, default=-999.0)), -999.0, places=12)
        self.assertAlmostEqual(float(validate_safe_division(10.0, 1e-18, eps=1e-15, default=0.0)), 0.0, places=12)

    def test_validate_attitude_angles(self):
        # Caso nominal
        r, p, y = validate_attitude_angles(np.radians(10.0), np.radians(20.0), np.radians(350.0))
        self.assertAlmostEqual(float(np.degrees(r)), 10.0, places=10)
        self.assertAlmostEqual(float(np.degrees(p)), 20.0, places=10)
        self.assertAlmostEqual(float(np.degrees(y)), 350.0, places=10)

        # Cabeceo fuera de rango físico [-90, 90] deg en modo estricto
        with self.assertRaises(ValidationError):
            validate_attitude_angles(0.0, np.radians(95.0), 0.0, strict_pitch=True)

        with self.assertRaises(ValidationError):
            validate_attitude_angles(0.0, np.radians(-91.0), 0.0, strict_pitch=True)

        # Cabeceo fuera de rango en modo no estricto aplica clamping a +/- pi/2
        _, p_clamp, _ = validate_attitude_angles(0.0, np.radians(110.0), 0.0, strict_pitch=False)
        self.assertAlmostEqual(float(p_clamp), np.pi / 2.0, places=12)


class TestMathBatteryRotations(unittest.TestCase):
    """Pruebas del módulo de rotaciones y metrología de actitud."""

    def test_elementary_rotations(self):
        ang = np.radians(30.0)
        for R_func in (R1, R2, R3):
            mat = R_func(ang)
            det, ortho_err = audit_dcm_condition(mat)
            self.assertAlmostEqual(det, 1.0, places=12)
            self.assertAlmostEqual(ortho_err, 0.0, places=14)

    def test_ecef_to_ned_matrix_inverse(self):
        lat = np.radians(39.4820)
        lon = np.radians(-0.3475)
        Ce2n = e_to_n_matrix(lat, lon)
        Cn2e = n_to_e_matrix(lat, lon)
        identity = Ce2n @ Cn2e
        np.testing.assert_allclose(identity, np.eye(3), atol=1e-15)

    def test_attitude_dcm_roundtrip(self):
        r_in = np.radians(5.123456)
        p_in = np.radians(-3.654321)
        y_in = np.radians(124.789123)

        Cb2n = attitude_to_dcm(r_in, p_in, y_in)
        det, ortho_err = audit_dcm_condition(Cb2n)
        self.assertAlmostEqual(det, 1.0, places=12)
        self.assertAlmostEqual(ortho_err, 0.0, places=14)

        r_out, p_out, y_out = dcm_to_attitude(Cb2n)
        self.assertAlmostEqual(r_out, r_in, places=10)
        self.assertAlmostEqual(p_out, p_in, places=10)
        self.assertAlmostEqual(y_out, y_in, places=10)

    def test_chain_ins_attitude_matrix(self):
        Cb2n = chain_ins_attitude_matrix(
            roll_rad=np.radians(1.0),
            pitch_rad=np.radians(2.0),
            yaw_rad=np.radians(45.0),
            declination_rad=np.radians(-0.700),
            alpha_rad=np.radians(0.1),
            beta_rad=np.radians(-0.2),
            gamma_rad=np.radians(0.5)
        )
        det, ortho_err = audit_dcm_condition(Cb2n)
        self.assertAlmostEqual(det, 1.0, places=12)
        self.assertAlmostEqual(ortho_err, 0.0, places=14)


class TestMathBatteryGeodesy(unittest.TestCase):
    """Pruebas del módulo de geodesia computacional y proyecciones."""

    def test_geodetic_to_ecef_roundtrip(self):
        lat_in = np.radians(39.481426)
        lon_in = np.radians(-0.335458)
        h_in = np.float64(52.345)

        xyz = geodetic_to_ecef(lat_in, lon_in, h_in, GRS80)
        lat_out, lon_out, h_out = ecef_to_geodetic(xyz, GRS80)

        self.assertAlmostEqual(lat_out, lat_in, places=12)
        self.assertAlmostEqual(lon_out, lon_in, places=12)
        self.assertAlmostEqual(h_out, h_in, places=8)

    def test_utm_projection_roundtrip(self):
        lat_in = np.radians(39.481426)
        lon_in = np.radians(-0.335458)

        easting, northing, zone = utm_projection(lat_in, lon_in, zone=30, hemisphere="N", ell=GRS80)
        self.assertEqual(zone, 30)

        lat_out, lon_out = utm_inverse(easting, northing, zone=30, hemisphere="N", ell=GRS80)
        self.assertAlmostEqual(lat_out, lat_in, places=10)
        self.assertAlmostEqual(lon_out, lon_in, places=10)

    def test_parse_coordinate_string(self):
        # Sexagesimal con símbolos
        deg1 = parse_coordinate_string("39º28'53.133637\"")
        self.assertAlmostEqual(deg1, 39.48142601, places=6)

        # Sexagesimal negativo Oeste
        deg2 = parse_coordinate_string("-0º20'7.650964\"")
        self.assertAlmostEqual(deg2, -0.33545860, places=6)

        # Decimal con coma
        deg3 = parse_coordinate_string("39,481426")
        self.assertAlmostEqual(deg3, 39.481426, places=6)

    def test_orthometric_conversions(self):
        h = 100.0
        N = 50.0
        H = ellipsoidal_to_orthometric(h, N)
        self.assertAlmostEqual(H, 50.0, places=10)
        h_back = orthometric_to_ellipsoidal(H, N)
        self.assertAlmostEqual(h_back, h, places=10)

    def test_grid_bearing(self):
        yaw = np.radians(110.0)
        gamma = np.radians(1.5)
        grid_b = grid_bearing(yaw, gamma)
        self.assertAlmostEqual(grid_b, np.radians(108.5), places=10)


class TestMathBatteryKinematics(unittest.TestCase):
    """Pruebas del módulo de cinemática pura y transformaciones geométricas."""

    def test_propagate_lever_arm_ecef(self):
        r_orig = np.array([4918500.0, -28800.0, 4035600.0], dtype=np.float64)
        Cb2e = np.eye(3, dtype=np.float64)
        arm = np.array([1.0, 2.0, 3.0], dtype=np.float64)

        r_sens = propagate_lever_arm_ecef(r_orig, Cb2e, arm)
        np.testing.assert_allclose(r_sens, r_orig + arm, atol=1e-12)

    def test_geodetic_navigation_rates(self):
        lat = np.radians(39.4820)
        h = 50.0
        # 10 m/s hacia el Norte
        v_n = np.array([10.0, 0.0, 0.0], dtype=np.float64)
        dlat, dlon, dh = geodetic_navigation_rates(v_n, lat, h, GRS80)

        Rm, _ = radii_of_curvature(lat, GRS80)
        expected_dlat = 10.0 / (Rm + h)
        self.assertAlmostEqual(dlat, expected_dlat, places=12)
        self.assertAlmostEqual(dlon, 0.0, places=12)
        self.assertAlmostEqual(dh, 0.0, places=12)

    def test_rotate_scale_polygon_2d(self):
        poly = [[1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0]]
        # Rotar 90 grados alrededor del origen [0, 0]
        rotated = rotate_polygon_2d(poly, 90.0, center_2d=[0.0, 0.0])
        # [1, -1] rotado 90 deg -> [1, 1]
        self.assertAlmostEqual(rotated[0][0], 1.0, places=3)
        self.assertAlmostEqual(rotated[0][1], 1.0, places=3)

        # Escalado x2
        scaled = scale_polygon_2d(poly, 2.0, 2.0, center_2d=[0.0, 0.0])
        self.assertAlmostEqual(scaled[0][0], 2.0, places=3)
        self.assertAlmostEqual(scaled[0][1], -2.0, places=3)

        bounds = compute_polygon_2d_bounds(scaled)
        self.assertAlmostEqual(bounds["length_m"], 4.0, places=3)
        self.assertAlmostEqual(bounds["width_m"], 4.0, places=3)


class TestMathBatteryGeoreferencingPipeline(unittest.TestCase):
    """Pruebas del pipeline atómico de georreferenciación y paridad matemática."""

    def setUp(self):
        self.platform = create_reference_platform()
        self.obs = {
            "REC2": (np.radians(39.48142721), np.radians(-0.33545582), 52.348),
            "REC3": (np.radians(39.48143234), np.radians(-0.33544876), 52.347),
            "REC4": (np.radians(39.48142145), np.radians(-0.33545934), 52.349),
            "REC5": (np.radians(39.48142658), np.radians(-0.33545228), 52.348),
        }
        self.gnss_codes = ["REC2", "REC3", "REC4", "REC5"]
        self.lever_arms_b = {c: self.platform.sensors[c].lever_arm_b for c in self.platform.sensors}

    def test_pipeline_atomic_steps(self):
        # 1. Observables a ECEF
        gnss_ecef = gnss_observations_to_ecef(self.obs, GRS80)
        self.assertEqual(len(gnss_ecef), 4)

        # 2. Centroide
        centroid_ecef, lat_c, lon_c, h_c, Ce2n_c = compute_navigation_centroid(gnss_ecef, self.gnss_codes, GRS80)
        self.assertEqual(centroid_ecef.shape, (3,))
        self.assertAlmostEqual(float(np.degrees(lat_c)), 39.4814, places=3)

        # 3. Proyección al n-frame
        dx_n = project_ecef_to_nframe(gnss_ecef, self.gnss_codes, centroid_ecef, Ce2n_c)
        self.assertEqual(len(dx_n), 4)

        # 4. Kabsch SVD
        Cb2n, cent_b, cent_n, euler_deg, att_deg, det_dcm, ortho_err = solve_attitude_kabsch(
            self.lever_arms_b, dx_n, self.gnss_codes
        )
        self.assertAlmostEqual(det_dcm, 1.0, places=10)
        self.assertAlmostEqual(ortho_err, 0.0, places=12)

        # 5. Origen PLA
        r_pla, lat_p, lon_p, h_p, Cn2e_pla, Cb2e = solve_pla_origin_ecef(
            centroid_ecef, cent_b, Cb2n, lat_c, lon_c, GRS80
        )
        self.assertEqual(r_pla.shape, (3,))

    def test_pure_pipeline_vs_facade_parity(self):
        # Ejecutar pipeline matemático puro
        sol_pure = solve_georeferencing_pipeline(
            gnss_observations=self.obs,
            lever_arms_b=self.lever_arms_b,
            gnss_sensor_codes=self.gnss_codes,
            ins_attitude_deg=(0.263568, -0.437974, 2.869214),
            ins_boresight_deg=self.platform.sensors["INS"].boresight_deg,
            magnetic_declination_deg=-0.700,
            geoid_undulation_N=50.0166,
            ellipsoid=GRS80,
            utm_zone=30,
            utm_hemisphere="N"
        )

        # Ejecutar fachada sobre Platform
        sol_facade = solve_multisensor_georeferencing(
            platform=self.platform,
            gnss_observations=self.obs,
            ins_attitude_deg=(0.263568, -0.437974, 2.869214),
            gnss_sensor_codes=self.gnss_codes,
            magnetic_declination_deg=-0.700,
            geoid_undulation_N=50.0166,
            ellipsoid=GRS80,
            utm_zone=30,
            utm_hemisphere="N"
        )

        # Verificar paridad exacta (0.0 desviación numérica)
        np.testing.assert_allclose(sol_pure.pla_origin_ecef, sol_facade.pla_origin_ecef, atol=1e-14)
        self.assertAlmostEqual(sol_pure.pla_origin_lat_rad, sol_facade.pla_origin_lat_rad, places=14)
        self.assertAlmostEqual(sol_pure.pla_origin_lon_rad, sol_facade.pla_origin_lon_rad, places=14)
        self.assertAlmostEqual(sol_pure.pla_origin_h_ellip, sol_facade.pla_origin_h_ellip, places=14)
        np.testing.assert_allclose(sol_pure.Cb2n_gnss, sol_facade.Cb2n_gnss, atol=1e-14)
        np.testing.assert_allclose(sol_pure.Cb2n_ins, sol_facade.Cb2n_ins, atol=1e-14)

        for code in sol_pure.results_gnss:
            np.testing.assert_allclose(sol_pure.results_gnss[code].ecef, sol_facade.results_gnss[code].ecef, atol=1e-14)
            self.assertAlmostEqual(sol_pure.results_gnss[code].easting, sol_facade.results_gnss[code].easting, places=10)
            self.assertAlmostEqual(sol_pure.results_gnss[code].northing, sol_facade.results_gnss[code].northing, places=10)


if __name__ == "__main__":
    unittest.main()

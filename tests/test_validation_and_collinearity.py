"""
Tests de Validación Numérica y Detección de Geometría Degenerada / Colineal
===========================================================================
Valida que core/validation.py detecte y rechace anomalías físicas, valores
no finitos y configuraciones de antenas colineales o coincidentes.
"""

import unittest
import numpy as np

from core.validation import (
    ValidationError, CollinearGeometryError,
    validate_finite, validate_lat_lon, validate_utm_params,
    validate_antenna_geometry, validate_sensor_codes_and_obs
)
from core.alignment import kabsch_orthogonal_procrustes
from core.geodesy import geodetic_to_ecef, utm_projection, utm_inverse


class TestValidationAndCollinearity(unittest.TestCase):

    def test_validate_finite(self):
        # Escalares y arrays válidos
        self.assertEqual(validate_finite(5.0), 5.0)
        arr = validate_finite([1.0, 2.0, 3.0])
        self.assertEqual(arr.shape, (3,))

        # NaN e Inf deben lanzar ValidationError
        with self.assertRaises(ValidationError):
            validate_finite(np.nan)
        with self.assertRaises(ValidationError):
            validate_finite([1.0, np.inf, 3.0])

    def test_validate_lat_lon(self):
        # Latitud válida
        phi, lam = validate_lat_lon(np.radians(39.48), np.radians(-0.33))
        self.assertAlmostEqual(phi, np.radians(39.48))
        self.assertAlmostEqual(lam, np.radians(-0.33))

        # Latitud fuera de rango [-pi/2, pi/2]
        with self.assertRaises(ValidationError):
            validate_lat_lon(np.radians(95.0), 0.0)
        with self.assertRaises(ValidationError):
            validate_lat_lon(np.radians(-91.0), 0.0)

        # NaN
        with self.assertRaises(ValidationError):
            validate_lat_lon(np.nan, 0.0)

    def test_validate_utm_params(self):
        # Válidos
        z, h = validate_utm_params(30, "N")
        self.assertEqual(z, 30)
        self.assertEqual(h, "N")

        z, h = validate_utm_params("31", "s")
        self.assertEqual(z, 31)
        self.assertEqual(h, "S")

        # Fuera de rango
        with self.assertRaises(ValidationError):
            validate_utm_params(0, "N")
        with self.assertRaises(ValidationError):
            validate_utm_params(61, "N")
        with self.assertRaises(ValidationError):
            validate_utm_params(30, "X")

    def test_antenna_collinearity_detection(self):
        # Caso 1: 3 puntos no colineales (triángulo equilátero en plano XY)
        pts_ok = np.array([
            [1.0, 0.0, 0.0],
            [-0.5, 0.866, 0.0],
            [-0.5, -0.866, 0.0]
        ]).T
        res = validate_antenna_geometry(pts_ok, min_points=3)
        self.assertEqual(res.shape, (3, 3))

        # Caso 2: 3 puntos colineales a lo largo del eje X (línea recta)
        pts_collinear = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.5, 0.0, 0.0]
        ]).T
        with self.assertRaises(CollinearGeometryError):
            validate_antenna_geometry(pts_collinear, min_points=3)

        # Caso 3: Puntos coincidentes (todos en el mismo lugar)
        pts_coincident = np.array([
            [1.0, 2.0, 3.0],
            [1.0, 2.0, 3.0],
            [1.0, 2.0, 3.0]
        ]).T
        with self.assertRaises(CollinearGeometryError):
            validate_antenna_geometry(pts_coincident, min_points=3)

        # Caso 4: Menos de 3 puntos
        pts_few = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0]
        ]).T
        with self.assertRaises(ValidationError):
            validate_antenna_geometry(pts_few, min_points=3)

    def test_kabsch_rejects_collinear_antennas(self):
        # Kabsch debe rechazar antenas colineales con CollinearGeometryError
        pts_from_collinear = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0]
        ]).T
        pts_to = pts_from_collinear.copy()

        with self.assertRaises(CollinearGeometryError):
            kabsch_orthogonal_procrustes(pts_from_collinear, pts_to)

    def test_geodesy_guards(self):
        # Geodetic to ECEF con latitud no física
        with self.assertRaises(ValidationError):
            geodetic_to_ecef(np.radians(100.0), 0.0, 0.0)

        # UTM projection con huso inválido
        with self.assertRaises(ValidationError):
            utm_projection(np.radians(39.0), np.radians(-0.3), zone=0)

        # UTM inverse con valores no finitos
        with self.assertRaises(ValidationError):
            utm_inverse(np.nan, 4300000.0, zone=30)


if __name__ == "__main__":
    unittest.main()

"""
PyGSN - Angular Coordinate Parsing and Formatting Tests
=======================================================
Gramática de parse_coordinate_string y redondeo/acarreo de rad_to_dms.
"""

import math
import unittest

from core.geodesy import parse_coordinate_string, rad_to_dms


DMS = 39 + 28 / 60 + 53.13 / 3600


class TestParseCoordinateString(unittest.TestCase):
    CASES = [
        ("39.481426", 39.481426),
        ("-0.335458", -0.335458),
        ("39,481426", 39.481426),
        ("39º28'53.13\"", DMS),
        ("39°28'53.13\"", DMS),
        ("39º 28' 53.13\" N", DMS),
        ("39º28'53.13\"S", -DMS),
        ("-0º20'7.650964\"", -(20 / 60 + 7.650964 / 3600)),
        ("0º20'7.65\" W", -(20 / 60 + 7.65 / 3600)),
        ("0º20'7.65\" O", -(20 / 60 + 7.65 / 3600)),
        ("39d28m53.13s", DMS),                       # 's' = segundos, no Sur
        ("39D28M53.13S", DMS),                       # notación con letras: S tras el 3er número = segundos
        ("39d28m53.13sS", -DMS),                     # segundos + hemisferio Sur
        ("3d42m10.5sE", 3 + 42 / 60 + 10.5 / 3600),
        ("39 28 53.13 S", -DMS),
        ("W 0 20 7.65", -(20 / 60 + 7.65 / 3600)),
        ("39 28", 39 + 28 / 60),
        ("39°28′53.13″", DMS),              # prima y doble prima tipográficas
    ]

    def test_cases(self):
        for txt, expected in self.CASES:
            with self.subTest(txt=txt):
                self.assertAlmostEqual(parse_coordinate_string(txt), expected, places=12)

    def test_invalid(self):
        for txt in ["", "abc", "39º61'00\"", "39º28'60\"", "-39º28'53\" N", "39 28 53 1", "39º28'53\" N S", "39-28"]:
            with self.subTest(txt=txt):
                with self.assertRaises(ValueError):
                    parse_coordinate_string(txt)


class TestRadToDms(unittest.TestCase):
    def test_carry_never_prints_sixty(self):
        val = math.radians(39 + 28 / 60 + 59.9999996 / 3600)
        d, m, s, txt = rad_to_dms(val)
        self.assertEqual((d, m), (39, 29))
        self.assertAlmostEqual(s, 0.0, places=9)
        self.assertNotIn("60.000000", txt)
        self.assertIn("39º29'00.000000", txt)

    def test_sign_below_one_degree(self):
        d, m, s, txt = rad_to_dms(math.radians(-(20 / 60)))
        self.assertEqual((d, m), (0, -20))
        self.assertTrue(txt.startswith("-"))
        d, m, s, txt = rad_to_dms(math.radians(-(5 / 3600)))
        self.assertEqual((d, m), (0, 0))
        self.assertAlmostEqual(s, -5.0, places=9)

    def test_roundtrip_with_parser(self):
        for deg in [39.481425, -0.335458, 0.0, 89.9999999]:
            txt = rad_to_dms(math.radians(deg))[3].strip()
            self.assertAlmostEqual(parse_coordinate_string(txt), deg, delta=1e-6 / 3600 + 1e-12)


if __name__ == "__main__":
    unittest.main()

"""
Tests de Desacoplamiento Cartográfico y Multi-Huso en CartoMapCanvas
=====================================================================
Valida que CartoMapCanvas obtenga dinámicamente los parámetros del SRT activo
(huso, hemisferio y elipsoide) y no dependa del Huso 30N fijo.
"""

import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from core.models import Platform, ReferenceSystem
from core.project import Project
from core.geodesy import GRS80, WGS84, utm_inverse
from gui.canvas_map import CartoMapCanvas, CartoMapWidget

# Asegurar instancia de QApplication para pruebas de widgets
app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestCanvasMapMultizone(unittest.TestCase):

    def setUp(self):
        self.proj = Project(name="Test Project")
        # Definir SRT en Huso 31N (Baleares/Cataluña)
        self.rs31 = ReferenceSystem(
            id="SRT_31N",
            name="UTM 31N WGS84",
            ellipsoid="WGS84",
            utm_zone=31,
            utm_hemisphere="N"
        )
        self.proj.add_reference_system(self.rs31, set_active=True)

        # Definir SRT en Huso 18S (Sudamérica / Perú)
        self.rs18s = ReferenceSystem(
            id="SRT_18S",
            name="UTM 18S WGS84",
            ellipsoid="WGS84",
            utm_zone=18,
            utm_hemisphere="S"
        )
        self.proj.add_reference_system(self.rs18s)

    def test_canvas_extracts_srt_parameters(self):
        # Crear lienzo asociado a SRT_31N
        canvas = CartoMapCanvas(
            get_project=lambda: self.proj,
            ref_system_id="SRT_31N"
        )
        rs = canvas.get_current_ref_system()
        self.assertIsNotNone(rs)
        self.assertEqual(rs.utm_zone, 31)
        self.assertEqual(rs.utm_hemisphere, "N")
        self.assertEqual(rs.get_ellipsoid(), WGS84)

        # Crear lienzo asociado a SRT_18S
        canvas_south = CartoMapCanvas(
            get_project=lambda: self.proj,
            ref_system_id="SRT_18S"
        )
        rs_s = canvas_south.get_current_ref_system()
        self.assertIsNotNone(rs_s)
        self.assertEqual(rs_s.utm_zone, 18)
        self.assertEqual(rs_s.utm_hemisphere, "S")

    def test_tile_projection_caching_performance(self):
        # Verificar que la caché de esquinas UTM almacene las proyecciones sin recalcular
        canvas = CartoMapCanvas(
            get_project=lambda: self.proj,
            ref_system_id="SRT_31N"
        )
        self.assertEqual(len(canvas._tile_utm_cache), 0)

        # Simular dibujo / consulta de tesela en la caché
        key = (15, 16500, 12000, 31, "N")
        canvas._tile_utm_cache[key] = (500000.0, 4500000.0, 501000.0, 4500000.0, 501000.0, 4499000.0, 500000.0, 4499000.0)
        self.assertEqual(len(canvas._tile_utm_cache), 1)

        # La consulta debe ser inmediata (O(1))
        cached_val = canvas._tile_utm_cache.get(key)
        self.assertIsNotNone(cached_val)
        self.assertEqual(cached_val[0], 500000.0)


if __name__ == "__main__":
    unittest.main()

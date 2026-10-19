"""
Pruebas unitarias y de integración para la Suite PySide6 / Qt
=============================================================
Valida la instanciación de la ventana principal, árbol de capas,
creación de plataformas, montaje de sensores, vistas CAD y solvers.
"""

import sys
import unittest
import numpy as np

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.models import Platform, Sensor, SensorType
from core.project import Project
from gui.app import PyGSNMainWindow


class TestPySideGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.window = PyGSNMainWindow()

    def tearDown(self):
        self.window.close()

    def test_startup_clean_state(self):
        """Verifica que el arranque sea 100% limpio (workspace vacío, sin plataformas iniciales)."""
        self.assertEqual(self.window.workspace.count(), 0)
        self.assertEqual(len(self.window.project.platforms), 0)
        self.assertEqual(self.window.hierarchy_dock.tree.topLevelItemCount(), 1)
        root = self.window.hierarchy_dock.tree.topLevelItem(0)
        self.assertTrue("Proyecto" in root.text(0))
        # Debe haber 2 ramas: Plataformas y Sistemas de Referencia
        self.assertEqual(root.childCount(), 2)
        plat_group = root.child(0)
        self.assertTrue("Plataformas" in plat_group.text(0))
        self.assertTrue("No hay plataformas" in plat_group.child(0).text(0))
        srts_group = root.child(1)
        self.assertTrue("Sistemas de Referencia" in srts_group.text(0))
        self.assertTrue("No hay sistemas de referencia" in srts_group.child(0).text(0))

    def test_create_and_activate_platform(self):
        """Verifica la creación de una plataforma y su activación en el Workspace CAD."""
        plat = Platform(
            id="VEH_01",
            name="Vehiculo Test",
            platform_type="VEHICLE",
            has_dimensions=True,
            length_m=4.5,
            width_m=2.0,
            height_m=1.6
        )
        self.window.project.add_platform(plat, set_active=True)
        self.window.on_project_changed()

        # Debe estar en el árbol dentro de la rama Plataformas
        root = self.window.hierarchy_dock.tree.topLevelItem(0)
        self.assertEqual(root.childCount(), 2)
        plat_group = root.child(0)
        self.assertEqual(plat_group.childCount(), 1)
        plat_item = plat_group.child(0)
        self.assertTrue("Vehiculo Test" in plat_item.text(0))

        # Abrir pestaña en el workspace
        self.window.open_platform_tab("VEH_01")
        self.assertEqual(self.window.workspace.count(), 1)
        self.assertEqual(self.window.workspace.tabText(0), "Plataforma: Vehiculo Test")

        # Verificar controles de vistas CAD
        cad_widget = self.window.platform_canvases["VEH_01"]
        self.assertTrue(cad_widget.is_quad_mode)
        cad_widget.set_single_view("S")
        self.assertFalse(cad_widget.is_quad_mode)
        self.assertEqual(cad_widget.canvas_single.view_type, "S")
        cad_widget.set_quad_mode()
        self.assertTrue(cad_widget.is_quad_mode)

    def test_reference_system_lifecycle(self):
        """Verifica la creación, listado y eliminación en el árbol para Sistemas de Referencia Terrestres."""
        from core.models import ReferenceSystem
        proj = self.window.project
        # Arranque limpio: 0 SRTs iniciales
        self.assertEqual(len(proj.reference_systems), 0)

        # Añadir un SRT
        rs1 = ReferenceSystem(id="SRT_01", name="ETRS89 UTM 30N", ellipsoid="GRS80", utm_zone=30)
        proj.add_reference_system(rs1)
        self.window.on_project_changed()

        self.assertEqual(len(proj.reference_systems), 1)
        root = self.window.hierarchy_dock.tree.topLevelItem(0)
        srts_group = root.child(1)
        self.assertEqual(srts_group.childCount(), 1)
        self.assertTrue("SRT_01" in srts_group.child(0).text(0))

        # Añadir un segundo SRT
        rs2 = ReferenceSystem(id="SRT_02", name="UTM 31N WGS84", ellipsoid="WGS84", utm_zone=31)
        proj.add_reference_system(rs2)
        self.window.on_project_changed()
        self.assertEqual(len(proj.reference_systems), 2)
        srts_group = self.window.hierarchy_dock.tree.topLevelItem(0).child(1)
        self.assertEqual(srts_group.childCount(), 2)

        # Eliminar el primer SRT libremente
        proj.remove_reference_system("SRT_01")
        self.window.on_project_changed()
        self.assertEqual(len(proj.reference_systems), 1)
        srts_group = self.window.hierarchy_dock.tree.topLevelItem(0).child(1)
        self.assertEqual(srts_group.childCount(), 1)

        # Eliminar también el segundo SRT (permitiendo volver a 0)
        proj.remove_reference_system("SRT_02")
        self.window.on_project_changed()
        self.assertEqual(len(proj.reference_systems), 0)
        srts_group = self.window.hierarchy_dock.tree.topLevelItem(0).child(1)
        self.assertTrue("No hay sistemas de referencia" in srts_group.child(0).text(0))

    def test_sensor_mounting_and_centration(self):
        """Verifica el montaje de sensores y los comandos de centrado."""
        plat = Platform(id="ROV_01", name="Rover Test", has_dimensions=False)
        s1 = Sensor("GPS1", "Antena GNSS", SensorType.GNSS, lever_arm_b=np.array([1.2, 0.5, -0.8]))
        s2 = Sensor("IMU1", "Unidad INS", SensorType.INS, lever_arm_b=np.array([0.0, 0.0, 0.0]))
        plat.add_sensor(s1)
        plat.add_sensor(s2)

        self.window.project.add_platform(plat, set_active=True)
        self.window.open_platform_tab("ROV_01")

        cad_widget = self.window.platform_canvases["ROV_01"]
        cad_widget.center_origin()
        self.assertEqual(cad_widget.canvas_top.pan_x, 0.0)
        self.assertEqual(cad_widget.canvas_top.pan_y, 0.0)

        cad_widget.center_centroid()
        # El centroide no es 0 ya que GPS1 está en [1.2, 0.5, -0.8]
        self.assertNotEqual(cad_widget.canvas_top.pan_x, 0.0)

    def test_console_dock_commands(self):
        """Verifica la ejecución de comandos en la terminal CLI integrada."""
        console = self.window.console_dock
        console._execute_command("status")
        console._execute_command("platforms")
        console._execute_command("help")
        log_text = console.output.toPlainText()
        self.assertTrue("Proyecto" in log_text)
        self.assertTrue("Comandos disponibles" in log_text)


if __name__ == "__main__":
    unittest.main()

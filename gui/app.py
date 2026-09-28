"""
PyGSN - GUI Application Orchestrator
===================================
Orquestador principal de la interfaz gráfica de ingeniería:
- Viewport maximizado a pantalla completa por defecto (sin desfases ni recortes).
- Arranque limpio en blanco ("Proyecto sin título - PyGSN") sin sesgos ni datos pre-cargados.
- Barra de Menú Global y Barra de Herramientas Contextual de acceso rápido.
- Panel Izquierdo: Capas / Jerarquía del Proyecto e Inspector de Propiedades en tiempo real.
- Panel Derecho: Workspace Dinámico con 4 vistas desacopladas:
  1. Lienzo CAD 2D (3 Vistas Ortogonales: Planta, Perfil, Alzado con zoom dinámico)
  2. Solver de Georreferenciación & Actitud Multi-Sensor (SVD de Kabsch)
  3. Informe Técnico TXT Monospace de Grado Industrial
  4. Simulación Cinemática & Trayectorias
- Barra de Estado inferior en tiempo real.
"""

import unicodedata
from pathlib import Path
import dearpygui.dearpygui as dpg
import numpy as np


def _ascii_viewport_title(text: str) -> str:
    """Convierte un string a ASCII puro eliminando diacriticos.
    Requerido porque DearPyGui delega el titulo del viewport al OS en Windows (CP1252),
    corrompiendo caracteres UTF-8 fuera del rango ASCII basico (U+0000..U+007F).
    Solo debe aplicarse a dpg.create_viewport(title=...) y dpg.set_viewport_title().
    Los dpg.add_text() y add_menu_item() usan el motor de fuentes interno de DearPyGui
    y admiten UTF-8 sin problema.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn" and ord(c) < 128)

from core.models import Platform, Sensor, SensorType
from core.project import Project
from gui.theme import apply_pygsn_theme
from gui.modals import ProjectModals
from gui.panel_hierarchy import HierarchyPanel
from gui.panel_georeferencing import GeoreferencingPanel
from gui.panel_report import ReportViewerPanel
from gui.panel_kinematics import KinematicsPanel
from gui.views_ortho import OrthoViewCanvas


class PyGSNApp:
    """Aplicación principal DearPyGui para PyGSN (Arquitectura Desktop tipo QGIS/Statgraphics)."""

    def __init__(self):
        # Arranque limpio: Plataforma genérica con único sensor de origen PLA
        self.platform = Platform(
            name="Plataforma Principal",
            platform_type="GENERIC",
            length_m=2.0,
            width_m=1.0,
            height_m=0.5
        )
        self.platform.add_sensor(
            Sensor(
                code="PLA",
                name="Origen de Plataforma",
                sensor_type=SensorType.PLATFORM_ORIGIN,
                lever_arm_b=np.zeros(3, dtype=np.float64),
                boresight_deg=(0.0, 0.0, 0.0)
            )
        )
        self.project = Project(
            name="Proyecto sin titulo",
            description="Proyecto de Georeferenciacion y Navegacion Multi-Sensor",
            platform=self.platform
        )
        self.current_project_file: Path | None = None

        # Componentes de la interfaz
        self.canvas: OrthoViewCanvas | None = None
        self.panel_georef: GeoreferencingPanel | None = None
        self.panel_report: ReportViewerPanel | None = None
        self.panel_kinematics: KinematicsPanel | None = None
        self.hierarchy: HierarchyPanel | None = None
        self.modals: ProjectModals | None = None

    def on_platform_changed(self):
        """Callback ejecutado cuando se modifica la geometría o sensores de la plataforma."""
        if self.canvas:
            self.canvas.redraw_all()
        if self.hierarchy:
            self.hierarchy.rebuild_tree()

    def set_active_project(self, new_project: Project, filepath: str | Path | None = None):
        """Asigna un nuevo proyecto activo en la aplicación."""
        self.project = new_project
        self.platform = new_project.platform
        self.current_project_file = Path(filepath) if filepath else None

        if self.canvas:
            self.canvas.platform = self.platform
            self.canvas.redraw_all()
        if self.panel_georef:
            self.panel_georef.platform = self.platform
            self.panel_georef.clear_gnss_observations()
        if self.hierarchy:
            self.hierarchy.rebuild_tree()
            self.hierarchy.rebuild_inspector()

        self.update_ui_state()
        dpg.set_value("status_bar_state", f"[OK] Proyecto cargado: {self.project.name}")

    def on_project_changed(self):
        """Callback ejecutado cuando se actualizan propiedades del proyecto o del chasis."""
        self.on_platform_changed()
        self.update_ui_state()

    def on_georef_solved(self, solution, report_text: str):
        """Callback ejecutado tras resolver la georreferenciación."""
        if self.panel_report:
            self.panel_report.update_report(report_text)
        dpg.set_value("status_bar_state", "[OK] Georreferenciación y actitud calculadas con éxito")
        if dpg.does_item_exist("workspace_tabs"):
            dpg.set_value("workspace_tabs", "tab_solver")

    def update_ui_state(self):
        """Actualiza titulo de ventana y barra de estado."""
        title = _ascii_viewport_title(f"{self.project.name} - PyGSN")
        dpg.set_viewport_title(title)
        if dpg.does_item_exist("status_bar_proj_name"):
            dpg.set_value("status_bar_proj_name", f"Proyecto: {self.project.name}")
        if dpg.does_item_exist("status_bar_geodesy"):
            cfg = self.project.config
            dpg.set_value(
                "status_bar_geodesy",
                f"Elipsoide: {self.project.ellipsoid_name} | UTM: Huso {cfg.get('utm_zone', 30)} | N: {cfg.get('geoid_undulation_n', 0.0):.3f}m"
            )

    def save_current_project(self):
        """Guarda el proyecto en el archivo actual o abre el dialogo Guardar Como."""
        if self.current_project_file:
            try:
                self.project.save(self.current_project_file)
                dpg.set_value("status_bar_state", f"[OK] Guardado en: {self.current_project_file.name}")
            except Exception as e:
                dpg.set_value("status_bar_state", f"Error al guardar: {str(e)[:40]}")
        else:
            self.modals.show_save_project()

    def import_calibration_dialog(self):
        """Abre explorador nativo para importar calibracion de plataforma (.txt)."""
        from gui.modals import pick_open_file_native
        path = pick_open_file_native(
            title="Importar Calibracion de Plataforma",
            filetypes=(("Archivos de Calibracion (*.txt)", "*.txt"), ("Todos los archivos (*.*)", "*.*")),
            initialdir="data"
        )
        if not path:
            return
        p = Path(path)
        try:
            self.project.import_calibration_txt(p)
            self.platform = self.project.platform
            self.on_platform_changed()
            dpg.set_value("status_bar_state", f"[OK] Calibracion importada: {p.name}")
        except Exception as e:
            dpg.set_value("status_bar_state", f"Error al importar calibracion: {str(e)[:40]}")

    def export_calibration_dialog(self):
        """Abre explorador nativo para exportar calibracion de plataforma (.txt)."""
        from gui.modals import pick_save_file_native
        path = pick_save_file_native(
            title="Exportar Calibracion de Plataforma",
            defaultextension=".txt",
            filetypes=(("Archivos de Calibracion (*.txt)", "*.txt"), ("Todos los archivos (*.*)", "*.*")),
            initialdir="output"
        )
        if not path:
            return
        p = Path(path)
        try:
            self.project.export_calibration_txt(p)
            dpg.set_value("status_bar_state", f"[OK] Calibracion exportada: {p.name}")
        except Exception as e:
            dpg.set_value("status_bar_state", f"Error al exportar calibracion: {str(e)[:40]}")

    def run(self):
        dpg.create_context()
        apply_pygsn_theme()

        # Viewport de DearPyGui maximizado por defecto
        # NOTA: title debe ser ASCII puro (Error A - 2026-09-27).
        # DearPyGui delega el titulo al OS en Windows (CP1252).
        dpg.create_viewport(
            title=_ascii_viewport_title(f"{self.project.name} - PyGSN"),
            width=1440,
            height=900,
            min_width=1100,
            min_height=700
        )
        dpg.setup_dearpygui()

        # Instanciación de módulos
        self.canvas = OrthoViewCanvas(self.platform)
        self.panel_georef = GeoreferencingPanel(self.platform, on_solution_computed=self.on_georef_solved)
        self.panel_report = ReportViewerPanel(get_report_text=lambda: self.panel_georef.last_report_text if self.panel_georef else "")
        self.panel_kinematics = KinematicsPanel(get_project=lambda: self.project)
        self.hierarchy = HierarchyPanel(
            get_project=lambda: self.project,
            on_update_callback=self.on_platform_changed,
            on_add_sensor_click=lambda: self.modals.show_add_sensor() if self.modals else None,
            get_obs_count=lambda: len(self.panel_georef.gnss_obs_list) if self.panel_georef else 0
        )
        self.modals = ProjectModals(
            get_project=lambda: self.project,
            set_project=self.set_active_project,
            on_project_updated=self.on_project_changed
        )

        # Construir modales ocultos
        self.modals.build_modals()

        # Ventana Principal que abarca todo el viewport
        with dpg.window(label="PyGSN Master Window", tag="main_window", no_title_bar=True, no_move=True):
            # =================================================================
            # 1. BARRA DE MENÚ GLOBAL
            # =================================================================
            with dpg.menu_bar():
                with dpg.menu(label="Proyecto"):
                    dpg.add_menu_item(label="Nuevo Proyecto...",       callback=lambda: self.modals.show_new_project())
                    dpg.add_menu_item(label="Abrir Proyecto (.pygsn)...", callback=lambda: self.modals.open_project_dialog())
                    dpg.add_separator()
                    dpg.add_menu_item(label="Guardar",                 callback=self.save_current_project)
                    dpg.add_menu_item(label="Guardar Como...",          callback=lambda: self.modals.show_save_project())
                    dpg.add_separator()
                    dpg.add_menu_item(label="Propiedades del Proyecto...", callback=lambda: self.modals.show_project_properties())
                    dpg.add_menu_item(label="Exportar Informe TXT...",  callback=lambda: self.panel_georef._cb_export_txt() if self.panel_georef else None)
                    dpg.add_separator()
                    dpg.add_menu_item(label="Salir de PyGSN",           callback=lambda: dpg.stop_dearpygui())

                with dpg.menu(label="Plataforma"):
                    dpg.add_menu_item(label="Anadir Sensor al Rig...",  callback=lambda: self.modals.show_add_sensor())
                    dpg.add_separator()
                    dpg.add_menu_item(label="Importar Calibracion (.txt)...", callback=self.import_calibration_dialog)
                    dpg.add_menu_item(label="Exportar Calibracion (.txt)...", callback=self.export_calibration_dialog)

                with dpg.menu(label="Georreferenciacion"):
                    dpg.add_menu_item(label="Resolver Actitud C_b^n (SVD Kabsch)", callback=lambda: self.panel_georef._cb_solve() if self.panel_georef else None)
                    dpg.add_menu_item(label="Ir a Pestana Solver",      callback=lambda: dpg.set_value("workspace_tabs", "tab_solver"))
                    dpg.add_separator()
                    dpg.add_menu_item(label="Cargar Observaciones (.txt)...", callback=lambda: self.panel_georef._cb_open_file_dialog() if self.panel_georef else None)
                    dpg.add_menu_item(label="Limpiar Observaciones",    callback=lambda: self.panel_georef.clear_gnss_observations() if self.panel_georef else None)

                with dpg.menu(label="Cinematica"):
                    dpg.add_menu_item(label="Simulador de Trayectorias", callback=lambda: dpg.set_value("workspace_tabs", "tab_kinematics"))

                with dpg.menu(label="Visualizacion"):
                    dpg.add_menu_item(label="Lienzo CAD 2D",            callback=lambda: dpg.set_value("workspace_tabs", "tab_canvas"))
                    dpg.add_menu_item(label="Centrar Modelo / Reset Zoom", callback=lambda: self.canvas.set_zoom(260.0))

                with dpg.menu(label="Configuracion"):
                    dpg.add_menu_item(label="Parametros Geodesicos del Proyecto...", callback=lambda: self.modals.show_project_properties())

                with dpg.menu(label="Ayuda"):
                    dpg.add_menu_item(label="Acerca de PyGSN", callback=lambda: self.modals.show_about())

            # =================================================================
            # 2. BARRA DE HERRAMIENTAS CONTEXTUAL (Action Ribbon)
            # =================================================================
            with dpg.group(horizontal=True):
                dpg.add_button(label="Nuevo",       callback=lambda: self.modals.show_new_project(), small=True)
                dpg.add_button(label="Abrir",       callback=lambda: self.modals.open_project_dialog(), small=True)
                dpg.add_button(label="Guardar",     callback=self.save_current_project, small=True)
                dpg.add_button(label="Propiedades", callback=lambda: self.modals.show_project_properties(), small=True)
                dpg.add_text("|", color=(80, 90, 105, 255))
                dpg.add_button(label="+ Sensor",    callback=lambda: self.modals.show_add_sensor(), small=True)
                dpg.add_text("|", color=(80, 90, 105, 255))
                dpg.add_button(label="Resolver SVD", callback=lambda: self.panel_georef._cb_solve() if self.panel_georef else None, small=True)
                dpg.add_button(label="Cinematica",  callback=lambda: dpg.set_value("workspace_tabs", "tab_kinematics"), small=True)
                dpg.add_text("|", color=(80, 90, 105, 255))
                dpg.add_button(label="Exportar TXT", callback=lambda: self.panel_georef._cb_export_txt() if self.panel_georef else None, small=True)
                dpg.add_spacer(width=20)
                dpg.add_text("PyGSN | Georeferenciacion de Sensores y Navegacion", color=(140, 150, 165, 255))

            dpg.add_separator()

            # =================================================================
            # 3. DOCKS PRINCIPALES: JERARQUÍA (IZQ) Y WORKSPACE (DER)
            # =================================================================
            with dpg.group(horizontal=True):
                # DOCK IZQUIERDO: Capas / Jerarquía e Inspector (~290 px)
                with dpg.child_window(width=290, height=-28, border=True, tag="dock_hierarchy"):
                    self.hierarchy.build_ui("dock_hierarchy")

                # DOCK DERECHO: Workspace Dinámico Responsivo (ancho y alto restantes)
                with dpg.child_window(width=-1, height=-28, border=True, tag="dock_workspace"):
                    with dpg.tab_bar(tag="workspace_tabs"):
                        # PESTAÑA 1: Lienzo CAD 2D
                        with dpg.tab(label="Lienzo CAD 2D (Rig de Sensores)", tag="tab_canvas"):
                            self._build_canvas_tab()

                        # PESTAÑA 2: Solver de Georreferenciación
                        with dpg.tab(label="Solver de Georreferenciación & Actitud", tag="tab_solver"):
                            self.panel_georef.build_ui("tab_solver")

                        # PESTAÑA 3: Informe Técnico TXT
                        with dpg.tab(label="Informe Técnico TXT Paso a Paso", tag="tab_report"):
                            self.panel_report.build_ui("tab_report")

                        # PESTAÑA 4: Simulación Cinemática
                        with dpg.tab(label="Simulación Cinemática & Trayectorias", tag="tab_kinematics"):
                            self.panel_kinematics.build_ui("tab_kinematics")

            # =================================================================
            # 4. BARRA DE ESTADO INFERIOR
            # =================================================================
            with dpg.group(horizontal=True):
                dpg.add_text("[Listo]", tag="status_bar_state", color=(6, 214, 160, 255))
                dpg.add_text("|", color=(80, 90, 105, 255))
                dpg.add_text(f"Proyecto: {self.project.name}", tag="status_bar_proj_name", color=(255, 209, 102, 255))
                dpg.add_text("|", color=(80, 90, 105, 255))
                cfg = self.project.config
                dpg.add_text(
                    f"Elipsoide: {self.project.ellipsoid_name} | UTM: Huso {cfg.get('utm_zone', 30)} | N: {cfg.get('geoid_undulation_n', 0.0):.3f}m",
                    tag="status_bar_geodesy",
                    color=(140, 150, 165, 255)
                )

        # Redimensionar main_window al tamaño del viewport y maximizar
        dpg.set_primary_window("main_window", True)
        dpg.show_viewport()
        dpg.maximize_viewport()

        # Dibujar vistas ortogonales por primera vez
        self.canvas.redraw_all()

        dpg.start_dearpygui()
        dpg.destroy_context()

    def _build_canvas_tab(self):
        """Construye la pestaña del Lienzo CAD con las 3 vistas ortogonales amplias."""
        with dpg.group(parent="tab_canvas"):
            # Barra de herramientas del lienzo
            with dpg.group(horizontal=True):
                dpg.add_text("Lienzo de Montaje CAD (3 Vistas Ortogonales 2D):", color=(0, 180, 216, 255))
                dpg.add_spacer(width=20)
                dpg.add_text("Escala Zoom:")
                dpg.add_slider_float(
                    default_value=260.0,
                    min_value=100.0,
                    max_value=600.0,
                    width=150,
                    callback=lambda s, a: self.canvas.set_zoom(a)
                )
                dpg.add_button(label="Centrar Modelo", callback=lambda: self.canvas.set_zoom(260.0))
                dpg.add_spacer(width=30)
                dpg.add_text("Convención: Xb Adelante (Rojo) | Yb Derecha (Verde) | -Zb Arriba (Azul)", color=(140, 150, 165, 255))

            dpg.add_separator()
            dpg.add_spacer(height=3)

            # Cuadrícula 2x2 amplia de vistas técnicas
            with dpg.group(horizontal=True):
                # Vista Superior
                with dpg.group():
                    dpg.add_text("1. VISTA SUPERIOR (Planta) [Xb Adelante vs Yb Derecha]")
                    with dpg.child_window(width=470, height=330, border=True):
                        dpg.add_drawlist(width=460, height=320, tag=self.canvas.tag_draw_top)

                # Vista Lateral
                with dpg.group():
                    dpg.add_text("2. VISTA LATERAL (Perfil) [Xb Adelante vs -Zb Arriba]")
                    with dpg.child_window(width=470, height=330, border=True):
                        dpg.add_drawlist(width=460, height=320, tag=self.canvas.tag_draw_side)

            with dpg.group(horizontal=True):
                # Vista Frontal
                with dpg.group():
                    dpg.add_text("3. VISTA FRONTAL (Alzado) [Yb Derecha vs -Zb Arriba]")
                    with dpg.child_window(width=470, height=330, border=True):
                        dpg.add_drawlist(width=460, height=320, tag=self.canvas.tag_draw_front)

                # Leyenda de Referencia y Cuadrícula
                with dpg.group():
                    dpg.add_text("Leyenda Técnica y Cuadrícula:")
                    with dpg.child_window(width=470, height=330, border=True):
                        dpg.add_text("Ejes Cartesianos del Body (b-frame):", color=(255, 209, 102, 255))
                        dpg.add_text("  [-] Eje Xb (Adelante / Longitudinal)", color=(230, 57, 70, 255))
                        dpg.add_text("  [-] Eje Yb (Derecha / Transversal)", color=(42, 157, 143, 255))
                        dpg.add_text("  [-] Eje Zb (Abajo / Vertical)", color=(69, 123, 157, 255))
                        dpg.add_separator()
                        dpg.add_text("Categorías de Sensores del Rig:", color=(255, 209, 102, 255))
                        dpg.add_text("  [*] Origen de Plataforma (PLA)", color=(255, 255, 255, 255))
                        dpg.add_text("  [*] Antenas GNSS (Receptores)", color=(255, 209, 102, 255))
                        dpg.add_text("  [*] Sensores Inerciales (INS/IMU)", color=(6, 214, 160, 255))
                        dpg.add_text("  [*] Sensores Ópticos / Cámaras", color=(247, 37, 133, 255))
                        dpg.add_text("  [*] LiDARs / Sensores Láser", color=(0, 180, 216, 255))
                        dpg.add_text("  [*] Odómetros / Sensores Auxiliares", color=(180, 180, 180, 255))
                        dpg.add_separator()
                        dpg.add_text("Cuadrícula Técnica CAD:", color=(0, 180, 216, 255))
                        dpg.add_text("  - Líneas secundarias: cada 10 cm (0.1 m)")
                        dpg.add_text("  - Líneas principales: cada 50 cm (0.5 m)")
                        dpg.add_text("  - Origen cartesiano [0, 0, 0]: Círculo blanco")

"""
PyGSN - GUI Application Orchestrator
===================================
Orquestador principal de la interfaz gráfica de ingeniería:
- Viewport maximizado a pantalla completa por defecto (sin desfases ni recortes).
- Arranque 100% limpio en blanco ("Proyecto: Proyecto sin titulo") sin plataformas ni sensores arbitrarios.
- Barra de Menú Global y Barra de Herramientas Contextual de acceso rápido.
- Panel Izquierdo: Capas / Jerarquía del Proyecto.
- Panel Central: Workspace Dinámico con apertura modular de plataformas en pestañas CAD limpias.
- Panel Derecho: Consola CLI interactiva colapsable.
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
from gui.panel_console import ConsolePanel
from gui.views_ortho import OrthoViewCanvas


class PyGSNApp:
    """Aplicación principal DearPyGui para PyGSN (Arquitectura Desktop tipo QGIS/Statgraphics)."""

    def __init__(self):
        # Arranque 100% limpio: Proyecto sin plataformas ni sensores arbitrarios cargados
        self.project = Project(
            name="Proyecto sin titulo",
            description="Proyecto de Georreferenciacion de Sensores y Navegacion",
            platforms={}
        )
        self.platform: Platform | None = None
        self.current_project_file: Path | None = None

        # Diccionario de lienzos CAD por plataforma abierta en workspace
        self.canvases: dict[str, OrthoViewCanvas] = {}
        self.canvas: OrthoViewCanvas | None = None

        # Componentes de la interfaz
        self.panel_georef: GeoreferencingPanel | None = None
        self.panel_report: ReportViewerPanel | None = None
        self.panel_kinematics: KinematicsPanel | None = None
        self.hierarchy: HierarchyPanel | None = None
        self.modals: ProjectModals | None = None
        self.console: ConsolePanel | None = None

        # Estado interactivo de herramientas de toolbar y consola
        self.platform_edit_mode: bool = False
        self.platform_active_tool: str = "Mover"
        self.sensor_edit_mode: bool = False
        self.sensor_active_tool: str = "Mover"
        self.console_visible: bool = False

    def toggle_console(self):
        """Abre o cierra el dock derecho de la consola CLI."""
        self.console_visible = not self.console_visible
        if dpg.does_item_exist("dock_console"):
            dpg.configure_item("dock_console", show=self.console_visible)
        if dpg.does_item_exist("dock_workspace"):
            dpg.configure_item("dock_workspace", width=-325 if self.console_visible else -1)
        lbl = "Consola CLI [ON]" if self.console_visible else "Consola CLI"
        if dpg.does_item_exist("btn_toggle_cli"):
            dpg.configure_item("btn_toggle_cli", label=lbl)
        dpg.set_value("status_bar_state", f"[Consola CLI {'abierta' if self.console_visible else 'cerrada'}]")
        self._cb_viewport_resized()

    def _cb_viewport_resized(self):
        """Callback al redimensionar la ventana para ajustar el lienzo al espacio exacto sin desbordamiento."""
        vp_w = dpg.get_viewport_width()
        vp_h = dpg.get_viewport_height()
        avail_w = vp_w - 295 - (325 if self.console_visible else 0)
        avail_h = vp_h - 165
        for c in self.canvases.values():
            c.resize_to_workspace(avail_w, avail_h)

    def _cb_mouse_wheel(self, sender, app_data):
        """Maneja el zoom con Ctrl + Rueda del ratón sobre el lienzo activo."""
        if self.canvas and dpg.is_key_down(dpg.mvKey_Control):
            self.canvas.handle_mouse_wheel(app_data)

    def open_platform_workspace(self, plat_id: str):
        """Activa y visualiza la plataforma indicada en una pestaña dedicada del workspace CAD."""
        plat = self.project.get_platform(plat_id)
        if not plat:
            return
        self.project.set_active_platform(plat_id)
        self.platform = plat

        tab_tag = f"tab_platform_{plat_id}"

        # Si la pestaña ya existe en el workspace, simplemente enfocarla
        if dpg.does_item_exist(tab_tag):
            dpg.set_value("workspace_tabs", tab_tag)
            if plat_id in self.canvases:
                self.canvas = self.canvases[plat_id]
                self.canvas.platform = plat
                self.canvas.redraw_all()
            dpg.set_value("status_bar_state", f"[Workspace Activo: Plataforma {plat.name}]")
            return

        # Si no existe, crear el lienzo y la pestaña en el workspace
        canvas = OrthoViewCanvas(plat, tag_prefix=f"plat_{plat_id}")
        self.canvases[plat_id] = canvas
        self.canvas = canvas

        with dpg.tab(label=f"Plataforma: {plat.name}", tag=tab_tag, parent="workspace_tabs", closable=True):
            canvas.build_canvas_ui(tab_tag)

        # Ajustar dimensiones exactas para evitar desbordamiento vertical
        vp_w = dpg.get_viewport_width()
        vp_h = dpg.get_viewport_height()
        avail_w = vp_w - 295 - (325 if self.console_visible else 0)
        avail_h = vp_h - 165
        canvas.resize_to_workspace(avail_w, avail_h)

        dpg.set_value("workspace_tabs", tab_tag)
        canvas.redraw_all()
        dpg.set_value("status_bar_state", f"[Workspace Activo: Plataforma {plat.name}]")

    def on_chassis_click(self, plat_id: str):
        """Abre la plataforma en el workspace y despliega el diálogo de acciones de chasis."""
        self.open_platform_workspace(plat_id)
        if self.modals:
            self.modals.show_chassis_actions(plat_id)

    def on_center_origin(self):
        """Centra la vista de la plataforma activa en el origen [0, 0, 0]."""
        if self.canvas:
            self.canvas.center_origin()
            dpg.set_value("status_bar_state", "[Vista] Centrado en el origen [0, 0, 0]")

    def on_center_centroid(self):
        """Centra la vista de la plataforma activa en su centroide."""
        if self.canvas:
            self.canvas.center_centroid()
            dpg.set_value("status_bar_state", "[Vista] Centrado en el centroide de la geometria")

    def open_solver_tab(self):
        """Abre la pestaña del Solver en el workspace bajo demanda."""
        if not dpg.does_item_exist("tab_solver"):
            with dpg.tab(label="Solver de Georreferenciación & Actitud", tag="tab_solver", parent="workspace_tabs", closable=True):
                self.panel_georef.build_ui("tab_solver")
        dpg.set_value("workspace_tabs", "tab_solver")

    def open_report_tab(self):
        """Abre la pestaña de informe técnico en el workspace bajo demanda."""
        if not dpg.does_item_exist("tab_report"):
            with dpg.tab(label="Informe Técnico TXT Paso a Paso", tag="tab_report", parent="workspace_tabs", closable=True):
                self.panel_report.build_ui("tab_report")
        dpg.set_value("workspace_tabs", "tab_report")

    def open_kinematics_tab(self):
        """Abre la pestaña de simulación cinemática bajo demanda."""
        if not dpg.does_item_exist("tab_kinematics"):
            with dpg.tab(label="Simulación Cinemática & Trayectorias", tag="tab_kinematics", parent="workspace_tabs", closable=True):
                self.panel_kinematics.build_ui("tab_kinematics")
        dpg.set_value("workspace_tabs", "tab_kinematics")

    def on_toolbar_create_platform(self):
        """Abre el asistente para crear una nueva plataforma."""
        if self.modals:
            self.modals.show_create_platform()

    def on_toggle_platform_edit(self):
        """Alterna el modo de edicion de plataforma."""
        self.platform_edit_mode = not self.platform_edit_mode
        tools = ["btn_plat_tool_move", "btn_plat_tool_rot", "btn_plat_tool_scale", "btn_plat_tool_vert"]
        for t in tools:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, enabled=self.platform_edit_mode)

        lbl = "Editar [ON]##plat" if self.platform_edit_mode else "Editar##plat"
        if dpg.does_item_exist("btn_plat_edit_toggle"):
            dpg.configure_item("btn_plat_edit_toggle", label=lbl)

        if self.platform_edit_mode:
            dpg.set_value("status_bar_state", f"[Modo Edicion Plataforma ACTIVO: {self.platform_active_tool}]")
        else:
            dpg.set_value("status_bar_state", "[Listo]")

    def set_platform_tool(self, tool_name: str):
        self.platform_active_tool = tool_name
        dpg.set_value("status_bar_state", f"[Herramienta Plataforma: {tool_name}]")

    def on_toggle_sensor_edit(self):
        self.sensor_edit_mode = not self.sensor_edit_mode
        tools = ["btn_sens_tool_move", "btn_sens_tool_rot"]
        for t in tools:
            if dpg.does_item_exist(t):
                dpg.configure_item(t, enabled=self.sensor_edit_mode)

        lbl = "Editar [ON]##sens" if self.sensor_edit_mode else "Editar##sens"
        if dpg.does_item_exist("btn_sens_edit_toggle"):
            dpg.configure_item("btn_sens_edit_toggle", label=lbl)

        if self.sensor_edit_mode:
            dpg.set_value("status_bar_state", f"[Modo Edicion Sensor ACTIVO: {self.sensor_active_tool}]")
        else:
            dpg.set_value("status_bar_state", "[Listo]")

    def set_sensor_tool(self, tool_name: str):
        self.sensor_active_tool = tool_name
        dpg.set_value("status_bar_state", f"[Herramienta Sensor: {tool_name}]")

    def on_toolbar_propagate(self):
        if self.panel_georef:
            self.panel_georef._cb_solve()

    def on_toolbar_transform_frames(self):
        if self.modals:
            self.modals.show_frame_transform()

    def on_toolbar_show_residuals(self):
        self.open_solver_tab()
        if self.panel_georef and self.panel_georef.last_solution:
            dpg.set_value("status_bar_state", "[Analisis] Inspeccionando residuales de consistencia GNSS vs INS")
        else:
            dpg.set_value("status_bar_state", "[Alerta] No hay solucion previa calculada. Cargue datos y resuelva primero.")

    def on_toolbar_show_diagnostics(self):
        sol = self.panel_georef.last_solution if self.panel_georef else None
        if self.modals:
            self.modals.show_diagnostics(sol)

    def on_platform_changed(self):
        """Callback ejecutado cuando se modifica la geometría o sensores de una plataforma."""
        for c in self.canvases.values():
            c.redraw_all()
        if self.hierarchy:
            self.hierarchy.rebuild_tree()
        self.update_ui_state()

    def set_active_project(self, new_project: Project, filepath: str | Path | None = None):
        """Asigna un nuevo proyecto activo en la aplicación."""
        self.project = new_project
        self.platform = new_project.platform
        self.current_project_file = Path(filepath) if filepath else None

        self.canvases.clear()
        self.canvas = None

        if dpg.does_item_exist("workspace_tabs"):
            dpg.delete_item("workspace_tabs", children_only=True)

        if self.panel_georef:
            self.panel_georef.platform = self.platform
            self.panel_georef.clear_gnss_observations()
        if self.hierarchy:
            self.hierarchy.rebuild_tree()

        self.update_ui_state()
        dpg.set_value("status_bar_state", f"[OK] Proyecto cargado: {self.project.name}")

    def on_project_changed(self):
        self.on_platform_changed()

    def on_georef_solved(self, solution, report_text: str):
        if self.panel_report:
            self.panel_report.update_report(report_text)
        dpg.set_value("status_bar_state", "[OK] Georreferenciación y actitud calculadas con éxito")
        self.open_solver_tab()

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
        if self.current_project_file:
            try:
                self.project.save(self.current_project_file)
                dpg.set_value("status_bar_state", f"[OK] Guardado en: {self.current_project_file.name}")
            except Exception as e:
                dpg.set_value("status_bar_state", f"Error al guardar: {str(e)[:40]}")
        else:
            self.modals.show_save_project()

    def import_calibration_dialog(self):
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
            if self.platform:
                self.open_platform_workspace(self.platform.id)
            dpg.set_value("status_bar_state", f"[OK] Calibracion importada: {p.name}")
        except Exception as e:
            dpg.set_value("status_bar_state", f"Error al importar calibracion: {str(e)[:40]}")

    def export_calibration_dialog(self):
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
        # NOTA: title debe ser ASCII puro (Error A - 2026-09-27)
        dpg.create_viewport(
            title=_ascii_viewport_title(f"{self.project.name} - PyGSN"),
            width=1440,
            height=900,
            min_width=1100,
            min_height=700
        )
        dpg.setup_dearpygui()

        # Instanciación de módulos
        self.panel_georef = GeoreferencingPanel(self.platform, on_solution_computed=self.on_georef_solved)
        self.panel_report = ReportViewerPanel(get_report_text=lambda: self.panel_georef.last_report_text if self.panel_georef else "")
        self.panel_kinematics = KinematicsPanel(get_project=lambda: self.project)
        self.console = ConsolePanel(
            get_project=lambda: self.project,
            get_solution=lambda: self.panel_georef.last_solution if self.panel_georef else None,
            on_solve_requested=lambda: self.panel_georef._cb_solve() if self.panel_georef else None,
            on_close_requested=self.toggle_console
        )
        self.hierarchy = HierarchyPanel(
            get_project=lambda: self.project,
            on_update_callback=self.on_platform_changed,
            on_add_sensor_click=lambda: self.modals.show_add_sensor() if self.modals else None,
            get_obs_count=lambda: len(self.panel_georef.gnss_obs_list) if self.panel_georef else 0,
            on_open_platform_tab=self.open_platform_workspace,
            on_chassis_click=self.on_chassis_click
        )
        self.modals = ProjectModals(
            get_project=lambda: self.project,
            set_project=self.set_active_project,
            on_project_updated=self.on_project_changed,
            on_center_origin=self.on_center_origin,
            on_center_centroid=self.on_center_centroid
        )

        # Construir modales ocultos
        self.modals.build_modals()

        # Registros de eventos globales: Rueda de raton con Ctrl para zoom CAD
        with dpg.handler_registry():
            dpg.add_mouse_wheel_handler(callback=self._cb_mouse_wheel)

        # Callback de redimensionamiento dinámico
        dpg.set_viewport_resize_callback(lambda: self._cb_viewport_resized())

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
                    dpg.add_menu_item(label="Crear Nueva Plataforma...", callback=self.on_toolbar_create_platform)
                    dpg.add_menu_item(
                        label="Abrir Plataforma en Workspace",
                        callback=lambda: self.open_platform_workspace(self.project.active_platform_id) if self.project.active_platform_id else None
                    )
                    dpg.add_separator()
                    dpg.add_menu_item(label="Anadir Sensor al Rig...",   callback=lambda: self.modals.show_add_sensor())
                    dpg.add_separator()
                    dpg.add_menu_item(label="Importar Calibracion (.txt)...", callback=self.import_calibration_dialog)
                    dpg.add_menu_item(label="Exportar Calibracion (.txt)...", callback=self.export_calibration_dialog)

                with dpg.menu(label="Procesamiento"):
                    dpg.add_menu_item(label="Resolver Georreferenciacion & Actitud (SVD)", callback=lambda: self.panel_georef._cb_solve() if self.panel_georef else None)
                    dpg.add_menu_item(label="Propagar Coordenadas Globales (ECEF, Geo, UTM)", callback=self.on_toolbar_propagate)
                    dpg.add_menu_item(label="Simulacion Cinematica de Trayectorias", callback=self.open_kinematics_tab)
                    dpg.add_menu_item(label="Transformador de Marcos de Referencia (i/e/n/b/s)...", callback=self.on_toolbar_transform_frames)
                    dpg.add_separator()
                    dpg.add_menu_item(label="Cargar Observaciones de Campo (.txt)...", callback=lambda: self.panel_georef._cb_open_file_dialog() if self.panel_georef else None)
                    dpg.add_menu_item(label="Limpiar Observaciones",    callback=lambda: self.panel_georef.clear_gnss_observations() if self.panel_georef else None)

                with dpg.menu(label="Analisis"):
                    dpg.add_menu_item(label="Analisis de Residuales y Consistencia (GNSS vs INS)", callback=self.on_toolbar_show_residuals)
                    dpg.add_menu_item(label="Diagnostico Espectral SVD y Ortonormalidad DCM", callback=self.on_toolbar_show_diagnostics)
                    dpg.add_menu_item(label="Ver Informe Tecnico TXT Paso a Paso", callback=self.open_report_tab)

                with dpg.menu(label="Visualizacion"):
                    dpg.add_menu_item(label="Alternar Cuadrantes / Vista Unica [/]", callback=lambda: self.canvas.toggle_view_mode() if self.canvas else None)
                    dpg.add_menu_item(label="Vista Superior (Planta) [S]", callback=lambda: self.canvas.set_single_view("S") if self.canvas else None)
                    dpg.add_menu_item(label="Vista Frontal (Alzado) [F]",  callback=lambda: self.canvas.set_single_view("F") if self.canvas else None)
                    dpg.add_menu_item(label="Vista Lateral (Perfil) [L]",  callback=lambda: self.canvas.set_single_view("L") if self.canvas else None)
                    dpg.add_separator()
                    dpg.add_menu_item(label="Centrar al Origen [0, 0]",    callback=self.on_center_origin)
                    dpg.add_menu_item(label="Centrar al Centroide",        callback=self.on_center_centroid)
                    dpg.add_separator()
                    dpg.add_menu_item(label="Alternar Consola CLI",        callback=self.toggle_console)

                with dpg.menu(label="Configuracion"):
                    dpg.add_menu_item(label="Parametros Geodesicos del Proyecto...", callback=lambda: self.modals.show_project_properties())

                with dpg.menu(label="Ayuda"):
                    dpg.add_menu_item(label="Acerca de PyGSN", callback=lambda: self.modals.show_about())

            # =================================================================
            # 2. BARRA DE HERRAMIENTAS DE INGENIERÍA
            # =================================================================
            with dpg.group(horizontal=True, tag="toolbar_engineering"):
                # --- GRUPO 1: PLATAFORMA ---
                dpg.add_text("Plataforma:", color=(0, 180, 216, 255))
                dpg.add_button(label="Crear##plat", callback=self.on_toolbar_create_platform, small=True)
                dpg.add_button(label="Editar##plat", tag="btn_plat_edit_toggle", callback=self.on_toggle_platform_edit, small=True)
                dpg.add_button(label="Mover##plat", tag="btn_plat_tool_move", callback=lambda: self.set_platform_tool("Mover"), small=True, enabled=False)
                dpg.add_button(label="Rotar##plat", tag="btn_plat_tool_rot", callback=lambda: self.set_platform_tool("Rotar"), small=True, enabled=False)
                dpg.add_button(label="Escalar##plat", tag="btn_plat_tool_scale", callback=lambda: self.set_platform_tool("Escalar"), small=True, enabled=False)
                dpg.add_button(label="Vertices##plat", tag="btn_plat_tool_vert", callback=lambda: self.set_platform_tool("Vertices"), small=True, enabled=False)

                dpg.add_text("|", color=(80, 90, 105, 255))

                # --- GRUPO 2: SENSORES ---
                dpg.add_text("Sensores:", color=(255, 209, 102, 255))
                dpg.add_button(label="+ Sensor", callback=lambda: self.modals.show_add_sensor(), small=True)
                dpg.add_button(label="Editar##sens", tag="btn_sens_edit_toggle", callback=self.on_toggle_sensor_edit, small=True)
                dpg.add_button(label="Mover##sens", tag="btn_sens_tool_move", callback=lambda: self.set_sensor_tool("Mover Lever-arm"), small=True, enabled=False)
                dpg.add_button(label="Rotar##sens", tag="btn_sens_tool_rot", callback=lambda: self.set_sensor_tool("Rotar Boresight"), small=True, enabled=False)

                # Espaciador hacia la derecha
                dpg.add_spacer(width=30)
                dpg.add_text("|", color=(80, 90, 105, 255))
                dpg.add_button(label="Consola CLI", tag="btn_toggle_cli", callback=self.toggle_console, small=True)

            dpg.add_separator()

            # =================================================================
            # 3. DOCKS PRINCIPALES: [Capas] [WorkSpace] [Consola]
            # =================================================================
            with dpg.group(horizontal=True):
                # DOCK IZQUIERDO: Capas / Jerarquía (~280 px)
                with dpg.child_window(width=280, height=-28, border=True, tag="dock_hierarchy"):
                    self.hierarchy.build_ui("dock_hierarchy")

                # DOCK CENTRAL: Workspace Limpio Dinámico (sin desbordamiento vertical)
                with dpg.child_window(width=-1, height=-28, border=True, no_scrollbar=True, tag="dock_workspace"):
                    with dpg.tab_bar(tag="workspace_tabs"):
                        # Arranque limpio: Ninguna pestaña ni texto precargado
                        pass

                # DOCK DERECHO: Consola CLI (oculta por defecto, toggleable con [Consola CLI])
                with dpg.child_window(width=320, height=-28, border=True, tag="dock_console", show=False):
                    self.console.build_ui("dock_console")

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

        dpg.start_dearpygui()
        dpg.destroy_context()

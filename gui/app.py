"""
PyGSN - Master Application Window (PySide6 / Qt)
================================================
Suite técnica para Georreferenciación de Sensores y Navegación:
- Menú global desacoplado (Proyecto, Plataforma, Procesamiento, Análisis, Visualización, Configuración, Ayuda).
- Barra de herramientas con conmutación dinámica de herramientas CAD y Sensores.
- Workspace central con pestañas limpias e independientes para cada plataforma (OrthoCADWidget).
- Docks profesionales: Capas/Jerarquía (izquierda) y Consola CLI interactiva (derecha).
- Barra de estado geodésica en tiempo real.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QToolBar, QToolButton,
    QStatusBar, QLabel, QFileDialog, QMessageBox, QWidget, QDockWidget,
    QDoubleSpinBox, QComboBox, QAbstractSpinBox
)
from PySide6.QtCore import Qt, QPoint, QLocale
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut

from core.models import Platform
from core.project import Project
from core.georeferencing import create_reference_platform

from gui.theme import apply_pyside_theme, set_window_titlebar_light
from gui.dock_hierarchy import HierarchyDock
from gui.dock_console import ConsoleDock
from gui.canvas_ortho import OrthoCADWidget
from gui.canvas_map import CartoMapWidget
from gui.panel_georeferencing import GeoreferencingWidget
from gui.panel_report import ReportViewerWidget
from gui.panel_kinematics import KinematicsWidget
from gui.dialogs import (
    DialogNewProject, DialogProjectProperties, DialogCreatePlatform,
    DialogPlatformProperties, DialogAddSensor, DialogSensorProperties,
    DialogChassisActions, DialogDiagnostics,
    DialogCreateReferenceSystem, DialogReferenceSystemProperties
)
from gui.dialogs_tools import (
    ToolDialogMoveChassis, ToolDialogRotateChassis, ToolDialogScaleChassis,
    ToolDialogSensorMove, ToolDialogSensorRotate
)
from gui.dialog_georeferencing import DialogGeoreferencingSolver
from gui.dialog_attribute_table import DialogAttributeTable


class PyGSNMainWindow(QMainWindow):
    """Ventana principal de la Suite PyGSN."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setLocale(QLocale.c())
        self.project: Project = Project(name="Proyecto sin título", platforms={})
        self.current_project_file: Optional[Path] = None

        self.platform_canvases: Dict[str, OrthoCADWidget] = {}
        self.map_canvases: Dict[str, CartoMapWidget] = {}
        self.panel_georef: Optional[GeoreferencingWidget] = None
        self.panel_report: Optional[ReportViewerWidget] = None
        self.panel_kinematics: Optional[KinematicsWidget] = None

        # Sesión de edición exclusiva y máquina de estados
        self.editing_target_type: Optional[str] = None  # None | "PLATFORM" | "SENSOR"
        self.editing_platform_id: Optional[str] = None
        self.editing_sensor_code: Optional[str] = None
        self.selected_sensor_code: Optional[str] = None
        self._edit_initial_snapshot: Optional[dict] = None
        self._undo_stack: List[dict] = []
        self.is_dirty: bool = False

        # Modos de herramientas
        self.active_platform_tool: str = "Mover"
        self.active_sensor_tool: str = "Seleccionar"

        # Instancias únicas de herramientas flotantes
        self.tool_dlg_move: Optional[ToolDialogMoveChassis] = None
        self.tool_dlg_rot: Optional[ToolDialogRotateChassis] = None
        self.tool_dlg_scale: Optional[ToolDialogScaleChassis] = None
        self.tool_dlg_sens_move: Optional[ToolDialogSensorMove] = None
        self.tool_dlg_sens_rot: Optional[ToolDialogSensorRotate] = None

        self._init_window()
        self._init_central_workspace()
        self._init_docks()
        self._init_menu_bar()
        self._init_tool_bar()
        self._init_status_bar()

        self.update_ui_state()

    def _init_window(self):
        self.setWindowTitle(f"{self.project.name} - PyGSN")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)

        # Icono de ventana
        icons_dir = Path(__file__).resolve().parent.parent / "icons"
        icon_path = icons_dir / "Logo.ico"
        if not icon_path.exists():
            icon_path = icons_dir / "Logo.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Barra de ventana nativa de Windows en modo claro
        set_window_titlebar_light(self)

    def showEvent(self, event):
        super().showEvent(event)
        set_window_titlebar_light(self)

    def _init_central_workspace(self):
        self.workspace = QTabWidget()
        self.workspace.setTabsClosable(True)
        self.workspace.setMovable(True)
        self.workspace.tabCloseRequested.connect(self._on_tab_close_requested)
        self.workspace.currentChanged.connect(self._on_workspace_tab_changed)
        self.setCentralWidget(self.workspace)

    def _init_docks(self):
        # Dock Izquierdo: Capas / Jerarquía
        self.hierarchy_dock = HierarchyDock(
            get_project=lambda: self.project,
            on_project_changed=self.on_project_changed,
            parent=self
        )
        self.hierarchy_dock.platform_activated.connect(self.open_platform_tab)
        self.hierarchy_dock.center_origin_requested.connect(self.center_platform_origin)
        self.hierarchy_dock.center_centroid_requested.connect(self.center_platform_centroid)
        self.hierarchy_dock.add_sensor_requested.connect(self.show_add_sensor_dialog)
        self.hierarchy_dock.import_sensors_requested.connect(self.action_import_sensors_file)
        self.hierarchy_dock.platform_properties_requested.connect(self.show_platform_properties_dialog)
        self.hierarchy_dock.platform_attribute_table_requested.connect(self.action_open_attribute_table)
        self.hierarchy_dock.delete_platform_requested.connect(self.delete_platform)
        self.hierarchy_dock.chassis_edit_requested.connect(self.start_chassis_edit)
        self.hierarchy_dock.chassis_clear_requested.connect(self.clear_chassis)
        self.hierarchy_dock.sensor_edit_requested.connect(self.start_sensor_edit)
        self.hierarchy_dock.sensor_selected.connect(lambda pid, code: self.select_sensor(pid, code))
        self.hierarchy_dock.sensor_zoom_requested.connect(self.zoom_to_sensor)
        self.hierarchy_dock.sensor_properties_requested.connect(self.show_sensor_properties_dialog)
        self.hierarchy_dock.delete_sensor_requested.connect(self.delete_sensor)
        self.hierarchy_dock.create_platform_requested.connect(self.action_create_platform)
        self.hierarchy_dock.create_reference_system_requested.connect(self.action_create_reference_system)
        self.hierarchy_dock.reference_system_activated.connect(self.action_set_active_reference_system)
        self.hierarchy_dock.reference_system_map_requested.connect(self.open_reference_system_map)
        self.hierarchy_dock.reference_system_properties_requested.connect(self.action_reference_system_properties)
        self.hierarchy_dock.delete_reference_system_requested.connect(self.action_delete_reference_system)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.hierarchy_dock)

        # Dock Derecho: Consola CLI (oculta por defecto)
        self.console_dock = ConsoleDock(
            get_project=lambda: self.project,
            get_solution=lambda: self.panel_georef.last_solution if self.panel_georef else None,
            parent=self
        )
        self.console_dock.solve_requested.connect(self.action_solve_georef)
        self.console_dock.diagnostics_requested.connect(self.action_show_diagnostics)
        self.console_dock.residuals_requested.connect(self.action_show_residuals)
        self.console_dock.chassis_modified.connect(self._on_cli_chassis_modified)
        self.console_dock.sensor_modified.connect(self._on_cli_sensor_modified)
        self.console_dock.platform_created.connect(self.open_platform_tab)
        self.addDockWidget(Qt.RightDockWidgetArea, self.console_dock)
        self.console_dock.hide()

    def _init_menu_bar(self):
        mb = self.menuBar()

        # 1. Menú Proyecto
        menu_proj = mb.addMenu("&Proyecto")
        menu_proj.addAction("Nuevo Proyecto...", self.action_new_project, QKeySequence.New)
        menu_proj.addAction("Abrir Proyecto...", self.action_open_project, QKeySequence.Open)
        menu_proj.addSeparator()
        menu_proj.addAction("Guardar", self.action_save_project, QKeySequence.Save)
        menu_proj.addAction("Guardar Como...", self.action_save_project_as)
        menu_proj.addSeparator()
        menu_proj.addAction("Propiedades...", self.action_project_properties)
        menu_proj.addAction("Exportar Informe...", self.action_export_report)
        menu_proj.addSeparator()
        menu_proj.addAction("Salir", self.close, QKeySequence.Quit)

        # 2. Menú Crear (antiguo Plataforma)
        menu_create = mb.addMenu("&Crear")
        self.action_menu_new_plat = menu_create.addAction("Nueva Plataforma...", self.action_create_platform)
        self.action_menu_add_sens = menu_create.addAction(
            "Nuevo Sensor...",
            lambda: self.show_add_sensor_dialog(self.project.active_platform_id) if self.project.active_platform_id else None
        )
        menu_create.addSeparator()
        self.action_menu_new_rs = menu_create.addAction(
            "Nuevo Sistema de Referencia...",
            self.action_create_reference_system
        )
        menu_create.addSeparator()
        self.action_menu_open_plat = menu_create.addAction(
            "Abrir Plataforma en Workspace",
            lambda: self.open_platform_tab(self.project.active_platform_id) if self.project.active_platform_id else None
        )
        menu_create.addSeparator()
        menu_create.addAction("Importar Calibración...", self.action_import_calibration)
        menu_create.addAction("Exportar Calibración...", self.action_export_calibration)

        # 3. Menú Procesamiento
        menu_proc = mb.addMenu("P&rocesamiento")
        menu_proc.addAction("Georreferenciación Multipunto...", self.action_open_georeferencing_solver)
        menu_proc.addAction("Tabla de Atributos (F6)", self.action_open_active_attribute_table, QKeySequence("F6"))
        menu_proc.addAction("Calcular Orientación (SVD)", self.action_solve_georef)
        menu_proc.addAction("Simulación Cinemática", self.open_kinematics_tab)
        menu_proc.addSeparator()
        menu_proc.addAction("Cargar Observaciones...", self.action_load_observations)

        # Atajo global de Tabla de Atributos (F6)
        self.shortcut_f6 = QShortcut(QKeySequence("F6"), self, self.action_open_active_attribute_table)

        # 4. Menú Análisis
        menu_ana = mb.addMenu("&Análisis")
        menu_ana.addAction("Residuales GNSS vs INS", self.action_show_residuals)
        menu_ana.addAction("Auditoría y Diagnóstico DCM", self.action_show_diagnostics)

        # 5. Menú Vista
        menu_vis = mb.addMenu("Vista")
        menu_vis.addAction("Panel de Capas", lambda: self.hierarchy_dock.setVisible(not self.hierarchy_dock.isVisible()))
        menu_vis.addAction("Consola CLI", self.toggle_console)
        menu_vis.addSeparator()
        menu_vis.addAction("Abrir Mapa (e-frame)...", lambda: self.open_reference_system_map())
        menu_vis.addSeparator()
        menu_vis.addAction("Centrar en Origen", lambda: self.center_platform_origin(self.project.active_platform_id))
        menu_vis.addAction("Centrar en Centroide", lambda: self.center_platform_centroid(self.project.active_platform_id))
        menu_vis.addSeparator()
        menu_vis.addAction("Pantalla Completa", self.toggle_fullscreen, QKeySequence("F11"))

        # 6. Menú Ayuda
        menu_help = mb.addMenu("A&yuda")
        menu_help.addAction("Acerca de", self.action_about)

        # Atajo global de Deshacer (Ctrl+Z)
        self.action_undo_op = QAction("Deshacer Operación", self)
        self.action_undo_op.setShortcut(QKeySequence.Undo)
        self.action_undo_op.triggered.connect(self.action_undo)
        self.addAction(self.action_undo_op)

    def _init_tool_bar(self):
        tb = QToolBar("Herramientas Rápidas")
        tb.setMovable(False)
        self.addToolBar(tb)

        # SECCIÓN 1: PLATAFORMA
        lbl_plat = QLabel("Plataforma: ")
        lbl_plat.setStyleSheet("color: #0077b6; font-weight: bold;")
        tb.addWidget(lbl_plat)

        self.btn_add_plat = QToolButton()
        self.btn_add_plat.setText("+")
        self.btn_add_plat.setToolTip("Crear nueva plataforma en el proyecto")
        self.btn_add_plat.clicked.connect(self.action_create_platform)
        tb.addWidget(self.btn_add_plat)

        self.btn_plat_edit = QToolButton()
        self.btn_plat_edit.setText("Editar")
        self.btn_plat_edit.setCheckable(True)
        self.btn_plat_edit.setToolTip("Activar/Desactivar modo de edición de plataforma")
        self.btn_plat_edit.toggled.connect(self._on_toggle_platform_edit)
        tb.addWidget(self.btn_plat_edit)

        # Orden de edición de plataforma: [Dibujar, Vértices, Mover, Rotar, Escalar]
        self.tool_plat_draw = QToolButton()
        self.tool_plat_draw.setText("Dibujar")
        self.tool_plat_draw.setCheckable(True)
        self.tool_plat_draw.setEnabled(False)
        self.tool_plat_draw.setToolTip("Dibujar polígono o arrastrar caja envolvente de chasis")
        self.tool_plat_draw.clicked.connect(lambda: self._select_platform_tool("Dibujar"))
        tb.addWidget(self.tool_plat_draw)

        self.tool_plat_verts = QToolButton()
        self.tool_plat_verts.setText("Vértices")
        self.tool_plat_verts.setCheckable(True)
        self.tool_plat_verts.setEnabled(False)
        self.tool_plat_verts.setToolTip("Modificar interactivamente los vértices del polígono con el ratón y snap")
        self.tool_plat_verts.clicked.connect(lambda: self._select_platform_tool("Vértices"))
        tb.addWidget(self.tool_plat_verts)

        self.tool_plat_move = QToolButton()
        self.tool_plat_move.setText("Mover")
        self.tool_plat_move.setCheckable(True)
        self.tool_plat_move.setEnabled(False)
        self.tool_plat_move.setToolTip("Desplazar o centrar la geometría del chasis")
        self.tool_plat_move.clicked.connect(lambda: self._select_platform_tool("Mover"))
        tb.addWidget(self.tool_plat_move)

        self.tool_plat_rot = QToolButton()
        self.tool_plat_rot.setText("Rotar")
        self.tool_plat_rot.setCheckable(True)
        self.tool_plat_rot.setEnabled(False)
        self.tool_plat_rot.setToolTip("Rotar el chasis en el plano ortogonal activo")
        self.tool_plat_rot.clicked.connect(lambda: self._select_platform_tool("Rotar"))
        tb.addWidget(self.tool_plat_rot)

        self.tool_plat_scale = QToolButton()
        self.tool_plat_scale.setText("Escalar")
        self.tool_plat_scale.setCheckable(True)
        self.tool_plat_scale.setEnabled(False)
        self.tool_plat_scale.setToolTip("Escalar dimensiones del chasis respecto al centroide")
        self.tool_plat_scale.clicked.connect(lambda: self._select_platform_tool("Escalar"))
        tb.addWidget(self.tool_plat_scale)

        tb.addSeparator()

        # SECCIÓN 2: SENSOR
        lbl_sens = QLabel("Sensor: ")
        lbl_sens.setStyleSheet("color: #b45309; font-weight: bold;")
        tb.addWidget(lbl_sens)

        self.btn_add_sens = QToolButton()
        self.btn_add_sens.setText("+")
        self.btn_add_sens.setToolTip("Añadir nuevo sensor a la plataforma")
        self.btn_add_sens.clicked.connect(lambda: self.show_add_sensor_dialog(self.project.active_platform_id))
        tb.addWidget(self.btn_add_sens)

        self.btn_sens_edit = QToolButton()
        self.btn_sens_edit.setText("Editar")
        self.btn_sens_edit.setCheckable(True)
        self.btn_sens_edit.setToolTip("Activar/Desactivar modo de edición del sensor seleccionado")
        self.btn_sens_edit.toggled.connect(self._on_toggle_sensor_edit)
        tb.addWidget(self.btn_sens_edit)

        self.tool_sens_draw = QToolButton()
        self.tool_sens_draw.setText("Dibujar")
        self.tool_sens_draw.setCheckable(True)
        self.tool_sens_draw.setEnabled(False)
        self.tool_sens_draw.setToolTip("Ubicar el sensor haciendo clic en el lienzo CAD con snap")
        self.tool_sens_draw.clicked.connect(lambda: self._select_sensor_tool("Dibujar"))
        tb.addWidget(self.tool_sens_draw)

        self.tool_sens_move = QToolButton()
        self.tool_sens_move.setText("Mover")
        self.tool_sens_move.setCheckable(True)
        self.tool_sens_move.setEnabled(False)
        self.tool_sens_move.setToolTip("Mover coordenadas del lever-arm del sensor")
        self.tool_sens_move.clicked.connect(lambda: self._select_sensor_tool("Mover"))
        tb.addWidget(self.tool_sens_move)

        self.tool_sens_rot = QToolButton()
        self.tool_sens_rot.setText("Rotar")
        self.tool_sens_rot.setCheckable(True)
        self.tool_sens_rot.setEnabled(False)
        self.tool_sens_rot.setToolTip("Rotar ángulos de orientación (boresight Roll, Pitch, Yaw)")
        self.tool_sens_rot.clicked.connect(lambda: self._select_sensor_tool("Rotar"))
        tb.addWidget(self.tool_sens_rot)

        tb.addSeparator()

        # SECCIÓN SNAPPING / AJUSTE A REJILLA (GENERAL PARA CHASIS Y SENSORES)
        lbl_snap = QLabel("Ajuste: ")
        lbl_snap.setStyleSheet("color: #0077b6; font-weight: bold;")
        tb.addWidget(lbl_snap)

        self.btn_snap = QToolButton()
        self.btn_snap.setText("Snap Rejilla")
        self.btn_snap.setCheckable(True)
        self.btn_snap.setChecked(True)
        self.btn_snap.toggled.connect(self._on_snap_setting_changed)
        tb.addWidget(self.btn_snap)

        self.spin_snap_val = QDoubleSpinBox()
        self.spin_snap_val.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_snap_val.setRange(0.1, 1000.0)
        self.spin_snap_val.setValue(5.0)  # 5 cm por defecto
        self.spin_snap_val.setDecimals(1)
        self.spin_snap_val.setFixedWidth(52)
        self.spin_snap_val.valueChanged.connect(self._on_snap_setting_changed)
        tb.addWidget(self.spin_snap_val)

        self.combo_snap_unit = QComboBox()
        self.combo_snap_unit.addItems(["cm", "m"])
        self.combo_snap_unit.setCurrentText("cm")  # cm por defecto
        self.combo_snap_unit.setFixedWidth(55)
        self.combo_snap_unit.currentTextChanged.connect(self._on_snap_setting_changed)
        tb.addWidget(self.combo_snap_unit)

        tb.addSeparator()

        # SECCIÓN 3: CONSOLA CLI
        self.btn_toggle_cli = QToolButton()
        self.btn_toggle_cli.setText("Consola CLI")
        self.btn_toggle_cli.setCheckable(True)
        self.btn_toggle_cli.toggled.connect(lambda chk: self.console_dock.setVisible(chk))
        tb.addWidget(self.btn_toggle_cli)

    def _init_status_bar(self):
        sb = self.statusBar()
        self.lbl_status_state = QLabel("[Listo]")
        self.lbl_status_state.setStyleSheet("color: #059669; font-weight: bold;")
        sb.addWidget(self.lbl_status_state)

        self.lbl_status_proj = QLabel(f"Proyecto: {self.project.name}")
        self.lbl_status_proj.setStyleSheet("color: #0077b6; font-weight: 500;")
        sb.addPermanentWidget(self.lbl_status_proj)

        self.lbl_status_geo = QLabel("")
        self.lbl_status_geo.setStyleSheet("color: #495057;")
        sb.addPermanentWidget(self.lbl_status_geo)

    def update_ui_state(self):
        self.setWindowTitle(f"{self.project.name} - PyGSN")
        self.lbl_status_proj.setText(f"Proyecto: {self.project.name}")
        cfg = self.project.config
        utm = cfg.get("utm_zone", 30)
        hemi = "Norte" if utm >= 0 else "Sur"
        n = cfg.get("geoid_undulation_n", 0.0)
        self.lbl_status_geo.setText(
            f"Elipsoide: {self.project.ellipsoid_name} | UTM: Huso {abs(utm)} ({hemi}) | N: {n:.3f}m"
        )
        self.hierarchy_dock.rebuild_tree()

    def _select_platform_tool(self, tool_name: str):
        self.active_platform_tool = tool_name
        tools = {
            "Dibujar": self.tool_plat_draw,
            "Vértices": self.tool_plat_verts,
            "Mover": self.tool_plat_move,
            "Rotar": self.tool_plat_rot,
            "Escalar": self.tool_plat_scale,
        }
        for name, btn in tools.items():
            btn.setChecked(name == tool_name)
        for widget in self.platform_canvases.values():
            widget.set_active_tool(tool_name)
        self.lbl_status_state.setText(f"[Herramienta Plataforma: {tool_name}]")

        if self.editing_target_type == "PLATFORM":
            if tool_name == "Mover":
                self._show_move_tool_dialog()
            elif tool_name == "Rotar":
                self._show_rotate_tool_dialog()
            elif tool_name == "Escalar":
                self._show_scale_tool_dialog()
            else:
                self._close_all_tool_dialogs()

    def _update_platform_tools_availability(self, plat: Optional[Platform]):
        """Habilita o deshabilita herramientas según si la plataforma tiene chasis definido."""
        has_dims = bool(plat and plat.has_dimensions)
        self.tool_plat_draw.setEnabled(True)
        self.tool_plat_verts.setEnabled(has_dims)
        self.tool_plat_move.setEnabled(has_dims)
        self.tool_plat_rot.setEnabled(has_dims)
        self.tool_plat_scale.setEnabled(has_dims)

    def _disable_all_platform_tools(self):
        """Deshabilita y desmarca todas las herramientas de modificación de chasis."""
        for btn in (self.tool_plat_draw, self.tool_plat_verts, self.tool_plat_move, self.tool_plat_rot, self.tool_plat_scale):
            btn.setChecked(False)
            btn.setEnabled(False)
        self.active_platform_tool = "Navegar"
        for widget in self.platform_canvases.values():
            widget.set_editing_mode(False)
            widget.set_active_tool("Navegar")

    def _select_sensor_tool(self, tool_name: str):
        self.active_sensor_tool = tool_name
        self.tool_sens_draw.setChecked(tool_name == "Dibujar")
        self.tool_sens_move.setChecked(tool_name == "Mover")
        self.tool_sens_rot.setChecked(tool_name == "Rotar")

        plat_id = self.editing_platform_id
        if plat_id and plat_id in self.platform_canvases:
            widget = self.platform_canvases[plat_id]
            widget.set_editing_sensor(self.editing_sensor_code)
            if tool_name == "Dibujar":
                widget.set_active_tool("Dibujar")
                self._close_all_tool_dialogs()
            elif tool_name == "Mover":
                widget.set_active_tool("Mover")
                self._show_sensor_move_dialog()
            elif tool_name == "Rotar":
                widget.set_active_tool("Rotar")
                self._show_sensor_rot_dialog()
        self.lbl_status_state.setText(f"[Herramienta Sensor: {tool_name}]")

    def _disable_all_sensor_tools(self):
        """Deshabilita y desmarca todas las herramientas de sensor."""
        for btn in (self.tool_sens_draw, self.tool_sens_move, self.tool_sens_rot):
            btn.setChecked(False)
            btn.setEnabled(False)
        self.active_sensor_tool = "Navegar"
        for widget in self.platform_canvases.values():
            widget.set_editing_sensor(None)

    def _close_all_tool_dialogs(self):
        """Oculta todos los cuadros de herramientas flotantes."""
        for dlg in (self.tool_dlg_move, self.tool_dlg_rot, self.tool_dlg_scale, self.tool_dlg_sens_move, self.tool_dlg_sens_rot):
            if dlg:
                dlg.hide()

    def _position_tool_dialog(self, dlg: QWidget):
        """Posiciona una ventana de herramienta flotante en la esquina superior izquierda del Workspace (X.9)."""
        if hasattr(self, 'workspace') and self.workspace:
            global_pos = self.workspace.mapToGlobal(QPoint(15, 15))
            dlg.move(global_pos)

    def _center_chassis_geometry_to_origin(self):
        """Centra la geometría física 3D del chasis en el origen PLA [0, 0, 0]."""
        plat_id = self.editing_platform_id
        if not plat_id:
            return
        plat = self.project.get_platform(plat_id)
        if not plat or not plat.has_dimensions:
            return
        plat.center_to_origin()
        self._undo_stack.append(plat.to_dict())
        self.is_dirty = True
        if plat_id in self.platform_canvases:
            self.platform_canvases[plat_id].redraw_all()
        self.lbl_status_state.setText("[Mover] Geometría del chasis centrada en el origen PLA [0, 0, 0]")

    def _show_move_tool_dialog(self):
        plat_id = self.editing_platform_id
        if not plat_id:
            return
        if self.tool_dlg_rot:
            self.tool_dlg_rot.hide()
        if self.tool_dlg_scale:
            self.tool_dlg_scale.hide()
        if not self.tool_dlg_move:
            self.tool_dlg_move = ToolDialogMoveChassis(
                on_apply=self._apply_chassis_move,
                on_center=self._center_chassis_geometry_to_origin,
                parent=self
            )
        self._position_tool_dialog(self.tool_dlg_move)
        self.tool_dlg_move.show()
        self.tool_dlg_move.raise_()
        self.tool_dlg_move.activateWindow()

    def _apply_chassis_move(self, dx: float, dy: float, dz: float):
        plat_id = self.editing_platform_id
        if not plat_id:
            return
        plat = self.project.get_platform(plat_id)
        if not plat or not plat.has_dimensions:
            return
        plat.translate(dx, dy, dz)
        self._undo_stack.append(plat.to_dict())
        self.is_dirty = True
        if plat_id in self.platform_canvases:
            self.platform_canvases[plat_id].redraw_all()
        self.lbl_status_state.setText(f"[Mover] Chasis trasladado ΔX={dx:+.3f}m, ΔY={dy:+.3f}m, ΔZ={dz:+.3f}m")

    def _show_rotate_tool_dialog(self):
        plat_id = self.editing_platform_id
        if not plat_id:
            return
        if self.tool_dlg_move:
            self.tool_dlg_move.hide()
        if self.tool_dlg_scale:
            self.tool_dlg_scale.hide()
        widget = self.platform_canvases.get(plat_id)
        get_active_view = widget.get_active_view if widget else (lambda: "S")
        if not self.tool_dlg_rot:
            self.tool_dlg_rot = ToolDialogRotateChassis(
                get_active_view=get_active_view,
                on_apply=self._apply_chassis_rotate,
                parent=self
            )
        else:
            self.tool_dlg_rot.get_active_view = get_active_view
            self.tool_dlg_rot.refresh_view_context()
        self._position_tool_dialog(self.tool_dlg_rot)
        self.tool_dlg_rot.show()
        self.tool_dlg_rot.raise_()
        self.tool_dlg_rot.activateWindow()

    def _apply_chassis_rotate(self, angle_deg: float, plane: str):
        plat_id = self.editing_platform_id
        if not plat_id:
            return
        plat = self.project.get_platform(plat_id)
        if not plat or not plat.has_dimensions:
            return
        plat.rotate_plane(angle_deg, plane)
        self._undo_stack.append(plat.to_dict())
        self.is_dirty = True
        if plat_id in self.platform_canvases:
            self.platform_canvases[plat_id].redraw_all()
        plane_axis_map = {"S": "Zb (Yaw)", "F": "Xb (Roll)", "L": "Yb (Pitch)"}
        axis_name = plane_axis_map.get(plane.upper(), plane)
        self.lbl_status_state.setText(f"[Rotar] Chasis rotado {angle_deg:+.1f}° en plano {plane} (Eje {axis_name})")

    def _show_scale_tool_dialog(self):
        plat_id = self.editing_platform_id
        if not plat_id:
            return
        if self.tool_dlg_move:
            self.tool_dlg_move.hide()
        if self.tool_dlg_rot:
            self.tool_dlg_rot.hide()
        if not self.tool_dlg_scale:
            self.tool_dlg_scale = ToolDialogScaleChassis(
                on_apply=self._apply_chassis_scale,
                parent=self
            )
        self._position_tool_dialog(self.tool_dlg_scale)
        self.tool_dlg_scale.show()
        self.tool_dlg_scale.raise_()
        self.tool_dlg_scale.activateWindow()

    def _apply_chassis_scale(self, fx: float, fy: float, fz: float):
        plat_id = self.editing_platform_id
        if not plat_id:
            return
        plat = self.project.get_platform(plat_id)
        if not plat or not plat.has_dimensions:
            return
        plat.scale_dimensions(fx, fy, fz)
        self._undo_stack.append(plat.to_dict())
        self.is_dirty = True
        if plat_id in self.platform_canvases:
            self.platform_canvases[plat_id].redraw_all()
        self.lbl_status_state.setText(f"[Escalar] Chasis escalado ({fx:.2f}x, {fy:.2f}x, {fz:.2f}x)")

    def _show_sensor_move_dialog(self):
        if not self.editing_sensor_code or not self.editing_platform_id:
            return
        plat = self.project.get_platform(self.editing_platform_id)
        sens = plat.sensors.get(self.editing_sensor_code) if plat else None
        sens_name = sens.name if (sens and sens.name) else self.editing_sensor_code

        if self.tool_dlg_sens_rot:
            self.tool_dlg_sens_rot.hide()
        if not self.tool_dlg_sens_move:
            self.tool_dlg_sens_move = ToolDialogSensorMove(
                sensor_code=self.editing_sensor_code,
                on_apply=self._apply_sensor_move,
                sensor_name=sens_name,
                parent=self
            )
        else:
            self.tool_dlg_sens_move.setWindowTitle(f"Mover: {sens_name}")
        self._position_tool_dialog(self.tool_dlg_sens_move)
        self.tool_dlg_sens_move.show()
        self.tool_dlg_sens_move.raise_()
        self.tool_dlg_sens_move.activateWindow()

    def _apply_sensor_move(self, dx: float, dy: float, dz: float):
        if not self.editing_sensor_code or not self.editing_platform_id:
            return
        plat = self.project.get_platform(self.editing_platform_id)
        if not plat or self.editing_sensor_code not in plat.sensors:
            return
        sens = plat.sensors[self.editing_sensor_code]
        sens.lever_arm_b = [
            float(sens.lever_arm_b[0] + dx),
            float(sens.lever_arm_b[1] + dy),
            float(sens.lever_arm_b[2] + dz)
        ]
        self._undo_stack.append(plat.to_dict())
        self.is_dirty = True
        if self.editing_platform_id in self.platform_canvases:
            self.platform_canvases[self.editing_platform_id].redraw_all()
        self.hierarchy_dock.rebuild_tree()
        self.lbl_status_state.setText(f"[Sensor] Lever-arm de '{sens.name}' desplazado ({sens.lever_arm_b[0]:.3f}, {sens.lever_arm_b[1]:.3f}, {sens.lever_arm_b[2]:.3f})m")

    def _show_sensor_rot_dialog(self):
        if not self.editing_sensor_code or not self.editing_platform_id:
            return
        plat = self.project.get_platform(self.editing_platform_id)
        sens = plat.sensors.get(self.editing_sensor_code) if plat else None
        sens_name = sens.name if (sens and sens.name) else self.editing_sensor_code

        if self.tool_dlg_sens_move:
            self.tool_dlg_sens_move.hide()
        if not self.tool_dlg_sens_rot:
            self.tool_dlg_sens_rot = ToolDialogSensorRotate(
                sensor_code=self.editing_sensor_code,
                on_apply=self._apply_sensor_rotate,
                sensor_name=sens_name,
                parent=self
            )
        else:
            self.tool_dlg_sens_rot.setWindowTitle(f"Rotar: {sens_name}")
        self._position_tool_dialog(self.tool_dlg_sens_rot)
        self.tool_dlg_sens_rot.show()
        self.tool_dlg_sens_rot.raise_()
        self.tool_dlg_sens_rot.activateWindow()

    def _apply_sensor_rotate(self, da: float, db: float, dc: float):
        if not self.editing_sensor_code or not self.editing_platform_id:
            return
        plat = self.project.get_platform(self.editing_platform_id)
        if not plat or self.editing_sensor_code not in plat.sensors:
            return
        sens = plat.sensors[self.editing_sensor_code]
        cur_a, cur_b, cur_c = sens.get_boresight_alpha_beta_gamma()
        sens.boresight_deg = (
            round(float(cur_a + da), 6),
            round(float(cur_b + db), 6),
            round(float(cur_c + dc), 6)
        )
        self._undo_stack.append(plat.to_dict())
        self.is_dirty = True
        if self.editing_platform_id in self.platform_canvases:
            self.platform_canvases[self.editing_platform_id].redraw_all()
        self.hierarchy_dock.rebuild_tree()
        self.lbl_status_state.setText(f"[Sensor] Boresight de '{sens.name}' rotado ({sens.boresight_deg[0]:.6f}°, {sens.boresight_deg[1]:.6f}°, {sens.boresight_deg[2]:.6f}°)")

    def action_undo(self):
        """Revierte la última operación en la plataforma o sensor bajo edición."""
        if not self.editing_target_type or not self.editing_platform_id:
            return

        plat = self.project.get_platform(self.editing_platform_id)
        if not plat:
            return

        if len(self._undo_stack) > 1:
            self._undo_stack.pop()  # Retira estado actual
            prev_state = self._undo_stack[-1]
            restored = Platform.from_dict(prev_state)
            self.project.platforms[self.editing_platform_id] = restored
            if self.editing_platform_id in self.platform_canvases:
                self.platform_canvases[self.editing_platform_id].platform = restored
                self.platform_canvases[self.editing_platform_id].redraw_all()

            if self.editing_target_type == "PLATFORM":
                self._update_platform_tools_availability(restored)
                self.lbl_status_state.setText("[Deshacer] Operación de chasis revertida (Ctrl+Z)")
            else:
                self.lbl_status_state.setText("[Deshacer] Operación de sensor revertida (Ctrl+Z)")

            if len(self._undo_stack) <= 1:
                self.is_dirty = False
            self.hierarchy_dock.rebuild_tree()
        else:
            self.lbl_status_state.setText("[Deshacer] No hay más operaciones para revertir")

    def _on_toggle_platform_edit(self, checked: bool):
        if checked:
            # Comprobar si ya existe edición activa de sensor
            if self.editing_target_type == "SENSOR":
                QMessageBox.information(
                    self, "Edición Bloqueada",
                    f"Ya existe una sesión de edición de sensor activa ({self.editing_sensor_code}).\n"
                    "Finalice o descarte dicha edición antes de editar la plataforma."
                )
                self.btn_plat_edit.blockSignals(True)
                self.btn_plat_edit.setChecked(False)
                self.btn_plat_edit.blockSignals(False)
                return

            plat_id = self.project.active_platform_id
            if not plat_id:
                QMessageBox.warning(self, "Aviso", "No hay ninguna plataforma activa seleccionada para editar.")
                self.btn_plat_edit.blockSignals(True)
                self.btn_plat_edit.setChecked(False)
                self.btn_plat_edit.blockSignals(False)
                return

            plat = self.project.get_platform(plat_id)
            if not plat:
                self.btn_plat_edit.blockSignals(True)
                self.btn_plat_edit.setChecked(False)
                self.btn_plat_edit.blockSignals(False)
                return

            self.open_platform_tab(plat_id)

            # Iniciar sesión de edición de plataforma
            self.editing_target_type = "PLATFORM"
            self.editing_platform_id = plat_id
            self._edit_initial_snapshot = plat.to_dict()
            self._undo_stack = [plat.to_dict()]
            self.is_dirty = False

            self.btn_plat_edit.setText("Editar [ON]")
            self.btn_add_plat.setEnabled(False)
            self.action_menu_new_plat.setEnabled(False)
            self.btn_add_sens.setEnabled(False)
            self.action_menu_add_sens.setEnabled(False)
            self.btn_sens_edit.setEnabled(False)

            if plat_id in self.platform_canvases:
                self.platform_canvases[plat_id].set_editing_lock(True)
                self.platform_canvases[plat_id].set_editing_mode(True)

            self.hierarchy_dock.set_editing_context(plat_id, None)
            self._update_platform_tools_availability(plat)
            self._select_platform_tool("Mover" if plat.has_dimensions else "Dibujar")
            self.lbl_status_state.setText(f"[Modo Edición Plataforma ACTIVO: {plat.name}]")

        else:
            # Desactivar edición: comprobar si hay cambios pendientes
            if self.is_dirty:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Guardar Cambios")
                msg_box.setText(f"Ha realizado modificaciones en la plataforma '{self.editing_platform_id}'.\n¿Desea guardar o descartar los cambios?")
                set_window_titlebar_light(msg_box)
                btn_save = msg_box.addButton("Guardar Cambios", QMessageBox.AcceptRole)
                btn_discard = msg_box.addButton("Descartar Cambios", QMessageBox.DestructiveRole)
                btn_cancel = msg_box.addButton("Cancelar", QMessageBox.RejectRole)
                msg_box.setDefaultButton(btn_save)
                msg_box.exec()
                clicked = msg_box.clickedButton()

                if clicked == btn_cancel:
                    self.btn_plat_edit.blockSignals(True)
                    self.btn_plat_edit.setChecked(True)
                    self.btn_plat_edit.blockSignals(False)
                    return
                elif clicked == btn_discard:
                    if self._edit_initial_snapshot and self.editing_platform_id:
                        restored = Platform.from_dict(self._edit_initial_snapshot)
                        self.project.platforms[self.editing_platform_id] = restored
                        if self.editing_platform_id in self.platform_canvases:
                            self.platform_canvases[self.editing_platform_id].platform = restored
                            self.platform_canvases[self.editing_platform_id].redraw_all()
                        self.lbl_status_state.setText(f"[Descarte] Modificaciones de '{restored.name}' descartadas.")
                else:
                    self.lbl_status_state.setText(f"[Guardado] Cambios de '{self.editing_platform_id}' guardados.")

            self._close_all_tool_dialogs()
            plat_id = self.editing_platform_id
            if plat_id and plat_id in self.platform_canvases:
                self.platform_canvases[plat_id].set_editing_lock(False)
                self.platform_canvases[plat_id].set_editing_mode(False)
                self.platform_canvases[plat_id].set_active_tool("Navegar")

            self.editing_target_type = None
            self.editing_platform_id = None
            self._edit_initial_snapshot = None
            self._undo_stack.clear()
            self.is_dirty = False

            self.btn_plat_edit.setText("Editar")
            self.btn_plat_edit.setChecked(False)
            self.btn_add_plat.setEnabled(True)
            self.action_menu_new_plat.setEnabled(True)
            self.btn_add_sens.setEnabled(True)
            self.action_menu_add_sens.setEnabled(True)
            self.btn_sens_edit.setEnabled(True)
            self._disable_all_platform_tools()
            self.hierarchy_dock.set_editing_context(None, None)
            self.update_ui_state()

    def _on_toggle_sensor_edit(self, checked: bool):
        if checked:
            if self.editing_target_type == "PLATFORM":
                QMessageBox.information(
                    self, "Edición Bloqueada",
                    f"Ya se está editando la plataforma '{self.editing_platform_id}'.\n"
                    "Finalice o descarte la edición de plataforma primero."
                )
                self.btn_sens_edit.blockSignals(True)
                self.btn_sens_edit.setChecked(False)
                self.btn_sens_edit.blockSignals(False)
                return

            plat_id = self.project.active_platform_id
            plat = self.project.get_platform(plat_id) if plat_id else None
            if not plat or not plat.sensors:
                QMessageBox.warning(self, "Aviso", "No hay sensores en la plataforma activa para editar.")
                self.btn_sens_edit.blockSignals(True)
                self.btn_sens_edit.setChecked(False)
                self.btn_sens_edit.blockSignals(False)
                return

            selected_code = self.selected_sensor_code or self.hierarchy_dock.get_selected_sensor_code()
            if not selected_code or selected_code not in plat.sensors:
                selected_code = list(plat.sensors.keys())[0]
            self.selected_sensor_code = selected_code

            self.open_platform_tab(plat_id)

            self.editing_target_type = "SENSOR"
            self.editing_platform_id = plat_id
            self.editing_sensor_code = selected_code
            self._edit_initial_snapshot = plat.to_dict()
            self._undo_stack = [plat.to_dict()]
            self.is_dirty = False

            self.btn_sens_edit.setText("Editar [ON]")
            self.btn_add_plat.setEnabled(False)
            self.action_menu_new_plat.setEnabled(False)
            self.btn_add_sens.setEnabled(False)
            self.action_menu_add_sens.setEnabled(False)
            self.btn_plat_edit.setEnabled(False)
            self._disable_all_platform_tools()

            self.tool_sens_draw.setEnabled(True)
            self.tool_sens_move.setEnabled(True)
            self.tool_sens_rot.setEnabled(True)
            self._select_sensor_tool("Dibujar")

            if plat_id in self.platform_canvases:
                self.platform_canvases[plat_id].set_editing_lock(True)
                self.platform_canvases[plat_id].set_editing_sensor(selected_code)

            self.hierarchy_dock.set_editing_context(plat_id, selected_code)
            sens = plat.sensors.get(selected_code) if (plat and selected_code) else None
            sens_name = sens.name if (sens and sens.name) else selected_code
            self.lbl_status_state.setText(f"[Modo Edición Sensor ACTIVO: {sens_name} en {plat.name}]")

        else:
            plat = self.project.get_platform(self.editing_platform_id) if self.editing_platform_id else None
            sens = plat.sensors.get(self.editing_sensor_code) if (plat and self.editing_sensor_code) else None
            sens_name = sens.name if (sens and sens.name) else (self.editing_sensor_code or "Sensor")

            if self.is_dirty:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Guardar Cambios")
                msg_box.setText(f"Ha realizado modificaciones en el sensor '{sens_name}'.\n¿Desea guardar o descartar los cambios?")
                set_window_titlebar_light(msg_box)
                btn_save = msg_box.addButton("Guardar Cambios", QMessageBox.AcceptRole)
                btn_discard = msg_box.addButton("Descartar Cambios", QMessageBox.DestructiveRole)
                btn_cancel = msg_box.addButton("Cancelar", QMessageBox.RejectRole)
                msg_box.setDefaultButton(btn_save)
                msg_box.exec()
                clicked = msg_box.clickedButton()

                if clicked == btn_cancel:
                    self.btn_sens_edit.blockSignals(True)
                    self.btn_sens_edit.setChecked(True)
                    self.btn_sens_edit.blockSignals(False)
                    return
                elif clicked == btn_discard:
                    if self._edit_initial_snapshot and self.editing_platform_id:
                        restored = Platform.from_dict(self._edit_initial_snapshot)
                        self.project.platforms[self.editing_platform_id] = restored
                        if self.editing_platform_id in self.platform_canvases:
                            self.platform_canvases[self.editing_platform_id].platform = restored
                            self.platform_canvases[self.editing_platform_id].redraw_all()
                        self.lbl_status_state.setText(f"[Descarte] Modificaciones del sensor '{sens_name}' descartadas.")
                else:
                    self.lbl_status_state.setText(f"[Guardado] Cambios del sensor '{sens_name}' guardados.")

            self._close_all_tool_dialogs()
            self._disable_all_sensor_tools()
            plat_id = self.editing_platform_id
            if plat_id and plat_id in self.platform_canvases:
                self.platform_canvases[plat_id].set_editing_lock(False)
                self.platform_canvases[plat_id].set_editing_mode(False)
                self.platform_canvases[plat_id].set_active_tool("Navegar")
                self.platform_canvases[plat_id].set_editing_sensor(None)

            self.editing_target_type = None
            self.editing_platform_id = None
            self.editing_sensor_code = None
            self._edit_initial_snapshot = None
            self._undo_stack.clear()
            self.is_dirty = False

            self.btn_sens_edit.setText("Editar")
            self.btn_sens_edit.setChecked(False)
            self.btn_add_plat.setEnabled(True)
            self.action_menu_new_plat.setEnabled(True)
            self.btn_add_sens.setEnabled(True)
            self.action_menu_add_sens.setEnabled(True)
            self.btn_plat_edit.setEnabled(True)
            self.hierarchy_dock.set_editing_context(None, None)
            self.update_ui_state()

    def _on_workspace_tab_changed(self, index: int):
        widget = self.workspace.widget(index)
        if isinstance(widget, OrthoCADWidget) and widget.platform:
            plat = widget.platform
            self.project.set_active_platform(plat.id)
            if self.editing_target_type == "PLATFORM":
                if plat.id == self.editing_platform_id:
                    self._update_platform_tools_availability(plat)
                    self.btn_plat_edit.setEnabled(True)
                    self.btn_plat_edit.blockSignals(True)
                    self.btn_plat_edit.setChecked(True)
                    self.btn_plat_edit.blockSignals(False)
                    widget.set_editing_lock(True)
                    widget.set_editing_mode(True)
                    self.lbl_status_state.setText(f"[Modo Edición Plataforma ACTIVO: {plat.name}]")
                else:
                    self._disable_all_platform_tools()
                    self.btn_plat_edit.setEnabled(False)
                    self.btn_plat_edit.blockSignals(True)
                    self.btn_plat_edit.setChecked(False)
                    self.btn_plat_edit.blockSignals(False)
                    widget.set_editing_lock(False)
                    widget.set_editing_mode(False)
                    widget.set_active_tool("Navegar")
                    self.lbl_status_state.setText(f"[Modo Lectura - Editando {self.editing_platform_id}]")
            elif self.editing_target_type == "SENSOR":
                self._disable_all_platform_tools()
                self.btn_plat_edit.setEnabled(False)
                if plat.id == self.editing_platform_id:
                    self.btn_sens_edit.setEnabled(True)
                    self.btn_sens_edit.blockSignals(True)
                    self.btn_sens_edit.setChecked(True)
                    self.btn_sens_edit.blockSignals(False)
                    self.tool_sens_draw.setEnabled(True)
                    self.tool_sens_move.setEnabled(True)
                    self.tool_sens_rot.setEnabled(True)
                    widget.set_editing_lock(True)
                    widget.set_editing_mode(True)
                    widget.set_editing_sensor(self.editing_sensor_code)
                    self.lbl_status_state.setText(f"[Modo Edición Sensor ACTIVO: {self.editing_sensor_code} en {plat.name}]")
                else:
                    self.btn_sens_edit.setEnabled(False)
                    self.btn_sens_edit.blockSignals(True)
                    self.btn_sens_edit.setChecked(False)
                    self.btn_sens_edit.blockSignals(False)
                    self._disable_all_sensor_tools()
                    widget.set_editing_lock(False)
                    widget.set_editing_mode(False)
                    widget.set_active_tool("Navegar")
                    widget.set_editing_sensor(None)
                    self.lbl_status_state.setText(f"[Modo Lectura - Editando sensor en {self.editing_platform_id}]")
            else:
                self.btn_plat_edit.setEnabled(True)
                self.btn_sens_edit.setEnabled(bool(plat.sensors))
                self._disable_all_platform_tools()
                self._disable_all_sensor_tools()
                self.lbl_status_state.setText(f"[Workspace Activo: {plat.name}]")
            self.hierarchy_dock.rebuild_tree()

    def _on_canvas_chassis_updated(self, plat_id: str):
        if self.editing_target_type == "PLATFORM" and self.editing_platform_id == plat_id:
            plat = self.project.get_platform(plat_id)
            if plat:
                self._undo_stack.append(plat.to_dict())
                self.is_dirty = True
                self._update_platform_tools_availability(plat)
        self.update_ui_state()

    def get_snap_step_m(self) -> Optional[float]:
        """Calcula el paso de ajuste en metros según el valor numérico y unidad seleccionada."""
        if not hasattr(self, 'btn_snap') or not self.btn_snap.isChecked():
            return None
        val = self.spin_snap_val.value()
        unit = self.combo_snap_unit.currentText()
        return (val / 100.0) if unit == "cm" else val

    def _on_snap_setting_changed(self):
        step_m = self.get_snap_step_m()
        for widget in self.platform_canvases.values():
            widget.set_snap_step_m(step_m)
        unit = self.combo_snap_unit.currentText()
        val = self.spin_snap_val.value()
        status_txt = f"{val:.1f} {unit}" if step_m is not None else "Desactivado"
        self.lbl_status_state.setText(f"[Snap Rejilla: {status_txt}]")

    def toggle_console(self):
        vis = not self.console_dock.isVisible()
        self.console_dock.setVisible(vis)
        self.btn_toggle_cli.setChecked(vis)

    # =========================================================================
    # GESTIÓN DEL WORKSPACE
    # =========================================================================
    def open_platform_tab(self, plat_id: str):
        plat = self.project.get_platform(plat_id)
        if not plat:
            return
        self.project.set_active_platform(plat_id)

        # Buscar si ya existe la pestaña
        tab_title = f"Plataforma: {plat.name}"
        for i in range(self.workspace.count()):
            if self.workspace.tabText(i) == tab_title:
                if self.workspace.currentIndex() == i:
                    self._on_workspace_tab_changed(i)
                else:
                    self.workspace.setCurrentIndex(i)
                return

        widget = OrthoCADWidget(plat)
        if self.editing_target_type and self.editing_platform_id == plat_id:
            widget.set_editing_lock(True)
            widget.set_editing_mode(True)
            widget.set_active_tool(self.active_platform_tool)
        else:
            widget.set_editing_lock(False)
            widget.set_editing_mode(False)
            widget.set_active_tool("Navegar")
        widget.set_snap_step_m(self.get_snap_step_m())
        widget.chassis_updated.connect(lambda pid=plat_id: self._on_canvas_chassis_updated(pid))
        widget.sensor_placed.connect(lambda code, x, y, z, pid=plat_id: self._on_canvas_sensor_placed(pid, code, x, y, z))
        widget.sensor_moved.connect(lambda code, x, y, z, pid=plat_id: self._on_canvas_sensor_moved(pid, code, x, y, z))
        widget.sensor_selected.connect(lambda code, pid=plat_id: self.select_sensor(pid, code))
        widget.view_changed.connect(lambda v, pid=plat_id: self._on_canvas_view_changed(pid, v))
        self.platform_canvases[plat_id] = widget
        idx = self.workspace.addTab(widget, tab_title)
        self.workspace.setCurrentIndex(idx)
        self._on_workspace_tab_changed(idx)

    def open_reference_system_map(self, rs_id: Optional[str] = None):
        """Abre o activa la pestaña de mapa cartográfico 2D (e-frame) para el Sistema de Referencia Terrestre."""
        if not rs_id:
            rs_id = getattr(self.project, "active_reference_system_id", None)
            if not rs_id and getattr(self.project, "reference_systems", None):
                rs_id = next(iter(self.project.reference_systems.keys()))

        if not rs_id or rs_id not in self.project.reference_systems:
            QMessageBox.warning(
                self, "Sistema de Referencia no Encontrado",
                "No hay ningún Sistema de Referencia Terrestre (SRT) configurado en el proyecto."
            )
            return

        rs = self.project.reference_systems[rs_id]
        tab_title = f"Mapa: {rs.name}"

        # Comprobar si ya existe abierta en el workspace
        for i in range(self.workspace.count()):
            w = self.workspace.widget(i)
            if isinstance(w, CartoMapWidget) and w.ref_system_id == rs_id:
                self.workspace.setCurrentIndex(i)
                w.refresh()
                return

        # Crear nuevo widget de mapa
        map_widget = CartoMapWidget(
            get_project=lambda: self.project,
            ref_system_id=rs_id,
            parent=self
        )
        self.map_canvases[rs_id] = map_widget
        idx = self.workspace.addTab(map_widget, tab_title)
        self.workspace.setCurrentIndex(idx)
        self.lbl_status_state.setText(f"[Mapa] Vista cartográfica e-frame activada ({rs.name})")

    def _on_canvas_sensor_placed(self, plat_id: str, code: str, x: float, y: float, z: float):
        if self.editing_target_type == "SENSOR" and self.editing_platform_id == plat_id:
            plat = self.project.get_platform(plat_id)
            if plat:
                self._undo_stack.append(plat.to_dict())
                self.is_dirty = True
                self.hierarchy_dock.rebuild_tree()
                self.lbl_status_state.setText(f"[Sensor] {code} posicionado en [{x:.3f}, {y:.3f}, {z:.3f}]m")

    def _on_canvas_sensor_moved(self, plat_id: str, code: str, x: float, y: float, z: float):
        if self.editing_target_type == "SENSOR" and self.editing_platform_id == plat_id:
            plat = self.project.get_platform(plat_id)
            if plat:
                self._undo_stack.append(plat.to_dict())
                self.is_dirty = True
                self.hierarchy_dock.rebuild_tree()
                self.lbl_status_state.setText(f"[Sensor] {code} desplazado a [{x:.3f}, {y:.3f}, {z:.3f}]m")

    def _on_canvas_view_changed(self, plat_id: str, view_key: str):
        """Notifica al diálogo de rotación el cambio de vista activa para actualizar plano y eje en tiempo real."""
        if self.tool_dlg_rot and self.tool_dlg_rot.isVisible():
            self.tool_dlg_rot.refresh_view_context()

    def _on_cli_chassis_modified(self):
        self.on_project_changed()
        for widget in self.platform_canvases.values():
            widget.redraw_all()
        self.hierarchy_dock.rebuild_tree()
        self.lbl_status_state.setText("[CLI] Geometría de chasis actualizada desde consola")

    def _on_cli_sensor_modified(self):
        self.on_project_changed()
        for widget in self.platform_canvases.values():
            widget.redraw_all()
        self.hierarchy_dock.rebuild_tree()
        plat = self.project.platform
        if plat:
            self.btn_sens_edit.setEnabled(bool(plat.sensors))
        self.lbl_status_state.setText("[CLI] Sensores actualizados desde consola")

    def _on_tab_close_requested(self, index: int):
        widget = self.workspace.widget(index)
        if isinstance(widget, OrthoCADWidget):
            plat_id = widget.platform.id if widget.platform else None
            if self.editing_target_type == "PLATFORM" and self.editing_platform_id == plat_id:
                QMessageBox.warning(
                    self, "Pestaña Bloqueada",
                    f"No puede cerrar la pestaña de '{widget.platform.name}' mientras está en modo edición.\n"
                    "Finalice la edición primero."
                )
                return
            if plat_id and plat_id in self.platform_canvases:
                del self.platform_canvases[plat_id]
        elif isinstance(widget, CartoMapWidget):
            rs_id = widget.ref_system_id
            if rs_id in self.map_canvases:
                del self.map_canvases[rs_id]
        self.workspace.removeTab(index)

    def center_platform_origin(self, plat_id: Optional[str]):
        if not plat_id or plat_id not in self.platform_canvases:
            return
        self.platform_canvases[plat_id].center_origin()
        self.lbl_status_state.setText("[Vista] Centrado en el origen [0, 0, 0]")

    def center_platform_centroid(self, plat_id: Optional[str]):
        if not plat_id or plat_id not in self.platform_canvases:
            return
        self.platform_canvases[plat_id].center_centroid()
        self.lbl_status_state.setText("[Vista] Centrado en el centroide de la geometría")

    def show_chassis_actions(self, plat_id: str):
        plat = self.project.get_platform(plat_id)
        if not plat:
            return
        self.open_platform_tab(plat_id)
        dlg = DialogChassisActions(
            platform_name=plat.name,
            on_center_origin=lambda: self.center_platform_origin(plat_id),
            on_center_centroid=lambda: self.center_platform_centroid(plat_id),
            parent=self
        )
        dlg.exec()

    def show_add_sensor_dialog(self, plat_id: Optional[str]):
        if self.editing_target_type is not None:
            QMessageBox.warning(
                self, "Acción Bloqueada",
                "No se pueden añadir sensores mientras una sesión de edición está activa.\n"
                "Finalice o descarte la edición primero."
            )
            return
        if not plat_id:
            plat_id = self.project.active_platform_id
        if not plat_id:
            QMessageBox.warning(self, "Aviso", "Primero debe crear o seleccionar una plataforma.")
            return
        plat = self.project.get_platform(plat_id)
        if not plat:
            return
        dlg = DialogAddSensor(plat, self)
        if dlg.exec():
            sens = dlg.get_sensor()
            plat.add_sensor(sens)
            self.is_dirty = True
            if plat_id in self.platform_canvases:
                self.platform_canvases[plat_id].redraw_all()
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Sensor {sens.code} añadido a {plat.name}")

    def action_import_sensors_file(self, plat_id: Optional[str] = None):
        if self.editing_target_type is not None:
            QMessageBox.warning(
                self, "Acción Bloqueada",
                "No se pueden importar sensores mientras una sesión de edición está activa.\n"
                "Finalice o descarte la edición primero."
            )
            return
        if not plat_id:
            plat_id = self.project.active_platform_id
        if not plat_id:
            QMessageBox.warning(self, "Aviso", "Primero debe crear o seleccionar una plataforma.")
            return
        plat = self.project.get_platform(plat_id)
        if not plat:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Importar Sensores y Atributos para '{plat.name}' - PyGSN",
            "",
            "Tablas de Sensores y Atributos (*.xlsx *.csv *.txt *.dat);;Libros de Excel (*.xlsx);;Archivos de Texto / CSV (*.txt *.csv *.dat);;Todos los archivos (*.*)"
        )
        if not file_path:
            return

        self._undo_stack.append(plat.to_dict())
        try:
            srt = self.project.get_active_reference_system()
            srt_id = srt.id if srt else ""
            imported = plat.import_sensors_from_table(file_path, ref_system_id=srt_id)
        except Exception as e:
            QMessageBox.critical(self, "Error de Importación", f"No se pudo procesar el archivo:\n{e}")
            return

        if imported:
            self.is_dirty = True
            if plat_id in self.platform_canvases:
                self.platform_canvases[plat_id].redraw_all()
            self.on_project_changed()
            geo_count = sum(1 for s in imported if s.observation and s.observation.has_geodetic)
            att_count = sum(1 for s in imported if s.observation and s.observation.has_attitude)
            obs_info = f" ({geo_count} con GNSS, {att_count} con INS)" if (geo_count or att_count) else ""
            self.lbl_status_state.setText(f"[Importación] {len(imported)} sensores importados en '{plat.name}'{obs_info}.")
            QMessageBox.information(
                self, "Importación Exitosa",
                f"Se han importado/actualizado {len(imported)} sensores en '{plat.name}':\n"
                f"- Sensores geométricos en b-frame: {len(imported)}\n"
                f"- Observaciones GNSS asociadas: {geo_count}\n"
                f"- Observaciones de actitud INS asociadas: {att_count}\n\n"
                f"Los observables quedarán precargados automáticamente en el solver de georreferenciación."
            )
        else:
            QMessageBox.warning(
                self, "Aviso de Importación",
                "No se encontraron filas o registros de sensores válidos en el archivo seleccionado.\n"
                "Verifique el formato (ej. columnas 'Sensores', 'X1_m', 'X2_m', 'X3_m', 'alpha_deg', etc.)."
            )

    def show_platform_properties_dialog(self, plat_id: str):
        plat = self.project.get_platform(plat_id)
        if not plat:
            return
        dlg = DialogPlatformProperties(plat, self)
        if dlg.exec():
            dlg.apply_changes()
            self.is_dirty = True
            for i in range(self.workspace.count()):
                w = self.workspace.widget(i)
                if isinstance(w, OrthoCADWidget) and w.platform and w.platform.id == plat_id:
                    self.workspace.setTabText(i, f"Plataforma: {plat.name}")
                    w.lbl_info.setText(f"Plataforma: {plat.name} [{plat.platform_type}]")
            if plat_id in self.platform_canvases:
                self.platform_canvases[plat_id].redraw_all()
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Propiedades de '{plat.name}' actualizadas.")

    def delete_platform(self, plat_id: str):
        plat = self.project.get_platform(plat_id)
        if not plat:
            return
        if self.editing_target_type is not None and self.editing_platform_id == plat_id:
            QMessageBox.warning(
                self, "Acción Bloqueada",
                "No se puede eliminar la plataforma mientras está en modo edición.\n"
                "Finalice o descarte la edición primero."
            )
            return

        res = QMessageBox.question(
            self, "Confirmar Eliminación",
            f"¿Está seguro de eliminar la plataforma '{plat.name}' y todos sus sensores asociados?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res == QMessageBox.Yes:
            tab_to_close = -1
            for i in range(self.workspace.count()):
                w = self.workspace.widget(i)
                if isinstance(w, OrthoCADWidget) and w.platform and w.platform.id == plat_id:
                    tab_to_close = i
                    break
            if tab_to_close >= 0:
                self.workspace.removeTab(tab_to_close)

            if plat_id in self.platform_canvases:
                del self.platform_canvases[plat_id]

            self.project.remove_platform(plat_id)
            self.is_dirty = True
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Plataforma '{plat.name}' eliminada.")

    def start_chassis_edit(self, plat_id: str):
        plat = self.project.get_platform(plat_id)
        if not plat:
            return
        self.open_platform_tab(plat_id)
        if self.editing_target_type == "PLATFORM" and self.editing_platform_id == plat_id:
            return
        if not self.btn_plat_edit.isChecked():
            self.btn_plat_edit.setChecked(True)

    def start_sensor_edit(self, plat_id: str, sensor_code: str):
        plat = self.project.get_platform(plat_id)
        if not plat or sensor_code not in plat.sensors:
            return
        self.open_platform_tab(plat_id)
        self.selected_sensor_code = sensor_code
        self.hierarchy_dock.select_sensor_item(sensor_code)
        if plat_id in self.platform_canvases:
            self.platform_canvases[plat_id].set_selected_sensor(sensor_code)

        if self.editing_target_type == "SENSOR" and self.editing_platform_id == plat_id:
            if self.editing_sensor_code != sensor_code:
                self.editing_sensor_code = sensor_code
                if plat_id in self.platform_canvases:
                    self.platform_canvases[plat_id].set_editing_sensor(sensor_code)
                self.hierarchy_dock.set_editing_context(plat_id, sensor_code)
                sens = plat.sensors[sensor_code]
                self.lbl_status_state.setText(f"[Modo Edición Sensor ACTIVO: {sens.name} ({sensor_code})]")
            return

        self.hierarchy_dock.editing_sensor_code = sensor_code
        if not self.btn_sens_edit.isChecked():
            self.btn_sens_edit.setChecked(True)

    def zoom_to_sensor(self, plat_id: str, sensor_code: str):
        plat = self.project.get_platform(plat_id)
        if not plat or sensor_code not in plat.sensors:
            return
        self.open_platform_tab(plat_id)
        widget = self.platform_canvases.get(plat_id)
        if widget:
            widget.zoom_to_sensor(sensor_code)
            self.lbl_status_state.setText(f"[Zoom] Sensor '{sensor_code}' enfocado.")

    def show_sensor_properties_dialog(self, plat_id: str, sensor_code: str):
        plat = self.project.get_platform(plat_id)
        if not plat or sensor_code not in plat.sensors:
            return
        sensor = plat.sensors[sensor_code]
        dlg = DialogSensorProperties(sensor, plat.name, self)
        if dlg.exec():
            dlg.apply_changes()
            self.is_dirty = True
            if self.editing_target_type == "SENSOR" and self.editing_platform_id == plat_id:
                self._undo_stack.append(plat.to_dict())
            if plat_id in self.platform_canvases:
                self.platform_canvases[plat_id].platform = plat
                self.platform_canvases[plat_id].redraw_all()
            self.on_project_changed()
            self.hierarchy_dock.rebuild_tree()
            self.lbl_status_state.setText(f"[OK] Propiedades del sensor '{sensor.name}' actualizadas.")

    def delete_sensor(self, plat_id: str, sensor_code: str):
        plat = self.project.get_platform(plat_id)
        if not plat or sensor_code not in plat.sensors:
            return
        if self.editing_target_type == "SENSOR" and self.editing_sensor_code == sensor_code:
            QMessageBox.warning(
                self, "Acción Bloqueada",
                "No se puede eliminar el sensor mientras está en modo edición."
            )
            return

        res = QMessageBox.question(
            self, "Confirmar Eliminación",
            f"¿Está seguro de eliminar el sensor '{sensor_code}' de '{plat.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res == QMessageBox.Yes:
            plat.remove_sensor(sensor_code)
            if self.selected_sensor_code == sensor_code:
                self.selected_sensor_code = None
            self.is_dirty = True
            if plat_id in self.platform_canvases:
                self.platform_canvases[plat_id].redraw_all()
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Sensor '{sensor_code}' eliminado.")

    def select_sensor(self, plat_id: str, sensor_code: str):
        """Sincroniza la selección de un sensor entre el lienzo CAD, el árbol de capas y el modo de edición."""
        plat = self.project.get_platform(plat_id)
        if not plat or sensor_code not in plat.sensors:
            return
        self.selected_sensor_code = sensor_code
        self.hierarchy_dock.select_sensor_item(sensor_code)
        if plat_id in self.platform_canvases:
            self.platform_canvases[plat_id].set_selected_sensor(sensor_code)

        # Si ya estamos en sesión de edición de sensor de esta plataforma, cambiar el sensor activo en edición
        if self.editing_target_type == "SENSOR" and self.editing_platform_id == plat_id:
            if self.editing_sensor_code != sensor_code:
                self.editing_sensor_code = sensor_code
                if plat_id in self.platform_canvases:
                    self.platform_canvases[plat_id].set_editing_sensor(sensor_code)
                self.hierarchy_dock.set_editing_context(plat_id, sensor_code)
                sens = plat.sensors[sensor_code]
                self.lbl_status_state.setText(f"[Modo Edición Sensor ACTIVO: {sens.name} ({sensor_code})]")

    def clear_chassis(self, plat_id: str):
        """Restablece el chasis a estado libre sin dimensiones ni geometría poligonal."""
        plat = self.project.get_platform(plat_id)
        if not plat:
            return
        res = QMessageBox.question(
            self, "Confirmar Limpieza de Chasis",
            f"¿Está seguro de limpiar y dejar libre el chasis de la plataforma '{plat.name}'?\n"
            "Se eliminarán las dimensiones fijadas y la geometría poligonal existente.",
            QMessageBox.Yes | QMessageBox.No
        )
        if res == QMessageBox.Yes:
            plat.clear_chassis()
            self.is_dirty = True
            if plat_id in self.platform_canvases:
                self.platform_canvases[plat_id].redraw_all()
            self.hierarchy_dock.rebuild_tree()
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Chasis de '{plat.name}' restablecido a libre.")

    def open_solver_tab(self):
        plat = self.project.platform
        tab_title = "Solver de Georreferenciación & Actitud"
        for i in range(self.workspace.count()):
            if self.workspace.tabText(i) == tab_title:
                self.workspace.setCurrentIndex(i)
                return
        if not self.panel_georef:
            self.panel_georef = GeoreferencingWidget(plat)
            self.panel_georef.solution_computed.connect(self._on_solution_computed)
        else:
            self.panel_georef.platform = plat

        idx = self.workspace.addTab(self.panel_georef, tab_title)
        self.workspace.setCurrentIndex(idx)

    def open_report_tab(self):
        tab_title = "Informe Técnico TXT Paso a Paso"
        for i in range(self.workspace.count()):
            if self.workspace.tabText(i) == tab_title:
                self.workspace.setCurrentIndex(i)
                return
        if not self.panel_report:
            self.panel_report = ReportViewerWidget()
        if self.panel_georef and self.panel_georef.last_report_text:
            self.panel_report.set_report_text(self.panel_georef.last_report_text)
        idx = self.workspace.addTab(self.panel_report, tab_title)
        self.workspace.setCurrentIndex(idx)

    def open_kinematics_tab(self):
        tab_title = "Simulación Cinemática & Trayectorias"
        for i in range(self.workspace.count()):
            if self.workspace.tabText(i) == tab_title:
                self.workspace.setCurrentIndex(i)
                return
        if not self.panel_kinematics:
            self.panel_kinematics = KinematicsWidget(get_project=lambda: self.project)
        idx = self.workspace.addTab(self.panel_kinematics, tab_title)
        self.workspace.setCurrentIndex(idx)

    def _on_solution_computed(self, sol, report_text: str):
        self.lbl_status_state.setText("[OK] Georreferenciación y actitud calculadas con éxito")
        if self.panel_report:
            self.panel_report.set_report_text(report_text)
        self.open_solver_tab()

    def on_project_changed(self):
        for pid, widget in self.platform_canvases.items():
            p = self.project.get_platform(pid)
            if p:
                widget.platform = p
                widget.redraw_all()
        for map_w in self.map_canvases.values():
            map_w.refresh()
        self.update_ui_state()

    # =========================================================================
    # ACCIONES DE MENÚ
    # =========================================================================
    def action_new_project(self):
        dlg = DialogNewProject(self)
        if dlg.exec():
            data = dlg.get_project_data()
            new_proj = Project(
                name=data["name"],
                ellipsoid_name=data["ellipsoid_name"],
                platforms={},
                config={
                    "utm_zone": data["utm_zone"],
                    "geoid_undulation_n": data["geoid_undulation_n"],
                    "mag_declination_deg": data["mag_declination_deg"]
                }
            )
            self.project = new_proj
            self.current_project_file = None
            self.workspace.clear()
            self.platform_canvases.clear()
            self.map_canvases.clear()
            self.update_ui_state()
            self.lbl_status_state.setText(f"[OK] Nuevo proyecto creado: {new_proj.name}")

    def action_open_project(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self, "Abrir Proyecto PyGSN", "data", "Proyecto PyGSN (*.pygsn);;JSON (*.json);;Todos (*.*)"
        )
        if not fpath:
            return
        p = Path(fpath)
        try:
            loaded_proj = Project.load(p)
            self.project = loaded_proj
            self.current_project_file = p
            self.workspace.clear()
            self.platform_canvases.clear()
            self.map_canvases.clear()
            self.update_ui_state()
            self.lbl_status_state.setText(f"[OK] Proyecto cargado: {p.name}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Cargar", f"No se pudo cargar el proyecto: {str(e)}")

    def action_save_project(self) -> bool:
        if self.current_project_file:
            try:
                self.project.save(self.current_project_file)
                self.is_dirty = False
                self.lbl_status_state.setText(f"[OK] Guardado en: {self.current_project_file.name}")
                return True
            except Exception as e:
                QMessageBox.critical(self, "Error al Guardar", f"No se pudo guardar el archivo: {str(e)}")
                return False
        else:
            return self.action_save_project_as()

    def action_save_project_as(self) -> bool:
        fpath, _ = QFileDialog.getSaveFileName(
            self, "Guardar Proyecto Como...", "data/proyecto.pygsn", "Proyecto PyGSN (*.pygsn)"
        )
        if not fpath:
            return False
        p = Path(fpath)
        try:
            self.project.save(p)
            self.current_project_file = p
            self.is_dirty = False
            self.lbl_status_state.setText(f"[OK] Guardado en: {p.name}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error al Guardar", f"No se pudo guardar el archivo: {str(e)}")
            return False

    def action_project_properties(self):
        dlg = DialogProjectProperties(self.project, self)
        if dlg.exec():
            dlg.apply_to_project()
            self.is_dirty = True
            self.update_ui_state()

    def action_create_platform(self):
        if self.editing_target_type is not None:
            QMessageBox.warning(
                self, "Acción Bloqueada",
                f"No se puede crear una nueva plataforma mientras la sesión de edición de '{self.editing_platform_id}' está activa.\n"
                "Guarde o descarte la edición antes de crear otra plataforma."
            )
            return
        existing_ids = list(self.project.platforms.keys())
        dlg = DialogCreatePlatform(existing_ids=existing_ids, existing_count=len(self.project.platforms), parent=self)
        if dlg.exec():
            plat = dlg.get_platform()
            self.project.add_platform(plat, set_active=True)
            self.is_dirty = True
            self.on_project_changed()
            self.open_platform_tab(plat.id)
            self.lbl_status_state.setText(f"[OK] Plataforma '{plat.name}' ({plat.id}) creada.")

    def action_create_reference_system(self):
        """Abre el diálogo para crear un nuevo Sistema de Referencia Terrestre (SRT / e-frame)."""
        existing_ids = list(self.project.reference_systems.keys())
        dlg = DialogCreateReferenceSystem(
            existing_ids=existing_ids,
            existing_count=len(self.project.reference_systems),
            parent=self
        )
        if dlg.exec():
            rs = dlg.get_reference_system()
            self.project.add_reference_system(rs, set_active=rs.is_active)
            self.is_dirty = True
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Sistema de referencia terrestre '{rs.name}' ({rs.id}) creado.")

    def action_set_active_reference_system(self, rs_id: str):
        """Establece el Sistema de Referencia Terrestre activo del proyecto."""
        if self.project.set_active_reference_system(rs_id):
            self.is_dirty = True
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Sistema de referencia '{rs_id}' seleccionado.")

    def action_reference_system_properties(self, rs_id: str):
        """Abre el diálogo de propiedades de un Sistema de Referencia Terrestre."""
        rs = self.project.get_reference_system(rs_id)
        if not rs:
            return
        dlg = DialogReferenceSystemProperties(rs, self)
        if dlg.exec():
            if rs.is_active:
                self.project.set_active_reference_system(rs.id)
            self.is_dirty = True
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Propiedades de '{rs.name}' ({rs.id}) actualizadas.")

    def action_delete_reference_system(self, rs_id: str):
        """Elimina un Sistema de Referencia Terrestre del proyecto."""
        rs = self.project.get_reference_system(rs_id)
        if not rs:
            return
        res = QMessageBox.question(
            self, "Confirmar Eliminación",
            f"¿Está seguro de eliminar el sistema de referencia terrestre '{rs.id}' ({rs.name})?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res == QMessageBox.Yes:
            self.project.remove_reference_system(rs_id)
            self.is_dirty = True
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Sistema de referencia '{rs_id}' eliminado.")

    def action_import_calibration(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self, "Importar Calibración", "data", "Texto (*.txt);;Todos (*.*)"
        )
        if not fpath:
            return
        p = Path(fpath)
        try:
            plat = Platform.from_txt(p.read_text(encoding="utf-8"))
            self.project.add_platform(plat, set_active=True)
            self.on_project_changed()
            self.open_platform_tab(plat.id)
            self.lbl_status_state.setText(f"[OK] Plataforma importada desde {p.name}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Importar", f"No se pudo parsear el archivo: {str(e)}")

    def action_export_calibration(self):
        plat = self.project.platform
        if not plat:
            QMessageBox.warning(self, "Aviso", "No hay plataforma activa para exportar.")
            return
        fpath, _ = QFileDialog.getSaveFileName(
            self, "Exportar Calibración", f"data/{plat.id}_calibracion.txt", "Texto (*.txt)"
        )
        if not fpath:
            return
        try:
            Path(fpath).write_text(plat.to_txt(), encoding="utf-8")
            self.lbl_status_state.setText(f"[OK] Calibración guardada en {Path(fpath).name}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo guardar el archivo: {str(e)}")

    def action_open_georeferencing_solver(self):
        """Abre el diálogo técnico e interactivo de Georreferenciación Multipunto (b-frame ↔ e-frame)."""
        dlg = DialogGeoreferencingSolver(self.project, self)
        dlg.solution_applied.connect(self.on_project_changed)
        dlg.exec()

    def action_open_attribute_table(self, plat_id: Optional[str] = None):
        """Abre la Tabla de Atributos interactiva (estilo QGIS F6) para la plataforma indicada."""
        if not plat_id:
            plat = self.project.get_active_platform()
            if not plat and self.project.platforms:
                plat = next(iter(self.project.platforms.values()))
            if not plat:
                QMessageBox.information(
                    self,
                    "Tabla de Atributos",
                    "No hay ninguna plataforma definida en el proyecto actual."
                )
                return
            plat_id = plat.id

        plat = self.project.platforms.get(plat_id)
        if not plat:
            QMessageBox.warning(self, "Aviso", f"No se encontró la plataforma '{plat_id}'.")
            return

        dlg = DialogAttributeTable(platform=plat, parent=self)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def action_open_active_attribute_table(self):
        """Abre la Tabla de Atributos (F6) para la plataforma activa actual."""
        self.action_open_attribute_table(self.project.active_platform_id)

    def action_solve_georef(self):
        self.open_solver_tab()
        if self.panel_georef:
            self.panel_georef.solve()

    def action_load_observations(self):
        self.open_solver_tab()
        if self.panel_georef:
            self.panel_georef.load_observations_dialog()

    def action_show_residuals(self):
        self.open_solver_tab()
        self.lbl_status_state.setText("[Análisis] Inspeccionando residuales GNSS vs INS")

    def action_show_diagnostics(self):
        sol = self.panel_georef.last_solution if self.panel_georef else None
        dlg = DialogDiagnostics(solution=sol, parent=self)
        dlg.exec()

    def action_export_report(self):
        if self.panel_georef:
            self.panel_georef.export_report_dialog()
        else:
            QMessageBox.warning(self, "Aviso", "No hay informe calculado en la sesión.")

    def toggle_fullscreen(self):
        """Conmuta entre modo pantalla completa pura y ventana maximizada estándar."""
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def action_about(self):
        QMessageBox.information(
            self, "Acerca de PyGSN",
            "PyGSN - Georreferenciación de Sensores y Navegación v2.0\n"
            "Arquitectura de Ingeniería en PySide6 (Qt) con computación NumPy/SciPy float64.\n\n"
            "Licencia: GNU General Public License v3 (GPLv3)"
        )

    def closeEvent(self, event):
        """Gestiona el cierre ordenado de la aplicación preguntando si hay cambios pendientes."""
        if self.is_dirty:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Salir")
            msg_box.setText("Existen modificaciones sin guardar en el proyecto actual.\n¿Desea guardar los cambios antes de salir?")
            set_window_titlebar_light(msg_box)
            btn_save = msg_box.addButton("Guardar", QMessageBox.AcceptRole)
            btn_discard = msg_box.addButton("Salir sin guardar", QMessageBox.DestructiveRole)
            btn_cancel = msg_box.addButton("Cancelar", QMessageBox.RejectRole)
            msg_box.setDefaultButton(btn_save)
            msg_box.exec()
            clicked = msg_box.clickedButton()

            if clicked == btn_save:
                saved = self.action_save_project()
                if saved:
                    event.accept()
                else:
                    event.ignore()
            elif clicked == btn_discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()



class PyGSNApp:
    """Clase de inicialización y ejecución de la aplicación gráfica."""

    def __init__(self):
        # Configurar identificador de proceso en Windows para que la barra de tareas
        # muestre el icono del programa en lugar del genérico de python.exe
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("upv.pygsn.suite.v2")
        except Exception:
            pass

        # Requerimiento A.L: Punto decimal estrictamente programático estándar C en toda la suite
        QLocale.setDefault(QLocale.c())
        self.app = QApplication(sys.argv)

        # Establecer icono global de la suite
        icons_dir = Path(__file__).resolve().parent.parent / "icons"
        icon_path = icons_dir / "Logo.ico"
        if not icon_path.exists():
            icon_path = icons_dir / "Logo.svg"
        if icon_path.exists():
            self.app.setWindowIcon(QIcon(str(icon_path)))

        apply_pyside_theme(self.app)
        self.window = PyGSNMainWindow()

    def run(self):
        self.window.showMaximized()
        sys.exit(self.app.exec())

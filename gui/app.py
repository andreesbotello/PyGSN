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
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QToolBar, QToolButton,
    QStatusBar, QLabel, QFileDialog, QMessageBox, QWidget, QDockWidget,
    QDoubleSpinBox, QComboBox, QAbstractSpinBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence

from core.models import Platform
from core.project import Project
from core.georeferencing import create_reference_platform

from gui.theme import apply_pyside_theme, set_window_titlebar_light
from gui.dock_hierarchy import HierarchyDock
from gui.dock_console import ConsoleDock
from gui.canvas_ortho import OrthoCADWidget
from gui.panel_georeferencing import GeoreferencingWidget
from gui.panel_report import ReportViewerWidget
from gui.panel_kinematics import KinematicsWidget
from gui.dialogs import (
    DialogNewProject, DialogProjectProperties, DialogCreatePlatform,
    DialogAddSensor, DialogChassisActions, DialogDiagnostics
)


class PyGSNMainWindow(QMainWindow):
    """Ventana principal de la Suite PyGSN."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project: Project = Project(name="Proyecto sin título", platforms={})
        self.current_project_file: Optional[Path] = None

        self.platform_canvases: Dict[str, OrthoCADWidget] = {}
        self.panel_georef: Optional[GeoreferencingWidget] = None
        self.panel_report: Optional[ReportViewerWidget] = None
        self.panel_kinematics: Optional[KinematicsWidget] = None

        # Modos de edición de barra de herramientas (Mover por defecto)
        self.platform_edit_mode: bool = False
        self.sensor_edit_mode: bool = False
        self.active_platform_tool: str = "Mover"
        self.active_sensor_tool: str = "Seleccionar"

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
        self.setCentralWidget(self.workspace)

    def _init_docks(self):
        # Dock Izquierdo: Capas / Jerarquía
        self.hierarchy_dock = HierarchyDock(
            get_project=lambda: self.project,
            on_project_changed=self.on_project_changed,
            parent=self
        )
        self.hierarchy_dock.platform_activated.connect(self.open_platform_tab)
        # Nota: Clic en chasis activa la plataforma directamente sin ventana modal emergente
        self.hierarchy_dock.center_origin_requested.connect(self.center_platform_origin)
        self.hierarchy_dock.center_centroid_requested.connect(self.center_platform_centroid)
        self.hierarchy_dock.add_sensor_requested.connect(self.show_add_sensor_dialog)
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
        self.console_dock.chassis_modified.connect(self.on_project_changed)
        self.console_dock.platform_created.connect(self.open_platform_tab)
        self.addDockWidget(Qt.RightDockWidgetArea, self.console_dock)
        self.console_dock.hide()

    def _init_menu_bar(self):
        mb = self.menuBar()

        # 1. Menú Proyecto
        menu_proj = mb.addMenu("&Proyecto")
        menu_proj.addAction("Nuevo Proyecto...", self.action_new_project, QKeySequence.New)
        menu_proj.addAction("Abrir Proyecto (.pygsn)...", self.action_open_project, QKeySequence.Open)
        menu_proj.addSeparator()
        menu_proj.addAction("Guardar", self.action_save_project, QKeySequence.Save)
        menu_proj.addAction("Guardar Como...", self.action_save_project_as)
        menu_proj.addSeparator()
        menu_proj.addAction("Propiedades del Proyecto...", self.action_project_properties)
        menu_proj.addAction("Exportar Informe TXT...", self.action_export_report)
        menu_proj.addSeparator()
        menu_proj.addAction("Salir de PyGSN", self.close, QKeySequence.Quit)

        # 2. Menú Plataforma
        menu_plat = mb.addMenu("&Plataforma")
        menu_plat.addAction("Crear Nueva Plataforma...", self.action_create_platform)
        menu_plat.addAction(
            "Abrir Plataforma en Workspace",
            lambda: self.open_platform_tab(self.project.active_platform_id) if self.project.active_platform_id else None
        )
        menu_plat.addSeparator()
        menu_plat.addAction(
            "Añadir Sensor al Rig...",
            lambda: self.show_add_sensor_dialog(self.project.active_platform_id) if self.project.active_platform_id else None
        )
        menu_plat.addSeparator()
        menu_plat.addAction("Importar Calibración (.txt)...", self.action_import_calibration)
        menu_plat.addAction("Exportar Calibración (.txt)...", self.action_export_calibration)

        # 3. Menú Procesamiento
        menu_proc = mb.addMenu("P&rocesamiento")
        menu_proc.addAction("Resolver Georreferenciación & Actitud (SVD)", self.action_solve_georef)
        menu_proc.addAction("Simulación Cinemática de Trayectorias", self.open_kinematics_tab)
        menu_proc.addSeparator()
        menu_proc.addAction("Cargar Observaciones de Campo (.txt)...", self.action_load_observations)

        # 4. Menú Análisis
        menu_ana = mb.addMenu("&Análisis")
        menu_ana.addAction("Inspeccionar Residuales GNSS vs INS", self.action_show_residuals)
        menu_ana.addAction("Diagnóstico SVD y Auditoría de Matrices DCM", self.action_show_diagnostics)

        # 5. Menú Vista
        menu_vis = mb.addMenu("Vista")
        menu_vis.addAction("Mostrar/Ocultar Panel de Capas", lambda: self.hierarchy_dock.setVisible(not self.hierarchy_dock.isVisible()))
        menu_vis.addAction("Mostrar/Ocultar Consola CLI", self.toggle_console)
        menu_vis.addSeparator()
        menu_vis.addAction("Centrar Vista al Origen [0, 0, 0]", lambda: self.center_platform_origin(self.project.active_platform_id))
        menu_vis.addAction("Centrar Vista al Centroide", lambda: self.center_platform_centroid(self.project.active_platform_id))
        menu_vis.addSeparator()
        menu_vis.addAction("Pantalla Completa", self.toggle_fullscreen, QKeySequence("F11"))

        # 6. Menú Ayuda
        menu_help = mb.addMenu("A&yuda")
        menu_help.addAction("Acerca de PyGSN", self.action_about)

    def _init_tool_bar(self):
        tb = QToolBar("Herramientas Rápidas")
        tb.setMovable(False)
        self.addToolBar(tb)

        # SECCIÓN 1: PLATAFORMA
        lbl_plat = QLabel("Plataforma: ")
        lbl_plat.setStyleSheet("color: #0077b6; font-weight: bold;")
        tb.addWidget(lbl_plat)

        btn_add_plat = QToolButton()
        btn_add_plat.setText("+ Plataforma")
        btn_add_plat.clicked.connect(self.action_create_platform)
        tb.addWidget(btn_add_plat)

        self.btn_plat_edit = QToolButton()
        self.btn_plat_edit.setText("Editar")
        self.btn_plat_edit.setCheckable(True)
        self.btn_plat_edit.toggled.connect(self._on_toggle_platform_edit)
        tb.addWidget(self.btn_plat_edit)

        self.tool_plat_move = QToolButton()
        self.tool_plat_move.setText("Mover")
        self.tool_plat_move.setCheckable(True)
        self.tool_plat_move.setChecked(True)
        self.tool_plat_move.setEnabled(False)
        self.tool_plat_move.clicked.connect(lambda: self._select_platform_tool("Mover"))
        tb.addWidget(self.tool_plat_move)

        self.tool_plat_draw = QToolButton()
        self.tool_plat_draw.setText("Dibujar Chasis")
        self.tool_plat_draw.setCheckable(True)
        self.tool_plat_draw.setEnabled(False)
        self.tool_plat_draw.clicked.connect(lambda: self._select_platform_tool("Dibujar"))
        tb.addWidget(self.tool_plat_draw)

        self.tool_plat_rot = QToolButton()
        self.tool_plat_rot.setText("Rotar")
        self.tool_plat_rot.setCheckable(True)
        self.tool_plat_rot.setEnabled(False)
        self.tool_plat_rot.clicked.connect(lambda: self._select_platform_tool("Rotar"))
        tb.addWidget(self.tool_plat_rot)

        self.tool_plat_scale = QToolButton()
        self.tool_plat_scale.setText("Escalar")
        self.tool_plat_scale.setCheckable(True)
        self.tool_plat_scale.setEnabled(False)
        self.tool_plat_scale.clicked.connect(lambda: self._select_platform_tool("Escalar"))
        tb.addWidget(self.tool_plat_scale)

        self.tool_plat_verts = QToolButton()
        self.tool_plat_verts.setText("Vértices")
        self.tool_plat_verts.setCheckable(True)
        self.tool_plat_verts.setEnabled(False)
        self.tool_plat_verts.clicked.connect(lambda: self._select_platform_tool("Vértices"))
        tb.addWidget(self.tool_plat_verts)

        tb.addSeparator()

        # SECCIÓN 2: SENSORES
        lbl_sens = QLabel("Sensores: ")
        lbl_sens.setStyleSheet("color: #b45309; font-weight: bold;")
        tb.addWidget(lbl_sens)

        btn_add_sens = QToolButton()
        btn_add_sens.setText("+ Sensor")
        btn_add_sens.clicked.connect(lambda: self.show_add_sensor_dialog(self.project.active_platform_id))
        tb.addWidget(btn_add_sens)

        self.btn_sens_edit = QToolButton()
        self.btn_sens_edit.setText("Editar")
        self.btn_sens_edit.setCheckable(True)
        self.btn_sens_edit.toggled.connect(self._on_toggle_sensor_edit)
        tb.addWidget(self.btn_sens_edit)

        self.tool_sens_move = QToolButton()
        self.tool_sens_move.setText("Mover Lever-arm")
        self.tool_sens_move.setEnabled(False)
        tb.addWidget(self.tool_sens_move)

        self.tool_sens_rot = QToolButton()
        self.tool_sens_rot.setText("Rotar Boresight")
        self.tool_sens_rot.setEnabled(False)
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
            "Mover": self.tool_plat_move,
            "Dibujar": self.tool_plat_draw,
            "Rotar": self.tool_plat_rot,
            "Escalar": self.tool_plat_scale,
            "Vértices": self.tool_plat_verts
        }
        for name, btn in tools.items():
            btn.setChecked(name == tool_name)
        for widget in self.platform_canvases.values():
            widget.set_active_tool(tool_name)
        self.lbl_status_state.setText(f"[Herramienta Plataforma: {tool_name}]")

    def _on_toggle_platform_edit(self, checked: bool):
        self.platform_edit_mode = checked
        self.btn_plat_edit.setText("Editar [ON]" if checked else "Editar")
        self.tool_plat_move.setEnabled(checked)
        self.tool_plat_draw.setEnabled(checked)
        self.tool_plat_rot.setEnabled(checked)
        self.tool_plat_scale.setEnabled(checked)
        self.tool_plat_verts.setEnabled(checked)
        if checked:
            self._select_platform_tool("Mover")
        else:
            self._select_platform_tool("Mover")
        self.lbl_status_state.setText("[Modo Edición Plataforma ACTIVO]" if checked else "[Listo]")

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

    def _on_toggle_sensor_edit(self, checked: bool):
        self.sensor_edit_mode = checked
        self.btn_sens_edit.setText("Editar [ON]" if checked else "Editar")
        self.tool_sens_move.setEnabled(checked)
        self.tool_sens_rot.setEnabled(checked)
        self.lbl_status_state.setText("[Modo Edición Sensores ACTIVO]" if checked else "[Listo]")

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
                self.workspace.setCurrentIndex(i)
                self.lbl_status_state.setText(f"[Workspace Activo: {plat.name}]")
                return

        widget = OrthoCADWidget(plat)
        widget.set_active_tool(self.active_platform_tool)
        widget.set_snap_step_m(self.get_snap_step_m())
        widget.chassis_updated.connect(self.update_ui_state)
        self.platform_canvases[plat_id] = widget
        idx = self.workspace.addTab(widget, tab_title)
        self.workspace.setCurrentIndex(idx)
        self.lbl_status_state.setText(f"[Workspace Activo: {plat.name}]")

    def _on_tab_close_requested(self, index: int):
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
        if not plat_id:
            plat_id = self.project.active_platform_id
        if not plat_id:
            QMessageBox.warning(self, "Aviso", "Primero debe crear o seleccionar una plataforma.")
            return
        plat = self.project.get_platform(plat_id)
        if not plat:
            return
        dlg = DialogAddSensor(plat.name, self)
        if dlg.exec():
            sens = dlg.get_sensor()
            plat.add_sensor(sens)
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Sensor {sens.code} añadido a {plat.name}")

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
            self.update_ui_state()
            self.lbl_status_state.setText(f"[OK] Proyecto cargado: {p.name}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Cargar", f"No se pudo cargar el proyecto: {str(e)}")

    def action_save_project(self):
        if self.current_project_file:
            try:
                self.project.save(self.current_project_file)
                self.lbl_status_state.setText(f"[OK] Guardado en: {self.current_project_file.name}")
            except Exception as e:
                QMessageBox.critical(self, "Error al Guardar", f"No se pudo guardar el archivo: {str(e)}")
        else:
            self.action_save_project_as()

    def action_save_project_as(self):
        fpath, _ = QFileDialog.getSaveFileName(
            self, "Guardar Proyecto Como...", "data/proyecto.pygsn", "Proyecto PyGSN (*.pygsn)"
        )
        if not fpath:
            return
        p = Path(fpath)
        try:
            self.project.save(p)
            self.current_project_file = p
            self.lbl_status_state.setText(f"[OK] Guardado en: {p.name}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Guardar", f"No se pudo guardar el archivo: {str(e)}")

    def action_project_properties(self):
        dlg = DialogProjectProperties(self.project, self)
        if dlg.exec():
            dlg.apply_to_project()
            self.update_ui_state()

    def action_create_platform(self):
        dlg = DialogCreatePlatform(len(self.project.platforms), self)
        if dlg.exec():
            plat = dlg.get_platform()
            self.project.add_platform(plat, set_active=True)
            self.on_project_changed()
            self.lbl_status_state.setText(f"[OK] Plataforma '{plat.name}' creada.")

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

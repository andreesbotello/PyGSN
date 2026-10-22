"""
PyGSN - GUI Georeferencing Solver Dialog (PySide6 / Qt)
======================================================
Diálogo técnico interactivo para georreferenciación y determinación de actitud:
- Conexión flexible y desacoplada entre cualquier Plataforma (b-frame) y cualquier SRT (e-frame).
- Flujo secuencial y modular estilo QGIS:
  1. Marcos de Referencia (Plataforma b-frame y Sistema Terrestre e-frame).
  2. Observables de Receptores GNSS (fichero .txt o edición interactiva en tabla).
  3. Fuente de Orientación / Actitud (Constelación GNSS por SVD o Unidad Inercial INS).
- Entrada de actitud INS tanto por fichero como manual directa (Roll, Pitch, Yaw o α, β, γ).
- Comparación de consistencia angular (GNSS vs INS) y propagación cinemática tridimensional.
- Auditoría matemática rigurosa (det(C)=+1, residuos métricos por antena).
- Generación y exportación de informes técnicos de ingeniería.
"""

from typing import Optional, Dict, Any, List, Tuple
import numpy as np

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QPushButton, QLabel, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTabWidget, QTextEdit, QFileDialog, QMessageBox,
    QCheckBox, QWidget, QSplitter, QRadioButton, QButtonGroup,
    QLineEdit, QDoubleSpinBox, QFrame, QToolButton
)
from PySide6.QtCore import Qt, QLocale, Signal

from core.models import (
    Platform, Sensor, SensorType, ReferenceSystem, SensorObservation,
    parse_dms_or_deg, SensorGeoref, PlatformPose
)
from core.project import Project
from core.geodesy import rad_to_dms, dms_to_rad, utm_projection
from core.georeferencing import solve_multisensor_georeferencing, GeoreferencingSolution
from core.reporting import generate_georeferencing_report
from gui.dialogs import BaseDialog


def _read_text_file_robust(fpath: str) -> str:
    """Lee un fichero de texto probando codificaciones comunes (UTF-8, UTF-8-BOM, CP1252, Latin-1)."""
    with open(fpath, "rb") as f:
        raw_bytes = f.read()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


class DialogGeoreferencingSolver(BaseDialog):
    """
    Diálogo de ingeniería para la estimación de pose y propagación cinemática
    vinculando un b-frame arbitrario con un e-frame de libre elección.
    """
    solution_applied = Signal()

    def __init__(self, project: Project, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.last_solution: Optional[GeoreferencingSolution] = None
        self.last_report: str = ""
        self.ins_convention: str = "RPY"  # "RPY" (Roll, Pitch, Yaw) o "ABG" (Alpha, Beta, Gamma)

        self.setWindowTitle("Georreferenciación y Pose de Plataforma")
        self.resize(1140, 720)
        self.setMinimumSize(960, 600)
        self.setModal(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(8)

        # Encabezado técnico
        header = QLabel("Módulo de Georreferenciación Multipunto y Actitud (b-frame ↔ e-frame)")
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #0077b6; padding-bottom: 2px;")
        main_layout.addWidget(header)

        # Navegación principal en 2 Pestañas secuenciales a ancho completo
        self.main_tabs = QTabWidget()
        self.main_tabs.setStyleSheet("QTabBar::tab { font-weight: bold; padding: 6px 18px; font-size: 11px; }")

        # =====================================================================
        # PESTAÑA 1: Parámetros y Observables de Entrada (1 -> 2 -> 3)
        # =====================================================================
        # =====================================================================
        # PESTAÑA 1: Parámetros y Observables de Entrada (2 Paneles Sup. + GNSS Inf.)
        # =====================================================================
        panel_left = QWidget()
        vbox_left = QVBoxLayout(panel_left)
        vbox_left.setContentsMargins(10, 10, 10, 10)
        vbox_left.setSpacing(8)

        # Fila Superior: 2 Paneles Paralelos (Izquierdo: Marcos/Método, Derecho: INS)
        hbox_top = QHBoxLayout()
        hbox_top.setSpacing(10)

        # ---------------------------------------------------------------------
        # 1. Marcos de Referencia y Método (Panel Izquierdo)
        # ---------------------------------------------------------------------
        grp_frames = QGroupBox("1. Marcos de Referencia y Método")
        vbox_frames = QVBoxLayout(grp_frames)
        vbox_frames.setContentsMargins(10, 8, 10, 8)
        vbox_frames.setSpacing(6)

        form_frames = QFormLayout()
        form_frames.setContentsMargins(0, 0, 0, 0)
        form_frames.setVerticalSpacing(6)

        self.combo_plat = QComboBox()
        self.combo_plat.currentIndexChanged.connect(self._on_platform_changed)
        form_frames.addRow("Plataforma (b-frame):", self.combo_plat)

        self.combo_srt = QComboBox()
        self.combo_srt.currentIndexChanged.connect(self._on_srt_changed)
        form_frames.addRow("Sistema Terrestre (e-frame):", self.combo_srt)

        self.combo_method = QComboBox()
        self.combo_method.addItems([
            "Constelación GNSS (Ajuste rígido SVD de Kabsch / Horn)",
            "Sensor Inercial (Unidad INS / IMU)",
            "Ambos Métodos con Auditoría Cruzada (SVD + INS)"
        ])
        self.combo_method.currentIndexChanged.connect(self._on_attitude_source_changed)
        form_frames.addRow("Método de Orientación:", self.combo_method)
        vbox_frames.addLayout(form_frames)

        self.lbl_method_info = QLabel(
            "Orientación calculada por descomposición en valores singulares (SVD) a partir de las coordenadas observadas en las antenas GNSS (mínimo 3)."
        )
        self.lbl_method_info.setWordWrap(True)
        self.lbl_method_info.setStyleSheet("color: #475569; font-size: 11px; font-style: italic; padding-top: 4px;")
        vbox_frames.addWidget(self.lbl_method_info)
        vbox_frames.addStretch()

        hbox_top.addWidget(grp_frames, 1)

        # ---------------------------------------------------------------------
        # 2. Orientación Inercial (Panel Derecho)
        # ---------------------------------------------------------------------
        grp_ins = QGroupBox("2. Orientación Inercial")
        vbox_ins = QVBoxLayout(grp_ins)
        vbox_ins.setContentsMargins(10, 8, 10, 8)
        vbox_ins.setSpacing(6)

        form_ins_top = QFormLayout()
        form_ins_top.setContentsMargins(0, 0, 0, 0)
        form_ins_top.setVerticalSpacing(4)

        self.combo_ins = QComboBox()
        self.combo_ins.currentIndexChanged.connect(self._on_ins_sensor_selected)
        form_ins_top.addRow("Sensor INS:", self.combo_ins)

        # Modo de Entrada
        hbox_ins_mode = QHBoxLayout()
        self.radio_ins_manual = QRadioButton("Entrada Manual")
        self.radio_ins_file = QRadioButton("Desde Fichero")
        self.radio_ins_manual.setChecked(True)
        self.bg_ins_mode = QButtonGroup(self)
        self.bg_ins_mode.addButton(self.radio_ins_manual, 0)
        self.bg_ins_mode.addButton(self.radio_ins_file, 1)
        self.bg_ins_mode.idToggled.connect(self._on_ins_mode_changed)
        hbox_ins_mode.addWidget(self.radio_ins_manual)
        hbox_ins_mode.addWidget(self.radio_ins_file)
        hbox_ins_mode.addStretch()
        form_ins_top.addRow("Modo:", hbox_ins_mode)
        vbox_ins.addLayout(form_ins_top)

        # Fichero INS (si 'Desde Fichero' está activo, va arriba para actualizar los campos inferiores)
        self.widget_ins_file = QWidget()
        vbox_f_ins = QVBoxLayout(self.widget_ins_file)
        vbox_f_ins.setContentsMargins(0, 2, 0, 2)
        vbox_f_ins.setSpacing(2)

        hbox_ins_f = QHBoxLayout()
        self.line_ins_path = QLineEdit()
        self.line_ins_path.setReadOnly(True)
        self.line_ins_path.setPlaceholderText("Seleccionar fichero con actitud INS (.txt)...")
        hbox_ins_f.addWidget(self.line_ins_path, 1)

        self.btn_browse_ins = QToolButton()
        self.btn_browse_ins.setText("...")
        self.btn_browse_ins.setToolTip("Examinar fichero INS en disco...")
        self.btn_browse_ins.setFixedSize(30, 26)
        self.btn_browse_ins.setStyleSheet(
            "QToolButton { background-color: #f1f5f9; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 3px; font-weight: bold; font-size: 13px; } "
            "QToolButton:hover { background-color: #e2e8f0; border-color: #0077b6; color: #0077b6; }"
        )
        self.btn_browse_ins.clicked.connect(self._on_browse_ins_file)
        hbox_ins_f.addWidget(self.btn_browse_ins)

        self.btn_clear_ins = QToolButton()
        self.btn_clear_ins.setText("X")
        self.btn_clear_ins.setToolTip("Limpiar fichero INS")
        self.btn_clear_ins.setFixedSize(26, 26)
        self.btn_clear_ins.setStyleSheet(
            "QToolButton { background-color: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; border-radius: 3px; font-size: 11px; font-weight: bold; padding: 0px; margin: 0px; } "
            "QToolButton:hover { background-color: #fee2e2; color: #dc2626; border-color: #fca5a5; }"
        )
        self.btn_clear_ins.clicked.connect(self._on_clear_ins_file)
        hbox_ins_f.addWidget(self.btn_clear_ins)
        vbox_f_ins.addLayout(hbox_ins_f)

        self.lbl_ins_file_status = QLabel("Sin fichero INS cargado.")
        self.lbl_ins_file_status.setStyleSheet("color: #64748b; font-size: 10px;")
        vbox_f_ins.addWidget(self.lbl_ins_file_status)
        self.widget_ins_file.setVisible(False)
        vbox_ins.addWidget(self.widget_ins_file)

        # Convención y Spinboxes de Actitud
        form_ins_spins = QFormLayout()
        form_ins_spins.setContentsMargins(0, 0, 0, 0)
        form_ins_spins.setVerticalSpacing(4)

        self.combo_ins_convention = QComboBox()
        self.combo_ins_convention.addItems([
            "(Roll, Pitch, Yaw) de Navegación",
            "(Alpha, Beta, Gamma) de Calibración Pasiva"
        ])
        self.combo_ins_convention.currentIndexChanged.connect(self._on_ins_convention_changed)
        form_ins_spins.addRow("Convención:", self.combo_ins_convention)

        self.lbl_spin1 = QLabel("Roll:")
        self.spin_roll = QDoubleSpinBox()
        self.spin_roll.setRange(-360.0, 360.0)
        self.spin_roll.setDecimals(6)
        self.spin_roll.setSuffix("°")
        self.spin_roll.setLocale(QLocale.c())
        form_ins_spins.addRow(self.lbl_spin1, self.spin_roll)

        self.lbl_spin2 = QLabel("Pitch:")
        self.spin_pitch = QDoubleSpinBox()
        self.spin_pitch.setRange(-360.0, 360.0)
        self.spin_pitch.setDecimals(6)
        self.spin_pitch.setSuffix("°")
        self.spin_pitch.setLocale(QLocale.c())
        form_ins_spins.addRow(self.lbl_spin2, self.spin_pitch)

        self.lbl_spin3 = QLabel("Yaw:")
        self.spin_yaw = QDoubleSpinBox()
        self.spin_yaw.setRange(-360.0, 360.0)
        self.spin_yaw.setDecimals(6)
        self.spin_yaw.setSuffix("°")
        self.spin_yaw.setLocale(QLocale.c())
        form_ins_spins.addRow(self.lbl_spin3, self.spin_yaw)

        vbox_ins.addLayout(form_ins_spins)
        vbox_ins.addStretch()

        hbox_top.addWidget(grp_ins, 1)
        vbox_left.addLayout(hbox_top)

        # ---------------------------------------------------------------------
        # 3. Observables GNSS
        # ---------------------------------------------------------------------
        grp_gnss = QGroupBox("3. Observables GNSS")
        vbox_gnss = QVBoxLayout(grp_gnss)
        vbox_gnss.setContentsMargins(10, 8, 10, 8)
        vbox_gnss.setSpacing(6)

        # Fila de selección de fichero (estilo QGIS)
        hbox_gnss_file = QHBoxLayout()
        hbox_gnss_file.setSpacing(4)
        lbl_gnss_f = QLabel("Fichero GNSS:")
        lbl_gnss_f.setFixedWidth(82)
        hbox_gnss_file.addWidget(lbl_gnss_f)

        self.line_gnss_path = QLineEdit()
        self.line_gnss_path.setReadOnly(True)
        self.line_gnss_path.setPlaceholderText("Seleccionar fichero de coordenadas GNSS (.txt)...")
        hbox_gnss_file.addWidget(self.line_gnss_path, 1)

        self.btn_browse_gnss = QToolButton()
        self.btn_browse_gnss.setText("...")
        self.btn_browse_gnss.setToolTip("Examinar fichero de coordenadas GNSS en disco...")
        self.btn_browse_gnss.setFixedSize(30, 26)
        self.btn_browse_gnss.setStyleSheet(
            "QToolButton { background-color: #f1f5f9; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 3px; font-weight: bold; font-size: 13px; } "
            "QToolButton:hover { background-color: #e2e8f0; border-color: #0077b6; color: #0077b6; }"
        )
        self.btn_browse_gnss.clicked.connect(self._on_browse_gnss_file)
        hbox_gnss_file.addWidget(self.btn_browse_gnss)

        self.btn_clear_gnss = QToolButton()
        self.btn_clear_gnss.setText("X")
        self.btn_clear_gnss.setToolTip("Limpiar fichero y coordenadas cargadas")
        self.btn_clear_gnss.setFixedSize(26, 26)
        self.btn_clear_gnss.setStyleSheet(
            "QToolButton { background-color: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; border-radius: 3px; font-size: 11px; font-weight: bold; padding: 0px; margin: 0px; } "
            "QToolButton:hover { background-color: #fee2e2; color: #dc2626; border-color: #fca5a5; }"
        )
        self.btn_clear_gnss.clicked.connect(self._on_clear_gnss_file)
        hbox_gnss_file.addWidget(self.btn_clear_gnss)
        vbox_gnss.addLayout(hbox_gnss_file)

        # Tabla interactiva de antenas GNSS (ancho completo, verticalHeader oculto)
        self.table_antennas = QTableWidget(0, 6)
        self.table_antennas.setHorizontalHeaderLabels([
            "Usar", "Sensor", "Lever-Arm [X, Y, Z] (m)", "Latitud", "Longitud", "h Elip (m)"
        ])
        self.table_antennas.verticalHeader().setVisible(False)
        self.table_antennas.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_antennas.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_antennas.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_antennas.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_antennas.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table_antennas.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table_antennas.setAlternatingRowColors(True)
        self.table_antennas.itemChanged.connect(self._on_antenna_cell_changed)
        vbox_gnss.addWidget(self.table_antennas, 1)

        self.lbl_gnss_status = QLabel("Sin coordenadas observadas.")
        self.lbl_gnss_status.setStyleSheet("color: #64748b; font-size: 11px;")
        vbox_gnss.addWidget(self.lbl_gnss_status)

        vbox_left.addWidget(grp_gnss, 1)

        # Botón de Cálculo Principal (sin flecha)
        self.btn_solve = QPushButton("Calcular Solución")
        self.btn_solve.setFixedHeight(36)
        self.btn_solve.setStyleSheet(
            "QPushButton { background-color: #0077b6; color: white; font-weight: bold; font-size: 12px; border-radius: 4px; } "
            "QPushButton:hover { background-color: #0096c7; }"
        )
        self.btn_solve.clicked.connect(self.solve)
        vbox_left.addWidget(self.btn_solve)

        self.main_tabs.addTab(panel_left, "1. Parámetros y Observables")

        # =====================================================================
        # PESTAÑA 2: Resultados, Pose Propagada y Auditoría
        # =====================================================================
        panel_right = QWidget()
        vbox_right = QVBoxLayout(panel_right)
        vbox_right.setContentsMargins(8, 8, 8, 8)
        vbox_right.setSpacing(6)

        self.tabs_results = QTabWidget()
        vbox_right.addWidget(self.tabs_results, 1)

        # Pestaña 2.1: Pose de Plataforma y Coordenadas Propagadas
        tab_pose = QWidget()
        vbox_pose = QVBoxLayout(tab_pose)
        vbox_pose.setContentsMargins(6, 6, 6, 6)
        vbox_pose.setSpacing(6)

        # Tarjeta resumen de PLA
        self.grp_pla_summary = QGroupBox("Pose del Centro de Referencia (PLA)")
        vbox_pla = QVBoxLayout(self.grp_pla_summary)
        vbox_pla.setContentsMargins(8, 6, 8, 6)

        self.lbl_pla_coords = QLabel("Coordenadas Geodésicas: Pendiente de cálculo.")
        self.lbl_pla_coords.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px; color: #0f172a;")
        vbox_pla.addWidget(self.lbl_pla_coords)

        self.lbl_pla_attitude = QLabel("Actitud de Plataforma: Pendiente de cálculo.")
        self.lbl_pla_attitude.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px; color: #b45309; font-weight: bold;")
        vbox_pla.addWidget(self.lbl_pla_attitude)

        self.lbl_pla_utm = QLabel("Proyección UTM: Pendiente de cálculo.")
        self.lbl_pla_utm.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px; color: #0284c7;")
        vbox_pla.addWidget(self.lbl_pla_utm)
        vbox_pose.addWidget(self.grp_pla_summary)

        # Tabla de todos los sensores propagados
        lbl_tbl = QLabel("Coordenadas Propagadas a Todos los Sensores del Rig:")
        lbl_tbl.setStyleSheet("font-weight: 500; font-size: 11px; color: #334155;")
        vbox_pose.addWidget(lbl_tbl)

        self.table_propagated = QTableWidget(0, 11)
        self.table_propagated.setHorizontalHeaderLabels([
            "Sensor", "Tipo", "X ECEF (m)", "Y ECEF (m)", "Z ECEF (m)",
            "Latitud (DMS)", "Longitud (DMS)", "h Elip (m)", "Este UTM (m)", "Norte UTM (m)", "Cota H (m)"
        ])
        self.table_propagated.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_propagated.setAlternatingRowColors(True)
        vbox_pose.addWidget(self.table_propagated, 1)

        self.tabs_results.addTab(tab_pose, "Pose y Sensores")

        # Pestaña 2.2: Auditoría Matemática y Residuos
        tab_audit = QWidget()
        vbox_audit = QVBoxLayout(tab_audit)
        vbox_audit.setContentsMargins(6, 6, 6, 6)
        vbox_audit.setSpacing(6)

        self.text_audit = QTextEdit()
        self.text_audit.setReadOnly(True)
        self.text_audit.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px; background-color: #f8fafc;")
        vbox_audit.addWidget(self.text_audit, 1)

        self.tabs_results.addTab(tab_audit, "Auditoría y Residuos")

        # Pestaña 2.3: Informe Técnico Exportable
        tab_report = QWidget()
        vbox_rep = QVBoxLayout(tab_report)
        vbox_rep.setContentsMargins(6, 6, 6, 6)
        vbox_rep.setSpacing(6)

        self.text_report = QTextEdit()
        self.text_report.setReadOnly(True)
        self.text_report.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px; background-color: #ffffff;")
        vbox_rep.addWidget(self.text_report, 1)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        self.btn_export_rep = QPushButton("Exportar Informe...")
        self.btn_export_rep.clicked.connect(self._on_export_report)
        btn_bar.addWidget(self.btn_export_rep)
        vbox_rep.addLayout(btn_bar)

        self.tabs_results.addTab(tab_report, "Informe Técnico")

        self.main_tabs.addTab(panel_right, "2. Resultados y Auditoría")
        main_layout.addWidget(self.main_tabs, 1)

        # Barra inferior de acciones globales
        btn_action_box = QHBoxLayout()
        self.btn_back_to_params = QPushButton("← Volver a Parámetros")
        self.btn_back_to_params.setStyleSheet("padding: 5px 12px;")
        self.btn_back_to_params.clicked.connect(lambda: self.main_tabs.setCurrentIndex(0))
        btn_action_box.addWidget(self.btn_back_to_params)

        btn_action_box.addStretch()

        self.btn_apply = QPushButton("Aplicar al Proyecto")
        self.btn_apply.setFixedHeight(30)
        self.btn_apply.setEnabled(False)
        self.btn_apply.setStyleSheet(
            "QPushButton { background-color: #0284c7; color: white; font-weight: bold; padding: 5px 20px; border-radius: 4px; } "
            "QPushButton:hover { background-color: #0369a1; } "
            "QPushButton:disabled { background-color: #cbd5e1; color: #94a3b8; }"
        )
        self.btn_apply.clicked.connect(self._on_apply_to_project)
        btn_action_box.addWidget(self.btn_apply)

        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.reject)
        btn_action_box.addWidget(btn_close)
        main_layout.addLayout(btn_action_box)

        # Inicialización de combos
        self._populate_platforms_and_srts()

    # =========================================================================
    # Métodos de Carga y Población de Datos
    # =========================================================================

    def _populate_platforms_and_srts(self):
        """Puebla los desplegables con las entidades actuales del proyecto."""
        self.combo_plat.blockSignals(True)
        self.combo_srt.blockSignals(True)
        self.combo_plat.clear()
        self.combo_srt.clear()

        # Plataformas
        if self.project.platforms:
            for pid, p in self.project.platforms.items():
                self.combo_plat.addItem(f"{p.name} [{pid}]", pid)
        else:
            self.combo_plat.addItem("(No hay plataformas en el proyecto)", "")

        # Sistemas de Referencia Terrestres
        if self.project.reference_systems:
            for srt_id, srt in self.project.reference_systems.items():
                self.combo_srt.addItem(f"{srt.name} [{srt_id}]", srt_id)
        else:
            self.combo_srt.addItem("(No hay sistemas de referencia configurados)", "")

        self.combo_plat.blockSignals(False)
        self.combo_srt.blockSignals(False)

        self._on_platform_changed()
        self._on_srt_changed()

    def _get_current_platform(self) -> Optional[Platform]:
        pid = self.combo_plat.currentData()
        if pid and pid in self.project.platforms:
            return self.project.platforms[pid]
        return None

    def _get_current_srt(self) -> Optional[ReferenceSystem]:
        srt_id = self.combo_srt.currentData()
        if srt_id and srt_id in self.project.reference_systems:
            return self.project.reference_systems[srt_id]
        return None

    def _on_platform_changed(self):
        """Actualiza las tablas y listas de sensores al cambiar la plataforma seleccionada."""
        plat = self._get_current_platform()
        self.combo_ins.blockSignals(True)
        self.combo_ins.clear()

        if not plat:
            self.combo_ins.addItem("(Sin plataforma seleccionada)", "")
            self.combo_ins.blockSignals(False)
            self._populate_antennas()
            return

        # Sensores INS disponibles
        ins_count = 0
        for code, s in plat.sensors.items():
            if s.sensor_type == SensorType.INS or "INS" in code.upper() or "IMU" in code.upper():
                self.combo_ins.addItem(f"{s.name} [{code}]", code)
                ins_count += 1
        if ins_count == 0:
            self.combo_ins.addItem("(Sin sensor inercial detectado)", "")

        self.combo_ins.blockSignals(False)
        self._on_ins_sensor_selected()
        self._populate_antennas()

    def _on_srt_changed(self):
        """Actualiza el título de la tarjeta de resumen según el SRT seleccionado."""
        srt = self._get_current_srt()
        if srt:
            self.grp_pla_summary.setTitle(f"Pose Estimada del Centro de Referencia (PLA) en {srt.name} [{srt.id}]")
        else:
            self.grp_pla_summary.setTitle("Pose Estimada del Centro de Referencia (PLA)")

    def _populate_antennas(self):
        """Llena la tabla con las antenas GNSS de la plataforma actual."""
        plat = self._get_current_platform()
        self.table_antennas.blockSignals(True)
        self.table_antennas.setRowCount(0)

        if not plat:
            self.lbl_gnss_status.setText("Seleccione una plataforma para ver sus sensores.")
            self.table_antennas.blockSignals(False)
            return

        gnss_sensors = [s for s in plat.sensors.values() if s.sensor_type == SensorType.GNSS or "REC" in s.code.upper() or "GNSS" in s.code.upper()]
        self.table_antennas.setRowCount(len(gnss_sensors))

        for row, s in enumerate(gnss_sensors):
            chk = QCheckBox()
            has_coords = s.observation is not None and s.observation.has_geodetic
            chk.setChecked(has_coords)
            chk.stateChanged.connect(self._update_gnss_status)

            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self.table_antennas.setCellWidget(row, 0, chk_widget)

            # Col 1: Nombre y Código (no editable)
            item_name = QTableWidgetItem(f"{s.name} [{s.code}]")
            item_name.setData(Qt.UserRole, s.code)
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
            self.table_antennas.setItem(row, 1, item_name)

            # Col 2: Lever-Arm (no editable)
            arm = s.lever_arm_b
            item_arm = QTableWidgetItem(f"[{arm[0]:+6.3f}, {arm[1]:+6.3f}, {arm[2]:+6.3f}]")
            item_arm.setTextAlignment(Qt.AlignCenter)
            item_arm.setFlags(item_arm.flags() & ~Qt.ItemIsEditable)
            self.table_antennas.setItem(row, 2, item_arm)

            # Col 3, 4, 5: Latitud, Longitud, Altura (editables directamente por el usuario)
            if has_coords:
                lat_d, lon_d, h_m = s.observation.geodetic_deg
                _, _, _, s_lat = rad_to_dms(np.radians(lat_d))
                _, _, _, s_lon = rad_to_dms(np.radians(lon_d))
                item_lat = QTableWidgetItem(s_lat.strip())
                item_lon = QTableWidgetItem(s_lon.strip())
                item_h = QTableWidgetItem(f"{h_m:.3f}")
            else:
                item_lat = QTableWidgetItem("")
                item_lon = QTableWidgetItem("")
                item_h = QTableWidgetItem("")

            self.table_antennas.setItem(row, 3, item_lat)
            self.table_antennas.setItem(row, 4, item_lon)
            self.table_antennas.setItem(row, 5, item_h)

        self.table_antennas.blockSignals(False)
        self._update_gnss_status()

    def _update_gnss_status(self):
        """Actualiza el recuento de antenas seleccionadas y la retroalimentación visual."""
        plat = self._get_current_platform()
        if not plat:
            self.lbl_gnss_status.setText("Sin plataforma seleccionada.")
            self.lbl_gnss_status.setStyleSheet("color: #64748b; font-size: 11px;")
            return

        total = self.table_antennas.rowCount()
        active = 0
        for row in range(total):
            chk_widget = self.table_antennas.cellWidget(row, 0)
            chk = chk_widget.findChild(QCheckBox) if chk_widget else None
            if chk and chk.isChecked():
                active += 1

        if active >= 3:
            self.lbl_gnss_status.setText(f"{active} de {total} antenas seleccionadas para ajuste (mínimo 3 cumplido).")
            self.lbl_gnss_status.setStyleSheet("color: #16a34a; font-size: 11px; font-weight: 500;")
            if not self.line_gnss_path.text().strip():
                self.line_gnss_path.setPlaceholderText(f"Coordenadas precargadas desde atributos ({active} antenas).")
        elif active > 0:
            self.lbl_gnss_status.setText(f"{active} de {total} antenas seleccionadas (se requieren mín. 3 para SVD, o mín. 1 para INS).")
            self.lbl_gnss_status.setStyleSheet("color: #b45309; font-size: 11px;")
        else:
            self.lbl_gnss_status.setText(f"Sin antenas seleccionadas ({total} disponibles).")
            self.lbl_gnss_status.setStyleSheet("color: #64748b; font-size: 11px;")

    def _on_antenna_cell_changed(self, item: QTableWidgetItem):
        """Permite editar coordenadas manualmente en la tabla actualizando el observable del sensor."""
        col = item.column()
        if col not in (3, 4, 5):
            return

        row = item.row()
        plat = self._get_current_platform()
        if not plat:
            return

        name_item = self.table_antennas.item(row, 1)
        if not name_item:
            return
        code = name_item.data(Qt.UserRole)
        sens = plat.sensors.get(code)
        if not sens:
            return

        lat_item = self.table_antennas.item(row, 3)
        lon_item = self.table_antennas.item(row, 4)
        h_item = self.table_antennas.item(row, 5)

        lat_s = lat_item.text().strip() if lat_item else ""
        lon_s = lon_item.text().strip() if lon_item else ""
        h_s = h_item.text().strip() if h_item else ""

        if lat_s and lon_s and h_s:
            try:
                lat_deg = parse_dms_or_deg(lat_s)
                lon_deg = parse_dms_or_deg(lon_s)
                h_m = float(h_s)
                srt = self._get_current_srt()
                srt_id = srt.id if srt else ""
                if not sens.observation:
                    sens.observation = SensorObservation(ref_system_id=srt_id)
                sens.observation.geodetic_deg = (lat_deg, lon_deg, h_m)
                if srt_id:
                    sens.observation.ref_system_id = srt_id

                # Activar automáticamente el checkbox si tiene coordenadas válidas
                chk_widget = self.table_antennas.cellWidget(row, 0)
                chk = chk_widget.findChild(QCheckBox) if chk_widget else None
                if chk and not chk.isChecked():
                    chk.blockSignals(True)
                    chk.setChecked(True)
                    chk.blockSignals(False)
            except Exception:
                pass
        self._update_gnss_status()

    # =========================================================================
    # Gestión de Ficheros GNSS e INS (Estilo QGIS)
    # =========================================================================

    def _on_browse_gnss_file(self):
        """Abre explorador de archivos para cargar coordenadas de antenas GNSS."""
        plat = self._get_current_platform()
        if not plat:
            QMessageBox.warning(self, "Aviso", "Seleccione una plataforma antes de importar coordenadas.")
            return

        fpath, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Fichero de Coordenadas GNSS", "",
            "Ficheros de Coordenadas y Tablas (*.txt *.csv *.dat *.xlsx);;Libros de Excel (*.xlsx);;Archivos de Texto / CSV (*.txt *.csv *.dat);;Todos los archivos (*.*)"
        )
        if not fpath:
            return

        srt = self._get_current_srt()
        srt_id = srt.id if srt else ""

        try:
            if fpath.lower().endswith(".xlsx"):
                imported = plat.import_sensors_from_table(fpath, ref_system_id=srt_id)
                self.line_gnss_path.setText(fpath)
                self._populate_antennas()
                geo_count = sum(1 for s in imported if s.observation and s.observation.has_geodetic)
                QMessageBox.information(
                    self, "Importación GNSS Exitosa",
                    f"Tabla procesada con éxito en '{plat.name}':\n"
                    f"- Receptores GNSS con coordenadas observadas: {geo_count}"
                )
            else:
                content = _read_text_file_robust(fpath)
                counts = plat.import_observations_from_txt(content, ref_system_id=srt_id)
                self.line_gnss_path.setText(fpath)
                self._populate_antennas()

                if counts["gnss"] == 0:
                    sensor_list = [f"'{s.name}'" for s in plat.sensors.values() if s.sensor_type == SensorType.GNSS]
                    names_str = ", ".join(sensor_list) if sensor_list else "(sin antenas registradas)"
                    QMessageBox.warning(
                        self, "Aviso de Importación",
                        f"No se encontraron correspondencias de antenas GNSS en la plataforma '{plat.name}'.\n\n"
                        f"Nombres de antenas en la plataforma: {names_str}\n\n"
                        f"Asegúrese de que la primera columna del fichero coincida con el Nombre asignado a cada antena."
                    )
                else:
                    QMessageBox.information(
                        self, "Importación GNSS Exitosa",
                        f"Coordenadas importadas a la plataforma '{plat.name}':\n"
                        f"- Receptores GNSS vinculados: {counts['gnss']}"
                    )
        except Exception as e:
            QMessageBox.critical(self, "Error de Lectura", f"No se pudo procesar el fichero GNSS:\n{str(e)}")

    def _on_clear_gnss_file(self):
        """Limpia la ruta y las coordenadas GNSS observadas en la plataforma."""
        self.line_gnss_path.clear()
        plat = self._get_current_platform()
        if plat:
            for s in plat.sensors.values():
                if s.observation and s.observation.has_geodetic:
                    s.observation.geodetic_deg = None
        self._populate_antennas()

    def _on_browse_ins_file(self):
        """Abre explorador para cargar observaciones de actitud del sensor INS."""
        plat = self._get_current_platform()
        if not plat:
            QMessageBox.warning(self, "Aviso", "Seleccione una plataforma antes de importar actitud INS.")
            return

        fpath, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Fichero de Actitud INS", "",
            "Ficheros de Actitud y Tablas (*.txt *.csv *.dat *.xlsx);;Libros de Excel (*.xlsx);;Archivos de Texto / CSV (*.txt *.csv *.dat);;Todos los archivos (*.*)"
        )
        if not fpath:
            return

        srt = self._get_current_srt()
        srt_id = srt.id if srt else ""

        try:
            if fpath.lower().endswith(".xlsx"):
                imported = plat.import_sensors_from_table(fpath, ref_system_id=srt_id)
                self.line_ins_path.setText(fpath)
                self._on_ins_sensor_selected()
                att_count = sum(1 for s in imported if s.observation and s.observation.has_attitude)
                QMessageBox.information(
                    self, "Importación INS Exitosa",
                    f"Tabla procesada con éxito en '{plat.name}':\n"
                    f"- Sensores con actitud inercial cargada: {att_count}"
                )
            else:
                content = _read_text_file_robust(fpath)
                counts = plat.import_observations_from_txt(content, ref_system_id=srt_id)
                self.line_ins_path.setText(fpath)

                ins_code = self.combo_ins.currentData()
                sens = plat.sensors.get(ins_code) if ins_code else None
                if sens and sens.observation and sens.observation.has_attitude:
                    r, p, y = sens.observation.attitude_rpy_deg
                    self._set_spinboxes_from_rpy(r, p, y)
                    self.lbl_ins_file_status.setText(f"Actitud cargada: Roll={r:+.4f}°, Pitch={p:+.4f}°, Yaw={y:.4f}°")
                    self.lbl_ins_file_status.setStyleSheet("color: #16a34a; font-size: 10px; font-weight: 500;")
                else:
                    self.lbl_ins_file_status.setText(f"Se importaron {counts['attitude']} observaciones inerciales.")

                QMessageBox.information(
                    self, "Importación INS Exitosa",
                    f"Observaciones de actitud cargadas: {counts['attitude']}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Error de Lectura", f"No se pudo procesar el fichero INS:\n{str(e)}")

    def _on_clear_ins_file(self):
        """Limpia el fichero INS y restablece los spinboxes."""
        self.line_ins_path.clear()
        self.lbl_ins_file_status.setText("Sin fichero INS cargado.")
        self.lbl_ins_file_status.setStyleSheet("color: #64748b; font-size: 10px;")

    # =========================================================================
    # Gestión de Actitud y Convenciones INS
    # =========================================================================

    @property
    def radio_source_gnss(self):
        class _Proxy:
            def __init__(self, combo): self.combo = combo
            def isChecked(self): return self.combo.currentIndex() == 0
            def setChecked(self, v):
                if v: self.combo.setCurrentIndex(0)
        return _Proxy(self.combo_method)

    @property
    def radio_source_ins(self):
        class _Proxy:
            def __init__(self, combo): self.combo = combo
            def isChecked(self): return self.combo.currentIndex() == 1
            def setChecked(self, v):
                if v: self.combo.setCurrentIndex(1)
        return _Proxy(self.combo_method)

    @property
    def radio_source_both(self):
        class _Proxy:
            def __init__(self, combo): self.combo = combo
            def isChecked(self): return self.combo.currentIndex() == 2
            def setChecked(self, v):
                if v: self.combo.setCurrentIndex(2)
        return _Proxy(self.combo_method)

    def _on_attitude_source_changed(self):
        """Conmuta dinámicamente el método de actitud principal (GNSS SVD, INS o Ambos)."""
        idx = self.combo_method.currentIndex()
        if idx == 0:
            self.lbl_method_info.setText(
                "La orientación se calcula por descomposición en valores singulares (SVD) a partir de las coordenadas observadas de las antenas GNSS (mínimo 3)."
            )
        elif idx == 1:
            self.lbl_method_info.setText(
                "La orientación se adopta directamente de los ángulos de actitud medidos por la unidad inercial (INS) corregidos por declinación magnética y boresight."
            )
        else:
            self.lbl_method_info.setText(
                "Auditoría Cruzada Activa: Se calcularán las orientaciones por ambas metodologías independientes (SVD e INS) y se auditarán sus residuos métricos y discrepancias angulares."
            )

    def _on_ins_mode_changed(self):
        """Conmuta entre entrada manual directa por teclado o carga por fichero para el INS."""
        is_manual = self.radio_ins_manual.isChecked()
        self.widget_ins_file.setVisible(not is_manual)

    def _on_ins_sensor_selected(self):
        """Actualiza los spinboxes con la actitud almacenada en el sensor INS seleccionado."""
        plat = self._get_current_platform()
        if not plat:
            return
        ins_code = self.combo_ins.currentData()
        sens = plat.sensors.get(ins_code) if ins_code else None
        if sens and sens.observation and sens.observation.has_attitude:
            r, p, y = sens.observation.attitude_rpy_deg
            self._set_spinboxes_from_rpy(r, p, y)
            if not self.line_ins_path.text().strip():
                self.line_ins_path.setPlaceholderText(f"Actitud precargada desde atributos ({sens.name})")
            self.lbl_ins_file_status.setText(f"Actitud precargada de '{sens.name}': Roll={r:+.4f}°, Pitch={p:+.4f}°, Yaw={y:.4f}°")
            self.lbl_ins_file_status.setStyleSheet("color: #16a34a; font-size: 10px; font-weight: 500;")

    def _set_spinboxes_from_rpy(self, r: float, p: float, y: float):
        """Fija los valores de los spinboxes respetando la convención activa."""
        if self.ins_convention == "RPY":
            self.spin_roll.setValue(r)
            self.spin_pitch.setValue(p)
            self.spin_yaw.setValue(y)
        else:
            # Convención Alpha, Beta, Gamma: Alpha = -Roll, Beta = -Pitch, Gamma = -Yaw
            self.spin_roll.setValue(-r)
            self.spin_pitch.setValue(-p)
            self.spin_yaw.setValue(-y)

    def _on_ins_convention_changed(self, idx: int):
        """Gestiona el cambio de convención desde el desplegable."""
        val1 = self.spin_roll.value()
        val2 = self.spin_pitch.value()
        val3 = self.spin_yaw.value()

        if idx == 0:
            self.ins_convention = "RPY"
            self.lbl_spin1.setText("Roll:")
            self.lbl_spin2.setText("Pitch:")
            self.lbl_spin3.setText("Yaw:")
            self.spin_roll.setValue(-val1)
            self.spin_pitch.setValue(-val2)
            self.spin_yaw.setValue(-val3)
        else:
            self.ins_convention = "ABG"
            self.lbl_spin1.setText("Alpha (α):")
            self.lbl_spin2.setText("Beta (β):")
            self.lbl_spin3.setText("Gamma (γ):")
            self.spin_roll.setValue(-val1)
            self.spin_pitch.setValue(-val2)
            self.spin_yaw.setValue(-val3)

    def _on_toggle_ins_convention(self):
        """Método de conveniencia para pruebas que alterna el índice de la convención."""
        new_idx = 1 if self.combo_ins_convention.currentIndex() == 0 else 0
        self.combo_ins_convention.setCurrentIndex(new_idx)


    def _get_ins_attitude_deg(self) -> Optional[Tuple[float, float, float]]:
        """Devuelve la actitud del INS normalizada en (Roll, Pitch, Yaw) en grados."""
        if self.radio_ins_manual.isChecked():
            v1 = self.spin_roll.value()
            v2 = self.spin_pitch.value()
            v3 = self.spin_yaw.value()
            if self.ins_convention == "RPY":
                return (v1, v2, v3)
            else:
                return (-v1, -v2, -v3)
        else:
            plat = self._get_current_platform()
            ins_code = self.combo_ins.currentData()
            sens = plat.sensors.get(ins_code) if (plat and ins_code) else None
            if sens and sens.observation and sens.observation.has_attitude:
                return sens.observation.attitude_rpy_deg
            return (self.spin_roll.value(), self.spin_pitch.value(), self.spin_yaw.value())

    # =========================================================================
    # Ejecución del Cálculo y Muestra de Resultados
    # =========================================================================

    def solve(self):
        """Ejecuta el cálculo analítico de georreferenciación multipunto."""
        plat = self._get_current_platform()
        if not plat:
            QMessageBox.warning(self, "Aviso", "Seleccione una plataforma válida para procesar.")
            return

        srt = self._get_current_srt()
        if not srt:
            QMessageBox.warning(self, "Aviso", "Seleccione un Sistema de Referencia Terrestre (SRT / e-frame).")
            return

        use_gnss_svd = self.radio_source_gnss.isChecked()

        # 1. Antenas GNSS seleccionadas y válidas
        selected_antennas = []
        gnss_obs = {}
        for row in range(self.table_antennas.rowCount()):
            chk_widget = self.table_antennas.cellWidget(row, 0)
            chk = chk_widget.findChild(QCheckBox) if chk_widget else None
            if chk and chk.isChecked():
                name_item = self.table_antennas.item(row, 1)
                code = name_item.data(Qt.UserRole)
                s = plat.sensors.get(code)
                if s and s.observation and s.observation.has_geodetic:
                    selected_antennas.append(code)
                    gnss_obs[code] = s.geodetic_obs

        # Validación según método seleccionado
        if self.radio_source_gnss.isChecked() or self.radio_source_both.isChecked():
            if len(selected_antennas) < 3:
                QMessageBox.warning(
                    self, "Antenas GNSS Insuficientes",
                    f"Para calcular la orientación mediante la Constelación GNSS (SVD de Kabsch / Horn) "
                    f"se requieren al menos 3 antenas no colineales con coordenadas observadas.\n\n"
                    f"Antenas seleccionadas con coordenadas válidas: {len(selected_antennas)}.\n"
                    f"Cargue el fichero de coordenadas GNSS o introduzca los valores manualmente en la tabla."
                )
                return
        else:
            if len(selected_antennas) < 1:
                QMessageBox.warning(
                    self, "Antena Requerida para Posición",
                    f"Para orientar mediante Sensor Inercial (INS) se requiere al menos 1 antena GNSS "
                    f"seleccionada para fijar la posición métrica absoluta de la plataforma en el terreno."
                )
                return

        # 2. Obtener y sincronizar actitud del INS
        ins_code = self.combo_ins.currentData() or None
        ins_att = self._get_ins_attitude_deg()
        if ins_code and ins_code in plat.sensors and ins_att is not None:
            sens_ins = plat.sensors[ins_code]
            if not sens_ins.observation:
                sens_ins.observation = SensorObservation(ref_system_id=srt.id)
            sens_ins.observation.attitude_rpy_deg = ins_att

        try:
            sol = solve_multisensor_georeferencing(
                platform=plat,
                gnss_observations=gnss_obs,
                ins_attitude_deg=ins_att,
                reference_system=srt,
                gnss_sensor_codes=selected_antennas,
                ins_sensor_code=ins_code
            )
            self.last_solution = sol
            self._display_results(sol, plat, srt)
            self.btn_apply.setEnabled(True)
            self.main_tabs.setCurrentIndex(1)
        except Exception as e:
            QMessageBox.critical(self, "Error en Cálculo", f"Error al resolver la georreferenciación:\n{str(e)}")

    def _display_results(self, sol: GeoreferencingSolution, plat: Platform, srt: ReferenceSystem):
        """Muestra los resultados estructurados en las tres pestañas técnicas."""
        _, _, _, s_lat = rad_to_dms(sol.pla_origin_lat_rad)
        _, _, _, s_lon = rad_to_dms(sol.pla_origin_lon_rad)
        lat_deg = float(np.degrees(sol.pla_origin_lat_rad))
        lon_deg = float(np.degrees(sol.pla_origin_lon_rad))

        self.lbl_pla_coords.setText(
            f"Geodésicas PLA: φ = {s_lat.strip()} ({lat_deg:+11.6f}°), "
            f"λ = {s_lon.strip()} ({lon_deg:+11.6f}°), h = {sol.pla_origin_h_ellip:9.3f} m"
        )

        r, p, y = sol.attitude_gnss_deg
        r_i, p_i, y_i = sol.attitude_ins_total_deg

        use_ins = self.radio_source_ins.isChecked()
        if use_ins:
            self.lbl_pla_attitude.setText(
                f"Actitud Activa: Sensor INS (Roll = {r_i:+8.4f}°, Pitch = {p_i:+8.4f}°, Yaw = {y_i:8.4f}°) | "
                f"GNSS SVD: Roll = {r:+8.4f}°, Pitch = {p:+8.4f}°, Yaw = {y:8.4f}°"
            )
        else:
            self.lbl_pla_attitude.setText(
                f"Actitud Activa: Constelación GNSS (Roll = {r:+8.4f}°, Pitch = {p:+8.4f}°, Yaw = {y:8.4f}°) | "
                f"INS Total: Roll = {r_i:+8.4f}°, Pitch = {p_i:+8.4f}°, Yaw = {y_i:8.4f}°"
            )

        res_pla = sol.results_gnss.get("PLA")
        if res_pla:
            self.lbl_pla_utm.setText(
                f"Proyección UTM (Huso {res_pla.zone}{srt.utm_hemisphere}): "
                f"E = {res_pla.easting:11.3f} m, N = {res_pla.northing:11.3f} m, H_orto = {res_pla.h_orto:8.3f} m (N={srt.geoid_undulation_N} m)"
            )

        results_map = sol.results_ins if use_ins else sol.results_gnss

        self.table_propagated.setRowCount(len(plat.sensors))
        for row, (code, s) in enumerate(plat.sensors.items()):
            res = results_map.get(code)
            if not res:
                continue

            _, _, _, lat_str = rad_to_dms(res.lat_rad)
            _, _, _, lon_str = rad_to_dms(res.lon_rad)

            self.table_propagated.setItem(row, 0, QTableWidgetItem(f"{s.name} [{code}]"))
            self.table_propagated.setItem(row, 1, QTableWidgetItem(s.sensor_type.value))
            self.table_propagated.setItem(row, 2, QTableWidgetItem(f"{res.ecef[0]:12.3f}"))
            self.table_propagated.setItem(row, 3, QTableWidgetItem(f"{res.ecef[1]:12.3f}"))
            self.table_propagated.setItem(row, 4, QTableWidgetItem(f"{res.ecef[2]:12.3f}"))
            self.table_propagated.setItem(row, 5, QTableWidgetItem(lat_str.strip()))
            self.table_propagated.setItem(row, 6, QTableWidgetItem(lon_str.strip()))
            self.table_propagated.setItem(row, 7, QTableWidgetItem(f"{res.h_ellip:8.3f}"))
            self.table_propagated.setItem(row, 8, QTableWidgetItem(f"{res.easting:11.3f}"))
            self.table_propagated.setItem(row, 9, QTableWidgetItem(f"{res.northing:11.3f}"))
            self.table_propagated.setItem(row, 10, QTableWidgetItem(f"{res.h_orto:8.3f}"))

        lines_audit = [
            "================================================================================",
            "AUDITORÍA MATEMÁTICA Y CONTROL DE CALIDAD DE GEORREFERENCIACIÓN",
            "================================================================================",
            f"Plataforma analizada: {plat.name} ({len(plat.sensors)} dispositivos)",
            f"Sistema de Referencia: {srt.name} [{srt.id}] (Elipsoide {srt.ellipsoid}, Huso UTM {srt.utm_zone}{srt.utm_hemisphere})",
            f"Método de Actitud Activo: {'Sensor Inercial (INS)' if use_ins else ('Ambos (SVD + INS)' if self.radio_source_both.isChecked() else 'Constelación GNSS (SVD de Horn / Kabsch)')}",
            "",
            "1. ORTONORMALIDAD DE LA MATRIZ DE ROTACIÓN C_b^n (GNSS):",
            f"   - Determinante det(C_b^n)              : {sol.det_dcm:+.12f}  {'[DET=+1 OK]' if abs(sol.det_dcm - 1.0) < 1e-6 else '[ALERTA REFLEXIÓN]'}",
            f"   - Error de Ortonormalidad ||C*C^T - I||_F: {sol.ortho_error_dcm:.2e}  {'[EXCELENTE < 1e-12]' if sol.ortho_error_dcm < 1e-10 else '[REVISAR]'}",
            "",
            "2. RESIDUOS MÉTRICOS 3D DE AJUSTE POR ANTENA (||r_obs - r_calc||):",
        ]
        for c, res_m in sol.residuals_gnss_m.items():
            lines_audit.append(f"   - Antena {c:<6s}: {res_m * 1000.0:8.3f} mm  ({res_m:8.5f} m)")

        d_r = sol.attitude_ins_total_deg[0] - sol.attitude_gnss_deg[0]
        d_p = sol.attitude_ins_total_deg[1] - sol.attitude_gnss_deg[1]
        d_y = sol.attitude_ins_total_deg[2] - sol.attitude_gnss_deg[2]
        lines_audit.extend([
            "",
            "3. DISCREPANCIA ANGULAR (INS Total vs Constelación GNSS):",
            f"   - ΔRoll   : {d_r:+8.4f}°",
            f"   - ΔPitch  : {d_p:+8.4f}°",
            f"   - ΔYaw    : {d_y:+8.4f}°",
            "",
            "4. DISCREPANCIAS MÉTRICAS EN UTM POR DISPOSITIVO (GNSS vs INS):",
            f"   {'Dispositivo':<12s} {'ΔEste (mm)':>12s} {'ΔNorte (mm)':>12s} {'ΔCota (mm)':>12s}"
        ])
        for c, (de, dn, dh) in sol.diff_gnss_ins_utm.items():
            lines_audit.append(f"   {c:<12s} {de*1000.0:+12.2f} {dn*1000.0:+12.2f} {dh*1000.0:+12.2f}")

        self.text_audit.setText("\n".join(lines_audit))

        rep_text = generate_georeferencing_report(sol, platform=plat)
        self.last_report = rep_text
        self.text_report.setText(rep_text)

    def _on_export_report(self):
        """Exporta el informe técnico generado a un archivo .txt o .md."""
        if not self.last_report:
            QMessageBox.warning(self, "Aviso", "Primero debe calcular una solución para generar el informe.")
            return

        fpath, _ = QFileDialog.getSaveFileName(
            self, "Exportar Informe Técnico de Georreferenciación", "informe_georreferenciacion.txt",
            "Archivo de Texto (*.txt);;Markdown (*.md);;Todos los archivos (*.*)"
        )
        if not fpath:
            return

        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(self.last_report)
            QMessageBox.information(self, "Exportación Exitosa", f"Informe guardado correctamente en:\n{fpath}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo guardar el archivo:\n{str(e)}")

    def _on_apply_to_project(self):
        """Aplica la solución calculada a la plataforma y enriquece cada sensor con sus atributos e-frame."""
        plat = self._get_current_platform()
        srt = self._get_current_srt()

        if not self.last_solution or not plat or not srt:
            QMessageBox.warning(self, "Aviso", "Primero debe calcular una solución antes de aplicar los cambios al proyecto.")
            return

        sol = self.last_solution

        method_str = "SVD"
        if self.radio_source_ins.isChecked():
            method_str = "INS"
        elif self.radio_source_both.isChecked():
            method_str = "SVD+INS"

        # Delegación al método desacoplado de Platform en core
        count_updated = plat.apply_georeferencing_solution(
            solution=sol,
            reference_system=srt,
            method_str=method_str
        )

        # Notificar a la ventana principal de cambios pendientes
        parent_w = self.parent()
        if parent_w and hasattr(parent_w, "is_dirty"):
            parent_w.is_dirty = True
        if parent_w and hasattr(parent_w, "hierarchy_dock"):
            parent_w.hierarchy_dock.refresh_all()

        QMessageBox.information(
            self,
            "Cambios Aplicados con Éxito",
            f"Se han propagado y vinculado los atributos del sistema '{srt.name}' a la plataforma '{plat.name}' "
            f"y a {count_updated} sensores del rig.\n\n"
            f"Puede consultar la Tabla de Atributos completa presionando F6 o desde el menú contextual de la plataforma."
        )
        self.solution_applied.emit()

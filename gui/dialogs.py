"""
PyGSN - GUI Dialogs and Modals (PySide6 / Qt)
=============================================
Diálogos técnicos para configuración de proyectos, plataformas, sensores y cálculo.
"""

from typing import Optional, Dict, Any, Callable
from pathlib import Path
import numpy as np

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QLabel, QGroupBox, QTextEdit, QMessageBox, QWidget, QAbstractSpinBox
)
from PySide6.QtCore import Qt

from core.models import Platform, Sensor, SensorType, PlatformType
from core.project import Project
from core.geodesy import GRS80, WGS84, geodetic_to_ecef, ecef_to_geodetic, rad_to_dms
from gui.theme import set_window_titlebar_light


class BaseDialog(QDialog):
    """Clase base para todos los cuadros de diálogo con barra de título Windows clara."""

    def showEvent(self, event):
        super().showEvent(event)
        set_window_titlebar_light(self)


class DialogNewProject(BaseDialog):
    """Diálogo para configurar y crear un nuevo proyecto limpio."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Crear Nuevo Proyecto - PyGSN")
        self.setFixedSize(480, 310)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        header = QLabel("Configuración del Nuevo Proyecto")
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #0077b6;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setVerticalSpacing(7)

        self.input_name = QLineEdit("Proyecto Nuevo")
        form.addRow("Nombre del Proyecto:", self.input_name)

        self.combo_ellipsoid = QComboBox()
        self.combo_ellipsoid.addItems(["WGS84", "GRS80"])
        form.addRow("Elipsoide de Referencia:", self.combo_ellipsoid)

        utm_layout = QHBoxLayout()
        self.spin_utm = QSpinBox()
        self.spin_utm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_utm.setRange(1, 60)
        self.spin_utm.setValue(30)
        self.combo_hemi = QComboBox()
        self.combo_hemi.addItems(["Norte", "Sur"])
        utm_layout.addWidget(self.spin_utm)
        utm_layout.addWidget(self.combo_hemi)
        form.addRow("Huso UTM / Hemisferio:", utm_layout)

        self.spin_geoid = QDoubleSpinBox()
        self.spin_geoid.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_geoid.setRange(-200.0, 200.0)
        self.spin_geoid.setDecimals(4)
        self.spin_geoid.setValue(0.0)
        self.spin_geoid.setSuffix(" m")
        form.addRow("Ondulación Geoidal N:", self.spin_geoid)

        self.spin_decl = QDoubleSpinBox()
        self.spin_decl.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_decl.setRange(-180.0, 180.0)
        self.spin_decl.setDecimals(4)
        self.spin_decl.setValue(0.0)
        self.spin_decl.setSuffix(" °")
        form.addRow("Declinación Magnética:", self.spin_decl)

        layout.addLayout(form)
        layout.addSpacing(6)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_create = QPushButton("Crear Proyecto")
        self.btn_create.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_create)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def get_project_data(self) -> Dict[str, Any]:
        utm_val = self.spin_utm.value()
        if self.combo_hemi.currentText() == "Sur":
            utm_val = -utm_val
        return {
            "name": self.input_name.text().strip() or "Proyecto Nuevo",
            "ellipsoid_name": self.combo_ellipsoid.currentText(),
            "utm_zone": utm_val,
            "geoid_undulation_n": self.spin_geoid.value(),
            "mag_declination_deg": self.spin_decl.value(),
        }


class DialogProjectProperties(BaseDialog):
    """Diálogo para consultar y editar las propiedades del proyecto activo."""

    def __init__(self, project: Project, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Propiedades del Proyecto - PyGSN")
        self.setFixedSize(480, 310)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        header = QLabel("Parámetros y Metadatos Activos")
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #0077b6;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setVerticalSpacing(7)

        self.input_name = QLineEdit(project.name)
        form.addRow("Nombre del Proyecto:", self.input_name)

        self.combo_ellipsoid = QComboBox()
        self.combo_ellipsoid.addItems(["WGS84", "GRS80"])
        self.combo_ellipsoid.setCurrentText(project.ellipsoid_name)
        form.addRow("Elipsoide de Referencia:", self.combo_ellipsoid)

        utm_layout = QHBoxLayout()
        raw_utm = project.config.get("utm_zone", 30)
        self.spin_utm = QSpinBox()
        self.spin_utm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_utm.setRange(1, 60)
        self.spin_utm.setValue(abs(raw_utm))
        self.combo_hemi = QComboBox()
        self.combo_hemi.addItems(["Norte", "Sur"])
        self.combo_hemi.setCurrentText("Norte" if raw_utm >= 0 else "Sur")
        utm_layout.addWidget(self.spin_utm)
        utm_layout.addWidget(self.combo_hemi)
        form.addRow("Huso UTM / Hemisferio:", utm_layout)

        self.spin_geoid = QDoubleSpinBox()
        self.spin_geoid.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_geoid.setRange(-200.0, 200.0)
        self.spin_geoid.setDecimals(4)
        self.spin_geoid.setValue(float(project.config.get("geoid_undulation_n", 0.0)))
        self.spin_geoid.setSuffix(" m")
        form.addRow("Ondulación Geoidal N:", self.spin_geoid)

        self.spin_decl = QDoubleSpinBox()
        self.spin_decl.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_decl.setRange(-180.0, 180.0)
        self.spin_decl.setDecimals(4)
        self.spin_decl.setValue(float(project.config.get("mag_declination_deg", 0.0)))
        self.spin_decl.setSuffix(" °")
        form.addRow("Declinación Magnética:", self.spin_decl)

        layout.addLayout(form)
        layout.addSpacing(6)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_apply = QPushButton("Aplicar Cambios")
        self.btn_apply.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_apply)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def apply_to_project(self):
        self.project.name = self.input_name.text().strip() or self.project.name
        self.project.ellipsoid_name = self.combo_ellipsoid.currentText()
        utm_val = self.spin_utm.value()
        if self.combo_hemi.currentText() == "Sur":
            utm_val = -utm_val
        self.project.config["utm_zone"] = utm_val
        self.project.config["geoid_undulation_n"] = self.spin_geoid.value()
        self.project.config["mag_declination_deg"] = self.spin_decl.value()


class DialogCreatePlatform(BaseDialog):
    """Diálogo para crear una nueva plataforma (vehículo o estación fija)."""

    def __init__(self, existing_count: int = 0, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Crear Nueva Plataforma - PyGSN")
        self.setFixedSize(460, 265)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(6)

        header = QLabel("Definición de Plataforma en el Proyecto")
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #0077b6; margin: 0px; padding: 0px;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 4)
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(10)

        default_id = f"PLAT_{existing_count + 1}"
        self.input_id = QLineEdit(default_id)
        form.addRow("Identificador Único:", self.input_id)

        self.input_name = QLineEdit(f"Vehículo {existing_count + 1}")
        form.addRow("Nombre Descriptivo:", self.input_name)

        self.combo_type = QComboBox()
        self.combo_type.addItems(["VEHICLE", "ROVER", "CAR", "DRONE_X4", "BASE_STATION", "TEST_BENCH", "GENERIC"])
        form.addRow("Tipo de Plataforma:", self.combo_type)

        self.check_fixed = QCheckBox("Estación fija de referencia (origen topocéntrico)")
        form.addRow("", self.check_fixed)

        self.check_dims = QCheckBox("Definir dimensiones de caja envolvente")
        self.check_dims.setChecked(False)
        self.check_dims.toggled.connect(self._on_dims_toggled)
        form.addRow("Dimensiones Chasis:", self.check_dims)

        dims_layout = QHBoxLayout()
        dims_layout.setSpacing(6)

        self.spin_l = QDoubleSpinBox()
        self.spin_l.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_l.setRange(0.01, 500.0)
        self.spin_l.setValue(2.0)
        self.spin_l.setPrefix("L: ")
        self.spin_l.setSuffix(" m")
        self.spin_l.setEnabled(False)

        self.spin_w = QDoubleSpinBox()
        self.spin_w.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_w.setRange(0.01, 100.0)
        self.spin_w.setValue(1.0)
        self.spin_w.setPrefix("W: ")
        self.spin_w.setSuffix(" m")
        self.spin_w.setEnabled(False)

        self.spin_h = QDoubleSpinBox()
        self.spin_h.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_h.setRange(0.01, 100.0)
        self.spin_h.setValue(0.5)
        self.spin_h.setPrefix("H: ")
        self.spin_h.setSuffix(" m")
        self.spin_h.setEnabled(False)

        dims_layout.addWidget(self.spin_l)
        dims_layout.addWidget(self.spin_w)
        dims_layout.addWidget(self.spin_h)

        self.lbl_dims = QLabel("Longitud x Ancho x Alto:")
        self.lbl_dims.setEnabled(False)
        form.addRow(self.lbl_dims, dims_layout)

        layout.addLayout(form)
        layout.addSpacing(4)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_create = QPushButton("Crear Plataforma")
        self.btn_create.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_create)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def _on_dims_toggled(self, checked: bool):
        self.lbl_dims.setEnabled(checked)
        self.spin_l.setEnabled(checked)
        self.spin_w.setEnabled(checked)
        self.spin_h.setEnabled(checked)

    def get_platform(self) -> Platform:
        pid = self.input_id.text().strip().upper() or "PLAT_1"
        pname = self.input_name.text().strip() or pid
        ptype = self.combo_type.currentText()
        is_fixed = self.check_fixed.isChecked()
        has_dims = self.check_dims.isChecked()
        return Platform(
            id=pid,
            name=pname,
            platform_type=ptype,
            is_fixed=is_fixed,
            has_dimensions=has_dims,
            length_m=self.spin_l.value() if has_dims else 0.0,
            width_m=self.spin_w.value() if has_dims else 0.0,
            height_m=self.spin_h.value() if has_dims else 0.0
        )


class DialogAddSensor(BaseDialog):
    """Diálogo para montar un sensor en la plataforma activa."""

    def __init__(self, platform_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Añadir Sensor a {platform_name} - PyGSN")
        self.setFixedSize(500, 390)
        self.setModal(True)

        layout = QVBoxLayout(self)
        header = QLabel(f"Montaje en Plataforma: {platform_name}")
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #b45309;")
        layout.addWidget(header)

        form = QFormLayout()

        self.input_code = QLineEdit("REC1")
        form.addRow("Código / ID:", self.input_code)

        self.input_name = QLineEdit("Antena GNSS Principal")
        form.addRow("Nombre Descriptivo:", self.input_name)

        self.combo_type = QComboBox()
        self.combo_type.addItems(["GNSS", "INS", "CAMERA", "LIDAR", "ODOMETER", "OTHER"])
        form.addRow("Tipo de Sensor:", self.combo_type)
        layout.addLayout(form)

        group_arm = QGroupBox("Palanca de Brazo (Lever-Arm) en b-frame (m)")
        arm_layout = QHBoxLayout(group_arm)
        self.spin_arm_x = QDoubleSpinBox()
        self.spin_arm_x.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_arm_x.setRange(-100.0, 100.0)
        self.spin_arm_x.setDecimals(4)
        self.spin_arm_x.setPrefix("Xb: ")
        self.spin_arm_y = QDoubleSpinBox()
        self.spin_arm_y.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_arm_y.setRange(-100.0, 100.0)
        self.spin_arm_y.setDecimals(4)
        self.spin_arm_y.setPrefix("Yb: ")
        self.spin_arm_z = QDoubleSpinBox()
        self.spin_arm_z.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_arm_z.setRange(-100.0, 100.0)
        self.spin_arm_z.setDecimals(4)
        self.spin_arm_z.setPrefix("Zb: ")
        arm_layout.addWidget(self.spin_arm_x)
        arm_layout.addWidget(self.spin_arm_y)
        arm_layout.addWidget(self.spin_arm_z)
        layout.addWidget(group_arm)

        group_bore = QGroupBox("Ángulos de Boresight Euler (s-frame -> b-frame) (°)")
        bore_layout = QHBoxLayout(group_bore)
        self.spin_roll = QDoubleSpinBox()
        self.spin_roll.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_roll.setRange(-180.0, 180.0)
        self.spin_roll.setDecimals(4)
        self.spin_roll.setPrefix("Roll: ")
        self.spin_pitch = QDoubleSpinBox()
        self.spin_pitch.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_pitch.setRange(-180.0, 180.0)
        self.spin_pitch.setDecimals(4)
        self.spin_pitch.setPrefix("Pitch: ")
        self.spin_yaw = QDoubleSpinBox()
        self.spin_yaw.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_yaw.setRange(-180.0, 180.0)
        self.spin_yaw.setDecimals(4)
        self.spin_yaw.setPrefix("Yaw: ")
        bore_layout.addWidget(self.spin_roll)
        bore_layout.addWidget(self.spin_pitch)
        bore_layout.addWidget(self.spin_yaw)
        layout.addWidget(group_bore)
        layout.addSpacing(10)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_add = QPushButton("Añadir Sensor")
        self.btn_add.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def get_sensor(self) -> Sensor:
        code = self.input_code.text().strip().upper() or "SENS_1"
        name = self.input_name.text().strip() or code
        stype_str = self.combo_type.currentText()
        stype = getattr(SensorType, stype_str, SensorType.OTHER)
        arm = np.array([self.spin_arm_x.value(), self.spin_arm_y.value(), self.spin_arm_z.value()], dtype=np.float64)
        euler = (self.spin_roll.value(), self.spin_pitch.value(), self.spin_yaw.value())
        return Sensor(code=code, name=name, sensor_type=stype, lever_arm_b=arm, boresight_euler_deg=euler)


class DialogChassisActions(BaseDialog):
    """Diálogo de acciones rápidas sobre el chasis (Centrar al Origen, Centrar al Centroide)."""

    def __init__(
        self,
        platform_name: str,
        on_center_origin: Callable[[], None],
        on_center_centroid: Callable[[], None],
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Acciones de Chasis - PyGSN")
        self.setFixedSize(320, 170)
        self.setModal(True)

        layout = QVBoxLayout(self)
        title = QLabel(f"Plataforma: {platform_name}")
        title.setStyleSheet("font-weight: bold; color: #0077b6;")
        layout.addWidget(title)

        btn_origin = QPushButton("Centrar al Origen [0, 0]")
        btn_origin.clicked.connect(lambda: [on_center_origin(), self.accept()])
        layout.addWidget(btn_origin)

        btn_centroid = QPushButton("Centrar al Centroide")
        btn_centroid.clicked.connect(lambda: [on_center_centroid(), self.accept()])
        layout.addWidget(btn_centroid)

        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.reject)
        layout.addWidget(btn_close)


class DialogDiagnostics(BaseDialog):
    """Diálogo de diagnóstico espectral SVD y auditoría DCM."""

    def __init__(self, solution=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Diagnóstico SVD y Auditoría DCM - PyGSN")
        self.setFixedSize(620, 440)
        self.setModal(True)

        layout = QVBoxLayout(self)
        header = QLabel("Auditoría Espectral SVD y Consistencia de Actitud")
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #ef476f;")
        layout.addWidget(header)

        self.text_diag = QTextEdit()
        self.text_diag.setReadOnly(True)
        self.text_diag.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px;")
        layout.addWidget(self.text_diag)

        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        self._populate(solution)

    def _populate(self, solution):
        if solution is None:
            self.text_diag.setText("No hay solución previa calculada. Cargue datos y ejecute [Resolver SVD].")
            return

        try:
            Cb2n = solution.Cb2n_gnss
            det = float(np.linalg.det(Cb2n))
            ortho_err = float(np.linalg.norm(Cb2n @ Cb2n.T - np.eye(3)))
            r, p, y = solution.attitude_gnss_deg
            lines = [
                "1. Auditoría de Ortonormalidad de la Matriz de Rotación C_b^n (GNSS):",
                f"   - Determinante det(C_b^n): {det:+.10f}  {'[FISICA DET=+1 OK]' if abs(det - 1.0) < 1e-6 else '[ALERTA REFLEXION]'}",
                f"   - Error de Ortonormalidad ||C*C^T - I||_F: {ortho_err:.2e}  {'[EXCELENTE < 1e-12]' if ortho_err < 1e-10 else '[REVISAR]'}",
                "",
                "2. Ángulos de Actitud de Plataforma (b-frame -> n-frame):",
                f"   - Alabeo  (Roll)   : {r:+10.4f}°",
                f"   - Cabeceo (Pitch)  : {p:+10.4f}°",
                f"   - Guiñada (Yaw)    : {y:+10.4f}°  (Acimut geodésico respecto al Norte)",
                "",
                "3. Matriz C_b^n Numérica Completa:",
                f"   [{Cb2n[0,0]:+10.6f}  {Cb2n[0,1]:+10.6f}  {Cb2n[0,2]:+10.6f}]",
                f"   [{Cb2n[1,0]:+10.6f}  {Cb2n[1,1]:+10.6f}  {Cb2n[1,2]:+10.6f}]",
                f"   [{Cb2n[2,0]:+10.6f}  {Cb2n[2,1]:+10.6f}  {Cb2n[2,2]:+10.6f}]",
                "",
                "4. Consistencia con Sensor INS:",
                f"   - Actitud Total INS (corregida boresight + declinación):",
                f"     Roll={solution.attitude_ins_total_deg[0]:+.4f}°, Pitch={solution.attitude_ins_total_deg[1]:+.4f}°, Yaw={solution.attitude_ins_total_deg[2]:+.4f}°"
            ]
            self.text_diag.setText("\n".join(lines))
        except Exception as e:
            self.text_diag.setText(f"Error al generar diagnóstico: {str(e)}")

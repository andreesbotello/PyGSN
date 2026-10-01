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

    def __init__(
        self,
        existing_ids: Optional[list] = None,
        existing_count: int = 0,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Crear Nueva Plataforma - PyGSN")
        self.setFixedSize(460, 245)
        self.setModal(True)

        # Generación automática de identificador alfanumérico, consistente y explicativo
        if existing_ids:
            i = 1
            while f"PLAT_{i:02d}" in existing_ids or f"PLAT_{i}" in existing_ids:
                i += 1
            self.auto_id = f"PLAT_{i:02d}"
        else:
            self.auto_id = f"PLAT_{existing_count + 1:02d}"

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

        self.input_name = QLineEdit(f"Vehículo {existing_count + 1}")
        form.addRow("Nombre de Plataforma:", self.input_name)

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
        pname = self.input_name.text().strip() or self.auto_id
        ptype = self.combo_type.currentText()
        is_fixed = self.check_fixed.isChecked()
        has_dims = self.check_dims.isChecked()
        return Platform(
            id=self.auto_id,
            name=pname,
            platform_type=ptype,
            is_fixed=is_fixed,
            has_dimensions=has_dims,
            length_m=self.spin_l.value() if has_dims else 0.0,
            width_m=self.spin_w.value() if has_dims else 0.0,
            height_m=self.spin_h.value() if has_dims else 0.0
        )


class DialogPlatformProperties(BaseDialog):
    """Diálogo para consultar y modificar las propiedades de una plataforma existente."""

    def __init__(self, platform: Platform, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.platform = platform
        self.setWindowTitle("Propiedades de la Plataforma - PyGSN")
        self.setFixedSize(460, 200)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(6)

        header = QLabel(f"Propiedades de Plataforma: {platform.name} [{platform.id}]")
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #0077b6; margin: 0px; padding: 0px;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 4)
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(10)

        self.input_name = QLineEdit(platform.name)
        form.addRow("Nombre de Plataforma:", self.input_name)

        self.combo_type = QComboBox()
        self.combo_type.addItems(["VEHICLE", "ROVER", "CAR", "DRONE_X4", "BASE_STATION", "TEST_BENCH", "GENERIC"])
        self.combo_type.setCurrentText(platform.platform_type)
        form.addRow("Tipo de Plataforma:", self.combo_type)

        self.check_fixed = QCheckBox("Estación fija de referencia (origen topocéntrico)")
        self.check_fixed.setChecked(platform.is_fixed)
        form.addRow("", self.check_fixed)

        # Estado del chasis como información de solo lectura
        if platform.has_dimensions:
            dims_txt = f"Definido ({platform.length_m:.2f} x {platform.width_m:.2f} x {platform.height_m:.2f} m)"
        else:
            dims_txt = "Libre (sin dimensiones fijadas)"
        lbl_chassis_status = QLabel(dims_txt)
        lbl_chassis_status.setStyleSheet("color: #475569; font-weight: 500;")
        form.addRow("Estado del Chasis:", lbl_chassis_status)

        layout.addLayout(form)
        layout.addSpacing(4)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_apply = QPushButton("Aplicar Cambios")
        self.btn_apply.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_apply)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def apply_changes(self):
        self.platform.name = self.input_name.text().strip() or self.platform.name
        self.platform.platform_type = self.combo_type.currentText()
        self.platform.is_fixed = self.check_fixed.isChecked()


class DialogAddSensor(BaseDialog):
    """Diálogo técnico para montar un sensor en la plataforma activa."""

    def __init__(self, platform_or_name: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.platform = platform_or_name if isinstance(platform_or_name, Platform) else None
        self.setWindowTitle("Añadir sensor")
        self.setFixedSize(470, 350)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(6)

        form = QFormLayout()
        form.setContentsMargins(0, 2, 0, 4)
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(10)

        self.input_name = QLineEdit("Antena GNSS Principal")
        form.addRow("Nombre Descriptivo:", self.input_name)

        self.combo_type = QComboBox()
        self.combo_type.addItems(["GNSS", "INS", "CAMERA", "LIDAR", "ODOMETER", "OTHER"])
        self.combo_type.currentTextChanged.connect(self._on_type_changed)
        form.addRow("Tipo de Sensor:", self.combo_type)
        layout.addLayout(form)

        # Palanca de brazo (Lever-Arm) opcional (por defecto [0, 0, 0] para dibujar o acotar luego)
        group_arm = QGroupBox("Posición del Sensor (Lever-Arm) en b-frame (m)")
        arm_vbox = QVBoxLayout(group_arm)
        arm_vbox.setContentsMargins(8, 4, 8, 6)
        arm_vbox.setSpacing(4)

        self.check_arm = QCheckBox("Definir posición de montaje inicial (Lever-Arm)")
        self.check_arm.setChecked(False)
        self.check_arm.toggled.connect(self._on_arm_toggled)
        arm_vbox.addWidget(self.check_arm)

        arm_layout = QHBoxLayout()
        arm_layout.setSpacing(6)
        self.spin_arm_x = QDoubleSpinBox()
        self.spin_arm_x.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_arm_x.setRange(-100.0, 100.0)
        self.spin_arm_x.setDecimals(4)
        self.spin_arm_x.setValue(0.0)
        self.spin_arm_x.setPrefix("Xb: ")
        self.spin_arm_x.setEnabled(False)

        self.spin_arm_y = QDoubleSpinBox()
        self.spin_arm_y.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_arm_y.setRange(-100.0, 100.0)
        self.spin_arm_y.setDecimals(4)
        self.spin_arm_y.setValue(0.0)
        self.spin_arm_y.setPrefix("Yb: ")
        self.spin_arm_y.setEnabled(False)

        self.spin_arm_z = QDoubleSpinBox()
        self.spin_arm_z.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_arm_z.setRange(-100.0, 100.0)
        self.spin_arm_z.setDecimals(4)
        self.spin_arm_z.setValue(0.0)
        self.spin_arm_z.setPrefix("Zb: ")
        self.spin_arm_z.setEnabled(False)

        arm_layout.addWidget(self.spin_arm_x)
        arm_layout.addWidget(self.spin_arm_y)
        arm_layout.addWidget(self.spin_arm_z)
        arm_vbox.addLayout(arm_layout)
        layout.addWidget(group_arm)

        # Orientación / Inclinación del Sensor (s-frame -> b-frame)
        group_bore = QGroupBox("Inclinación / Orientación del Sensor (s-frame → b-frame)")
        bore_vbox = QVBoxLayout(group_bore)
        bore_vbox.setContentsMargins(8, 4, 8, 6)
        bore_vbox.setSpacing(4)

        conv_layout = QHBoxLayout()
        conv_layout.setSpacing(6)
        lbl_conv = QLabel("Convención:")
        lbl_conv.setStyleSheet("color: #475569; font-weight: 500; font-size: 11px;")
        self.combo_convention = QComboBox()
        self.combo_convention.addItems([
            "Calibración (α, β, γ) [s-frame → b-frame]",
            "Actitud Aeroespacial (Roll, Pitch, Yaw)"
        ])
        self.combo_convention.currentIndexChanged.connect(self._on_convention_changed)
        conv_layout.addWidget(lbl_conv)
        conv_layout.addWidget(self.combo_convention, 1)
        bore_vbox.addLayout(conv_layout)

        bore_layout = QHBoxLayout()
        bore_layout.setSpacing(6)

        self.spin_ang1 = QDoubleSpinBox()
        self.spin_ang1.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_ang1.setRange(-360.0, 360.0)
        self.spin_ang1.setDecimals(4)
        self.spin_ang1.setValue(0.0)
        self.spin_ang1.setPrefix("α (X): ")

        self.spin_ang2 = QDoubleSpinBox()
        self.spin_ang2.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_ang2.setRange(-360.0, 360.0)
        self.spin_ang2.setDecimals(4)
        self.spin_ang2.setValue(0.0)
        self.spin_ang2.setPrefix("β (Y): ")

        self.spin_ang3 = QDoubleSpinBox()
        self.spin_ang3.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_ang3.setRange(-360.0, 360.0)
        self.spin_ang3.setDecimals(4)
        self.spin_ang3.setValue(0.0)
        self.spin_ang3.setPrefix("γ (Z): ")

        bore_layout.addWidget(self.spin_ang1)
        bore_layout.addWidget(self.spin_ang2)
        bore_layout.addWidget(self.spin_ang3)
        bore_vbox.addLayout(bore_layout)
        layout.addWidget(group_bore)

        layout.addSpacing(4)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_add = QPushButton("Añadir Sensor")
        self.btn_add.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def _on_arm_toggled(self, checked: bool):
        self.spin_arm_x.setEnabled(checked)
        self.spin_arm_y.setEnabled(checked)
        self.spin_arm_z.setEnabled(checked)

    def _on_convention_changed(self, idx: int):
        v1 = self.spin_ang1.value()
        v2 = self.spin_ang2.value()
        v3 = self.spin_ang3.value()

        # Conversión exacta: Roll = -alpha, Pitch = -beta, Yaw = -gamma
        new_v1 = -v1
        new_v2 = -v2
        new_v3 = -v3
        if new_v3 < -180.0:
            new_v3 += 360.0
        elif new_v3 > 180.0:
            new_v3 -= 360.0

        self.spin_ang1.blockSignals(True)
        self.spin_ang2.blockSignals(True)
        self.spin_ang3.blockSignals(True)

        self.spin_ang1.setValue(round(new_v1, 4))
        self.spin_ang2.setValue(round(new_v2, 4))
        self.spin_ang3.setValue(round(new_v3, 4))

        if idx == 0:
            self.spin_ang1.setPrefix("α (X): ")
            self.spin_ang2.setPrefix("β (Y): ")
            self.spin_ang3.setPrefix("γ (Z): ")
        else:
            self.spin_ang1.setPrefix("Roll: ")
            self.spin_ang2.setPrefix("Pitch: ")
            self.spin_ang3.setPrefix("Yaw: ")

        self.spin_ang1.blockSignals(False)
        self.spin_ang2.blockSignals(False)
        self.spin_ang3.blockSignals(False)

    def _on_type_changed(self, stype_str: str):
        default_names = {
            "GNSS": "Antena GNSS Principal",
            "INS": "Unidad Inercial INS",
            "CAMERA": "Cámara Fotogramétrica",
            "LIDAR": "Sensor LiDAR 3D",
            "ODOMETER": "Odómetro de Rueda",
            "OTHER": "Sensor Auxiliar"
        }
        current_txt = self.input_name.text().strip()
        if not current_txt or current_txt in default_names.values():
            self.input_name.setText(default_names.get(stype_str, "Sensor"))

    def get_sensor(self) -> Sensor:
        stype_str = self.combo_type.currentText()
        stype = getattr(SensorType, stype_str, SensorType.OTHER)

        # Generación interna de ID alfanumérico, consistente y explicativo
        prefix_map = {
            "GNSS": "GNSS",
            "INS": "INS",
            "CAMERA": "CAM",
            "LIDAR": "LIDAR",
            "ODOMETER": "ODO",
            "OTHER": "SENS"
        }
        prefix = prefix_map.get(stype_str, "SENS")
        existing_codes = set(self.platform.sensors.keys()) if self.platform else set()
        i = 1
        while f"{prefix}_{i:02d}" in existing_codes or f"{prefix}_{i}" in existing_codes:
            i += 1
        auto_code = f"{prefix}_{i:02d}"

        name = self.input_name.text().strip() or auto_code

        if self.check_arm.isChecked():
            arm = np.array([self.spin_arm_x.value(), self.spin_arm_y.value(), self.spin_arm_z.value()], dtype=np.float64)
        else:
            arm = np.zeros(3, dtype=np.float64)

        if self.combo_convention.currentIndex() == 1:
            # En pantalla está Roll, Pitch, Yaw -> guardar canónicamente alpha, beta, gamma
            r = self.spin_ang1.value()
            p = self.spin_ang2.value()
            y = self.spin_ang3.value()
            boresight = (-r, -p, -y)
        else:
            boresight = (self.spin_ang1.value(), self.spin_ang2.value(), self.spin_ang3.value())

        return Sensor(code=auto_code, name=name, sensor_type=stype, lever_arm_b=arm, boresight_deg=boresight)


class DialogSensorProperties(BaseDialog):
    """Diálogo para consultar y modificar las propiedades de un sensor montado."""

    def __init__(self, sensor: Sensor, platform_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.sensor = sensor
        self.setWindowTitle("Propiedades del Sensor - PyGSN")
        self.setFixedSize(470, 360)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(6)

        header = QLabel(f"Sensor: {sensor.name} [{sensor.code}] — Plataforma: {platform_name}")
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #b45309; margin: 0px; padding: 0px;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 4)
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(10)

        self.input_name = QLineEdit(sensor.name)
        form.addRow("Nombre Descriptivo:", self.input_name)

        self.combo_type = QComboBox()
        self.combo_type.addItems(["GNSS", "INS", "CAMERA", "LIDAR", "ODOMETER", "OTHER"])
        self.combo_type.setCurrentText(sensor.sensor_type.value)
        form.addRow("Tipo de Sensor:", self.combo_type)
        layout.addLayout(form)

        # Palanca de brazo (Lever-Arm)
        group_arm = QGroupBox("Posición del Sensor (Lever-Arm) en b-frame (m)")
        arm_layout = QHBoxLayout(group_arm)
        arm_layout.setContentsMargins(8, 6, 8, 6)
        arm_layout.setSpacing(6)

        self.spin_arm_x = QDoubleSpinBox()
        self.spin_arm_x.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_arm_x.setRange(-100.0, 100.0)
        self.spin_arm_x.setDecimals(4)
        self.spin_arm_x.setValue(float(sensor.lever_arm_b[0]))
        self.spin_arm_x.setPrefix("Xb: ")

        self.spin_arm_y = QDoubleSpinBox()
        self.spin_arm_y.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_arm_y.setRange(-100.0, 100.0)
        self.spin_arm_y.setDecimals(4)
        self.spin_arm_y.setValue(float(sensor.lever_arm_b[1]))
        self.spin_arm_y.setPrefix("Yb: ")

        self.spin_arm_z = QDoubleSpinBox()
        self.spin_arm_z.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_arm_z.setRange(-100.0, 100.0)
        self.spin_arm_z.setDecimals(4)
        self.spin_arm_z.setValue(float(sensor.lever_arm_b[2]))
        self.spin_arm_z.setPrefix("Zb: ")

        arm_layout.addWidget(self.spin_arm_x)
        arm_layout.addWidget(self.spin_arm_y)
        arm_layout.addWidget(self.spin_arm_z)
        layout.addWidget(group_arm)

        # Orientación / Inclinación del Sensor (s-frame -> b-frame)
        group_bore = QGroupBox("Inclinación / Orientación del Sensor (s-frame → b-frame)")
        bore_vbox = QVBoxLayout(group_bore)
        bore_vbox.setContentsMargins(8, 4, 8, 6)
        bore_vbox.setSpacing(4)

        conv_layout = QHBoxLayout()
        conv_layout.setSpacing(6)
        lbl_conv = QLabel("Convención:")
        lbl_conv.setStyleSheet("color: #475569; font-weight: 500; font-size: 11px;")
        self.combo_convention = QComboBox()
        self.combo_convention.addItems([
            "Calibración (α, β, γ) [s-frame → b-frame]",
            "Actitud Aeroespacial (Roll, Pitch, Yaw)"
        ])
        self.combo_convention.currentIndexChanged.connect(self._on_convention_changed)
        conv_layout.addWidget(lbl_conv)
        conv_layout.addWidget(self.combo_convention, 1)
        bore_vbox.addLayout(conv_layout)

        bore_layout = QHBoxLayout()
        bore_layout.setSpacing(6)

        b_deg = sensor.boresight_deg
        self.spin_ang1 = QDoubleSpinBox()
        self.spin_ang1.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_ang1.setRange(-360.0, 360.0)
        self.spin_ang1.setDecimals(4)
        self.spin_ang1.setValue(float(b_deg[0]))
        self.spin_ang1.setPrefix("α (X): ")

        self.spin_ang2 = QDoubleSpinBox()
        self.spin_ang2.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_ang2.setRange(-360.0, 360.0)
        self.spin_ang2.setDecimals(4)
        self.spin_ang2.setValue(float(b_deg[1]))
        self.spin_ang2.setPrefix("β (Y): ")

        self.spin_ang3 = QDoubleSpinBox()
        self.spin_ang3.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_ang3.setRange(-360.0, 360.0)
        self.spin_ang3.setDecimals(4)
        self.spin_ang3.setValue(float(b_deg[2]))
        self.spin_ang3.setPrefix("γ (Z): ")

        bore_layout.addWidget(self.spin_ang1)
        bore_layout.addWidget(self.spin_ang2)
        bore_layout.addWidget(self.spin_ang3)
        bore_vbox.addLayout(bore_layout)
        layout.addWidget(group_bore)

        layout.addSpacing(4)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_apply = QPushButton("Aplicar Cambios")
        self.btn_apply.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_apply)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def _on_convention_changed(self, idx: int):
        v1 = self.spin_ang1.value()
        v2 = self.spin_ang2.value()
        v3 = self.spin_ang3.value()

        # Conversión exacta: Roll = -alpha, Pitch = -beta, Yaw = -gamma
        new_v1 = -v1
        new_v2 = -v2
        new_v3 = -v3
        if new_v3 < -180.0:
            new_v3 += 360.0
        elif new_v3 > 180.0:
            new_v3 -= 360.0

        self.spin_ang1.blockSignals(True)
        self.spin_ang2.blockSignals(True)
        self.spin_ang3.blockSignals(True)

        self.spin_ang1.setValue(round(new_v1, 4))
        self.spin_ang2.setValue(round(new_v2, 4))
        self.spin_ang3.setValue(round(new_v3, 4))

        if idx == 0:
            self.spin_ang1.setPrefix("α (X): ")
            self.spin_ang2.setPrefix("β (Y): ")
            self.spin_ang3.setPrefix("γ (Z): ")
        else:
            self.spin_ang1.setPrefix("Roll: ")
            self.spin_ang2.setPrefix("Pitch: ")
            self.spin_ang3.setPrefix("Yaw: ")

        self.spin_ang1.blockSignals(False)
        self.spin_ang2.blockSignals(False)
        self.spin_ang3.blockSignals(False)

    def apply_changes(self):
        self.sensor.name = self.input_name.text().strip() or self.sensor.name
        stype_str = self.combo_type.currentText()
        self.sensor.sensor_type = getattr(SensorType, stype_str, SensorType.OTHER)
        self.sensor.lever_arm_b = np.array(
            [self.spin_arm_x.value(), self.spin_arm_y.value(), self.spin_arm_z.value()],
            dtype=np.float64
        )
        if self.combo_convention.currentIndex() == 1:
            # En pantalla está Roll, Pitch, Yaw -> convertir a alpha, beta, gamma
            r = self.spin_ang1.value()
            p = self.spin_ang2.value()
            y = self.spin_ang3.value()
            self.sensor.set_boresight_from_rpy(r, p, y)
        else:
            self.sensor.boresight_deg = (
                self.spin_ang1.value(),
                self.spin_ang2.value(),
                self.spin_ang3.value()
            )



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

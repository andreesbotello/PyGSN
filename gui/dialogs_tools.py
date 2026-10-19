"""
PyGSN - Floating CAD Transformation Tools (PySide6 / Qt)
========================================================
Cuadros de herramientas flotantes desacoplados (Qt.Tool) para transformación paramétrica
interactiva de chasis y sensores (Mover, Rotar, Escalar).
- Botón "Aplicar" iterativo: ejecuta la transformación sin cerrar el cuadro de diálogo.
- Rotación estrictamente vinculada al plano 2D de la proyección ortogonal activa.
- Barras de título en modo claro nativo Windows y spinboxes limpios sin flechas.
"""

from typing import Callable, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QDoubleSpinBox, QComboBox, QWidget, QAbstractSpinBox,
    QGroupBox
)
from PySide6.QtCore import Qt, QLocale

from gui.theme import set_window_titlebar_light


class BaseToolDialog(QDialog):
    """Clase base para herramientas flotantes no modales con botón 'Aplicar' permanente y punto decimal C."""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setLocale(QLocale.c())
        self.setWindowTitle(title)
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

    def showEvent(self, event):
        super().showEvent(event)
        set_window_titlebar_light(self)


class ToolDialogMoveChassis(BaseToolDialog):
    """Herramienta para trasladar paramétricamente el chasis."""

    def __init__(
        self,
        on_apply: Callable[[float, float, float], None],
        on_center: Callable[[], None],
        parent: Optional[QWidget] = None
    ):
        super().__init__("Mover Chasis - PyGSN", parent)
        self.on_apply = on_apply
        self.on_center = on_center
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        lbl_desc = QLabel("Desplazamiento incremental del chasis:")
        lbl_desc.setStyleSheet("font-weight: bold; color: #0077b6;")
        layout.addWidget(lbl_desc)

        form = QFormLayout()
        form.setVerticalSpacing(6)

        self.spin_dx = QDoubleSpinBox()
        self.spin_dx.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_dx.setRange(-50.0, 50.0)
        self.spin_dx.setDecimals(3)
        self.spin_dx.setValue(0.0)
        form.addRow("ΔXb (Adelante/Atrás):", self.spin_dx)

        self.spin_dy = QDoubleSpinBox()
        self.spin_dy.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_dy.setRange(-50.0, 50.0)
        self.spin_dy.setDecimals(3)
        self.spin_dy.setValue(0.0)
        form.addRow("ΔYb (Derecha/Izquierda):", self.spin_dy)

        self.spin_dz = QDoubleSpinBox()
        self.spin_dz.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_dz.setRange(-50.0, 50.0)
        self.spin_dz.setDecimals(3)
        self.spin_dz.setValue(0.0)
        form.addRow("ΔZb (Abajo/Arriba):", self.spin_dz)

        unit_layout = QHBoxLayout()
        self.combo_unit = QComboBox()
        self.combo_unit.addItems(["metros (m)", "centímetros (cm)"])
        unit_layout.addWidget(self.combo_unit)
        form.addRow("Unidades:", unit_layout)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        self.btn_apply = QPushButton("Aplicar Traslación")
        self.btn_apply.setStyleSheet("background-color: #0077b6; color: white; font-weight: bold;")
        self.btn_apply.setFixedHeight(28)
        self.btn_apply.clicked.connect(self._do_apply)
        btn_layout.addWidget(self.btn_apply)

        self.btn_center = QPushButton("Centrar a [0, 0, 0]")
        self.btn_center.setFixedHeight(28)
        self.btn_center.clicked.connect(self.on_center)
        btn_layout.addWidget(self.btn_center)
        layout.addLayout(btn_layout)

        self.btn_close = QPushButton("Cerrar")
        self.btn_close.setFixedHeight(26)
        self.btn_close.clicked.connect(self.hide)
        layout.addWidget(self.btn_close)

    def _do_apply(self):
        factor = 0.01 if "cm" in self.combo_unit.currentText() else 1.0
        dx = self.spin_dx.value() * factor
        dy = self.spin_dy.value() * factor
        dz = self.spin_dz.value() * factor
        self.on_apply(dx, dy, dz)


class ToolDialogRotateChassis(BaseToolDialog):
    """
    Herramienta para rotar el chasis en el plano ortogonal 2D activo.
    En Superior (S): Rotación alrededor de Zb (Guiñada / Yaw) en plano Xb-Yb (ΔZb = 0).
    En Frontal (F): Rotación alrededor de Xb (Alabeo / Roll) en plano Yb-Zb.
    En Lateral (L): Rotación alrededor de Yb (Cabeceo / Pitch) en plano Xb-Zb.
    """

    def __init__(
        self,
        get_active_view: Callable[[], str],
        on_apply: Callable[[float, str], None],
        parent: Optional[QWidget] = None
    ):
        super().__init__("Rotar Chasis - PyGSN", parent)
        self.get_active_view = get_active_view
        self.on_apply = on_apply
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Banner técnico distintivo para identificar el plano y eje activo
        self.card_info = QFrame()
        self.card_info.setStyleSheet("""
            QFrame {
                background-color: #f0f9ff;
                border: 1px solid #bae6fd;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        card_layout = QVBoxLayout(self.card_info)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(3)

        self.lbl_view_title = QLabel("")
        self.lbl_view_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #0369a1;")
        card_layout.addWidget(self.lbl_view_title)

        self.lbl_axis_desc = QLabel("")
        self.lbl_axis_desc.setStyleSheet("font-size: 10px; font-weight: 500; color: #0284c7;")
        card_layout.addWidget(self.lbl_axis_desc)
        layout.addWidget(self.card_info)

        form = QFormLayout()
        form.setVerticalSpacing(8)

        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_angle.setRange(-360.0, 360.0)
        self.spin_angle.setDecimals(1)
        self.spin_angle.setValue(90.0)
        self.spin_angle.setSuffix(" °")
        form.addRow("Ángulo de Giro (θ):", self.spin_angle)
        layout.addLayout(form)

        quick_box = QGroupBox("Giros Ortogonales Rápidos")
        quick_layout = QHBoxLayout(quick_box)
        quick_layout.setSpacing(8)
        btn_p90 = QPushButton("+90°")
        btn_p90.clicked.connect(lambda: self._quick_rotate(90.0))
        btn_m90 = QPushButton("-90°")
        btn_m90.clicked.connect(lambda: self._quick_rotate(-90.0))
        btn_180 = QPushButton("180°")
        btn_180.clicked.connect(lambda: self._quick_rotate(180.0))
        quick_layout.addWidget(btn_p90)
        quick_layout.addWidget(btn_m90)
        quick_layout.addWidget(btn_180)
        layout.addWidget(quick_box)

        btn_apply = QPushButton("Aplicar Rotación")
        btn_apply.setStyleSheet("background-color: #0077b6; color: white; font-weight: bold;")
        btn_apply.setFixedHeight(28)
        btn_apply.clicked.connect(self._do_apply)
        layout.addWidget(btn_apply)

        btn_close = QPushButton("Cerrar")
        btn_close.setFixedHeight(26)
        btn_close.clicked.connect(self.hide)
        layout.addWidget(btn_close)

        self.refresh_view_context()

    def refresh_view_context(self):
        v = self.get_active_view().upper()
        if v == "S":
            self.lbl_view_title.setText("Plano Ortogonal: Vista Superior (S)")
            self.lbl_axis_desc.setText("Eje de Rotación: Eje Zb (Yaw / Guiñada)")
        elif v == "F":
            self.lbl_view_title.setText("Plano Ortogonal: Vista Frontal (F)")
            self.lbl_axis_desc.setText("Eje de Rotación: Eje Xb (Roll / Alabeo)")
        else:
            self.lbl_view_title.setText("Plano Ortogonal: Vista Lateral (L)")
            self.lbl_axis_desc.setText("Eje de Rotación: Eje Yb (Pitch / Cabeceo)")

    def _quick_rotate(self, angle: float):
        v = self.get_active_view().upper()
        self.on_apply(angle, v)

    def _do_apply(self):
        v = self.get_active_view().upper()
        ang = self.spin_angle.value()
        self.on_apply(ang, v)


class ToolDialogScaleChassis(BaseToolDialog):
    """Herramienta para escalar paramétricamente las dimensiones del chasis."""

    def __init__(
        self,
        on_apply: Callable[[float, float, float], None],
        parent: Optional[QWidget] = None
    ):
        super().__init__("Escalar Chasis - PyGSN", parent)
        self.on_apply = on_apply
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        lbl_desc = QLabel("Escalado dimensional respecto al centroide:")
        lbl_desc.setStyleSheet("font-weight: bold; color: #0077b6;")
        layout.addWidget(lbl_desc)

        form = QFormLayout()
        form.setVerticalSpacing(6)

        self.spin_scale_pct = QDoubleSpinBox()
        self.spin_scale_pct.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_scale_pct.setRange(1.0, 1000.0)
        self.spin_scale_pct.setDecimals(1)
        self.spin_scale_pct.setValue(110.0)
        self.spin_scale_pct.setSuffix(" %")
        form.addRow("Factor Global (%):", self.spin_scale_pct)
        layout.addLayout(form)

        quick_box = QGroupBox("Factores Rápidos")
        quick_layout = QHBoxLayout(quick_box)
        btn_plus10 = QPushButton("+10%")
        btn_plus10.clicked.connect(lambda: self.on_apply(1.10, 1.10, 1.10))
        btn_minus10 = QPushButton("-10%")
        btn_minus10.clicked.connect(lambda: self.on_apply(0.90, 0.90, 0.90))
        btn_double = QPushButton("x2 (+100%)")
        btn_double.clicked.connect(lambda: self.on_apply(2.00, 2.00, 2.00))
        quick_layout.addWidget(btn_plus10)
        quick_layout.addWidget(btn_minus10)
        quick_layout.addWidget(btn_double)
        layout.addWidget(quick_box)

        btn_apply = QPushButton("Aplicar Escala")
        btn_apply.setStyleSheet("background-color: #0077b6; color: white; font-weight: bold;")
        btn_apply.setFixedHeight(28)
        btn_apply.clicked.connect(self._do_apply)
        layout.addWidget(btn_apply)

        btn_close = QPushButton("Cerrar")
        btn_close.setFixedHeight(26)
        btn_close.clicked.connect(self.hide)
        layout.addWidget(btn_close)

    def _do_apply(self):
        f = self.spin_scale_pct.value() / 100.0
        self.on_apply(f, f, f)


class ToolDialogSensorMove(BaseToolDialog):
    """Herramienta para trasladar paramétricamente el lever-arm del sensor activo."""

    def __init__(
        self,
        sensor_code: str,
        on_apply: Callable[[float, float, float], None],
        sensor_name: Optional[str] = None,
        parent: Optional[QWidget] = None
    ):
        disp_name = sensor_name or sensor_code
        super().__init__(f"Mover Sensor {disp_name} - PyGSN", parent)
        self.sensor_code = sensor_code
        self.sensor_name = disp_name
        self.on_apply = on_apply
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        lbl_desc = QLabel(f"Desplazamiento Lever-Arm en b-frame ({disp_name}):")
        lbl_desc.setStyleSheet("font-weight: bold; color: #b45309;")
        layout.addWidget(lbl_desc)

        form = QFormLayout()
        form.setVerticalSpacing(6)

        self.spin_dx = QDoubleSpinBox()
        self.spin_dx.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_dx.setRange(-20.0, 20.0)
        self.spin_dx.setDecimals(6)
        self.spin_dx.setValue(0.0)
        form.addRow("ΔXb (Adelante/Atrás):", self.spin_dx)

        self.spin_dy = QDoubleSpinBox()
        self.spin_dy.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_dy.setRange(-20.0, 20.0)
        self.spin_dy.setDecimals(6)
        self.spin_dy.setValue(0.0)
        form.addRow("ΔYb (Derecha/Izquierda):", self.spin_dy)

        self.spin_dz = QDoubleSpinBox()
        self.spin_dz.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_dz.setRange(-20.0, 20.0)
        self.spin_dz.setDecimals(6)
        self.spin_dz.setValue(0.0)
        form.addRow("ΔZb (Abajo/Arriba):", self.spin_dz)

        self.combo_unit = QComboBox()
        self.combo_unit.addItems(["metros (m)", "centímetros (cm)"])
        form.addRow("Unidades:", self.combo_unit)
        layout.addLayout(form)

        btn_apply = QPushButton("Aplicar a Lever-Arm")
        btn_apply.setStyleSheet("background-color: #b45309; color: white; font-weight: bold;")
        btn_apply.setFixedHeight(28)
        btn_apply.clicked.connect(self._do_apply)
        layout.addWidget(btn_apply)

        btn_close = QPushButton("Cerrar")
        btn_close.setFixedHeight(26)
        btn_close.clicked.connect(self.hide)
        layout.addWidget(btn_close)

    def _do_apply(self):
        factor = 0.01 if "cm" in self.combo_unit.currentText() else 1.0
        dx = self.spin_dx.value() * factor
        dy = self.spin_dy.value() * factor
        dz = self.spin_dz.value() * factor
        self.on_apply(dx, dy, dz)


class ToolDialogSensorRotate(BaseToolDialog):
    """Herramienta para ajustar paramétricamente los ángulos de Boresight del sensor."""

    def __init__(
        self,
        sensor_code: str,
        on_apply: Callable[[float, float, float], None],
        sensor_name: Optional[str] = None,
        parent: Optional[QWidget] = None
    ):
        disp_name = sensor_name or sensor_code
        super().__init__(f"Rotar Boresight {disp_name} - PyGSN", parent)
        self.sensor_code = sensor_code
        self.sensor_name = disp_name
        self.on_apply = on_apply
        self.setFixedWidth(330)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        lbl_desc = QLabel(f"Ajuste Angular Boresight ({disp_name}):")
        lbl_desc.setStyleSheet("font-weight: bold; color: #b45309;")
        layout.addWidget(lbl_desc)

        conv_layout = QHBoxLayout()
        conv_layout.setSpacing(6)
        lbl_conv = QLabel("Convención:")
        lbl_conv.setStyleSheet("color: #475569; font-weight: 500; font-size: 11px;")
        self.combo_convention = QComboBox()
        self.combo_convention.addItems([
            "Calibración (Δα, Δβ, Δγ)",
            "Actitud (ΔRoll, ΔPitch, ΔYaw)"
        ])
        self.combo_convention.currentIndexChanged.connect(self._on_convention_changed)
        conv_layout.addWidget(lbl_conv)
        conv_layout.addWidget(self.combo_convention, 1)
        layout.addLayout(conv_layout)

        form = QFormLayout()
        form.setVerticalSpacing(6)

        self.spin_a1 = QDoubleSpinBox()
        self.spin_a1.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_a1.setRange(-180.0, 180.0)
        self.spin_a1.setDecimals(6)
        self.spin_a1.setValue(0.0)
        self.spin_a1.setSuffix(" °")
        self.lbl_row1 = QLabel("Δα (Eje X):")
        form.addRow(self.lbl_row1, self.spin_a1)

        self.spin_a2 = QDoubleSpinBox()
        self.spin_a2.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_a2.setRange(-180.0, 180.0)
        self.spin_a2.setDecimals(6)
        self.spin_a2.setValue(0.0)
        self.spin_a2.setSuffix(" °")
        self.lbl_row2 = QLabel("Δβ (Eje Y):")
        form.addRow(self.lbl_row2, self.spin_a2)

        self.spin_a3 = QDoubleSpinBox()
        self.spin_a3.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spin_a3.setRange(-180.0, 180.0)
        self.spin_a3.setDecimals(6)
        self.spin_a3.setValue(0.0)
        self.spin_a3.setSuffix(" °")
        self.lbl_row3 = QLabel("Δγ (Eje Z):")
        form.addRow(self.lbl_row3, self.spin_a3)
        layout.addLayout(form)

        btn_apply = QPushButton("Aplicar a Boresight")
        btn_apply.setStyleSheet("background-color: #b45309; color: white; font-weight: bold;")
        btn_apply.setFixedHeight(28)
        btn_apply.clicked.connect(self._do_apply)
        layout.addWidget(btn_apply)

        btn_close = QPushButton("Cerrar")
        btn_close.setFixedHeight(26)
        btn_close.clicked.connect(self.hide)
        layout.addWidget(btn_close)

    def _on_convention_changed(self, idx: int):
        if idx == 0:
            self.lbl_row1.setText("Δα (Eje X):")
            self.lbl_row2.setText("Δβ (Eje Y):")
            self.lbl_row3.setText("Δγ (Eje Z):")
        else:
            self.lbl_row1.setText("ΔRoll (Alabeo):")
            self.lbl_row2.setText("ΔPitch (Cabeceo):")
            self.lbl_row3.setText("ΔYaw (Guiñada):")

    def _do_apply(self):
        v1 = self.spin_a1.value()
        v2 = self.spin_a2.value()
        v3 = self.spin_a3.value()
        if self.combo_convention.currentIndex() == 1:
            # Entrada es Roll, Pitch, Yaw -> delta a (alpha, beta, gamma) es -delta(rpy)
            da = -v1
            db = -v2
            dc = -v3
        else:
            da = v1
            db = v2
            dc = v3
        self.on_apply(da, db, dc)

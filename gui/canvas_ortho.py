"""
PyGSN - Orthogonal CAD Canvas (PySide6 / Qt)
============================================
Lienzo técnico vectorial para las 3 Vistas Ortogonales 2D:
- Superior (Planta): Xb (Adelante, Rojo R) vs Yb (Derecha, Verde G)
- Frontal (Alzado):  Yb (Derecha, Verde G) vs -Zb (Arriba, Azul B)
- Lateral (Perfil):  Xb (Adelante, Rojo R) vs -Zb (Arriba, Azul B)

Soporta modo 4 cuadrantes [[S, F], [L, Leyenda]] y vista única ampliada [S, F, L],
con zoom mediante rueda de ratón, paneo fluido y menú contextual nativo.
"""

from typing import Optional, Dict, Tuple
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QToolButton,
    QLabel, QMenu, QFrame
)
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QWheelEvent,
    QMouseEvent, QPainterPath
)

from core.models import Platform, Sensor, SensorType
from gui.theme import (
    COLOR_CANVAS_BG, COLOR_GRID_MAJOR, COLOR_GRID_MINOR,
    COLOR_AXIS_X, COLOR_AXIS_Y, COLOR_AXIS_Z, COLOR_PLATFORM_BODY,
    COLOR_ORIGIN, COLOR_CENTROID, COLOR_SENSOR_GNSS, COLOR_SENSOR_INS,
    COLOR_SENSOR_CAM, COLOR_SENSOR_DEFAULT, COLOR_TEXT_PRIMARY, COLOR_TEXT_MUTED
)


def _to_qcolor(c: Tuple[int, int, int, int]) -> QColor:
    return QColor(c[0], c[1], c[2], c[3])


class OrthoCADCanvas(QWidget):
    """Lienzo técnico 2D individual para una proyección ortogonal (S, F o L)."""

    def __init__(self, view_type: str = "S", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.view_type = view_type.upper()  # "S", "F", "L"
        self.platform: Optional[Platform] = None

        self.scale: float = 80.0  # Píxeles por metro
        self.pan_x: float = 0.0   # Desplazamiento horizontal en píxeles
        self.pan_y: float = 0.0   # Desplazamiento vertical en píxeles

        self._dragging: bool = False
        self._last_mouse_pos = QPointF(0, 0)

        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def set_platform(self, platform: Optional[Platform]):
        self.platform = platform
        self.update()

    def center_origin(self):
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def center_centroid(self):
        if not self.platform or not self.platform.sensors:
            self.center_origin()
            return
        pts = [s.lever_arm_b for s in self.platform.sensors.values()]
        mean_pt = np.mean(pts, axis=0)
        # Proyectar según vista
        if self.view_type == "S":
            # Xb adelante (arriba en pantalla), Yb derecha
            cx, cy = mean_pt[1], mean_pt[0]
        elif self.view_type == "F":
            # Yb derecha, -Zb arriba
            cx, cy = mean_pt[1], -mean_pt[2]
        else: # L
            # Xb adelante (derecha o izquierda), -Zb arriba
            cx, cy = mean_pt[0], -mean_pt[2]
        self.pan_x = -cx * self.scale
        self.pan_y = cy * self.scale
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 0.85
        self.scale = max(10.0, min(2000.0, self.scale * factor))
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._dragging = True
            self._last_mouse_pos = event.position()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            delta = event.position() - self._last_mouse_pos
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self._last_mouse_pos = event.position()
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        act_orig = menu.addAction("Centrar al Origen [0, 0]")
        act_orig.triggered.connect(self.center_origin)
        act_cent = menu.addAction("Centrar al Centroide")
        act_cent.triggered.connect(self.center_centroid)
        menu.exec(self.mapToGlobal(pos))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()
        cx = w / 2.0 + self.pan_x
        cy = h / 2.0 + self.pan_y

        # Fondo
        painter.fillRect(0, 0, w, h, _to_qcolor(COLOR_CANVAS_BG))

        # Cuadrícula métrica CAD
        self._draw_grid(painter, cx, cy, w, h)

        # Ejes coordenados b-frame RGB
        self._draw_axes(painter, cx, cy)

        # Geometría de plataforma (chasis) si está configurado
        if self.platform and self.platform.has_dimensions:
            self._draw_chassis(painter, cx, cy)

        # Sensores montados
        if self.platform:
            self._draw_sensors(painter, cx, cy)

        # Título de vista
        self._draw_overlay_title(painter)

    def _draw_grid(self, p: QPainter, cx: float, cy: float, w: int, h: int):
        # Cuadrícula menor (0.1m o 0.5m) y mayor (1.0m o 5.0m)
        step_m = 1.0 if self.scale >= 40 else 5.0
        step_px = step_m * self.scale

        pen_minor = QPen(_to_qcolor(COLOR_GRID_MINOR), 1, Qt.DotLine)
        pen_major = QPen(_to_qcolor(COLOR_GRID_MAJOR), 1, Qt.SolidLine)

        # Líneas verticales
        start_x = (cx % step_px) - step_px
        x = start_x
        while x < w + step_px:
            p.setPen(pen_major if abs((x - cx) % (step_px * 5)) < 1.0 else pen_minor)
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            x += step_px

        # Líneas horizontales
        start_y = (cy % step_px) - step_px
        y = start_y
        while y < h + step_px:
            p.setPen(pen_major if abs((y - cy) % (step_px * 5)) < 1.0 else pen_minor)
            p.drawLine(QPointF(0, y), QPointF(w, y))
            y += step_px

    def _draw_axes(self, p: QPainter, cx: float, cy: float):
        axis_len = 70.0
        arrow_size = 6.0

        if self.view_type == "S":
            # Vista Superior (Planta):
            # +Xb Adelante -> Hacia ARRIBA (-Y pantalla) [Rojo R]
            # +Yb Derecha  -> Hacia DERECHA (+X pantalla) [Verde G]
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_X), 2))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy - axis_len))
            p.drawText(QPointF(cx + 4, cy - axis_len + 12), "+Xb (Adelante)")

            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Y), 2))
            p.drawLine(QPointF(cx, cy), QPointF(cx + axis_len, cy))
            p.drawText(QPointF(cx + axis_len - 15, cy - 6), "+Yb (Der)")

        elif self.view_type == "F":
            # Vista Frontal (Alzado):
            # +Yb Derecha -> Hacia DERECHA (+X pantalla) [Verde G]
            # -Zb Arriba  -> Hacia ARRIBA (-Y pantalla) [Azul B]
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Y), 2))
            p.drawLine(QPointF(cx, cy), QPointF(cx + axis_len, cy))
            p.drawText(QPointF(cx + axis_len - 15, cy - 6), "+Yb (Der)")

            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Z), 2))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy - axis_len))
            p.drawText(QPointF(cx + 4, cy - axis_len + 12), "-Zb (Arriba)")

        elif self.view_type == "L":
            # Vista Lateral (Perfil):
            # +Xb Adelante -> Hacia DERECHA (+X pantalla) [Rojo R]
            # -Zb Arriba   -> Hacia ARRIBA (-Y pantalla) [Azul B]
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_X), 2))
            p.drawLine(QPointF(cx, cy), QPointF(cx + axis_len, cy))
            p.drawText(QPointF(cx + axis_len - 15, cy - 6), "+Xb (Adelante)")

            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Z), 2))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy - axis_len))
            p.drawText(QPointF(cx + 4, cy - axis_len + 12), "-Zb (Arriba)")

        # Origen [0, 0, 0]
        p.setPen(QPen(_to_qcolor(COLOR_ORIGIN), 1))
        p.setBrush(QBrush(_to_qcolor(COLOR_ORIGIN)))
        p.drawEllipse(QPointF(cx, cy), 3, 3)
        p.drawText(QPointF(cx + 6, cy + 14), "PLA [0,0,0]")

    def _draw_chassis(self, p: QPainter, cx: float, cy: float):
        l, w, h = self.platform.length_m, self.platform.width_m, self.platform.height_m
        pen_body = QPen(_to_qcolor(COLOR_PLATFORM_BODY), 2, Qt.DashLine)
        p.setPen(pen_body)
        p.setBrush(Qt.NoBrush)

        if self.view_type == "S":
            # Xb adelante (alto), Yb derecha (ancho)
            rect_w = w * self.scale
            rect_h = l * self.scale
            p.drawRect(QRectF(cx - rect_w / 2.0, cy - rect_h / 2.0, rect_w, rect_h))
        elif self.view_type == "F":
            rect_w = w * self.scale
            rect_h = h * self.scale
            p.drawRect(QRectF(cx - rect_w / 2.0, cy - rect_h / 2.0, rect_w, rect_h))
        elif self.view_type == "L":
            rect_w = l * self.scale
            rect_h = h * self.scale
            p.drawRect(QRectF(cx - rect_w / 2.0, cy - rect_h / 2.0, rect_w, rect_h))

    def _draw_sensors(self, p: QPainter, cx: float, cy: float):
        font = QFont("Segoe UI", 9)
        p.setFont(font)

        for code, s in self.platform.sensors.items():
            arm = s.lever_arm_b
            if self.view_type == "S":
                sx = cx + arm[1] * self.scale
                sy = cy - arm[0] * self.scale
            elif self.view_type == "F":
                sx = cx + arm[1] * self.scale
                sy = cy + arm[2] * self.scale  # arm[2] es +Zb abajo
            elif self.view_type == "L":
                sx = cx + arm[0] * self.scale
                sy = cy + arm[2] * self.scale

            stype_str = s.sensor_type.value
            if "GNSS" in stype_str:
                col = _to_qcolor(COLOR_SENSOR_GNSS)
                p.setPen(QPen(col, 2))
                p.setBrush(QBrush(col))
                # Dibujar rombo
                path = QPainterPath()
                path.moveTo(sx, sy - 5)
                path.lineTo(sx + 5, sy)
                path.lineTo(sx, sy + 5)
                path.lineTo(sx - 5, sy)
                path.closeSubpath()
                p.drawPath(path)
            elif "INS" in stype_str or "IMU" in stype_str:
                col = _to_qcolor(COLOR_SENSOR_INS)
                p.setPen(QPen(col, 2))
                p.setBrush(QBrush(col))
                p.drawRect(QRectF(sx - 4, sy - 4, 8, 8))
            elif "CAM" in stype_str:
                col = _to_qcolor(COLOR_SENSOR_CAM)
                p.setPen(QPen(col, 2))
                p.setBrush(QBrush(col))
                path = QPainterPath()
                path.moveTo(sx, sy - 5)
                path.lineTo(sx + 5, sy + 4)
                path.lineTo(sx - 5, sy + 4)
                path.closeSubpath()
                p.drawPath(path)
            else:
                col = _to_qcolor(COLOR_SENSOR_DEFAULT)
                p.setPen(QPen(col, 2))
                p.setBrush(QBrush(col))
                p.drawEllipse(QPointF(sx, sy), 4, 4)

            p.setPen(QPen(_to_qcolor(COLOR_TEXT_PRIMARY), 1))
            p.drawText(QPointF(sx + 7, sy + 4), code)

    def _draw_overlay_title(self, p: QPainter):
        p.setPen(QPen(_to_qcolor(COLOR_TEXT_MUTED), 1))
        titles = {
            "S": "Superior (Planta: Xb vs Yb)",
            "F": "Frontal (Alzado: Yb vs -Zb)",
            "L": "Lateral (Perfil: Xb vs -Zb)"
        }
        title = titles.get(self.view_type, self.view_type)
        p.drawText(QPointF(10, 20), title)


class OrthoCADWidget(QWidget):
    """Contenedor de la pestaña de plataforma que gestiona modo 4 cuadrantes o vista única."""

    def __init__(self, platform: Platform, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.platform = platform

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)

        # Barra superior compacta con los 4 botones pequeños en la esquina superior derecha
        bar_layout = QHBoxLayout()
        bar_layout.setContentsMargins(4, 2, 4, 2)
        lbl_info = QLabel(f"Plataforma: {platform.name} [{platform.platform_type}]")
        lbl_info.setStyleSheet("color: #00b4d8; font-weight: bold;")
        bar_layout.addWidget(lbl_info)
        bar_layout.addStretch()

        self.btn_quad = QToolButton()
        self.btn_quad.setText("/")
        self.btn_quad.setToolTip("Alternar Cuadrícula 4 Cuadrantes / Vista Única")
        self.btn_quad.setFixedSize(22, 20)
        self.btn_quad.clicked.connect(self.toggle_view_mode)
        bar_layout.addWidget(self.btn_quad)

        self.btn_s = QToolButton()
        self.btn_s.setText("S")
        self.btn_s.setToolTip("Vista Superior (Planta)")
        self.btn_s.setFixedSize(22, 20)
        self.btn_s.clicked.connect(lambda: self.set_single_view("S"))
        bar_layout.addWidget(self.btn_s)

        self.btn_f = QToolButton()
        self.btn_f.setText("F")
        self.btn_f.setToolTip("Vista Frontal (Alzado)")
        self.btn_f.setFixedSize(22, 20)
        self.btn_f.clicked.connect(lambda: self.set_single_view("F"))
        bar_layout.addWidget(self.btn_f)

        self.btn_l = QToolButton()
        self.btn_l.setText("L")
        self.btn_l.setToolTip("Vista Lateral (Perfil)")
        self.btn_l.setFixedSize(22, 20)
        self.btn_l.clicked.connect(lambda: self.set_single_view("L"))
        bar_layout.addWidget(self.btn_l)

        main_layout.addLayout(bar_layout)

        # Área de vistas
        self.container = QWidget()
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(2)

        self.canvas_top = OrthoCADCanvas("S")
        self.canvas_front = OrthoCADCanvas("F")
        self.canvas_side = OrthoCADCanvas("L")
        self.canvas_single = OrthoCADCanvas("S")

        # Leyenda
        self.legend_box = QFrame()
        self.legend_box.setStyleSheet("background-color: #14161b; border: 1px solid #2d313d;")
        leg_layout = QVBoxLayout(self.legend_box)
        leg_title = QLabel("Convención de Ejes b-frame:")
        leg_title.setStyleSheet("font-weight: bold; color: #ffd166;")
        leg_layout.addWidget(leg_title)
        leg_layout.addWidget(QLabel("  [-] Xb Adelante: Rojo (R)"))
        leg_layout.addWidget(QLabel("  [-] Yb Derecha:  Verde (G)"))
        leg_layout.addWidget(QLabel("  [-] Zb Abajo:    Azul (B)"))
        leg_layout.addSpacing(6)
        leg_sens = QLabel("Sensores:")
        leg_sens.setStyleSheet("font-weight: bold; color: #ffd166;")
        leg_layout.addWidget(leg_sens)
        leg_layout.addWidget(QLabel("  [*] GNSS (Amarillo)"))
        leg_layout.addWidget(QLabel("  [*] INS/IMU (Menta)"))
        leg_layout.addWidget(QLabel("  [*] Cámara (Rosa)"))
        leg_layout.addStretch()

        self.canvases = [self.canvas_top, self.canvas_front, self.canvas_side, self.canvas_single]
        for c in self.canvases:
            c.set_platform(platform)

        # Configurar 4 cuadrantes
        self.grid_layout.addWidget(self.canvas_top, 0, 0)
        self.grid_layout.addWidget(self.canvas_front, 0, 1)
        self.grid_layout.addWidget(self.canvas_side, 1, 0)
        self.grid_layout.addWidget(self.legend_box, 1, 1)

        self.canvas_single.hide()
        self.grid_layout.addWidget(self.canvas_single, 0, 0, 2, 2)

        main_layout.addWidget(self.container)
        self.is_quad_mode = True

    def toggle_view_mode(self):
        if self.is_quad_mode:
            self.set_single_view("S")
        else:
            self.set_quad_mode()

    def set_quad_mode(self):
        self.is_quad_mode = True
        self.canvas_single.hide()
        self.canvas_top.show()
        self.canvas_front.show()
        self.canvas_side.show()
        self.legend_box.show()
        self.redraw_all()

    def set_single_view(self, view_key: str):
        self.is_quad_mode = False
        self.canvas_top.hide()
        self.canvas_front.hide()
        self.canvas_side.hide()
        self.legend_box.hide()
        self.canvas_single.view_type = view_key.upper()
        self.canvas_single.show()
        self.canvas_single.update()

    def center_origin(self):
        for c in self.canvases:
            c.center_origin()

    def center_centroid(self):
        for c in self.canvases:
            c.center_centroid()

    def redraw_all(self):
        for c in self.canvases:
            c.set_platform(self.platform)
            c.update()

"""
PyGSN - Orthogonal CAD Canvas (PySide6 / Qt)
============================================
Lienzo técnico vectorial para las 3 Vistas Ortogonales 2D:
- Superior (Planta): Xb (Adelante, Rojo R) vs Yb (Derecha, Verde G)
- Frontal (Alzado):  Yb (Derecha, Verde G) vs -Zb (Arriba, Azul B)
- Lateral (Perfil):  Xb (Adelante, Rojo R) vs -Zb (Arriba, Azul B)

Soporta modo 4 cuadrantes [[S, F], [L, Leyenda]] y vista única ampliada [S, F, L]
gestionados mediante QStackedWidget:
- Margen y separación visual nítida entre cuadrantes.
- En 4 cuadrantes: paneo lateral bloqueado (alineación ortogonal) y zoom sincronizado.
- Cuadrícula métrica adaptativa (1mm a 5m) con cotas numéricas puras en cada casilla.
- Regla gráfica de escala técnica en la esquina inferior izquierda.
- Límite superior de 5 metros de alto para el campo de trabajo visible.
- Herramienta de dibujo de chasis por vértices (polígono) y caja con snapping automático a 5 cm.
"""

from typing import Optional, Dict, Tuple, List
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QToolButton,
    QLabel, QMenu, QFrame, QStackedWidget
)
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
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

    scale_changed = Signal(float)
    chassis_dimensions_changed = Signal(float, float, float) # length, width, height

    # Pasos de cuadrícula dinámicos disponibles en metros
    GRID_STEPS_M: List[float] = [0.001, 0.005, 0.010, 0.050, 0.100, 0.500, 1.000, 5.000]

    def __init__(self, view_type: str = "S", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.view_type = view_type.upper()  # "S", "F", "L"
        self.platform: Optional[Platform] = None

        self.scale: float = 80.0  # Píxeles por metro
        self.pan_x: float = 0.0   # Desplazamiento horizontal en píxeles
        self.pan_y: float = 0.0   # Desplazamiento vertical en píxeles
        self.allow_pan: bool = True  # Bloqueado en 4Q para mantener alineación ortogonal

        # Herramientas y Snapping
        self.active_tool: str = "Mover" # Modo por defecto
        self.snap_step_m: Optional[float] = 0.05 # 5 cm por defecto

        self._dragging: bool = False
        self._last_mouse_pos = QPointF(0, 0)
        self._mouse_press_pos = QPointF(0, 0)

        # Estado de dibujo de chasis (vértices punto a punto y arrastre de caja)
        self._polygon_vertices: List[Tuple[float, float]] = []
        self._current_mouse_pos: Optional[QPointF] = None
        self._box_start_pos: Optional[QPointF] = None
        self._box_preview_dims: Optional[Tuple[float, float, float]] = None

        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def set_tool(self, tool_name: str):
        """Actualiza la herramienta activa y el cursor del lienzo."""
        self.active_tool = tool_name
        self._polygon_vertices.clear()
        self._box_preview_dims = None
        if tool_name == "Mover":
            self.setCursor(Qt.OpenHandCursor if self.allow_pan else Qt.ArrowCursor)
        elif tool_name == "Dibujar":
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def set_snap_step(self, step_m: Optional[float]):
        """Configura el paso de ajuste métrico (None para desactivado)."""
        self.snap_step_m = step_m
        self.update()

    def set_platform(self, platform: Optional[Platform]):
        self.platform = platform
        self.update()

    def set_scale(self, new_scale: float):
        """Ajusta la escala respetando el límite superior de 5m de campo vertical."""
        h_viewport = max(50.0, float(self.height()))
        min_scale = h_viewport / 5.0
        max_scale = 10000.0
        self.scale = max(min_scale, min(max_scale, new_scale))
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
        if self.view_type == "S":
            cx, cy = mean_pt[1], mean_pt[0]
        elif self.view_type == "F":
            cx, cy = mean_pt[1], -mean_pt[2]
        else: # L
            cx, cy = mean_pt[0], -mean_pt[2]
        self.pan_x = -cx * self.scale
        self.pan_y = cy * self.scale
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 0.85

        # Límite superior: la altura visible del lienzo no puede exceder 5.0 metros
        # viewport_height_m = h / scale <= 5.0 m ==> min_scale = h / 5.0
        h_viewport = max(50.0, float(self.height()))
        min_scale = h_viewport / 5.0
        max_scale = 10000.0

        new_scale = max(min_scale, min(max_scale, self.scale * factor))
        if abs(new_scale - self.scale) > 1e-4:
            self.scale = new_scale
            self.scale_changed.emit(self.scale)
            self.update()
        event.accept()

    def _snap_coord(self, val: float) -> float:
        if self.snap_step_m and self.snap_step_m > 0:
            return round(val / self.snap_step_m) * self.snap_step_m
        return val

    def _screen_to_body_2d(self, pos: QPointF, cx: float, cy: float) -> Tuple[float, float]:
        """Convierte coordenadas de pantalla a coordenadas métricas de la proyección activa."""
        du = (pos.x() - cx) / self.scale
        dv = (pos.y() - cy) / self.scale
        if self.view_type == "S":
            # Horizontal: +Yb (Derecha), Vertical: +Xb (Arriba en pantalla)
            xb = -dv
            yb = du
            return xb, yb
        elif self.view_type == "F":
            # Horizontal: +Yb (Derecha), Vertical: -Zb (Arriba en pantalla => dv hacia abajo es +Zb)
            yb = du
            zb = dv
            return yb, zb
        else: # L
            # Horizontal: +Xb (Adelante/Derecha), Vertical: -Zb (Arriba => dv hacia abajo es +Zb)
            xb = du
            zb = dv
            return xb, zb

    def _body_2d_to_screen(self, u: float, v: float, cx: float, cy: float) -> QPointF:
        """Convierte coordenadas métricas de proyección a píxeles de pantalla."""
        if self.view_type == "S":
            # u = Xb, v = Yb
            return QPointF(cx + v * self.scale, cy - u * self.scale)
        elif self.view_type == "F":
            # u = Yb, v = Zb
            return QPointF(cx + u * self.scale, cy + v * self.scale)
        else: # L
            # u = Xb, v = Zb
            return QPointF(cx + u * self.scale, cy + v * self.scale)

    def mousePressEvent(self, event: QMouseEvent):
        self._mouse_press_pos = event.position()
        if event.button() == Qt.LeftButton:
            if self.active_tool == "Mover":
                if self.allow_pan:
                    self._dragging = True
                    self._last_mouse_pos = event.position()
                    self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
            elif self.active_tool == "Dibujar":
                self._box_start_pos = event.position()
                w, h = float(self.width()), float(self.height())
                cx = w / 2.0 + self.pan_x
                cy = h / 2.0 + self.pan_y
                u_raw, v_raw = self._screen_to_body_2d(event.position(), cx, cy)
                u_snap = self._snap_coord(u_raw)
                v_snap = self._snap_coord(v_raw)

                # Si hace clic cerca del primer vértice (distancia < 15px en pantalla) y hay >= 3 vértices: cerrar polígono
                if len(self._polygon_vertices) >= 3:
                    first_pt = self._polygon_vertices[0]
                    first_px = self._body_2d_to_screen(first_pt[0], first_pt[1], cx, cy)
                    dist_px = np.hypot(event.position().x() - first_px.x(), event.position().y() - first_px.y())
                    if dist_px < 15.0:
                        self._close_polygon()
                        event.accept()
                        return

                self._polygon_vertices.append((u_snap, v_snap))
                self.update()
                event.accept()
                return

        elif event.button() in (Qt.MiddleButton, Qt.RightButton):
            if self.allow_pan:
                self._dragging = True
                self._last_mouse_pos = event.position()
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self._current_mouse_pos = event.position()
        if self._dragging:
            delta = event.position() - self._last_mouse_pos
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self._last_mouse_pos = event.position()
            self.update()
            event.accept()
        elif self.active_tool == "Dibujar":
            # Vista previa dinámica mientras mueve el ratón
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._dragging:
            self._dragging = False
            self.setCursor(Qt.OpenHandCursor if (self.active_tool == "Mover" and self.allow_pan) else Qt.ArrowCursor)
            event.accept()
            return
        elif self.active_tool == "Dibujar":
            # Comprobar si fue un arrastre de caja envolvente desde el origen
            if self._box_start_pos is not None:
                drag_dist = np.hypot(event.position().x() - self._box_start_pos.x(), event.position().y() - self._box_start_pos.y())
                # Si arrastró más de 25 píxeles y no tenía una cadena de vértices abierta previa, crea la caja directamente
                if drag_dist > 25.0 and len(self._polygon_vertices) <= 1:
                    w, h = float(self.width()), float(self.height())
                    cx = w / 2.0 + self.pan_x
                    cy = h / 2.0 + self.pan_y
                    u1, v1 = self._screen_to_body_2d(self._box_start_pos, cx, cy)
                    u2, v2 = self._screen_to_body_2d(event.position(), cx, cy)
                    u_min, u_max = min(u1, u2), max(u1, u2)
                    v_min, v_max = min(v1, v2), max(v1, v2)
                    du = max(0.05, abs(u_max - u_min))
                    dv = max(0.05, abs(v_max - v_min))
                    du = self._snap_coord(du)
                    dv = self._snap_coord(dv)
                    self._commit_box_dims(du, dv)
                    self._polygon_vertices.clear()
                    self._box_start_pos = None
                    self.update()
                    event.accept()
                    return
            self._box_start_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.active_tool == "Dibujar":
            if len(self._polygon_vertices) >= 3:
                self._close_polygon()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def _commit_box_dims(self, dim_u: float, dim_v: float):
        if not self.platform:
            return
        prev_l = self.platform.length_m if self.platform.has_dimensions else 2.00
        prev_w = self.platform.width_m if self.platform.has_dimensions else 1.00
        prev_h = self.platform.height_m if self.platform.has_dimensions else 0.50

        if self.view_type == "S":
            # u = Xb (Largo), v = Yb (Ancho)
            l, w, h = dim_u, dim_v, prev_h
        elif self.view_type == "F":
            # u = Yb (Ancho), v = Zb (Alto)
            l, w, h = prev_l, dim_u, dim_v
        else: # L
            # u = Xb (Largo), v = Zb (Alto)
            l, w, h = dim_u, prev_w, dim_v

        self.platform.length_m = round(l, 4)
        self.platform.width_m = round(w, 4)
        self.platform.height_m = round(h, 4)
        self.platform.has_dimensions = True
        self.chassis_dimensions_changed.emit(self.platform.length_m, self.platform.width_m, self.platform.height_m)

    def _close_polygon(self):
        """Cierra el polígono actual, guarda los vértices y actualiza la caja envolvente."""
        if len(self._polygon_vertices) < 3 or not self.platform:
            self._polygon_vertices.clear()
            self.update()
            return

        pts = np.array(self._polygon_vertices)
        u_min, u_max = float(np.min(pts[:, 0])), float(np.max(pts[:, 0]))
        v_min, v_max = float(np.min(pts[:, 1])), float(np.max(pts[:, 1]))

        extent_u = max(0.05, abs(u_max - u_min))
        extent_v = max(0.05, abs(v_max - v_min))

        prev_l = self.platform.length_m if self.platform.has_dimensions else 2.00
        prev_w = self.platform.width_m if self.platform.has_dimensions else 1.00
        prev_h = self.platform.height_m if self.platform.has_dimensions else 0.50

        if self.view_type == "S":
            l = extent_u
            w = extent_v
            h = prev_h
            # En vista Superior guardamos los vértices del polígono chasis [[xb, yb], ...]
            self.platform.chassis_polygon = [[float(p[0]), float(p[1])] for p in pts]
        elif self.view_type == "F":
            w = extent_u
            h = extent_v
            l = prev_l
        else: # L
            l = extent_u
            h = extent_v
            w = prev_w

        self.platform.length_m = round(l, 4)
        self.platform.width_m = round(w, 4)
        self.platform.height_m = round(h, 4)
        self.platform.has_dimensions = True

        self.chassis_dimensions_changed.emit(self.platform.length_m, self.platform.width_m, self.platform.height_m)
        self._polygon_vertices.clear()
        self.update()

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

        # 1. Fondo técnico de ingeniería
        painter.fillRect(0, 0, w, h, _to_qcolor(COLOR_CANVAS_BG))

        # 2. Cuadrícula métrica CAD adaptativa con cotas numéricas puras en cada casilla
        self._draw_grid(painter, cx, cy, w, h)

        # 3. Ejes perimetrales infinitos con rótulos
        self._draw_axes(painter, cx, cy)

        # 4. Geometría del chasis (caja envolvente o polígono guardado)
        if self.platform and self.platform.has_dimensions:
            self._draw_chassis(painter, cx, cy)

        # 5. Previsualización de dibujo interactivo de polígono / chasis
        if self.active_tool == "Dibujar":
            self._draw_drawing_preview(painter, cx, cy, w, h)

        # 6. Sensores montados
        if self.platform:
            self._draw_sensors(painter, cx, cy)

        # 7. Regla gráfica técnica de escala en la esquina inferior izquierda
        self._draw_scale_ruler(painter, w, h)

        # 8. Título técnico de la proyección ortogonal
        self._draw_overlay_title(painter)

        # 9. Borde de cuadrante nítido para delimitar vistas
        painter.setPen(QPen(QColor(222, 226, 230), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(0.5, 0.5, float(w) - 1.0, float(h) - 1.0))

    def _draw_grid(self, p: QPainter, cx: float, cy: float, w: int, h: int):
        """Dibuja la cuadrícula técnica con pasos [1mm..5m] y números de cota en cada casilla."""
        step_m = 5.0
        for s in self.GRID_STEPS_M:
            if s * self.scale >= 35.0:
                step_m = s
                break

        step_px = step_m * self.scale
        pen_minor = QPen(_to_qcolor(COLOR_GRID_MINOR), 1, Qt.DotLine)
        pen_major = QPen(_to_qcolor(COLOR_GRID_MAJOR), 1, Qt.SolidLine)

        font_coord = QFont("Segoe UI", 7)
        p.setFont(font_coord)
        col_text = QColor(148, 163, 184, 210) # Pizarra 400 técnico legible sin saturar

        # Determinar rango horizontal
        k_start = int(np.floor((0.0 - cx) / step_px)) - 1
        k_end = int(np.ceil((float(w) - cx) / step_px)) + 1

        for k in range(k_start, k_end + 1):
            x = cx + k * step_px
            if -step_px <= x <= w + step_px:
                is_major = (k % 5 == 0)
                p.setPen(pen_major if is_major else pen_minor)
                p.drawLine(QPointF(x, 0), QPointF(x, h))

                # Rótulo de coordenada numérica horizontal sin unidad
                if k != 0 and (is_major or step_px >= 65.0):
                    val = k * step_m
                    if step_m >= 1.0:
                        lbl = f"{val:.0f}" if abs(val - round(val)) < 1e-4 else f"{val:.1f}"
                    elif step_m >= 0.1:
                        lbl = f"{val:.1f}"
                    elif step_m >= 0.01:
                        lbl = f"{val:.2f}"
                    else:
                        lbl = f"{val:.3f}"
                    if lbl.endswith(".0"):
                        lbl = lbl[:-2]

                    p.setPen(QPen(col_text, 1))
                    p.drawText(QPointF(x + 3, h - 6), lbl)

        # Determinar rango vertical
        m_start = int(np.floor((0.0 - cy) / step_px)) - 1
        m_end = int(np.ceil((float(h) - cy) / step_px)) + 1

        for m in range(m_start, m_end + 1):
            y = cy + m * step_px
            if -step_px <= y <= h + step_px:
                is_major = (m % 5 == 0)
                p.setPen(pen_major if is_major else pen_minor)
                p.drawLine(QPointF(0, y), QPointF(w, y))

                # Rótulo de coordenada numérica vertical (inversión de eje de pantalla)
                if m != 0 and (is_major or step_px >= 65.0):
                    val = -m * step_m
                    if step_m >= 1.0:
                        lbl = f"{val:.0f}" if abs(val - round(val)) < 1e-4 else f"{val:.1f}"
                    elif step_m >= 0.1:
                        lbl = f"{val:.1f}"
                    elif step_m >= 0.01:
                        lbl = f"{val:.2f}"
                    else:
                        lbl = f"{val:.3f}"
                    if lbl.endswith(".0"):
                        lbl = lbl[:-2]

                    p.setPen(QPen(col_text, 1))
                    p.drawText(QPointF(6, y - 3), lbl)

    def _draw_axes(self, p: QPainter, cx: float, cy: float):
        w, h = float(self.width()), float(self.height())
        font_axis = QFont("Segoe UI", 9, QFont.Bold)
        p.setFont(font_axis)

        if self.view_type == "S":
            # Eje Vertical: +Xb Adelante (Arriba), -Xb Atrás (Abajo) [Rojo R]
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_X), 1.5))
            p.drawLine(QPointF(cx, 0), QPointF(cx, h))

            # Eje Horizontal: +Yb Derecha (Derecha), -Yb Izquierda (Izquierda) [Verde G]
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Y), 1.5))
            p.drawLine(QPointF(0, cy), QPointF(w, cy))

            # Rótulos perimetrales en los bordes
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_X)))
            p.drawText(QPointF(cx + 6, 18), "+Xb (Adelante)")
            p.setPen(QPen(QColor(180, 80, 80, 180)))
            p.drawText(QPointF(cx + 6, h - 8), "-Xb (Atrás)")

            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Y)))
            p.drawText(QPointF(w - 95, cy - 6), "+Yb (Derecha)")
            p.setPen(QPen(QColor(40, 140, 60, 180)))
            p.drawText(QPointF(8, cy - 6), "-Yb (Izquierda)")

        elif self.view_type == "F":
            # Eje Horizontal: +Yb Derecha, -Yb Izquierda [Verde G]
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Y), 1.5))
            p.drawLine(QPointF(0, cy), QPointF(w, cy))

            # Eje Vertical: -Zb Arriba, +Zb Abajo [Azul B]
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Z), 1.5))
            p.drawLine(QPointF(cx, 0), QPointF(cx, h))

            # Rótulos perimetrales en los bordes
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Z)))
            p.drawText(QPointF(cx + 6, 18), "-Zb (Arriba)")
            p.setPen(QPen(QColor(60, 110, 190, 180)))
            p.drawText(QPointF(cx + 6, h - 8), "+Zb (Abajo)")

            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Y)))
            p.drawText(QPointF(w - 95, cy - 6), "+Yb (Derecha)")
            p.setPen(QPen(QColor(40, 140, 60, 180)))
            p.drawText(QPointF(8, cy - 6), "-Yb (Izquierda)")

        elif self.view_type == "L":
            # Eje Horizontal: +Xb Adelante, -Xb Atrás [Rojo R]
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_X), 1.5))
            p.drawLine(QPointF(0, cy), QPointF(w, cy))

            # Eje Vertical: -Zb Arriba, +Zb Abajo [Azul B]
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Z), 1.5))
            p.drawLine(QPointF(cx, 0), QPointF(cx, h))

            # Rótulos perimetrales en los bordes
            p.setPen(QPen(_to_qcolor(COLOR_AXIS_Z)))
            p.drawText(QPointF(cx + 6, 18), "-Zb (Arriba)")
            p.setPen(QPen(QColor(60, 110, 190, 180)))
            p.drawText(QPointF(cx + 6, h - 8), "+Zb (Abajo)")

            p.setPen(QPen(_to_qcolor(COLOR_AXIS_X)))
            p.drawText(QPointF(w - 95, cy - 6), "+Xb (Adelante)")
            p.setPen(QPen(QColor(180, 80, 80, 180)))
            p.drawText(QPointF(8, cy - 6), "-Xb (Atrás)")

        # Origen PLA [0, 0, 0] limpio y discreto
        p.setPen(QPen(_to_qcolor(COLOR_ORIGIN), 1))
        p.setBrush(QBrush(_to_qcolor(COLOR_ORIGIN)))
        p.drawEllipse(QPointF(cx, cy), 3, 3)
        font_pla = QFont("Segoe UI", 8)
        p.setFont(font_pla)
        p.drawText(QPointF(cx + 4, cy + 12), "PLA [0,0,0]")

    def _draw_chassis(self, p: QPainter, cx: float, cy: float):
        l = self.platform.length_m
        w = self.platform.width_m
        h = self.platform.height_m

        pen_body = QPen(_to_qcolor(COLOR_PLATFORM_BODY), 2, Qt.DashLine)
        p.setPen(pen_body)
        p.setBrush(QBrush(QColor(2, 132, 199, 25)))

        # 1. Si existe un polígono personalizado y estamos en vista Superior ("S"):
        if self.view_type == "S" and self.platform.chassis_polygon and len(self.platform.chassis_polygon) >= 3:
            path = QPainterPath()
            pts = self.platform.chassis_polygon
            p0 = self._body_2d_to_screen(pts[0][0], pts[0][1], cx, cy)
            path.moveTo(p0)
            for pt in pts[1:]:
                path.lineTo(self._body_2d_to_screen(pt[0], pt[1], cx, cy))
            path.closeSubpath()
            p.drawPath(path)

            # Caja envolvente en línea de trazos tenue
            p.setPen(QPen(QColor(2, 132, 199, 100), 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            rect_w = w * self.scale
            rect_h = l * self.scale
            p.drawRect(QRectF(cx - rect_w / 2.0, cy - rect_h / 2.0, rect_w, rect_h))
        elif self.view_type == "S":
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

        # 2. Líneas envolventes proyectadas hacia los márgenes
        p.setPen(QPen(QColor(2, 132, 199, 50), 1, Qt.DashDotLine))
        if self.view_type == "S":
            rw = w * self.scale
            rl = l * self.scale
            p.drawLine(QPointF(cx - rw / 2.0, 0), QPointF(cx - rw / 2.0, self.height()))
            p.drawLine(QPointF(cx + rw / 2.0, 0), QPointF(cx + rw / 2.0, self.height()))
            p.drawLine(QPointF(0, cy - rl / 2.0), QPointF(self.width(), cy - rl / 2.0))
            p.drawLine(QPointF(0, cy + rl / 2.0), QPointF(self.width(), cy + rl / 2.0))
        elif self.view_type == "F":
            rw = w * self.scale
            rh = h * self.scale
            p.drawLine(QPointF(cx - rw / 2.0, 0), QPointF(cx - rw / 2.0, self.height()))
            p.drawLine(QPointF(cx + rw / 2.0, 0), QPointF(cx + rw / 2.0, self.height()))
            p.drawLine(QPointF(0, cy - rh / 2.0), QPointF(self.width(), cy - rh / 2.0))
            p.drawLine(QPointF(0, cy + rh / 2.0), QPointF(self.width(), cy + rh / 2.0))
        elif self.view_type == "L":
            rl = l * self.scale
            rh = h * self.scale
            p.drawLine(QPointF(cx - rl / 2.0, 0), QPointF(cx - rl / 2.0, self.height()))
            p.drawLine(QPointF(cx + rl / 2.0, 0), QPointF(cx + rl / 2.0, self.height()))
            p.drawLine(QPointF(0, cy - rh / 2.0), QPointF(self.width(), cy - rh / 2.0))
            p.drawLine(QPointF(0, cy + rh / 2.0), QPointF(self.width(), cy + rh / 2.0))

    def _draw_drawing_preview(self, p: QPainter, cx: float, cy: float, w: int, h: int):
        """Muestra los vértices trazados y la línea guía con snapping activo."""
        pen_poly = QPen(QColor(0, 119, 182, 230), 2, Qt.SolidLine)
        p.setPen(pen_poly)
        p.setBrush(Qt.NoBrush)

        num_pts = len(self._polygon_vertices)
        if num_pts > 0:
            path = QPainterPath()
            p0 = self._body_2d_to_screen(self._polygon_vertices[0][0], self._polygon_vertices[0][1], cx, cy)
            path.moveTo(p0)
            for pt in self._polygon_vertices[1:]:
                path.lineTo(self._body_2d_to_screen(pt[0], pt[1], cx, cy))
            p.drawPath(path)

            # Dibujar nodos de vértices
            p.setBrush(QBrush(QColor(0, 119, 182)))
            for i, pt in enumerate(self._polygon_vertices):
                screen_pt = self._body_2d_to_screen(pt[0], pt[1], cx, cy)
                radius = 4 if i > 0 else 5
                p.drawEllipse(screen_pt, radius, radius)

        # Segmento elástico al ratón actual con snapping
        if self._current_mouse_pos is not None:
            u_raw, v_raw = self._screen_to_body_2d(self._current_mouse_pos, cx, cy)
            u_snap = self._snap_coord(u_raw)
            v_snap = self._snap_coord(v_raw)
            snapped_px = self._body_2d_to_screen(u_snap, v_snap, cx, cy)

            if num_pts > 0:
                last_pt = self._body_2d_to_screen(self._polygon_vertices[-1][0], self._polygon_vertices[-1][1], cx, cy)
                p.setPen(QPen(QColor(0, 119, 182, 160), 1.5, Qt.DashLine))
                p.drawLine(last_pt, snapped_px)

            # Cruz de cursor de snapping
            p.setPen(QPen(QColor(220, 38, 38, 200), 1))
            p.drawLine(QPointF(snapped_px.x() - 6, snapped_px.y()), QPointF(snapped_px.x() + 6, snapped_px.y()))
            p.drawLine(QPointF(snapped_px.x(), snapped_px.y() - 6), QPointF(snapped_px.x(), snapped_px.y() + 6))

            # HUD de coordenadas junto al cursor
            p.setPen(QPen(QColor(15, 23, 42, 220), 1))
            font_hud = QFont("Segoe UI", 8)
            p.setFont(font_hud)
            snap_txt = f"[{u_snap:+.2f}, {v_snap:+.2f}] (Clic: Vértice | Doble-clic: Cerrar)"
            p.drawText(QPointF(snapped_px.x() + 10, snapped_px.y() - 6), snap_txt)

    def _draw_sensors(self, p: QPainter, cx: float, cy: float):
        font = QFont("Segoe UI", 9)
        p.setFont(font)

        for code, s in self.platform.sensors.items():
            bx, by, bz = s.lever_arm_b[0], s.lever_arm_b[1], s.lever_arm_b[2]

            if self.view_type == "S":
                sx = cx + by * self.scale
                sy = cy - bx * self.scale
            elif self.view_type == "F":
                sx = cx + by * self.scale
                sy = cy + bz * self.scale
            else: # L
                sx = cx + bx * self.scale
                sy = cy + bz * self.scale

            stype = s.sensor_type.value
            if "GNSS" in stype:
                col = _to_qcolor(COLOR_SENSOR_GNSS)
            elif "INS" in stype or "IMU" in stype:
                col = _to_qcolor(COLOR_SENSOR_INS)
            elif "CAM" in stype:
                col = _to_qcolor(COLOR_SENSOR_CAM)
            else:
                col = _to_qcolor(COLOR_SENSOR_DEFAULT)

            p.setPen(QPen(col, 2))
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(sx, sy), 4, 4)

            p.setPen(QPen(_to_qcolor(COLOR_TEXT_PRIMARY), 1))
            p.drawText(QPointF(sx + 6, sy - 4), f"{code}")

    def _draw_scale_ruler(self, p: QPainter, w: int, h: int):
        """Dibuja en la esquina inferior izquierda la regla gráfica técnica con unidades activas."""
        ruler_candidates = [0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 2.00, 5.00]
        chosen_d = 1.00
        for d in ruler_candidates:
            px_len = d * self.scale
            if px_len >= 55.0:
                chosen_d = d
                break

        ruler_px = chosen_d * self.scale
        if ruler_px < 25.0:
            ruler_px = 25.0

        if chosen_d < 0.01:
            lbl_unit = f"{int(chosen_d * 1000)} mm"
        elif chosen_d < 1.0:
            lbl_unit = f"{int(chosen_d * 100)} cm"
        else:
            lbl_unit = f"{chosen_d:g} m"

        x0 = 14.0
        y0 = float(h) - 20.0

        # Fondo sutil para máxima legibilidad
        badge_w = max(ruler_px + 16.0, 75.0)
        badge_h = 22.0
        p.setPen(QPen(QColor(203, 213, 225, 220), 1))
        p.setBrush(QBrush(QColor(255, 255, 255, 220)))
        p.drawRoundedRect(QRectF(x0 - 6, y0 - 14, badge_w, badge_h), 3, 3)

        # Barra de escala horizontal con marcas en los extremos
        pen_ruler = QPen(QColor(30, 41, 59, 230), 1.5)
        p.setPen(pen_ruler)
        p.drawLine(QPointF(x0, y0), QPointF(x0 + ruler_px, y0))
        p.drawLine(QPointF(x0, y0 - 4), QPointF(x0, y0 + 4))
        p.drawLine(QPointF(x0 + ruler_px, y0 - 4), QPointF(x0 + ruler_px, y0 + 4))

        # Texto centrado sobre el segmento
        font_ruler = QFont("Segoe UI", 8, QFont.Bold)
        p.setFont(font_ruler)
        p.setPen(QPen(QColor(30, 41, 59, 240), 1))
        ruler_rect = QRectF(x0, y0 - 15, ruler_px, 12)
        p.drawText(ruler_rect, Qt.AlignCenter, lbl_unit)

    def _draw_overlay_title(self, p: QPainter):
        p.setPen(QPen(_to_qcolor(COLOR_TEXT_MUTED), 1))
        font_ov = QFont("Segoe UI", 9)
        p.setFont(font_ov)
        titles = {
            "S": "Superior (Planta: Xb vs Yb)",
            "F": "Frontal (Alzado: Yb vs -Zb)",
            "L": "Lateral (Perfil: Xb vs -Zb)"
        }
        title = titles.get(self.view_type, self.view_type)
        p.drawText(QPointF(10, 20), title)


class OrthoCADWidget(QWidget):
    """Contenedor de la pestaña de plataforma que gestiona modo 4 cuadrantes o vista única con QStackedWidget."""

    chassis_updated = Signal()

    def __init__(self, platform: Platform, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.platform = platform

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Barra superior compacta con botones [/], [S], [F], [L]
        bar_layout = QHBoxLayout()
        bar_layout.setContentsMargins(4, 2, 4, 2)
        self.lbl_info = QLabel(f"Plataforma: {platform.name} [{platform.platform_type}]")
        self.lbl_info.setStyleSheet("color: #0077b6; font-weight: bold;")
        bar_layout.addWidget(self.lbl_info)
        bar_layout.addStretch()

        self.btn_quad = QToolButton()
        self.btn_quad.setText("/")
        self.btn_quad.setToolTip("Alternar Cuadrícula 4 Cuadrantes / Vista Única")
        self.btn_quad.setFixedSize(26, 22)
        self.btn_quad.clicked.connect(self.toggle_view_mode)
        bar_layout.addWidget(self.btn_quad)

        self.btn_s = QToolButton()
        self.btn_s.setText("S")
        self.btn_s.setCheckable(True)
        self.btn_s.setToolTip("Vista Superior (Planta)")
        self.btn_s.setFixedSize(22, 22)
        self.btn_s.clicked.connect(lambda: self.set_single_view("S"))
        bar_layout.addWidget(self.btn_s)

        self.btn_f = QToolButton()
        self.btn_f.setText("F")
        self.btn_f.setCheckable(True)
        self.btn_f.setToolTip("Vista Frontal (Alzado)")
        self.btn_f.setFixedSize(22, 22)
        self.btn_f.clicked.connect(lambda: self.set_single_view("F"))
        bar_layout.addWidget(self.btn_f)

        self.btn_l = QToolButton()
        self.btn_l.setText("L")
        self.btn_l.setCheckable(True)
        self.btn_l.setToolTip("Vista Lateral (Perfil)")
        self.btn_l.setFixedSize(22, 22)
        self.btn_l.clicked.connect(lambda: self.set_single_view("L"))
        bar_layout.addWidget(self.btn_l)

        main_layout.addLayout(bar_layout)

        # Contenedor apilado para alternar limpiamente entre 4 cuadrantes y vista única
        self.stack = QStackedWidget()

        # Página 0: 4 Cuadrantes con márgenes y separación visual nítida
        self.quad_container = QWidget()
        self.quad_layout = QGridLayout(self.quad_container)
        self.quad_layout.setContentsMargins(6, 6, 6, 6)
        self.quad_layout.setSpacing(6)

        self.canvas_top = OrthoCADCanvas("S")
        self.canvas_front = OrthoCADCanvas("F")
        self.canvas_side = OrthoCADCanvas("L")
        self.canvas_single = OrthoCADCanvas("S")

        # Leyenda técnica
        self.legend_box = QFrame()
        self.legend_box.setStyleSheet("background-color: #ffffff; border: 1px solid #dee2e6; border-radius: 4px; padding: 6px;")
        leg_layout = QVBoxLayout(self.legend_box)
        leg_title = QLabel("Convención de Ejes b-frame:")
        leg_title.setStyleSheet("font-weight: bold; color: #0077b6;")
        leg_layout.addWidget(leg_title)
        leg_layout.addWidget(QLabel("  [-] Xb Adelante: Rojo (R)"))
        leg_layout.addWidget(QLabel("  [-] Yb Derecha:  Verde (G)"))
        leg_layout.addWidget(QLabel("  [-] Zb Abajo:    Azul (B)"))
        leg_layout.addSpacing(6)
        leg_sens = QLabel("Sensores:")
        leg_sens.setStyleSheet("font-weight: bold; color: #b45309;")
        leg_layout.addWidget(leg_sens)
        leg_layout.addWidget(QLabel("  [*] GNSS (Ámbar)"))
        leg_layout.addWidget(QLabel("  [*] INS/IMU (Esmeralda)"))
        leg_layout.addWidget(QLabel("  [*] Cámara (Magenta)"))
        leg_layout.addStretch()

        self.quad_layout.addWidget(self.canvas_top, 0, 0)
        self.quad_layout.addWidget(self.canvas_front, 0, 1)
        self.quad_layout.addWidget(self.canvas_side, 1, 0)
        self.quad_layout.addWidget(self.legend_box, 1, 1)

        self.quad_layout.setRowStretch(0, 1)
        self.quad_layout.setRowStretch(1, 1)
        self.quad_layout.setColumnStretch(0, 1)
        self.quad_layout.setColumnStretch(1, 1)

        self.stack.addWidget(self.quad_container) # Índice 0
        self.stack.addWidget(self.canvas_single)   # Índice 1

        main_layout.addWidget(self.stack)

        self.canvases = [self.canvas_top, self.canvas_front, self.canvas_side, self.canvas_single]
        for c in self.canvases:
            c.set_platform(platform)
            c.chassis_dimensions_changed.connect(self._on_chassis_drawn)

        # Sincronización continua de escala de zoom entre los 3 cuadrantes S, F, L
        self.canvas_top.scale_changed.connect(lambda s: self._on_quad_scale_changed(s, self.canvas_top))
        self.canvas_front.scale_changed.connect(lambda s: self._on_quad_scale_changed(s, self.canvas_front))
        self.canvas_side.scale_changed.connect(lambda s: self._on_quad_scale_changed(s, self.canvas_side))

        self.is_quad_mode = True
        self.set_quad_mode()

    def _on_quad_scale_changed(self, new_scale: float, sender: OrthoCADCanvas):
        """Sincroniza la escala en los tres cuadrantes para mantener concordancia espacial."""
        for c in (self.canvas_top, self.canvas_front, self.canvas_side):
            if c is not sender:
                c.scale = new_scale
                c.update()

    def _on_chassis_drawn(self, l: float, w: float, h: float):
        for c in self.canvases:
            c.update()
        self.chassis_updated.emit()

    def set_active_tool(self, tool_name: str):
        for c in self.canvases:
            c.set_tool(tool_name)

    def set_snap_step_m(self, step_m: Optional[float]):
        for c in self.canvases:
            c.set_snap_step(step_m)

    def toggle_view_mode(self):
        if self.is_quad_mode:
            self.set_single_view("S")
        else:
            self.set_quad_mode()

    def set_quad_mode(self):
        self.is_quad_mode = True
        self.stack.setCurrentIndex(0)
        self.btn_quad.setText("/")
        self.btn_quad.setToolTip("Cambiar a Vista Única")

        # En 4 cuadrantes, bloquear desplazamiento lateral (paneo) para garantizar alineación ortogonal
        self.canvas_top.allow_pan = False
        self.canvas_front.allow_pan = False
        self.canvas_side.allow_pan = False
        self.canvas_top.center_origin()
        self.canvas_front.center_origin()
        self.canvas_side.center_origin()

        # Deshabilitar botones S, F, L individuales
        self.btn_s.setEnabled(False)
        self.btn_f.setEnabled(False)
        self.btn_l.setEnabled(False)
        self.btn_s.setChecked(False)
        self.btn_f.setChecked(False)
        self.btn_l.setChecked(False)
        self.redraw_all()

    def set_single_view(self, view_key: str):
        self.is_quad_mode = False
        self.stack.setCurrentIndex(1)
        self.btn_quad.setText("4Q")
        self.btn_quad.setToolTip("Cambiar a 4 Cuadrantes")

        # En vista única ampliada, permitir paneo fluido y habilitar botones S, F, L
        self.canvas_single.allow_pan = True
        self.btn_s.setEnabled(True)
        self.btn_f.setEnabled(True)
        self.btn_l.setEnabled(True)
        self.btn_s.setChecked(view_key == "S")
        self.btn_f.setChecked(view_key == "F")
        self.btn_l.setChecked(view_key == "L")
        self.canvas_single.view_type = view_key.upper()
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

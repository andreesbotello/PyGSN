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
from core.rotations import sensor_to_body_matrix
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
    sensor_placed = Signal(str, float, float, float) # code, x, y, z
    sensor_moved = Signal(str, float, float, float)
    sensor_clicked = Signal(str) # code del sensor clickeado

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
        self.is_editing: bool = False # Flag estricto de sesión de edición activa
        self.active_tool: str = "Navegar" # Modo por defecto
        self.snap_step_m: Optional[float] = 0.05 # 5 cm por defecto
        self.editing_sensor_code: Optional[str] = None # Sensor activo en edición si aplica
        self.selected_sensor_code: Optional[str] = None # Sensor seleccionado para inspección visual

        self._dragging: bool = False
        self._moving_chassis: bool = False
        self._moving_sensor: bool = False
        self._chassis_moved: bool = False
        self._dragging_vertex_idx: Optional[int] = None
        self._hovered_vertex_idx: Optional[int] = None
        self._vertex_moved: bool = False
        self._drag_start_bounds: Optional[Dict[str, float]] = None
        self._drag_start_polygon: Optional[List[List[float]]] = None
        self._last_mouse_pos = QPointF(0, 0)
        self._mouse_press_pos = QPointF(0, 0)

        # Objetos de renderizado vectorial en caché para alto rendimiento (60+ FPS)
        self._pen_grid_minor = QPen(_to_qcolor(COLOR_GRID_MINOR), 1, Qt.DotLine)
        self._pen_grid_major = QPen(_to_qcolor(COLOR_GRID_MAJOR), 1, Qt.SolidLine)
        self._font_grid = QFont("Segoe UI", 7)
        self._pen_grid_text = QPen(QColor(148, 163, 184, 210), 1)
        self._font_axis = QFont("Segoe UI", 9, QFont.Bold)
        self._pen_axis_x = QPen(_to_qcolor(COLOR_AXIS_X), 1.5)
        self._pen_axis_y = QPen(_to_qcolor(COLOR_AXIS_Y), 1.5)
        self._pen_axis_z = QPen(_to_qcolor(COLOR_AXIS_Z), 1.5)

        # Estado de dibujo de chasis (vértices punto a punto y arrastre de caja)
        self._polygon_vertices: List[Tuple[float, float]] = []
        self._current_mouse_pos: Optional[QPointF] = None
        self._box_start_pos: Optional[QPointF] = None
        self._box_preview_dims: Optional[Tuple[float, float, float]] = None

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def keyPressEvent(self, event):
        """Gestiona navegación por flechas de teclado y borrado de último vértice con Backspace."""
        key = event.key()

        # 1. Borrado de último vértice dibujado con Backspace o Delete
        if key in (Qt.Key_Backspace, Qt.Key_Delete):
            if self.active_tool == "Dibujar" and len(self._polygon_vertices) > 0:
                self._polygon_vertices.pop()
                self.update()
                event.accept()
                return

        # 2. Desplazamiento del workspace mediante las flechas del teclado
        step_base_m = self.snap_step_m if (self.snap_step_m and self.snap_step_m > 0) else 0.05
        mult = 5.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0
        delta_px = step_base_m * mult * self.scale

        if key == Qt.Key_Up:
            self.pan_y += delta_px
            self.update()
            event.accept()
            return
        elif key == Qt.Key_Down:
            self.pan_y -= delta_px
            self.update()
            event.accept()
            return
        elif key == Qt.Key_Left:
            self.pan_x += delta_px
            self.update()
            event.accept()
            return
        elif key == Qt.Key_Right:
            self.pan_x -= delta_px
            self.update()
            event.accept()
            return

        super().keyPressEvent(event)

    def set_tool(self, tool_name: str):
        """Actualiza la herramienta activa y el cursor del lienzo."""
        self.active_tool = tool_name
        self._polygon_vertices.clear()
        self._box_preview_dims = None
        self._dragging_vertex_idx = None
        self._hovered_vertex_idx = None
        self._vertex_moved = False
        self._drag_start_bounds = None
        self._drag_start_polygon = None
        if self.is_editing and tool_name == "Mover":
            self.setCursor(Qt.OpenHandCursor)
        elif self.is_editing and tool_name == "Dibujar":
            self.setCursor(Qt.CrossCursor)
        elif self.is_editing and tool_name == "Vértices":
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.OpenHandCursor if self.allow_pan else Qt.ArrowCursor)
        self.update()

    def set_editing_mode(self, enabled: bool):
        """Activa o desactiva las capacidades de edición interactiva."""
        self.is_editing = enabled
        self._moving_chassis = False
        self._dragging = False
        self._polygon_vertices.clear()
        self._box_start_pos = None
        self._box_preview_dims = None
        self._dragging_vertex_idx = None
        self._hovered_vertex_idx = None
        self._vertex_moved = False
        if not enabled:
            self.active_tool = "Navegar"
            self.editing_sensor_code = None
            self.setCursor(Qt.OpenHandCursor if self.allow_pan else Qt.ArrowCursor)
        else:
            if self.active_tool == "Mover":
                self.setCursor(Qt.OpenHandCursor)
            elif self.active_tool == "Dibujar":
                self.setCursor(Qt.CrossCursor)
            elif self.active_tool == "Vértices":
                self.setCursor(Qt.ArrowCursor)
            else:
                self.setCursor(Qt.OpenHandCursor if self.allow_pan else Qt.ArrowCursor)
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

    def set_selected_sensor(self, code: Optional[str]):
        """Establece o deselecciona el sensor enfocado visualmente en el lienzo."""
        if self.selected_sensor_code != code:
            self.selected_sensor_code = code
            self.update()

    def _get_sensor_at_pos(self, pos: QPointF) -> Optional[str]:
        """Detecta si la posición del puntero en pantalla coincide con un sensor montado (radio 12px)."""
        if not self.platform or not self.platform.sensors:
            return None
        w, h = float(self.width()), float(self.height())
        cx = w / 2.0 + self.pan_x
        cy = h / 2.0 + self.pan_y
        for code, s in self.platform.sensors.items():
            bx, by, bz = s.lever_arm_b[0], s.lever_arm_b[1], s.lever_arm_b[2]
            if self.view_type == "S":
                scr_pos = QPointF(cx + by * self.scale, cy - bx * self.scale)
            elif self.view_type == "F":
                scr_pos = QPointF(cx + by * self.scale, cy + bz * self.scale)
            else:  # L
                scr_pos = QPointF(cx + bx * self.scale, cy + bz * self.scale)
            if np.hypot(pos.x() - scr_pos.x(), pos.y() - scr_pos.y()) <= 12.0:
                return code
        return None

    def zoom_to_sensor(self, xb: float, yb: float, zb: float, target_scale: Optional[float] = 220.0):
        """Enfoca y hace zoom sobre las coordenadas métricas 3D de un sensor en b-frame."""
        if target_scale is not None:
            self.scale = target_scale
        else:
            self.scale = max(self.scale, 200.0)

        if self.view_type == "S":
            cx, cy = yb, xb
        elif self.view_type == "F":
            cx, cy = yb, -zb
        else: # L
            cx, cy = xb, -zb

        self.pan_x = -cx * self.scale
        self.pan_y = cy * self.scale
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 0.85

        # Límite superior: la altura visible del lienzo no puede exceder 5.0 metros
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
            # Comprobación de selección interactiva de sensor por clic
            clicked_code = self._get_sensor_at_pos(event.position())
            if clicked_code:
                self.selected_sensor_code = clicked_code
                self.sensor_clicked.emit(clicked_code)
                self.update()
                # Si no estamos en sesión de edición de este sensor con herramienta Mover, capturar clic aquí
                if not (self.is_editing and self.allow_pan and self.active_tool == "Mover" and self.editing_sensor_code == clicked_code):
                    event.accept()
                    return

            # Si estamos en modo edición y la vista permite interacción activa (no 4Q)
            if self.is_editing and self.allow_pan:
                if self.active_tool == "Mover":
                    # Si estamos editando un sensor, verificar si hace clic cerca del sensor para arrastrarlo
                    if self.editing_sensor_code and self.platform and self.editing_sensor_code in self.platform.sensors:
                        sens = self.platform.sensors[self.editing_sensor_code]
                        w, h = float(self.width()), float(self.height())
                        cx = w / 2.0 + self.pan_x
                        cy = h / 2.0 + self.pan_y
                        bx, by, bz = sens.lever_arm_b[0], sens.lever_arm_b[1], sens.lever_arm_b[2]
                        if self.view_type == "S":
                            scr_pos = QPointF(cx + by * self.scale, cy - bx * self.scale)
                        elif self.view_type == "F":
                            scr_pos = QPointF(cx + by * self.scale, cy + bz * self.scale)
                        else:  # L
                            scr_pos = QPointF(cx + bx * self.scale, cy + bz * self.scale)
                        if np.hypot(event.position().x() - scr_pos.x(), event.position().y() - scr_pos.y()) <= 16.0:
                            self._moving_sensor = True
                            self._last_mouse_pos = event.position()
                            self.setCursor(Qt.ClosedHandCursor)
                            event.accept()
                            return

                    # Si hay chasis definido, el arrastre traslada la geometría del chasis
                    if self.platform and self.platform.has_dimensions:
                        self._moving_chassis = True
                        self._chassis_moved = False
                        self._last_mouse_pos = event.position()
                        self.setCursor(Qt.ClosedHandCursor)
                        event.accept()
                        return
                    else:
                        self._dragging = True
                        self._last_mouse_pos = event.position()
                        self.setCursor(Qt.ClosedHandCursor)
                        event.accept()
                        return

                elif self.active_tool == "Vértices":
                    if self.platform and self.platform.has_dimensions:
                        self.platform.ensure_polygon()
                        w, h = float(self.width()), float(self.height())
                        cx = w / 2.0 + self.pan_x
                        cy = h / 2.0 + self.pan_y
                        pos = event.position()
                        verts = self._get_view_vertices()
                        for idx, (u, v, _) in enumerate(verts):
                            scr_pt = self._body_2d_to_screen(u, v, cx, cy)
                            if np.hypot(pos.x() - scr_pt.x(), pos.y() - scr_pt.y()) <= 14.0:
                                self._dragging_vertex_idx = idx
                                self._vertex_moved = False
                                self._drag_start_bounds = dict(self.platform.get_bounding_box())
                                self._drag_start_polygon = [list(p) for p in self.platform.chassis_polygon] if self.platform.chassis_polygon else None
                                self.setCursor(Qt.CrossCursor)
                                self.update()
                                event.accept()
                                return

                elif self.active_tool == "Dibujar":
                    # Si se está editando un sensor, ubicarlo directamente en la coordenada con snap
                    if self.editing_sensor_code and self.platform and self.editing_sensor_code in self.platform.sensors:
                        w, h = float(self.width()), float(self.height())
                        cx = w / 2.0 + self.pan_x
                        cy = h / 2.0 + self.pan_y
                        u_raw, v_raw = self._screen_to_body_2d(event.position(), cx, cy)
                        u_snap = self._snap_coord(u_raw)
                        v_snap = self._snap_coord(v_raw)
                        sens = self.platform.sensors[self.editing_sensor_code]
                        arm = list(sens.lever_arm_b)
                        if self.view_type == "S":
                            arm[0] = round(u_snap, 4)
                            arm[1] = round(v_snap, 4)
                        elif self.view_type == "F":
                            arm[1] = round(u_snap, 4)
                            arm[2] = round(v_snap, 4)
                        else:  # L
                            arm[0] = round(u_snap, 4)
                            arm[2] = round(v_snap, 4)
                        sens.lever_arm_b = np.array(arm, dtype=np.float64)
                        self.sensor_placed.emit(sens.code, float(arm[0]), float(arm[1]), float(arm[2]))
                        self.update()
                        event.accept()
                        return

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

            # Si no está en edición activa o la herramienta no capturó el clic,
            # pero la vista permite paneo (modo vista única), arrastrar la cámara
            if self.allow_pan:
                self._dragging = True
                self._last_mouse_pos = event.position()
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
            else:
                # En 4Q (allow_pan == False), no permitir mover chasis ni arrastre de cámara
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

        # 1. Arrastre interactivo de vértices del polígono (Requerimiento Y - Vistas S, F, L)
        if self.is_editing and self.allow_pan and self.active_tool == "Vértices":
            if self._dragging_vertex_idx is not None and self.platform and self.platform.has_dimensions:
                w, h = float(self.width()), float(self.height())
                cx = w / 2.0 + self.pan_x
                cy = h / 2.0 + self.pan_y
                u_raw, v_raw = self._screen_to_body_2d(event.position(), cx, cy)
                u_snap = self._snap_coord(u_raw)
                v_snap = self._snap_coord(v_raw)

                if self.view_type == "S":
                    self.platform.ensure_polygon()
                    if self.platform.chassis_polygon and 0 <= self._dragging_vertex_idx < len(self.platform.chassis_polygon):
                        self.platform.chassis_polygon[self._dragging_vertex_idx] = [round(u_snap, 4), round(v_snap, 4)]
                        pts = np.array(self.platform.chassis_polygon)
                        self.platform.length_m = round(float(np.max(pts[:, 0]) - np.min(pts[:, 0])), 4)
                        self.platform.width_m = round(float(np.max(pts[:, 1]) - np.min(pts[:, 1])), 4)
                        self.platform.chassis_center_b[0] = round(float(np.mean(pts[:, 0])), 4)
                        self.platform.chassis_center_b[1] = round(float(np.mean(pts[:, 1])), 4)
                        self._vertex_moved = True
                        self.update()
                        event.accept()
                        return
                elif self.view_type == "F":
                    self._apply_vertex_drag_front(self._dragging_vertex_idx, u_snap, v_snap)
                    self._vertex_moved = True
                    self.update()
                    event.accept()
                    return
                elif self.view_type == "L":
                    self._apply_vertex_drag_lateral(self._dragging_vertex_idx, u_snap, v_snap)
                    self._vertex_moved = True
                    self.update()
                    event.accept()
                    return
            else:
                # Detección de hover sobre vértices para feedback visual (Vistas S, F, L)
                w, h = float(self.width()), float(self.height())
                cx = w / 2.0 + self.pan_x
                cy = h / 2.0 + self.pan_y
                found_idx = None
                if self.platform and self.platform.has_dimensions:
                    pos = event.position()
                    verts = self._get_view_vertices()
                    for idx, (u, v, _) in enumerate(verts):
                        scr_pt = self._body_2d_to_screen(u, v, cx, cy)
                        if np.hypot(pos.x() - scr_pt.x(), pos.y() - scr_pt.y()) <= 14.0:
                            found_idx = idx
                            break
                if found_idx != self._hovered_vertex_idx:
                    self._hovered_vertex_idx = found_idx
                    self.setCursor(Qt.PointingHandCursor if found_idx is not None else Qt.ArrowCursor)
                    self.update()

        # 2. Arrastre de sensor con ratón
        if self.is_editing and self.allow_pan and self._moving_sensor and self.editing_sensor_code and self.platform:
            sens = self.platform.sensors.get(self.editing_sensor_code)
            if sens:
                w, h = float(self.width()), float(self.height())
                cx = w / 2.0 + self.pan_x
                cy = h / 2.0 + self.pan_y
                u_now, v_now = self._screen_to_body_2d(event.position(), cx, cy)
                u_snap = self._snap_coord(u_now)
                v_snap = self._snap_coord(v_now)
                arm = list(sens.lever_arm_b)
                if self.view_type == "S":
                    arm[0] = round(u_snap, 4)
                    arm[1] = round(v_snap, 4)
                elif self.view_type == "F":
                    arm[1] = round(u_snap, 4)
                    arm[2] = round(v_snap, 4)
                else:  # L
                    arm[0] = round(u_snap, 4)
                    arm[2] = round(v_snap, 4)
                sens.lever_arm_b = np.array(arm, dtype=np.float64)
                self.sensor_moved.emit(sens.code, float(arm[0]), float(arm[1]), float(arm[2]))
                self.update()
                event.accept()
                return

        # 3. Traslación del chasis completo
        if self.is_editing and self.allow_pan and self._moving_chassis and self.platform and self.platform.has_dimensions:
            w, h = float(self.width()), float(self.height())
            cx = w / 2.0 + self.pan_x
            cy = h / 2.0 + self.pan_y
            u_prev, v_prev = self._screen_to_body_2d(self._last_mouse_pos, cx, cy)
            u_now, v_now = self._screen_to_body_2d(event.position(), cx, cy)
            du = u_now - u_prev
            dv = v_now - v_prev

            if self.snap_step_m and self.snap_step_m > 0:
                du = round(du / self.snap_step_m) * self.snap_step_m
                dv = round(dv / self.snap_step_m) * self.snap_step_m

            if abs(du) > 1e-4 or abs(dv) > 1e-4:
                if self.view_type == "S":
                    self.platform.translate(du, dv, 0.0)
                elif self.view_type == "F":
                    self.platform.translate(0.0, du, dv)
                else: # L
                    self.platform.translate(du, 0.0, dv)
                self._chassis_moved = True
                self._last_mouse_pos = event.position()
                self.update()
            event.accept()
            return
        elif self._dragging:
            delta = event.position() - self._last_mouse_pos
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self._last_mouse_pos = event.position()
            self.update()
            event.accept()
        elif self.is_editing and self.active_tool == "Dibujar":
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._moving_sensor:
            self._moving_sensor = False
            self.setCursor(Qt.OpenHandCursor if self.allow_pan else Qt.ArrowCursor)
            event.accept()
            return
        if self._dragging_vertex_idx is not None:
            self._dragging_vertex_idx = None
            self._drag_start_bounds = None
            self._drag_start_polygon = None
            self.setCursor(Qt.PointingHandCursor if (self._hovered_vertex_idx is not None) else Qt.ArrowCursor)
            if self._vertex_moved:
                self._vertex_moved = False
                if self.platform:
                    self.chassis_dimensions_changed.emit(self.platform.length_m, self.platform.width_m, self.platform.height_m)
            self.update()
            event.accept()
            return
        if self._moving_chassis:
            self._moving_chassis = False
            self.setCursor(Qt.OpenHandCursor if (self.is_editing and self.active_tool == "Mover") else (Qt.OpenHandCursor if self.allow_pan else Qt.ArrowCursor))
            if self._chassis_moved:
                self._chassis_moved = False
                if self.platform:
                    self.chassis_dimensions_changed.emit(self.platform.length_m, self.platform.width_m, self.platform.height_m)
            event.accept()
            return
        elif self._dragging:
            self._dragging = False
            self.setCursor(Qt.OpenHandCursor if self.allow_pan else Qt.ArrowCursor)
            event.accept()
            return
        elif self.is_editing and self.allow_pan and self.active_tool == "Dibujar":
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
                    u_c = (u_min + u_max) / 2.0
                    v_c = (v_min + v_max) / 2.0
                    self._commit_box_dims(du, dv, u_c, v_c)
                    self._polygon_vertices.clear()
                    self._box_start_pos = None
                    self.update()
                    event.accept()
                    return
            self._box_start_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.is_editing and self.allow_pan and self.active_tool == "Dibujar":
            if len(self._polygon_vertices) >= 3:
                self._close_polygon()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def _commit_box_dims(self, dim_u: float, dim_v: float, u_c: float = 0.0, v_c: float = 0.0):
        if not self.platform:
            return
        prev_l = self.platform.length_m if self.platform.has_dimensions else 2.00
        prev_w = self.platform.width_m if self.platform.has_dimensions else 1.00
        prev_h = self.platform.height_m if self.platform.has_dimensions else 0.50

        if self.view_type == "S":
            # u = Xb (Largo), v = Yb (Ancho)
            l, w, h = dim_u, dim_v, prev_h
            self.platform.chassis_center_b[0] = round(u_c, 4)
            self.platform.chassis_center_b[1] = round(v_c, 4)
            hl = l / 2.0
            hw = w / 2.0
            self.platform.chassis_polygon = [
                [round(u_c + hl, 4), round(v_c - hw, 4)],
                [round(u_c + hl, 4), round(v_c + hw, 4)],
                [round(u_c - hl, 4), round(v_c + hw, 4)],
                [round(u_c - hl, 4), round(v_c - hw, 4)]
            ]
        elif self.view_type == "F":
            # u = Yb (Ancho), v = Zb (Alto)
            l, w, h = prev_l, dim_u, dim_v
            self.platform.chassis_center_b[1] = round(u_c, 4)
            self.platform.chassis_center_b[2] = round(v_c, 4)
        else: # L
            # u = Xb (Largo), v = Zb (Alto)
            l, w, h = dim_u, prev_w, dim_v
            self.platform.chassis_center_b[0] = round(u_c, 4)
            self.platform.chassis_center_b[2] = round(v_c, 4)

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
            self.platform.chassis_polygon = [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in pts]
            cx_poly = float(np.mean(pts[:, 0]))
            cy_poly = float(np.mean(pts[:, 1]))
            self.platform.chassis_center_b[0] = round(cx_poly, 4)
            self.platform.chassis_center_b[1] = round(cy_poly, 4)
        elif self.view_type == "F":
            w = extent_u
            h = extent_v
            l = prev_l
            cy_poly = float(np.mean(pts[:, 0]))
            cz_poly = float(np.mean(pts[:, 1]))
            self.platform.chassis_center_b[1] = round(cy_poly, 4)
            self.platform.chassis_center_b[2] = round(cz_poly, 4)
        else: # L
            l = extent_u
            h = extent_v
            w = prev_w
            cx_poly = float(np.mean(pts[:, 0]))
            cz_poly = float(np.mean(pts[:, 1]))
            self.platform.chassis_center_b[0] = round(cx_poly, 4)
            self.platform.chassis_center_b[2] = round(cz_poly, 4)

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

        # 5.1 Vértices interactivos del polígono (Requerimiento Y)
        if self.active_tool == "Vértices" and self.is_editing and self.platform and self.platform.has_dimensions:
            self._draw_vertices_handles(painter, cx, cy)

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
        p.setFont(self._font_grid)

        # Determinar rango horizontal
        k_start = int(np.floor((0.0 - cx) / step_px)) - 1
        k_end = int(np.ceil((float(w) - cx) / step_px)) + 1

        for k in range(k_start, k_end + 1):
            x = cx + k * step_px
            if -step_px <= x <= w + step_px:
                is_major = (k % 5 == 0)
                p.setPen(self._pen_grid_major if is_major else self._pen_grid_minor)
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

                    p.setPen(self._pen_grid_text)
                    p.drawText(QPointF(x + 3, h - 6), lbl)

        # Determinar rango vertical
        m_start = int(np.floor((0.0 - cy) / step_px)) - 1
        m_end = int(np.ceil((float(h) - cy) / step_px)) + 1

        for m in range(m_start, m_end + 1):
            y = cy + m * step_px
            if -step_px <= y <= h + step_px:
                is_major = (m % 5 == 0)
                p.setPen(self._pen_grid_major if is_major else self._pen_grid_minor)
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

                    p.setPen(self._pen_grid_text)
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
        bounds = self.platform.get_bounding_box()

        pen_body = QPen(_to_qcolor(COLOR_PLATFORM_BODY), 2, Qt.DashLine)
        p.setPen(pen_body)
        p.setBrush(QBrush(QColor(2, 132, 199, 25)))

        # 1. Geometría del chasis según la vista activa
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
            p_tl = self._body_2d_to_screen(bounds["x_max"], bounds["y_min"], cx, cy)
            p_br = self._body_2d_to_screen(bounds["x_min"], bounds["y_max"], cx, cy)
            p.drawRect(QRectF(p_tl, p_br))
        elif self.view_type == "S":
            p_tl = self._body_2d_to_screen(bounds["x_max"], bounds["y_min"], cx, cy)
            p_br = self._body_2d_to_screen(bounds["x_min"], bounds["y_max"], cx, cy)
            p.drawRect(QRectF(p_tl, p_br))
        elif self.view_type == "F":
            # u = Yb, v = Zb
            p_tl = self._body_2d_to_screen(bounds["y_min"], bounds["z_min"], cx, cy)
            p_br = self._body_2d_to_screen(bounds["y_max"], bounds["z_max"], cx, cy)
            p.drawRect(QRectF(p_tl, p_br))
        else: # L
            # u = Xb, v = Zb
            p_tl = self._body_2d_to_screen(bounds["x_min"], bounds["z_min"], cx, cy)
            p_br = self._body_2d_to_screen(bounds["x_max"], bounds["z_max"], cx, cy)
            p.drawRect(QRectF(p_tl, p_br))

        # 2. Líneas envolventes proyectadas hacia los márgenes
        p.setPen(QPen(QColor(2, 132, 199, 50), 1, Qt.DashDotLine))
        if self.view_type == "S":
            p_tl = self._body_2d_to_screen(bounds["x_max"], bounds["y_min"], cx, cy)
            p_br = self._body_2d_to_screen(bounds["x_min"], bounds["y_max"], cx, cy)
        elif self.view_type == "F":
            p_tl = self._body_2d_to_screen(bounds["y_min"], bounds["z_min"], cx, cy)
            p_br = self._body_2d_to_screen(bounds["y_max"], bounds["z_max"], cx, cy)
        else: # L
            p_tl = self._body_2d_to_screen(bounds["x_min"], bounds["z_min"], cx, cy)
            p_br = self._body_2d_to_screen(bounds["x_max"], bounds["z_max"], cx, cy)

        x_left = min(p_tl.x(), p_br.x())
        x_right = max(p_tl.x(), p_br.x())
        y_top = min(p_tl.y(), p_br.y())
        y_bottom = max(p_tl.y(), p_br.y())

        p.drawLine(QPointF(x_left, 0), QPointF(x_left, self.height()))
        p.drawLine(QPointF(x_right, 0), QPointF(x_right, self.height()))
        p.drawLine(QPointF(0, y_top), QPointF(self.width(), y_top))
        p.drawLine(QPointF(0, y_bottom), QPointF(self.width(), y_bottom))

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

    def _get_view_vertices(self) -> List[Tuple[float, float, str]]:
        """Devuelve los vértices proyectados (u, v, rótulo) según la vista activa (S, F, L)."""
        if not self.platform or not self.platform.has_dimensions:
            return []

        if self.view_type == "S":
            self.platform.ensure_polygon()
            if not self.platform.chassis_polygon:
                return []
            return [
                (float(pt[0]), float(pt[1]), f"V{i + 1} [{pt[0]:+.2f}, {pt[1]:+.2f}]")
                for i, pt in enumerate(self.platform.chassis_polygon)
            ]

        bounds = self.platform.get_bounding_box()
        if self.view_type == "F":
            # Proyección Frontal: u = Yb (Ancho), v = Zb (Alto, positivo hacia abajo)
            y_min, y_max = bounds["y_min"], bounds["y_max"]
            z_min, z_max = bounds["z_min"], bounds["z_max"]
            return [
                (y_min, z_min, f"V1 [{y_min:+.2f}, {z_min:+.2f}]"),
                (y_max, z_min, f"V2 [{y_max:+.2f}, {z_min:+.2f}]"),
                (y_max, z_max, f"V3 [{y_max:+.2f}, {z_max:+.2f}]"),
                (y_min, z_max, f"V4 [{y_min:+.2f}, {z_max:+.2f}]"),
            ]
        else:  # L
            # Proyección Lateral: u = Xb (Largo), v = Zb (Alto, positivo hacia abajo)
            x_min, x_max = bounds["x_min"], bounds["x_max"]
            z_min, z_max = bounds["z_min"], bounds["z_max"]
            return [
                (x_min, z_min, f"V1 [{x_min:+.2f}, {z_min:+.2f}]"),
                (x_max, z_min, f"V2 [{x_max:+.2f}, {z_min:+.2f}]"),
                (x_max, z_max, f"V3 [{x_max:+.2f}, {z_max:+.2f}]"),
                (x_min, z_max, f"V4 [{x_min:+.2f}, {z_max:+.2f}]"),
            ]

    def _apply_vertex_drag_front(self, idx: int, u_snap: float, v_snap: float):
        """Ajusta límites métricos, dimensiones y escala transversal en Vista Frontal (F)."""
        if not self.platform or not self._drag_start_bounds:
            return
        y_min_0 = self._drag_start_bounds["y_min"]
        y_max_0 = self._drag_start_bounds["y_max"]
        z_min_0 = self._drag_start_bounds["z_min"]
        z_max_0 = self._drag_start_bounds["z_max"]

        if idx == 0:  # V1: Top-Left (Izquierda - Arriba)
            y_min = min(u_snap, y_max_0 - 0.05)
            z_min = min(v_snap, z_max_0 - 0.05)
            y_max = y_max_0
            z_max = z_max_0
        elif idx == 1:  # V2: Top-Right (Derecha - Arriba)
            y_min = y_min_0
            z_min = min(v_snap, z_max_0 - 0.05)
            y_max = max(u_snap, y_min_0 + 0.05)
            z_max = z_max_0
        elif idx == 2:  # V3: Bottom-Right (Derecha - Abajo)
            y_min = y_min_0
            z_min = z_min_0
            y_max = max(u_snap, y_min_0 + 0.05)
            z_max = max(v_snap, z_min_0 + 0.05)
        elif idx == 3:  # V4: Bottom-Left (Izquierda - Abajo)
            y_min = min(u_snap, y_max_0 - 0.05)
            z_min = z_min_0
            y_max = y_max_0
            z_max = max(v_snap, z_min_0 + 0.05)
        else:
            return

        new_w = max(0.05, y_max - y_min)
        new_h = max(0.05, z_max - z_min)
        cy = (y_min + y_max) / 2.0
        cz = (z_min + z_max) / 2.0

        self.platform.width_m = round(float(new_w), 4)
        self.platform.height_m = round(float(new_h), 4)
        self.platform.chassis_center_b[1] = round(float(cy), 4)
        self.platform.chassis_center_b[2] = round(float(cz), 4)

        if self._drag_start_polygon:
            span_y_0 = y_max_0 - y_min_0
            factor_y = (y_max - y_min) / span_y_0 if span_y_0 > 1e-4 else 1.0
            self.platform.chassis_polygon = [
                [pt[0], round(float(y_min + (pt[1] - y_min_0) * factor_y), 4)]
                for pt in self._drag_start_polygon
            ]

    def _apply_vertex_drag_lateral(self, idx: int, u_snap: float, v_snap: float):
        """Ajusta límites métricos, dimensiones y escala longitudinal en Vista Lateral (L)."""
        if not self.platform or not self._drag_start_bounds:
            return
        x_min_0 = self._drag_start_bounds["x_min"]
        x_max_0 = self._drag_start_bounds["x_max"]
        z_min_0 = self._drag_start_bounds["z_min"]
        z_max_0 = self._drag_start_bounds["z_max"]

        if idx == 0:  # V1: Top-Left (Atrás - Arriba)
            x_min = min(u_snap, x_max_0 - 0.05)
            z_min = min(v_snap, z_max_0 - 0.05)
            x_max = x_max_0
            z_max = z_max_0
        elif idx == 1:  # V2: Top-Right (Adelante - Arriba)
            x_min = x_min_0
            z_min = min(v_snap, z_max_0 - 0.05)
            x_max = max(u_snap, x_min_0 + 0.05)
            z_max = z_max_0
        elif idx == 2:  # V3: Bottom-Right (Adelante - Abajo)
            x_min = x_min_0
            z_min = z_min_0
            x_max = max(u_snap, x_min_0 + 0.05)
            z_max = max(v_snap, z_min_0 + 0.05)
        elif idx == 3:  # V4: Bottom-Left (Atrás - Abajo)
            x_min = min(u_snap, x_max_0 - 0.05)
            z_min = z_min_0
            x_max = x_max_0
            z_max = max(v_snap, z_min_0 + 0.05)
        else:
            return

        new_l = max(0.05, x_max - x_min)
        new_h = max(0.05, z_max - z_min)
        cx = (x_min + x_max) / 2.0
        cz = (z_min + z_max) / 2.0

        self.platform.length_m = round(float(new_l), 4)
        self.platform.height_m = round(float(new_h), 4)
        self.platform.chassis_center_b[0] = round(float(cx), 4)
        self.platform.chassis_center_b[2] = round(float(cz), 4)

        if self._drag_start_polygon:
            span_x_0 = x_max_0 - x_min_0
            factor_x = (x_max - x_min) / span_x_0 if span_x_0 > 1e-4 else 1.0
            self.platform.chassis_polygon = [
                [round(float(x_min + (pt[0] - x_min_0) * factor_x), 4), pt[1]]
                for pt in self._drag_start_polygon
            ]

    def _draw_vertices_handles(self, p: QPainter, cx: float, cy: float):
        """Dibuja nodos manipulables con ratón sobre cada vértice en vistas S, F y L (Requerimiento Y)."""
        if not self.platform or not self.platform.has_dimensions:
            return

        font_v = QFont("Segoe UI", 8, QFont.Bold)
        p.setFont(font_v)

        verts = self._get_view_vertices()
        for idx, (u, v, lbl) in enumerate(verts):
            scr_pos = self._body_2d_to_screen(u, v, cx, cy)
            is_active = (idx == self._dragging_vertex_idx or idx == self._hovered_vertex_idx)

            if is_active:
                # Halo exterior ámbar
                p.setPen(QPen(QColor(245, 158, 11, 120), 6))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(scr_pos, 7.0, 7.0)

                # Nodo central
                p.setPen(QPen(QColor(217, 119, 6), 2))
                p.setBrush(QBrush(QColor(254, 243, 199)))
                p.drawEllipse(scr_pos, 5.0, 5.0)

                # Rótulo de coordenadas métricas
                p.setPen(QPen(QColor(30, 41, 59, 230), 1))
                p.drawText(QPointF(scr_pos.x() + 9, scr_pos.y() - 5), lbl)
            else:
                # Nodo estándar CAD: círculo blanco con borde azul técnico
                p.setPen(QPen(QColor(2, 132, 199), 2))
                p.setBrush(QBrush(QColor(255, 255, 255)))
                p.drawEllipse(scr_pos, 4.5, 4.5)

    def _draw_sensors(self, p: QPainter, cx: float, cy: float):
        font = QFont("Segoe UI", 9)
        font_bold = QFont("Segoe UI", 9, QFont.Bold)
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

            is_selected = (code == self.editing_sensor_code or code == getattr(self, "selected_sensor_code", None))
            if is_selected:
                # Halo visual de selección técnica (cuadrado cian translúcido)
                p.setPen(QPen(QColor(14, 165, 233, 220), 2))
                p.setBrush(QBrush(QColor(14, 165, 233, 50)))
                p.drawRoundedRect(QRectF(sx - 8.5, sy - 8.5, 17.0, 17.0), 2.0, 2.0)

            stype = s.sensor_type.value
            if "GNSS" in stype:
                col = _to_qcolor(COLOR_SENSOR_GNSS)
            elif "INS" in stype or "IMU" in stype:
                col = _to_qcolor(COLOR_SENSOR_INS)
            elif "CAM" in stype:
                col = _to_qcolor(COLOR_SENSOR_CAM)
            else:
                col = _to_qcolor(COLOR_SENSOR_DEFAULT)

            # Requerimiento A.K: Línea punteada direccional hacia adelante para sensores direccionales y orientados
            is_directional = ("CAM" in stype or "INS" in stype or "IMU" in stype or "LIDAR" in stype or any(abs(float(ang)) > 1e-5 for ang in (s.boresight_deg or (0,0,0))))
            if is_directional:
                a, b, c = s.get_boresight_alpha_beta_gamma()
                Cs2b = sensor_to_body_matrix(np.radians(a), np.radians(b), np.radians(c))
                # Vector unitario hacia adelante en s-frame [1, 0, 0] proyectado a b-frame
                ux = float(Cs2b[0, 0])
                uy = float(Cs2b[1, 0])
                uz = float(Cs2b[2, 0])

                line_len = 24.0
                if self.view_type == "S":
                    dx = uy * line_len
                    dy = -ux * line_len
                elif self.view_type == "F":
                    dx = uy * line_len
                    dy = uz * line_len
                else: # L
                    dx = ux * line_len
                    dy = uz * line_len

                mag = (dx**2 + dy**2)**0.5
                if mag >= 2.0:
                    pen_dash = QPen(col, 1.8, Qt.DashLine)
                    p.setPen(pen_dash)
                    p.drawLine(QPointF(sx, sy), QPointF(sx + dx, sy + dy))
                    # Requerimiento A.K: Sin punto al final de la línea punteada
                else:
                    # Vector casi perpendicular al plano de proyección (indicador frontal)
                    p.setPen(QPen(col, 1.2, Qt.DotLine))
                    p.setBrush(Qt.NoBrush)
                    p.drawEllipse(QPointF(sx, sy), 7.0, 7.0)

            # Requerimiento A.K: Forma estrictamente cuadrada para discernir con vértices circulares
            sq_half = 4.5
            p.setPen(QPen(QColor(30, 41, 59, 230), 1.5))
            p.setBrush(QBrush(col))
            p.drawRect(QRectF(sx - sq_half, sy - sq_half, 2.0 * sq_half, 2.0 * sq_half))

            p.setPen(QPen(_to_qcolor(COLOR_TEXT_PRIMARY), 1))
            p.setFont(font_bold if is_selected else font)
            # Requerimiento A.G: mostrar el Nombre descriptivo del sensor, no su ID interno
            p.drawText(QPointF(sx + 7, sy - 5), f"{s.name}")

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
    sensor_placed = Signal(str, float, float, float)
    sensor_moved = Signal(str, float, float, float)
    sensor_selected = Signal(str) # sensor_code
    view_changed = Signal(str)

    def __init__(self, platform: Platform, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.platform = platform
        self.is_editing: bool = False

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
            c.sensor_placed.connect(self._on_sensor_placed)
            c.sensor_moved.connect(self._on_sensor_moved)
            c.sensor_clicked.connect(self._on_sensor_clicked)

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

    def _on_sensor_clicked(self, code: str):
        self.set_selected_sensor(code)
        self.sensor_selected.emit(code)

    def set_selected_sensor(self, sensor_code: Optional[str]):
        for c in self.canvases:
            c.set_selected_sensor(sensor_code)

    def _on_chassis_drawn(self, l: float, w: float, h: float):
        for c in self.canvases:
            c.update()
        self.chassis_updated.emit()

    def _on_sensor_placed(self, code: str, x: float, y: float, z: float):
        for c in self.canvases:
            c.update()
        self.sensor_placed.emit(code, x, y, z)

    def _on_sensor_moved(self, code: str, x: float, y: float, z: float):
        for c in self.canvases:
            c.update()
        self.sensor_moved.emit(code, x, y, z)

    def set_editing_sensor(self, sensor_code: Optional[str]):
        for c in self.canvases:
            c.editing_sensor_code = sensor_code
            c.set_selected_sensor(sensor_code)
            c.update()

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
        self.view_changed.emit(view_key.upper())

    def set_editing_lock(self, locked: bool):
        """
        Bloquea o desbloquea el modo 4 cuadrantes durante la edición.
        En cualquier tipo de edición NO se permite usar la vista 4Q (SFLLeyenda).
        """
        self.btn_quad.setEnabled(not locked)
        if locked and self.is_quad_mode:
            self.set_single_view("S")
        self.set_editing_mode(locked)

    def set_editing_mode(self, enabled: bool):
        """Propaga el estado de edición interactiva a todos los lienzos ortogonales."""
        self.is_editing = enabled
        for c in self.canvases:
            c.set_editing_mode(enabled)

    def get_active_view(self) -> str:
        """Devuelve la vista ortogonal activa ('S', 'F' o 'L')."""
        return self.canvas_single.view_type

    def center_origin(self):
        for c in self.canvases:
            c.center_origin()

    def center_centroid(self):
        for c in self.canvases:
            c.center_centroid()

    def zoom_to_sensor(self, sensor_code: str, target_scale: float = 220.0):
        """Enfoca y hace zoom sobre el sensor especificado en todos los lienzos ortogonales."""
        if not self.platform or sensor_code not in self.platform.sensors:
            return
        sens = self.platform.sensors[sensor_code]
        arm = sens.lever_arm_b
        xb, yb, zb = float(arm[0]), float(arm[1]), float(arm[2])
        for c in self.canvases:
            c.zoom_to_sensor(xb, yb, zb, target_scale)
        if self.is_quad_mode:
            self.canvas_top.scale_changed.emit(target_scale)

    def redraw_all(self):
        for c in self.canvases:
            c.set_platform(self.platform)
            c.update()


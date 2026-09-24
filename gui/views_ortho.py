"""
PyGSN - Orthogonal 2D Views Canvas (DearPyGui)
=============================================
Lienzo tecnico con 3 Vistas Ortogonales 2D:
- Vista Superior (Planta / Top-down): Xb (Adelante) vs Yb (Derecha)
- Vista Lateral (Perfil / Side):      Xb (Adelante) vs -Zb (Arriba)
- Vista Frontal (Alzado / Front):     Yb (Derecha) vs -Zb (Arriba)

Zero renderizado 3D: Proyeccion ortogonal pura sobre papel milimetrado CAD.
"""

from typing import Callable
import dearpygui.dearpygui as dpg
import numpy as np

from core.models import Platform, Sensor, SensorType
from core.rotations import sensor_to_body_matrix
from gui.theme import (
    COLOR_CANVAS_BG, COLOR_GRID_MAJOR, COLOR_GRID_MINOR,
    COLOR_AXIS_X, COLOR_AXIS_Y, COLOR_AXIS_Z, COLOR_PLATFORM_BODY,
    COLOR_ORIGIN, COLOR_CENTROID, COLOR_SENSOR_GNSS, COLOR_SENSOR_INS,
    COLOR_SENSOR_CAM, COLOR_SENSOR_DEFAULT, COLOR_TEXT_PRIMARY, COLOR_TEXT_MUTED
)


class OrthoViewCanvas:
    """Manejador de los 3 lienzos ortogonales tecnicos."""

    def __init__(self, platform: Platform, on_sensor_selected: Callable[[str], None] | None = None):
        self.platform = platform
        self.on_sensor_selected = on_sensor_selected
        
        # Escala: pixeles por metro
        self.pixels_per_meter = 260.0
        self.selected_sensor_code: str | None = None

        # Tags de drawlists
        self.tag_draw_top = "drawlist_top_view"
        self.tag_draw_side = "drawlist_side_view"
        self.tag_draw_front = "drawlist_front_view"

        # Dimensiones de cada lienzo en pixeles
        self.canvas_width = 380
        self.canvas_height = 290

    def get_sensor_color(self, sensor: Sensor) -> tuple[int, int, int, int]:
        if sensor.sensor_type == SensorType.GNSS:
            return COLOR_SENSOR_GNSS
        elif sensor.sensor_type == SensorType.INS:
            return COLOR_SENSOR_INS
        elif sensor.sensor_type == SensorType.CAMERA:
            return COLOR_SENSOR_CAM
        elif sensor.code == "PLA":
            return COLOR_ORIGIN
        return COLOR_SENSOR_DEFAULT

    def draw_grid_and_axes(self, drawlist_tag: str, h_axis_label: str, v_axis_label: str, h_axis_color, v_axis_color):
        """Dibuja el fondo cuadriculado milimetrado y los ejes cartesianos de referencia."""
        cx = self.canvas_width / 2.0
        cy = self.canvas_height / 2.0
        scale = self.pixels_per_meter

        # Fondo
        dpg.draw_rectangle([0, 0], [self.canvas_width, self.canvas_height],
                           fill=COLOR_CANVAS_BG, color=COLOR_CANVAS_BG, parent=drawlist_tag)

        # Cuadricula menor cada 0.1 m (10 cm)
        step_minor = 0.1 * scale
        # Cuadricula mayor cada 0.5 m (50 cm)
        step_major = 0.5 * scale

        # Lineas verticales
        n_v = int(self.canvas_width / step_minor / 2.0) + 1
        for i in range(-n_v, n_v + 1):
            px = cx + i * step_minor
            is_major = (i % 5 == 0)
            col = COLOR_GRID_MAJOR if is_major else COLOR_GRID_MINOR
            thick = 1.2 if is_major else 0.8
            dpg.draw_line([px, 0], [px, self.canvas_height], color=col, thickness=thick, parent=drawlist_tag)
            if is_major and i != 0:
                dist_m = i * 0.1
                dpg.draw_text([px + 3, self.canvas_height - 18], f"{dist_m:+.1f}m",
                              color=COLOR_TEXT_MUTED, size=11, parent=drawlist_tag)

        # Lineas horizontales
        n_h = int(self.canvas_height / step_minor / 2.0) + 1
        for j in range(-n_h, n_h + 1):
            py = cy + j * step_minor
            is_major = (j % 5 == 0)
            col = COLOR_GRID_MAJOR if is_major else COLOR_GRID_MINOR
            thick = 1.2 if is_major else 0.8
            dpg.draw_line([0, py], [self.canvas_width, py], color=col, thickness=thick, parent=drawlist_tag)
            if is_major and j != 0:
                dist_m = -j * 0.1  # Invertido por coordenada de pantalla
                dpg.draw_text([5, py - 14], f"{dist_m:+.1f}m",
                              color=COLOR_TEXT_MUTED, size=11, parent=drawlist_tag)

        # Eje Horizontal
        dpg.draw_line([0, cy], [self.canvas_width, cy], color=h_axis_color, thickness=2.0, parent=drawlist_tag)
        dpg.draw_text([self.canvas_width - 45, cy - 20], h_axis_label, color=h_axis_color, size=14, parent=drawlist_tag)

        # Eje Vertical
        dpg.draw_line([cx, 0], [cx, self.canvas_height], color=v_axis_color, thickness=2.0, parent=drawlist_tag)
        dpg.draw_text([cx + 8, 8], v_axis_label, color=v_axis_color, size=14, parent=drawlist_tag)

        # Origen (0, 0)
        dpg.draw_circle([cx, cy], 3.0, color=COLOR_ORIGIN, fill=COLOR_ORIGIN, parent=drawlist_tag)

    def draw_top_view(self):
        """
        Vista Superior (Planta):
        Horizontal = Yb (Derecha, verde)
        Vertical   = Xb (Adelante hacia arriba, rojo)
        """
        tag = self.tag_draw_top
        dpg.delete_item(tag, children_only=True)
        cx = self.canvas_width / 2.0
        cy = self.canvas_height / 2.0
        scale = self.pixels_per_meter

        self.draw_grid_and_axes(tag, "+Yb (Der)", "+Xb (Adelante)", COLOR_AXIS_Y, COLOR_AXIS_X)

        # Contorno del chasis / body
        L = self.platform.length_m
        W = self.platform.width_m
        # Centrado respecto al origen b-frame
        # X va hacia arriba (-screen_y), Y va hacia la derecha (+screen_x)
        p_min = [cx - (W / 2.0) * scale, cy - (L / 2.0) * scale]
        p_max = [cx + (W / 2.0) * scale, cy + (L / 2.0) * scale]
        dpg.draw_rectangle(p_min, p_max, color=COLOR_PLATFORM_BODY, thickness=1.8, parent=tag)
        # Flecha indicadora de morro (hacia adelante / +Xb)
        arrow_tip = [cx, cy - (L / 2.0) * scale - 12]
        dpg.draw_triangle([cx - 8, cy - (L / 2.0) * scale],
                          [cx + 8, cy - (L / 2.0) * scale],
                          arrow_tip, color=COLOR_AXIS_X, fill=COLOR_AXIS_X, parent=tag)

        # Sensores
        for code, sensor in self.platform.sensors.items():
            xb, yb, zb = sensor.lever_arm_b
            sx = cx + yb * scale
            sy = cy - xb * scale
            col = self.get_sensor_color(sensor)

            # Circulo del sensor
            is_sel = (code == self.selected_sensor_code)
            radius = 6.0 if not is_sel else 9.0
            dpg.draw_circle([sx, sy], radius, color=(255, 255, 255, 255) if is_sel else col,
                            fill=col, thickness=2.0 if is_sel else 1.0, parent=tag)

            # Etiqueta
            dpg.draw_text([sx + 8, sy - 14], code, color=COLOR_TEXT_PRIMARY, size=13, parent=tag)

            # Triedro miniatura local de sensor
            if sensor.boresight_deg != (0.0, 0.0, 0.0):
                a1, a2, a3 = [np.radians(x) for x in sensor.boresight_deg]
                Cs2b = sensor_to_body_matrix(a1, a2, a3)
                v_len = 16.0
                # Eje x_s en b-frame proyectado: dx_b = Cs2b[0, 0], dy_b = Cs2b[1, 0]
                tx = sx + Cs2b[1, 0] * v_len
                ty = sy - Cs2b[0, 0] * v_len
                dpg.draw_line([sx, sy], [tx, ty], color=COLOR_AXIS_X, thickness=1.5, parent=tag)

    def draw_side_view(self):
        """
        Vista Lateral (Perfil):
        Horizontal = Xb (Adelante hacia la derecha, rojo)
        Vertical   = -Zb (Arriba / Cota, azul)
        """
        tag = self.tag_draw_side
        dpg.delete_item(tag, children_only=True)
        cx = self.canvas_width / 2.0
        cy = self.canvas_height / 2.0
        scale = self.pixels_per_meter

        self.draw_grid_and_axes(tag, "+Xb (Adelante)", "-Zb (Arriba)", COLOR_AXIS_X, COLOR_AXIS_Z)

        L = self.platform.length_m
        H = self.platform.height_m
        p_min = [cx - (L / 2.0) * scale, cy - (H / 2.0) * scale]
        p_max = [cx + (L / 2.0) * scale, cy + (H / 2.0) * scale]
        dpg.draw_rectangle(p_min, p_max, color=COLOR_PLATFORM_BODY, thickness=1.8, parent=tag)

        # Sensores
        for code, sensor in self.platform.sensors.items():
            xb, yb, zb = sensor.lever_arm_b
            sx = cx + xb * scale
            sy = cy + zb * scale  # Si Zb es Down (+zb hacia abajo en mundo), en pantalla va hacia abajo (+sy)
            col = self.get_sensor_color(sensor)

            is_sel = (code == self.selected_sensor_code)
            radius = 6.0 if not is_sel else 9.0
            dpg.draw_circle([sx, sy], radius, color=(255, 255, 255, 255) if is_sel else col,
                            fill=col, thickness=2.0 if is_sel else 1.0, parent=tag)
            dpg.draw_text([sx + 8, sy - 14], code, color=COLOR_TEXT_PRIMARY, size=13, parent=tag)

    def draw_front_view(self):
        """
        Vista Frontal (Alzado):
        Horizontal = Yb (Derecha, verde)
        Vertical   = -Zb (Arriba / Cota, azul)
        """
        tag = self.tag_draw_front
        dpg.delete_item(tag, children_only=True)
        cx = self.canvas_width / 2.0
        cy = self.canvas_height / 2.0
        scale = self.pixels_per_meter

        self.draw_grid_and_axes(tag, "+Yb (Derecha)", "-Zb (Arriba)", COLOR_AXIS_Y, COLOR_AXIS_Z)

        W = self.platform.width_m
        H = self.platform.height_m
        p_min = [cx - (W / 2.0) * scale, cy - (H / 2.0) * scale]
        p_max = [cx + (W / 2.0) * scale, cy + (H / 2.0) * scale]
        dpg.draw_rectangle(p_min, p_max, color=COLOR_PLATFORM_BODY, thickness=1.8, parent=tag)

        # Sensores
        for code, sensor in self.platform.sensors.items():
            xb, yb, zb = sensor.lever_arm_b
            sx = cx + yb * scale
            sy = cy + zb * scale
            col = self.get_sensor_color(sensor)

            is_sel = (code == self.selected_sensor_code)
            radius = 6.0 if not is_sel else 9.0
            dpg.draw_circle([sx, sy], radius, color=(255, 255, 255, 255) if is_sel else col,
                            fill=col, thickness=2.0 if is_sel else 1.0, parent=tag)
            dpg.draw_text([sx + 8, sy - 14], code, color=COLOR_TEXT_PRIMARY, size=13, parent=tag)

    def redraw_all(self):
        """Actualiza el dibujo de las 3 vistas tecnicas."""
        self.draw_top_view()
        self.draw_side_view()
        self.draw_front_view()

    def set_zoom(self, new_scale: float):
        self.pixels_per_meter = np.clip(new_scale, 80.0, 800.0)
        self.redraw_all()

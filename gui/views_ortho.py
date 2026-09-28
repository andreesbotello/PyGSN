"""
PyGSN - Orthogonal 2D Views Canvas (DearPyGui)
=============================================
Lienzo tecnico con 3 Vistas Ortogonales 2D:
- Vista Superior (Planta / Top-down): Xb (Adelante, Rojo R) vs Yb (Derecha, Verde G)
- Vista Lateral (Perfil / Side):      Xb (Adelante, Rojo R) vs -Zb (Arriba, Azul B)
- Vista Frontal (Alzado / Front):     Yb (Derecha, Verde G) vs -Zb (Arriba, Azul B)

Zero renderizado 3D: Proyeccion ortogonal pura sobre papel milimetrado CAD.
Convencion de colores de ejes estrictamente RGB:
  - Eje 1 (Xb, Adelante): Rojo (R)
  - Eje 2 (Yb, Derecha):  Verde (G)
  - Eje 3 (Zb, Abajo / -Zb Arriba): Azul (B)
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
    """Manejador de los lienzos ortogonales tecnicos en modo 4 cuadrantes o vista unica."""

    def __init__(
        self,
        platform: Platform,
        on_sensor_selected: Callable[[str], None] | None = None,
        tag_prefix: str = ""
    ):
        self.platform = platform
        self.on_sensor_selected = on_sensor_selected
        plat_id_clean = getattr(platform, "id", "") or "default"
        self.tag_prefix = tag_prefix or f"plat_{plat_id_clean}"

        # Escala: pixeles por metro y desplazamientos pan (px)
        self.pixels_per_meter = 240.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.selected_sensor_code: str | None = None

        # Modo de visualización: QUAD ([[S, F], [L, Leyenda]]) o SINGLE (Vista única ampliada S, F o L)
        self.view_mode: str = "QUAD"
        self.active_single_view: str = "S"

        # Tags de drawlists y grupos dinamicos por plataforma
        self.tag_draw_top = f"{self.tag_prefix}_drawlist_top"
        self.tag_draw_side = f"{self.tag_prefix}_drawlist_side"
        self.tag_draw_front = f"{self.tag_prefix}_drawlist_front"
        self.tag_draw_single = f"{self.tag_prefix}_drawlist_single"
        self.tag_quad_group = f"{self.tag_prefix}_group_quad"
        self.tag_single_group = f"{self.tag_prefix}_group_single"

        # Dimensiones iniciales seguras para evitar cualquier desbordamiento vertical
        self.canvas_width = 370
        self.canvas_height = 240
        self.single_width = 760
        self.single_height = 510

    def toggle_view_mode(self):
        """Alterna entre modo 4 cuadrantes [[S, F], [L, Leyenda]] y vista única ampliada."""
        self.view_mode = "SINGLE" if self.view_mode == "QUAD" else "QUAD"
        self._sync_view_visibility()
        self.redraw_all()

    def set_single_view(self, view_key: str):
        """Activa una vista única ampliada ('S'=Superior, 'F'=Frontal, 'L'=Lateral)."""
        self.active_single_view = view_key.upper()
        self.view_mode = "SINGLE"
        self._sync_view_visibility()
        self.redraw_all()

    def _sync_view_visibility(self):
        is_quad = (self.view_mode == "QUAD")
        if dpg.does_item_exist(self.tag_quad_group):
            dpg.configure_item(self.tag_quad_group, show=is_quad)
        if dpg.does_item_exist(self.tag_single_group):
            dpg.configure_item(self.tag_single_group, show=not is_quad)

    def center_origin(self):
        """Centra la visualización en el origen [0, 0, 0]."""
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.redraw_all()

    def center_centroid(self):
        """Centra la visualización en el centroide de sensores y geometría."""
        pts = []
        for s in self.platform.sensors.values():
            pts.append([s.lever_arm_b[1], -s.lever_arm_b[0]])
        if self.platform.has_dimensions and self.platform.length_m > 0:
            pts.append([0.0, 0.0])
        if pts:
            mean_pt = np.mean(pts, axis=0)
            self.pan_x = -float(mean_pt[0]) * self.pixels_per_meter
            self.pan_y = -float(mean_pt[1]) * self.pixels_per_meter
        else:
            self.pan_x = 0.0
            self.pan_y = 0.0
        self.redraw_all()

    def handle_mouse_wheel(self, delta: float):
        """Gestiona el zoom interactivo con Ctrl + Rueda del ratón."""
        if dpg.is_key_down(dpg.mvKey_Control):
            factor = 1.15 if delta > 0 else (1.0 / 1.15)
            self.pixels_per_meter = float(np.clip(self.pixels_per_meter * factor, 30.0, 1200.0))
            self.redraw_all()

    def resize_to_workspace(self, avail_w: int, avail_h: int):
        """Ajusta las dimensiones de los cuadrantes exactamente al espacio visible sin desbordamiento ni scroll."""
        quad_w = max(200, int((avail_w - 20) / 2))
        quad_h = max(150, int((avail_h - 45) / 2))

        self.canvas_width = quad_w
        self.canvas_height = quad_h
        self.single_width = max(300, avail_w - 15)
        self.single_height = max(200, avail_h - 35)

        for win_tag, dl_tag in [
            (f"{self.tag_prefix}_win_top", self.tag_draw_top),
            (f"{self.tag_prefix}_win_front", self.tag_draw_front),
            (f"{self.tag_prefix}_win_side", self.tag_draw_side),
            (f"{self.tag_prefix}_win_legend", None),
        ]:
            if dpg.does_item_exist(win_tag):
                dpg.configure_item(win_tag, width=quad_w, height=quad_h)
            if dl_tag and dpg.does_item_exist(dl_tag):
                dpg.configure_item(dl_tag, width=quad_w - 6, height=quad_h - 6)

        if dpg.does_item_exist(f"{self.tag_prefix}_win_single"):
            dpg.configure_item(f"{self.tag_prefix}_win_single", width=self.single_width, height=self.single_height)
        if dpg.does_item_exist(self.tag_draw_single):
            dpg.configure_item(self.tag_draw_single, width=self.single_width - 6, height=self.single_height - 6)

        self.redraw_all()

    def build_canvas_ui(self, parent_tag: str):
        """Construye los controles y áreas de dibujo en el contenedor especificado."""
        with dpg.group(parent=parent_tag):
            # Barra superior: Únicamente los 4 botones pequeños en la esquina superior derecha
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=-95)
                dpg.add_button(label="/", width=20, height=18, callback=self.toggle_view_mode, small=True)
                dpg.add_button(label="S", width=20, height=18, callback=lambda: self.set_single_view("S"), small=True)
                dpg.add_button(label="F", width=20, height=18, callback=lambda: self.set_single_view("F"), small=True)
                dpg.add_button(label="L", width=20, height=18, callback=lambda: self.set_single_view("L"), small=True)

            dpg.add_spacer(height=2)

            # MODO 1: Cuadrícula 2x2 (4 cuadrantes [[S, F], [L, Leyenda]])
            with dpg.group(tag=self.tag_quad_group):
                # Fila 1: [S, F]
                with dpg.group(horizontal=True):
                    # Superior (S)
                    with dpg.group():
                        dpg.add_text("Superior (Planta)", color=COLOR_TEXT_PRIMARY)
                        with dpg.child_window(width=self.canvas_width, height=self.canvas_height, border=True, no_scrollbar=True, tag=f"{self.tag_prefix}_win_top"):
                            dpg.add_drawlist(width=self.canvas_width - 6, height=self.canvas_height - 6, tag=self.tag_draw_top)

                    # Frontal (F)
                    with dpg.group():
                        dpg.add_text("Frontal (Alzado)", color=COLOR_TEXT_PRIMARY)
                        with dpg.child_window(width=self.canvas_width, height=self.canvas_height, border=True, no_scrollbar=True, tag=f"{self.tag_prefix}_win_front"):
                            dpg.add_drawlist(width=self.canvas_width - 6, height=self.canvas_height - 6, tag=self.tag_draw_front)

                # Fila 2: [L, Leyenda]
                with dpg.group(horizontal=True):
                    # Lateral (L)
                    with dpg.group():
                        dpg.add_text("Lateral (Perfil)", color=COLOR_TEXT_PRIMARY)
                        with dpg.child_window(width=self.canvas_width, height=self.canvas_height, border=True, no_scrollbar=True, tag=f"{self.tag_prefix}_win_side"):
                            dpg.add_drawlist(width=self.canvas_width - 6, height=self.canvas_height - 6, tag=self.tag_draw_side)

                    # Leyenda
                    with dpg.group():
                        dpg.add_text("Leyenda", color=COLOR_TEXT_PRIMARY)
                        with dpg.child_window(width=self.canvas_width, height=self.canvas_height, border=True, no_scrollbar=True, tag=f"{self.tag_prefix}_win_legend"):
                            dpg.add_text("Ejes Body (b-frame) RGB:", color=(255, 209, 102, 255))
                            dpg.add_text("  [-] Xb Adelante (Rojo R)", color=COLOR_AXIS_X)
                            dpg.add_text("  [-] Yb Derecha (Verde G)", color=COLOR_AXIS_Y)
                            dpg.add_text("  [-] Zb Abajo (Azul B)", color=COLOR_AXIS_Z)
                            dpg.add_separator()
                            dpg.add_text("Sensores:", color=(255, 209, 102, 255))
                            dpg.add_text("  [*] GNSS", color=COLOR_SENSOR_GNSS)
                            dpg.add_text("  [*] INS/IMU", color=COLOR_SENSOR_INS)
                            dpg.add_text("  [*] Camara", color=COLOR_SENSOR_CAM)
                            dpg.add_text("  [*] Origen [0,0,0]", color=COLOR_ORIGIN)

            # MODO 2: Vista Única Ampliada (Ocupa todo el workspace)
            with dpg.group(tag=self.tag_single_group, show=False):
                with dpg.child_window(width=-1, height=-1, border=True, no_scrollbar=True, tag=f"{self.tag_prefix}_win_single"):
                    dpg.add_drawlist(width=self.single_width, height=self.single_height, tag=self.tag_draw_single)

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

    def draw_grid_and_axes(self, drawlist_tag: str, h_axis_label: str, v_axis_label: str, h_axis_color, v_axis_color, width=None, height=None):
        """Dibuja el fondo cuadriculado milimetrado y los ejes cartesianos de referencia."""
        w = width or self.canvas_width
        h = height or self.canvas_height
        cx = (w / 2.0) + self.pan_x
        cy = (h / 2.0) + self.pan_y
        scale = self.pixels_per_meter

        # Fondo
        dpg.draw_rectangle([0, 0], [w, h], fill=COLOR_CANVAS_BG, color=COLOR_CANVAS_BG, parent=drawlist_tag)

        # Cuadricula menor cada 0.1 m (10 cm)
        step_minor = 0.1 * scale
        step_major = 0.5 * scale

        # Lineas verticales
        n_v = int(w / max(step_minor, 5.0) / 2.0) + 2
        for i in range(-n_v, n_v + 1):
            px = cx + i * step_minor
            if 0 <= px <= w:
                is_major = (i % 5 == 0)
                col = COLOR_GRID_MAJOR if is_major else COLOR_GRID_MINOR
                thick = 1.0 if is_major else 0.6
                dpg.draw_line([px, 0], [px, h], color=col, thickness=thick, parent=drawlist_tag)

        # Lineas horizontales
        n_h = int(h / max(step_minor, 5.0) / 2.0) + 2
        for j in range(-n_h, n_h + 1):
            py = cy + j * step_minor
            if 0 <= py <= h:
                is_major = (j % 5 == 0)
                col = COLOR_GRID_MAJOR if is_major else COLOR_GRID_MINOR
                thick = 1.0 if is_major else 0.6
                dpg.draw_line([0, py], [w, py], color=col, thickness=thick, parent=drawlist_tag)

        # Eje Horizontal
        dpg.draw_line([0, cy], [w, cy], color=h_axis_color, thickness=2.0, parent=drawlist_tag)
        dpg.draw_text([w - 55, max(5, cy - 18)], h_axis_label, color=h_axis_color, size=13, parent=drawlist_tag)

        # Eje Vertical
        dpg.draw_line([cx, 0], [cx, h], color=v_axis_color, thickness=2.0, parent=drawlist_tag)
        dpg.draw_text([max(5, cx + 6), 6], v_axis_label, color=v_axis_color, size=13, parent=drawlist_tag)

        # Origen (0, 0)
        dpg.draw_circle([cx, cy], 3.0, color=COLOR_ORIGIN, fill=COLOR_ORIGIN, parent=drawlist_tag)

    def draw_top_view(self, tag=None, w=None, h=None):
        """
        Vista Superior (Planta):
        Horizontal = Yb (Derecha, verde G)
        Vertical   = Xb (Adelante hacia arriba, rojo R)
        """
        target_tag = tag or self.tag_draw_top
        if not dpg.does_item_exist(target_tag):
            return
        dpg.delete_item(target_tag, children_only=True)

        width = w or (self.canvas_width - 6)
        height = h or (self.canvas_height - 6)
        cx = (width / 2.0) + self.pan_x
        cy = (height / 2.0) + self.pan_y
        scale = self.pixels_per_meter

        self.draw_grid_and_axes(target_tag, "+Yb (Der)", "+Xb (Adel)", COLOR_AXIS_Y, COLOR_AXIS_X, width=width, height=height)

        # Contorno del chasis / body solo si tiene dimensiones fijas
        if self.platform.has_dimensions and self.platform.length_m > 0 and self.platform.width_m > 0:
            L = self.platform.length_m
            W = self.platform.width_m
            p_min = [cx - (W / 2.0) * scale, cy - (L / 2.0) * scale]
            p_max = [cx + (W / 2.0) * scale, cy + (L / 2.0) * scale]
            dpg.draw_rectangle(p_min, p_max, color=COLOR_PLATFORM_BODY, thickness=1.8, parent=target_tag)

            # Flecha indicadora de morro (+Xb hacia arriba)
            arrow_tip = [cx, cy - (L / 2.0) * scale - 10]
            dpg.draw_triangle([cx - 6, cy - (L / 2.0) * scale],
                              [cx + 6, cy - (L / 2.0) * scale],
                              arrow_tip, color=COLOR_AXIS_X, fill=COLOR_AXIS_X, parent=target_tag)

        # Sensores
        for code, sensor in self.platform.sensors.items():
            xb, yb, zb = sensor.lever_arm_b
            sx = cx + yb * scale
            sy = cy - xb * scale
            col = self.get_sensor_color(sensor)

            is_sel = (code == self.selected_sensor_code)
            radius = 5.0 if not is_sel else 8.0
            dpg.draw_circle([sx, sy], radius, color=(255, 255, 255, 255) if is_sel else col,
                            fill=col, thickness=2.0 if is_sel else 1.0, parent=target_tag)
            dpg.draw_text([sx + 6, sy - 12], code, color=COLOR_TEXT_PRIMARY, size=12, parent=target_tag)

            if sensor.boresight_deg != (0.0, 0.0, 0.0):
                a1, a2, a3 = [np.radians(x) for x in sensor.boresight_deg]
                Cs2b = sensor_to_body_matrix(a1, a2, a3)
                v_len = 14.0
                tx = sx + Cs2b[1, 0] * v_len
                ty = sy - Cs2b[0, 0] * v_len
                dpg.draw_line([sx, sy], [tx, ty], color=COLOR_AXIS_X, thickness=1.5, parent=target_tag)

    def draw_side_view(self, tag=None, w=None, h=None):
        """
        Vista Lateral (Perfil):
        Horizontal = Xb (Adelante hacia la derecha, rojo R)
        Vertical   = -Zb (Arriba / Cota, azul B)
        """
        target_tag = tag or self.tag_draw_side
        if not dpg.does_item_exist(target_tag):
            return
        dpg.delete_item(target_tag, children_only=True)

        width = w or (self.canvas_width - 6)
        height = h or (self.canvas_height - 6)
        cx = (width / 2.0) + self.pan_x
        cy = (height / 2.0) + self.pan_y
        scale = self.pixels_per_meter

        self.draw_grid_and_axes(target_tag, "+Xb (Adel)", "-Zb (Arriba)", COLOR_AXIS_X, COLOR_AXIS_Z, width=width, height=height)

        if self.platform.has_dimensions and self.platform.length_m > 0 and self.platform.height_m > 0:
            L = self.platform.length_m
            H = self.platform.height_m
            p_min = [cx - (L / 2.0) * scale, cy - (H / 2.0) * scale]
            p_max = [cx + (L / 2.0) * scale, cy + (H / 2.0) * scale]
            dpg.draw_rectangle(p_min, p_max, color=COLOR_PLATFORM_BODY, thickness=1.8, parent=target_tag)

        for code, sensor in self.platform.sensors.items():
            xb, yb, zb = sensor.lever_arm_b
            sx = cx + xb * scale
            sy = cy + zb * scale
            col = self.get_sensor_color(sensor)

            is_sel = (code == self.selected_sensor_code)
            radius = 5.0 if not is_sel else 8.0
            dpg.draw_circle([sx, sy], radius, color=(255, 255, 255, 255) if is_sel else col,
                            fill=col, thickness=2.0 if is_sel else 1.0, parent=target_tag)
            dpg.draw_text([sx + 6, sy - 12], code, color=COLOR_TEXT_PRIMARY, size=12, parent=target_tag)

    def draw_front_view(self, tag=None, w=None, h=None):
        """
        Vista Frontal (Alzado):
        Horizontal = Yb (Derecha, verde G)
        Vertical   = -Zb (Arriba / Cota, azul B)
        """
        target_tag = tag or self.tag_draw_front
        if not dpg.does_item_exist(target_tag):
            return
        dpg.delete_item(target_tag, children_only=True)

        width = w or (self.canvas_width - 6)
        height = h or (self.canvas_height - 6)
        cx = (width / 2.0) + self.pan_x
        cy = (height / 2.0) + self.pan_y
        scale = self.pixels_per_meter

        self.draw_grid_and_axes(target_tag, "+Yb (Der)", "-Zb (Arriba)", COLOR_AXIS_Y, COLOR_AXIS_Z, width=width, height=height)

        if self.platform.has_dimensions and self.platform.width_m > 0 and self.platform.height_m > 0:
            W = self.platform.width_m
            H = self.platform.height_m
            p_min = [cx - (W / 2.0) * scale, cy - (H / 2.0) * scale]
            p_max = [cx + (W / 2.0) * scale, cy + (H / 2.0) * scale]
            dpg.draw_rectangle(p_min, p_max, color=COLOR_PLATFORM_BODY, thickness=1.8, parent=target_tag)

        for code, sensor in self.platform.sensors.items():
            xb, yb, zb = sensor.lever_arm_b
            sx = cx + yb * scale
            sy = cy + zb * scale
            col = self.get_sensor_color(sensor)

            is_sel = (code == self.selected_sensor_code)
            radius = 5.0 if not is_sel else 8.0
            dpg.draw_circle([sx, sy], radius, color=(255, 255, 255, 255) if is_sel else col,
                            fill=col, thickness=2.0 if is_sel else 1.0, parent=target_tag)
            dpg.draw_text([sx + 6, sy - 12], code, color=COLOR_TEXT_PRIMARY, size=12, parent=target_tag)

    def redraw_all(self):
        """Actualiza el dibujo de las vistas tecnicas segun el modo activo."""
        if self.view_mode == "QUAD":
            self.draw_top_view()
            self.draw_front_view()
            self.draw_side_view()
        else:
            if self.active_single_view == "S":
                self.draw_top_view(tag=self.tag_draw_single, w=self.single_width - 6, h=self.single_height - 6)
            elif self.active_single_view == "F":
                self.draw_front_view(tag=self.tag_draw_single, w=self.single_width - 6, h=self.single_height - 6)
            elif self.active_single_view == "L":
                self.draw_side_view(tag=self.tag_draw_single, w=self.single_width - 6, h=self.single_height - 6)

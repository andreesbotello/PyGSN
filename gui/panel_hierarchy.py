"""
PyGSN - Hierarchy & Layers Panel
================================
Panel lateral colapsable (~290 px) con vista en árbol de los elementos del proyecto
y subpanel Inspector de Propiedades:
- Árbol jerárquico de Proyecto, Plataforma, Sensores del Rig, Observaciones y Resultados.
- Inspector interactivo para modificar en tiempo real dimensiones del chasis, lever-arms
  y desalineamiento boresight del sensor seleccionado con sincronización inmediata al lienzo CAD.
- Botones de acción rápida para añadir o eliminar sensores del rig.
"""

from typing import Callable, Any
import dearpygui.dearpygui as dpg
import numpy as np

from core.models import Sensor, SensorType
from core.project import Project


class HierarchyPanel:
    """Panel de capas, árbol del proyecto e inspector dinámico de propiedades."""

    def __init__(
        self,
        get_project: Callable[[], Project],
        on_update_callback: Callable[[], None],
        on_add_sensor_click: Callable[[], None],
        get_obs_count: Callable[[], int] | None = None
    ):
        self.get_project = get_project
        self.on_update = on_update_callback
        self.on_add_sensor_click = on_add_sensor_click
        self.get_obs_count = get_obs_count or (lambda: 0)
        self.selected_sensor_code: str | None = "PLA"

    def build_ui(self, parent_tag: str):
        with dpg.group(parent=parent_tag):
            # Cabecera del panel de capas
            with dpg.group(horizontal=True):
                dpg.add_text("Capas / Jerarquía", color=(0, 180, 216, 255))
                dpg.add_spacer(width=20)
                dpg.add_button(label="+ Sensor", small=True, callback=self.on_add_sensor_click)

            dpg.add_separator()
            dpg.add_spacer(height=3)

            # Contenedor con scroll para el árbol
            with dpg.child_window(height=310, border=True, tag="child_hierarchy_tree"):
                self.rebuild_tree()

            dpg.add_spacer(height=6)
            dpg.add_text("Inspector de Propiedades", color=(0, 180, 216, 255))
            dpg.add_separator()

            # Contenedor para el inspector del elemento seleccionado
            with dpg.child_window(height=-1, border=True, tag="child_inspector"):
                self.rebuild_inspector()

    def rebuild_tree(self):
        """Reconstruye el árbol de elementos del proyecto."""
        if not dpg.does_item_exist("child_hierarchy_tree"):
            return
        dpg.delete_item("child_hierarchy_tree", children_only=True)
        proj = self.get_project()
        plat = proj.platform

        with dpg.tree_node(label=f"Proyecto: {proj.name}", default_open=True, parent="child_hierarchy_tree"):
            # Rama: Vehículo / Chasis
            is_chassis_sel = (self.selected_sensor_code == "__CHASSIS__")
            with dpg.tree_node(label=f"Chasis: {plat.name} ({plat.length_m:.2f}x{plat.width_m:.2f}m)", default_open=True):
                dpg.add_selectable(
                    label=f"Dimensiones ({plat.length_m:.2f} x {plat.width_m:.2f} x {plat.height_m:.2f} m)",
                    default_value=is_chassis_sel,
                    callback=lambda: self._select_element("__CHASSIS__")
                )

            # Rama: Sensores Montados en el Rig
            n_sens = len(plat.sensors)
            with dpg.tree_node(label=f"Sensores del Rig ({n_sens})", default_open=True):
                for code, s in plat.sensors.items():
                    is_sel = (self.selected_sensor_code == code)
                    type_tag = f"[{s.sensor_type.value[:3]}]"
                    dpg.add_selectable(
                        label=f"{code:<6s} {type_tag} {s.name}",
                        default_value=is_sel,
                        user_data=code,
                        callback=self._cb_select_sensor
                    )

            # Rama: Observaciones Activas
            n_obs = self.get_obs_count()
            with dpg.tree_node(label=f"Observaciones ({n_obs} GNSS)"):
                if n_obs > 0:
                    dpg.add_text(f"  [*] {n_obs} antenas con datos cargados", color=(255, 209, 102, 255))
                else:
                    dpg.add_text("  [!] Sin observaciones de campo", color=(140, 150, 165, 255))

            # Rama: Productos y Resultados
            with dpg.tree_node(label="Resultados y Reportes"):
                dpg.add_text("  [-] Matriz Actitud C_b^n (SVD)")
                dpg.add_text("  [-] Coordenadas Propagadas")
                dpg.add_text("  [-] Informe Técnico TXT")

    def _cb_select_sensor(self, sender, app_data, user_data):
        self.selected_sensor_code = user_data
        self.rebuild_tree()
        self.rebuild_inspector()

    def _select_element(self, element_id: str):
        self.selected_sensor_code = element_id
        self.rebuild_tree()
        self.rebuild_inspector()

    def rebuild_inspector(self):
        """Reconstruye el inspector mostrando las propiedades del elemento seleccionado."""
        if not dpg.does_item_exist("child_inspector"):
            return
        dpg.delete_item("child_inspector", children_only=True)
        proj = self.get_project()
        plat = proj.platform

        if self.selected_sensor_code == "__CHASSIS__":
            # Inspector de dimensiones del vehiculo / plataforma
            with dpg.group(parent="child_inspector"):
                dpg.add_text("Dimensiones del Chasis", color=(255, 209, 102, 255))
                dpg.add_input_text(label="Nombre", default_value=plat.name, width=140,
                                   callback=lambda s, a: setattr(plat, "name", a))
                dpg.add_combo(label="Tipo", items=["GENERIC", "CAR", "DRONE_X4", "BOAT", "RIG"],
                              default_value=plat.platform_type, width=110,
                              callback=lambda s, a: setattr(plat, "platform_type", a))
                dpg.add_spacer(height=3)
                dpg.add_drag_float(label="Largo X (m)", default_value=plat.length_m, min_value=0.1, max_value=25.0,
                                   speed=0.05, width=90, callback=lambda s, a: self._update_chassis_dim("length_m", a))
                dpg.add_drag_float(label="Ancho Y (m)", default_value=plat.width_m, min_value=0.1, max_value=15.0,
                                   speed=0.05, width=90, callback=lambda s, a: self._update_chassis_dim("width_m", a))
                dpg.add_drag_float(label="Alto Z (m)", default_value=plat.height_m, min_value=0.05, max_value=8.0,
                                   speed=0.02, width=90, callback=lambda s, a: self._update_chassis_dim("height_m", a))
            return

        sensor = plat.get_sensor(self.selected_sensor_code or "PLA")
        if not sensor:
            dpg.add_text("Seleccione un sensor o el chasis en el árbol superior.",
                         color=(140, 150, 165, 255), parent="child_inspector")
            return

        code = sensor.code
        with dpg.group(parent="child_inspector"):
            with dpg.group(horizontal=True):
                dpg.add_text(f"Sensor: [{code}]", color=(255, 209, 102, 255))
                if code != "PLA":
                    dpg.add_spacer(width=20)
                    dpg.add_button(label="Eliminar", small=True, user_data=code, callback=self._cb_delete_sensor)

            dpg.add_combo(label="Tipo", items=["GNSS", "INS", "CAMERA", "LIDAR", "ODOMETER", "OTHER", "ORIGIN"],
                          default_value=sensor.sensor_type.value, width=110,
                          callback=lambda s, a, sc=sensor: self._cb_change_sensor_type(sc, a))

            dpg.add_input_text(label="Nombre", default_value=sensor.name, width=140,
                               callback=lambda s, a, sc=sensor: setattr(sc, "name", a))

            dpg.add_spacer(height=3)
            dpg.add_text("Brazo de Palanca r_b^s (m):", color=(0, 180, 216, 255))
            dpg.add_drag_float(label=f"x1 Adelante##insp_{code}", default_value=sensor.lever_arm_b[0],
                               speed=0.005, width=90, callback=lambda s, a: self._cb_edit_arm(code, 0, a))
            dpg.add_drag_float(label=f"x2 Derecha##insp_{code}", default_value=sensor.lever_arm_b[1],
                               speed=0.005, width=90, callback=lambda s, a: self._cb_edit_arm(code, 1, a))
            dpg.add_drag_float(label=f"x3 Abajo##insp_{code}", default_value=sensor.lever_arm_b[2],
                               speed=0.005, width=90, callback=lambda s, a: self._cb_edit_arm(code, 2, a))

            dpg.add_spacer(height=3)
            dpg.add_text("Desalineamiento Boresight (deg):", color=(0, 180, 216, 255))
            a, b, c = sensor.boresight_deg
            dpg.add_drag_float(label=f"alpha##insp_{code}", default_value=a, speed=0.05, width=90,
                               callback=lambda s, val: self._cb_edit_boresight(code, 0, val))
            dpg.add_drag_float(label=f"beta##insp_{code}", default_value=b, speed=0.05, width=90,
                               callback=lambda s, val: self._cb_edit_boresight(code, 1, val))
            dpg.add_drag_float(label=f"gamma##insp_{code}", default_value=c, speed=0.05, width=90,
                               callback=lambda s, val: self._cb_edit_boresight(code, 2, val))

    def _cb_change_sensor_type(self, sensor: Sensor, type_str: str):
        sensor.sensor_type = getattr(SensorType, type_str, SensorType.OTHER)
        self.rebuild_tree()
        self.on_update()

    def _update_chassis_dim(self, attr: str, val: float):
        plat = self.get_project().platform
        setattr(plat, attr, val)
        self.on_update()

    def _cb_edit_arm(self, code: str, axis: int, val: float):
        sensor = self.get_project().platform.get_sensor(code)
        if sensor:
            sensor.lever_arm_b[axis] = val
            self.on_update()

    def _cb_edit_boresight(self, code: str, angle_idx: int, val: float):
        sensor = self.get_project().platform.get_sensor(code)
        if sensor:
            cur = list(sensor.boresight_deg)
            cur[angle_idx] = val
            sensor.boresight_deg = (cur[0], cur[1], cur[2])
            self.on_update()

    def _cb_delete_sensor(self, sender, app_data, user_data):
        code = user_data
        self.get_project().platform.remove_sensor(code)
        self.selected_sensor_code = "PLA"
        self.rebuild_tree()
        self.rebuild_inspector()
        self.on_update()

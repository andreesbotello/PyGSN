"""
PyGSN - Platform & Sensor Rig Editor
====================================
Panel interactivo para crear y configurar cualquier plataforma (coche, dron, rover)
y gestionar la lista de sensores con sus palancas (lever-arm) y desalineamientos (boresight).
"""

from typing import Callable
import dearpygui.dearpygui as dpg
import numpy as np

from core.models import Platform, Sensor, SensorType
from core.georeferencing import create_reference_platform


class PlatformEditor:
    """Controlador del panel editor de vehiculos y sensores."""

    def __init__(self, platform: Platform, on_update_callback: Callable[[], None]):
        self.platform = platform
        self.on_update = on_update_callback

    def build_ui(self, parent_tag: str):
        with dpg.group(parent=parent_tag):
            dpg.add_text("Configuración Geométrica del Vehículo / Plataforma", color=(0, 180, 216, 255))
            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_button(label="Cargar Rig P1 (2026)", callback=self._cb_preset_p1)
                dpg.add_button(label="Preset Dron X4", callback=self._cb_preset_drone)
                dpg.add_button(label="Limpiar Todo", callback=self._cb_clear)

            with dpg.group(horizontal=True):
                dpg.add_input_text(default_value="data/calibracion_p1.txt", width=190, tag="input_body_txt_path")
                dpg.add_button(label="📂 Cargar TXT", callback=self._cb_load_txt)
                dpg.add_button(label="💾 Guardar TXT", callback=self._cb_save_txt)

            dpg.add_spacer(height=5)
            dpg.add_input_text(label="Nombre del Chasis", default_value=self.platform.name,
                               callback=self._cb_update_name, tag="input_plat_name")

            with dpg.group(horizontal=True):
                dpg.add_drag_float(label="Largo (m)", default_value=self.platform.length_m,
                                   min_value=0.2, max_value=10.0, speed=0.05, width=90,
                                   callback=self._cb_update_dims, tag="drag_plat_l")
                dpg.add_drag_float(label="Ancho (m)", default_value=self.platform.width_m,
                                   min_value=0.2, max_value=10.0, speed=0.05, width=90,
                                   callback=self._cb_update_dims, tag="drag_plat_w")
                dpg.add_drag_float(label="Alto (m)", default_value=self.platform.height_m,
                                   min_value=0.05, max_value=5.0, speed=0.02, width=90,
                                   callback=self._cb_update_dims, tag="drag_plat_h")

            dpg.add_spacer(height=10)
            dpg.add_text("Sensores Montados (b-frame y s-frame)", color=(0, 180, 216, 255))
            dpg.add_separator()

            # Formulario rapido para anadir sensor
            with dpg.collapsing_header(label="+ Añadir Nuevo Sensor", default_open=False):
                with dpg.group(horizontal=True):
                    dpg.add_input_text(label="Código", default_value="SENS1", width=70, tag="new_sens_code")
                    dpg.add_combo(label="Tipo", items=["GNSS", "INS", "CAMERA", "LIDAR", "ODOMETER", "OTHER"],
                                  default_value="GNSS", width=95, tag="new_sens_type")
                with dpg.group(horizontal=True):
                    dpg.add_drag_float(label="x1 (m)", default_value=0.0, speed=0.01, width=70, tag="new_sens_x")
                    dpg.add_drag_float(label="x2 (m)", default_value=0.0, speed=0.01, width=70, tag="new_sens_y")
                    dpg.add_drag_float(label="x3 (m)", default_value=0.0, speed=0.01, width=70, tag="new_sens_z")
                with dpg.group(horizontal=True):
                    dpg.add_drag_float(label="alpha (º)", default_value=0.0, speed=0.1, width=70, tag="new_sens_a")
                    dpg.add_drag_float(label="beta (º)", default_value=0.0, speed=0.1, width=70, tag="new_sens_b")
                    dpg.add_drag_float(label="gamma (º)", default_value=0.0, speed=0.1, width=70, tag="new_sens_c")
                dpg.add_button(label="Insertar Sensor", callback=self._cb_add_sensor)

            dpg.add_spacer(height=5)
            # Lista de sensores actuales
            dpg.add_text("Sensores Instalados:")
            with dpg.child_window(height=260, border=True, tag="child_sensor_list"):
                self.rebuild_sensor_list()

    def rebuild_sensor_list(self):
        """Reconstruye la lista de sensores con controles de edicion rapida."""
        dpg.delete_item("child_sensor_list", children_only=True)
        for code, sensor in self.platform.sensors.items():
            with dpg.group(parent="child_sensor_list"):
                with dpg.group(horizontal=True):
                    dpg.add_text(f"[{code}]", color=(255, 209, 102, 255))
                    dpg.add_text(f"{sensor.name} ({sensor.sensor_type.value})")
                    if code != "PLA":
                        dpg.add_button(label="X", user_data=code, callback=self._cb_delete_sensor,
                                       small=True)
                
                # Sliders lever-arm
                with dpg.group(horizontal=True):
                    dpg.add_drag_float(label=f"x1##{code}", default_value=sensor.lever_arm_b[0],
                                       speed=0.01, width=65, user_data=(code, 0), callback=self._cb_edit_arm)
                    dpg.add_drag_float(label=f"x2##{code}", default_value=sensor.lever_arm_b[1],
                                       speed=0.01, width=65, user_data=(code, 1), callback=self._cb_edit_arm)
                    dpg.add_drag_float(label=f"x3##{code}", default_value=sensor.lever_arm_b[2],
                                       speed=0.01, width=65, user_data=(code, 2), callback=self._cb_edit_arm)

                # Sliders boresight
                with dpg.group(horizontal=True):
                    dpg.add_drag_float(label=f"a##{code}", default_value=sensor.boresight_deg[0],
                                       speed=0.05, width=65, user_data=(code, 0), callback=self._cb_edit_ang)
                    dpg.add_drag_float(label=f"b##{code}", default_value=sensor.boresight_deg[1],
                                       speed=0.05, width=65, user_data=(code, 1), callback=self._cb_edit_ang)
                    dpg.add_drag_float(label=f"c##{code}", default_value=sensor.boresight_deg[2],
                                       speed=0.05, width=65, user_data=(code, 2), callback=self._cb_edit_ang)
                dpg.add_separator()

    def _cb_edit_arm(self, sender, app_data, user_data):
        code, axis = user_data
        if code in self.platform.sensors:
            self.platform.sensors[code].lever_arm_b[axis] = app_data
            self.on_update()

    def _cb_edit_ang(self, sender, app_data, user_data):
        code, idx = user_data
        if code in self.platform.sensors:
            angles = list(self.platform.sensors[code].boresight_deg)
            angles[idx] = app_data
            self.platform.sensors[code].boresight_deg = tuple(angles)
            self.on_update()

    def _cb_update_name(self, sender, app_data):
        self.platform.name = app_data

    def _cb_update_dims(self, sender, app_data):
        self.platform.length_m = dpg.get_value("drag_plat_l")
        self.platform.width_m = dpg.get_value("drag_plat_w")
        self.platform.height_m = dpg.get_value("drag_plat_h")
        self.on_update()

    def _cb_delete_sensor(self, sender, app_data, user_data):
        code = user_data
        self.platform.remove_sensor(code)
        self.rebuild_sensor_list()
        self.on_update()

    def _cb_add_sensor(self):
        code = dpg.get_value("new_sens_code").strip().upper()
        if not code or code in self.platform.sensors:
            return
        stype = SensorType(dpg.get_value("new_sens_type"))
        arm = np.array([
            dpg.get_value("new_sens_x"),
            dpg.get_value("new_sens_y"),
            dpg.get_value("new_sens_z")
        ], dtype=np.float64)
        ang = (
            float(dpg.get_value("new_sens_a")),
            float(dpg.get_value("new_sens_b")),
            float(dpg.get_value("new_sens_c"))
        )
        self.platform.add_sensor(Sensor(code=code, name=f"Sensor {code}", sensor_type=stype,
                                        lever_arm_b=arm, boresight_deg=ang))
        self.rebuild_sensor_list()
        self.on_update()

    def _cb_preset_p1(self):
        default_p1 = create_reference_platform()
        self.platform.name = default_p1.name
        self.platform.length_m = default_p1.length_m
        self.platform.width_m = default_p1.width_m
        self.platform.height_m = default_p1.height_m
        self.platform.sensors = default_p1.sensors
        dpg.set_value("input_plat_name", self.platform.name)
        dpg.set_value("drag_plat_l", self.platform.length_m)
        dpg.set_value("drag_plat_w", self.platform.width_m)
        dpg.set_value("drag_plat_h", self.platform.height_m)
        self.rebuild_sensor_list()
        self.on_update()

    def _cb_preset_drone(self):
        self.platform.name = "Dron Cuadricoptero X4"
        self.platform.length_m = 0.6
        self.platform.width_m = 0.6
        self.platform.height_m = 0.2
        self.platform.sensors.clear()
        self.platform.add_sensor(Sensor("PLA", "Centro Masa", SensorType.PLATFORM_ORIGIN, np.zeros(3)))
        self.platform.add_sensor(Sensor("IMU", "Pixhawk 6X", SensorType.INS, np.array([0.0, 0.0, -0.01])))
        self.platform.add_sensor(Sensor("GNSS1", "Here3 GPS", SensorType.GNSS, np.array([0.0, 0.0, -0.15])))
        self.platform.add_sensor(Sensor("CAM_G", "Gimbal 4K", SensorType.CAMERA, np.array([0.15, 0.0, 0.08]), (0, 30, 0)))
        dpg.set_value("input_plat_name", self.platform.name)
        dpg.set_value("drag_plat_l", self.platform.length_m)
        dpg.set_value("drag_plat_w", self.platform.width_m)
        dpg.set_value("drag_plat_h", self.platform.height_m)
        self.rebuild_sensor_list()
        self.on_update()

    def _cb_clear(self):
        self.platform.sensors.clear()
        self.platform.add_sensor(Sensor("PLA", "Origen", SensorType.PLATFORM_ORIGIN, np.zeros(3)))
        self.rebuild_sensor_list()
        self.on_update()

    def _cb_load_txt(self):
        from pathlib import Path
        path_str = dpg.get_value("input_body_txt_path").strip()
        p = Path(path_str)
        if p.exists():
            content = p.read_text(encoding="utf-8")
            loaded = Platform.from_txt(content)
            self.platform.name = loaded.name
            self.platform.length_m = loaded.length_m
            self.platform.width_m = loaded.width_m
            self.platform.height_m = loaded.height_m
            self.platform.sensors = loaded.sensors
            dpg.set_value("input_plat_name", self.platform.name)
            dpg.set_value("drag_plat_l", self.platform.length_m)
            dpg.set_value("drag_plat_w", self.platform.width_m)
            dpg.set_value("drag_plat_h", self.platform.height_m)
            self.rebuild_sensor_list()
            self.on_update()

    def _cb_save_txt(self):
        from pathlib import Path
        path_str = dpg.get_value("input_body_txt_path").strip()
        if not path_str:
            path_str = "data/mi_plataforma.txt"
        p = Path(path_str)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.platform.to_txt(), encoding="utf-8")


"""
PyGSN - GUI Modals Module
=========================
Dialogos modales para gestion de proyectos, configuracion geodesica y componentes del rig:
- Modal Nuevo Proyecto (elipsoide, zona UTM con hemisferio, ondulacion N, declinacion)
- Modal Propiedades del Proyecto
- Apertura y Guardado de Proyectos mediante el Explorador de Archivos Nativo del Sistema Operativo
- Modal Anadir Sensor al Rig
- Modal Acerca de PyGSN
"""

from pathlib import Path
from typing import Callable, Optional
import dearpygui.dearpygui as dpg
import numpy as np

from core.models import Platform, Sensor, SensorType, PlatformType
from core.assets import VehicleMesh
from core.project import Project
from core.geodesy import GRS80, WGS84, geodetic_to_ecef, ecef_to_geodetic, rad_to_dms


# -----------------------------------------------------------------------------
# Explorador de Archivos Nativo del Sistema Operativo (Windows Explorer / OS)
# -----------------------------------------------------------------------------
def pick_open_file_native(
    title: str = "Abrir Proyecto PyGSN",
    filetypes: tuple = (
        ("Archivos de Proyecto PyGSN (*.pygsn)", "*.pygsn"),
        ("Archivos JSON (*.json)", "*.json"),
        ("Todos los archivos (*.*)", "*.*")
    ),
    initialdir: Optional[str | Path] = None
) -> str:
    """Abre el explorador de archivos nativo del sistema operativo (Windows Explorer)."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        init_dir = str(Path(initialdir).resolve()) if initialdir and Path(initialdir).exists() else None
        selected = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes,
            initialdir=init_dir
        )
    finally:
        root.destroy()
    return selected or ""


def pick_save_file_native(
    title: str = "Guardar Proyecto Como... - PyGSN",
    defaultextension: str = ".pygsn",
    filetypes: tuple = (
        ("Archivos de Proyecto PyGSN (*.pygsn)", "*.pygsn"),
        ("Archivos JSON (*.json)", "*.json"),
        ("Todos los archivos (*.*)", "*.*")
    ),
    initialdir: Optional[str | Path] = None
) -> str:
    """Abre el explorador de archivos nativo de Windows para guardar archivos."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        init_dir = str(Path(initialdir).resolve()) if initialdir and Path(initialdir).exists() else None
        selected = filedialog.asksaveasfilename(
            title=title,
            defaultextension=defaultextension,
            filetypes=filetypes,
            initialdir=init_dir
        )
    finally:
        root.destroy()
    return selected or ""


class ProjectModals:
    """Manejador universal de ventanas modales y dialogos de configuracion."""

    def __init__(
        self,
        get_project: Callable[[], Project],
        set_project: Callable[[Project, Optional[Path]], None],
        on_project_updated: Callable[[], None],
        on_center_origin: Callable[[], None] | None = None,
        on_center_centroid: Callable[[], None] | None = None
    ):
        self.get_project = get_project
        self.set_project = set_project
        self.on_project_updated = on_project_updated
        self.on_center_origin = on_center_origin
        self.on_center_centroid = on_center_centroid
        self.active_chassis_plat_id: str | None = None

    def build_modals(self):
        """Construye las ventanas modales ocultas en el contexto de DearPyGui."""
        self._build_modal_new_project()
        self._build_modal_project_properties()
        self._build_modal_create_platform()
        self._build_modal_chassis_actions()
        self._build_modal_add_sensor()
        self._build_modal_frame_transform()
        self._build_modal_diagnostics()
        self._build_modal_about()

    # -------------------------------------------------------------------------
    # Utilidad: centrar una ventana modal
    # -------------------------------------------------------------------------
    @staticmethod
    def _center_window(tag: str, w: int, h: int):
        """Posiciona una ventana modal en el centro del viewport."""
        vw = dpg.get_viewport_width()
        vh = dpg.get_viewport_height()
        x = max(0, (vw - w) // 2)
        y = max(0, (vh - h) // 2)
        dpg.set_item_pos(tag, [x, y])

    # -------------------------------------------------------------------------
    # 1. Modal: Nuevo Proyecto
    # -------------------------------------------------------------------------
    def _build_modal_new_project(self):
        W, H = 540, 330
        with dpg.window(
            label="Crear Nuevo Proyecto", tag="modal_new_project",
            modal=True, show=False, no_resize=True,
            width=W, height=H, no_title_bar=False,
            pos=[0, 0]
        ):
            dpg.add_text("Configuracion del Nuevo Proyecto", color=(0, 180, 216, 255))
            dpg.add_separator()
            dpg.add_spacer(height=6)

            with dpg.table(header_row=False, borders_innerH=False, borders_innerV=False,
                           borders_outerH=False, borders_outerV=False):
                dpg.add_table_column(width_fixed=True, init_width_or_weight=180)
                dpg.add_table_column(width_stretch=True)

                # Fila 1: Nombre
                with dpg.table_row():
                    dpg.add_text("Nombre del Proyecto:")
                    dpg.add_input_text(default_value="Proyecto Nuevo", width=-1, tag="modal_new_proj_name")

                # Fila 2: Elipsoide
                with dpg.table_row():
                    dpg.add_text("Elipsoide de Referencia:")
                    dpg.add_combo(items=["GRS80", "WGS84"], default_value="GRS80", width=-1, tag="modal_new_proj_ellipsoid")

                # Fila 3: Huso UTM y Hemisferio
                with dpg.table_row():
                    dpg.add_text("Huso UTM y Hemisferio:")
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(default_value="30", width=65, tag="modal_new_proj_utm", decimal=True)
                        dpg.add_spacer(width=10)
                        dpg.add_text("Hemisferio:")
                        dpg.add_combo(items=["Norte", "Sur"], default_value="Norte", width=105, tag="modal_new_proj_hemisphere")

                # Fila 4: Ondulacion N
                with dpg.table_row():
                    dpg.add_text("Ondulacion Geoidal N (m):")
                    dpg.add_input_float(default_value=0.000, step=0.0, step_fast=0.0, format="%.4f", width=-1, tag="modal_new_proj_geoid")

                # Fila 5: Declinacion Magnetica
                with dpg.table_row():
                    dpg.add_text("Declinacion Mag. (deg):")
                    dpg.add_input_float(default_value=0.000, step=0.0, step_fast=0.0, format="%.4f", width=-1, tag="modal_new_proj_decl")

            dpg.add_spacer(height=14)
            dpg.add_separator()
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=220)
                dpg.add_button(
                    label="Crear Proyecto", width=140,
                    callback=self._cb_confirm_new_project
                )
                dpg.add_button(
                    label="Cancelar", width=90,
                    callback=lambda: dpg.configure_item("modal_new_project", show=False)
                )

    def show_new_project(self):
        """Muestra el modal Nuevo Proyecto centrado."""
        W, H = 540, 330
        dpg.configure_item("modal_new_project", show=True)
        self._center_window("modal_new_project", W, H)

    def _cb_confirm_new_project(self):
        name = dpg.get_value("modal_new_proj_name").strip() or "Proyecto Nuevo"
        ell  = dpg.get_value("modal_new_proj_ellipsoid")

        # Huso UTM: parsear solo digitos del string
        utm_raw = dpg.get_value("modal_new_proj_utm").strip()
        try:
            utm = max(1, min(60, int("".join(c for c in utm_raw if c.isdigit()) or "30")))
        except ValueError:
            utm = 30
        hemi = dpg.get_value("modal_new_proj_hemisphere")  # "Norte" | "Sur"
        utm_signed = utm if hemi == "Norte" else -utm  # negativo = Sur

        geoid_n = float(dpg.get_value("modal_new_proj_geoid"))
        decl    = float(dpg.get_value("modal_new_proj_decl"))

        # Proyecto 100% limpio sin plataformas iniciales ni sensores ficticios
        new_proj = Project(
            name=name,
            description="Proyecto de Georreferenciacion de Sensores y Navegacion",
            ellipsoid_name=ell,
            platforms={},
            config={
                "utm_zone": utm_signed,
                "geoid_undulation_n": geoid_n,
                "mag_declination_deg": decl
            }
        )
        self.set_project(new_proj, None)
        dpg.configure_item("modal_new_project", show=False)
        self.on_project_updated()

    # -------------------------------------------------------------------------
    # 2. Modal: Propiedades del Proyecto
    # -------------------------------------------------------------------------
    def _build_modal_project_properties(self):
        W, H = 540, 330
        with dpg.window(
            label="Propiedades del Proyecto", tag="modal_project_properties",
            modal=True, show=False, no_resize=True,
            width=W, height=H, pos=[0, 0]
        ):
            dpg.add_text("Parametros y Metadatos Activos", color=(0, 180, 216, 255))
            dpg.add_separator()
            dpg.add_spacer(height=6)

            with dpg.table(header_row=False, borders_innerH=False, borders_innerV=False,
                           borders_outerH=False, borders_outerV=False):
                dpg.add_table_column(width_fixed=True, init_width_or_weight=180)
                dpg.add_table_column(width_stretch=True)

                # Fila 1: Nombre
                with dpg.table_row():
                    dpg.add_text("Nombre del Proyecto:")
                    dpg.add_input_text(width=-1, tag="prop_proj_name")

                # Fila 2: Elipsoide
                with dpg.table_row():
                    dpg.add_text("Elipsoide de Referencia:")
                    dpg.add_combo(items=["GRS80", "WGS84"], width=-1, tag="prop_proj_ellipsoid")

                # Fila 3: Huso UTM y Hemisferio
                with dpg.table_row():
                    dpg.add_text("Huso UTM y Hemisferio:")
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(width=65, tag="prop_proj_utm", decimal=True)
                        dpg.add_spacer(width=10)
                        dpg.add_text("Hemisferio:")
                        dpg.add_combo(items=["Norte", "Sur"], default_value="Norte", width=105, tag="prop_proj_hemisphere")

                # Fila 4: Ondulacion N
                with dpg.table_row():
                    dpg.add_text("Ondulacion Geoidal N (m):")
                    dpg.add_input_float(step=0.0, step_fast=0.0, format="%.4f", width=-1, tag="prop_proj_geoid")

                # Fila 5: Declinacion Magnetica
                with dpg.table_row():
                    dpg.add_text("Declinacion Mag. (deg):")
                    dpg.add_input_float(step=0.0, step_fast=0.0, format="%.4f", width=-1, tag="prop_proj_decl")

            dpg.add_spacer(height=14)
            dpg.add_separator()
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=220)
                dpg.add_button(
                    label="Aplicar Cambios", width=140,
                    callback=self._cb_apply_project_properties
                )
                dpg.add_button(
                    label="Cerrar", width=90,
                    callback=lambda: dpg.configure_item("modal_project_properties", show=False)
                )

    def show_project_properties(self):
        proj = self.get_project()
        dpg.set_value("prop_proj_name", proj.name)
        dpg.set_value("prop_proj_ellipsoid", proj.ellipsoid_name)
        utm_val = proj.config.get("utm_zone", 30)
        hemi = "Norte" if utm_val >= 0 else "Sur"
        dpg.set_value("prop_proj_utm", str(abs(utm_val)))
        dpg.set_value("prop_proj_hemisphere", hemi)
        dpg.set_value("prop_proj_geoid", proj.config.get("geoid_undulation_n", 0.0))
        dpg.set_value("prop_proj_decl", proj.config.get("mag_declination_deg", 0.0))
        W, H = 540, 330
        dpg.configure_item("modal_project_properties", show=True)
        self._center_window("modal_project_properties", W, H)

    def _cb_apply_project_properties(self):
        proj = self.get_project()
        proj.name = dpg.get_value("prop_proj_name").strip() or proj.name
        proj.ellipsoid_name = dpg.get_value("prop_proj_ellipsoid")

        utm_raw = dpg.get_value("prop_proj_utm").strip()
        try:
            utm = max(1, min(60, int("".join(c for c in utm_raw if c.isdigit()) or "30")))
        except ValueError:
            utm = 30
        hemi = dpg.get_value("prop_proj_hemisphere")
        proj.config["utm_zone"] = utm if hemi == "Norte" else -utm
        proj.config["geoid_undulation_n"] = float(dpg.get_value("prop_proj_geoid"))
        proj.config["mag_declination_deg"] = float(dpg.get_value("prop_proj_decl"))

        dpg.configure_item("modal_project_properties", show=False)
        self.on_project_updated()

    # -------------------------------------------------------------------------
    # 3. Abrir Proyecto: Explorador de Archivos Nativo del Sistema Operativo
    # -------------------------------------------------------------------------
    def open_project_dialog(self):
        """Abre el explorador de archivos nativo del SO (Windows Explorer) para cargar un proyecto."""
        selected = pick_open_file_native(
            title="Abrir Proyecto PyGSN",
            filetypes=(
                ("Archivos de Proyecto PyGSN (*.pygsn)", "*.pygsn"),
                ("Archivos JSON (*.json)", "*.json"),
                ("Todos los archivos (*.*)", "*.*")
            ),
            initialdir="data"
        )
        if not selected:
            return
        p = Path(selected)
        if not p.exists():
            return
        try:
            loaded_proj = Project.load(p)
            self.set_project(loaded_proj, p)
            self.on_project_updated()
            if dpg.does_item_exist("status_bar_state"):
                dpg.set_value("status_bar_state", f"[OK] Proyecto cargado: {p.name}")
        except Exception as e:
            if dpg.does_item_exist("status_bar_state"):
                dpg.set_value("status_bar_state", f"Error al cargar proyecto: {str(e)[:45]}")

    # -------------------------------------------------------------------------
    # 4. Guardar Proyecto Como...: Explorador Nativo de Guardado
    # -------------------------------------------------------------------------
    def show_save_project(self):
        """Abre el explorador de archivos nativo del SO para Guardar Proyecto Como..."""
        selected = pick_save_file_native(
            title="Guardar Proyecto Como... - PyGSN",
            defaultextension=".pygsn",
            filetypes=(
                ("Archivos de Proyecto PyGSN (*.pygsn)", "*.pygsn"),
                ("Archivos JSON (*.json)", "*.json"),
                ("Todos los archivos (*.*)", "*.*")
            ),
            initialdir="data"
        )
        if not selected:
            return
        p = Path(selected)
        try:
            proj = self.get_project()
            proj.save(p)
            self.set_project(proj, p)
            if dpg.does_item_exist("status_bar_state"):
                dpg.set_value("status_bar_state", f"[OK] Guardado en: {p.name}")
        except Exception as e:
            if dpg.does_item_exist("status_bar_state"):
                dpg.set_value("status_bar_state", f"Error al guardar: {str(e)[:45]}")

    # -------------------------------------------------------------------------
    # 5. Modal: Anadir Sensor
    # -------------------------------------------------------------------------
    def _build_modal_add_sensor(self):
        W, H = 450, 360
        with dpg.window(
            label="Anadir Nuevo Sensor al Rig", tag="modal_add_sensor",
            modal=True, show=False, no_resize=True,
            width=W, height=H, pos=[0, 0]
        ):
            dpg.add_text("Definicion de Sensor en Plataforma", color=(0, 180, 216, 255))
            dpg.add_separator()
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    label="Codigo", default_value="GNSS_1",
                    width=100, tag="modal_sens_code"
                )
                dpg.add_combo(
                    label="Tipo",
                    items=["GNSS", "INS", "CAMERA", "LIDAR", "ODOMETER", "OTHER"],
                    default_value="GNSS", width=120, tag="modal_sens_type",
                    callback=self._cb_sens_type_changed
                )

            dpg.add_input_text(
                label="Nombre", default_value="Antena GNSS Primaria",
                width=270, tag="modal_sens_name"
            )
            dpg.add_spacer(height=5)

            dpg.add_text("Brazo de Palanca en b-frame (m):", color=(255, 209, 102, 255))
            with dpg.group(horizontal=True):
                dpg.add_drag_float(label="x1 Adelante", default_value=0.0, speed=0.01, width=80, tag="modal_sens_x")
                dpg.add_drag_float(label="x2 Derecha",  default_value=0.0, speed=0.01, width=80, tag="modal_sens_y")
                dpg.add_drag_float(label="x3 Abajo",    default_value=0.0, speed=0.01, width=80, tag="modal_sens_z")

            dpg.add_spacer(height=5)
            dpg.add_text("Desalineamiento Boresight C_s^b (deg):", color=(255, 209, 102, 255))
            with dpg.group(horizontal=True):
                dpg.add_drag_float(label="alpha (x)", default_value=0.0, speed=0.05, width=80, tag="modal_sens_alpha")
                dpg.add_drag_float(label="beta (y)",  default_value=0.0, speed=0.05, width=80, tag="modal_sens_beta")
                dpg.add_drag_float(label="gamma (z)", default_value=0.0, speed=0.05, width=80, tag="modal_sens_gamma")

            dpg.add_separator()
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Anadir Sensor", width=130,
                    callback=self._cb_confirm_add_sensor
                )
                dpg.add_button(
                    label="Cancelar", width=90,
                    callback=lambda: dpg.configure_item("modal_add_sensor", show=False)
                )

    def show_add_sensor(self):
        W, H = 450, 360
        dpg.configure_item("modal_add_sensor", show=True)
        self._center_window("modal_add_sensor", W, H)

    def _cb_sens_type_changed(self, sender, app_data):
        stype = app_data
        plat = self.get_project().platform
        count = sum(1 for s in plat.sensors.values() if s.sensor_type.value == stype) + 1
        dpg.set_value("modal_sens_code", f"{stype}_{count}")
        names = {
            "GNSS":     f"Antena GNSS {count}",
            "INS":      f"Unidad Inercial IMU/INS {count}",
            "CAMERA":   f"Camara Optica {count}",
            "LIDAR":    f"Sensor LiDAR {count}",
            "ODOMETER": f"Odometro de Rueda {count}",
            "OTHER":    f"Sensor Auxiliar {count}"
        }
        dpg.set_value("modal_sens_name", names.get(stype, f"Sensor {count}"))

    def _cb_confirm_add_sensor(self):
        code    = dpg.get_value("modal_sens_code").strip().upper()
        name    = dpg.get_value("modal_sens_name").strip() or code
        tipo_str = dpg.get_value("modal_sens_type")
        x = float(dpg.get_value("modal_sens_x"))
        y = float(dpg.get_value("modal_sens_y"))
        z = float(dpg.get_value("modal_sens_z"))
        a = float(dpg.get_value("modal_sens_alpha"))
        b = float(dpg.get_value("modal_sens_beta"))
        c = float(dpg.get_value("modal_sens_gamma"))

        stype = getattr(SensorType, tipo_str, SensorType.OTHER)
        s = Sensor(
            code=code, name=name, sensor_type=stype,
            lever_arm_b=np.array([x, y, z], dtype=np.float64),
            boresight_deg=(a, b, c)
        )
        proj = self.get_project()
        proj.platform.add_sensor(s)
        dpg.configure_item("modal_add_sensor", show=False)
        self.on_project_updated()

    # -------------------------------------------------------------------------
    # 6. Modal: Acerca de PyGSN
    # -------------------------------------------------------------------------
    def _build_modal_about(self):
        W, H = 460, 250
        with dpg.window(
            label="Acerca de PyGSN", tag="modal_about",
            modal=True, show=False, no_resize=True,
            width=W, height=H, pos=[0, 0]
        ):
            dpg.add_text("PyGSN - Georreferenciacion de Sensores y Navegacion", color=(0, 180, 216, 255))
            dpg.add_text("Version: 1.0.0  |  Licencia: GPLv3", color=(140, 150, 165, 255))
            dpg.add_separator()
            dpg.add_spacer(height=5)
            dpg.add_text(
                "Software modular de ingenieria para la cinematica de marcos\n"
                "de referencia (i/e/n/b/s-frame), determinacion de actitud\n"
                "mediante Procrustes SVD (Kabsch) y georreferenciacion rigurosa\n"
                "de rigs multisensor (GNSS, INS, Camaras, LiDAR, Odometros).\n\n"
                "Convencion de navegacion: Jekeli / Hoffmann / Groves.\n"
                "Calculo matricial optimizado en NumPy/SciPy (np.float64)."
            )
            dpg.add_spacer(height=10)
            dpg.add_separator()
            dpg.add_button(
                label="Cerrar", width=100,
                callback=lambda: dpg.configure_item("modal_about", show=False)
            )

    def show_about(self):
        W, H = 460, 250
        dpg.configure_item("modal_about", show=True)
        self._center_window("modal_about", W, H)

    # -------------------------------------------------------------------------
    # 7. Modal: Crear Plataforma (Vehiculo o Estacion Base)
    # -------------------------------------------------------------------------
    def _build_modal_create_platform(self):
        W, H = 540, 370
        with dpg.window(
            label="Crear Nueva Plataforma", tag="modal_create_platform",
            modal=True, show=False, no_resize=True,
            width=W, height=H, pos=[0, 0]
        ):
            dpg.add_text("Definicion de Plataforma en el Proyecto", color=(0, 180, 216, 255))
            dpg.add_separator()
            dpg.add_spacer(height=6)

            with dpg.table(header_row=False, borders_innerH=False, borders_innerV=False,
                           borders_outerH=False, borders_outerV=False):
                dpg.add_table_column(width_fixed=True, init_width_or_weight=180)
                dpg.add_table_column(width_stretch=True)

                with dpg.table_row():
                    dpg.add_text("Identificador Unico:")
                    dpg.add_input_text(default_value="PLAT_1", width=-1, tag="modal_plat_id")

                with dpg.table_row():
                    dpg.add_text("Nombre Descriptivo:")
                    dpg.add_input_text(default_value="Vehiculo Principal", width=-1, tag="modal_plat_name")

                with dpg.table_row():
                    dpg.add_text("Tipo de Plataforma:")
                    dpg.add_combo(
                        items=["VEHICLE", "ROVER", "CAR", "DRONE_X4", "BASE_STATION", "TEST_BENCH", "GENERIC"],
                        default_value="VEHICLE", width=-1, tag="modal_plat_type"
                    )

                with dpg.table_row():
                    dpg.add_text("Estacion fija de referencia:")
                    dpg.add_checkbox(default_value=False, tag="modal_plat_is_fixed")

                with dpg.table_row():
                    dpg.add_text("Dimensiones del chasis:")
                    dpg.add_checkbox(
                        label="Definir caja envolvente",
                        default_value=False,
                        tag="modal_plat_has_dims",
                        callback=lambda s, a: dpg.configure_item("row_plat_dims", show=a)
                    )

                with dpg.table_row(tag="row_plat_dims", show=False):
                    dpg.add_text("Dimensiones (L x W x H m):")
                    with dpg.group(horizontal=True):
                        dpg.add_drag_float(label="X", default_value=2.0, speed=0.05, width=65, tag="modal_plat_l")
                        dpg.add_drag_float(label="Y", default_value=1.0, speed=0.05, width=65, tag="modal_plat_w")
                        dpg.add_drag_float(label="Z", default_value=0.5, speed=0.05, width=65, tag="modal_plat_h")

            dpg.add_spacer(height=12)
            dpg.add_separator()
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=200)
                dpg.add_button(label="Crear Plataforma", width=160, callback=self._cb_confirm_create_platform)
                dpg.add_button(label="Cancelar", width=90, callback=lambda: dpg.configure_item("modal_create_platform", show=False))

    def show_create_platform(self):
        W, H = 540, 370
        proj = self.get_project()
        next_idx = len(proj.platforms) + 1
        dpg.set_value("modal_plat_id", f"PLAT_{next_idx}")
        dpg.set_value("modal_plat_name", f"Plataforma {next_idx}")
        dpg.set_value("modal_plat_has_dims", False)
        if dpg.does_item_exist("row_plat_dims"):
            dpg.configure_item("row_plat_dims", show=False)
        dpg.configure_item("modal_create_platform", show=True)
        self._center_window("modal_create_platform", W, H)

    def _cb_confirm_create_platform(self):
        pid = dpg.get_value("modal_plat_id").strip().upper() or f"PLAT_{len(self.get_project().platforms)+1}"
        name = dpg.get_value("modal_plat_name").strip() or pid
        ptype = dpg.get_value("modal_plat_type")
        is_fixed = bool(dpg.get_value("modal_plat_is_fixed"))
        has_dims = bool(dpg.get_value("modal_plat_has_dims"))
        l_m = float(dpg.get_value("modal_plat_l")) if has_dims else 0.0
        w_m = float(dpg.get_value("modal_plat_w")) if has_dims else 0.0
        h_m = float(dpg.get_value("modal_plat_h")) if has_dims else 0.0

        new_plat = Platform(
            id=pid,
            name=name,
            platform_type=ptype,
            is_fixed=is_fixed,
            has_dimensions=has_dims,
            length_m=l_m,
            width_m=w_m,
            height_m=h_m
        )
        proj = self.get_project()
        proj.add_platform(new_plat, set_active=True)
        dpg.configure_item("modal_create_platform", show=False)
        self.on_project_updated()

    # -------------------------------------------------------------------------
    # 7.1. Modal: Acciones de Chasis (Centrar al Origen, Centrar al Centroide)
    # -------------------------------------------------------------------------
    def _build_modal_chassis_actions(self):
        W, H = 340, 180
        with dpg.window(
            label="Acciones de Chasis", tag="modal_chassis_actions",
            modal=True, show=False, no_resize=True,
            width=W, height=H, pos=[0, 0]
        ):
            dpg.add_text("Acciones de Visualizacion", color=(0, 180, 216, 255))
            dpg.add_separator()
            dpg.add_spacer(height=6)
            dpg.add_button(
                label="Centrar al Origen [0, 0]", width=-1,
                callback=self._cb_chassis_center_origin
            )
            dpg.add_spacer(height=4)
            dpg.add_button(
                label="Centrar al Centroide", width=-1,
                callback=self._cb_chassis_center_centroid
            )
            dpg.add_spacer(height=8)
            dpg.add_separator()
            dpg.add_spacer(height=4)
            dpg.add_button(
                label="Cerrar", width=-1,
                callback=lambda: dpg.configure_item("modal_chassis_actions", show=False)
            )

    def show_chassis_actions(self, plat_id: str):
        self.active_chassis_plat_id = plat_id
        W, H = 340, 180
        dpg.configure_item("modal_chassis_actions", show=True)
        self._center_window("modal_chassis_actions", W, H)

    def _cb_chassis_center_origin(self):
        dpg.configure_item("modal_chassis_actions", show=False)
        if self.on_center_origin:
            self.on_center_origin()

    def _cb_chassis_center_centroid(self):
        dpg.configure_item("modal_chassis_actions", show=False)
        if self.on_center_centroid:
            self.on_center_centroid()

    # -------------------------------------------------------------------------
    # 8. Modal: Transformacion de Marcos (Frame Transformations)
    # -------------------------------------------------------------------------
    def _build_modal_frame_transform(self):
        W, H = 580, 420
        with dpg.window(
            label="Transformador de Marcos de Referencia (i / e / n / b / s)",
            tag="modal_frame_transform",
            modal=True, show=False, no_resize=True,
            width=W, height=H, pos=[0, 0]
        ):
            dpg.add_text("Conversión de Coordenadas Geodésicas <-> Cartesianas ECEF", color=(0, 180, 216, 255))
            dpg.add_separator()
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_text("Modo:")
                dpg.add_combo(items=["Geodesicas -> ECEF", "ECEF -> Geodesicas"], default_value="Geodesicas -> ECEF",
                              width=220, tag="ft_mode")
                dpg.add_spacer(width=10)
                dpg.add_text("Elipsoide:")
                dpg.add_combo(items=["GRS80", "WGS84"], default_value="GRS80", width=110, tag="ft_ellips")

            dpg.add_spacer(height=5)
            dpg.add_text("Entradas:", color=(255, 209, 102, 255))
            with dpg.group(horizontal=True):
                dpg.add_input_float(label="Lat / X", default_value=39.482000, format="%.6f", width=130, tag="ft_in_1")
                dpg.add_input_float(label="Lon / Y", default_value=-0.347500, format="%.6f", width=130, tag="ft_in_2")
                dpg.add_input_float(label="h / Z",   default_value=50.000,    format="%.3f", width=130, tag="ft_in_3")

            dpg.add_spacer(height=5)
            dpg.add_button(label="Ejecutar Transformacion", width=190, callback=self._cb_calc_frame_transform)
            dpg.add_spacer(height=8)
            dpg.add_separator()
            dpg.add_text("Resultados Transformados:", color=(6, 214, 160, 255))

            with dpg.child_window(height=160, border=True, tag="ft_results_box"):
                dpg.add_text("Pulse 'Ejecutar Transformacion' para visualizar resultados.", tag="ft_result_text")

            dpg.add_spacer(height=8)
            dpg.add_separator()
            dpg.add_button(label="Cerrar", width=100, callback=lambda: dpg.configure_item("modal_frame_transform", show=False))

    def show_frame_transform(self):
        W, H = 580, 420
        dpg.configure_item("modal_frame_transform", show=True)
        self._center_window("modal_frame_transform", W, H)

    def _cb_calc_frame_transform(self):
        mode = dpg.get_value("ft_mode")
        ell_name = dpg.get_value("ft_ellips")
        ell = GRS80 if ell_name == "GRS80" else WGS84
        v1 = float(dpg.get_value("ft_in_1"))
        v2 = float(dpg.get_value("ft_in_2"))
        v3 = float(dpg.get_value("ft_in_3"))

        try:
            if "Geodesicas -> ECEF" in mode:
                lat_rad = np.radians(v1)
                lon_rad = np.radians(v2)
                h_m = v3
                ecef = geodetic_to_ecef(lat_rad, lon_rad, h_m, ell)
                res_lines = [
                    f"Entrada Geodésica: {v1:.8f}° N, {v2:.8f}° E, h={h_m:.3f} m",
                    f"Elipsoide: {ell_name} (a={ell.a:.3f} m, 1/f={ell.inv_f:.6f})",
                    "",
                    "Coordenadas Cartesianas ECEF (e-frame):",
                    f"  X_e = {ecef[0]:15.4f} m",
                    f"  Y_e = {ecef[1]:15.4f} m",
                    f"  Z_e = {ecef[2]:15.4f} m",
                    f"  Distancia al centro: {np.linalg.norm(ecef):15.4f} m"
                ]
            else:
                ecef = np.array([v1, v2, v3], dtype=np.float64)
                lat_r, lon_r, h_m = ecef_to_geodetic(ecef, ell)
                lat_deg = float(np.degrees(lat_r))
                lon_deg = float(np.degrees(lon_r))
                d_lat, m_lat, s_lat = rad_to_dms(lat_r)
                d_lon, m_lon, s_lon = rad_to_dms(lon_r)
                res_lines = [
                    f"Entrada ECEF: X={v1:.4f}, Y={v2:.4f}, Z={v3:.4f} m",
                    f"Elipsoide: {ell_name}",
                    "",
                    "Coordenadas Geodésicas Elipsoidales:",
                    f"  Latitud  (phi) : {lat_deg:14.8f}°  ({abs(d_lat)}° {abs(m_lat)}' {abs(s_lat):.4f}\" {'N' if lat_deg >= 0 else 'S'})",
                    f"  Longitud (lam) : {lon_deg:14.8f}°  ({abs(d_lon)}° {abs(m_lon)}' {abs(s_lon):.4f}\" {'E' if lon_deg >= 0 else 'W'})",
                    f"  Altitud  (h)   : {h_m:14.4f} m"
                ]
            dpg.set_value("ft_result_text", "\n".join(res_lines))
        except Exception as e:
            dpg.set_value("ft_result_text", f"Error de transformacion: {str(e)}")

    # -------------------------------------------------------------------------
    # 9. Modal: Diagnostico SVD y Matrices
    # -------------------------------------------------------------------------
    def _build_modal_diagnostics(self):
        W, H = 600, 420
        with dpg.window(
            label="Diagnostico SVD y Auditoria de Matrices DCM",
            tag="modal_diagnostics",
            modal=True, show=False, no_resize=True,
            width=W, height=H, pos=[0, 0]
        ):
            dpg.add_text("Auditoria Espectral SVD y Consistencia de Actitud", color=(239, 71, 111, 255))
            dpg.add_separator()
            dpg.add_spacer(height=5)

            with dpg.child_window(height=310, border=True, tag="child_diag_box"):
                dpg.add_text("Sin cálculo previo de georreferenciación. Ejecute 'Resolver SVD' primero.", tag="diag_content_text")

            dpg.add_spacer(height=8)
            dpg.add_separator()
            dpg.add_button(label="Cerrar", width=100, callback=lambda: dpg.configure_item("modal_diagnostics", show=False))

    def show_diagnostics(self, solution=None):
        W, H = 600, 420
        dpg.configure_item("modal_diagnostics", show=True)
        self._center_window("modal_diagnostics", W, H)

        if solution is None:
            dpg.set_value("diag_content_text", "No hay solucion de georreferenciacion calculada en la sesion actual.\nCargue observaciones GNSS y presione [Resolver SVD].")
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
                f"4. Consistencia con Sensor INS:",
                f"   - Actitud Total INS (corregida boresight + declinación):",
                f"     Roll={solution.attitude_ins_total_deg[0]:+.4f}°, Pitch={solution.attitude_ins_total_deg[1]:+.4f}°, Yaw={solution.attitude_ins_total_deg[2]:+.4f}°"
            ]
            dpg.set_value("diag_content_text", "\n".join(lines))
        except Exception as e:
            dpg.set_value("diag_content_text", f"Error al generar diagnostico: {str(e)}")

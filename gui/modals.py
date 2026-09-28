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

from core.models import Platform, Sensor, SensorType
from core.assets import VehicleMesh
from core.project import Project


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
        on_project_updated: Callable[[], None]
    ):
        self.get_project = get_project
        self.set_project = set_project
        self.on_project_updated = on_project_updated

    def build_modals(self):
        """Construye las ventanas modales ocultas en el contexto de DearPyGui."""
        self._build_modal_new_project()
        self._build_modal_project_properties()
        self._build_modal_add_sensor()
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

        # Plataforma limpia con solo origen
        plat = Platform(
            name="Plataforma Principal", platform_type="GENERIC",
            length_m=2.0, width_m=1.0, height_m=0.5
        )
        plat.add_sensor(Sensor(
            code="PLA", name="Origen de Plataforma",
            sensor_type=SensorType.PLATFORM_ORIGIN,
            lever_arm_b=np.zeros(3, dtype=np.float64),
            boresight_deg=(0.0, 0.0, 0.0)
        ))
        mesh = VehicleMesh.create_box_vehicle(length_m=2.0, width_m=1.0, height_m=0.5)

        new_proj = Project(
            name=name,
            description="Proyecto de Georeferenciacion y Navegacion Multi-Sensor",
            ellipsoid_name=ell,
            platform=plat,
            asset=mesh,
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

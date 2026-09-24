"""
PyGSN - Georeferencing & Navigation Panel (DearPyGui)
====================================================
Panel interactivo para georreferenciacion multi-sensor:
- Entrada y edicion de observaciones GNSS e INS de campo.
- Parametros geodesicos locales (elipsoide, ondulacion geoidal, declinacion).
- Ejecucion del pipeline de transformacion y actitud (Kabsch SVD + encadenamiento DCM).
- Visor y exportador de informes tecnicos paso a paso.
"""

from pathlib import Path
import dearpygui.dearpygui as dpg
import numpy as np

from core.models import Platform
from core.geodesy import GRS80, WGS84, dms_to_rad, rad_to_dms
from core.georeferencing import solve_multisensor_georeferencing, GeoreferencingSolution
from core.reporting import generate_georeferencing_report


class GeoreferencingPanel:
    """Controlador de la interfaz de usuario para georreferenciacion multi-sensor."""

    def __init__(self, platform: Platform):
        self.platform = platform
        self.current_solution: GeoreferencingSolution | None = None
        self.last_report_text: str = ""

    def build_ui(self, parent_tag: str):
        with dpg.group(parent=parent_tag):
            dpg.add_text("Georreferenciación Multi-Sensor y Transformación", color=(0, 180, 216, 255))
            dpg.add_text("Estimación de actitud GNSS/INS y propagación cinemática", color=(140, 150, 165, 255))
            dpg.add_separator()

            with dpg.collapsing_header(label="1. Observaciones GNSS de Campo (ETRS89 / GRS80)", default_open=True):
                dpg.add_text("Coordenadas Geodésicas de las Antenas GNSS (Deg Min Sec):")
                # REC2
                with dpg.group(horizontal=True):
                    dpg.add_text("REC2: ", color=(255, 209, 102, 255))
                    dpg.add_input_text(default_value="39 28 53.133637", width=130, tag="geo_rec2_lat", label="Lat")
                    dpg.add_input_text(default_value="-0 20 7.650964", width=130, tag="geo_rec2_lon", label="Lon")
                    dpg.add_drag_float(default_value=55.8670, speed=0.001, width=75, tag="geo_rec2_h", label="h(m)")
                # REC3
                with dpg.group(horizontal=True):
                    dpg.add_text("REC3: ", color=(255, 209, 102, 255))
                    dpg.add_input_text(default_value="39 28 53.109885", width=130, tag="geo_rec3_lat", label="Lat")
                    dpg.add_input_text(default_value="-0 20 7.663129", width=130, tag="geo_rec3_lon", label="Lon")
                    dpg.add_drag_float(default_value=55.8290, speed=0.001, width=75, tag="geo_rec3_h", label="h(m)")
                # REC4
                with dpg.group(horizontal=True):
                    dpg.add_text("REC4: ", color=(255, 209, 102, 255))
                    dpg.add_input_text(default_value="39 28 53.143535", width=130, tag="geo_rec4_lat", label="Lat")
                    dpg.add_input_text(default_value="-0 20 7.680928", width=130, tag="geo_rec4_lon", label="Lon")
                    dpg.add_drag_float(default_value=55.8830, speed=0.001, width=75, tag="geo_rec4_h", label="h(m)")
                # REC5
                with dpg.group(horizontal=True):
                    dpg.add_text("REC5: ", color=(255, 209, 102, 255))
                    dpg.add_input_text(default_value="39 28 53.119474", width=130, tag="geo_rec5_lat", label="Lat")
                    dpg.add_input_text(default_value="-0 20 7.693816", width=130, tag="geo_rec5_lon", label="Lon")
                    dpg.add_drag_float(default_value=55.8660, speed=0.001, width=75, tag="geo_rec5_h", label="h(m)")

            with dpg.collapsing_header(label="2. Observaciones INS y Parámetros Geodésicos", default_open=True):
                with dpg.group(horizontal=True):
                    dpg.add_drag_float(label="Roll (º)", default_value=1.195278, speed=0.001, width=80, tag="geo_ins_roll")
                    dpg.add_drag_float(label="Pitch (º)", default_value=-1.189671, speed=0.001, width=80, tag="geo_ins_pitch")
                    dpg.add_drag_float(label="Yaw (º)", default_value=111.269874, speed=0.001, width=80, tag="geo_ins_yaw")
                with dpg.group(horizontal=True):
                    dpg.add_drag_float(label="Declinación δ (º)", default_value=-0.700, speed=0.01, width=80, tag="geo_decl")
                    dpg.add_drag_float(label="Geoide N (m)", default_value=50.0166, speed=0.001, width=80, tag="geo_geoide_n")

            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_input_text(label="Ruta Salida", default_value="output/Informe_Georreferenciacion.txt",
                                   width=260, tag="geo_output_path")
            with dpg.group(horizontal=True):
                dpg.add_button(label="CALCULAR GEORREFERENCIACION", callback=self._cb_solve,
                               width=210, height=28)
                dpg.add_button(label="EXPORTAR INFORME TXT", callback=self._cb_export_txt,
                               width=180, height=28)

            dpg.add_spacer(height=5)
            dpg.add_text("Estado: Listo para procesar", tag="geo_status_text", color=(6, 214, 160, 255))

            dpg.add_spacer(height=5)
            with dpg.collapsing_header(label="Resumen de Resultados", default_open=True):
                with dpg.group(horizontal=True):
                    dpg.add_text("Actitud Estimada (GNSS):")
                    dpg.add_text("-", tag="geo_res_att_gnss", color=(255, 209, 102, 255))
                with dpg.group(horizontal=True):
                    dpg.add_text("Origen Plataforma (PLA):")
                    dpg.add_text("-", tag="geo_res_pla_geo", color=(255, 209, 102, 255))
                with dpg.group(horizontal=True):
                    dpg.add_text("Actitud Total (INS + Boresight):")
                    dpg.add_text("-", tag="geo_res_att_ins", color=(6, 214, 160, 255))

            dpg.add_spacer(height=5)
            dpg.add_text("Visor de Informe Técnico:")
            with dpg.child_window(height=180, border=True):
                dpg.add_input_text(default_value="", multiline=True, readonly=True,
                                   width=-1, height=-1, tag="geo_report_viewer")

    def _parse_dms_string(self, s: str) -> np.float64:
        parts = s.strip().split()
        if len(parts) >= 3:
            deg = float(parts[0])
            m = float(parts[1])
            sec = float(parts[2])
            sign = -1 if deg < 0 or s.strip().startswith("-") else 1
            return dms_to_rad(abs(deg), m, sec, sign)
        return np.radians(float(parts[0]))

    def _cb_solve(self):
        try:
            gnss_obs = {
                "REC2": (self._parse_dms_string(dpg.get_value("geo_rec2_lat")),
                         self._parse_dms_string(dpg.get_value("geo_rec2_lon")),
                         np.float64(dpg.get_value("geo_rec2_h"))),
                "REC3": (self._parse_dms_string(dpg.get_value("geo_rec3_lat")),
                         self._parse_dms_string(dpg.get_value("geo_rec3_lon")),
                         np.float64(dpg.get_value("geo_rec3_h"))),
                "REC4": (self._parse_dms_string(dpg.get_value("geo_rec4_lat")),
                         self._parse_dms_string(dpg.get_value("geo_rec4_lon")),
                         np.float64(dpg.get_value("geo_rec4_h"))),
                "REC5": (self._parse_dms_string(dpg.get_value("geo_rec5_lat")),
                         self._parse_dms_string(dpg.get_value("geo_rec5_lon")),
                         np.float64(dpg.get_value("geo_rec5_h"))),
            }

            ins_att = (
                float(dpg.get_value("geo_ins_roll")),
                float(dpg.get_value("geo_ins_pitch")),
                float(dpg.get_value("geo_ins_yaw"))
            )
            decl = float(dpg.get_value("geo_decl"))
            geoide_n = float(dpg.get_value("geo_geoide_n"))

            sol = solve_multisensor_georeferencing(
                platform=self.platform,
                gnss_observations=gnss_obs,
                ins_attitude_deg=ins_att,
                magnetic_declination_deg=decl,
                geoid_undulation_N=geoide_n,
                ellipsoid=GRS80
            )
            self.current_solution = sol

            rg, pg, yg = sol.attitude_gnss_deg
            dpg.set_value("geo_res_att_gnss", f"Roll={rg:.6f}º, Pitch={pg:.6f}º, Yaw={yg:.6f}º")

            _, _, _, lat_str = rad_to_dms(sol.pla_origin_lat_rad)
            _, _, _, lon_str = rad_to_dms(sol.pla_origin_lon_rad)
            dpg.set_value("geo_res_pla_geo", f"Lat={lat_str}, Lon={lon_str}, h={sol.pla_origin_h_ellip:.4f}m")

            ri, pi, yi = sol.attitude_ins_total_deg
            dpg.set_value("geo_res_att_ins", f"Roll={ri:.6f}º, Pitch={pi:.6f}º, Yaw={yi:.6f}º")

            self.last_report_text = generate_georeferencing_report(sol)
            dpg.set_value("geo_report_viewer", self.last_report_text)
            dpg.set_value("geo_status_text", "[OK] Georreferenciacion calculada con exito")

        except Exception as e:
            dpg.set_value("geo_status_text", f"Error en calculo: {str(e)}")

    def _cb_export_txt(self):
        if not self.last_report_text:
            self._cb_solve()

        if self.last_report_text:
            out_str = dpg.get_value("geo_output_path").strip() or "output/Informe_Georreferenciacion.txt"
            out_path = Path(out_str)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(self.last_report_text, encoding="utf-8")
            dpg.set_value("geo_status_text", f"[OK] Fichero exportado en: {out_path.name}")


# Alias de compatibilidad
Practica1Panel = GeoreferencingPanel

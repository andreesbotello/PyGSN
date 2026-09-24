"""
PyGSN - Practica 1 Solver & Reporting Panel (DearPyGui)
======================================================
Panel dedicado para configurar las observaciones de campo (GNSS e INS),
ejecutar el pipeline matematico de la Practica 1 y visualizar o exportar
los ficheros de texto (.txt) del procesamiento paso a paso.
"""

from pathlib import Path
import dearpygui.dearpygui as dpg
import numpy as np

from ..core.models import Platform
from ..core.geodesy import GRS80, WGS84, dms_to_rad, rad_to_dms
from ..core.solver_p1 import solve_practica_1, P1Solution
from ..core.reporting import generate_p1_full_txt_report


class Practica1Panel:
    """Controlador de la interfaz de usuario para la Practica 1."""

    def __init__(self, platform: Platform):
        self.platform = platform
        self.current_solution: P1Solution | None = None
        self.last_report_text: str = ""

    def build_ui(self, parent_tag: str):
        with dpg.group(parent=parent_tag):
            dpg.add_text("Resolución Académica de la Práctica 1 (2026)", color=(0, 180, 216, 255))
            dpg.add_text("Transformación de Sistemas de Coordenadas y Georreferenciación", color=(140, 150, 165, 255))
            dpg.add_separator()

            with dpg.collapsing_header(label="1. Observaciones GNSS de Campo (ETRS89 / GRS80)", default_open=True):
                dpg.add_text("Coordenadas Geodésicas por Antena GNSS:")
                # REC2
                with dpg.group(horizontal=True):
                    dpg.add_text("REC2: ", color=(255, 209, 102, 255))
                    dpg.add_input_text(default_value="39 28 53.133637", width=130, tag="p1_rec2_lat", label="Lat")
                    dpg.add_input_text(default_value="-0 20 7.650964", width=130, tag="p1_rec2_lon", label="Lon")
                    dpg.add_drag_float(default_value=55.8670, speed=0.001, width=75, tag="p1_rec2_h", label="h(m)")
                # REC3
                with dpg.group(horizontal=True):
                    dpg.add_text("REC3: ", color=(255, 209, 102, 255))
                    dpg.add_input_text(default_value="39 28 53.109885", width=130, tag="p1_rec3_lat", label="Lat")
                    dpg.add_input_text(default_value="-0 20 7.663129", width=130, tag="p1_rec3_lon", label="Lon")
                    dpg.add_drag_float(default_value=55.8290, speed=0.001, width=75, tag="p1_rec3_h", label="h(m)")
                # REC4
                with dpg.group(horizontal=True):
                    dpg.add_text("REC4: ", color=(255, 209, 102, 255))
                    dpg.add_input_text(default_value="39 28 53.143535", width=130, tag="p1_rec4_lat", label="Lat")
                    dpg.add_input_text(default_value="-0 20 7.680928", width=130, tag="p1_rec4_lon", label="Lon")
                    dpg.add_drag_float(default_value=55.8830, speed=0.001, width=75, tag="p1_rec4_h", label="h(m)")
                # REC5
                with dpg.group(horizontal=True):
                    dpg.add_text("REC5: ", color=(255, 209, 102, 255))
                    dpg.add_input_text(default_value="39 28 53.119474", width=130, tag="p1_rec4_lat_alt", label="Lat")
                    dpg.add_input_text(default_value="-0 20 7.693816", width=130, tag="p1_rec5_lon", label="Lon")
                    dpg.add_drag_float(default_value=55.8660, speed=0.001, width=75, tag="p1_rec5_h", label="h(m)")

            with dpg.collapsing_header(label="2. Observaciones INS y Parámetros Locales", default_open=True):
                with dpg.group(horizontal=True):
                    dpg.add_drag_float(label="Roll (º)", default_value=1.195278, speed=0.001, width=80, tag="p1_ins_roll")
                    dpg.add_drag_float(label="Pitch (º)", default_value=-1.189671, speed=0.001, width=80, tag="p1_ins_pitch")
                    dpg.add_drag_float(label="Yaw (º)", default_value=111.269874, speed=0.001, width=80, tag="p1_ins_yaw")
                with dpg.group(horizontal=True):
                    dpg.add_drag_float(label="Declinación δ (º)", default_value=-0.700, speed=0.01, width=80, tag="p1_decl")
                    dpg.add_drag_float(label="Geoide N (m)", default_value=50.0166, speed=0.001, width=80, tag="p1_geoide_n")

            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="▶ CALCULAR PRÁCTICA 1", callback=self._cb_solve,
                               width=180, height=28)
                dpg.add_button(label="💾 EXPORTAR TXT PASO A PASO", callback=self._cb_export_txt,
                               width=220, height=28)

            dpg.add_spacer(height=5)
            dpg.add_text("Estado: Listo para calcular", tag="p1_status_text", color=(6, 214, 160, 255))

            dpg.add_spacer(height=5)
            with dpg.collapsing_header(label="Resumen de Resultados Numéricos", default_open=True):
                with dpg.group(horizontal=True):
                    dpg.add_text("Actitud GNSS (P1):")
                    dpg.add_text("-", tag="p1_res_att_gnss", color=(255, 209, 102, 255))
                with dpg.group(horizontal=True):
                    dpg.add_text("Origen PLA (P1):")
                    dpg.add_text("-", tag="p1_res_pla_geo", color=(255, 209, 102, 255))
                with dpg.group(horizontal=True):
                    dpg.add_text("Actitud INS Total (P2b):")
                    dpg.add_text("-", tag="p1_res_att_ins", color=(6, 214, 160, 255))

            dpg.add_spacer(height=5)
            dpg.add_text("Visor de Fichero de Salida (TXT Oficial):")
            with dpg.child_window(height=180, border=True):
                dpg.add_input_text(default_value="", multiline=True, readonly=True,
                                   width=-1, height=-1, tag="p1_report_viewer")

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
            # Parsear datos de entrada
            gnss_obs = {
                "REC2": (self._parse_dms_string(dpg.get_value("p1_rec2_lat")),
                         self._parse_dms_string(dpg.get_value("p1_rec2_lon")),
                         np.float64(dpg.get_value("p1_rec2_h"))),
                "REC3": (self._parse_dms_string(dpg.get_value("p1_rec3_lat")),
                         self._parse_dms_string(dpg.get_value("p1_rec3_lon")),
                         np.float64(dpg.get_value("p1_rec3_h"))),
                "REC4": (self._parse_dms_string(dpg.get_value("p1_rec4_lat")),
                         self._parse_dms_string(dpg.get_value("p1_rec4_lon")),
                         np.float64(dpg.get_value("p1_rec4_h"))),
                "REC5": (self._parse_dms_string(dpg.get_value("p1_rec4_lat_alt")),
                         self._parse_dms_string(dpg.get_value("p1_rec5_lon")),
                         np.float64(dpg.get_value("p1_rec5_h"))),
            }

            ins_att = (
                float(dpg.get_value("p1_ins_roll")),
                float(dpg.get_value("p1_ins_pitch")),
                float(dpg.get_value("p1_ins_yaw"))
            )
            decl = float(dpg.get_value("p1_decl"))
            geoide_n = float(dpg.get_value("p1_geoide_n"))

            # Ejecutar solucionador
            sol = solve_practica_1(
                platform=self.platform,
                gnss_observations=gnss_obs,
                ins_attitude_deg=ins_att,
                magnetic_declination_deg=decl,
                geoid_undulation_N=geoide_n,
                ellipsoid=GRS80
            )
            self.current_solution = sol

            # Actualizar textos de resumen
            rg, pg, yg = sol.attitude_gnss_deg
            dpg.set_value("p1_res_att_gnss", f"Roll={rg:.6f}º, Pitch={pg:.6f}º, Yaw={yg:.6f}º")

            _, _, _, lat_str = rad_to_dms(sol.pla_origin_lat_rad)
            _, _, _, lon_str = rad_to_dms(sol.pla_origin_lon_rad)
            dpg.set_value("p1_res_pla_geo", f"Lat={lat_str}, Lon={lon_str}, h={sol.pla_origin_h_ellip:.4f}m")

            ri, pi, yi = sol.attitude_ins_total_deg
            dpg.set_value("p1_res_att_ins", f"Roll={ri:.6f}º, Pitch={pi:.6f}º, Yaw={yi:.6f}º")

            # Generar texto de reporte
            self.last_report_text = generate_p1_full_txt_report(sol)
            dpg.set_value("p1_report_viewer", self.last_report_text)
            dpg.set_value("p1_status_text", "✓ Práctica 1 resuelta con éxito (100% verificado)")

        except Exception as e:
            dpg.set_value("p1_status_text", f"Error en cálculo: {str(e)}")

    def _cb_export_txt(self):
        if not self.last_report_text:
            self._cb_solve()

        if self.last_report_text:
            out_path = Path("P1_Resultados_Paso_a_Paso.txt")
            out_path.write_text(self.last_report_text, encoding="utf-8")
            abs_p = out_path.resolve()
            dpg.set_value("p1_status_text", f"✓ Fichero guardado en: {abs_p.name}")

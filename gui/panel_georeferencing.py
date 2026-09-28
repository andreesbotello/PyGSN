"""
PyGSN - General Georeferencing & Navigation Solver Panel
========================================================
Panel interactivo universal para georreferenciación y actitud multi-sensor:
- Tabla dinámica de observaciones GNSS (agrega, edita o elimina cualquier número de antenas).
- Soporte para cualquier rig de sensores (vehículos terrestres, drones UAV, embarcaciones, bancos de prueba).
- Carga de observaciones desde archivo (.txt / .csv) o entrada manual celda por celda.
- Resolución rigurosa por Procrustes Ortogonal (Kabsch SVD) y propagación a todos los sensores del rig.
- Cero valores fijos o cableados: comportamiento generalista de grado industrial.
"""

from pathlib import Path
from typing import Callable, Any
import dearpygui.dearpygui as dpg
import numpy as np

from core.models import Platform, SensorType
from core.geodesy import GRS80, WGS84, dms_to_rad, rad_to_dms
from core.georeferencing import solve_multisensor_georeferencing, GeoreferencingSolution
from core.reporting import generate_georeferencing_report


class GeoreferencingPanel:
    """Controlador universal de observación y cálculo de georreferenciación."""

    def __init__(self, platform: Platform, on_solution_computed: Callable[[GeoreferencingSolution, str], None] | None = None):
        self.platform = platform
        self.on_solution_computed = on_solution_computed
        self.current_solution: GeoreferencingSolution | None = None
        self.last_report_text: str = ""

        # Lista dinámica de observaciones GNSS:
        # Cada elemento: dict(id=int, code=str, lat_str=str, lon_str=str, h=float)
        self.gnss_obs_list: list[dict[str, Any]] = []
        self._next_obs_id = 1

    def add_gnss_observation(self, code: str | None = None, lat_str: str = "00 00 00.000", lon_str: str = "00 00 00.000", h: float = 0.0):
        """Agrega una observación GNSS a la lista dinámica."""
        if code is None:
            existing_codes = {o["code"] for o in self.gnss_obs_list}
            avail = [c for c, s in self.platform.sensors.items() if s.sensor_type == SensorType.GNSS and c not in existing_codes]
            code = avail[0] if avail else f"GNSS_{self._next_obs_id}"

        obs = {
            "id": self._next_obs_id,
            "code": code,
            "lat_str": lat_str,
            "lon_str": lon_str,
            "h": float(h)
        }
        self._next_obs_id += 1
        self.gnss_obs_list.append(obs)
        self.rebuild_gnss_obs_table()

    def remove_gnss_observation(self, obs_id: int):
        """Elimina una observación GNSS por su ID."""
        self.gnss_obs_list = [o for o in self.gnss_obs_list if o["id"] != obs_id]
        self.rebuild_gnss_obs_table()

    def clear_gnss_observations(self):
        """Limpia todas las observaciones."""
        self.gnss_obs_list.clear()
        self.rebuild_gnss_obs_table()

    def build_ui(self, parent_tag: str):
        with dpg.group(parent=parent_tag):
            # Barra superior de la pestaña
            with dpg.group(horizontal=True):
                dpg.add_text("Solver de Georreferenciación y Actitud Multi-Sensor", color=(0, 180, 216, 255))
                dpg.add_spacer(width=20)
                dpg.add_button(label="+ Añadir Observación GNSS", callback=lambda: self.add_gnss_observation())
                dpg.add_button(label="Importar Observaciones (.txt)", callback=self._cb_open_file_dialog)
                dpg.add_button(label="Limpiar Todo", callback=self.clear_gnss_observations)
                dpg.add_spacer(width=15)
                dpg.add_text("Estado: Listo", tag="geo_solver_status", color=(6, 214, 160, 255))

            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Distribución en 2 columnas principales amplias
            with dpg.group(horizontal=True):
                # COLUMNA IZQUIERDA: Observaciones de Entrada (~540 px)
                with dpg.child_window(width=540, height=-1, border=True):
                    dpg.add_text("1. Observaciones de Antenas GNSS (Tabla Dinámica):", color=(255, 209, 102, 255))
                    dpg.add_text("Cada fila relaciona un sensor del rig con su posición observada (DMS o deg y h elipsoidal)",
                                 color=(140, 150, 165, 255))
                    dpg.add_spacer(height=3)

                    # Contenedor con scroll para la tabla dinámica de GNSS
                    with dpg.child_window(height=260, border=True, tag="child_gnss_obs_container"):
                        self.rebuild_gnss_obs_table()

                    dpg.add_spacer(height=8)
                    dpg.add_text("2. Observación de Sensor Inercial (INS/IMU) / Actitud Auxiliar:", color=(255, 209, 102, 255))
                    with dpg.group(horizontal=True):
                        dpg.add_checkbox(label="Incluir INS en el cálculo", default_value=False, tag="geo_include_ins")
                        dpg.add_spacer(width=10)
                        dpg.add_text("Sensor INS del Rig:")
                        # Encontrar código INS por defecto si existe en la plataforma
                        ins_default = "INS"
                        for s in self.platform.sensors.values():
                            if s.sensor_type == SensorType.INS:
                                ins_default = s.code
                                break
                        dpg.add_input_text(default_value=ins_default, width=80, tag="geo_ins_code_input")

                    with dpg.group(horizontal=True):
                        dpg.add_drag_float(label="Roll (º)", default_value=0.0, speed=0.001, width=80, tag="geo_ins_roll")
                        dpg.add_drag_float(label="Pitch (º)", default_value=0.0, speed=0.001, width=80, tag="geo_ins_pitch")
                        dpg.add_drag_float(label="Yaw (º)", default_value=0.0, speed=0.001, width=80, tag="geo_ins_yaw")

                    dpg.add_spacer(height=5)
                    dpg.add_text("3. Parámetros Geodésicos y Corrección Local:", color=(255, 209, 102, 255))
                    with dpg.group(horizontal=True):
                        dpg.add_drag_float(label="Declinación Mag. δ (º)", default_value=0.000, speed=0.01, width=95, tag="geo_decl")
                        dpg.add_drag_float(label="Ondulación Geoide N (m)", default_value=0.000, speed=0.001, width=95, tag="geo_geoide_n")

                    dpg.add_spacer(height=12)
                    dpg.add_separator()
                    dpg.add_spacer(height=4)
                    dpg.add_button(
                        label="RESOLVER GEORREFERENCIACION Y ACTITUD (SVD KABSCH)",
                        callback=self._cb_solve,
                        width=-1,
                        height=36
                    )

                # COLUMNA DERECHA: Resultados del Cálculo (ancho restante)
                with dpg.child_window(width=-1, height=-1, border=True):
                    dpg.add_text("Resultados del Procesamiento Numérico:", color=(0, 180, 216, 255))
                    dpg.add_separator()
                    dpg.add_spacer(height=5)

                    # Tarjeta 1: Actitud estimada por GNSS
                    with dpg.child_window(height=80, border=True):
                        dpg.add_text("1. Actitud de la Plataforma (C_b^n por SVD de Kabsch):", color=(255, 209, 102, 255))
                        dpg.add_text("Roll:   -", tag="res_gnss_roll", color=(255, 255, 255, 255))
                        dpg.add_text("Pitch:  -", tag="res_gnss_pitch", color=(255, 255, 255, 255))
                        dpg.add_text("Yaw:    -", tag="res_gnss_yaw", color=(255, 255, 255, 255))

                    dpg.add_spacer(height=5)
                    # Tarjeta 2: Origen de la plataforma PLA
                    with dpg.child_window(height=85, border=True):
                        dpg.add_text("2. Origen del Vehículo / Plataforma (PLA):", color=(255, 209, 102, 255))
                        dpg.add_text("Geodésicas: Lat: -, Lon: -, h: -", tag="res_pla_geo", color=(255, 255, 255, 255))
                        dpg.add_text("Cartesianas ECEF: X: -, Y: -, Z: -", tag="res_pla_ecef", color=(140, 150, 165, 255))
                        dpg.add_text("UTM: Easting: -, Northing: -, H.orto: -", tag="res_pla_utm", color=(6, 214, 160, 255))

                    dpg.add_spacer(height=5)
                    # Tarjeta 3: Comparativa INS y residuales
                    with dpg.child_window(height=75, border=True):
                        dpg.add_text("3. Orientación Inercial INS (Boresight C_s^b + Declinación δ):", color=(6, 214, 160, 255))
                        dpg.add_text("Actitud INS Total: -", tag="res_ins_attitude")
                        dpg.add_text("Diferencia (GNSS - INS): -", tag="res_diff_attitude", color=(255, 209, 102, 255))

                    dpg.add_spacer(height=5)
                    # Tarjeta 4: Tabla de sensores propagados
                    dpg.add_text("Tabla de Sensores Propagados (Coordenadas en n-frame, e-frame y UTM):", color=(0, 180, 216, 255))
                    with dpg.child_window(height=-1, border=True, tag="child_sensors_table"):
                        dpg.add_text("Ejecute el cálculo para visualizar las coordenadas propagadas de todos los sensores del rig.",
                                     color=(140, 150, 165, 255))

    def rebuild_gnss_obs_table(self):
        """Reconstruye dinámicamente las filas de observaciones GNSS."""
        if not dpg.does_item_exist("child_gnss_obs_container"):
            return
        dpg.delete_item("child_gnss_obs_container", children_only=True)

        if not self.gnss_obs_list:
            dpg.add_text("No hay observaciones GNSS cargadas.", color=(140, 150, 165, 255), parent="child_gnss_obs_container")
            dpg.add_text("Haga clic en '+ Añadir Observación GNSS' para ingresar datos o use 'Importar Observaciones'.",
                         color=(140, 150, 165, 255), parent="child_gnss_obs_container")
            return

        with dpg.table(header_row=True, parent="child_gnss_obs_container",
                       borders_innerH=True, borders_outerH=True, borders_innerV=True, borders_outerV=True):
            dpg.add_table_column(label="Sensor", width_fixed=True, init_width_or_weight=70)
            dpg.add_table_column(label="Latitud (D M S o deg)", width_fixed=True, init_width_or_weight=135)
            dpg.add_table_column(label="Longitud (D M S o deg)", width_fixed=True, init_width_or_weight=135)
            dpg.add_table_column(label="h elip (m)", width_fixed=True, init_width_or_weight=75)
            dpg.add_table_column(label="Acción", width_fixed=True, init_width_or_weight=50)

            for obs in self.gnss_obs_list:
                oid = obs["id"]
                with dpg.table_row():
                    dpg.add_input_text(default_value=obs["code"], width=65, tag=f"obs_code_{oid}",
                                       callback=lambda s, a, o=obs: o.update({"code": a.strip().upper()}))
                    dpg.add_input_text(default_value=obs["lat_str"], width=130, tag=f"obs_lat_{oid}",
                                       callback=lambda s, a, o=obs: o.update({"lat_str": a.strip()}))
                    dpg.add_input_text(default_value=obs["lon_str"], width=130, tag=f"obs_lon_{oid}",
                                       callback=lambda s, a, o=obs: o.update({"lon_str": a.strip()}))
                    dpg.add_drag_float(default_value=obs["h"], speed=0.001, width=70, tag=f"obs_h_{oid}",
                                       callback=lambda s, a, o=obs: o.update({"h": float(a)}))
                    dpg.add_button(label="X", small=True, user_data=oid, callback=lambda s, a, u: self.remove_gnss_observation(u))

    def _cb_open_file_dialog(self):
        """Carga observaciones desde un fichero seleccionado mediante el explorador nativo."""
        from gui.modals import pick_open_file_native
        selected = pick_open_file_native(
            title="Importar Observaciones GNSS/INS",
            filetypes=(
                ("Archivos de Texto (*.txt;*.csv;*.dat)", "*.txt;*.csv;*.dat"),
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
            self._load_from_txt_content(p.read_text(encoding="utf-8"))
            dpg.set_value("geo_solver_status", f"[OK] Observaciones cargadas desde: {p.name}")
        except Exception as e:
            dpg.set_value("geo_solver_status", f"Error al cargar observaciones: {str(e)[:40]}")

    def _load_from_txt_content(self, content: str):
        """Parsea cualquier texto de observaciones e inserta las filas en la tabla dinámica."""
        self.gnss_obs_list.clear()
        from core.operators.georeferencing_operator import parse_observations_content
        data = parse_observations_content(content)

        gnss = data.get("gnss_observations", {})
        for code, (lat_rad, lon_rad, h) in gnss.items():
            _, _, _, lat_str = rad_to_dms(lat_rad)
            _, _, _, lon_str = rad_to_dms(lon_rad)
            lat_clean = lat_str.replace("º", " ").replace("'", " ").replace('"', '').strip()
            lon_clean = lon_str.replace("º", " ").replace("'", " ").replace('"', '').strip()
            self.gnss_obs_list.append({
                "id": self._next_obs_id,
                "code": code,
                "lat_str": lat_clean,
                "lon_str": lon_clean,
                "h": float(h)
            })
            self._next_obs_id += 1

        self.rebuild_gnss_obs_table()

        ins = data.get("ins_attitude_deg", (0.0, 0.0, 0.0))
        if dpg.does_item_exist("geo_ins_roll"):
            dpg.set_value("geo_ins_roll", ins[0])
            dpg.set_value("geo_ins_pitch", ins[1])
            dpg.set_value("geo_ins_yaw", ins[2])
            dpg.set_value("geo_include_ins", True)

        if dpg.does_item_exist("geo_decl"):
            dpg.set_value("geo_decl", data.get("magnetic_declination_deg", 0.0))
        if dpg.does_item_exist("geo_geoide_n"):
            dpg.set_value("geo_geoide_n", data.get("geoid_undulation_N", 0.0))

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
        """Ejecuta la resolución de georreferenciación con los sensores dinámicos."""
        try:
            if len(self.gnss_obs_list) < 3:
                dpg.set_value("geo_solver_status", f"Error: Se requieren al menos 3 observaciones GNSS (disponibles: {len(self.gnss_obs_list)})")
                return

            gnss_obs = {}
            for obs in self.gnss_obs_list:
                code = obs["code"].strip().upper()
                if code not in self.platform.sensors:
                    dpg.set_value(
                        "geo_solver_status",
                        f"Error: El sensor '{code}' no está instalado en la plataforma. Añádalo al chasis primero."
                    )
                    return
                lat_rad = self._parse_dms_string(obs["lat_str"])
                lon_rad = self._parse_dms_string(obs["lon_str"])
                gnss_obs[code] = (lat_rad, lon_rad, np.float64(obs["h"]))

            include_ins = dpg.get_value("geo_include_ins") if dpg.does_item_exist("geo_include_ins") else False
            if include_ins:
                ins_att = (
                    float(dpg.get_value("geo_ins_roll")),
                    float(dpg.get_value("geo_ins_pitch")),
                    float(dpg.get_value("geo_ins_yaw"))
                )
                ins_code = dpg.get_value("geo_ins_code_input").strip().upper() if dpg.does_item_exist("geo_ins_code_input") else "INS"
            else:
                ins_att = (0.0, 0.0, 0.0)
                ins_code = None

            decl = float(dpg.get_value("geo_decl")) if dpg.does_item_exist("geo_decl") else 0.0
            geoide_n = float(dpg.get_value("geo_geoide_n")) if dpg.does_item_exist("geo_geoide_n") else 0.0

            sol = solve_multisensor_georeferencing(
                platform=self.platform,
                gnss_observations=gnss_obs,
                ins_attitude_deg=ins_att,
                magnetic_declination_deg=decl,
                geoid_undulation_N=geoide_n,
                ellipsoid=GRS80,
                ins_sensor_code=ins_code
            )
            self.current_solution = sol

            # 1. Actualizar Tarjeta GNSS
            rg, pg, yg = sol.attitude_gnss_deg
            dpg.set_value("res_gnss_roll",  f"Roll  (Phi):    {rg:+10.6f} deg")
            dpg.set_value("res_gnss_pitch", f"Pitch (Theta):  {pg:+10.6f} deg")
            dpg.set_value("res_gnss_yaw",   f"Yaw   (Psi):    {yg:10.6f} deg")

            # 2. Actualizar Tarjeta PLA
            _, _, _, lat_str = rad_to_dms(sol.pla_origin_lat_rad)
            _, _, _, lon_str = rad_to_dms(sol.pla_origin_lon_rad)
            dpg.set_value("res_pla_geo", f"Geodésicas:  Lat: {lat_str}  |  Lon: {lon_str}  |  h: {sol.pla_origin_h_ellip:.4f} m")

            xp, yp, zp = sol.pla_origin_ecef
            dpg.set_value("res_pla_ecef", f"ECEF (m):     X: {xp:12.4f}  |  Y: {yp:12.4f}  |  Z: {zp:12.4f}")

            if "PLA" in sol.results_gnss:
                pla_res = sol.results_gnss["PLA"]
                dpg.set_value("res_pla_utm", f"UTM:  Easting: {pla_res.easting:10.4f} m  |  Northing: {pla_res.northing:10.4f} m  |  H.orto: {pla_res.h_orto:.4f} m")

            # 3. Actualizar Tarjeta INS
            if include_ins:
                ri, pi, yi = sol.attitude_ins_total_deg
                dpg.set_value("res_ins_attitude", f"Actitud INS Total:  Roll: {ri:+.6f}º  |  Pitch: {pi:+.6f}º  |  Yaw: {yi:.6f}º")
                dr, dp, dy = rg - ri, pg - pi, yg - yi
                dpg.set_value("res_diff_attitude", f"Diferencia (GNSS - INS):  dRoll: {dr:+.6f}º  |  dPitch: {dp:+.6f}º  |  dYaw: {dy:+.6f}º")
            else:
                dpg.set_value("res_ins_attitude", "Observación INS deshabilitada para este cálculo.")
                dpg.set_value("res_diff_attitude", "N/A")

            # 4. Actualizar Tabla de Sensores
            self._update_sensors_table(sol)

            # Generar informe técnico
            self.last_report_text = generate_georeferencing_report(sol)
            dpg.set_value("geo_solver_status", f"[OK] Actitud resuelta con éxito ({len(gnss_obs)} antenas GNSS)")

            if self.on_solution_computed:
                self.on_solution_computed(sol, self.last_report_text)

        except Exception as e:
            dpg.set_value("geo_solver_status", f"Error en cálculo: {str(e)[:50]}")

    def _update_sensors_table(self, sol: GeoreferencingSolution):
        """Dibuja la tabla de coordenadas de todos los sensores propagados."""
        if not dpg.does_item_exist("child_sensors_table"):
            return
        dpg.delete_item("child_sensors_table", children_only=True)

        with dpg.table(header_row=True, parent="child_sensors_table",
                       borders_innerH=True, borders_outerH=True, borders_innerV=True, borders_outerV=True):
            dpg.add_table_column(label="Sensor")
            dpg.add_table_column(label="Easting (m)")
            dpg.add_table_column(label="Northing (m)")
            dpg.add_table_column(label="H.orto (m)")
            dpg.add_table_column(label="Latitud")
            dpg.add_table_column(label="Longitud")

            for code, res in sol.results_gnss.items():
                _, _, _, lat_s = rad_to_dms(res.lat_rad)
                _, _, _, lon_s = rad_to_dms(res.lon_rad)
                sens = self.platform.get_sensor(code)
                is_gnss = (sens and sens.sensor_type == SensorType.GNSS) or "GNSS" in code or "REC" in code
                with dpg.table_row():
                    dpg.add_text(f"[{code}]", color=(255, 209, 102, 255) if is_gnss else (0, 180, 216, 255))
                    dpg.add_text(f"{res.easting:10.4f}")
                    dpg.add_text(f"{res.northing:10.4f}")
                    dpg.add_text(f"{res.h_orto:8.4f}", color=(6, 214, 160, 255))
                    dpg.add_text(lat_s)
                    dpg.add_text(lon_s)

    def _cb_export_txt(self):
        """Exporta el informe a fichero TXT."""
        if not self.last_report_text:
            dpg.set_value("geo_solver_status", "Aviso: Primero debe resolver la georreferenciación")
            return

        p = Path("output/Informe_Georreferenciacion.txt")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.last_report_text, encoding="utf-8")
        dpg.set_value("geo_solver_status", f"[OK] Fichero exportado en: {p.name}")

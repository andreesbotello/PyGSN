"""
PyGSN - Kinematics & Trajectory Simulation Panel
================================================
Panel para la simulacion e integracion cinematica de trayectorias desde el b-frame:
- Entrada de comandos en b-frame (velocidad de avance, actitud roll/pitch/yaw).
- Integracion elipsoidal b-frame -> n-frame (NED) -> e-frame (ECEF).
- Grafica 2D interactiva acelerada por GPU del recorrido en navegacion local (Norte vs Este).
"""

from typing import Callable
import dearpygui.dearpygui as dpg
import numpy as np

from core.project import Project
from core.operators import TrajectoryKinematicsOperator


class KinematicsPanel:
    """Panel de simulacion de trayectorias y navegacion b-frame -> n-frame -> e-frame."""

    def __init__(self, get_project: Callable[[], Project]):
        self.get_project = get_project
        self.last_results = None

    def build_ui(self, parent_tag: str):
        with dpg.group(parent=parent_tag):
            # Barra superior
            with dpg.group(horizontal=True):
                dpg.add_text("Simulador Cinemático de Trayectorias y Guiado", color=(0, 180, 216, 255))
                dpg.add_spacer(width=20)
                dpg.add_button(label="SIMULAR TRAYECTORIA (b -> n -> e)", callback=self._cb_run_simulation)
                dpg.add_spacer(width=10)
                dpg.add_text("Estado: En espera", tag="kin_status_text", color=(6, 214, 160, 255))

            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Dos columnas principales
            with dpg.group(horizontal=True):
                # COLUMNA IZQUIERDA: Parametros de Maniobra (~380 px)
                with dpg.child_window(width=380, height=-1, border=True):
                    dpg.add_text("1. Posición Inicial de Navegación:", color=(255, 209, 102, 255))
                    dpg.add_drag_float(label="Latitud inicial (º)", default_value=39.4820, speed=0.0001,
                                       width=110, tag="kin_init_lat")
                    dpg.add_drag_float(label="Longitud inicial (º)", default_value=-0.3475, speed=0.0001,
                                       width=110, tag="kin_init_lon")
                    dpg.add_drag_float(label="Cota inicial h (m)", default_value=50.0, speed=0.1,
                                       width=110, tag="kin_init_h")

                    dpg.add_spacer(height=10)
                    dpg.add_text("2. Comandos en Marco Cuerpo (b-frame):", color=(255, 209, 102, 255))
                    dpg.add_drag_float(label="Velocidad Avance vx_b (m/s)", default_value=8.0, speed=0.1,
                                       min_value=0.0, max_value=50.0, width=90, tag="kin_speed_fwd")
                    dpg.add_drag_float(label="Duración Total (s)", default_value=30.0, speed=1.0,
                                       min_value=5.0, max_value=300.0, width=90, tag="kin_duration")
                    dpg.add_drag_float(label="Paso de Tiempo dt (s)", default_value=0.5, speed=0.05,
                                       min_value=0.1, max_value=2.0, width=90, tag="kin_dt")

                    dpg.add_spacer(height=10)
                    dpg.add_text("3. Perfil de Maniobra Angular:", color=(255, 209, 102, 255))
                    dpg.add_combo(label="Patrón de Giro",
                                  items=["Avance Recto (Rumbo Constante)",
                                         "Giro Circular Continuo (Yaw Rate)",
                                         "Maniobra en S (Oscilante)",
                                         "Ascenso con Inclinación (Pitch)"],
                                  default_value="Giro Circular Continuo (Yaw Rate)",
                                  width=230, tag="kin_pattern")
                    dpg.add_drag_float(label="Rumbo Inicial (º)", default_value=45.0, speed=1.0,
                                       width=90, tag="kin_init_yaw")

                    dpg.add_spacer(height=15)
                    dpg.add_separator()
                    dpg.add_button(label="CALCULAR TRAYECTORIA Y PLOT", width=-1, height=32,
                                   callback=self._cb_run_simulation)

                # COLUMNA DERECHA: Plot 2D de Trayectoria Local (NED) y Cota (ancho restante)
                with dpg.child_window(width=-1, height=-1, border=True):
                    dpg.add_text("Trayectoria en Navegación Local (Plano Horizontal Este vs Norte) [m]:",
                                 color=(0, 180, 216, 255))

                    with dpg.plot(label="Plano Local NED (Metros)", height=380, width=-1, tag="kin_plot_ned"):
                        dpg.add_plot_legend()
                        dpg.add_plot_axis(dpg.mvXAxis, label="Este (m)", tag="kin_plot_x_axis")
                        dpg.add_plot_axis(dpg.mvYAxis, label="Norte (m)", tag="kin_plot_y_axis")
                        dpg.add_line_series([], [], label="Trayectoria del Vehiculo",
                                            parent="kin_plot_y_axis", tag="kin_series_ned")

                    dpg.add_spacer(height=5)
                    # Resumen de metricas
                    with dpg.child_window(height=-1, border=True):
                        dpg.add_text("Resumen de Navegación:", color=(255, 209, 102, 255))
                        dpg.add_text("Distancia Recorrida: -", tag="kin_res_dist")
                        dpg.add_text("Posición Final Geodésica: -", tag="kin_res_final_geo")
                        dpg.add_text("Coordenadas Finales ECEF: -", tag="kin_res_final_ecef", color=(140, 150, 165, 255))

    def _cb_run_simulation(self):
        """Ejecuta la integracion cinematica y actualiza la grafica."""
        try:
            lat0 = np.radians(float(dpg.get_value("kin_init_lat")))
            lon0 = np.radians(float(dpg.get_value("kin_init_lon")))
            h0 = float(dpg.get_value("kin_init_h"))
            speed = float(dpg.get_value("kin_speed_fwd"))
            duration = float(dpg.get_value("kin_duration"))
            dt = float(dpg.get_value("kin_dt"))
            pattern = dpg.get_value("kin_pattern")
            init_yaw = float(dpg.get_value("kin_init_yaw"))

            times = np.arange(0, duration + dt, dt)
            commands = []
            for t in times:
                if "Recto" in pattern:
                    yaw = init_yaw
                    pitch = 0.0
                    roll = 0.0
                elif "Circular" in pattern:
                    yaw = init_yaw + 4.0 * t  # 4 deg/sec
                    pitch = 0.0
                    roll = 1.0
                elif "Oscilante" in pattern:
                    yaw = init_yaw + 25.0 * np.sin(0.3 * t)
                    pitch = 0.5 * np.cos(0.3 * t)
                    roll = 2.0 * np.sin(0.3 * t)
                else:
                    yaw = init_yaw
                    pitch = 2.5
                    roll = 0.0

                commands.append({
                    "dt": dt,
                    "vel_b": [speed, 0.0, 0.0],
                    "attitude_deg": [roll, pitch, yaw]
                })

            op = TrajectoryKinematicsOperator()
            proj = self.get_project()
            res = op.execute(proj, initial_geodetic=(lat0, lon0, h0), commands=commands)

            if not res.success:
                dpg.set_value("kin_status_text", f"Fallo: {res.error_message}")
                return

            self.last_results = res.data
            pos_ned = res.data["pos_ned"]  # (N, 3): [North, East, Down]
            pos_geo = res.data["pos_geodetic"]
            pos_ecef = res.data["pos_ecef"]

            # Actualizar linea en el plot de DearPyGui
            # Eje X del plot = East (pos_ned[:, 1]), Eje Y = North (pos_ned[:, 0])
            east_pts = list(pos_ned[:, 1])
            north_pts = list(pos_ned[:, 0])

            if dpg.does_item_exist("kin_series_ned"):
                dpg.set_value("kin_series_ned", [east_pts, north_pts])
                dpg.fit_axis_data("kin_plot_x_axis")
                dpg.fit_axis_data("kin_plot_y_axis")

            # Metricas
            total_dist = float(np.sum(np.linalg.norm(np.diff(pos_ned, axis=0), axis=1)))
            dpg.set_value("kin_res_dist", f"Distancia Total Recorrida: {total_dist:.2f} m ({total_dist/1000.0:.3f} km)")

            lat_f = np.degrees(pos_geo[-1, 0])
            lon_f = np.degrees(pos_geo[-1, 1])
            h_f = pos_geo[-1, 2]
            dpg.set_value("kin_res_final_geo", f"Posición Final: {lat_f:.6f}º N, {lon_f:.6f}º E, cota: {h_f:.2f} m")

            xf, yf, zf = pos_ecef[-1]
            dpg.set_value("kin_res_final_ecef", f"Coordenadas ECEF: X: {xf:.2f} m, Y: {yf:.2f} m, Z: {zf:.2f} m")
            dpg.set_value("kin_status_text", f"[OK] Trayectoria integrada ({len(times)} épocas)")

        except Exception as e:
            dpg.set_value("kin_status_text", f"Error: {str(e)[:35]}")

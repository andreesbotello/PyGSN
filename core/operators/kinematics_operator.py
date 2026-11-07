"""
PyGSN - Trajectory Kinematics Operator
======================================
Operador de simulacion e integracion cinematica de trayectorias:
- Convierte perfiles de navegacion y maniobras definidas en b-frame (roll, pitch, yaw, velocidad de avance)
  a velocidades en n-frame (NED) mediante C_b^n(t).
- Resuelve la mecanizacion geodésica elipsoidal exacta (Groves / Jekeli) para propagar latitud, longitud y altitud.
- Calcula la trayectoria tridimensional en coordenadas terrestres ECEF (e-frame).
"""

from typing import Any
import numpy as np

from .base import BaseOperator, OperatorResult
from ..geodesy import GRS80, geodetic_to_ecef
from ..rotations import attitude_to_dcm, e_to_n_matrix
from ..kinematics import geodetic_navigation_rates


class TrajectoryKinematicsOperator(BaseOperator):
    """
    Operador que integra una trayectoria desde comandos b-frame hasta coordenadas globales e-frame.
    """
    def __init__(self):
        super().__init__(name="TrajectoryKinematicsOperator")

    def execute(self, project: Any, **kwargs) -> OperatorResult:
        """
        Ejecuta la integracion de trayectoria.
        
        Parametros aceptados en kwargs:
            initial_geodetic: tuple (lat_rad, lon_rad, h_m)
            commands: list de dicts con:
                      - 'dt': float (segundos)
                      - 'vel_b': [vx, vy, vz] en b-frame (m/s)
                      - 'attitude_deg': [roll, pitch, yaw] en grados
                      O arrays 'times', 'vel_b_arr' (N, 3), 'euler_arr' (N, 3).
        """
        result = OperatorResult(operator_name=self.name, success=False)
        result.log("Iniciando integracion cinematica b-frame -> n-frame -> e-frame")

        init_geo = kwargs.get("initial_geodetic")
        if init_geo is None:
            pose = getattr(getattr(project, "platform", None), "pose_e", None) if project is not None else None
            if pose is not None:
                # Origen PLA georreferenciado previamente
                init_geo = (np.radians(pose.lat_deg), np.radians(pose.lon_deg), float(pose.h_ellip_m))
                result.log("Usando como origen la pose PLA georreferenciada de la plataforma activa")
            else:
                init_geo = (0.0, 0.0, 0.0)
                result.log("Sin 'initial_geodetic' ni pose PLA: origen neutro (lat=0, lon=0, h=0)")

        commands = kwargs.get("commands")
        if not commands:
            # Generar una maniobra cinematica de prueba por defecto (ej. avance recto y giro suave)
            result.log("No se especificaron comandos de maniobra; generando perfil cinemático de prueba (10 s)")
            dt = 0.5
            times = np.arange(0, 10.5, dt)
            commands = []
            for t in times:
                # Avance a 5 m/s, giro suave en yaw
                yaw = 45.0 + 2.0 * t # Giro continuo
                pitch = 1.0 * np.sin(0.2 * t)
                roll = 0.5 * np.cos(0.2 * t)
                commands.append({
                    "dt": dt,
                    "vel_b": [5.0, 0.0, 0.0], # 5 m/s hacia adelante (+X_b)
                    "attitude_deg": [roll, pitch, yaw]
                })

        curr_lat, curr_lon, curr_h = float(init_geo[0]), float(init_geo[1]), float(init_geo[2])

        t_list = [0.0]
        geo_list = [[curr_lat, curr_lon, curr_h]]
        ecef_init = geodetic_to_ecef(np.float64(curr_lat), np.float64(curr_lon), np.float64(curr_h), GRS80)
        ecef_list = [ecef_init]
        euler_list = []

        total_t = 0.0
        for cmd in commands:
            dt = float(cmd.get("dt", 0.1))
            total_t += dt
            vel_b = np.array(cmd.get("vel_b", [0.0, 0.0, 0.0]), dtype=np.float64)
            r_deg, p_deg, y_deg = cmd.get("attitude_deg", [0.0, 0.0, 0.0])
            euler_list.append([r_deg, p_deg, y_deg])

            # 1. Matriz de actitud Cb2n (R1, R2, R3 pasivas): Cb2n = R3(-yaw) R2(-pitch) R1(-roll)
            C_b_n = attitude_to_dcm(np.radians(r_deg), np.radians(p_deg), np.radians(y_deg))

            # 2. Transformacion de velocidad a n-frame (NED): v^n = C_b^n * v^b
            v_n = C_b_n @ vel_b

            # 3. Mecanizacion elipsoidal en coordenadas geodésicas (Euler explícito)
            dlat_rate, dlon_rate, dh_rate = geodetic_navigation_rates(v_n, curr_lat, curr_h, GRS80)
            curr_lat += dlat_rate * dt
            curr_lon += dlon_rate * dt
            curr_h += dh_rate * dt

            # 4. Conversion a ECEF (e-frame)
            r_ecef = geodetic_to_ecef(np.float64(curr_lat), np.float64(curr_lon), np.float64(curr_h), GRS80)

            t_list.append(total_t)
            geo_list.append([curr_lat, curr_lon, curr_h])
            ecef_list.append(r_ecef)

        if euler_list:
            euler_list.insert(0, euler_list[0])

        # 5. Posicion en el n-frame (NED) fijo del origen: transformacion exacta de la trayectoria ECEF
        #    (sin la aproximacion de plano tangente: la componente D refleja la curvatura terrestre)
        pos_ecef = np.array(ecef_list, dtype=np.float64)
        Ce2n_0 = e_to_n_matrix(np.float64(init_geo[0]), np.float64(init_geo[1]))
        pos_ned = (pos_ecef - pos_ecef[0]) @ Ce2n_0.T

        result.success = True
        result.data["time"] = np.array(t_list)
        result.data["pos_ned"] = pos_ned
        result.data["pos_geodetic"] = np.array(geo_list)
        result.data["pos_ecef"] = pos_ecef
        result.data["attitude_euler_deg"] = np.array(euler_list)
        result.log(f"Integracion completada: {len(t_list)} epocas calculadas. Distancia horizontal en NED del origen: {np.linalg.norm(pos_ned[-1, :2]):.2f} m")

        return result

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
from ..geodesy import GRS80, radii_of_curvature, geodetic_to_ecef
from ..rotations import euler_to_dcm


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
            # Intentar usar el origen PLA si fue resuelto previamente, o posicion nominal Valencia
            init_geo = (np.radians(39.4820), np.radians(-0.3475), 50.0)
            result.log(f"Usando posicion de origen nominal: {np.degrees(init_geo[0]):.4f}N, {np.degrees(init_geo[1]):.4f}E")

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

        a = GRS80.a
        e2 = GRS80.e2

        curr_lat, curr_lon, curr_h = float(init_geo[0]), float(init_geo[1]), float(init_geo[2])
        curr_ned = np.zeros(3, dtype=np.float64)

        t_list = [0.0]
        ned_list = [curr_ned.copy()]
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

            # 1. Matriz de actitud C_b^n
            C_b_n = euler_to_dcm(np.radians(r_deg), np.radians(p_deg), np.radians(y_deg))

            # 2. Transformacion de velocidad a n-frame (NED): v^n = C_b^n * v^b
            v_n = C_b_n @ vel_b

            # 3. Integracion en n-frame (plano local métrico)
            curr_ned += v_n * dt

            # 4. Mecanizacion elipsoidal en coordenadas geodésicas
            Rm, Rn = radii_of_curvature(np.float64(curr_lat), GRS80)
            dlat = (v_n[0] / (Rm + curr_h)) * dt
            cos_lat = np.cos(curr_lat)
            dlon = (v_n[1] / ((Rn + curr_h) * cos_lat)) * dt if abs(cos_lat) > 1e-12 else 0.0
            dh = -v_n[2] * dt

            curr_lat += dlat
            curr_lon += dlon
            curr_h += dh

            # 5. Conversion a ECEF (e-frame)
            r_ecef = geodetic_to_ecef(np.float64(curr_lat), np.float64(curr_lon), np.float64(curr_h), GRS80)

            t_list.append(total_t)
            ned_list.append(curr_ned.copy())
            geo_list.append([curr_lat, curr_lon, curr_h])
            ecef_list.append(r_ecef)

        if euler_list:
            euler_list.insert(0, euler_list[0])

        result.success = True
        result.data["time"] = np.array(t_list)
        result.data["pos_ned"] = np.array(ned_list)
        result.data["pos_geodetic"] = np.array(geo_list)
        result.data["pos_ecef"] = np.array(ecef_list)
        result.data["attitude_euler_deg"] = np.array(euler_list)
        result.log(f"Integracion completada: {len(t_list)} epocas calculadas. Distancia NED recorrida: {np.linalg.norm(curr_ned[:2]):.2f} m")

        return result

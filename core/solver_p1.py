"""
PyGSN - Solver Practica 1 (2026)
================================
Motor de calculo desacoplado de la interfaz grafica para la Practica 1:
- Punto 1: Centroide GNSS, Procrustes SVD (Kabsch), Actitud Cb2n y Origen PLA
- Punto 2a: Transformacion global con actitud GNSS a ECEF, Geodesicas y UTM Huso 30
- Punto 2b: Transformacion global con orientacion INS, correccion de declinacion magnetica
            y desalineamiento de montaje (boresight).
- Calculo de diferencias residuales (2a - 2b).
"""

from dataclasses import dataclass, field
from typing import Any
import numpy as np

from .geodesy import GRS80, Ellipsoid, geodetic_to_ecef, ecef_to_geodetic, utm_projection_huso30, rad_to_dms, radii_of_curvature
from .rotations import (
    e_to_n_matrix, n_to_e_matrix, attitude_to_dcm, dcm_to_attitude, dcm_to_euler,
    sensor_to_body_matrix, magnetic_to_geodetic_north_matrix
)
from .alignment import kabsch_orthogonal_procrustes
from .models import Platform, Sensor, SensorType


@dataclass
class SensorResult:
    code: str
    ecef: np.ndarray             # [X, Y, Z] (m)
    lat_rad: np.float64          # Latitud geodesica (rad)
    lon_rad: np.float64          # Longitud geodesica (rad)
    h_ellip: np.float64          # Altitud elipsoidal (m)
    easting: np.float64          # Proyeccion UTM East (m)
    northing: np.float64         # Proyeccion UTM North (m)
    zone: int                    # Huso UTM
    h_orto: np.float64           # Altitud ortometrica (m)


@dataclass
class P1Solution:
    # Metadatos
    ellipsoid: Ellipsoid
    geoid_undulation_N: float
    magnetic_declination_deg: float

    # Punto 1: GNSS
    gnss_ecef: dict[str, np.ndarray]
    centroid_ecef: np.ndarray
    centroid_lat_rad: np.float64
    centroid_lon_rad: np.float64
    centroid_h_ellip: np.float64
    Ce2n_centroid: np.ndarray
    gnss_vectors_n: dict[str, np.ndarray]
    Cb2n_gnss: np.ndarray
    euler_gnss_deg: tuple[float, float, float]
    attitude_gnss_deg: tuple[float, float, float]   # (roll, pitch, yaw)
    pla_origin_ecef: np.ndarray
    pla_origin_lat_rad: np.float64
    pla_origin_lon_rad: np.float64
    pla_origin_h_ellip: np.float64

    # Punto 2a: Resultados con actitud GNSS
    results_2a: dict[str, SensorResult]

    # Punto 2b: INS
    ins_attitude_deg: tuple[float, float, float]
    Cs2n_mn: np.ndarray
    Cmn2gn: np.ndarray
    Cs2b_ins: np.ndarray
    Cb2s_ins: np.ndarray
    Cb2n_ins: np.ndarray
    euler_ins_deg: tuple[float, float, float]
    attitude_ins_total_deg: tuple[float, float, float]
    results_2b: dict[str, SensorResult]

    # Diferencias (2a - 2b) expresadas en UTM y altura ortometrica
    diff_2a_2b_utm: dict[str, tuple[float, float, float]] # code -> (dE, dN, dH)


def solve_practica_1(
    platform: Platform,
    gnss_observations: dict[str, tuple[np.float64, np.float64, np.float64]], # code -> (lat_rad, lon_rad, h)
    ins_attitude_deg: tuple[float, float, float],                            # (roll, pitch, yaw) deg
    magnetic_declination_deg: float = -0.700,
    geoid_undulation_N: float = 50.0166,
    ellipsoid: Ellipsoid = GRS80
) -> P1Solution:
    """
    Ejecuta el pipeline completo de resolucion de la Practica 1.
    """
    # -------------------------------------------------------------
    # 1. PUNTOS GNSS EN ECEF Y CENTROIDE
    # -------------------------------------------------------------
    gnss_codes = ["REC2", "REC3", "REC4", "REC5"]
    gnss_ecef = {}
    for code in gnss_codes:
        lat, lon, h = gnss_observations[code]
        gnss_ecef[code] = geodetic_to_ecef(lat, lon, h, ellipsoid)

    # Matriz 3 x 4 de receptores
    pts_ecef = np.array([gnss_ecef[c] for c in gnss_codes]).T
    centroid_ecef = np.mean(pts_ecef, axis=1)

    lat_cent, lon_cent, h_cent = ecef_to_geodetic(centroid_ecef, ellipsoid)
    Ce2n_centroid = e_to_n_matrix(lat_cent, lon_cent)

    # Vectores relativos en n-frame respecto al centroide
    gnss_vectors_n = {}
    for code in gnss_codes:
        dx_e = gnss_ecef[code] - centroid_ecef
        gnss_vectors_n[code] = Ce2n_centroid @ dx_e

    # Vectores en b-frame de los receptores
    pts_b = np.array([platform.sensors[c].lever_arm_b for c in gnss_codes]).T
    pts_n = np.array([gnss_vectors_n[c] for c in gnss_codes]).T

    # -------------------------------------------------------------
    # 2. RESOLUCION SVD KABSCH Cb2n (PUNTO 1)
    # -------------------------------------------------------------
    Cb2n_gnss, cent_b, cent_n, residuals = kabsch_orthogonal_procrustes(pts_b, pts_n)
    a1, a2, a3 = dcm_to_euler(Cb2n_gnss)
    roll_gnss, pitch_gnss, yaw_gnss = dcm_to_attitude(Cb2n_gnss)

    euler_gnss_deg = (float(np.degrees(a1)), float(np.degrees(a2)), float(np.degrees(a3)))
    attitude_gnss_deg = (float(np.degrees(roll_gnss)), float(np.degrees(pitch_gnss)), float(np.degrees(yaw_gnss)))

    # Origen de la plataforma en ECEF:
    # xe_pla = xe_cent - Cn2e @ Cb2n @ cent_b
    Cn2e_cent = n_to_e_matrix(lat_cent, lon_cent)
    Cb2e_gnss = Cn2e_cent @ Cb2n_gnss
    pla_ecef = centroid_ecef - Cb2e_gnss @ cent_b
    lat_pla, lon_pla, h_pla = ecef_to_geodetic(pla_ecef, ellipsoid)

    # Matriz Cb2e de la plataforma calculada en el origen PLA
    Cn2e_pla = n_to_e_matrix(lat_pla, lon_pla)
    Cb2e_1 = Cn2e_pla @ Cb2n_gnss

    # -------------------------------------------------------------
    # 3. CASO 2A: PROPAGACION DE TODOS LOS SENSORES CON ACTITUD GNSS
    # -------------------------------------------------------------
    # Se incluyen todos los sensores de la plataforma + CENT
    all_devices_b = {code: s.lever_arm_b for code, s in platform.sensors.items()}
    all_devices_b["CENT"] = cent_b

    results_2a = {}
    for code, xb in all_devices_b.items():
        xe = pla_ecef + Cb2e_1 @ xb
        lat_s, lon_s, h_s = ecef_to_geodetic(xe, ellipsoid)
        easting, northing, zone = utm_projection_huso30(lat_s, lon_s, ellipsoid)
        h_orto = h_s - geoid_undulation_N
        results_2a[code] = SensorResult(
            code=code, ecef=xe, lat_rad=lat_s, lon_rad=lon_s, h_ellip=h_s,
            easting=easting, northing=northing, zone=zone, h_orto=h_orto
        )

    # -------------------------------------------------------------
    # 4. CASO 2B: ORIENTACION INS + MISALIGNMENT + DECLINACION
    # -------------------------------------------------------------
    r_ins = np.radians(ins_attitude_deg[0])
    p_ins = np.radians(ins_attitude_deg[1])
    y_ins = np.radians(ins_attitude_deg[2])
    Cs2n_mn = attitude_to_dcm(r_ins, p_ins, y_ins)

    decl_rad = np.radians(magnetic_declination_deg)
    Cmn2gn = magnetic_to_geodetic_north_matrix(decl_rad)

    # Misalignment del INS
    ins_sensor = platform.sensors["INS"]
    a1_i, a2_i, a3_i = [np.radians(x) for x in ins_sensor.boresight_deg]
    Cs2b_ins = sensor_to_body_matrix(a1_i, a2_i, a3_i)
    Cb2s_ins = Cs2b_ins.T

    # Rotacion total Cb2n:
    Cb2n_ins = Cmn2gn @ (Cs2n_mn @ Cb2s_ins)
    a1_ins_tot, a2_ins_tot, a3_ins_tot = dcm_to_euler(Cb2n_ins)
    r_tot, p_tot, y_tot = dcm_to_attitude(Cb2n_ins)

    euler_ins_deg = (float(np.degrees(a1_ins_tot)), float(np.degrees(a2_ins_tot)), float(np.degrees(a3_ins_tot)))
    attitude_ins_total_deg = (float(np.degrees(r_tot)), float(np.degrees(p_tot)), float(np.degrees(y_tot)))

    Cb2e_2b = Cn2e_pla @ Cb2n_ins
    results_2b = {}
    diff_2a_2b_utm = {}

    for code, xb in all_devices_b.items():
        xe = pla_ecef + Cb2e_2b @ xb
        lat_s, lon_s, h_s = ecef_to_geodetic(xe, ellipsoid)
        easting, northing, zone = utm_projection_huso30(lat_s, lon_s, ellipsoid)
        h_orto = h_s - geoid_undulation_N
        results_2b[code] = SensorResult(
            code=code, ecef=xe, lat_rad=lat_s, lon_rad=lon_s, h_ellip=h_s,
            easting=easting, northing=northing, zone=zone, h_orto=h_orto
        )

        # Diferencia: 2a - 2b (conforme a 2025_P1_2b.txt)
        res_2a = results_2a[code]
        dE = res_2a.easting - easting
        dN = res_2a.northing - northing
        dH = res_2a.h_orto - h_orto
        diff_2a_2b_utm[code] = (dE, dN, dH)

    return P1Solution(
        ellipsoid=ellipsoid,
        geoid_undulation_N=geoid_undulation_N,
        magnetic_declination_deg=magnetic_declination_deg,
        gnss_ecef=gnss_ecef,
        centroid_ecef=centroid_ecef,
        centroid_lat_rad=lat_cent,
        centroid_lon_rad=lon_cent,
        centroid_h_ellip=h_cent,
        Ce2n_centroid=Ce2n_centroid,
        gnss_vectors_n=gnss_vectors_n,
        Cb2n_gnss=Cb2n_gnss,
        euler_gnss_deg=euler_gnss_deg,
        attitude_gnss_deg=attitude_gnss_deg,
        pla_origin_ecef=pla_ecef,
        pla_origin_lat_rad=lat_pla,
        pla_origin_lon_rad=lon_pla,
        pla_origin_h_ellip=h_pla,
        results_2a=results_2a,
        ins_attitude_deg=ins_attitude_deg,
        Cs2n_mn=Cs2n_mn,
        Cmn2gn=Cmn2gn,
        Cs2b_ins=Cs2b_ins,
        Cb2s_ins=Cb2s_ins,
        Cb2n_ins=Cb2n_ins,
        euler_ins_deg=euler_ins_deg,
        attitude_ins_total_deg=attitude_ins_total_deg,
        results_2b=results_2b,
        diff_2a_2b_utm=diff_2a_2b_utm
    )


def create_default_p1_platform() -> Platform:
    """Crea la plataforma oficial calibrada segun el enunciado de la Practica 1 (2026)."""
    plat = Platform(
        name="Plataforma P1 2026 (Car/Rig)",
        platform_type="CAR",
        length_m=1.2,
        width_m=0.8,
        height_m=0.1
    )
    # Sensores calibrados
    plat.add_sensor(Sensor(code="PLA", name="Centro Plataforma", sensor_type=SensorType.PLATFORM_ORIGIN,
                           lever_arm_b=np.array([0.0, 0.0, 0.0]), boresight_deg=(0.0, 0.0, 0.0)))
    plat.add_sensor(Sensor(code="INS", name="SBG Ellipse2-N", sensor_type=SensorType.INS,
                           lever_arm_b=np.array([0.0, 0.0, -0.025]), boresight_deg=(0.263568, -0.437974, 2.869214)))
    plat.add_sensor(Sensor(code="REC2", name="GNSS Antena 2", sensor_type=SensorType.GNSS,
                           lever_arm_b=np.array([0.4, -0.4, -0.015]), boresight_deg=(0.0, 0.0, 0.0)))
    plat.add_sensor(Sensor(code="REC3", name="GNSS Antena 3", sensor_type=SensorType.GNSS,
                           lever_arm_b=np.array([0.4, 0.4, -0.015]), boresight_deg=(0.0, 0.0, 0.0)))
    plat.add_sensor(Sensor(code="REC4", name="GNSS Antena 4", sensor_type=SensorType.GNSS,
                           lever_arm_b=np.array([-0.4, -0.4, -0.015]), boresight_deg=(0.0, 0.0, 0.0)))
    plat.add_sensor(Sensor(code="REC5", name="GNSS Antena 5", sensor_type=SensorType.GNSS,
                           lever_arm_b=np.array([-0.4, 0.4, -0.015]), boresight_deg=(0.0, 0.0, 0.0)))
    plat.add_sensor(Sensor(code="CAM1", name="Camara Izquierda", sensor_type=SensorType.CAMERA,
                           lever_arm_b=np.array([0.7, -0.15, -0.080]), boresight_deg=(0.196543, 0.541674, -1.355847)))
    plat.add_sensor(Sensor(code="CAM2", name="Camara Derecha", sensor_type=SensorType.CAMERA,
                           lever_arm_b=np.array([0.7, 0.15, -0.080]), boresight_deg=(-0.287495, 0.426588, 1.128792)))
    return plat

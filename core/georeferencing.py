"""
PyGSN - Core Georeferencing Module
==================================
Motor de cálculo para georreferenciación rigurosa y determinación de actitud:
- Estimación de actitud de plataforma mediante constelación de antenas GNSS (SVD de Kabsch / Procrustes).
- Determinación de coordenadas del centro de masa / origen del body-frame.
- Fusión y encadenamiento de rotaciones con sensores inerciales (INS):
  corrección por declinación magnética y matrices de desalineamiento (boresight).
- Propagación cinemática a todos los sensores del rig en:
  1. ECEF (Terrestre / e-frame)
  2. Geodésicas elipsoidales (phi, lambda, h)
  3. Proyección cartográfica Transversa de Mercator / UTM con cota ortométrica
- Análisis de consistencia y residuales de calibración (GNSS vs INS).
"""

from dataclasses import dataclass, field
from typing import Any
import numpy as np

from .geodesy import GRS80, Ellipsoid, geodetic_to_ecef, ecef_to_geodetic, utm_projection_huso30, rad_to_dms
from .rotations import (
    e_to_n_matrix, n_to_e_matrix, attitude_to_dcm, dcm_to_attitude, dcm_to_euler,
    sensor_to_body_matrix, magnetic_to_geodetic_north_matrix
)
from .alignment import kabsch_orthogonal_procrustes
from .models import Platform, Sensor, SensorType


@dataclass
class SensorResult:
    """Coordenadas propagadas de un sensor en los distintos sistemas."""
    code: str
    ecef: np.ndarray             # [X, Y, Z] ECEF (m)
    lat_rad: np.float64          # Latitud geodésica (rad)
    lon_rad: np.float64          # Longitud geodésica (rad)
    h_ellip: np.float64          # Altitud elipsoidal (m)
    easting: np.float64          # Proyección UTM Este (m)
    northing: np.float64         # Proyección UTM Norte (m)
    zone: int                    # Huso UTM
    h_orto: np.float64           # Altitud ortométrica (m)


@dataclass
class GeoreferencingSolution:
    """Resultado estructurado de la georreferenciación y transformación."""
    ellipsoid: Ellipsoid
    geoid_undulation_N: float
    magnetic_declination_deg: float

    # Estimación de orientación por GNSS
    gnss_ecef: dict[str, np.ndarray]
    centroid_ecef: np.ndarray
    centroid_lat_rad: np.float64
    centroid_lon_rad: np.float64
    centroid_h_ellip: np.float64
    Ce2n_centroid: np.ndarray
    gnss_vectors_n: dict[str, np.ndarray]
    Cb2n_gnss: np.ndarray
    euler_gnss_deg: tuple[float, float, float]
    attitude_gnss_deg: tuple[float, float, float]   # (roll, pitch, yaw) [deg]
    pla_origin_ecef: np.ndarray
    pla_origin_lat_rad: np.float64
    pla_origin_lon_rad: np.float64
    pla_origin_h_ellip: np.float64

    # Propagación con actitud estimada por GNSS
    results_gnss: dict[str, SensorResult]

    # Orientación y rotaciones con sensor INS
    ins_attitude_deg: tuple[float, float, float]
    Cs2n_mn: np.ndarray
    Cmn2gn: np.ndarray
    Cs2b_ins: np.ndarray
    Cb2s_ins: np.ndarray
    Cb2n_ins: np.ndarray
    euler_ins_deg: tuple[float, float, float]
    attitude_ins_total_deg: tuple[float, float, float]
    results_ins: dict[str, SensorResult]

    # Comparación de consistencia y residuales (GNSS vs INS) en UTM y cota
    diff_gnss_ins_utm: dict[str, tuple[float, float, float]]  # code -> (dE, dN, dH)

    # Auditoría matemática y métricas de error
    residuals_gnss_m: dict[str, float] = field(default_factory=dict) # code -> residuo 3D (m)
    det_dcm: float = 1.0
    ortho_error_dcm: float = 0.0
    reference_system: Any = None

    # Aliases de compatibilidad para evitar rupturas de código previo
    @property
    def results_2a(self) -> dict[str, SensorResult]:
        return self.results_gnss

    @property
    def results_2b(self) -> dict[str, SensorResult]:
        return self.results_ins

    @property
    def diff_2a_2b_utm(self) -> dict[str, tuple[float, float, float]]:
        return self.diff_gnss_ins_utm


# Alias de compatibilidad
P1Solution = GeoreferencingSolution


def solve_multisensor_georeferencing(
    platform: Platform,
    gnss_observations: dict[str, tuple[np.float64, np.float64, np.float64]] | None = None,
    ins_attitude_deg: tuple[float, float, float] | None = None,
    magnetic_declination_deg: float = -0.700,
    geoid_undulation_N: float = 50.0166,
    ellipsoid: Ellipsoid = GRS80,
    gnss_sensor_codes: list[str] | None = None,
    ins_sensor_code: str | None = None,
    reference_system: Any = None,
    utm_zone: int = 30,
    utm_hemisphere: str = "N"
) -> GeoreferencingSolution:
    """
    Calcula la orientación y georreferenciación de una plataforma multisensor arbitraria.
    Soporta desacoplamiento total mediante ReferenceSystem (SRT / e-frame).
    """
    from .geodesy import utm_projection

    if reference_system is not None:
        if hasattr(reference_system, "get_ellipsoid"):
            ellipsoid = reference_system.get_ellipsoid()
        geoid_undulation_N = float(getattr(reference_system, "geoid_undulation_N", geoid_undulation_N))
        magnetic_declination_deg = float(getattr(reference_system, "magnetic_declination_deg", magnetic_declination_deg))
        utm_zone = int(getattr(reference_system, "utm_zone", utm_zone))
        utm_hemisphere = str(getattr(reference_system, "utm_hemisphere", utm_hemisphere))

    # Auto-detección de observaciones GNSS si no se proporcionan explícitamente
    if gnss_observations is None:
        gnss_observations = {}
        for c, s in platform.sensors.items():
            g_obs = s.geodetic_obs
            if g_obs is not None:
                gnss_observations[c] = g_obs

    from .validation import validate_sensor_codes_and_obs
    gnss_sensor_codes = validate_sensor_codes_and_obs(
        platform.sensors,
        gnss_observations,
        required_codes=gnss_sensor_codes
    )

    # Auto-detección de actitud INS si no se proporciona
    if ins_attitude_deg is None:
        ins_sensor = None
        if ins_sensor_code and ins_sensor_code in platform.sensors:
            ins_sensor = platform.sensors[ins_sensor_code]
        else:
            for s in platform.sensors.values():
                if s.sensor_type == SensorType.INS or s.code == "INS":
                    ins_sensor = s
                    break
        if ins_sensor and ins_sensor.attitude_obs_deg is not None:
            ins_attitude_deg = ins_sensor.attitude_obs_deg
        else:
            ins_attitude_deg = (0.0, 0.0, 0.0)

    # 1. Puntos GNSS en ECEF y Centroide
    gnss_ecef = {}
    for code in gnss_sensor_codes:
        lat, lon, h = gnss_observations[code]
        gnss_ecef[code] = geodetic_to_ecef(lat, lon, h, ellipsoid)

    pts_ecef = np.array([gnss_ecef[c] for c in gnss_sensor_codes]).T
    centroid_ecef = np.mean(pts_ecef, axis=1)

    lat_cent, lon_cent, h_cent = ecef_to_geodetic(centroid_ecef, ellipsoid)
    Ce2n_centroid = e_to_n_matrix(lat_cent, lon_cent)

    # Vectores relativos en n-frame respecto al centroide
    gnss_vectors_n = {}
    for code in gnss_sensor_codes:
        dx_e = gnss_ecef[code] - centroid_ecef
        gnss_vectors_n[code] = Ce2n_centroid @ dx_e

    # Vectores en b-frame de los receptores
    pts_b = np.array([platform.sensors[c].lever_arm_b for c in gnss_sensor_codes]).T
    pts_n = np.array([gnss_vectors_n[c] for c in gnss_sensor_codes]).T

    # 2. Resolución de actitud Cb2n mediante Procrustes SVD (Kabsch)
    Cb2n_gnss, cent_b, cent_n, raw_residuals = kabsch_orthogonal_procrustes(pts_b, pts_n)
    a1, a2, a3 = dcm_to_euler(Cb2n_gnss)
    roll_gnss, pitch_gnss, yaw_gnss = dcm_to_attitude(Cb2n_gnss)

    euler_gnss_deg = (float(np.degrees(a1)), float(np.degrees(a2)), float(np.degrees(a3)))
    attitude_gnss_deg = (float(np.degrees(roll_gnss)), float(np.degrees(pitch_gnss)), float(np.degrees(yaw_gnss)))

    det_dcm = float(np.linalg.det(Cb2n_gnss))
    ortho_error_dcm = float(np.linalg.norm(Cb2n_gnss @ Cb2n_gnss.T - np.eye(3)))

    # Origen de la plataforma en ECEF:
    Cn2e_cent = n_to_e_matrix(lat_cent, lon_cent)
    Cb2e_gnss = Cn2e_cent @ Cb2n_gnss
    pla_ecef = centroid_ecef - Cb2e_gnss @ cent_b
    lat_pla, lon_pla, h_pla = ecef_to_geodetic(pla_ecef, ellipsoid)

    Cn2e_pla = n_to_e_matrix(lat_pla, lon_pla)
    Cb2e_1 = Cn2e_pla @ Cb2n_gnss

    # Residuos métricos 3D por antena
    residuals_gnss_m = {}
    for code in gnss_sensor_codes:
        calc_e = pla_ecef + Cb2e_1 @ platform.sensors[code].lever_arm_b
        res_m = float(np.linalg.norm(gnss_ecef[code] - calc_e))
        residuals_gnss_m[code] = res_m

    # 3. Propagación de todos los sensores con actitud GNSS
    all_devices_b = {code: s.lever_arm_b for code, s in platform.sensors.items()}
    all_devices_b["CENT"] = cent_b

    results_gnss = {}
    for code, xb in all_devices_b.items():
        xe = pla_ecef + Cb2e_1 @ xb
        lat_s, lon_s, h_s = ecef_to_geodetic(xe, ellipsoid)
        easting, northing, zone = utm_projection(lat_s, lon_s, zone=utm_zone, hemisphere=utm_hemisphere, ell=ellipsoid)
        h_orto = h_s - geoid_undulation_N
        results_gnss[code] = SensorResult(
            code=code, ecef=xe, lat_rad=lat_s, lon_rad=lon_s, h_ellip=h_s,
            easting=easting, northing=northing, zone=zone, h_orto=h_orto
        )

    # 4. Orientación con INS + Desalineamiento + Corrección Geomagnética
    r_ins = np.radians(ins_attitude_deg[0])
    p_ins = np.radians(ins_attitude_deg[1])
    y_ins = np.radians(ins_attitude_deg[2])
    Cs2n_mn = attitude_to_dcm(r_ins, p_ins, y_ins)

    decl_rad = np.radians(magnetic_declination_deg)
    Cmn2gn = magnetic_to_geodetic_north_matrix(decl_rad)

    # Boresight INS dinámico
    ins_sensor = None
    if ins_sensor_code:
        ins_sensor = platform.sensors.get(ins_sensor_code)
    if not ins_sensor:
        for s in platform.sensors.values():
            if s.sensor_type == SensorType.INS or s.code == "INS":
                ins_sensor = s
                break
    if ins_sensor:
        a1_i, a2_i, a3_i = [np.radians(x) for x in ins_sensor.boresight_deg]
    else:
        a1_i, a2_i, a3_i = 0.0, 0.0, 0.0

    Cs2b_ins = sensor_to_body_matrix(a1_i, a2_i, a3_i)
    Cb2s_ins = Cs2b_ins.T

    # Cb2n total INS
    Cb2n_ins = Cmn2gn @ (Cs2n_mn @ Cb2s_ins)
    a1_it, a2_it, a3_it = dcm_to_euler(Cb2n_ins)
    r_it, p_it, y_it = dcm_to_attitude(Cb2n_ins)

    euler_ins_deg = (float(np.degrees(a1_it)), float(np.degrees(a2_it)), float(np.degrees(a3_it)))
    attitude_ins_total_deg = (float(np.degrees(r_it)), float(np.degrees(p_it)), float(np.degrees(y_it)))

    Cb2e_2b = Cn2e_pla @ Cb2n_ins
    results_ins = {}
    diff_gnss_ins_utm = {}

    for code, xb in all_devices_b.items():
        xe = pla_ecef + Cb2e_2b @ xb
        lat_s, lon_s, h_s = ecef_to_geodetic(xe, ellipsoid)
        easting, northing, zone = utm_projection(lat_s, lon_s, zone=utm_zone, hemisphere=utm_hemisphere, ell=ellipsoid)
        h_orto = h_s - geoid_undulation_N
        results_ins[code] = SensorResult(
            code=code, ecef=xe, lat_rad=lat_s, lon_rad=lon_s, h_ellip=h_s,
            easting=easting, northing=northing, zone=zone, h_orto=h_orto
        )

        res_g = results_gnss[code]
        dE = res_g.easting - easting
        dN = res_g.northing - northing
        dH = res_g.h_orto - h_orto
        diff_gnss_ins_utm[code] = (dE, dN, dH)

    return GeoreferencingSolution(
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
        results_gnss=results_gnss,
        ins_attitude_deg=ins_attitude_deg,
        Cs2n_mn=Cs2n_mn,
        Cmn2gn=Cmn2gn,
        Cs2b_ins=Cs2b_ins,
        Cb2s_ins=Cb2s_ins,
        Cb2n_ins=Cb2n_ins,
        euler_ins_deg=euler_ins_deg,
        attitude_ins_total_deg=attitude_ins_total_deg,
        results_ins=results_ins,
        diff_gnss_ins_utm=diff_gnss_ins_utm,
        residuals_gnss_m=residuals_gnss_m,
        det_dcm=det_dcm,
        ortho_error_dcm=ortho_error_dcm,
        reference_system=reference_system
    )


def create_reference_platform() -> Platform:
    """Crea la plataforma de calibración de referencia con los sensores del vehículo."""
    plat = Platform(
        name="Plataforma de Referencia (4x GNSS + INS + 2x CAM)",
        platform_type="CAR",
        length_m=1.2,
        width_m=0.8,
        height_m=0.1
    )
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
    plat.add_sensor(Sensor(code="CAM1", name="Cámara Frontal Izq", sensor_type=SensorType.CAMERA,
                           lever_arm_b=np.array([0.7, -0.15, -0.080]), boresight_deg=(0.196543, 0.541674, -1.355847)))
    plat.add_sensor(Sensor(code="CAM2", name="Cámara Frontal Der", sensor_type=SensorType.CAMERA,
                           lever_arm_b=np.array([0.7, 0.15, -0.080]), boresight_deg=(-0.287495, 0.426588, 1.128792)))
    return plat


# Aliases
solve_practica_1 = solve_multisensor_georeferencing
create_default_p1_platform = create_reference_platform

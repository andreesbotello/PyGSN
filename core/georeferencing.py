"""
PyGSN - Core Georeferencing Module
==================================
Motor matemático para georreferenciación rigurosa y determinación de actitud:
- Descompuesto en funciones atómicas puras (100% deterministas y auditables).
- Estimación de actitud mediante constelación de antenas GNSS (SVD de Kabsch / Procrustes).
- Determinación de coordenadas del centro de masa / origen del body-frame en ECEF.
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

from .geodesy import (
    GRS80, Ellipsoid, geodetic_to_ecef, ecef_to_geodetic,
    utm_projection, ellipsoidal_to_orthometric
)
from .rotations import (
    e_to_n_matrix, n_to_e_matrix, attitude_to_dcm, dcm_to_attitude,
    dcm_to_euler, sensor_to_body_matrix, magnetic_to_geodetic_north_matrix,
    reorthonormalize_dcm, audit_dcm_condition
)
from .alignment import kabsch_orthogonal_procrustes
from .kinematics import propagate_lever_arm_ecef, solve_origin_from_centroid_ecef
from .validation import validate_finite, validate_attitude_angles, validate_sensor_codes_and_obs


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
LegacySolution = GeoreferencingSolution


# =============================================================================
# Batería de Funciones Matemáticas Puras (Agnósticas de POO)
# =============================================================================

def gnss_observations_to_ecef(
    gnss_observations: dict[str, tuple[float, float, float]],
    ell: Ellipsoid = GRS80
) -> dict[str, np.ndarray]:
    """
    Paso 1: Convierte observaciones geodésicas GNSS (lat, lon, h) a coordenadas
    cartesianas geocéntricas ECEF (X, Y, Z).
    """
    gnss_ecef = {}
    for code, (lat, lon, h) in gnss_observations.items():
        gnss_ecef[code] = geodetic_to_ecef(np.float64(lat), np.float64(lon), np.float64(h), ell)
    return gnss_ecef


def compute_navigation_centroid(
    gnss_ecef: dict[str, np.ndarray],
    codes: list[str],
    ell: Ellipsoid = GRS80
) -> tuple[np.ndarray, np.float64, np.float64, np.float64, np.ndarray]:
    """
    Paso 2: Calcula el centroide cartesiano ECEF de las antenas GNSS seleccionadas,
    sus coordenadas geodésicas en el elipsoide y la matriz de orientación local Ce2n.
    """
    pts_ecef = np.array([gnss_ecef[c] for c in codes], dtype=np.float64).T
    centroid_ecef = np.mean(pts_ecef, axis=1)

    lat_cent, lon_cent, h_cent = ecef_to_geodetic(centroid_ecef, ell)
    Ce2n_centroid = e_to_n_matrix(lat_cent, lon_cent)

    return centroid_ecef, lat_cent, lon_cent, h_cent, Ce2n_centroid


def project_ecef_to_nframe(
    gnss_ecef: dict[str, np.ndarray],
    codes: list[str],
    centroid_ecef: np.ndarray,
    Ce2n_centroid: np.ndarray
) -> dict[str, np.ndarray]:
    """
    Paso 3: Proyecta los desplazamientos relativos de las antenas en ECEF respecto al
    centroide hacia el plano tangencial local n-frame (NED) definido en el centroide:
        Delta r_i^n = Ce2n_centroid @ (r_i^e - r_cent^e)
    """
    gnss_vectors_n = {}
    for code in codes:
        dx_e = gnss_ecef[code] - centroid_ecef
        gnss_vectors_n[code] = Ce2n_centroid @ dx_e
    return gnss_vectors_n


def solve_attitude_kabsch(
    lever_arms_b: dict[str, np.ndarray],
    gnss_vectors_n: dict[str, np.ndarray],
    codes: list[str]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[float, float, float], tuple[float, float, float], float, float]:
    """
    Paso 4: Resuelve la orientación Cb2n de la plataforma respecto al n-frame
    mediante el algoritmo de Procrustes Ortogonal (Kabsch / SVD).

    Retorna:
        (Cb2n_gnss, cent_b, cent_n, euler_gnss_deg, attitude_gnss_deg, det_dcm, ortho_error)
    """
    pts_b = np.array([lever_arms_b[c] for c in codes], dtype=np.float64).T
    pts_n = np.array([gnss_vectors_n[c] for c in codes], dtype=np.float64).T

    Cb2n_gnss, cent_b, cent_n, _ = kabsch_orthogonal_procrustes(pts_b, pts_n)
    a1, a2, a3 = dcm_to_euler(Cb2n_gnss)
    roll_gnss, pitch_gnss, yaw_gnss = dcm_to_attitude(Cb2n_gnss)

    euler_gnss_deg = (float(np.degrees(a1)), float(np.degrees(a2)), float(np.degrees(a3)))
    attitude_gnss_deg = (float(np.degrees(roll_gnss)), float(np.degrees(pitch_gnss)), float(np.degrees(yaw_gnss)))

    det_dcm, ortho_error = audit_dcm_condition(Cb2n_gnss)

    return Cb2n_gnss, cent_b, cent_n, euler_gnss_deg, attitude_gnss_deg, det_dcm, ortho_error


def solve_pla_origin_ecef(
    centroid_ecef: np.ndarray,
    cent_b: np.ndarray,
    Cb2n_gnss: np.ndarray,
    lat_cent_rad: np.float64,
    lon_cent_rad: np.float64,
    ell: Ellipsoid = GRS80
) -> tuple[np.ndarray, np.float64, np.float64, np.float64, np.ndarray, np.ndarray]:
    """
    Paso 5: Determina la posición cartesiana ECEF y geodésica del origen de la plataforma (PLA) [0,0,0]^b,
    y computa la matriz de transformación Cb2e respecto al n-frame del punto PLA:
        Cb2e_cent = Cn2e(lat_cent, lon_cent) @ Cb2n_gnss
        r_pla^e = r_cent^e - Cb2e_cent @ cent_b
        Cb2e_pla = Cn2e(lat_pla, lon_pla) @ Cb2n_gnss
    """
    Cn2e_cent = n_to_e_matrix(lat_cent_rad, lon_cent_rad)
    Cb2e_cent = Cn2e_cent @ Cb2n_gnss

    pla_ecef = solve_origin_from_centroid_ecef(centroid_ecef, cent_b, Cb2e_cent)
    lat_pla, lon_pla, h_pla = ecef_to_geodetic(pla_ecef, ell)

    Cn2e_pla = n_to_e_matrix(lat_pla, lon_pla)
    Cb2e_pla = Cn2e_pla @ Cb2n_gnss

    return pla_ecef, lat_pla, lon_pla, h_pla, Cn2e_pla, Cb2e_pla


def solve_attitude_ins_chain(
    ins_attitude_deg: tuple[float, float, float],
    magnetic_declination_deg: float,
    boresight_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, tuple[float, float, float], tuple[float, float, float]]:
    """
    Paso 6: Calcula la orientación Cb2n estimada por el sensor INS, encadenando actitud
    medida en n-frame magnético, corrección por declinación geomagnética y boresight:
        Cb2n = Cmn2gn(delta) @ Cs2n_mn(r,p,y) @ (Cs2b(alpha,beta,gamma))^T
    """
    r_ins = np.radians(ins_attitude_deg[0])
    p_ins = np.radians(ins_attitude_deg[1])
    y_ins = np.radians(ins_attitude_deg[2])
    Cs2n_mn = attitude_to_dcm(r_ins, p_ins, y_ins)

    decl_rad = np.radians(magnetic_declination_deg)
    Cmn2gn = magnetic_to_geodetic_north_matrix(decl_rad)

    a1_i, a2_i, a3_i = [np.radians(x) for x in boresight_deg]
    Cs2b_ins = sensor_to_body_matrix(a1_i, a2_i, a3_i)
    Cb2s_ins = Cs2b_ins.T

    Cb2n_ins = Cmn2gn @ (Cs2n_mn @ Cb2s_ins)
    Cb2n_ins = reorthonormalize_dcm(Cb2n_ins)

    a1_it, a2_it, a3_it = dcm_to_euler(Cb2n_ins)
    r_it, p_it, y_it = dcm_to_attitude(Cb2n_ins)

    euler_ins_deg = (float(np.degrees(a1_it)), float(np.degrees(a2_it)), float(np.degrees(a3_it)))
    attitude_ins_total_deg = (float(np.degrees(r_it)), float(np.degrees(p_it)), float(np.degrees(y_it)))

    return Cs2n_mn, Cmn2gn, Cs2b_ins, Cb2s_ins, Cb2n_ins, euler_ins_deg, attitude_ins_total_deg


def propagate_sensor_network(
    pla_ecef: np.ndarray,
    Cb2e: np.ndarray,
    devices_b: dict[str, np.ndarray],
    ell: Ellipsoid = GRS80,
    utm_zone: int = 30,
    utm_hemisphere: str = "N",
    geoid_undulation_N: float = 0.0
) -> dict[str, SensorResult]:
    """
    Paso 7: Propaga cinemáticamente las coordenadas de todos los sensores montados en el rig
    a partir de sus palancas de brazo (lever-arms) en b-frame hacia:
    1. ECEF (X, Y, Z)
    2. Geodésicas (phi, lambda, h_elip)
    3. Proyección UTM (Easting, Northing, Zone)
    4. Cota ortométrica H = h - N
    """
    results = {}
    for code, xb in devices_b.items():
        xe = propagate_lever_arm_ecef(pla_ecef, Cb2e, xb)
        lat_s, lon_s, h_s = ecef_to_geodetic(xe, ell)
        easting, northing, zone = utm_projection(lat_s, lon_s, zone=utm_zone, hemisphere=utm_hemisphere, ell=ell)
        h_orto = ellipsoidal_to_orthometric(h_s, geoid_undulation_N)
        results[code] = SensorResult(
            code=code, ecef=xe, lat_rad=lat_s, lon_rad=lon_s, h_ellip=h_s,
            easting=easting, northing=northing, zone=zone, h_orto=h_orto
        )
    return results


def compute_georef_residuals(
    gnss_ecef: dict[str, np.ndarray],
    pla_ecef: np.ndarray,
    Cb2e: np.ndarray,
    lever_arms_b: dict[str, np.ndarray],
    codes: list[str]
) -> dict[str, float]:
    """
    Paso 8: Calcula el residuo métrico tridimensional 3D (en metros) por antena:
        res_i = || r_obs_i^e - (r_pla^e + Cb2e @ lever_arm_i^b) ||
    """
    residuals_m = {}
    for code in codes:
        calc_e = propagate_lever_arm_ecef(pla_ecef, Cb2e, lever_arms_b[code])
        res_m = float(np.linalg.norm(gnss_ecef[code] - calc_e))
        residuals_m[code] = res_m
    return residuals_m


def compute_consistency_residuals(
    results_gnss: dict[str, SensorResult],
    results_ins: dict[str, SensorResult]
) -> dict[str, tuple[float, float, float]]:
    """
    Paso 9: Calcula las discrepancias métricas en proyección UTM y cota ortométrica
    (dE, dN, dH) entre la solución calculada vía constelación GNSS y vía sensor INS.
    """
    diff_utm = {}
    for code in results_gnss:
        if code in results_ins:
            res_g = results_gnss[code]
            res_i = results_ins[code]
            dE = res_g.easting - res_i.easting
            dN = res_g.northing - res_i.northing
            dH = res_g.h_orto - res_i.h_orto
            diff_utm[code] = (float(dE), float(dN), float(dH))
    return diff_utm


# =============================================================================
# Pipeline Matemático Puro Integrado
# =============================================================================

def solve_georeferencing_pipeline(
    gnss_observations: dict[str, tuple[float, float, float]],
    lever_arms_b: dict[str, np.ndarray],
    gnss_sensor_codes: list[str],
    ins_attitude_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ins_boresight_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    magnetic_declination_deg: float = -0.700,
    geoid_undulation_N: float = 50.0166,
    ellipsoid: Ellipsoid = GRS80,
    utm_zone: int = 30,
    utm_hemisphere: str = "N",
    reference_system: Any = None
) -> GeoreferencingSolution:
    """
    Pipeline matemático funcional y determinista que ejecuta la cadena completa
    de georreferenciación multipunto a partir de entradas numéricas puras.
    """
    # 1. Observaciones GNSS a ECEF
    gnss_ecef = gnss_observations_to_ecef(gnss_observations, ell=ellipsoid)

    # 2. Centroide de navegación
    centroid_ecef, lat_cent, lon_cent, h_cent, Ce2n_centroid = compute_navigation_centroid(
        gnss_ecef, codes=gnss_sensor_codes, ell=ellipsoid
    )

    # 3. Proyección al n-frame
    gnss_vectors_n = project_ecef_to_nframe(
        gnss_ecef, codes=gnss_sensor_codes, centroid_ecef=centroid_ecef, Ce2n_centroid=Ce2n_centroid
    )

    # 4. Orientación Cb2n por Kabsch SVD
    Cb2n_gnss, cent_b, _, euler_gnss_deg, attitude_gnss_deg, det_dcm, ortho_error_dcm = solve_attitude_kabsch(
        lever_arms_b=lever_arms_b, gnss_vectors_n=gnss_vectors_n, codes=gnss_sensor_codes
    )

    # 5. Origen PLA en ECEF y matriz compuesta Cb2e_1
    pla_ecef, lat_pla, lon_pla, h_pla, Cn2e_pla, Cb2e_1 = solve_pla_origin_ecef(
        centroid_ecef=centroid_ecef, cent_b=cent_b, Cb2n_gnss=Cb2n_gnss,
        lat_cent_rad=lat_cent, lon_cent_rad=lon_cent, ell=ellipsoid
    )

    # 6. Residuales métricos GNSS
    residuals_gnss_m = compute_georef_residuals(
        gnss_ecef=gnss_ecef, pla_ecef=pla_ecef, Cb2e=Cb2e_1,
        lever_arms_b=lever_arms_b, codes=gnss_sensor_codes
    )

    # 7. Dispositivos a propagar (sensores montados + punto centroide)
    all_devices_b = dict(lever_arms_b)
    all_devices_b["CENT"] = cent_b

    # 8. Propagación de red con actitud GNSS
    results_gnss = propagate_sensor_network(
        pla_ecef=pla_ecef, Cb2e=Cb2e_1, devices_b=all_devices_b,
        ell=ellipsoid, utm_zone=utm_zone, utm_hemisphere=utm_hemisphere,
        geoid_undulation_N=geoid_undulation_N
    )

    # 9. Orientación y rotaciones con sensor INS
    Cs2n_mn, Cmn2gn, Cs2b_ins, Cb2s_ins, Cb2n_ins, euler_ins_deg, attitude_ins_total_deg = solve_attitude_ins_chain(
        ins_attitude_deg=ins_attitude_deg,
        magnetic_declination_deg=magnetic_declination_deg,
        boresight_deg=ins_boresight_deg
    )

    Cb2e_ins = Cn2e_pla @ Cb2n_ins

    # 10. Propagación de red con actitud INS y consistencia
    results_ins = propagate_sensor_network(
        pla_ecef=pla_ecef, Cb2e=Cb2e_ins, devices_b=all_devices_b,
        ell=ellipsoid, utm_zone=utm_zone, utm_hemisphere=utm_hemisphere,
        geoid_undulation_N=geoid_undulation_N
    )

    diff_gnss_ins_utm = compute_consistency_residuals(results_gnss, results_ins)

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


# =============================================================================
# Fachada Compatible para Modelos POO (Platform, ReferenceSystem)
# =============================================================================

def solve_multisensor_georeferencing(
    platform: Any,
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
    Fachada compatible que recibe una entidad Platform y opcionalmente ReferenceSystem,
    extrae sus parámetros y observaciones en estructuras primitivas y ejecuta
    solve_georeferencing_pipeline garantizando paridad matemática total.
    """
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

    gnss_sensor_codes = validate_sensor_codes_and_obs(
        platform.sensors,
        gnss_observations,
        required_codes=gnss_sensor_codes
    )

    # Auto-detección de actitud INS y boresight
    ins_sensor = None
    if ins_sensor_code and ins_sensor_code in platform.sensors:
        ins_sensor = platform.sensors[ins_sensor_code]
    else:
        for s in platform.sensors.values():
            s_type_val = s.sensor_type.value if hasattr(s.sensor_type, "value") else str(s.sensor_type)
            if s_type_val == "INS" or s.code == "INS":
                ins_sensor = s
                break

    if ins_attitude_deg is None:
        if ins_sensor and ins_sensor.attitude_obs_deg is not None:
            ins_attitude_deg = ins_sensor.attitude_obs_deg
        else:
            ins_attitude_deg = (0.0, 0.0, 0.0)

    ins_boresight_deg = ins_sensor.boresight_deg if ins_sensor else (0.0, 0.0, 0.0)

    lever_arms_b = {code: s.lever_arm_b for code, s in platform.sensors.items()}

    return solve_georeferencing_pipeline(
        gnss_observations=gnss_observations,
        lever_arms_b=lever_arms_b,
        gnss_sensor_codes=gnss_sensor_codes,
        ins_attitude_deg=ins_attitude_deg,
        ins_boresight_deg=ins_boresight_deg,
        magnetic_declination_deg=magnetic_declination_deg,
        geoid_undulation_N=geoid_undulation_N,
        ellipsoid=ellipsoid,
        utm_zone=utm_zone,
        utm_hemisphere=utm_hemisphere,
        reference_system=reference_system
    )


def create_reference_platform() -> Any:
    """Crea la plataforma de calibración de referencia con los sensores del vehículo."""
    from .models import Platform, Sensor, SensorType
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
solve_reference_rig = solve_multisensor_georeferencing
create_default_reference_platform = create_reference_platform

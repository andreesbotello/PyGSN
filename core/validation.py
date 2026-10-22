"""
PyGSN - Core Validation Module
==============================
Utilidades centralizadas y desacopladas (DRY) para validación numérica,
comprobación de límites geodésicos y detección de geometrías degeneradas
o colineales en conjuntos de antenas e instrumentación.
"""

from typing import Any, Sequence, Mapping
import numpy as np


class ValidationError(ValueError):
    """Excepción base para fallos de validación numérica o geométrica en PyGSN."""
    pass


class CollinearGeometryError(ValidationError):
    """Se produce cuando la configuración geométrica de antenas es colineal o coincidente (rango < 2)."""
    pass


def validate_finite(val_or_arr: Any, name: str = "valor") -> np.ndarray:
    """
    Verifica que el valor o array sea estrictamente finito (sin NaN ni Inf).
    Retorna el array como np.ndarray float64.
    """
    arr = np.asarray(val_or_arr, dtype=np.float64)
    if not np.all(np.isfinite(arr)):
        raise ValidationError(f"El parámetro '{name}' contiene valores no finitos (NaN o Inf).")
    return arr


def validate_lat_lon(
    lat_rad: float | np.floating,
    lon_rad: float | np.floating,
    allow_polar: bool = True
) -> tuple[np.float64, np.float64]:
    """
    Verifica que la latitud y longitud geodésicas en radianes estén dentro de límites físicos:
    - Latitud en [-pi/2, pi/2]
    - Longitud finita
    """
    phi = np.float64(lat_rad)
    lam = np.float64(lon_rad)

    if not (np.isfinite(phi) and np.isfinite(lam)):
        raise ValidationError("Las coordenadas geodésicas (latitud, longitud) deben ser valores finitos.")

    half_pi = np.pi / 2.0
    tol = 1e-12
    if phi < -half_pi - tol or phi > half_pi + tol:
        raise ValidationError(
            f"Latitud fuera del rango físico [-pi/2, pi/2] rad: {phi:.8f} rad "
            f"({np.degrees(phi):.4f} deg)."
        )

    if not allow_polar and np.abs(np.abs(phi) - half_pi) < 1e-7:
        raise ValidationError("La coordenada se encuentra en el polo geográfico (singularidad polar).")

    # Normalizar longitud a [-pi, pi]
    lam_norm = np.arctan2(np.sin(lam), np.cos(lam))
    return np.clip(phi, -half_pi, half_pi), np.float64(lam_norm)


def validate_utm_params(zone: int, hemisphere: str = "N") -> tuple[int, str]:
    """
    Verifica que los parámetros de proyección UTM sean válidos:
    - Huso (zone): entero entre 1 y 60.
    - Hemisferio: 'N' o 'S' (case-insensitive).
    """
    try:
        z = int(zone)
    except (ValueError, TypeError):
        raise ValidationError(f"El huso UTM debe ser un número entero (dado: {zone}).")

    if z < 1 or z > 60:
        raise ValidationError(f"El huso UTM debe estar comprendido entre 1 y 60 (dado: {z}).")

    hemi = str(hemisphere).strip().upper()
    if hemi not in ("N", "S"):
        raise ValidationError(f"El hemisferio UTM debe ser 'N' (Norte) o 'S' (Sur), dado: '{hemisphere}'.")

    return z, hemi


def validate_antenna_geometry(
    points_b: np.ndarray,
    min_points: int = 3,
    collinear_tol: float = 1e-5
) -> np.ndarray:
    """
    Verifica que un conjunto de puntos (lever arms en b-frame o vectores n-frame) cumpla
    los requisitos algebraicos para la determinación de actitud 3D (Kabsch / Procrustes):
    1. Finitud completa.
    2. Al menos `min_points` puntos.
    3. Rango de la matriz centrada >= 2 (no coincidentes ni colineales).

    Parámetros:
        points_b: Matriz de coordenadas (3, N) o (N, 3).
        min_points: Mínimo de puntos requeridos (por defecto 3).
        collinear_tol: Tolerancia relativa para el segundo valor singular respecto al primero.

    Retorna:
        Matriz con dimensiones garantizadas (3, N) de tipo float64.
    """
    pts = validate_finite(points_b, name="puntos_antenas")

    if pts.ndim != 2:
        raise ValidationError(f"El array de puntos debe tener 2 dimensiones (dado shape: {pts.shape}).")

    # Estandarizar a (3, N)
    if pts.shape[0] != 3 and pts.shape[1] == 3:
        pts = pts.T
    elif pts.shape[0] != 3:
        raise ValidationError(f"Las coordenadas deben ser tridimensionales (3, N) o (N, 3), dado: {pts.shape}.")

    n_points = pts.shape[1]
    if n_points < min_points:
        raise ValidationError(
            f"Se requieren al menos {min_points} antenas para determinar la orientación 3D (dados: {n_points})."
        )

    # Centroide y centrado
    centroid = np.mean(pts, axis=1, keepdims=True)
    centered = pts - centroid

    # Evaluación de valores singulares de la geometría centrada
    s = np.linalg.svd(centered, compute_uv=False)
    s_max = float(s[0]) if len(s) > 0 else 0.0

    if s_max < 1e-9:
        raise CollinearGeometryError(
            "Configuración geométrica degenerada: todos los puntos son idénticos o coincidentes (rango 0)."
        )

    # Segundo valor singular s[1] determina si los puntos abarcan un plano 2D
    s_mid = float(s[1]) if len(s) > 1 else 0.0
    if (s_mid / s_max) < collinear_tol or s_mid < 1e-8:
        raise CollinearGeometryError(
            f"Configuración de antenas colineal o degenerada (rango efectivo 1, s2/s1 = {s_mid/max(s_max, 1e-12):.2e}). "
            "Los puntos se encuentran alineados sobre una recta; la actitud 3D es indeterminada "
            "(el ángulo de rotación sobre el eje de las antenas no es observable)."
        )

    return pts


def validate_sensor_codes_and_obs(
    platform_sensors: Mapping[str, Any],
    gnss_observations: Mapping[str, Sequence[float]],
    required_codes: Sequence[str] | None = None
) -> list[str]:
    """
    Valida la coherencia entre los sensores registrados en la plataforma y las observaciones GNSS.
    Retorna la lista ordenada de códigos de antenas validadas para el ajuste.
    """
    if required_codes is not None:
        codes = list(required_codes)
        if len(codes) < 3:
            raise ValidationError(
                f"Se requieren al menos 3 códigos de antena para el solver GNSS (especificados: {len(codes)})."
            )
        missing_plat = [c for c in codes if c not in platform_sensors]
        if missing_plat:
            raise ValidationError(
                f"Las siguientes antenas solicitadas no existen en la plataforma: {missing_plat}"
            )
        missing_obs = [c for c in codes if c not in gnss_observations]
        if missing_obs:
            raise ValidationError(
                f"Las siguientes antenas carecen de observaciones de campo: {missing_obs}"
            )
    else:
        # Auto-detección: intersección entre sensores y observaciones
        codes = [c for c in gnss_observations.keys() if c in platform_sensors]
        if len(codes) < 3:
            raise ValidationError(
                f"Se requieren al menos 3 antenas GNSS coincidentes entre la plataforma y las observaciones "
                f"(encontradas: {len(codes)}: {codes})."
            )

    # Validar que las observaciones contengan coordenadas finitas
    for c in codes:
        obs = gnss_observations[c]
        if len(obs) < 3:
            raise ValidationError(f"La observación de la antena '{c}' debe contener [lat, lon, h] (tiene {len(obs)}).")
        validate_finite(obs, name=f"observación {c}")
        validate_lat_lon(obs[0], obs[1])

    return codes

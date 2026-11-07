"""
PyGSN - Core Kinematics Module
==============================
Operaciones matemáticas puras de cinemática de navegación, transformación
de palancas de brazo (lever-arms) y geometría métrica 2D/3D de plataformas.

Funciones 100% deterministas y agnósticas de clases POO (reciben y retornan
tipos primitivos de NumPy y float64).
"""

from typing import Any
import numpy as np

from .geodesy import GRS80, Ellipsoid, radii_of_curvature
from .validation import validate_finite, validate_safe_division


def propagate_lever_arm_ecef(
    r_origin_e: np.ndarray,
    Cb2e: np.ndarray,
    lever_arm_b: np.ndarray
) -> np.ndarray:
    """
    Propaga la posición de un sensor montado en la plataforma a coordenadas
    cartesianas ECEF (e-frame) a partir de su palanca de brazo (lever-arm) en b-frame.

    Ecuación cinemática rígida (Groves Ec. 2.115):
        r_sens^e = r_origin^e + C_b^e @ lever_arm^b

    Parámetros:
        r_origin_e: Vector de posición del origen de plataforma en ECEF [m], shape (3,).
        Cb2e: Matriz de rotación (DCM) del b-frame al e-frame, shape (3, 3).
        lever_arm_b: Vector palanca de brazo [xb, yb, zb] en b-frame [m], shape (3,) o (3, N).

    Retorna:
        Vector(es) de posición del sensor en ECEF [m], shape (3,) o (3, N) en np.float64.
    """
    r_orig = validate_finite(r_origin_e, name="r_origin_e")
    dcm = validate_finite(Cb2e, name="Cb2e")
    arm = validate_finite(lever_arm_b, name="lever_arm_b")

    if dcm.shape != (3, 3):
        raise ValueError(f"La matriz Cb2e debe tener dimensiones (3, 3), dado: {dcm.shape}")

    if arm.ndim == 1:
        if arm.shape[0] != 3:
            raise ValueError(f"El lever_arm_b debe tener longitud 3, dado: {arm.shape}")
        return np.float64(r_orig + dcm @ arm)
    elif arm.ndim == 2:
        if arm.shape[0] != 3 and arm.shape[1] == 3:
            arm = arm.T
        if arm.shape[0] != 3:
            raise ValueError(f"El array de lever_arms debe tener 3 filas, dado: {arm.shape}")
        return np.float64(r_orig[:, np.newaxis] + dcm @ arm)
    else:
        raise ValueError(f"Dimensiones de lever_arm_b inválidas: {arm.shape}")


def solve_origin_from_centroid_ecef(
    centroid_e: np.ndarray,
    cent_b: np.ndarray,
    Cb2e: np.ndarray
) -> np.ndarray:
    """
    Calcula la posición cartesiana ECEF del origen de la plataforma (PLA)
    a partir del centroide de antenas en ECEF, el centroide en b-frame y la matriz Cb2e.

    Ecuación:
        r_pla^e = r_cent^e - C_b^e @ bar_x^b

    Parámetros:
        centroid_e: Centroide de la constelación de antenas en ECEF [m], shape (3,).
        cent_b: Centroide de las antenas en b-frame [m], shape (3,).
        Cb2e: Matriz de transformación del b-frame al e-frame, shape (3, 3).

    Retorna:
        Vector ECEF del origen de la plataforma [m], shape (3,) en np.float64.
    """
    c_e = validate_finite(centroid_e, name="centroid_e")
    c_b = validate_finite(cent_b, name="cent_b")
    dcm = validate_finite(Cb2e, name="Cb2e")

    return np.float64(c_e - dcm @ c_b)


def geodetic_navigation_rates(
    v_n: np.ndarray,
    lat_rad: float | np.floating,
    h_m: float | np.floating,
    ell: Ellipsoid = GRS80
) -> tuple[np.float64, np.float64, np.float64]:
    """
    Calcula las tasas de variación temporal geodésicas (dot_phi, dot_lambda, dot_h)
    a partir del vector de velocidad en n-frame (NED).

    Ecuaciones de mecanización inercial (Groves Ec. 5.44 / Jekeli Ec. 1.85):
        dot_phi    = v_N / (R_m + h)
        dot_lambda = v_E / ((R_n + h) * cos(phi))
        dot_h      = -v_D = v_U

    Parámetros:
        v_n: Vector de velocidad en n-frame NED [v_N, v_E, v_D] [m/s], shape (3,).
        lat_rad: Latitud geodésica actual [rad].
        h_m: Altitud elipsoidal actual [m].
        ell: Elipsoide de referencia (por defecto GRS80).

    Retorna:
        (dot_lat, dot_lon, dot_h):
            dot_lat: Tasa de cambio de latitud [rad/s]
            dot_lon: Tasa de cambio de longitud [rad/s]
            dot_h:   Tasa de cambio de altitud elipsoidal [m/s]
    """
    vel = validate_finite(v_n, name="v_n")
    phi = np.float64(lat_rad)
    h = np.float64(h_m)

    Rm, Rn = radii_of_curvature(phi, ell)

    dlat = vel[0] / (Rm + h)
    cos_phi = np.cos(phi)

    # Protección polar mediante validate_safe_division
    denom_lon = (Rn + h) * cos_phi
    dlon = validate_safe_division(vel[1], denom_lon, eps=1e-12, default=0.0)
    dh = -vel[2]

    return np.float64(dlat), np.float64(dlon), np.float64(dh)


def rotate_polygon_2d(
    points_2d: np.ndarray | list[list[float]],
    angle_deg: float,
    center_2d: np.ndarray | list[float] | None = None
) -> np.ndarray:
    """
    Aplica una rotación en el plano métrico 2D a un polígono o conjunto de puntos.

    Parámetros:
        points_2d: Puntos 2D [[x1, y1], [x2, y2], ...] de shape (N, 2).
        angle_deg: Ángulo de rotación en grados (antihorario positivo).
        center_2d: Centro de rotación [cx, cy]. Si es None, utiliza el centroide de points_2d.

    Retorna:
        np.ndarray de shape (N, 2) con los puntos rotados (redondeados a 4 decimales).
    """
    pts = np.asarray(points_2d, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError(f"Los puntos 2D deben tener forma (N, 2), dado: {pts.shape}")

    if center_2d is None:
        c = np.mean(pts, axis=0)
    else:
        c = np.asarray(center_2d, dtype=np.float64)

    rad = np.radians(angle_deg)
    cos_a = np.cos(rad)
    sin_a = np.sin(rad)
    rot_mat = np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=np.float64)

    rel = pts - c
    rotated_rel = rel @ rot_mat.T
    rotated_pts = rotated_rel + c

    return np.round(rotated_pts, decimals=4)


def scale_polygon_2d(
    points_2d: np.ndarray | list[list[float]],
    factor_x: float,
    factor_y: float,
    center_2d: np.ndarray | list[float] | None = None
) -> np.ndarray:
    """
    Aplica un escalado paramétrico a un polígono 2D respecto a un centroide.

    Parámetros:
        points_2d: Puntos 2D [[x1, y1], ...] de shape (N, 2).
        factor_x: Factor multiplicativo en el eje X (> 0).
        factor_y: Factor multiplicativo en el eje Y (> 0).
        center_2d: Centroide de referencia [cx, cy]. Si es None, calcula el centroide.

    Retorna:
        np.ndarray de shape (N, 2) con los puntos escalados (redondeados a 4 decimales).
    """
    pts = np.asarray(points_2d, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError(f"Los puntos 2D deben tener forma (N, 2), dado: {pts.shape}")

    if center_2d is None:
        c = np.mean(pts, axis=0)
    else:
        c = np.asarray(center_2d, dtype=np.float64)

    rel = pts - c
    scaled_rel = rel * np.array([factor_x, factor_y], dtype=np.float64)
    scaled_pts = scaled_rel + c

    return np.round(scaled_pts, decimals=4)


def compute_polygon_2d_bounds(points_2d: np.ndarray | list[list[float]]) -> dict[str, float]:
    """
    Calcula los límites métricos envolventes y dimensiones de un polígono 2D.

    Retorna:
        dict con: x_min, x_max, y_min, y_max, length_m, width_m, center_x, center_y.
    """
    pts = np.asarray(points_2d, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError(f"Los puntos 2D deben tener forma (N, 2), dado: {pts.shape}")

    x_min = float(np.min(pts[:, 0]))
    x_max = float(np.max(pts[:, 0]))
    y_min = float(np.min(pts[:, 1]))
    y_max = float(np.max(pts[:, 1]))

    return {
        "x_min": round(x_min, 4),
        "x_max": round(x_max, 4),
        "y_min": round(y_min, 4),
        "y_max": round(y_max, 4),
        "length_m": round(x_max - x_min, 4),
        "width_m": round(y_max - y_min, 4),
        "center_x": round((x_min + x_max) / 2.0, 4),
        "center_y": round((y_min + y_max) / 2.0, 4),
    }


def compute_utm_bounding_box_points(
    origin_utm: tuple[float, float],
    heading_grid_rad: float,
    b_points_2d: np.ndarray | list[list[float]]
) -> dict[str, float]:
    """
    Calcula la caja envolvente mínima orientada al Norte cuadrícula (Bounding Box)
    en coordenadas proyectadas UTM (Easting, Northing) para un conjunto de puntos en b-frame.

    Ecuación de proyección de orientación de cuadrícula:
        E_i = E_0 + x_b * sin(psi_grid) + y_b * cos(psi_grid)
        N_i = N_0 + x_b * cos(psi_grid) - y_b * sin(psi_grid)

    Parámetros:
        origin_utm: Coordenadas (Easting, Northing) del origen [m].
        heading_grid_rad: Rumbo de cuadrícula (Heading Grid = Yaw - gamma) [rad].
        b_points_2d: Puntos [[xb, yb], ...] en el plano b-frame [m], shape (N, 2).

    Retorna:
        dict con: min_e, max_e, min_n, max_n, span_e, span_n, center_e, center_n.
    """
    pts = np.asarray(b_points_2d, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError(f"Los puntos en b-frame deben tener forma (N, 2), dado: {pts.shape}")

    e0, n0 = origin_utm
    sin_psi = np.sin(heading_grid_rad)
    cos_psi = np.cos(heading_grid_rad)

    xb = pts[:, 0]
    yb = pts[:, 1]

    e_pts = e0 + xb * sin_psi + yb * cos_psi
    n_pts = n0 + xb * cos_psi - yb * sin_psi

    min_e = float(np.min(e_pts))
    max_e = float(np.max(e_pts))
    min_n = float(np.min(n_pts))
    max_n = float(np.max(n_pts))

    return {
        "min_e": round(min_e, 4),
        "max_e": round(max_e, 4),
        "min_n": round(min_n, 4),
        "max_n": round(max_n, 4),
        "span_e": round(max_e - min_e, 4),
        "span_n": round(max_n - min_n, 4),
        "center_e": round((min_e + max_e) / 2.0, 4),
        "center_n": round((min_n + max_n) / 2.0, 4),
    }


def translate_points_3d(
    points_3d: np.ndarray | list[list[float]],
    dx: float,
    dy: float,
    dz: float = 0.0
) -> np.ndarray:
    """
    Traslada un conjunto de puntos 3D por un vector delta métrico [dx, dy, dz].
    """
    pts = np.asarray(points_3d, dtype=np.float64)
    delta = np.array([dx, dy, dz], dtype=np.float64)
    translated = pts + delta
    return np.round(translated, decimals=4)

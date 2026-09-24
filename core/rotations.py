"""
PyGSN - Core Rotations Module
=============================
Definicion de transformaciones y matrices de rotacion conforme a la
convencion del curso GSN (Jekeli Cap. 1, Hoffman, GeoTop).

- Matrices de rotacion elementales R1, R2, R3 (pasivas)
- Matriz Ce2n y Cn2e (de e-frame ECEF a n-frame NED y viceversa)
- Matriz Cb2n a partir de actitud (roll, pitch, yaw)
- Extraccion de angulos de Euler y actitud (r, p, y) con proteccion contra Gimbal Lock
- Matriz de desalineamiento de sensor Cs2b a partir de (alpha, beta, gamma)
- Correccion por declinacion magnetica Cmn2gn
- Re-ortonormalizacion de DCM mediante SVD / Polar
"""

import numpy as np


def R1(angle_rad: np.float64) -> np.ndarray:
    """
    Matriz de rotacion elemental sobre el eje 1 (X) [Pasiva].
    R1(a) = [[1,  0,       0     ],
             [0,  cos(a),  sin(a)],
             [0, -sin(a),  cos(a)]]
    """
    c = np.cos(angle_rad)
    s = np.sin(angle_rad)
    return np.array([
        [1.0, 0.0, 0.0],
        [0.0, c,   s],
        [0.0, -s,  c]
    ], dtype=np.float64)


def R2(angle_rad: np.float64) -> np.ndarray:
    """
    Matriz de rotacion elemental sobre el eje 2 (Y) [Pasiva].
    R2(a) = [[ cos(a), 0, -sin(a)],
             [ 0,      1,  0     ],
             [ sin(a), 0,  cos(a)]]
    """
    c = np.cos(angle_rad)
    s = np.sin(angle_rad)
    return np.array([
        [c,   0.0, -s],
        [0.0, 1.0, 0.0],
        [s,   0.0, c]
    ], dtype=np.float64)


def R3(angle_rad: np.float64) -> np.ndarray:
    """
    Matriz de rotacion elemental sobre el eje 3 (Z) [Pasiva].
    R3(a) = [[ cos(a), sin(a), 0],
             [-sin(a), cos(a), 0],
             [ 0,      0,      1]]
    """
    c = np.cos(angle_rad)
    s = np.sin(angle_rad)
    return np.array([
        [c,   s,   0.0],
        [-s,  c,   0.0],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)


def e_to_n_matrix(lat_rad: np.float64, lon_rad: np.float64) -> np.ndarray:
    """
    Matriz de rotacion Ce2n del e-frame (ECEF) al n-frame (NED local).
    Ce2n = [[-sin(lat)*cos(lon), -sin(lat)*sin(lon),  cos(lat)],
            [-sin(lon),           cos(lon),           0       ],
            [-cos(lat)*cos(lon), -cos(lat)*sin(lon), -sin(lat)]]
    """
    s_lat = np.sin(lat_rad)
    c_lat = np.cos(lat_rad)
    s_lon = np.sin(lon_rad)
    c_lon = np.cos(lon_rad)

    return np.array([
        [-s_lat * c_lon, -s_lat * s_lon,  c_lat],
        [-s_lon,          c_lon,          0.0],
        [-c_lat * c_lon, -c_lat * s_lon, -s_lat]
    ], dtype=np.float64)


def n_to_e_matrix(lat_rad: np.float64, lon_rad: np.float64) -> np.ndarray:
    """
    Matriz de rotacion Cn2e del n-frame (NED local) al e-frame (ECEF).
    Cn2e = (Ce2n)^T
    """
    return e_to_n_matrix(lat_rad, lon_rad).T


def euler_to_dcm(a1: np.float64, a2: np.float64, a3: np.float64) -> np.ndarray:
    """
    Construye una matriz DCM segun la secuencia estandar de Euler:
    C = R3(a3) @ R2(a2) @ R1(a1)
    """
    return R3(a3) @ (R2(a2) @ R1(a1))


def attitude_to_dcm(roll_rad: np.float64, pitch_rad: np.float64, yaw_rad: np.float64) -> np.ndarray:
    """
    Construye la matriz de rotacion Cb2n (del b-frame al n-frame) a partir
    de la actitud (roll, pitch, yaw) segun la convencion Jekeli (eq. 1.90) / Hoffman:
    Cb2n = R3(-yaw) @ R2(-pitch) @ R1(-roll)
    """
    return R3(-yaw_rad) @ (R2(-pitch_rad) @ R1(-roll_rad))


def dcm_to_euler(C: np.ndarray) -> tuple[np.float64, np.float64, np.float64]:
    """
    Extrae los angulos de Euler (a1, a2, a3) de una DCM que sigue:
    C = R3(a3) @ R2(a2) @ R1(a1)

    Protegido contra Gimbal Lock (|sin(a2)| -> 1).
    """
    sin_a2 = np.clip(C[2, 0], -1.0, 1.0)
    a2 = np.arcsin(sin_a2)
    cos_a2 = np.cos(a2)

    if np.abs(cos_a2) > 1e-10:
        a1 = np.arctan2(-C[2, 1], C[2, 2])
        a3 = np.arctan2(-C[1, 0], C[0, 0])
    else:
        # Singularidad de Gimbal Lock
        a1 = np.float64(0.0)
        a3 = np.arctan2(C[0, 1], C[1, 1])

    return a1, a2, a3


def dcm_to_attitude(Cb2n: np.ndarray) -> tuple[np.float64, np.float64, np.float64]:
    """
    Extrae la actitud de navegacion (roll, pitch, yaw) en radianes a partir de Cb2n:
    roll  = -a1
    pitch = -a2
    yaw   = -a3 (en rango [0, 2pi))
    """
    a1, a2, a3 = dcm_to_euler(Cb2n)
    roll = -a1
    pitch = -a2
    yaw = -a3
    if yaw < 0.0:
        yaw += np.float64(2.0 * np.pi)

    return roll, pitch, yaw


def sensor_to_body_matrix(alpha_rad: np.float64, beta_rad: np.float64, gamma_rad: np.float64) -> np.ndarray:
    """
    Calcula la matriz de desalineamiento / rotacion Cs2b (de s-frame a b-frame):
    Cs2b = R3(gamma) @ R2(beta) @ R1(alpha)
    """
    return R3(gamma_rad) @ (R2(beta_rad) @ R1(alpha_rad))


def body_to_sensor_matrix(alpha_rad: np.float64, beta_rad: np.float64, gamma_rad: np.float64) -> np.ndarray:
    """
    Calcula la matriz de rotacion Cb2s (de b-frame a s-frame):
    Cb2s = (Cs2b)^T
    """
    return sensor_to_body_matrix(alpha_rad, beta_rad, gamma_rad).T


def magnetic_to_geodetic_north_matrix(declination_rad: np.float64) -> np.ndarray:
    """
    Matriz de rotacion Cmn2gn del n-frame orientado a Norte Magnetico
    al n-frame orientado a Norte Geodesico:
    Cmn2gn = R3(declination)
    """
    return R3(declination_rad)


def reorthonormalize_dcm(C: np.ndarray) -> np.ndarray:
    """
    Re-ortonormaliza una matriz de rotacion 3x3 usando Descomposicion en Valores Singulares (SVD).
    Garantiza C^T @ C = I y det(C) = +1.
    """
    U, _, Vt = np.linalg.svd(C)
    R = U @ Vt
    # Asegurar determinante +1 (rotacion propia, no reflexion)
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Vt
    return R

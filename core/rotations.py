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
    C = R3(a3) @ R2(a2) @ R1(a1)   (R1, R2, R3 pasivas)

    ADVERTENCIA: euler_to_dcm(roll, pitch, yaw) NO es Cb2n. Con rotaciones pasivas,
    Cb2n = R3(-yaw) R2(-pitch) R1(-roll): usar attitude_to_dcm(roll, pitch, yaw).
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
    a2 se extrae con atan2(C20, hypot(C21, C22)) en lugar de arcsin(C20): es exacto
    cerca de +-90 deg (arcsin esta mal condicionado alli) y no necesita recorte [-1, 1].
    """
    cos_a2 = np.hypot(C[2, 1], C[2, 2])
    a2 = np.arctan2(C[2, 0], cos_a2)

    if cos_a2 > 1e-10:
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
    al n-frame orientado a Norte Geodesico.

    Convencion IGRF/WMM (Groves Sec. 6.1.1): la declinacion D es el rumbo del Norte
    magnetico medido desde el Norte geodesico, positiva hacia el Este. Por tanto:
        psi_geodesico = psi_magnetico + D
        Cmn2gn = R3(-D)        (R3 pasiva)

    Parametros:
        declination_rad: Declinacion magnetica D [rad], Este positivo.
    """
    return R3(-np.float64(declination_rad))


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


def chain_ins_attitude_matrix(
    roll_rad: float | np.floating,
    pitch_rad: float | np.floating,
    yaw_rad: float | np.floating,
    declination_rad: float | np.floating = 0.0,
    alpha_rad: float | np.floating = 0.0,
    beta_rad: float | np.floating = 0.0,
    gamma_rad: float | np.floating = 0.0
) -> np.ndarray:
    """
    Construye la matriz de rotación Cb2n total del vehículo estimada por el sensor INS,
    encadenando la actitud observada en el marco magnético local, la corrección por declinación
    geomagnética hacia el Norte geodésico, y el desalineamiento angular (boresight) de montaje:

    Ecuación (Groves Cap. 5):
        Cb2n = Cmn2gn(D) @ Cs2n_mn(roll, pitch, yaw) @ (Cs2b(alpha, beta, gamma))^T
        Cmn2gn(D) = R3(-D)

    Parámetros:
        roll_rad, pitch_rad, yaw_rad: Ángulos de actitud observados por la IMU/INS [rad].
        declination_rad: Declinación magnética D del lugar [rad], convención IGRF (Este positivo).
        alpha_rad, beta_rad, gamma_rad: Ángulos de boresight de calibración del sensor [rad].

    Retorna:
        Matriz Cb2n de rotación del vehículo (b-frame) al marco de navegación (n-frame) [3x3].
    """
    Cs2n_mn = attitude_to_dcm(np.float64(roll_rad), np.float64(pitch_rad), np.float64(yaw_rad))
    Cmn2gn = magnetic_to_geodetic_north_matrix(np.float64(declination_rad))
    Cs2b = sensor_to_body_matrix(np.float64(alpha_rad), np.float64(beta_rad), np.float64(gamma_rad))
    Cb2s = Cs2b.T

    Cb2n = Cmn2gn @ (Cs2n_mn @ Cb2s)
    return reorthonormalize_dcm(Cb2n)


def audit_dcm_condition(C: np.ndarray) -> tuple[float, float]:
    """
    Audita la condición matemática de una matriz de cosenos directores (DCM) 3x3.

    Retorna:
        (det_val, ortho_error):
            det_val: Determinante de la matriz (esperado exacto +1.0).
            ortho_error: Error de ortogonalidad norma Frobenius ||C @ C^T - I_3||_F.
    """
    arr = np.asarray(C, dtype=np.float64)
    if arr.shape != (3, 3):
        raise ValueError(f"La matriz debe ser 3x3 para auditar condición DCM, dado: {arr.shape}")

    det_val = float(np.linalg.det(arr))
    ortho_error = float(np.linalg.norm(arr @ arr.T - np.eye(3, dtype=np.float64)))
    return det_val, ortho_error


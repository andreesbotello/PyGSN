"""
PyGSN - Core Alignment Module
=============================
Resolucion de la orientacion y actitud relativa entre marcos
mediante el problema de Procrustes Ortogonal (Algoritmo de Kabsch / SVD).
"""

import numpy as np


def compute_centroid_3d(points: np.ndarray) -> np.ndarray:
    """
    Calcula el centroide baricéntrico métrico de un conjunto de puntos 3D.

    Parámetros:
        points: Coordenadas (3, N) o (N, 3).

    Retorna:
        Vector del centroide [cx, cy, cz] de shape (3,) en float64.
    """
    from .validation import validate_finite
    pts = validate_finite(points, name="points")
    if pts.ndim != 2:
        raise ValueError(f"Los puntos deben tener 2 dimensiones, dado: {pts.shape}")
    if pts.shape[0] != 3 and pts.shape[1] == 3:
        pts = pts.T
    return np.float64(np.mean(pts, axis=1))


def reduce_to_centroid_3d(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Reduce un conjunto de puntos 3D a su centroide baricéntrico.

    Retorna:
        (centered_points, centroid):
            centered_points: Puntos reducidos de shape (3, N) en float64.
            centroid: Vector del centroide de shape (3,) en float64.
    """
    from .validation import validate_finite
    pts = validate_finite(points, name="points")
    if pts.ndim != 2:
        raise ValueError(f"Los puntos deben tener 2 dimensiones, dado: {pts.shape}")
    if pts.shape[0] != 3 and pts.shape[1] == 3:
        pts = pts.T
    centroid = np.mean(pts, axis=1, keepdims=True)
    centered = pts - centroid
    return np.float64(centered), np.float64(centroid.ravel())


def kabsch_orthogonal_procrustes(
    points_from: np.ndarray,
    points_to: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Determina la matriz de rotacion R optima (3x3) tal que:
        points_to ≈ R @ points_from

    Parametros:
        points_from: Coordenadas de los puntos en el marco origen (3, N) o (N, 3).
        points_to:   Coordenadas de los puntos en el marco destino (3, N) o (N, 3).

    Retorna:
        (R, centroid_from, centroid_to, residuals):
            R: Matriz de rotacion propia (det = +1) de shape (3, 3)
            centroid_from: Centroide del marco origen (3,)
            centroid_to:   Centroide del marco destino (3,)
            residuals:     Residuales de ajuste (3, N)
    """
    from .validation import validate_antenna_geometry

    # Validar finitud, dimensión y rango no colineal (rango >= 2)
    pts_from = validate_antenna_geometry(points_from, min_points=3)
    pts_to = validate_antenna_geometry(points_to, min_points=3)

    if pts_from.shape != pts_to.shape:
        raise ValueError(f"Las dimensiones de los puntos no coinciden: {pts_from.shape} vs {pts_to.shape}")

    n_points = pts_from.shape[1]

    # Centroides
    centroid_from = np.mean(pts_from, axis=1, keepdims=True)
    centroid_to = np.mean(pts_to, axis=1, keepdims=True)

    # Traslacion a los respectivos centroides
    frx = pts_from - centroid_from
    tox = pts_to - centroid_to

    # Matriz de covarianza cruzada H = tox @ frx^T (3x3)
    H = tox @ frx.T

    # Descomposicion SVD
    U, _, Vt = np.linalg.svd(H)

    # Matriz de rotacion
    R = U @ Vt

    # Proteccion contra reflexion (det(R) debe ser +1 para rotacion fisica)
    det_R = np.linalg.det(R)
    if det_R < 0.0:
        U_mod = U.copy()
        U_mod[:, -1] *= -1.0
        R = U_mod @ Vt

    # Calculo de residuales: e = tox - R @ frx
    fitted = R @ frx
    residuals = tox - fitted

    return R, centroid_from.ravel(), centroid_to.ravel(), residuals

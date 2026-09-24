"""
PyGSN - Core Alignment Module
=============================
Resolucion de la orientacion y actitud relativa entre marcos
mediante el problema de Procrustes Ortogonal (Algoritmo de Kabsch / SVD).
"""

import numpy as np


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
    pts_from = np.asarray(points_from, dtype=np.float64)
    pts_to = np.asarray(points_to, dtype=np.float64)

    # Asegurar shape (3, N)
    if pts_from.shape[0] != 3 and pts_from.shape[1] == 3:
        pts_from = pts_from.T
    if pts_to.shape[0] != 3 and pts_to.shape[1] == 3:
        pts_to = pts_to.T

    if pts_from.shape != pts_to.shape:
        raise ValueError(f"Las dimensiones de los puntos no coinciden: {pts_from.shape} vs {pts_to.shape}")

    n_points = pts_from.shape[1]
    if n_points < 3:
        raise ValueError(f"Se requieren al menos 3 puntos no colineales para determinar la orientacion 3D (dados: {n_points})")

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

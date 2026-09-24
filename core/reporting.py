"""
PyGSN - Reporting Module
========================
Generador de informes y ficheros de texto (.txt) del procesamiento paso a paso
para la entrega academica de la Practica 1 (Georreferenciacion de Sensores y Navegacion, UPV).
"""

from datetime import datetime
import numpy as np
from .solver_p1 import P1Solution
from .geodesy import rad_to_dms, radii_of_curvature


def format_matrix_3x3(M: np.ndarray, indent: str = "   ") -> str:
    lines = []
    for r in range(3):
        lines.append(f"{indent}{M[r, 0]:16.10f}  {M[r, 1]:16.10f}  {M[r, 2]:16.10f}")
    return "\n".join(lines)


def generate_p1_full_txt_report(
    sol: P1Solution,
    student_name: str = "Bryan Andres Botello",
    student_id: str = "GSN-2026",
    group: str = "S3-UPV"
) -> str:
    """
    Genera el informe de texto completo paso a paso que cubre Punto 1, Punto 2a y Punto 2b.
    """
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    ell = sol.ellipsoid

    doc = []
    doc.append("=" * 90)
    doc.append("UNIVERSITAT POLITÈCNICA DE VALÈNCIA - MÁSTER EN GEOMÁTICA Y NAVEGACIÓN")
    doc.append("SISTEMAS DE NAVEGACIÓN (S3) - GEORREFERENCIACIÓN DE SENSORES")
    doc.append("PRÁCTICA 1: TRANSFORMACIÓN DE SISTEMAS DE COORDENADAS Y GEORREFERENCIACIÓN DE SENSORES")
    doc.append("=" * 90)
    doc.append(f"Estudiante: {student_name}")
    doc.append(f"ID / Grupo: {student_id} | {group}")
    doc.append(f"Fecha de Ejecución: {now_str}")
    doc.append(f"Elipsoide de Referencia: {ell.name} (a = {ell.a:.4f} m, 1/f = {ell.inv_f:.12f})")
    doc.append(f"Ondulación del Geoide (N): {sol.geoid_undulation_N:.4f} m")
    doc.append(f"Declinación Magnética: {sol.magnetic_declination_deg:+.4f} deg")
    doc.append("-" * 90)
    doc.append("")

    # =========================================================================
    # PUNTO 1
    # =========================================================================
    doc.append("=" * 90)
    doc.append("PUNTO 1: DETERMINACIÓN DE LA ORIENTACIÓN Y CENTRO DE LA PLATAFORMA (GNSS)")
    doc.append("=" * 90)
    doc.append("1.1. Coordenadas Geodésicas Observadas por los Receptores GNSS (ETRS89):")
    doc.append("   Sensor        Latitud            Longitud         h.elip(m)   Código")
    doc.append("   ------   -----------------   -----------------   -----------  ------")
    for code in ["REC2", "REC3", "REC4", "REC5"]:
        xe = sol.gnss_ecef[code]
        # Recuperamos geodesicas originales
        from .geodesy import ecef_to_geodetic
        lat, lon, h = ecef_to_geodetic(xe, ell)
        _, _, _, lat_str = rad_to_dms(lat)
        _, _, _, lon_str = rad_to_dms(lon)
        doc.append(f"      -     {lat_str:>17s}   {lon_str:>17s}   {h:11.4f}   {code}")

    doc.append("")
    doc.append("1.2. Coordenadas Cartesianas ECEF (e-frame) de los Receptores GNSS:")
    doc.append("   Sensor        X1 (m)             X2 (m)             X3 (m)      Código")
    doc.append("   ------   ----------------   ----------------   ----------------  ------")
    for code in ["REC2", "REC3", "REC4", "REC5"]:
        xe = sol.gnss_ecef[code]
        doc.append(f"      -     {xe[0]:16.4f}   {xe[1]:16.4f}   {xe[2]:16.4f}   {code}")

    doc.append("")
    doc.append("1.3. Centroide de los Receptores GNSS en e-frame:")
    ce = sol.centroid_ecef
    _, _, _, lat_cent_str = rad_to_dms(sol.centroid_lat_rad)
    _, _, _, lon_cent_str = rad_to_dms(sol.centroid_lon_rad)
    doc.append(f"   X_cent = {ce[0]:16.4f} m   Y_cent = {ce[1]:16.4f} m   Z_cent = {ce[2]:16.4f} m")
    doc.append(f"   Latitud: {lat_cent_str} ({np.degrees(sol.centroid_lat_rad):.12f} deg)")
    doc.append(f"   Longitud: {lon_cent_str} ({np.degrees(sol.centroid_lon_rad):.12f} deg)")
    doc.append(f"   Altitud elipsoidal: {sol.centroid_h_ellip:.4f} m")

    doc.append("")
    doc.append("1.4. Matriz de Rotación Ce2n del e-frame al n-frame (NED en Centroide):")
    doc.append(format_matrix_3x3(sol.Ce2n_centroid))

    doc.append("")
    doc.append("1.5. Vectores Relativos en n-frame respecto al Centroide:")
    doc.append("   Sensor        Norte (m)          Este (m)           Down (m)    Código")
    doc.append("   ------   ----------------   ----------------   ----------------  ------")
    for code in ["REC2", "REC3", "REC4", "REC5"]:
        vn = sol.gnss_vectors_n[code]
        doc.append(f"      -     {vn[0]:16.4f}   {vn[1]:16.4f}   {vn[2]:16.4f}   {code}")

    doc.append("")
    doc.append("1.6. Resolución de la Matriz de Actitud Cb2n (Algoritmo de Procrustes SVD / Kabsch):")
    doc.append("   H = tox @ frx.T  -->  [U, S, Vt] = svd(H)  -->  Cb2n = U @ Vt")
    doc.append("   Matriz Cb2n obtenida:")
    doc.append(format_matrix_3x3(sol.Cb2n_gnss))

    doc.append("")
    doc.append("1.7. Ángulos de Euler de la Rotación Cb2n = R3(a3) @ R2(a2) @ R1(a1):")
    a1, a2, a3 = sol.euler_gnss_deg
    doc.append(f"   a1 = {a1:16.10f} deg = {np.radians(a1):16.10f} rad")
    doc.append(f"   a2 = {a2:16.10f} deg = {np.radians(a2):16.10f} rad")
    doc.append(f"   a3 = {a3:16.10f} deg = {np.radians(a3):16.10f} rad")

    doc.append("")
    doc.append("1.8. Actitud de la Plataforma (Ángulos de Navegación Jekeli: r=-a1, p=-a2, y=-a3):")
    r_g, p_g, y_g = sol.attitude_gnss_deg
    doc.append(f"   ROLL  = {r_g:16.10f} deg")
    doc.append(f"   PITCH = {p_g:16.10f} deg")
    doc.append(f"   YAW   = {y_g:16.10f} deg")

    doc.append("")
    doc.append("1.9. Coordenadas del Origen de la Plataforma (PLA):")
    doc.append("   xe_pla = xe_cent - Cn2e @ Cb2n @ xb_cent")
    pe = sol.pla_origin_ecef
    _, _, _, lat_pla_str = rad_to_dms(sol.pla_origin_lat_rad)
    _, _, _, lon_pla_str = rad_to_dms(sol.pla_origin_lon_rad)
    doc.append(f"   ECEF: X = {pe[0]:16.4f} m   Y = {pe[1]:16.4f} m   Z = {pe[2]:16.4f} m")
    doc.append(f"   Latitud: {lat_pla_str} ({np.degrees(sol.pla_origin_lat_rad):.12f} deg)")
    doc.append(f"   Longitud: {lon_pla_str} ({np.degrees(sol.pla_origin_lon_rad):.12f} deg)")
    doc.append(f"   Altitud elipsoidal: {sol.pla_origin_h_ellip:.4f} m")
    doc.append("")

    # =========================================================================
    # PUNTO 2A
    # =========================================================================
    doc.append("=" * 90)
    doc.append("PUNTO 2A: DETERMINACIÓN DE COORDENADAS MEDIANTE ACTITUD GNSS")
    doc.append("=" * 90)
    doc.append("2A.1. Coordenadas en Sistema Terrestre ECEF (e-frame ETRS89):")
    doc.append("   Sensor        X1 (m)             X2 (m)             X3 (m)      Código")
    doc.append("   ------   ----------------   ----------------   ----------------  ------")
    for code, res in sol.results_2a.items():
        doc.append(f"   {code:6s}   {res.ecef[0]:16.4f}   {res.ecef[1]:16.4f}   {res.ecef[2]:16.4f}   {code}")

    doc.append("")
    doc.append("2A.2. Coordenadas Geodésicas (ETRS89) con Altitud Elipsoidal:")
    doc.append("   Sensor        Latitud            Longitud         h.elip(m)   Código")
    doc.append("   ------   -----------------   -----------------   -----------  ------")
    for code, res in sol.results_2a.items():
        _, _, _, lat_s = rad_to_dms(res.lat_rad)
        _, _, _, lon_s = rad_to_dms(res.lon_rad)
        doc.append(f"   {code:6s}   {lat_s:>17s}   {lon_s:>17s}   {res.h_ellip:11.4f}   {code}")

    doc.append("")
    doc.append("2A.3. Coordenadas Proyectadas UTM Huso 30 con Altitud Ortométrica (H = h - N):")
    doc.append("   Sensor        Easting (m)        Northing (m)    Huso  H.orto(m)  Código")
    doc.append("   ------   ----------------   -----------------    ----  ---------  ------")
    for code, res in sol.results_2a.items():
        doc.append(f"   {code:6s}   {res.easting:16.4f}   {res.northing:17.4f}      {res.zone:02d}  {res.h_orto:9.4f}  {code}")
    doc.append("")

    # =========================================================================
    # PUNTO 2B
    # =========================================================================
    doc.append("=" * 90)
    doc.append("PUNTO 2B: DETERMINACIÓN DE COORDENADAS MEDIANTE ORIENTACIÓN INS")
    doc.append("=" * 90)
    doc.append("2B.1. Parámetros y Rotaciones Encadenadas:")
    r_i, p_i, y_i = sol.ins_attitude_deg
    doc.append(f"   Actitud INS (Norte Magnético): Roll={r_i:.6f}º, Pitch={p_i:.6f}º, Yaw={y_i:.6f}º")
    doc.append(f"   Declinación Magnética: {sol.magnetic_declination_deg:+.6f} deg")
    doc.append("")
    doc.append("   Matriz Cs2b (Misalignment INS s-frame -> b-frame):")
    doc.append(format_matrix_3x3(sol.Cs2b_ins))
    doc.append("")
    doc.append("   Matriz Cmn2gn (Norte Magnético -> Norte Geodésico):")
    doc.append(format_matrix_3x3(sol.Cmn2gn))
    doc.append("")
    doc.append("   Matriz Cb2n Total = Cmn2gn @ Cs2n @ Cb2s:")
    doc.append(format_matrix_3x3(sol.Cb2n_ins))
    r_it, p_it, y_it = sol.attitude_ins_total_deg
    doc.append(f"   Actitud Total Plataforma con INS: Roll={r_it:.10f}º, Pitch={p_it:.10f}º, Yaw={y_it:.10f}º")

    doc.append("")
    doc.append("2B.2. Coordenadas Proyectadas UTM Huso 30 con Altitud Ortométrica (INS):")
    doc.append("   Sensor        Easting (m)        Northing (m)    Huso  H.orto(m)  Código")
    doc.append("   ------   ----------------   -----------------    ----  ---------  ------")
    for code, res in sol.results_2b.items():
        doc.append(f"   {code:6s}   {res.easting:16.4f}   {res.northing:17.4f}      {res.zone:02d}  {res.h_orto:9.4f}  {code}")

    doc.append("")
    doc.append("=" * 90)
    doc.append("COMPARACIÓN Y RESIDUALES: DIFERENCIAS (2A - 2B) EN UTM HUSO 30 Y COTA")
    doc.append("=" * 90)
    doc.append("   Sensor      Delta Este (m)     Delta Norte (m)     Delta H (m)    Código")
    doc.append("   ------   -----------------   -----------------   -------------    ------")
    for code, (dE, dN, dH) in sol.diff_2a_2b_utm.items():
        doc.append(f"   {code:6s}   {dE:17.4f}   {dN:17.4f}   {dH:13.4f}    {code}")

    doc.append("")
    doc.append("=" * 90)
    doc.append("FIN DEL INFORME DE PROCESAMIENTO PASO A PASO")
    doc.append("Generado automáticamente por PyGSN (Guiado, Sensores y Navegación)")
    doc.append("=" * 90)

    return "\n".join(doc)

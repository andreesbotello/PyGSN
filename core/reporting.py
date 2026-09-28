"""
PyGSN - Technical Reporting Module
==================================
Generador de informes técnicos rigurosos en formato texto (.txt) del procesamiento
paso a paso de georreferenciación, transformación de marcos de referencia y determinación
de actitud para plataformas y rigs multisensores arbitrarios.
"""

from datetime import datetime
import numpy as np
from .georeferencing import GeoreferencingSolution
from .geodesy import rad_to_dms, ecef_to_geodetic


def format_matrix_3x3(M: np.ndarray, indent: str = "   ") -> str:
    lines = []
    for r in range(3):
        lines.append(f"{indent}{M[r, 0]:16.10f}  {M[r, 1]:16.10f}  {M[r, 2]:16.10f}")
    return "\n".join(lines)


def generate_georeferencing_report(
    sol: GeoreferencingSolution,
    author: str = "Ingeniero PyGSN",
    project: str = "Proyecto de Georreferenciación y Navegación Multi-Sensor",
    doc_id: str = "PyGSN-GEOREF-SOLVER",
    title: str = "INFORME TÉCNICO DE GEORREFERENCIACIÓN Y TRANSFORMACIÓN MULTISENSOR"
) -> str:
    """
    Genera el informe técnico estructurado de procesamiento paso a paso para georreferenciación
    y determinación de actitud de cualquier plataforma multisensor.
    """
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    ell = sol.ellipsoid

    doc = []
    doc.append("=" * 90)
    doc.append("PyGSN - SISTEMA DE GEORREFERENCIACIÓN Y TRANSFORMACIÓN DE COORDENADAS")
    doc.append(f"PROYECTO: {project.upper()}")
    doc.append(f"{title.upper()}")
    doc.append("=" * 90)
    doc.append(f"Autor / Ingeniero: {author}")
    doc.append(f"Referencia / ID:   {doc_id}")
    doc.append(f"Fecha de Cálculo:  {now_str}")
    doc.append(f"Elipsoide:         {ell.name} (a = {ell.a:.4f} m, 1/f = {ell.inv_f:.12f})")
    doc.append(f"Ondulación Geoide: N = {sol.geoid_undulation_N:.4f} m")
    doc.append(f"Declinación Mag.:  δ = {sol.magnetic_declination_deg:+.4f} deg")
    doc.append("-" * 90)
    doc.append("")

    # =========================================================================
    # SECCION 1: GNSS Y DETERMINACION DE ACTITUD
    # =========================================================================
    doc.append("=" * 90)
    doc.append("SECCIÓN 1: DETERMINACIÓN DE ACTITUD DE PLATAFORMA MEDIANTE CONSTELACIÓN GNSS")
    doc.append("=" * 90)
    doc.append("1.1. Coordenadas Geodésicas Observadas por los Receptores GNSS:")
    doc.append("   Sensor        Latitud            Longitud         h.elip(m)   Código")
    doc.append("   ------   -----------------   -----------------   -----------  ------")
    for code in sol.gnss_ecef.keys():
        xe = sol.gnss_ecef[code]
        lat, lon, h = ecef_to_geodetic(xe, ell)
        _, _, _, lat_str = rad_to_dms(lat)
        _, _, _, lon_str = rad_to_dms(lon)
        doc.append(f"      -     {lat_str:>17s}   {lon_str:>17s}   {h:11.4f}   {code}")

    doc.append("")
    doc.append("1.2. Coordenadas Cartesianas ECEF (e-frame) de los Receptores GNSS:")
    doc.append("   Sensor        X1 (m)             X2 (m)             X3 (m)      Código")
    doc.append("   ------   ----------------   ----------------   ----------------  ------")
    for code in sol.gnss_ecef.keys():
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
    for code in sol.gnss_ecef.keys():
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
    # =========================================================================
    # SECCION 2: ORIGEN DE LA PLATAFORMA
    # =========================================================================
    doc.append("=" * 90)
    doc.append("SECCIÓN 2: DETERMINACIÓN DEL ORIGEN DE LA PLATAFORMA (PLA)")
    doc.append("=" * 90)
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
    # SECCION 3: PROPAGACION DE SENSORES CON ACTITUD GNSS
    # =========================================================================
    doc.append("=" * 90)
    doc.append("SECCIÓN 3: GEORREFERENCIACIÓN Y PROPAGACIÓN DE SENSORES DEL RIG (SOLUCIÓN GNSS)")
    doc.append("=" * 90)
    doc.append("3.1. Coordenadas en Sistema Terrestre ECEF (e-frame):")
    doc.append("   Sensor        X1 (m)             X2 (m)             X3 (m)      Código")
    doc.append("   ------   ----------------   ----------------   ----------------  ------")
    for code, res in sol.results_gnss.items():
        doc.append(f"   {code:6s}   {res.ecef[0]:16.4f}   {res.ecef[1]:16.4f}   {res.ecef[2]:16.4f}   {code}")

    doc.append("")
    doc.append("3.2. Coordenadas Geodésicas Elipsoidales con Altitud Elipsoidal:")
    doc.append("   Sensor        Latitud            Longitud         h.elip(m)   Código")
    doc.append("   ------   -----------------   -----------------   -----------  ------")
    for code, res in sol.results_gnss.items():
        _, _, _, lat_s = rad_to_dms(res.lat_rad)
        _, _, _, lon_s = rad_to_dms(res.lon_rad)
        doc.append(f"   {code:6s}   {lat_s:>17s}   {lon_s:>17s}   {res.h_ellip:11.4f}   {code}")

    doc.append("")
    doc.append(f"3.3. Coordenadas Proyectadas UTM con Altitud Ortométrica (H = h - N, N = {sol.geoid_undulation_N:.4f} m):")
    doc.append("   Sensor        Easting (m)        Northing (m)    Huso  H.orto(m)  Código")
    doc.append("   ------   ----------------   -----------------    ----  ---------  ------")
    for code, res in sol.results_gnss.items():
        doc.append(f"   {code:6s}   {res.easting:16.4f}   {res.northing:17.4f}      {res.zone:02d}  {res.h_orto:9.4f}  {code}")
    doc.append("")

    # =========================================================================
    # SECCION 4: ORIENTACION CON INS
    # =========================================================================
    doc.append("=" * 90)
    doc.append("SECCIÓN 4: ORIENTACIÓN INERCIAL Y FUSIÓN MULTISENSOR (SOLUCIÓN INS / BORESIGHT / DECLINACIÓN)")
    doc.append("=" * 90)
    r_i, p_i, y_i = sol.ins_attitude_deg
    doc.append(f"4.1. Actitud INS (Norte Magnético): Roll={r_i:.6f}º, Pitch={p_i:.6f}º, Yaw={y_i:.6f}º")
    doc.append(f"   Declinación Magnética Local: {sol.magnetic_declination_deg:+.6f} deg")
    doc.append("")
    doc.append("4.2. Matriz Cs2b (Desalineamiento Boresight INS s-frame -> b-frame):")
    doc.append(format_matrix_3x3(sol.Cs2b_ins))
    doc.append("")
    doc.append("4.3. Matriz Cmn2gn (Norte Magnético -> Norte Geodésico):")
    doc.append(format_matrix_3x3(sol.Cmn2gn))
    doc.append("")
    doc.append("4.4. Matriz Cb2n Total con INS = Cmn2gn @ Cs2n @ Cb2s:")
    doc.append(format_matrix_3x3(sol.Cb2n_ins))
    r_it, p_it, y_it = sol.attitude_ins_total_deg
    doc.append(f"   Actitud Total Plataforma con INS: Roll={r_it:.10f}º, Pitch={p_it:.10f}º, Yaw={y_it:.10f}º")

    doc.append("")
    doc.append("4.5. Coordenadas Proyectadas UTM con Altitud Ortométrica (Solución INS):")
    doc.append("   Sensor        Easting (m)        Northing (m)    Huso  H.orto(m)  Código")
    doc.append("   ------   ----------------   -----------------    ----  ---------  ------")
    for code, res in sol.results_ins.items():
        doc.append(f"   {code:6s}   {res.easting:16.4f}   {res.northing:17.4f}      {res.zone:02d}  {res.h_orto:9.4f}  {code}")

    doc.append("")
    # =========================================================================
    # SECCION 5: COMPARACION Y RESIDUALES
    # =========================================================================
    doc.append("=" * 90)
    doc.append("SECCIÓN 5: ANÁLISIS DE RESIDUALES Y CONTROL DE CALIDAD (DISCREPANCIAS GNSS - INS)")
    doc.append("=" * 90)
    doc.append("   Sensor      Delta Este (m)     Delta Norte (m)     Delta H (m)    Código")
    doc.append("   ------   -----------------   -----------------   -------------    ------")
    for code, (dE, dN, dH) in sol.diff_gnss_ins_utm.items():
        doc.append(f"   {code:6s}   {dE:17.4f}   {dN:17.4f}   {dH:13.4f}    {code}")

    doc.append("")
    doc.append("=" * 90)
    doc.append("FIN DEL INFORME TÉCNICO DE GEORREFERENCIACIÓN Y NAVEGACIÓN")
    doc.append("Generado automáticamente por PyGSN (Georreferenciación de Sensores y Navegación)")
    doc.append("=" * 90)

    return "\n".join(doc)


# Aliases de compatibilidad
generate_p1_full_txt_report = generate_georeferencing_report

"""
PyGSN - Guiado, Sensores y Navegacion [UPV - S3]
===============================================
Punto de entrada principal para la aplicacion PyGSN.

Modos de uso:
1. Modo Grafico (DearPyGui):
   python main.py
   (Abre la interfaz interactiva con constructor de plataformas y vistas 2D)

2. Modo Terminal / CLI (Para correccion academica rapida o headless):
   python main.py --p1 [--output resultado.txt]
   (Calcula la Practica 1 y genera el informe paso a paso en texto plano)

3. Modo Pruebas Unitarias:
   python main.py --test
   (Ejecuta la suite de validacion numerica)
"""

import sys
import argparse
from pathlib import Path

# Asegurar que el directorio de PyGSN este en sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from core.solver_p1 import create_default_p1_platform, solve_practica_1
from core.reporting import generate_p1_full_txt_report
from core.geodesy import dms_to_rad, rad_to_dms
import numpy as np


def run_cli_p1(output_filename: str = "P1_Resultados_Paso_a_Paso.txt"):
    """Ejecuta la solucion de la Practica 1 en modo consola y genera el informe TXT."""
    print("=" * 80)
    print("PyGSN - RESOLUCION EN LINEA DE COMANDOS (PRACTICA 1)")
    print("=" * 80)

    platform = create_default_p1_platform()
    gnss_obs = {
        "REC2": (dms_to_rad(39, 28, 53.133637, 1), dms_to_rad(0, 20, 7.650964, -1), np.float64(55.8670)),
        "REC3": (dms_to_rad(39, 28, 53.109885, 1), dms_to_rad(0, 20, 7.663129, -1), np.float64(55.8290)),
        "REC4": (dms_to_rad(39, 28, 53.143535, 1), dms_to_rad(0, 20, 7.680928, -1), np.float64(55.8830)),
        "REC5": (dms_to_rad(39, 28, 53.119474, 1), dms_to_rad(0, 20, 7.693816, -1), np.float64(55.8660)),
    }
    ins_attitude = (1.195278, -1.189671, 111.269874)

    print("> Ejecutando calculos geodesicos, SVD Kabsch y transformaciones...")
    sol = solve_practica_1(
        platform=platform,
        gnss_observations=gnss_obs,
        ins_attitude_deg=ins_attitude,
        magnetic_declination_deg=-0.700,
        geoid_undulation_N=50.0166
    )

    rg, pg, yg = sol.attitude_gnss_deg
    print("\n[RESULTADOS PRINCIPALES]")
    print(f"1. Actitud de la plataforma con GNSS (Cb2n):")
    print(f"   Roll  = {rg:+12.6f} deg")
    print(f"   Pitch = {pg:+12.6f} deg")
    print(f"   Yaw   = {yg:+12.6f} deg")

    _, _, _, lat_str = rad_to_dms(sol.pla_origin_lat_rad)
    _, _, _, lon_str = rad_to_dms(sol.pla_origin_lon_rad)
    print(f"2. Coordenadas del origen de la plataforma (PLA):")
    print(f"   Latitud  = {lat_str}")
    print(f"   Longitud = {lon_str}")
    print(f"   h.elip   = {sol.pla_origin_h_ellip:10.4f} m")

    ri, pi, yi = sol.attitude_ins_total_deg
    print(f"3. Actitud total con INS (boresight + declinacion):")
    print(f"   Roll  = {ri:+12.6f} deg")
    print(f"   Pitch = {pi:+12.6f} deg")
    print(f"   Yaw   = {yi:+12.6f} deg")

    print(f"\n> Generando informe detallado paso a paso...")
    report_text = generate_p1_full_txt_report(sol)
    out_file = Path(output_filename).resolve()
    out_file.write_text(report_text, encoding="utf-8")
    print(f"> Fichero guardado exitosamente en: {out_file}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="PyGSN - Guiado, Sensores y Navegacion [UPV]")
    parser.add_argument("--cli", action="store_true", help="Ejecutar en modo consola sin interfaz grafica")
    parser.add_argument("--p1", action="store_true", help="Resolver Practica 1 directamente")
    parser.add_argument("--test", action="store_true", help="Ejecutar pruebas unitarias de validacion")
    parser.add_argument("--output", "-o", type=str, default="P1_Resultados_Paso_a_Paso.txt",
                        help="Ruta de salida del fichero TXT")

    args = parser.parse_args()

    if args.test:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(root_dir / "tests"), pattern="test_*.py")
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)

    if args.cli or args.p1:
        run_cli_p1(args.output)
        sys.exit(0)

    # Modo grafico interactivo
    try:
        from gui.app import PyGSNApp
        app = PyGSNApp()
        app.run()
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar la interfaz grafica: {e}", file=sys.stderr)
        print("Lanzando resolucion en modo consola (CLI)...")
        run_cli_p1(args.output)


if __name__ == "__main__":
    main()

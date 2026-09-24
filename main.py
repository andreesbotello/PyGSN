"""
PyGSN - Guiado, Sensores y Navegacion [UPV - S3]
===============================================
Punto de entrada principal para la aplicacion PyGSN:
Transformacion de Coordenadas, Georreferenciacion de Rigs y Determinacion de Actitud.

Modos de uso:
1. Modo Grafico (DearPyGui):
   python main.py
   (Abre la interfaz interactiva con constructor de plataformas y vistas tecnicas 2D)

2. Modo Terminal / Consola (CLI):
   python main.py --run [--body data/calibracion_vehiculo.txt] [--output output/informe.txt]
   (Calcula la solucion completa y genera el informe paso a paso en texto plano)

3. Modo Pruebas Unitarias:
   python main.py --test
   (Ejecuta la suite de validacion cruzada de algoritmos)
"""

import sys
import argparse
from pathlib import Path

# Asegurar que el directorio raiz de PyGSN este en sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import numpy as np
from core.models import Platform
from core.georeferencing import create_reference_platform, solve_multisensor_georeferencing
from core.reporting import generate_georeferencing_report
from core.geodesy import dms_to_rad, rad_to_dms


def run_cli_georeferencing(
    output_filename: str = "output/Informe_Georreferenciacion.txt",
    body_file: str | None = None
):
    """Ejecuta la georreferenciacion en modo consola y genera el informe tecnico."""
    print("=" * 80)
    print("PyGSN - PROCESAMIENTO DE GEORREFERENCIACION Y NAVEGACION")
    print("=" * 80)

    if body_file and Path(body_file).exists():
        print(f"> Cargando plataforma desde: {body_file}")
        platform = Platform.from_txt(Path(body_file).read_text(encoding="utf-8"))
    else:
        print("> Usando plataforma calibrada de referencia")
        platform = create_reference_platform()

    gnss_obs = {
        "REC2": (dms_to_rad(39, 28, 53.133637, 1), dms_to_rad(0, 20, 7.650964, -1), np.float64(55.8670)),
        "REC3": (dms_to_rad(39, 28, 53.109885, 1), dms_to_rad(0, 20, 7.663129, -1), np.float64(55.8290)),
        "REC4": (dms_to_rad(39, 28, 53.143535, 1), dms_to_rad(0, 20, 7.680928, -1), np.float64(55.8830)),
        "REC5": (dms_to_rad(39, 28, 53.119474, 1), dms_to_rad(0, 20, 7.693816, -1), np.float64(55.8660)),
    }
    ins_attitude = (1.195278, -1.189671, 111.269874)

    print("> Ejecutando calculos geodesicos, SVD Kabsch y transformaciones...")
    sol = solve_multisensor_georeferencing(
        platform=platform,
        gnss_observations=gnss_obs,
        ins_attitude_deg=ins_attitude,
        magnetic_declination_deg=-0.700,
        geoid_undulation_N=50.0166
    )

    rg, pg, yg = sol.attitude_gnss_deg
    print("\n[RESULTADOS PRINCIPALES]")
    print(f"1. Actitud de la plataforma estimada por GNSS (Cb2n):")
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
    print(f"3. Actitud total con sensor INS (boresight + declinacion):")
    print(f"   Roll  = {ri:+12.6f} deg")
    print(f"   Pitch = {pi:+12.6f} deg")
    print(f"   Yaw   = {yi:+12.6f} deg")

    print(f"\n> Generando informe detallado paso a paso...")
    report_text = generate_georeferencing_report(sol)
    out_file = Path(output_filename)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report_text, encoding="utf-8")
    print(f"> Fichero guardado exitosamente en: {out_file.resolve()}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="PyGSN - Guiado, Sensores y Navegacion [UPV]")
    parser.add_argument("--cli", action="store_true", help="Ejecutar en modo consola sin interfaz grafica")
    parser.add_argument("--run", action="store_true", help="Ejecutar resolucion completa")
    parser.add_argument("--p1", action="store_true", help="Alias de compatibilidad para resolver la Practica 1")
    parser.add_argument("--project", type=str, default=None, help="Ruta al archivo de proyecto .pygsn")
    parser.add_argument("--body", type=str, default=None, help="Ruta al fichero .txt de definicion de la plataforma y sensores")
    parser.add_argument("--obs", type=str, default=None, help="Ruta al fichero .txt de observaciones de sensores")
    parser.add_argument("--test", action="store_true", help="Ejecutar pruebas unitarias de validacion")
    parser.add_argument("--output", "-o", type=str, default="output/Informe_Georreferenciacion.txt",
                        help="Ruta de salida del informe TXT")

    args = parser.parse_args()

    if args.test:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(root_dir / "tests"), pattern="test_*.py")
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)

    if args.project:
        from core.project import Project
        from core.operators import GeoreferencingOperator, ReportingOperator
        print(f"> Cargando proyecto PyGSN: {args.project}")
        proj = Project.load(args.project)
        geo_op = GeoreferencingOperator()
        res = geo_op.execute(proj, observations=args.obs)
        if not res.success:
            print(f"[ERROR] Fallo en la ejecucion del operador: {res.error_message}")
            sys.exit(1)
        for msg in res.messages:
            print(f"  {msg}")
        rep_op = ReportingOperator()
        rep_res = rep_op.execute(proj, georeferencing_result=res.data["georeferencing_result"], output_path=args.output)
        if rep_res.success:
            print(f"> Informe guardado exitosamente en: {args.output}")
        sys.exit(0)

    if args.cli or args.run or args.p1:
        run_cli_georeferencing(args.output, args.body)
        sys.exit(0)

    # Modo grafico interactivo
    from gui.app import PyGSNApp
    app = PyGSNApp()
    app.run()


if __name__ == "__main__":
    main()

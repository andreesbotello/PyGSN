"""
PyGSN - Georreferenciación de Sensores y Navegación
===================================================
Punto de entrada principal para la aplicación PyGSN:
Transformación de Coordenadas, Georreferenciación de Rigs y Determinación de Actitud.

Modos de uso:
1. Modo Gráfico (PySide6 / Qt):
   python main.py
   (Abre la interfaz interactiva con constructor de plataformas, vistas CAD 2D y capas)

2. Modo Terminal / Consola (CLI):
   python main.py --run [--body data/calibracion_vehiculo.txt] [--obs data/observaciones_sensores.txt] [--output output/informe.txt]
   (Calcula la solución completa y genera el informe técnico en texto plano)

3. Modo Proyectos Estructurados (.pygsn):
   python main.py --project data/proyecto_vehiculo_multisensor.pygsn --obs data/observaciones_sensores.txt

4. Modo Pruebas Unitarias:
   python main.py --test
   (Ejecuta la suite de validación algorítmica)
"""

import sys
import argparse
from pathlib import Path

# Asegurar que el directorio raíz de PyGSN esté en sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import numpy as np
from core.models import Platform
from core.georeferencing import create_reference_platform, solve_multisensor_georeferencing
from core.reporting import generate_georeferencing_report
from core.geodesy import dms_to_rad, rad_to_dms
from core.operators.georeferencing_operator import parse_observations_content


def run_cli_georeferencing(
    output_filename: str = "output/Informe_Georreferenciacion.txt",
    body_file: str | None = None,
    obs_file: str | None = None
):
    """Ejecuta la georreferenciación en modo consola y genera el informe técnico."""
    print("=" * 80)
    print("PyGSN - PROCESAMIENTO DE GEORREFERENCIACION Y NAVEGACION")
    print("=" * 80)

    if body_file and Path(body_file).exists():
        print(f"> Cargando plataforma desde: {body_file}")
        platform = Platform.from_txt(Path(body_file).read_text(encoding="utf-8"))
    else:
        print("> Usando plataforma de referencia")
        platform = create_reference_platform()

    # Carga de observaciones dinámica o dataset de referencia
    if obs_file and Path(obs_file).exists():
        print(f"> Cargando observaciones desde: {obs_file}")
        data = parse_observations_content(Path(obs_file).read_text(encoding="utf-8"))
        gnss_obs = data.get("gnss_observations", {})
        ins_attitude = data.get("ins_attitude_deg", (0.0, 0.0, 0.0))
        decl = data.get("magnetic_declination_deg", -0.700)
        undul_n = data.get("geoid_undulation_N", 50.0166)
    else:
        default_obs_path = Path("data/observaciones_sensores.txt")
        if default_obs_path.exists():
            data = parse_observations_content(default_obs_path.read_text(encoding="utf-8"))
            gnss_obs = data.get("gnss_observations", {})
            ins_attitude = data.get("ins_attitude_deg", (0.0, 0.0, 0.0))
            decl = data.get("magnetic_declination_deg", -0.700)
            undul_n = data.get("geoid_undulation_N", 50.0166)
        else:
            gnss_obs = {
                "REC2": (dms_to_rad(39, 28, 53.133637, 1), dms_to_rad(0, 20, 7.650964, -1), np.float64(55.8670)),
                "REC3": (dms_to_rad(39, 28, 53.109885, 1), dms_to_rad(0, 20, 7.663129, -1), np.float64(55.8290)),
                "REC4": (dms_to_rad(39, 28, 53.143535, 1), dms_to_rad(0, 20, 7.680928, -1), np.float64(55.8830)),
                "REC5": (dms_to_rad(39, 28, 53.119474, 1), dms_to_rad(0, 20, 7.693816, -1), np.float64(55.8660)),
            }
            ins_attitude = (1.195278, -1.189671, 111.269874)
            decl = -0.700
            undul_n = 50.0166

    print(f"> Sensores GNSS con observaciones: {list(gnss_obs.keys())}")
    print("> Ejecutando cálculos geodésicos, SVD Kabsch y transformaciones...")
    sol = solve_multisensor_georeferencing(
        platform=platform,
        gnss_observations=gnss_obs,
        ins_attitude_deg=ins_attitude,
        magnetic_declination_deg=decl,
        geoid_undulation_N=undul_n
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
    print(f"3. Actitud total con sensor INS (boresight + declinación):")
    print(f"   Roll  = {ri:+12.6f} deg")
    print(f"   Pitch = {pi:+12.6f} deg")
    print(f"   Yaw   = {yi:+12.6f} deg")

    print(f"\n> Generando informe técnico estructurado...")
    report_text = generate_georeferencing_report(sol)
    out_file = Path(output_filename)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report_text, encoding="utf-8")
    print(f"> Fichero guardado exitosamente en: {out_file.resolve()}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="PyGSN - Georreferenciación de Sensores y Navegación")
    parser.add_argument("--cli", action="store_true", help="Ejecutar en modo consola sin interfaz gráfica")
    parser.add_argument("--run", action="store_true", help="Ejecutar resolución completa en consola")
    parser.add_argument("--demo", action="store_true", help="Ejecutar demostración de cálculo multisensor")
    parser.add_argument("--p1", action="store_true", help="Alias de compatibilidad")
    parser.add_argument("--project", type=str, default=None, help="Ruta al archivo de proyecto .pygsn")
    parser.add_argument("--body", type=str, default=None, help="Ruta al fichero .txt de calibración de plataforma y sensores")
    parser.add_argument("--obs", type=str, default=None, help="Ruta al fichero .txt de observaciones de campo")
    parser.add_argument("--test", action="store_true", help="Ejecutar pruebas unitarias de validación")
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
            print(f"[ERROR] Fallo en la ejecución del operador: {res.error_message}")
            sys.exit(1)
        for msg in res.messages:
            print(f"  {msg}")
        rep_op = ReportingOperator()
        rep_res = rep_op.execute(proj, georeferencing_result=res.data["georeferencing_result"], output_path=args.output)
        if rep_res.success:
            print(f"> Informe guardado exitosamente en: {args.output}")
        sys.exit(0)

    if args.cli or args.run or args.demo or args.p1:
        run_cli_georeferencing(args.output, args.body, args.obs)
        sys.exit(0)

    # Modo gráfico interactivo
    from gui.app import PyGSNApp
    app = PyGSNApp()
    app.run()


if __name__ == "__main__":
    main()

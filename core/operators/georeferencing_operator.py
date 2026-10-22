"""
PyGSN - Georeferencing Operator
===============================
Operador para la resolucion rigurosa de georreferenciacion y actitud multi-sensor:
- Determinacion de la actitud de plataforma C_b^n por Procrustes Ortogonal (SVD de Kabsch).
- Traslacion cinematica al origen de plataforma (PLA) en ECEF, Geodesicas y UTM.
- Georreferenciacion de todos los sensores montados en el chasis (palancas lever-arm).
- Comparacion de actitud entre solucion GNSS y orientacion inercial (INS / Boresight / Declinacion).
"""

from pathlib import Path
from typing import Any
import numpy as np

from .base import BaseOperator, OperatorResult
from ..georeferencing import solve_multisensor_georeferencing
from ..geodesy import GRS80, WGS84, dms_to_rad


def parse_observations_content(content: str) -> dict[str, Any]:
    """
    Parsea el contenido de un archivo de observaciones en texto plano.
    
    Retorna diccionario con:
        'gnss_observations': dict[code, (lat_rad, lon_rad, h_m)]
        'ins_attitude_deg': tuple[roll, pitch, yaw]
        'magnetic_declination_deg': float
        'geoid_undulation_N': float
        'ellipsoid_name': str
    """
    gnss_obs = {}
    ins_att = (0.0, 0.0, 0.0)
    decl = -0.700
    geoid_n = 50.0166
    ell_name = "GRS80"

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        key = parts[0].upper()

        if key.startswith("REC") or key.startswith("GNSS"):
            # Formato: CODE  D M S (lat)  D M S (lon)  H
            if len(parts) >= 8:
                try:
                    lat_d, lat_m, lat_s = float(parts[1]), float(parts[2]), float(parts[3])
                    lon_d, lon_m, lon_s = float(parts[4]), float(parts[5]), float(parts[6])
                    h = float(parts[7])

                    lat_sign = -1 if lat_d < 0 or parts[1].startswith("-") else 1
                    lon_sign = -1 if lon_d < 0 or parts[4].startswith("-") else 1

                    lat_rad = dms_to_rad(abs(lat_d), lat_m, lat_s, lat_sign)
                    lon_rad = dms_to_rad(abs(lon_d), lon_m, lon_s, lon_sign)
                    gnss_obs[key] = (lat_rad, lon_rad, np.float64(h))
                except (ValueError, IndexError):
                    continue

        elif "INS_ACTITUD" in key or "INS_ATTITUDE" in key:
            if len(parts) >= 4:
                try:
                    ins_att = (float(parts[1]), float(parts[2]), float(parts[3]))
                except ValueError:
                    pass

        elif "DECLINACION" in key or "DECLINATION" in key:
            if len(parts) >= 2:
                try:
                    decl = float(parts[1])
                except ValueError:
                    pass

        elif "ONDULACION" in key or "GEOIDE" in key or "UNDULATION" in key:
            if len(parts) >= 2:
                try:
                    geoid_n = float(parts[1])
                except ValueError:
                    pass

        elif "ELIPSOIDE" in key or "ELLIPSOID" in key:
            if len(parts) >= 2:
                ell_name = parts[1].upper()

    return {
        "gnss_observations": gnss_obs,
        "ins_attitude_deg": ins_att,
        "magnetic_declination_deg": decl,
        "geoid_undulation_N": geoid_n,
        "ellipsoid_name": ell_name
    }


class GeoreferencingOperator(BaseOperator):
    """
    Operador que ejecuta la cadena completa de georreferenciacion de sensores.
    """
    def __init__(self):
        super().__init__(name="GeoreferencingOperator")

    def execute(self, project: Any, **kwargs) -> OperatorResult:
        """
        Ejecuta la resolucion.
        
        Parametros aceptados en kwargs:
            observations: str | Path | dict -> Ruta al fichero de observaciones, texto plano o dict.
            utm_zone: int -> Zona UTM (por defecto toma de project.config).
            geoid_undulation_n: float -> Ondulacion N (por defecto toma de project.config).
        """
        result = OperatorResult(operator_name=self.name, success=False)
        result.log(f"Iniciando ejecucion de {self.name} sobre plataforma: {project.platform.name}")

        obs_input = kwargs.get("observations")
        if obs_input is None:
            default_obs = Path(r"c:\Users\bryan\Desktop\UPV\S3\2_Sensores\PyGSN\data\observaciones_sensores.txt")
            if default_obs.exists():
                obs_input = default_obs
                result.log(f"Usando observaciones por defecto: {default_obs}")
            else:
                result.error_message = "No se proporcionaron observaciones GNSS/INS para el calculo."
                return result

        parsed_data = {}
        if isinstance(obs_input, (str, Path)) and (isinstance(obs_input, Path) or Path(obs_input).exists()):
            p = Path(obs_input)
            obs_text = p.read_text(encoding="utf-8")
            parsed_data = parse_observations_content(obs_text)
        elif isinstance(obs_input, str):
            parsed_data = parse_observations_content(obs_input)
        elif isinstance(obs_input, dict):
            parsed_data = obs_input

        gnss_obs = parsed_data.get("gnss_observations", {})
        ins_att = parsed_data.get("ins_attitude_deg", (0.0, 0.0, 0.0))
        decl = kwargs.get("magnetic_declination_deg", parsed_data.get("magnetic_declination_deg", -0.700))
        geoid_n = kwargs.get("geoid_undulation_n", parsed_data.get("geoid_undulation_N", 50.0166))
        ell_name = parsed_data.get("ellipsoid_name", project.ellipsoid_name)
        ell = WGS84 if ell_name == "WGS84" else GRS80

        if not gnss_obs:
            result.error_message = "No se encontraron observaciones GNSS validas para la plataforma."
            return result

        try:
            geo_res = solve_multisensor_georeferencing(
                platform=project.platform,
                gnss_observations=gnss_obs,
                ins_attitude_deg=ins_att,
                magnetic_declination_deg=decl,
                geoid_undulation_N=geoid_n,
                ellipsoid=ell
            )
            result.success = True
            result.data["georeferencing_result"] = geo_res
            result.data["C_b_n"] = geo_res.Cb2n_gnss
            result.data["attitude_gnss_deg"] = geo_res.attitude_gnss_deg
            result.data["euler_gnss_deg"] = geo_res.euler_gnss_deg
            result.data["r_pla_e"] = geo_res.pla_origin_ecef
            result.data["r_pla_geo"] = (geo_res.pla_origin_lat_rad, geo_res.pla_origin_lon_rad, geo_res.pla_origin_h_ellip)
            result.data["results_gnss"] = geo_res.results_gnss
            result.data["results_ins"] = geo_res.results_ins
            result.data["diff_gnss_ins_utm"] = geo_res.diff_gnss_ins_utm
            result.data["attitude_ins_total_deg"] = geo_res.attitude_ins_total_deg

            rg, pg, yg = geo_res.attitude_gnss_deg
            result.log(f"Actitud calculada con exito (SVD Kabsch): Roll={rg:.4f} deg, Pitch={pg:.4f} deg, Yaw={yg:.4f} deg")
            result.log(f"Posicion PLA: Lat={geo_res.pla_origin_lat_rad:.8f} rad, Lon={geo_res.pla_origin_lon_rad:.8f} rad, h={geo_res.pla_origin_h_ellip:.4f} m")

            if kwargs.get("apply_to_platform", True) and project.platform:
                srt = project.get_active_reference_system() if hasattr(project, "get_active_reference_system") else None
                if not srt:
                    from ..models import ReferenceSystem
                    srt = ReferenceSystem(
                        id="SRT_01",
                        name=f"{project.ellipsoid_name} / UTM {project.config.get('utm_zone', 30)}N",
                        ellipsoid=project.ellipsoid_name,
                        utm_zone=abs(int(project.config.get("utm_zone", 30))),
                        utm_hemisphere="S" if int(project.config.get("utm_zone", 30)) < 0 else "N",
                        geoid_undulation_N=geoid_n,
                        magnetic_declination_deg=decl
                    )
                    if hasattr(project, "add_reference_system"):
                        project.add_reference_system(srt, set_active=True)
                project.platform.apply_georeferencing_solution(geo_res, srt, method_str=kwargs.get("method", "SVD+INS"))

        except Exception as e:
            result.success = False
            result.error_message = f"Error durante el computo de georreferenciacion: {str(e)}"

        return result

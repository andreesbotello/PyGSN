"""
PyGSN - Core Models Module
==========================
Definicion de datos estructurados para plataformas universales y sensores:
- Representacion generica de plataformas (coche, dron, rover, barco, banco de pruebas)
- Sensores con lever-arms (b-frame) y desalineamientos (s-frame -> b-frame)
- Serializacion y deserializacion JSON para guardar/cargar rigs
"""

from dataclasses import dataclass, field
from enum import Enum
import json
import math
from typing import Any
import numpy as np


class SensorType(str, Enum):
    PLATFORM_ORIGIN = "ORIGIN"
    GNSS = "GNSS"
    INS = "INS"
    CAMERA = "CAMERA"
    LIDAR = "LIDAR"
    ODOMETER = "ODOMETER"
    OTHER = "OTHER"


def parse_dms_or_deg(s: str) -> float:
    """
    Parsea una coordenada en formato sexagesimal (ej: 39º28'53.133637", -0º20'7.650964", 39d28m53.13s)
    o decimal estándar (ej: 39.481426, -0.335458).
    """
    import re
    s_clean = s.strip().replace("“", "\"").replace("”", "\"").replace("''", "\"")
    try:
        return float(s_clean)
    except ValueError:
        pass

    is_neg = s_clean.startswith("-") or "S" in s_clean.upper() or "W" in s_clean.upper() or "O" in s_clean.upper()
    tokens = re.split(r"[º°'\"dmsDMS\s\-_+NSEWO\ufffd]+", s_clean)
    tokens = [t for t in tokens if t]
    if len(tokens) >= 3:
        d = float(tokens[0])
        m = float(tokens[1])
        sec = float(tokens[2])
        deg = d + m / 60.0 + sec / 3600.0
    elif len(tokens) == 2:
        d = float(tokens[0])
        m = float(tokens[1])
        deg = d + m / 60.0
    elif len(tokens) == 1:
        deg = float(tokens[0])
    else:
        raise ValueError(f"No se pudo parsear coordenada: {s}")
    return -deg if is_neg else deg


@dataclass
class SensorObservation:
    """
    Observaciones de campo del sensor en el mundo real (e-frame o n-frame local).
    Permite desacoplar y asociar mediciones a un Sistema de Referencia Terrestre específico.
    """
    ref_system_id: str = ""                                               # ID del SRT de referencia
    geodetic_deg: tuple[float, float, float] | None = None                # (lat_deg, lon_deg, h_m)
    attitude_rpy_deg: tuple[float, float, float] | None = None            # (roll_deg, pitch_deg, yaw_deg)

    @property
    def has_geodetic(self) -> bool:
        return self.geodetic_deg is not None

    @property
    def has_attitude(self) -> bool:
        return self.attitude_rpy_deg is not None

    def get_lat_lon_h_rad(self) -> tuple[np.float64, np.float64, np.float64] | None:
        if self.geodetic_deg is None:
            return None
        lat, lon, h = self.geodetic_deg
        return (np.radians(np.float64(lat)), np.radians(np.float64(lon)), np.float64(h))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_system_id": self.ref_system_id,
            "geodetic_deg": [float(x) for x in self.geodetic_deg] if self.geodetic_deg else None,
            "attitude_rpy_deg": [float(x) for x in self.attitude_rpy_deg] if self.attitude_rpy_deg else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SensorObservation":
        return cls(
            ref_system_id=data.get("ref_system_id", ""),
            geodetic_deg=tuple(data["geodetic_deg"]) if data.get("geodetic_deg") else None,
            attitude_rpy_deg=tuple(data["attitude_rpy_deg"]) if data.get("attitude_rpy_deg") else None,
        )


@dataclass
class SensorGeoref:
    """Atributos propagados del sensor en el sistema terrestre (e-frame / SRT)."""
    ref_system_id: str                          # Identificador del SRT (ej. "SRT_01")
    ref_system_name: str = ""                   # Nombre legible del SRT (ej. "ETRS89 / UTM 30N")
    ecef: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64)) # [X, Y, Z] en metros
    lat_deg: float = 0.0                        # Latitud geodésica en grados
    lon_deg: float = 0.0                        # Longitud geodésica en grados
    h_ellip_m: float = 0.0                      # Altura elipsoidal en metros
    utm_easting_m: float = 0.0                  # Coordenada X / Este UTM (m)
    utm_northing_m: float = 0.0                 # Coordenada Y / Norte UTM (m)
    utm_zone: int = 30                          # Huso UTM
    utm_hemisphere: str = "N"                   # Hemisferio UTM ('N' o 'S')
    h_ortho_m: float = 0.0                      # Altura ortométrica H = h - N (m)
    computed_via: str = "SVD"                   # "SVD", "INS", "SVD+INS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_system_id": self.ref_system_id,
            "ref_system_name": self.ref_system_name,
            "ecef": [float(x) for x in self.ecef],
            "lat_deg": float(self.lat_deg),
            "lon_deg": float(self.lon_deg),
            "h_ellip_m": float(self.h_ellip_m),
            "utm_easting_m": float(self.utm_easting_m),
            "utm_northing_m": float(self.utm_northing_m),
            "utm_zone": int(self.utm_zone),
            "utm_hemisphere": self.utm_hemisphere,
            "h_ortho_m": float(self.h_ortho_m),
            "computed_via": self.computed_via,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SensorGeoref":
        return cls(
            ref_system_id=data.get("ref_system_id", ""),
            ref_system_name=data.get("ref_system_name", ""),
            ecef=np.array(data.get("ecef", [0.0, 0.0, 0.0]), dtype=np.float64),
            lat_deg=float(data.get("lat_deg", 0.0)),
            lon_deg=float(data.get("lon_deg", 0.0)),
            h_ellip_m=float(data.get("h_ellip_m", 0.0)),
            utm_easting_m=float(data.get("utm_easting_m", 0.0)),
            utm_northing_m=float(data.get("utm_northing_m", 0.0)),
            utm_zone=int(data.get("utm_zone", 30)),
            utm_hemisphere=data.get("utm_hemisphere", "N"),
            h_ortho_m=float(data.get("h_ortho_m", 0.0)),
            computed_via=data.get("computed_via", "SVD"),
        )


@dataclass
class PlatformPose:
    """Pose estimada del centro de referencia de la plataforma (PLA) en el sistema terrestre (e-frame)."""
    ref_system_id: str
    ref_system_name: str = ""
    ecef: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64)) # [X, Y, Z] PLA en m
    lat_deg: float = 0.0
    lon_deg: float = 0.0
    h_ellip_m: float = 0.0
    utm_easting_m: float = 0.0
    utm_northing_m: float = 0.0
    utm_zone: int = 30
    utm_hemisphere: str = "N"
    h_ortho_m: float = 0.0
    attitude_rpy_deg: tuple[float, float, float] = (0.0, 0.0, 0.0) # (roll, pitch, yaw) [deg]
    dcm_b2e: list[list[float]] = field(default_factory=lambda: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    method: str = "SVD"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_system_id": self.ref_system_id,
            "ref_system_name": self.ref_system_name,
            "ecef": [float(x) for x in self.ecef],
            "lat_deg": float(self.lat_deg),
            "lon_deg": float(self.lon_deg),
            "h_ellip_m": float(self.h_ellip_m),
            "utm_easting_m": float(self.utm_easting_m),
            "utm_northing_m": float(self.utm_northing_m),
            "utm_zone": int(self.utm_zone),
            "utm_hemisphere": self.utm_hemisphere,
            "h_ortho_m": float(self.h_ortho_m),
            "attitude_rpy_deg": list(self.attitude_rpy_deg),
            "dcm_b2e": [[float(v) for v in row] for row in self.dcm_b2e],
            "method": self.method,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlatformPose":
        return cls(
            ref_system_id=data.get("ref_system_id", ""),
            ref_system_name=data.get("ref_system_name", ""),
            ecef=np.array(data.get("ecef", [0.0, 0.0, 0.0]), dtype=np.float64),
            lat_deg=float(data.get("lat_deg", 0.0)),
            lon_deg=float(data.get("lon_deg", 0.0)),
            h_ellip_m=float(data.get("h_ellip_m", 0.0)),
            utm_easting_m=float(data.get("utm_easting_m", 0.0)),
            utm_northing_m=float(data.get("utm_northing_m", 0.0)),
            utm_zone=int(data.get("utm_zone", 30)),
            utm_hemisphere=data.get("utm_hemisphere", "N"),
            h_ortho_m=float(data.get("h_ortho_m", 0.0)),
            attitude_rpy_deg=tuple(data.get("attitude_rpy_deg", (0.0, 0.0, 0.0))),
            dcm_b2e=data.get("dcm_b2e", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
            method=data.get("method", "SVD"),
        )

    @property
    def roll_deg(self) -> float:
        """Ángulo de balanceo (Roll) en grados."""
        return float(self.attitude_rpy_deg[0]) if self.attitude_rpy_deg else 0.0

    @property
    def pitch_deg(self) -> float:
        """Ángulo de cabeceo (Pitch) en grados."""
        return float(self.attitude_rpy_deg[1]) if self.attitude_rpy_deg else 0.0

    @property
    def yaw_deg(self) -> float:
        """Ángulo de guiñada o rumbo (Yaw) en grados respecto al Norte geográfico."""
        return float(self.attitude_rpy_deg[2]) if self.attitude_rpy_deg else 0.0

    @property
    def convergence_deg(self) -> float:
        """Convergencia de meridianos gamma en grados para el punto medio de la plataforma."""
        if self.lat_deg == 0.0 and self.lon_deg == 0.0:
            return 0.0
        from .geodesy import utm_meridian_convergence
        try:
            gamma_rad = utm_meridian_convergence(
                math.radians(self.lat_deg),
                math.radians(self.lon_deg),
                zone=self.utm_zone
            )
            return float(math.degrees(gamma_rad))
        except Exception:
            return 0.0



@dataclass
class Sensor:
    """Modelo de un sensor instalado en la plataforma."""
    code: str                                    # Identificador corto (ej. "REC2", "INS")
    name: str                                    # Nombre descriptivo
    sensor_type: SensorType = SensorType.OTHER
    lever_arm_b: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64)) # [x1, x2, x3] en b-frame (m)
    boresight_deg: tuple[float, float, float] = (0.0, 0.0, 0.0) # (alpha, beta, gamma) en deg
    observation: SensorObservation | None = None # Observables de campo asociados
    georef: SensorGeoref | None = None           # Coordenadas y atributos calculados en e-frame tras georreferenciación

    def __post_init__(self) -> None:
        if self.code:
            self.code = self.code.strip()
        if self.name:
            self.name = self.name.strip()

    @property
    def is_georeferenced(self) -> bool:
        """Indica si el sensor dispone de coordenadas propagadas en el e-frame."""
        return self.georef is not None

    @property
    def geodetic_obs(self) -> tuple[np.float64, np.float64, np.float64] | None:
        if self.observation and self.observation.has_geodetic:
            return self.observation.get_lat_lon_h_rad()
        return None

    @geodetic_obs.setter
    def geodetic_obs(self, val: tuple[float, float, float] | None):
        if val is None:
            if self.observation:
                self.observation.geodetic_deg = None
            return
        lat_deg = float(np.degrees(val[0]))
        lon_deg = float(np.degrees(val[1]))
        h_m = float(val[2])
        if not self.observation:
            self.observation = SensorObservation()
        self.observation.geodetic_deg = (lat_deg, lon_deg, h_m)

    @property
    def attitude_obs_deg(self) -> tuple[float, float, float] | None:
        if self.observation and self.observation.has_attitude:
            return self.observation.attitude_rpy_deg
        return None

    @attitude_obs_deg.setter
    def attitude_obs_deg(self, val: tuple[float, float, float] | None):
        if val is None:
            if self.observation:
                self.observation.attitude_rpy_deg = None
            return
        if not self.observation:
            self.observation = SensorObservation()
        self.observation.attitude_rpy_deg = (float(val[0]), float(val[1]), float(val[2]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "sensor_type": self.sensor_type.value,
            "lever_arm_b": [float(x) for x in self.lever_arm_b],
            "boresight_deg": [float(x) for x in self.boresight_deg],
            "observation": self.observation.to_dict() if self.observation else None,
            "georef": self.georef.to_dict() if self.georef else None,
            "geodetic_obs": [float(x) for x in self.geodetic_obs] if self.geodetic_obs else None,
            "attitude_obs_deg": list(self.attitude_obs_deg) if self.attitude_obs_deg else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Sensor":
        obs = None
        if "observation" in data and data["observation"]:
            obs = SensorObservation.from_dict(data["observation"])
        elif data.get("geodetic_obs") or data.get("attitude_obs_deg"):
            obs = SensorObservation()
            if data.get("geodetic_obs"):
                g = data["geodetic_obs"]
                obs.geodetic_deg = (float(np.degrees(g[0])), float(np.degrees(g[1])), float(g[2]))
            if data.get("attitude_obs_deg"):
                obs.attitude_rpy_deg = tuple(float(x) for x in data["attitude_obs_deg"])

        georef = SensorGeoref.from_dict(data["georef"]) if data.get("georef") else None

        return cls(
            code=data["code"],
            name=data.get("name", data["code"]),
            sensor_type=SensorType(data.get("sensor_type", "OTHER")),
            lever_arm_b=np.array(data["lever_arm_b"], dtype=np.float64),
            boresight_deg=tuple(data.get("boresight_deg", (0.0, 0.0, 0.0))),
            observation=obs,
            georef=georef,
        )

    def get_attributes_dict(self) -> dict[str, Any]:
        """Retorna un diccionario estructurado tipo tabla de atributos F6 con columnas b-frame y e-frame."""
        return {
            "code": self.code,
            "name": self.name,
            "type": self.sensor_type.value,
            "xb_m": float(self.lever_arm_b[0]),
            "yb_m": float(self.lever_arm_b[1]),
            "zb_m": float(self.lever_arm_b[2]),
            "alpha_deg": float(self.boresight_deg[0]),
            "beta_deg": float(self.boresight_deg[1]),
            "gamma_deg": float(self.boresight_deg[2]),
            "is_georef": self.is_georeferenced,
            "srt_id": self.georef.ref_system_id if self.georef else "-",
            "srt_name": self.georef.ref_system_name if self.georef else "-",
            "xe_m": float(self.georef.ecef[0]) if self.georef else None,
            "ye_m": float(self.georef.ecef[1]) if self.georef else None,
            "ze_m": float(self.georef.ecef[2]) if self.georef else None,
            "lat_deg": self.georef.lat_deg if self.georef else None,
            "lon_deg": self.georef.lon_deg if self.georef else None,
            "h_ellip_m": self.georef.h_ellip_m if self.georef else None,
            "utm_e_m": self.georef.utm_easting_m if self.georef else None,
            "utm_n_m": self.georef.utm_northing_m if self.georef else None,
            "h_ortho_m": self.georef.h_ortho_m if self.georef else None,
            "computed_via": self.georef.computed_via if self.georef else "-",
        }

    def get_boresight_alpha_beta_gamma(self) -> tuple[float, float, float]:
        """Devuelve los ángulos de desalineamiento de calibración (alpha, beta, gamma) en grados."""
        return (float(self.boresight_deg[0]), float(self.boresight_deg[1]), float(self.boresight_deg[2]))

    def get_boresight_rpy(self) -> tuple[float, float, float]:
        """
        Devuelve la orientación del sensor respecto a la plataforma bajo convención de actitud (Roll, Pitch, Yaw) en grados.
        Relación exacta: Roll = -alpha, Pitch = -beta, Yaw = -gamma.
        """
        a, b, c = self.get_boresight_alpha_beta_gamma()
        r = -a
        p = -b
        y = -c
        if y < -180.0:
            y += 360.0
        elif y > 180.0:
            y -= 360.0
        return (round(r, 6), round(p, 6), round(y, 6))

    def set_boresight_from_rpy(self, roll_deg: float, pitch_deg: float, yaw_deg: float) -> None:
        """
        Fija los ángulos de boresight a partir de la actitud (Roll, Pitch, Yaw) en grados.
        Convierte a la representación canónica (alpha, beta, gamma): alpha = -Roll, beta = -Pitch, gamma = -Yaw.
        """
        a = -roll_deg
        b = -pitch_deg
        c = -yaw_deg
        if c < -180.0:
            c += 360.0
        elif c > 180.0:
            c -= 360.0
        self.boresight_deg = (round(a, 6), round(b, 6), round(c, 6))


def infer_sensor_type_from_code(code: str) -> SensorType:
    """Infiere el tipo de sensor a partir del código o prefijo estándar."""
    c = code.upper()
    if c.startswith("REC") or "GNSS" in c or "GPS" in c:
        return SensorType.GNSS
    elif "INS" in c or "IMU" in c:
        return SensorType.INS
    elif c.startswith("CAM"):
        return SensorType.CAMERA
    elif "LIDAR" in c:
        return SensorType.LIDAR
    elif "ODO" in c:
        return SensorType.ODOMETER
    elif c in ("PLA", "ORIGEN", "CHASIS", "BODY"):
        return SensorType.PLATFORM_ORIGIN
    return SensorType.OTHER


@dataclass
class ReferenceSystem:
    """
    Modelo de un Sistema de Referencia Terrestre (SRT / e-frame).
    Contiene la parametrizacion geodesica local y de proyeccion:
    - Elipsoide de referencia (GRS80, WGS84)
    - Ondulacion del geoide N (m)
    - Declinacion magnetica delta (deg)
    - Zona UTM (1..60) y hemisferio ('N' o 'S')
    - Estado activo dentro del proyecto
    """
    id: str                                      # Identificador unico (ej. "SRT_01")
    name: str = ""                               # Nombre descriptivo (ej. "ETRS89 / UTM 30N")
    ellipsoid: str = "GRS80"                     # "GRS80" o "WGS84"
    geoid_undulation_N: float = 0.0              # metros (N)
    magnetic_declination_deg: float = 0.0        # grados (delta)
    utm_zone: int = 30                           # 1 a 60
    utm_hemisphere: str = "N"                    # "N" o "S"
    is_active: bool = False                      # Marca de SRT activo
    show_basemap: bool = True                    # Visibilidad del mapa base OpenStreetMap
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_ellipsoid(self):
        """Devuelve la instancia de Ellipsoid correspondiente."""
        from .geodesy import GRS80, WGS84
        return WGS84 if self.ellipsoid.upper() == "WGS84" else GRS80

    @property
    def ellipsoid_obj(self):
        """Propiedad de compatibilidad que devuelve la instancia de Ellipsoid."""
        return self.get_ellipsoid()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "ellipsoid": self.ellipsoid,
            "geoid_undulation_N": float(self.geoid_undulation_N),
            "magnetic_declination_deg": float(self.magnetic_declination_deg),
            "utm_zone": int(self.utm_zone),
            "utm_hemisphere": self.utm_hemisphere,
            "is_active": self.is_active,
            "show_basemap": bool(self.show_basemap),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReferenceSystem":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            ellipsoid=data.get("ellipsoid", "GRS80"),
            geoid_undulation_N=float(data.get("geoid_undulation_N", 0.0)),
            magnetic_declination_deg=float(data.get("magnetic_declination_deg", 0.0)),
            utm_zone=int(data.get("utm_zone", 30)),
            utm_hemisphere=str(data.get("utm_hemisphere", "N")),
            is_active=bool(data.get("is_active", False)),
            show_basemap=bool(data.get("show_basemap", True)),
            metadata=dict(data.get("metadata", {})),
        )


class PlatformType(str, Enum):
    GENERIC = "GENERIC"
    VEHICLE = "VEHICLE"
    DRONE_X4 = "DRONE_X4"
    CAR = "CAR"
    ROVER = "ROVER"
    BASE_STATION = "BASE_STATION"
    TEST_BENCH = "TEST_BENCH"


@dataclass
class Platform:
    """Modelo universal de plataforma / cuerpo de vehiculo o estacion base."""
    id: str = "PLAT_1"
    name: str = "Plataforma Generica"
    platform_type: str = "GENERIC"              # "GENERIC", "VEHICLE", "DRONE_X4", "CAR", "ROVER", "BASE_STATION", "TEST_BENCH"
    is_fixed: bool = False                      # True para estaciones base fijas / pilares
    origin_geodetic: tuple[float, float, float] | None = None  # (lat_rad, lon_rad, h_m) para estaciones fijas
    has_dimensions: bool = False                # False = sin caja rigida predeterminada (chasis libre)
    length_m: float = 0.0                       # Dimension longitudinal X [m]
    width_m: float = 0.0                        # Dimension transversal Y [m]
    height_m: float = 0.0                       # Dimension vertical Z [m]
    chassis_polygon: list[list[float]] | None = None # Polígono 2D opcional del chasis en b-frame [[x, y], ...]
    chassis_center_b: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0]) # Centroide/offset 3D del chasis [xb, yb, zb]
    sensors: dict[str, Sensor] = field(default_factory=dict)
    pose_e: PlatformPose | None = None          # Pose del centro de plataforma (PLA) en e-frame tras georreferenciación

    def __post_init__(self) -> None:
        if (self.length_m > 0 or self.width_m > 0 or self.height_m > 0 or self.chassis_polygon) and not self.has_dimensions:
            self.has_dimensions = True

    def add_sensor(self, sensor: Sensor) -> None:
        self.sensors[sensor.code] = sensor

    def get_sensor(self, code: str) -> Sensor | None:
        return self.sensors.get(code)

    def remove_sensor(self, code: str) -> bool:
        if code in self.sensors:
            del self.sensors[code]
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "platform_type": self.platform_type,
            "is_fixed": self.is_fixed,
            "origin_geodetic": list(self.origin_geodetic) if self.origin_geodetic else None,
            "has_dimensions": self.has_dimensions,
            "length_m": self.length_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "chassis_polygon": self.chassis_polygon,
            "chassis_center_b": list(self.chassis_center_b),
            "pose_e": self.pose_e.to_dict() if self.pose_e else None,
            "sensors": {k: s.to_dict() for k, s in self.sensors.items()}
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Platform":
        plat = cls(
            id=data.get("id", "PLAT_1"),
            name=data.get("name", "Plataforma"),
            platform_type=data.get("platform_type", "GENERIC"),
            is_fixed=bool(data.get("is_fixed", False)),
            origin_geodetic=tuple(data["origin_geodetic"]) if data.get("origin_geodetic") else None,
            has_dimensions=bool(data.get("has_dimensions", False)),
            length_m=float(data.get("length_m", 0.0)),
            width_m=float(data.get("width_m", 0.0)),
            height_m=float(data.get("height_m", 0.0)),
            chassis_polygon=data.get("chassis_polygon"),
            chassis_center_b=list(data.get("chassis_center_b", [0.0, 0.0, 0.0])),
            pose_e=PlatformPose.from_dict(data["pose_e"]) if data.get("pose_e") else None,
        )
        for s_data in data.get("sensors", {}).values():
            plat.add_sensor(Sensor.from_dict(s_data))
        return plat

    def ensure_polygon(self) -> None:
        """Garantiza la existencia de vértices poligonales a partir de la caja envolvente si no existen."""
        if not self.chassis_polygon and (self.has_dimensions or (self.length_m > 0 and self.width_m > 0)):
            if self.length_m > 0 and self.width_m > 0:
                self.has_dimensions = True
                hl = self.length_m / 2.0
                hw = self.width_m / 2.0
                cx, cy, _ = self.chassis_center_b
                self.chassis_polygon = [
                    [round(cx + hl, 4), round(cy - hw, 4)],
                    [round(cx + hl, 4), round(cy + hw, 4)],
                    [round(cx - hl, 4), round(cy + hw, 4)],
                    [round(cx - hl, 4), round(cy - hw, 4)]
                ]

    def get_bounding_box(self) -> dict[str, float]:
        """Devuelve los límites métricos envolventes (x_min, x_max, y_min, y_max, z_min, z_max)."""
        self.ensure_polygon()
        if self.chassis_polygon:
            pts = np.array(self.chassis_polygon, dtype=np.float64)
            x_min, x_max = float(np.min(pts[:, 0])), float(np.max(pts[:, 0]))
            y_min, y_max = float(np.min(pts[:, 1])), float(np.max(pts[:, 1]))
        else:
            hl = self.length_m / 2.0
            hw = self.width_m / 2.0
            cx, cy, _ = self.chassis_center_b
            x_min, x_max = cx - hl, cx + hl
            y_min, y_max = cy - hw, cy + hw
        hz = self.height_m / 2.0
        cz = self.chassis_center_b[2]
        return {
            "x_min": round(x_min, 4),
            "x_max": round(x_max, 4),
            "y_min": round(y_min, 4),
            "y_max": round(y_max, 4),
            "z_min": round(cz - hz, 4),
            "z_max": round(cz + hz, 4),
        }

    def get_utm_bounding_box(self) -> dict[str, float] | None:
        """
        Calcula la caja envolvente mínima orientada al Norte cartográfico (Bounding Box)
        en coordenadas UTM (Easting, Northing) para la plataforma y todos sus sensores vinculados.
        Retorna un diccionario con min_e, max_e, min_n, max_n, span_e, span_n, center_e, center_n,
        o None si la plataforma no está georreferenciada.
        """
        if not self.pose_e:
            return None

        e_pla = self.pose_e.utm_easting_m
        n_pla = self.pose_e.utm_northing_m

        # Obtener rumbo de cuadrícula (Heading Grid = Yaw - gamma)
        gamma_deg = self.pose_e.convergence_deg
        heading_grid_deg = self.pose_e.yaw_deg - gamma_deg
        psi_rad = math.radians(heading_grid_deg)
        sin_psi = math.sin(psi_rad)
        cos_psi = math.cos(psi_rad)

        all_e: list[float] = [e_pla]
        all_n: list[float] = [n_pla]

        # 1. Vértices del chasis en b-frame proyectados a UTM
        self.ensure_polygon()
        if self.chassis_polygon:
            for pt in self.chassis_polygon:
                xb, yb = float(pt[0]), float(pt[1])
                e_v = e_pla + xb * sin_psi + yb * cos_psi
                n_v = n_pla + xb * cos_psi - yb * sin_psi
                all_e.append(e_v)
                all_n.append(n_v)
        elif self.has_dimensions or (self.length_m > 0 and self.width_m > 0):
            hl = self.length_m / 2.0 if self.length_m > 0 else 1.25
            hw = self.width_m / 2.0 if self.width_m > 0 else 0.75
            cx_b = float(self.chassis_center_b[0]) if hasattr(self, "chassis_center_b") else 0.0
            cy_b = float(self.chassis_center_b[1]) if hasattr(self, "chassis_center_b") else 0.0
            for dx, dy in [(hl, -hw), (hl, hw), (-hl, hw), (-hl, -hw)]:
                xb = cx_b + dx
                yb = cy_b + dy
                e_v = e_pla + xb * sin_psi + yb * cos_psi
                n_v = n_pla + xb * cos_psi - yb * sin_psi
                all_e.append(e_v)
                all_n.append(n_v)

        # 2. Sensores vinculados a la plataforma
        for s in self.sensors.values():
            if s.georef and s.georef.ref_system_id == self.pose_e.ref_system_id:
                all_e.append(float(s.georef.utm_easting_m))
                all_n.append(float(s.georef.utm_northing_m))
            else:
                xb, yb = float(s.lever_arm_b[0]), float(s.lever_arm_b[1])
                e_s = e_pla + xb * sin_psi + yb * cos_psi
                n_s = n_pla + xb * cos_psi - yb * sin_psi
                all_e.append(e_s)
                all_n.append(n_s)

        min_e = min(all_e)
        max_e = max(all_e)
        min_n = min(all_n)
        max_n = max(all_n)

        return {
            "min_e": round(min_e, 4),
            "max_e": round(max_e, 4),
            "min_n": round(min_n, 4),
            "max_n": round(max_n, 4),
            "span_e": round(max_e - min_e, 4),
            "span_n": round(max_n - min_n, 4),
            "center_e": round((min_e + max_e) / 2.0, 4),
            "center_n": round((min_n + max_n) / 2.0, 4),
        }

    def translate(self, dx: float, dy: float, dz: float = 0.0) -> None:
        """Traslada el chasis (vértices del polígono y centroide 3D) por un delta métrico."""
        self.ensure_polygon()
        if self.chassis_polygon:
            for pt in self.chassis_polygon:
                pt[0] = round(pt[0] + dx, 4)
                pt[1] = round(pt[1] + dy, 4)
            pts = np.array(self.chassis_polygon)
            self.length_m = round(float(np.max(pts[:, 0]) - np.min(pts[:, 0])), 4)
            self.width_m = round(float(np.max(pts[:, 1]) - np.min(pts[:, 1])), 4)
        self.chassis_center_b[0] = round(self.chassis_center_b[0] + dx, 4)
        self.chassis_center_b[1] = round(self.chassis_center_b[1] + dy, 4)
        self.chassis_center_b[2] = round(self.chassis_center_b[2] + dz, 4)

    def center_to_origin(self) -> tuple[float, float, float]:
        """Centra la geometría del chasis en el origen (0, 0, 0) de b-frame."""
        bounds = self.get_bounding_box()
        cx = (bounds["x_min"] + bounds["x_max"]) / 2.0
        cy = (bounds["y_min"] + bounds["y_max"]) / 2.0
        cz = (bounds["z_min"] + bounds["z_max"]) / 2.0
        self.translate(-cx, -cy, -cz)
        self.chassis_center_b = [0.0, 0.0, 0.0]
        return (-cx, -cy, -cz)

    def clear_chassis(self) -> None:
        """Restablece el chasis a estado libre sin dimensiones fijadas ni geometría poligonal."""
        self.has_dimensions = False
        self.length_m = 0.0
        self.width_m = 0.0
        self.height_m = 0.0
        self.chassis_polygon = None
        self.chassis_center_b = [0.0, 0.0, 0.0]

    def rotate_plane(self, angle_deg: float, plane: str = "S") -> None:
        """
        Rota el chasis en el plano ortogonal 2D activo.
        - Plano 'S' (Superior): Rotación alrededor del eje Zb (Yaw / Guiñada) en plano Xb-Yb (ΔZb = 0).
        - Plano 'F' (Frontal):  Rotación alrededor del eje Xb (Roll / Alabeo) en plano Yb-Zb (ΔXb = 0).
        - Plano 'L' (Lateral):  Rotación alrededor del eje Yb (Pitch / Cabeceo) en plano Xb-Zb (ΔYb = 0).
        """
        self.ensure_polygon()
        if not self.has_dimensions:
            return

        rad = np.radians(angle_deg)
        cos_a = np.cos(rad)
        sin_a = np.sin(rad)
        p_mode = plane.upper()

        if p_mode == "S":
            # Rotación en plano Xb-Yb (Eje Zb / Yaw)
            if self.chassis_polygon:
                pts = np.array(self.chassis_polygon, dtype=np.float64)
                centroid = np.mean(pts, axis=0)
                rel = pts - centroid
                rot_mat = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
                rotated_rel = rel @ rot_mat.T
                rotated_pts = rotated_rel + centroid

                self.chassis_polygon = [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in rotated_pts]
                pts_new = np.array(self.chassis_polygon)
                self.length_m = round(float(np.max(pts_new[:, 0]) - np.min(pts_new[:, 0])), 4)
                self.width_m = round(float(np.max(pts_new[:, 1]) - np.min(pts_new[:, 1])), 4)
            else:
                l_old, w_old = self.length_m, self.width_m
                self.length_m = round(l_old * abs(cos_a) + w_old * abs(sin_a), 4)
                self.width_m = round(l_old * abs(sin_a) + w_old * abs(cos_a), 4)

        elif p_mode == "F":
            # Rotación en plano Yb-Zb (Eje Xb / Roll) -> transforma Ancho (Yb) y Alto (Zb)
            w_old = self.width_m
            h_old = self.height_m

            # Intercambio exacto para múltiplos de 90°
            is_90_mult = abs(abs(angle_deg) % 180.0 - 90.0) < 1e-3
            is_180_mult = abs(abs(angle_deg) % 180.0) < 1e-3

            if is_90_mult:
                w_new, h_new = h_old, w_old
            elif is_180_mult:
                w_new, h_new = w_old, h_old
            else:
                w_new = max(0.05, w_old * abs(cos_a) + h_old * abs(sin_a))
                h_new = max(0.05, w_old * abs(sin_a) + h_old * abs(cos_a))

            self.width_m = round(float(w_new), 4)
            self.height_m = round(float(h_new), 4)

            # Escalar proporcionalmente los vértices Yb del polígono de chasis
            if self.chassis_polygon and w_old > 1e-4:
                scale_y = w_new / w_old
                cy = self.chassis_center_b[1]
                for p in self.chassis_polygon:
                    p[1] = round(float(cy + (p[1] - cy) * scale_y), 4)

        elif p_mode == "L":
            # Rotación en plano Xb-Zb (Eje Yb / Pitch) -> transforma Largo (Xb) y Alto (Zb)
            l_old = self.length_m
            h_old = self.height_m

            is_90_mult = abs(abs(angle_deg) % 180.0 - 90.0) < 1e-3
            is_180_mult = abs(abs(angle_deg) % 180.0) < 1e-3

            if is_90_mult:
                l_new, h_new = h_old, l_old
            elif is_180_mult:
                l_new, h_new = l_old, h_old
            else:
                l_new = max(0.05, l_old * abs(cos_a) + h_old * abs(sin_a))
                h_new = max(0.05, l_old * abs(sin_a) + h_old * abs(cos_a))

            self.length_m = round(float(l_new), 4)
            self.height_m = round(float(h_new), 4)

            # Escalar proporcionalmente los vértices Xb del polígono de chasis
            if self.chassis_polygon and l_old > 1e-4:
                scale_x = l_new / l_old
                cx = self.chassis_center_b[0]
                for p in self.chassis_polygon:
                    p[0] = round(float(cx + (p[0] - cx) * scale_x), 4)


    def scale_dimensions(self, factor_l: float, factor_w: float, factor_h: float = 1.0) -> None:
        """Escala las dimensiones y el polígono del chasis respecto a su centroide."""
        if not self.has_dimensions:
            return
        self.ensure_polygon()
        if self.chassis_polygon:
            pts = np.array(self.chassis_polygon, dtype=np.float64)
            centroid = np.mean(pts, axis=0)
            rel = pts - centroid
            rel[:, 0] *= factor_l
            rel[:, 1] *= factor_w
            scaled_pts = rel + centroid
            self.chassis_polygon = [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in scaled_pts]
            pts_new = np.array(self.chassis_polygon)
            self.length_m = round(float(np.max(pts_new[:, 0]) - np.min(pts_new[:, 0])), 4)
            self.width_m = round(float(np.max(pts_new[:, 1]) - np.min(pts_new[:, 1])), 4)
        else:
            self.length_m = round(self.length_m * factor_l, 4)
            self.width_m = round(self.width_m * factor_w, 4)
        self.height_m = round(self.height_m * factor_h, 4)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "Platform":
        return cls.from_dict(json.loads(json_str))

    def to_txt(self) -> str:
        """Serializa la plataforma y sus sensores a un archivo de texto .txt legible."""
        lines = [
            "# ==============================================================================",
            "# PyGSN - DEFINICIÓN DE PLATAFORMA Y SENSORES (b-frame)",
            f"# PLATAFORMA: {self.name} | TIPO: {self.platform_type}",
            f"# DIMENSIONES (Largo Ancho Alto): {self.length_m:.4f} {self.width_m:.4f} {self.height_m:.4f}",
            "# Origen b-frame de referencia: [0, 0, 0] (Plataforma)",
            "#",
            "# Formato de columnas:",
            "# SENSOR   TIPO         X1(m)       X2(m)       X3(m)     ALPHA(deg)   BETA(deg)   GAMMA(deg)  NOMBRE",
            "# =============================================================================="
        ]
        type_names = {
            SensorType.PLATFORM_ORIGIN: "PLATAFORMA",
            SensorType.INS: "INERCIAL",
            SensorType.GNSS: "RECEPTOR",
            SensorType.CAMERA: "CAMARA",
            SensorType.LIDAR: "LIDAR",
            SensorType.ODOMETER: "ODOMETRO",
            SensorType.OTHER: "OTRO"
        }
        for code, s in self.sensors.items():
            t_str = type_names.get(s.sensor_type, "OTRO")
            x1, x2, x3 = s.lever_arm_b
            a, b, c = s.boresight_deg
            name_clean = s.name.replace(" ", "_")
            lines.append(f"{code:<8s} {t_str:<12s} {x1:10.4f} {x2:10.4f} {x3:10.4f}  {a:11.6f} {b:11.6f} {c:11.6f}  {name_clean}")
        return "\n".join(lines) + "\n"

    def import_sensors_from_table(self, file_path: Any, ref_system_id: str = "") -> list["Sensor"]:
        """
        Importa sensores y sus atributos (lever-arms b-frame, boresight y observables de campo)
        a partir de una tabla en formato Excel (.xlsx), CSV (.csv) o texto (.txt / .dat).
        Admite encabezados flexibles (ej. 'Sensores', 'X1_m', 'alpha_deg', 'Latitud', 'roll_deg', etc.)
        Si no se detectan encabezados tabulares en archivos de texto, aplica fallback automático
        al formato clásico de 'sensores.txt' (7 u 8+ columnas).
        """
        from pathlib import Path
        import re
        import csv

        path = Path(file_path)
        rows_data: list[dict[str, Any]] = []
        is_xlsx = path.suffix.lower() == ".xlsx"

        if is_xlsx:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(path, data_only=True)
                sheet = wb.active
                raw_rows = []
                for r in sheet.iter_rows(values_only=True):
                    if any(v is not None and str(v).strip() != "" for v in r):
                        raw_rows.append(list(r))
                if raw_rows:
                    header = [str(c) if c is not None else "" for c in raw_rows[0]]
                    for row in raw_rows[1:]:
                        row_dict = {}
                        for i, val in enumerate(row):
                            if i < len(header):
                                row_dict[header[i]] = val
                        rows_data.append(row_dict)
            except Exception as e:
                raise ValueError(f"Error al leer archivo Excel '{path.name}': {e}")
        else:
            # Archivo de texto / CSV / TSV
            content = None
            for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    with open(path, "r", encoding=enc) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            if content is None:
                raise ValueError(f"No se pudo decodificar el archivo '{path.name}'")

            lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
            if not lines:
                return []

            first_line = lines[0]
            delim = None
            if "\t" in first_line:
                delim = "\t"
            elif ";" in first_line:
                delim = ";"
            elif "," in first_line:
                delim = ","

            if delim:
                reader = csv.DictReader(lines, delimiter=delim)
                for r in reader:
                    rows_data.append(dict(r))
            else:
                parts_0 = first_line.split()
                has_header = any(
                    re.sub(r'[\s_]+', '', p.lower()) in (
                        "sensores", "sensor", "nombre", "x1m", "x1", "alphadeg", "latitud", "rolldeg"
                    ) for p in parts_0
                )
                if has_header:
                    header = parts_0
                    for line in lines[1:]:
                        parts = line.split()
                        row_dict = {}
                        for i, p in enumerate(parts):
                            if i < len(header):
                                row_dict[header[i]] = p
                        rows_data.append(row_dict)
                else:
                    return self.import_sensors_from_txt(content)

        if not rows_data:
            return []

        # Normalización de cabeceras de columnas
        sample_keys = list(rows_data[0].keys())
        col_map: dict[str, str] = {}
        for k in sample_keys:
            k_clean = re.sub(r'[\s_]+', '', str(k).strip().lower())
            if k_clean in ("sensores", "sensor", "nombre", "name", "code", "id"):
                col_map["name"] = k
            elif k_clean in ("x1m", "x1", "xm", "x", "xb", "leverx") or k_clean.startswith("x1"):
                col_map["x1"] = k
            elif k_clean in ("x2m", "x2", "ym", "y", "yb", "levery") or k_clean.startswith("x2"):
                col_map["x2"] = k
            elif k_clean in ("x3m", "x3", "zm", "z", "zb", "leverz") or k_clean.startswith("x3"):
                col_map["x3"] = k
            elif k_clean in ("alphadeg", "alpha", "alfadeg", "alfa", "a") or k_clean.startswith("alpha") or k_clean.startswith("alfa"):
                col_map["alpha"] = k
            elif k_clean in ("betadeg", "beta", "b") or k_clean.startswith("beta"):
                col_map["beta"] = k
            elif k_clean in ("gammadeg", "gamma", "c") or k_clean.startswith("gamma"):
                col_map["gamma"] = k
            elif k_clean in ("latitud", "latitude", "lat", "phi") or k_clean.startswith("lat"):
                col_map["lat"] = k
            elif k_clean in ("longitud", "longitude", "lon", "lambda") or k_clean.startswith("lon"):
                col_map["lon"] = k
            elif k_clean in ("helip", "hellip", "h", "helip.", "cotaelipsoidal", "alturaelip") or k_clean.startswith("helip"):
                col_map["h_elip"] = k
            elif k_clean in ("rolldeg", "roll", "alabeo") or k_clean.startswith("roll"):
                col_map["roll_obs"] = k
            elif k_clean in ("pitchdeg", "pitch", "cabeceo") or k_clean.startswith("pitch"):
                col_map["pitch_obs"] = k
            elif k_clean in ("yawdeg", "yaw", "guinada", "rumbo") or k_clean.startswith("yaw"):
                col_map["yaw_obs"] = k

        if "name" not in col_map:
            col_map["name"] = sample_keys[0]

        imported_sensors: list[Sensor] = []

        def _to_float(v: Any, field_name: str, row_idx: int, default: float = 0.0) -> float:
            if v is None:
                return default
            s = str(v).strip()
            if not s or s.lower() == "none" or s == "-":
                return default
            # Soporte transparente para comas decimales
            s_clean = s.replace(",", ".")
            try:
                val = float(s_clean)
                if not math.isfinite(val):
                    raise ValueError("Valor no finito (NaN o Inf)")
                return val
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Fila {row_idx} ({raw_name}), campo '{field_name}': "
                    f"el valor '{s}' no es un número válido ({exc})."
                )

        for row_idx, row in enumerate(rows_data, start=2):
            raw_name = row.get(col_map["name"])
            if raw_name is None or str(raw_name).strip() == "":
                continue
            name_str = str(raw_name).strip()
            code_upper = name_str.upper()

            # Extraer lever-arm
            x1 = _to_float(row.get(col_map.get("x1", "")), "x1", row_idx)
            x2 = _to_float(row.get(col_map.get("x2", "")), "x2", row_idx)
            x3 = _to_float(row.get(col_map.get("x3", "")), "x3", row_idx)
            lever_arm = np.array([x1, x2, x3], dtype=np.float64)

            # Extraer boresight
            alpha = _to_float(row.get(col_map.get("alpha", "")), "alpha", row_idx)
            beta = _to_float(row.get(col_map.get("beta", "")), "beta", row_idx)
            gamma = _to_float(row.get(col_map.get("gamma", "")), "gamma", row_idx)
            boresight = (alpha, beta, gamma)

            # Extraer observables de campo
            obs: SensorObservation | None = None
            lat_val = row.get(col_map.get("lat", ""))
            lon_val = row.get(col_map.get("lon", ""))
            h_val = row.get(col_map.get("h_elip", ""))

            has_geo = (lat_val is not None and str(lat_val).strip() != "" and str(lat_val).strip().lower() != "none" and
                       lon_val is not None and str(lon_val).strip() != "" and str(lon_val).strip().lower() != "none")

            if has_geo:
                try:
                    lat_deg = parse_dms_or_deg(str(lat_val))
                    lon_deg = parse_dms_or_deg(str(lon_val))
                    h_m = _to_float(h_val, "h_elip", row_idx, default=0.0)
                    obs = SensorObservation(ref_system_id=ref_system_id, geodetic_deg=(lat_deg, lon_deg, h_m))
                except Exception as exc:
                    raise ValueError(f"Fila {row_idx} ({raw_name}): error en coordenadas geodésicas ({exc}).")

            roll_val = row.get(col_map.get("roll_obs", ""))
            pitch_val = row.get(col_map.get("pitch_obs", ""))
            yaw_val = row.get(col_map.get("yaw_obs", ""))

            has_att = (roll_val is not None and str(roll_val).strip() != "" and str(roll_val).strip().lower() != "none" and
                       pitch_val is not None and str(pitch_val).strip() != "" and str(pitch_val).strip().lower() != "none" and
                       yaw_val is not None and str(yaw_val).strip() != "" and str(yaw_val).strip().lower() != "none")

            if has_att:
                try:
                    r_deg = float(str(roll_val).replace(",", "."))
                    p_deg = float(str(pitch_val).replace(",", "."))
                    y_deg = float(str(yaw_val).replace(",", "."))
                    if obs is None:
                        obs = SensorObservation(ref_system_id=ref_system_id, attitude_rpy_deg=(r_deg, p_deg, y_deg))
                    else:
                        obs.attitude_rpy_deg = (r_deg, p_deg, y_deg)
                except Exception as exc:
                    raise ValueError(f"Fila {row_idx} ({raw_name}): error en ángulos de actitud ({exc}).")

            # Inferencia del tipo de sensor
            if has_geo or "REC" in code_upper or "GNSS" in code_upper or "GPS" in code_upper:
                stype = SensorType.GNSS
            elif has_att or "INS" in code_upper or "IMU" in code_upper:
                stype = SensorType.INS
            elif "CAM" in code_upper:
                stype = SensorType.CAMERA
            elif "LIDAR" in code_upper:
                stype = SensorType.LIDAR
            elif "ODO" in code_upper:
                stype = SensorType.ODOMETER
            elif code_upper in ("PLA", "PLATAFORMA", "ORIGEN", "CHASIS"):
                stype = SensorType.PLATFORM_ORIGIN
            else:
                stype = infer_sensor_type_from_code(code_upper)

            # Buscar si el sensor ya existe en la plataforma (por código o por nombre)
            existing_sensor = None
            if code_upper in self.sensors:
                existing_sensor = self.sensors[code_upper]
            else:
                for s in self.sensors.values():
                    if s.name.strip().upper() == code_upper or s.code.strip().upper() == code_upper:
                        existing_sensor = s
                        break

            if existing_sensor:
                existing_sensor.lever_arm_b = lever_arm
                existing_sensor.boresight_deg = boresight
                existing_sensor.sensor_type = stype
                if obs is not None:
                    existing_sensor.observation = obs
                imported_sensors.append(existing_sensor)
            else:
                new_s = Sensor(
                    code=code_upper,
                    name=name_str,
                    sensor_type=stype,
                    lever_arm_b=lever_arm,
                    boresight_deg=boresight,
                    observation=obs
                )
                self.add_sensor(new_s)
                imported_sensors.append(new_s)

        return imported_sensors

    def import_sensors_from_txt(self, txt_content: str) -> list[Sensor]:
        """
        Importa sensores a partir del contenido de un archivo de texto.
        Soporta formato de 7 columnas (code, x1, x2, x3, alpha, beta, gamma) como 'sensores.txt'
        y formato de 8+ columnas (code, tipo, x1, x2, x3, alpha, beta, gamma, [nombre]).
        Retorna la lista de sensores importados.
        """
        imported: list[Sensor] = []
        type_map = {
            "PLATAFORMA": SensorType.PLATFORM_ORIGIN,
            "ORIGEN": SensorType.PLATFORM_ORIGIN,
            "PLA": SensorType.PLATFORM_ORIGIN,
            "CHASIS": SensorType.PLATFORM_ORIGIN,
            "BODY": SensorType.PLATFORM_ORIGIN,
            "INERCIAL": SensorType.INS,
            "INS": SensorType.INS,
            "IMU": SensorType.INS,
            "RECEPTOR": SensorType.GNSS,
            "GNSS": SensorType.GNSS,
            "GPS": SensorType.GNSS,
            "CAMARA": SensorType.CAMERA,
            "CAM": SensorType.CAMERA,
            "CAMERA": SensorType.CAMERA,
            "LIDAR": SensorType.LIDAR,
            "ODOMETRO": SensorType.ODOMETER,
            "ODOMETER": SensorType.ODOMETER,
            "OTRO": SensorType.OTHER,
            "OTHER": SensorType.OTHER
        }

        for line in txt_content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 4:
                continue

            code = parts[0].upper()
            if code.lower() in ("sensor", "id", "code", "nombre"):
                continue

            # Detectar si la segunda columna es numérica (formato de 7 columnas) o texto (tipo)
            try:
                float(parts[1])
                is_numeric_second = True
            except ValueError:
                is_numeric_second = False

            try:
                if is_numeric_second:
                    # Formato sensores.txt: code, x1, x2, x3, [alpha, beta, gamma, [name]]
                    x1 = float(parts[1])
                    x2 = float(parts[2])
                    x3 = float(parts[3])
                    alpha = float(parts[4]) if len(parts) > 4 else 0.0
                    beta = float(parts[5]) if len(parts) > 5 else 0.0
                    gamma = float(parts[6]) if len(parts) > 6 else 0.0
                    name = parts[7].replace("_", " ") if len(parts) > 7 else code
                    stype = infer_sensor_type_from_code(code)
                else:
                    # Formato extendido: code, tipo, x1, x2, x3, [alpha, beta, gamma, [name]]
                    tipo_raw = parts[1].upper()
                    stype = type_map.get(tipo_raw, infer_sensor_type_from_code(code))
                    x1 = float(parts[2])
                    x2 = float(parts[3])
                    x3 = float(parts[4])
                    alpha = float(parts[5]) if len(parts) > 5 else 0.0
                    beta = float(parts[6]) if len(parts) > 6 else 0.0
                    gamma = float(parts[7]) if len(parts) > 7 else 0.0
                    name = parts[8].replace("_", " ") if len(parts) > 8 else code

                arm = np.array([x1, x2, x3], dtype=np.float64)
                sens = Sensor(
                    code=code,
                    name=name,
                    sensor_type=stype,
                    lever_arm_b=arm,
                    boresight_deg=(alpha, beta, gamma)
                )
                self.add_sensor(sens)
                imported.append(sens)
            except ValueError:
                continue

        return imported

    @classmethod
    def from_txt(cls, txt_content: str) -> "Platform":
        """
        Carga una plataforma y sus sensores desde un archivo de texto .txt.
        Ignora lineas de comentarios (#) y lineas vacias.
        """
        plat = cls(name="Plataforma desde TXT")
        for line in txt_content.splitlines():
            line = line.strip()
            if line.startswith("#"):
                upper = line.upper()
                if "PLATAFORMA:" in upper:
                    try:
                        part = line.split("PLATAFORMA:")[1].split("|")[0].strip()
                        if part:
                            plat.name = part
                    except Exception:
                        pass
                if "DIMENSIONES" in upper:
                    try:
                        vals = [float(v) for v in line.split(":")[-1].strip().split()]
                        if len(vals) >= 3:
                            plat.length_m, plat.width_m, plat.height_m = vals[0], vals[1], vals[2]
                    except Exception:
                        pass
        plat.import_sensors_from_txt(txt_content)
        return plat

    def import_observations_from_txt(self, txt_content: str, ref_system_id: str = "") -> dict[str, int]:
        """
        Importa observaciones de campo (GNSS lat/lon/h o INS roll/pitch/yaw)
        asociándolas a los sensores existentes de la plataforma.
        Formato estándar de 4 columnas delimitadas por espacios o tabulaciones:
          SENSOR   LATITUD            LONGITUD           H_ELIP     (para GNSS: sexagesimal DMS o decimal)
          SENSOR   ROLL(deg)          PITCH(deg)         YAW(deg)   (para INS: grados decimales)
        Retorna diccionario con el recuento de observaciones importadas: {"gnss": count, "attitude": count}.
        """
        counts = {"gnss": 0, "attitude": 0}

        for line in txt_content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 4:
                continue

            code_raw = parts[0].strip().upper()
            if code_raw.lower() in ("sensor", "id", "code", "nombre", "dispositivo"):
                continue

            target_sensor = None
            # Prioridad 1: Coincidencia por Nombre asignado por el usuario (limpio de espacios, insensible a mayúsculas)
            for s in self.sensors.values():
                if s.name and s.name.strip().upper() == code_raw:
                    target_sensor = s
                    break
            # Prioridad 2: Coincidencia por Código interno (por si el fichero o sensor usan el código)
            if not target_sensor:
                for s in self.sensors.values():
                    if s.code and s.code.strip().upper() == code_raw:
                        target_sensor = s
                        break
            if not target_sensor:
                continue

            sens = target_sensor

            # Caso INS / IMU: Roll, Pitch, Yaw en grados
            if sens.sensor_type == SensorType.INS or "INS" in code_raw or "IMU" in code_raw:
                try:
                    r = float(parts[1])
                    p = float(parts[2])
                    y = float(parts[3])
                    if not sens.observation:
                        sens.observation = SensorObservation(ref_system_id=ref_system_id)
                    sens.observation.attitude_rpy_deg = (r, p, y)
                    if ref_system_id:
                        sens.observation.ref_system_id = ref_system_id
                    counts["attitude"] += 1
                except ValueError:
                    pass
                continue

            # Caso GNSS / Posición geodésica: Latitud, Longitud, Altura elipsoidal
            try:
                lat_deg = parse_dms_or_deg(parts[1])
                lon_deg = parse_dms_or_deg(parts[2])
                h_m = float(parts[3])
                if not sens.observation:
                    sens.observation = SensorObservation(ref_system_id=ref_system_id)
                sens.observation.geodetic_deg = (lat_deg, lon_deg, h_m)
                if ref_system_id:
                    sens.observation.ref_system_id = ref_system_id
                counts["gnss"] += 1
            except ValueError:
                pass

        return counts

    def apply_georeferencing_solution(
        self,
        solution: Any,
        reference_system: Any,
        method_str: str = "SVD+INS"
    ) -> int:
        """
        Aplica los resultados del cálculo de georreferenciación a la plataforma y a sus sensores.
        Actualiza self.pose_e con PlatformPose y sens.georef con SensorGeoref para cada sensor.
        Retorna la cantidad de sensores actualizados.
        """
        from .geodesy import utm_projection
        sol = solution
        srt = reference_system

        pla_ecef = sol.pla_origin_ecef
        lat_d = float(np.degrees(sol.pla_origin_lat_rad))
        lon_d = float(np.degrees(sol.pla_origin_lon_rad))
        h_m = float(sol.pla_origin_h_ellip)

        ell = srt.get_ellipsoid() if hasattr(srt, "get_ellipsoid") else getattr(srt, "ellipsoid_obj", None)
        easting, northing, zone = utm_projection(
            sol.pla_origin_lat_rad, sol.pla_origin_lon_rad,
            zone=srt.utm_zone, hemisphere=srt.utm_hemisphere, ell=ell
        )
        h_orto = h_m - srt.geoid_undulation_N
        att = sol.attitude_ins_total_deg if method_str == "INS" else sol.attitude_gnss_deg
        dcm_b2e = sol.Cb2n_ins @ sol.Ce2n_centroid if method_str == "INS" else (sol.Ce2n_centroid.T @ sol.Cb2n_gnss).T

        self.pose_e = PlatformPose(
            ref_system_id=srt.id,
            ref_system_name=srt.name or srt.id,
            ecef=pla_ecef,
            lat_deg=lat_d,
            lon_deg=lon_d,
            h_ellip_m=h_m,
            utm_easting_m=float(easting),
            utm_northing_m=float(northing),
            utm_zone=int(zone),
            utm_hemisphere=srt.utm_hemisphere,
            h_ortho_m=float(h_orto),
            attitude_rpy_deg=att,
            dcm_b2e=[[float(v) for v in row] for row in dcm_b2e],
            method=method_str,
        )

        count_updated = 0
        results_map = sol.results_ins if method_str == "INS" else sol.results_gnss

        for sens_code, sens in self.sensors.items():
            if sens_code in results_map:
                sr = results_map[sens_code]
                sens.georef = SensorGeoref(
                    ref_system_id=srt.id,
                    ref_system_name=srt.name or srt.id,
                    ecef=sr.ecef,
                    lat_deg=float(np.degrees(sr.lat_rad)),
                    lon_deg=float(np.degrees(sr.lon_rad)),
                    h_ellip_m=float(sr.h_ellip),
                    utm_easting_m=float(sr.easting),
                    utm_northing_m=float(sr.northing),
                    utm_zone=int(sr.zone),
                    utm_hemisphere=srt.utm_hemisphere,
                    h_ortho_m=float(sr.h_orto),
                    computed_via=method_str,
                )
                count_updated += 1

        return count_updated




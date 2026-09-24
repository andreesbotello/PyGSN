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


@dataclass
class Sensor:
    """Modelo de un sensor instalado en la plataforma."""
    code: str                                    # Identificador corto (ej. "REC2", "INS")
    name: str                                    # Nombre descriptivo
    sensor_type: SensorType = SensorType.OTHER
    lever_arm_b: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64)) # [x1, x2, x3] en b-frame (m)
    boresight_deg: tuple[float, float, float] = (0.0, 0.0, 0.0) # (alpha, beta, gamma) en deg
    
    # Observaciones opcionales asociadas al sensor
    geodetic_obs: tuple[np.float64, np.float64, np.float64] | None = None  # (lat_rad, lon_rad, h_m)
    attitude_obs_deg: tuple[float, float, float] | None = None              # (roll, pitch, yaw) deg

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "sensor_type": self.sensor_type.value,
            "lever_arm_b": self.lever_arm_b.tolist(),
            "boresight_deg": list(self.boresight_deg),
            "geodetic_obs": [float(x) for x in self.geodetic_obs] if self.geodetic_obs else None,
            "attitude_obs_deg": list(self.attitude_obs_deg) if self.attitude_obs_deg else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Sensor":
        return cls(
            code=data["code"],
            name=data.get("name", data["code"]),
            sensor_type=SensorType(data.get("sensor_type", "OTHER")),
            lever_arm_b=np.array(data["lever_arm_b"], dtype=np.float64),
            boresight_deg=tuple(data.get("boresight_deg", (0.0, 0.0, 0.0))),
            geodetic_obs=tuple(data["geodetic_obs"]) if data.get("geodetic_obs") else None,
            attitude_obs_deg=tuple(data["attitude_obs_deg"]) if data.get("attitude_obs_deg") else None,
        )


@dataclass
class Platform:
    """Modelo universal de plataforma / cuerpo del vehiculo."""
    name: str = "Plataforma Generica"
    platform_type: str = "GENERIC"              # "GENERIC", "DRONE_X4", "CAR", "ROVER"
    length_m: float = 1.0                       # Dimension longitudinal X [m]
    width_m: float = 0.8                        # Dimension transversal Y [m]
    height_m: float = 0.2                       # Dimension vertical Z [m]
    sensors: dict[str, Sensor] = field(default_factory=dict)

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
            "name": self.name,
            "platform_type": self.platform_type,
            "length_m": self.length_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "sensors": {k: s.to_dict() for k, s in self.sensors.items()}
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Platform":
        plat = cls(
            name=data.get("name", "Plataforma"),
            platform_type=data.get("platform_type", "GENERIC"),
            length_m=float(data.get("length_m", 1.0)),
            width_m=float(data.get("width_m", 0.8)),
            height_m=float(data.get("height_m", 0.2)),
        )
        for s_data in data.get("sensors", {}).values():
            plat.add_sensor(Sensor.from_dict(s_data))
        return plat

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "Platform":
        return cls.from_dict(json.loads(json_str))

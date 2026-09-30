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
        )
        for s_data in data.get("sensors", {}).values():
            plat.add_sensor(Sensor.from_dict(s_data))
        return plat

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

    @classmethod
    def from_txt(cls, txt_content: str) -> "Platform":
        """
        Carga una plataforma y sus sensores desde un archivo de texto .txt.
        Ignora lineas de comentarios (#) y lineas vacias.
        """
        plat = cls(name="Plataforma desde TXT")
        type_map = {
            "PLATAFORMA": SensorType.PLATFORM_ORIGIN,
            "ORIGEN": SensorType.PLATFORM_ORIGIN,
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
            if not line:
                continue

            # Parsear metadatos de comentarios
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
                continue

            parts = line.split()
            if len(parts) < 4:
                continue

            # Formato esperado:
            # 1: code
            # 2: tipo
            # 3, 4, 5: x1, x2, x3
            # 6, 7, 8: alpha, beta, gamma (opcional)
            # 9: nombre (opcional)
            code = parts[0].upper()
            tipo_raw = parts[1].upper()
            stype = type_map.get(tipo_raw, SensorType.OTHER)

            try:
                x1 = float(parts[2])
                x2 = float(parts[3])
                x3 = float(parts[4])
                arm = np.array([x1, x2, x3], dtype=np.float64)

                alpha, beta, gamma = 0.0, 0.0, 0.0
                name = code
                if len(parts) >= 8:
                    alpha = float(parts[5])
                    beta = float(parts[6])
                    gamma = float(parts[7])
                if len(parts) >= 9:
                    name = parts[8].replace("_", " ")

                plat.add_sensor(Sensor(
                    code=code,
                    name=name,
                    sensor_type=stype,
                    lever_arm_b=arm,
                    boresight_deg=(alpha, beta, gamma)
                ))
            except ValueError:
                # Linea de cabecera no comentada
                continue

        return plat


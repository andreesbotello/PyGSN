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
            "lever_arm_b": [float(x) for x in self.lever_arm_b],
            "boresight_deg": [float(x) for x in self.boresight_deg],
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


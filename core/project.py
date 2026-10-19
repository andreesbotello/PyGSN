"""
PyGSN - Core Project Module
===========================
Gestion integral de proyectos de navegacion y rigs multisensores (.pygsn):
- Encapsula la plataforma de vehiculo, los sensores instalados y los assets 3D de carroceria.
- Almacena parametros geodésicos (elipsoide GRS80/WGS84, ondulacion geoidal, zona UTM).
- Serializacion y deserializacion estructurada en formato JSON estandar.
- Interoperabilidad con ficheros de calibracion .txt.
"""

from dataclasses import dataclass, field, InitVar
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .assets import VehicleMesh
from .models import Platform, Sensor, ReferenceSystem


class Project:
    """
    Contenedor principal de un proyecto de ingenieria en PyGSN.
    Soporta jerarquia semantica multi-plataforma (vehiculo principal, estaciones base fijas, rigs)
    y gestion desacoplada de Sistemas de Referencia Terrestres (SRT / e-frame).
    """
    def __init__(
        self,
        name: str = "Proyecto sin titulo",
        description: str = "Proyecto de Georreferenciacion de Sensores y Navegacion",
        ellipsoid_name: str = "GRS80",
        platforms: dict[str, Platform] | None = None,
        active_platform_id: str = "",
        platform: Platform | None = None,
        reference_systems: dict[str, ReferenceSystem] | None = None,
        active_reference_system_id: str = "",
        asset: VehicleMesh | None = None,
        metadata: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None
    ):
        self.name = name
        self.description = description
        self.ellipsoid_name = ellipsoid_name
        self.platforms: dict[str, Platform] = platforms if platforms is not None else {}
        self.active_platform_id = active_platform_id

        if platform is not None:
            pid = getattr(platform, "id", None) or "PLAT_1"
            platform.id = pid
            self.platforms[pid] = platform
            self.active_platform_id = pid
        elif self.platforms:
            if not self.active_platform_id or self.active_platform_id not in self.platforms:
                self.active_platform_id = next(iter(self.platforms.keys()))
        else:
            self.active_platform_id = ""

        self.asset = asset if asset is not None else VehicleMesh.create_box_vehicle(name="Chasis Vehiculo")
        self.metadata = metadata if metadata is not None else {
            "created_at": datetime.now().isoformat(),
            "author": "PyGSN Engineer",
            "version": "1.0.0"
        }
        self.config = config if config is not None else {}

        # Sistemas de Referencia Terrestres (SRT / e-frame)
        self.reference_systems: dict[str, ReferenceSystem] = reference_systems if reference_systems is not None else {}
        self.active_reference_system_id = active_reference_system_id

        if self.reference_systems and (not self.active_reference_system_id or self.active_reference_system_id not in self.reference_systems):
            self.active_reference_system_id = next(iter(self.reference_systems.keys()))

    @property
    def platform(self) -> Platform | None:
        """Devuelve la plataforma activa o None si no hay plataformas en el proyecto."""
        if self.active_platform_id and self.active_platform_id in self.platforms:
            return self.platforms[self.active_platform_id]
        if self.platforms:
            return next(iter(self.platforms.values()))
        return None

    @platform.setter
    def platform(self, p: Platform | None):
        if p is None:
            return
        pid = getattr(p, "id", None) or f"PLAT_{len(self.platforms) + 1}"
        p.id = pid
        self.platforms[pid] = p
        self.active_platform_id = pid

    def add_platform(self, plat: Platform, set_active: bool = True) -> str:
        """Anade una nueva plataforma al proyecto (vehiculo o estacion base)."""
        if not plat.id:
            plat.id = f"PLAT_{len(self.platforms) + 1}"
        self.platforms[plat.id] = plat
        if set_active or len(self.platforms) == 1:
            self.active_platform_id = plat.id
        return plat.id

    def get_platform(self, plat_id: str) -> Platform | None:
        return self.platforms.get(plat_id)

    def set_active_platform(self, plat_id: str):
        if plat_id in self.platforms:
            self.active_platform_id = plat_id

    def remove_platform(self, plat_id: str) -> bool:
        """Elimina una plataforma del proyecto y reajusta la plataforma activa."""
        if plat_id in self.platforms:
            del self.platforms[plat_id]
            if self.active_platform_id == plat_id:
                self.active_platform_id = next(iter(self.platforms.keys())) if self.platforms else None
            return True
        return False

    # -------------------------------------------------------------------------
    # Gestion de Sistemas de Referencia Terrestres (SRT / e-frame)
    # -------------------------------------------------------------------------
    def add_reference_system(self, rs: ReferenceSystem, set_active: bool = False) -> str:
        """Añade un nuevo sistema de referencia terrestre (SRT) al proyecto."""
        if not rs.id:
            rs.id = f"SRT_{len(self.reference_systems) + 1:02d}"
        self.reference_systems[rs.id] = rs
        if set_active or len(self.reference_systems) == 1:
            self.set_active_reference_system(rs.id)
        return rs.id

    def get_reference_system(self, rs_id: str) -> ReferenceSystem | None:
        """Devuelve el sistema de referencia terrestre por su identificador."""
        return self.reference_systems.get(rs_id)

    def set_active_reference_system(self, rs_id: str) -> bool:
        """Establece el sistema de referencia terrestre activo del proyecto."""
        if rs_id in self.reference_systems:
            self.active_reference_system_id = rs_id
            for rid, rs in self.reference_systems.items():
                rs.is_active = (rid == rs_id)
            # Sincronizar compatibilidad con config legado
            act = self.reference_systems[rs_id]
            self.ellipsoid_name = act.ellipsoid
            self.config["utm_zone"] = act.utm_zone if act.utm_hemisphere == "N" else -act.utm_zone
            self.config["geoid_undulation_n"] = act.geoid_undulation_N
            self.config["mag_declination_deg"] = act.magnetic_declination_deg
            return True
        return False

    def get_active_reference_system(self) -> ReferenceSystem | None:
        """Devuelve el sistema de referencia terrestre activo o None."""
        if self.active_reference_system_id and self.active_reference_system_id in self.reference_systems:
            return self.reference_systems[self.active_reference_system_id]
        if self.reference_systems:
            return next(iter(self.reference_systems.values()))
        return None

    def remove_reference_system(self, rs_id: str) -> bool:
        """Elimina un sistema de referencia terrestre y reajusta el SRT activo."""
        if rs_id in self.reference_systems:
            del self.reference_systems[rs_id]
            if self.active_reference_system_id == rs_id:
                if self.reference_systems:
                    new_active = next(iter(self.reference_systems.keys()))
                    self.set_active_reference_system(new_active)
                else:
                    self.active_reference_system_id = ""
            return True
        return False

    # -------------------------------------------------------------------------
    # Serializacion y Deserializacion
    # -------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "PyGSN_Project",
            "version": self.metadata.get("version", "1.0.0"),
            "name": self.name,
            "description": self.description,
            "ellipsoid_name": self.ellipsoid_name,
            "metadata": self.metadata,
            "config": self.config,
            "active_platform_id": self.active_platform_id,
            "platforms": {k: p.to_dict() for k, p in self.platforms.items()},
            "active_reference_system_id": self.active_reference_system_id,
            "reference_systems": {k: rs.to_dict() for k, rs in self.reference_systems.items()},
            # Compatibilidad con parsers legacy
            "platform": self.platform.to_dict() if self.platform else None,
            "asset": self.asset.to_dict() if self.asset else None
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        platforms = {}
        if "platforms" in data and isinstance(data["platforms"], dict):
            for pid, pdata in data["platforms"].items():
                plat = Platform.from_dict(pdata)
                plat.id = pid
                platforms[pid] = plat
        elif "platform" in data and data["platform"]:
            plat = Platform.from_dict(data["platform"])
            plat.id = data["platform"].get("id", "PLAT_1")
            platforms[plat.id] = plat

        reference_systems = {}
        if "reference_systems" in data and isinstance(data["reference_systems"], dict):
            for rs_id, rs_data in data["reference_systems"].items():
                rs = ReferenceSystem.from_dict(rs_data)
                rs.id = rs_id
                reference_systems[rs_id] = rs

        asset_data = data.get("asset", {})
        asset = VehicleMesh.from_dict(asset_data) if asset_data else VehicleMesh.create_box_vehicle()

        proj = cls(
            name=data.get("name", "Proyecto"),
            description=data.get("description", ""),
            ellipsoid_name=data.get("ellipsoid_name", "GRS80"),
            platforms=platforms,
            active_platform_id=data.get("active_platform_id", "PLAT_1"),
            reference_systems=reference_systems if reference_systems else None,
            active_reference_system_id=data.get("active_reference_system_id", ""),
            asset=asset,
            metadata=data.get("metadata", {}),
            config=data.get("config", {})
        )
        return proj

    def save(self, filepath: str | Path) -> None:
        """Guarda el proyecto en disco en formato JSON (.pygsn)."""
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str | Path) -> "Project":
        """Carga un proyecto desde un archivo (.pygsn o .json)."""
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"Archivo de proyecto no encontrado: {filepath}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    # -------------------------------------------------------------------------
    # Interoperabilidad con Calibracion TXT
    # -------------------------------------------------------------------------
    def export_calibration_txt(self, filepath: str | Path) -> None:
        """Exporta la definicion de sensores y plataforma a fichero TXT."""
        txt = self.platform.to_txt()
        Path(filepath).write_text(txt, encoding="utf-8")

    def import_calibration_txt(self, filepath: str | Path) -> None:
        """Importa una plataforma y sensores desde un archivo TXT."""
        content = Path(filepath).read_text(encoding="utf-8")
        self.platform = Platform.from_txt(content)

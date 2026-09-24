"""
PyGSN - Core Project Module
===========================
Gestion integral de proyectos de navegacion y rigs multisensores (.pygsn):
- Encapsula la plataforma de vehiculo, los sensores instalados y los assets 3D de carroceria.
- Almacena parametros geodésicos (elipsoide GRS80/WGS84, ondulacion geoidal, zona UTM).
- Serializacion y deserializacion estructurada en formato JSON estandar.
- Interoperabilidad con ficheros de calibracion .txt.
"""

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .assets import VehicleMesh
from .models import Platform, Sensor


@dataclass
class Project:
    """
    Contenedor principal de un proyecto de ingenieria en PyGSN.
    """
    name: str = "Proyecto Nuevo"
    description: str = "Proyecto multisensor de navegacion y georreferenciacion"
    ellipsoid_name: str = "GRS80"
    platform: Platform = field(default_factory=lambda: Platform(name="Plataforma Vehiculo"))
    asset: VehicleMesh = field(default_factory=lambda: VehicleMesh.create_box_vehicle(name="Chasis Vehiculo"))
    metadata: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=lambda: {
        "utm_zone": 30,
        "geoid_undulation_n": 49.548, # metros (default zona Valencia)
        "mag_declination_deg": 1.25,  # deg (default WMM)
    })

    def __post_init__(self):
        if not self.metadata:
            self.metadata = {
                "created_at": datetime.now().isoformat(),
                "author": "PyGSN Engineer",
                "version": "1.0.0"
            }

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
            "platform": self.platform.to_dict(),
            "asset": self.asset.to_dict()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        plat_data = data.get("platform", {})
        platform = Platform.from_dict(plat_data) if plat_data else Platform()

        asset_data = data.get("asset", {})
        asset = VehicleMesh.from_dict(asset_data) if asset_data else VehicleMesh.create_box_vehicle()

        return cls(
            name=data.get("name", "Proyecto"),
            description=data.get("description", ""),
            ellipsoid_name=data.get("ellipsoid_name", "GRS80"),
            platform=platform,
            asset=asset,
            metadata=data.get("metadata", {}),
            config=data.get("config", {
                "utm_zone": 30,
                "geoid_undulation_n": 49.548,
                "mag_declination_deg": 1.25
            })
        )

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

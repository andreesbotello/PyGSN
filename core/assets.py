"""
PyGSN - Core Assets Module
==========================
Representacion geometrica y matricial optima de chasis y cuerpos de vehiculos en 3D (b-frame):
- Mallas tridimensionales ligeras basadas en NumPy (vertices y poligonos/aristas).
- Proyecciones ortograficas vectorizadas instantaneas para vistas CAD (Planta, Perfil, Alzado).
- Constructores para geometrias estandar: vehiculo terrestre (coche/furgoneta), dron multirotor, y prismas simples.
- Serializacion y deserializacion sin dependencias de motores 3D externos.
"""

from dataclasses import dataclass, field
import json
from typing import Any
import numpy as np


@dataclass
class VehicleMesh:
    """
    Representacion de la malla 3D del chasis del vehiculo en b-frame.
    
    Ejes b-frame:
      X_b: Hacia adelante (+X)
      Y_b: Hacia estribor / derecha (+Y)
      Z_b: Hacia abajo (+Z)
    """
    name: str = "Chasis Vehiculo"
    vertices: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.float64)) # (V, 3)
    edges: list[tuple[int, int]] = field(default_factory=list) # Aristas conectando pares de vertices
    faces: list[list[int]] = field(default_factory=list)       # Poligonos / caras indexadas
    color_rgb: tuple[int, int, int] = (140, 160, 185)         # Color para renderizado en lineas

    @property
    def num_vertices(self) -> int:
        return len(self.vertices)

    @property
    def num_edges(self) -> int:
        return len(self.edges)

    @property
    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        """Retorna (min_bounds, max_bounds) en b-frame [m]."""
        if len(self.vertices) == 0:
            return np.zeros(3), np.zeros(3)
        return np.min(self.vertices, axis=0), np.max(self.vertices, axis=0)

    # -------------------------------------------------------------------------
    # Proyecciones Ortograficas 2D Vectorizadas
    # -------------------------------------------------------------------------
    def project_top(self) -> np.ndarray:
        """
        Proyeccion ortogonal sobre el plano X_b vs Y_b (Planta / Top-down).
        Retorna matriz (V, 2) con coordenadas [X_b (adelante), Y_b (derecha)].
        """
        if len(self.vertices) == 0:
            return np.zeros((0, 2), dtype=np.float64)
        return self.vertices[:, [0, 1]]

    def project_side(self) -> np.ndarray:
        """
        Proyeccion ortogonal sobre el plano X_b vs -Z_b (Perfil / Side).
        Retorna matriz (V, 2) con coordenadas [X_b (adelante), -Z_b (cota/arriba)].
        """
        if len(self.vertices) == 0:
            return np.zeros((0, 2), dtype=np.float64)
        x_fwd = self.vertices[:, 0]
        z_up = -self.vertices[:, 2]
        return np.column_stack([x_fwd, z_up])

    def project_front(self) -> np.ndarray:
        """
        Proyeccion ortogonal sobre el plano Y_b vs -Z_b (Frontal / Alzado).
        Retorna matriz (V, 2) con coordenadas [Y_b (derecha), -Z_b (cota/arriba)].
        """
        if len(self.vertices) == 0:
            return np.zeros((0, 2), dtype=np.float64)
        y_right = self.vertices[:, 1]
        z_up = -self.vertices[:, 2]
        return np.column_stack([y_right, z_up])

    # -------------------------------------------------------------------------
    # Constructores Predefinidos
    # -------------------------------------------------------------------------
    @classmethod
    def create_box_vehicle(
        cls,
        length_m: float = 4.5,
        width_m: float = 1.8,
        height_m: float = 1.5,
        cabin_ratio: float = 0.5,
        hood_ratio: float = 0.25,
        name: str = "Vehiculo Terrestre"
    ) -> "VehicleMesh":
        """
        Genera un chasis estilizado con capó, cabina y parte trasera.
        El origen [0, 0, 0] se ubica en el centro de la base del vehiculo.
        """
        x_half = length_m / 2.0
        y_half = width_m / 2.0
        z_base = 0.0          # Base del chasis en Z_b = 0
        z_hood = -height_m * 0.55  # Capo a media altura (negativo en Z_b = arriba)
        z_roof = -height_m         # Techo de la cabina

        x_front = x_half
        x_hood_end = x_half - length_m * hood_ratio
        x_cabin_end = x_hood_end - length_m * cabin_ratio
        x_rear = -x_half

        # 16 vertices estructurados
        verts = np.array([
            # Base inferior (0..3)
            [x_front, -y_half, z_base],
            [x_front,  y_half, z_base],
            [x_rear,   y_half, z_base],
            [x_rear,  -y_half, z_base],
            # Nivel capó frontal (4..7)
            [x_front, -y_half, z_hood],
            [x_front,  y_half, z_hood],
            [x_hood_end,  y_half, z_hood],
            [x_hood_end, -y_half, z_hood],
            # Techo cabina (8..11)
            [x_hood_end * 0.8, -y_half * 0.85, z_roof],
            [x_hood_end * 0.8,  y_half * 0.85, z_roof],
            [x_cabin_end,       y_half * 0.85, z_roof],
            [x_cabin_end,      -y_half * 0.85, z_roof],
            # Parte trasera (12..15)
            [x_cabin_end, -y_half, z_hood],
            [x_cabin_end,  y_half, z_hood],
            [x_rear,       y_half, z_hood],
            [x_rear,      -y_half, z_hood],
        ], dtype=np.float64)

        edges = [
            # Base inferior
            (0, 1), (1, 2), (2, 3), (3, 0),
            # Capó frontal
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5),
            # Parabrisas y techo
            (7, 8), (6, 9), (8, 9), (9, 10), (10, 11), (11, 8),
            # Caida trasera cabina
            (11, 12), (10, 13),
            # Maletero / parte trasera
            (12, 13), (13, 14), (14, 15), (15, 12),
            (2, 14), (3, 15), (6, 13), (7, 12)
        ]

        return cls(name=name, vertices=verts, edges=edges)

    @classmethod
    def create_uav_multirotor(
        cls,
        arm_length_m: float = 0.35,
        body_radius_m: float = 0.12,
        height_m: float = 0.15,
        name: str = "Dron Quadrotor X4"
    ) -> "VehicleMesh":
        """Genera el modelo geometrico 3D de un UAV Quadrotor en configuracion X."""
        # Centro
        z_top = -height_m
        z_bot = 0.0
        r_b = body_radius_m
        
        # Vertices del fuselaje central octogonal
        verts_list = []
        for i in range(8):
            ang = i * np.pi / 4.0
            verts_list.append([r_b * np.cos(ang), r_b * np.sin(ang), z_bot])
            verts_list.append([r_b * np.cos(ang), r_b * np.sin(ang), z_top])
        
        # 4 motores / extremos de brazos (a 45°, 135°, 225°, 315°)
        arm_angles = [np.pi / 4.0, 3 * np.pi / 4.0, 5 * np.pi / 4.0, 7 * np.pi / 4.0]
        motor_start_idx = len(verts_list)
        for ang in arm_angles:
            mx = arm_length_m * np.cos(ang)
            my = arm_length_m * np.sin(ang)
            verts_list.append([mx, my, z_top * 0.7])
            # Aro de motor
            for j in range(4):
                jang = j * np.pi / 2.0
                verts_list.append([mx + 0.05 * np.cos(jang), my + 0.05 * np.sin(jang), z_top * 0.7])

        verts = np.array(verts_list, dtype=np.float64)
        
        edges = []
        # Fuselaje central
        for i in range(8):
            b1 = i * 2
            t1 = i * 2 + 1
            b2 = ((i + 1) % 8) * 2
            t2 = ((i + 1) % 8) * 2 + 1
            edges.extend([(b1, b2), (t1, t2), (b1, t1)])
        
        # Brazos a motores
        for k in range(4):
            m_center = motor_start_idx + k * 5
            edges.append((1, m_center)) # Conectar a fuselaje
            # Cruz de helice
            edges.append((m_center + 1, m_center + 3))
            edges.append((m_center + 2, m_center + 4))

        return cls(name=name, vertices=verts, edges=edges)

    # -------------------------------------------------------------------------
    # Serializacion JSON
    # -------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "vertices": self.vertices.tolist(),
            "edges": self.edges,
            "faces": self.faces,
            "color_rgb": list(self.color_rgb)
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VehicleMesh":
        return cls(
            name=data.get("name", "Chasis"),
            vertices=np.array(data.get("vertices", []), dtype=np.float64),
            edges=[tuple(e) for e in data.get("edges", [])],
            faces=data.get("faces", []),
            color_rgb=tuple(data.get("color_rgb", (140, 160, 185)))
        )

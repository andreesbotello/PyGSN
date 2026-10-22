"""
PyGSN Core - Package Initialization
===================================
Motor matematico, geodesico y de gestion de proyectos de navegacion.
"""

from .models import Sensor, SensorType, Platform
from .assets import VehicleMesh
from .project import Project
from .geodesy import (
    Ellipsoid, GRS80, WGS84,
    radii_of_curvature, geodetic_to_ecef, ecef_to_geodetic,
    utm_projection_huso30, dms_to_rad, rad_to_dms
)
from .rotations import (
    R1, R2, R3,
    e_to_n_matrix, n_to_e_matrix,
    euler_to_dcm, attitude_to_dcm, dcm_to_euler, dcm_to_attitude,
    sensor_to_body_matrix, body_to_sensor_matrix,
    magnetic_to_geodetic_north_matrix, reorthonormalize_dcm
)
from .alignment import kabsch_orthogonal_procrustes
from .georeferencing import solve_multisensor_georeferencing, GeoreferencingSolution, SensorResult
from .reporting import generate_georeferencing_report
from .operators import (
    BaseOperator, OperatorResult,
    GeoreferencingOperator, TrajectoryKinematicsOperator, ReportingOperator
)

from .cli_engine import CLIEngine

__all__ = [
    "Sensor", "SensorType", "Platform",
    "VehicleMesh", "Project", "CLIEngine",
    "Ellipsoid", "GRS80", "WGS84",
    "radii_of_curvature", "geodetic_to_ecef", "ecef_to_geodetic",
    "utm_projection_huso30", "dms_to_rad", "rad_to_dms",
    "R1", "R2", "R3", "e_to_n_matrix", "n_to_e_matrix",
    "euler_to_dcm", "attitude_to_dcm", "dcm_to_euler", "dcm_to_attitude",
    "sensor_to_body_matrix", "body_to_sensor_matrix",
    "magnetic_to_geodetic_north_matrix", "reorthonormalize_dcm",
    "kabsch_orthogonal_procrustes",
    "solve_multisensor_georeferencing", "GeoreferencingSolution", "SensorResult",
    "generate_georeferencing_report",
    "BaseOperator", "OperatorResult",
    "GeoreferencingOperator", "TrajectoryKinematicsOperator", "ReportingOperator"
]

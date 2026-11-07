"""
PyGSN Core - Package Initialization
===================================
Motor matematico, geodesico y de gestion de proyectos de navegacion.
"""

from .models import Sensor, SensorType, Platform, ReferenceSystem, PlatformPose, SensorGeoref
from .assets import VehicleMesh
from .project import Project
from .geodesy import (
    Ellipsoid, GRS80, WGS84,
    radii_of_curvature, geodetic_to_ecef, ecef_to_geodetic,
    utm_projection, utm_projection_huso30, utm_inverse, utm_meridian_convergence,
    dms_to_rad, rad_to_dms, parse_coordinate_string, ellipsoidal_to_orthometric, grid_bearing
)
from .rotations import (
    R1, R2, R3,
    e_to_n_matrix, n_to_e_matrix,
    euler_to_dcm, attitude_to_dcm, dcm_to_euler, dcm_to_attitude,
    sensor_to_body_matrix, body_to_sensor_matrix,
    magnetic_to_geodetic_north_matrix, reorthonormalize_dcm,
    chain_ins_attitude_matrix, audit_dcm_condition
)
from .alignment import kabsch_orthogonal_procrustes, compute_centroid_3d, reduce_to_centroid_3d
from .kinematics import (
    propagate_lever_arm_ecef, solve_origin_from_centroid_ecef,
    geodetic_navigation_rates, rotate_polygon_2d, scale_polygon_2d,
    compute_polygon_2d_bounds, compute_utm_bounding_box_points, translate_points_3d
)
from .georeferencing import (
    solve_multisensor_georeferencing, solve_georeferencing_pipeline,
    GeoreferencingSolution, SensorResult,
    gnss_observations_to_ecef, compute_navigation_centroid, project_ecef_to_nframe,
    solve_attitude_kabsch, solve_pla_origin_ecef, solve_attitude_ins_chain,
    propagate_sensor_network, compute_georef_residuals, compute_consistency_residuals,
    compute_attitude_uncertainty, AttitudeUncertainty
)
from .validation import (
    ValidationError, CollinearGeometryError, validate_finite,
    normalize_angle_pi, normalize_angle_2pi, normalize_angle_deg_180, normalize_angle_deg_360,
    validate_attitude_angles, validate_antenna_geometry, validate_lat_lon, validate_safe_division
)
from .reporting import generate_georeferencing_report
from .operators import (
    BaseOperator, OperatorResult,
    GeoreferencingOperator, TrajectoryKinematicsOperator, ReportingOperator
)

from .cli_engine import CLIEngine

__all__ = [
    "Sensor", "SensorType", "Platform", "ReferenceSystem", "PlatformPose", "SensorGeoref",
    "VehicleMesh", "Project", "CLIEngine",
    "Ellipsoid", "GRS80", "WGS84",
    "radii_of_curvature", "geodetic_to_ecef", "ecef_to_geodetic",
    "utm_projection", "utm_projection_huso30", "utm_inverse", "utm_meridian_convergence",
    "dms_to_rad", "rad_to_dms", "parse_coordinate_string", "ellipsoidal_to_orthometric", "grid_bearing",
    "R1", "R2", "R3", "e_to_n_matrix", "n_to_e_matrix",
    "euler_to_dcm", "attitude_to_dcm", "dcm_to_euler", "dcm_to_attitude",
    "sensor_to_body_matrix", "body_to_sensor_matrix",
    "magnetic_to_geodetic_north_matrix", "reorthonormalize_dcm",
    "chain_ins_attitude_matrix", "audit_dcm_condition",
    "kabsch_orthogonal_procrustes", "compute_centroid_3d", "reduce_to_centroid_3d",
    "propagate_lever_arm_ecef", "solve_origin_from_centroid_ecef",
    "geodetic_navigation_rates", "rotate_polygon_2d", "scale_polygon_2d",
    "compute_polygon_2d_bounds", "compute_utm_bounding_box_points", "translate_points_3d",
    "solve_multisensor_georeferencing", "solve_georeferencing_pipeline", "GeoreferencingSolution", "SensorResult",
    "gnss_observations_to_ecef", "compute_navigation_centroid", "project_ecef_to_nframe",
    "solve_attitude_kabsch", "solve_pla_origin_ecef", "solve_attitude_ins_chain",
    "propagate_sensor_network", "compute_georef_residuals", "compute_consistency_residuals",
    "compute_attitude_uncertainty", "AttitudeUncertainty",
    "ValidationError", "CollinearGeometryError", "validate_finite",
    "normalize_angle_pi", "normalize_angle_2pi", "normalize_angle_deg_180", "normalize_angle_deg_360",
    "validate_attitude_angles", "validate_antenna_geometry", "validate_lat_lon", "validate_safe_division",
    "generate_georeferencing_report",
    "BaseOperator", "OperatorResult",
    "GeoreferencingOperator", "TrajectoryKinematicsOperator", "ReportingOperator"
]

"""
PyGSN - Operators Package
=========================
Pipeline modular de operadores de navegacion y georreferenciacion:
- BaseOperator, OperatorResult
- GeoreferencingOperator: Actitud por SVD de Kabsch y propagacion multi-sensor.
- TrajectoryKinematicsOperator: Integracion b-frame -> n-frame -> e-frame.
- ReportingOperator: Generador de reportes tecnicos paso a paso.
"""

from .base import BaseOperator, OperatorResult
from .georeferencing_operator import GeoreferencingOperator
from .kinematics_operator import TrajectoryKinematicsOperator
from .reporting_operator import ReportingOperator

__all__ = [
    "BaseOperator",
    "OperatorResult",
    "GeoreferencingOperator",
    "TrajectoryKinematicsOperator",
    "ReportingOperator"
]

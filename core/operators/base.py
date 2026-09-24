"""
PyGSN - Operators Base Module
=============================
Definicion de interfaces estandar para el pipeline de operadores de navegacion y computo:
- BaseOperator: Clase abstracta que define el contrato de ejecucion.
- OperatorResult: Estructura de resultados con estado de exito, datos computados y trazabilidad paso a paso.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class OperatorResult:
    """Resultado estandarizado de la ejecucion de un operador."""
    operator_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    error_message: str | None = None

    def log(self, message: str) -> None:
        self.messages.append(message)


class BaseOperator(ABC):
    """Interfaz base para todos los operadores de calculo cinemático y geodésico."""
    
    def __init__(self, name: str | None = None):
        self.name = name or self.__class__.__name__

    @abstractmethod
    def execute(self, project: Any, **kwargs) -> OperatorResult:
        """
        Ejecuta el calculo matematico sobre el proyecto.
        
        Args:
            project: Instancia de Project con la plataforma, sensores y configuracion.
            **kwargs: Argumentos especificos del operador (ej. observaciones, ficheros, epocas).
            
        Returns:
            OperatorResult con los datos computados y trazabilidad paso a paso.
        """
        pass

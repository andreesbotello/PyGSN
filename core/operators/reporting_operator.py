"""
PyGSN - Reporting Operator
==========================
Operador de generacion y exportacion de informes tecnicos paso a paso (.txt):
- Recolecta las matrices y estados intermedios del GeoreferencingOperator.
- Genera un archivo tabular con rigor matematico y trazabilidad completa.
"""

from pathlib import Path
from typing import Any

from .base import BaseOperator, OperatorResult
from ..reporting import generate_georeferencing_report


class ReportingOperator(BaseOperator):
    """
    Operador que formatea y exporta los informes tecnicos de resolucion.
    """
    def __init__(self):
        super().__init__(name="ReportingOperator")

    def execute(self, project: Any, **kwargs) -> OperatorResult:
        """
        Genera el informe tecnico a partir de un GeoreferencingSolution.
        
        Parametros aceptados en kwargs:
            georeferencing_result: Instancia de GeoreferencingSolution.
            output_path: str | Path opcional donde guardar el archivo .txt.
        """
        result = OperatorResult(operator_name=self.name, success=False)

        geo_res = kwargs.get("georeferencing_result")
        if geo_res is None:
            result.error_message = "No se proporciono el resultado de georreferenciacion para el informe."
            return result

        try:
            report_text = generate_georeferencing_report(
                sol=geo_res,
                author=project.metadata.get("author", "PyGSN Engineer"),
                project=project.name,
                doc_id=project.metadata.get("doc_id", "PyGSN-REPORT")
            )
            result.success = True
            result.data["report_text"] = report_text

            out_path = kwargs.get("output_path")
            if out_path:
                p = Path(out_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(report_text, encoding="utf-8")
                result.data["output_file"] = str(p)
                result.log(f"Informe tecnico exportado exitosamente a: {p.resolve()}")

        except Exception as e:
            result.success = False
            result.error_message = f"Error al generar informe tecnico: {str(e)}"

        return result

"""
PyGSN - Technical Report Viewer Panel
=====================================
Visor dedicado de informe tecnico paso a paso:
- Ocupa todo el alto y ancho del workspace con tipografia monoespaciada legible.
- Exportacion directa a fichero .txt y copia al portapapeles del sistema.
"""

from pathlib import Path
from typing import Callable
import dearpygui.dearpygui as dpg


class ReportViewerPanel:
    """Panel visor y exportador de informes tecnicos paso a paso."""

    def __init__(self, get_report_text: Callable[[], str]):
        self.get_report_text = get_report_text

    def build_ui(self, parent_tag: str):
        with dpg.group(parent=parent_tag):
            # Barra de herramientas superior del visor
            with dpg.group(horizontal=True):
                dpg.add_text("Informe Técnico Paso a Paso:", color=(0, 180, 216, 255))
                dpg.add_spacer(width=20)
                dpg.add_input_text(label="Ruta Fichero", default_value="output/Informe_Georreferenciacion.txt",
                                   width=260, tag="report_output_path_input")
                dpg.add_button(label="EXPORTAR FICHERO TXT", callback=self._cb_export_file)
                dpg.add_button(label="COPIAR AL PORTAPAPELES", callback=self._cb_copy_clipboard)
                dpg.add_spacer(width=10)
                dpg.add_text("", tag="report_status_text", color=(6, 214, 160, 255))

            dpg.add_separator()
            dpg.add_spacer(height=3)

            # Area de texto de informe a pantalla completa
            with dpg.child_window(width=-1, height=-1, border=True):
                dpg.add_input_text(
                    default_value="",
                    multiline=True,
                    readonly=True,
                    width=-1,
                    height=-1,
                    tag="global_report_viewer"
                )

    def update_report(self, text: str):
        """Actualiza el contenido mostrado en el visor de informe."""
        if dpg.does_item_exist("global_report_viewer"):
            dpg.set_value("global_report_viewer", text)

    def _cb_copy_clipboard(self):
        txt = self.get_report_text()
        if txt:
            dpg.set_clipboard_text(txt)
            dpg.set_value("report_status_text", "[OK] Copiado al portapapeles")
        else:
            dpg.set_value("report_status_text", "Aviso: No hay informe generado aún")

    def _cb_export_file(self):
        txt = self.get_report_text()
        if not txt:
            dpg.set_value("report_status_text", "Aviso: Ejecute primero el cálculo")
            return

        out_path_str = dpg.get_value("report_output_path_input").strip() or "output/Informe_Georreferenciacion.txt"
        p = Path(out_path_str)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(txt, encoding="utf-8")
            dpg.set_value("report_status_text", f"[OK] Guardado en: {p.name}")
        except Exception as e:
            dpg.set_value("report_status_text", f"Error: {str(e)[:35]}")

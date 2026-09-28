"""
PyGSN - Technical Report Viewer Panel (PySide6 / Qt)
====================================================
Visor de informes técnicos de georreferenciación y navegación paso a paso.
"""

from typing import Optional
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QFileDialog, QMessageBox, QLabel
)
from PySide6.QtCore import Qt


class ReportViewerWidget(QWidget):
    """Pestaña del Workspace para inspeccionar el informe técnico TXT generado."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.report_text: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        bar_layout = QHBoxLayout()
        lbl = QLabel("Informe Técnico Paso a Paso (Auditoría SVD, Geodesia y Residuales)")
        lbl.setStyleSheet("color: #00b4d8; font-weight: bold;")
        bar_layout.addWidget(lbl)
        bar_layout.addStretch()

        self.btn_export = QPushButton("Exportar Informe TXT...")
        self.btn_export.clicked.connect(self.export_report)
        bar_layout.addWidget(self.btn_export)

        self.btn_copy = QPushButton("Copiar al Portapapeles")
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        bar_layout.addWidget(self.btn_copy)

        layout.addLayout(bar_layout)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet(
            "background-color: #121418; color: #e6ebf5; font-family: 'Consolas', 'Courier New', monospace; font-size: 11px; border: 1px solid #2d313d;"
        )
        layout.addWidget(self.text_edit)

    def set_report_text(self, text: str):
        self.report_text = text
        self.text_edit.setPlainText(text)

    def export_report(self):
        if not self.report_text:
            QMessageBox.warning(self, "Aviso", "No hay contenido en el informe para exportar.")
            return
        fpath, _ = QFileDialog.getSaveFileName(
            self, "Exportar Informe Técnico", "output/Informe_Georreferenciacion.txt", "Texto (*.txt)"
        )
        if fpath:
            Path(fpath).write_text(self.report_text, encoding="utf-8")
            QMessageBox.information(self, "Guardado", f"Informe guardado en:\n{fpath}")

    def copy_to_clipboard(self):
        if not self.report_text:
            return
        self.text_edit.selectAll()
        self.text_edit.copy()
        QMessageBox.information(self, "Copiado", "Informe copiado al portapapeles del sistema.")

"""
PyGSN - GUI Attribute Table Dialog (PySide6 / Qt)
=================================================
Tabla interactiva de atributos de ingeniería (estilo QGIS F6):
- Muestra de forma unificada y tabular todos los sensores montados en una plataforma.
- Columnas desacopladas y secuenciales:
  1. Identificación y Tipología (Código, Nombre, Tipo de Sensor).
  2. Atributos de Montaje en b-frame (Brazo de palanca X, Y, Z y ángulos boresight α, β, γ).
  3. Atributos Georreferenciados en e-frame (SRT, ECEF X, Y, Z, Latitud DMS, Longitud DMS,
     h elipsoidal, UTM Este, UTM Norte, Cota ortométrica H y método de cálculo).
- Filtrado en tiempo real por texto.
- Copiado de tabla completa o filtrada al portapapeles y exportación a CSV/TXT.
- Conmutación ágil mediante el atajo de teclado global F6.
"""

from typing import Optional, List, Dict, Any
import numpy as np

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QApplication, QWidget
)
from PySide6.QtCore import Qt, QLocale
from PySide6.QtGui import QKeySequence, QShortcut

from core.models import Platform, Sensor
from core.geodesy import rad_to_dms
from gui.dialogs import BaseDialog


class DialogAttributeTable(BaseDialog):
    """
    Diálogo técnico no modal con la tabla de atributos de sensores (estilo QGIS F6).
    """

    def __init__(self, platform: Platform, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setLocale(QLocale.c())
        self.platform = platform

        self.setWindowTitle(f"Tabla de Atributos: {self.platform.name}")
        self.resize(1120, 540)
        self.setMinimumSize(850, 400)
        self.setModal(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(8)

        # Encabezado informativo
        hbox_head = QHBoxLayout()
        vbox_info = QVBoxLayout()
        vbox_info.setSpacing(2)

        lbl_title = QLabel(f"Plataforma: {self.platform.name} [{self.platform.id}] ({self.platform.platform_type})")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0077b6;")
        vbox_info.addWidget(lbl_title)

        if self.platform.pose_e:
            p = self.platform.pose_e
            _, _, _, s_lat = rad_to_dms(np.radians(p.lat_deg))
            _, _, _, s_lon = rad_to_dms(np.radians(p.lon_deg))
            status_txt = (
                f"Estado: Georreferenciada en {p.ref_system_name} [{p.ref_system_id}] | "
                f"Método: {p.method} | "
                f"PLA: φ={s_lat.strip()}, λ={s_lon.strip()}, h={p.h_ellip_m:.3f} m, H={p.h_ortho_m:.3f} m"
            )
            lbl_status = QLabel(status_txt)
            lbl_status.setStyleSheet("color: #16a34a; font-size: 11px; font-weight: 500;")
        else:
            lbl_status = QLabel("Estado: Sin georreferenciar en e-frame (Solo coordenadas locales b-frame).")
            lbl_status.setStyleSheet("color: #64748b; font-size: 11px; font-style: italic;")

        vbox_info.addWidget(lbl_status)
        hbox_head.addLayout(vbox_info)
        hbox_head.addStretch()

        # Barra de búsqueda y filtrado
        lbl_filter = QLabel("Filtrar:")
        lbl_filter.setStyleSheet("font-weight: 500; font-size: 11px; color: #334155;")
        hbox_head.addWidget(lbl_filter)

        self.line_filter = QLineEdit()
        self.line_filter.setPlaceholderText("Buscar sensor...")
        self.line_filter.setFixedWidth(200)
        self.line_filter.textChanged.connect(self._on_filter_changed)
        hbox_head.addWidget(self.line_filter)

        main_layout.addLayout(hbox_head)

        # Tabla de atributos (21 columnas)
        self.headers = [
            "Código", "Nombre", "Tipo",
            "X_b (m)", "Y_b (m)", "Z_b (m)",
            "α (°)", "β (°)", "γ (°)",
            "Estado Georref", "SRT ID",
            "X_e (m)", "Y_e (m)", "Z_e (m)",
            "Latitud (DMS)", "Longitud (DMS)", "h Elip (m)",
            "Este UTM (m)", "Norte UTM (m)", "Cota H (m)", "Método"
        ]

        self.table = QTableWidget(0, len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setStyleSheet(
            "QTableWidget { font-family: 'Segoe UI', sans-serif; font-size: 11px; gridline-color: #e2e8f0; } "
            "QHeaderView::section { background-color: #f1f5f9; font-weight: bold; padding: 4px; border: 1px solid #cbd5e1; }"
        )
        main_layout.addWidget(self.table, 1)

        # Barra inferior de acciones
        hbox_foot = QHBoxLayout()
        self.lbl_count = QLabel(f"Total: {len(self.platform.sensors)} sensores.")
        self.lbl_count.setStyleSheet("color: #64748b; font-size: 11px;")
        hbox_foot.addWidget(self.lbl_count)
        hbox_foot.addStretch()

        btn_copy = QPushButton("Copiar Tabla (CSV)")
        btn_copy.setToolTip("Copia los registros visibles al portapapeles en formato CSV")
        btn_copy.clicked.connect(self._on_copy_csv)
        hbox_foot.addWidget(btn_copy)

        btn_export = QPushButton("Exportar (.csv)...")
        btn_export.setToolTip("Guarda la tabla de atributos en un fichero CSV")
        btn_export.clicked.connect(self._on_export_csv)
        hbox_foot.addWidget(btn_export)

        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.accept)
        hbox_foot.addWidget(btn_close)

        main_layout.addLayout(hbox_foot)

        # Poblar la tabla
        self._populate_table()

    def _populate_table(self):
        """Puebla todas las filas con los atributos b-frame y e-frame de los sensores."""
        self.table.setRowCount(0)
        sensors = list(self.platform.sensors.values())
        self.table.setRowCount(len(sensors))

        for row, s in enumerate(sensors):
            attr = s.get_attributes_dict()

            # 0..2: Identificación
            self.table.setItem(row, 0, QTableWidgetItem(attr["code"]))
            self.table.setItem(row, 1, QTableWidgetItem(attr["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(attr["type"]))

            # 3..5: Lever-Arm en b-frame
            self.table.setItem(row, 3, QTableWidgetItem(f"{attr['xb_m']:+8.4f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{attr['yb_m']:+8.4f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{attr['zb_m']:+8.4f}"))

            # 6..8: Boresight en b-frame
            self.table.setItem(row, 6, QTableWidgetItem(f"{attr['alpha_deg']:+8.4f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{attr['beta_deg']:+8.4f}"))
            self.table.setItem(row, 8, QTableWidgetItem(f"{attr['gamma_deg']:+8.4f}"))

            # 9..10: Estado y SRT
            is_geo = attr["is_georef"]
            status_item = QTableWidgetItem("Georreferenciado" if is_geo else "Local b-frame")
            if is_geo:
                status_item.setForeground(Qt.darkGreen)
            else:
                status_item.setForeground(Qt.gray)
            self.table.setItem(row, 9, status_item)
            self.table.setItem(row, 10, QTableWidgetItem(attr["srt_id"]))

            # 11..20: Atributos e-frame
            if is_geo:
                self.table.setItem(row, 11, QTableWidgetItem(f"{attr['xe_m']:12.3f}"))
                self.table.setItem(row, 12, QTableWidgetItem(f"{attr['ye_m']:12.3f}"))
                self.table.setItem(row, 13, QTableWidgetItem(f"{attr['ze_m']:12.3f}"))

                _, _, _, lat_dms = rad_to_dms(np.radians(attr["lat_deg"]))
                _, _, _, lon_dms = rad_to_dms(np.radians(attr["lon_deg"]))
                self.table.setItem(row, 14, QTableWidgetItem(lat_dms.strip()))
                self.table.setItem(row, 15, QTableWidgetItem(lon_dms.strip()))
                self.table.setItem(row, 16, QTableWidgetItem(f"{attr['h_ellip_m']:8.3f}"))
                self.table.setItem(row, 17, QTableWidgetItem(f"{attr['utm_e_m']:11.3f}"))
                self.table.setItem(row, 18, QTableWidgetItem(f"{attr['utm_n_m']:11.3f}"))
                self.table.setItem(row, 19, QTableWidgetItem(f"{attr['h_ortho_m']:8.3f}"))
                self.table.setItem(row, 20, QTableWidgetItem(attr["computed_via"]))
            else:
                for col in range(11, 21):
                    empty_it = QTableWidgetItem("-")
                    empty_it.setForeground(Qt.lightGray)
                    empty_it.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, col, empty_it)

    def _on_filter_changed(self, text: str):
        """Filtra dinámicamente las filas visibles por coincidencia de texto."""
        pattern = text.strip().lower()
        visible_count = 0
        for row in range(self.table.rowCount()):
            matches = False
            if not pattern:
                matches = True
            else:
                for col in range(3):  # Buscar en código, nombre y tipo
                    item = self.table.item(row, col)
                    if item and pattern in item.text().lower():
                        matches = True
                        break
            self.table.setRowHidden(row, not matches)
            if matches:
                visible_count += 1
        self.lbl_count.setText(f"Mostrando {visible_count} de {len(self.platform.sensors)} sensores.")

    def _generate_csv_text(self) -> str:
        """Construye una cadena de texto en formato CSV con las filas visibles."""
        lines = [";".join(self.headers)]
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                vals = [self.table.item(row, col).text() if self.table.item(row, col) else "" for col in range(len(self.headers))]
                lines.append(";".join(vals))
        return "\n".join(lines)

    def _on_copy_csv(self):
        """Copia el contenido CSV al portapapeles del sistema."""
        csv_text = self._generate_csv_text()
        QApplication.clipboard().setText(csv_text)
        QMessageBox.information(self, "Copiado", "Tabla de atributos copiada al portapapeles en formato CSV.")

    def _on_export_csv(self):
        """Exporta la tabla a un fichero CSV en disco."""
        fpath, _ = QFileDialog.getSaveFileName(
            self, "Exportar Tabla de Atributos",
            f"atributos_{self.platform.id.lower()}.csv",
            "Fichero CSV (*.csv);;Texto (*.txt);;Todos los archivos (*.*)"
        )
        if not fpath:
            return
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(self._generate_csv_text())
            QMessageBox.information(self, "Exportación Exitosa", f"Tabla guardada en:\n{fpath}")
        except Exception as e:
            QMessageBox.critical(self, "Error al Exportar", f"No se pudo guardar el archivo:\n{str(e)}")

    def keyPressEvent(self, event):
        """Permite cerrar o conmutar la tabla mediante F6 o Escape."""
        if event.key() in (Qt.Key_F6, Qt.Key_Escape):
            self.accept()
            return
        super().keyPressEvent(event)

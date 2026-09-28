"""
PyGSN - Georeferencing & SVD Attitude Solver Panel (PySide6 / Qt)
================================================================
Panel de procesamiento para estimación de actitud y posición por SVD Kabsch.
"""

from typing import Optional, Dict, Tuple, Callable
from pathlib import Path
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QGroupBox, QFileDialog, QMessageBox, QHeaderView
)
from PySide6.QtCore import Qt, Signal

from core.models import Platform
from core.georeferencing import solve_multisensor_georeferencing, GeoreferencingSolution
from core.reporting import generate_georeferencing_report
from core.geodesy import dms_to_rad, rad_to_dms
from core.operators.georeferencing_operator import parse_observations_content


class GeoreferencingWidget(QWidget):
    """Pestaña del Workspace para cálculo de Georreferenciación y Actitud SVD."""

    solution_computed = Signal(object, str)  # solution, report_text

    def __init__(self, platform: Optional[Platform], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.platform = platform
        self.last_solution: Optional[GeoreferencingSolution] = None
        self.last_report_text: str = ""

        self.gnss_observations: Dict[str, Tuple[float, float, float]] = {}
        self.ins_attitude_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.magnetic_declination_deg: float = -0.700
        self.geoid_undulation_n: float = 50.0166

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Barra de acciones
        act_layout = QHBoxLayout()
        self.btn_load_obs = QPushButton("Cargar Observaciones de Campo (.txt)...")
        self.btn_load_obs.clicked.connect(self.load_observations_dialog)
        act_layout.addWidget(self.btn_load_obs)

        self.btn_solve = QPushButton("Resolver Georreferenciación & Actitud (SVD)")
        self.btn_solve.setStyleSheet("background-color: #0077b6; font-weight: bold;")
        self.btn_solve.clicked.connect(self.solve)
        act_layout.addWidget(self.btn_solve)

        self.btn_export = QPushButton("Exportar Informe TXT...")
        self.btn_export.clicked.connect(self.export_report_dialog)
        act_layout.addWidget(self.btn_export)

        act_layout.addStretch()
        layout.addLayout(act_layout)

        # Tablas de datos y resultados en split horizontal
        tables_layout = QHBoxLayout()

        # Tabla de observaciones GNSS
        grp_obs = QGroupBox("Observaciones GNSS Topocéntricas")
        obs_vbox = QVBoxLayout(grp_obs)
        self.table_obs = QTableWidget(0, 4)
        self.table_obs.setHorizontalHeaderLabels(["Código", "Latitud (DMS)", "Longitud (DMS)", "h Elip. (m)"])
        self.table_obs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        obs_vbox.addWidget(self.table_obs)
        tables_layout.addWidget(grp_obs, 1)

        # Panel de Resultados
        grp_res = QGroupBox("Resultados de Georreferenciación y Actitud")
        res_vbox = QVBoxLayout(grp_res)

        self.lbl_sol_attitude = QLabel("Actitud GNSS (Cb2n): Sin resolver")
        self.lbl_sol_attitude.setStyleSheet("color: #ffd166; font-weight: bold;")
        res_vbox.addWidget(self.lbl_sol_attitude)

        self.lbl_sol_origin = QLabel("Origen PLA: Sin resolver")
        self.lbl_sol_origin.setStyleSheet("color: #00b4d8; font-weight: bold;")
        res_vbox.addWidget(self.lbl_sol_origin)

        self.lbl_sol_ins = QLabel("Actitud Total INS: Sin resolver")
        self.lbl_sol_ins.setStyleSheet("color: #06d6a0; font-weight: bold;")
        res_vbox.addWidget(self.lbl_sol_ins)

        self.table_residuals = QTableWidget(0, 4)
        self.table_residuals.setHorizontalHeaderLabels(["Sensor", "Res. X (m)", "Res. Y (m)", "Res. Z (m)"])
        self.table_residuals.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        res_vbox.addWidget(QLabel("Residuales de Consistencia Geodésica:"))
        res_vbox.addWidget(self.table_residuals)

        tables_layout.addWidget(grp_res, 1)
        layout.addLayout(tables_layout)

    def load_observations_dialog(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self, "Cargar Observaciones de Campo", "data", "Archivos de Texto (*.txt);;Todos los archivos (*.*)"
        )
        if not fpath:
            return
        p = Path(fpath)
        if not p.exists():
            return
        try:
            content = p.read_text(encoding="utf-8")
            data = parse_observations_content(content)
            self.gnss_observations = data.get("gnss_observations", {})
            self.ins_attitude_deg = data.get("ins_attitude_deg", (0.0, 0.0, 0.0))
            self.magnetic_declination_deg = data.get("magnetic_declination_deg", -0.700)
            self.geoid_undulation_n = data.get("geoid_undulation_N", 50.0166)
            self._update_obs_table()
        except Exception as e:
            QMessageBox.critical(self, "Error al Cargar Observaciones", f"No se pudo parsear el archivo: {str(e)}")

    def _update_obs_table(self):
        self.table_obs.setRowCount(len(self.gnss_observations))
        for r, (code, (phi, lam, h)) in enumerate(self.gnss_observations.items()):
            _, _, _, lat_str = rad_to_dms(phi)
            _, _, _, lon_str = rad_to_dms(lam)
            self.table_obs.setItem(r, 0, QTableWidgetItem(code))
            self.table_obs.setItem(r, 1, QTableWidgetItem(lat_str))
            self.table_obs.setItem(r, 2, QTableWidgetItem(lon_str))
            self.table_obs.setItem(r, 3, QTableWidgetItem(f"{h:.4f}"))

    def solve(self):
        if not self.platform:
            QMessageBox.warning(self, "Aviso", "No hay una plataforma activa configurada.")
            return
        if not self.gnss_observations:
            QMessageBox.warning(self, "Aviso", "No hay observaciones GNSS cargadas. Use 'Cargar Observaciones'.")
            return

        try:
            sol = solve_multisensor_georeferencing(
                platform=self.platform,
                gnss_observations=self.gnss_observations,
                ins_attitude_deg=self.ins_attitude_deg,
                magnetic_declination_deg=self.magnetic_declination_deg,
                geoid_undulation_N=self.geoid_undulation_n
            )
            self.last_solution = sol
            self.last_report_text = generate_georeferencing_report(sol)

            # Mostrar resultados
            rg, pg, yg = sol.attitude_gnss_deg
            self.lbl_sol_attitude.setText(f"Actitud GNSS (Cb2n): Roll={rg:+8.4f}°, Pitch={pg:+8.4f}°, Yaw={yg:+8.4f}°")

            _, _, _, lat_str = rad_to_dms(sol.pla_origin_lat_rad)
            _, _, _, lon_str = rad_to_dms(sol.pla_origin_lon_rad)
            self.lbl_sol_origin.setText(f"Origen PLA: Lat={lat_str}, Lon={lon_str}, h={sol.pla_origin_h_ellip:.4f}m")

            ri, pi, yi = sol.attitude_ins_total_deg
            self.lbl_sol_ins.setText(f"Actitud Total INS: Roll={ri:+8.4f}°, Pitch={pi:+8.4f}°, Yaw={yi:+8.4f}°")

            # Residuales
            if hasattr(sol, "residuals_b") and sol.residuals_b:
                self.table_residuals.setRowCount(len(sol.residuals_b))
                for row, (c, res) in enumerate(sol.residuals_b.items()):
                    self.table_residuals.setItem(row, 0, QTableWidgetItem(c))
                    self.table_residuals.setItem(row, 1, QTableWidgetItem(f"{res[0]:+.4f}"))
                    self.table_residuals.setItem(row, 2, QTableWidgetItem(f"{res[1]:+.4f}"))
                    self.table_residuals.setItem(row, 3, QTableWidgetItem(f"{res[2]:+.4f}"))

            self.solution_computed.emit(sol, self.last_report_text)

        except Exception as e:
            QMessageBox.critical(self, "Error en Resolución SVD", f"Fallo al resolver georreferenciación: {str(e)}")

    def export_report_dialog(self):
        if not self.last_report_text:
            QMessageBox.warning(self, "Aviso", "No hay informe calculado. Ejecute [Resolver SVD] primero.")
            return
        fpath, _ = QFileDialog.getSaveFileName(
            self, "Guardar Informe Técnico", "output/Informe_Georreferenciacion.txt", "Texto (*.txt)"
        )
        if fpath:
            Path(fpath).write_text(self.last_report_text, encoding="utf-8")
            QMessageBox.information(self, "Informe Guardado", f"Informe guardado en:\n{fpath}")

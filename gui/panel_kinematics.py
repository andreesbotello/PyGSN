"""
PyGSN - Kinematics & Trajectory Simulation Panel (PySide6 / Qt)
==============================================================
Panel de simulación cinemática y propagación de trayectorias con IMU y GNSS.
"""

from typing import Optional, Callable
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QDoubleSpinBox, QSpinBox, QPushButton, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt

from core.project import Project


class KinematicsWidget(QWidget):
    """Pestaña de simulación cinemática para trayectorias vehiculares."""

    def __init__(self, get_project: Callable[[], Project], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.get_project = get_project

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel("Simulación Cinemática de Trayectorias y Sensores Inerciales")
        header.setStyleSheet("color: #00b4d8; font-weight: bold; font-size: 13px;")
        layout.addWidget(header)

        # Configuración en dos columnas
        top_layout = QHBoxLayout()

        grp_traj = QGroupBox("Parámetros de Maniobra Cinemática")
        form_traj = QFormLayout(grp_traj)

        self.combo_pattern = QComboBox()
        self.combo_pattern.addItems([
            "Línea recta con aceleración constante",
            "Giro circular coordinado (Curva plana)",
            "Maniobra de cambio de carril (S-curve)",
            "Perfil 8 (Ocho de calibración magnetométrica)",
            "Vuelo estacionario / Estático con ruido de sensor"
        ])
        form_traj.addRow("Patrón de Movimiento:", self.combo_pattern)

        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(1.0, 3600.0)
        self.spin_duration.setValue(60.0)
        self.spin_duration.setSuffix(" s")
        form_traj.addRow("Duración:", self.spin_duration)

        self.spin_rate = QSpinBox()
        self.spin_rate.setRange(1, 500)
        self.spin_rate.setValue(100)
        self.spin_rate.setSuffix(" Hz")
        form_traj.addRow("Frecuencia IMU:", self.spin_rate)

        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.0, 150.0)
        self.spin_speed.setValue(15.0)
        self.spin_speed.setSuffix(" m/s")
        form_traj.addRow("Velocidad Nominal:", self.spin_speed)

        top_layout.addWidget(grp_traj)

        grp_noise = QGroupBox("Modelado de Errores Inerciales")
        form_noise = QFormLayout(grp_noise)

        self.spin_acc_bias = QDoubleSpinBox()
        self.spin_acc_bias.setRange(0.0, 1.0)
        self.spin_acc_bias.setDecimals(4)
        self.spin_acc_bias.setValue(0.005)
        self.spin_acc_bias.setSuffix(" m/s²")
        form_noise.addRow("Bias Acelerómetros:", self.spin_acc_bias)

        self.spin_gyro_bias = QDoubleSpinBox()
        self.spin_gyro_bias.setRange(0.0, 10.0)
        self.spin_gyro_bias.setDecimals(4)
        self.spin_gyro_bias.setValue(0.05)
        self.spin_gyro_bias.setSuffix(" °/s")
        form_noise.addRow("Bias Giroscopios:", self.spin_gyro_bias)

        self.spin_gnss_noise = QDoubleSpinBox()
        self.spin_gnss_noise.setRange(0.001, 10.0)
        self.spin_gnss_noise.setDecimals(3)
        self.spin_gnss_noise.setValue(0.02)
        self.spin_gnss_noise.setSuffix(" m")
        form_noise.addRow("Ruido GNSS (1-sigma):", self.spin_gnss_noise)

        top_layout.addWidget(grp_noise)
        layout.addLayout(top_layout)

        # Botón de simulación
        self.btn_run = QPushButton("Generar Trayectoria y Sintetizar Telemetría")
        self.btn_run.setStyleSheet("background-color: #0077b6; font-weight: bold; padding: 6px;")
        self.btn_run.clicked.connect(self._run_simulation)
        layout.addWidget(self.btn_run)

        # Tabla de muestras generadas
        grp_table = QGroupBox("Telemetría Simulada (Primeras 100 muestras)")
        vbox_table = QVBoxLayout(grp_table)
        self.table_sim = QTableWidget(0, 7)
        self.table_sim.setHorizontalHeaderLabels([
            "Tiempo (s)", "Pos X (m)", "Pos Y (m)", "Pos Z (m)", "Roll (°)", "Pitch (°)", "Yaw (°)"
        ])
        self.table_sim.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        vbox_table.addWidget(self.table_sim)
        layout.addWidget(grp_table)

    def _run_simulation(self):
        duration = self.spin_duration.value()
        rate = self.spin_rate.value()
        speed = self.spin_speed.value()
        dt = 1.0 / rate
        n_pts = int(duration * rate)
        pattern_idx = self.combo_pattern.currentIndex()

        t = np.linspace(0, duration, n_pts)
        pos = np.zeros((n_pts, 3), dtype=np.float64)
        att = np.zeros((n_pts, 3), dtype=np.float64)

        if pattern_idx == 0:
            # Recta con aceleración suave
            pos[:, 0] = speed * t
        elif pattern_idx == 1:
            # Giro circular R = 50m
            R = 50.0
            omega = speed / R
            pos[:, 0] = R * np.sin(omega * t)
            pos[:, 1] = R * (1 - np.cos(omega * t))
            att[:, 2] = np.rad2deg(omega * t) % 360.0
        else:
            pos[:, 0] = speed * t
            pos[:, 1] = 5.0 * np.sin(0.2 * t)
            att[:, 2] = np.rad2deg(np.arctan2(np.gradient(pos[:, 1], dt), speed))

        # Poblar tabla con las primeras 100 muestras
        display_pts = min(n_pts, 100)
        self.table_sim.setRowCount(display_pts)
        step = max(1, n_pts // display_pts)
        for i in range(display_pts):
            idx = i * step
            self.table_sim.setItem(i, 0, QTableWidgetItem(f"{t[idx]:.2f}"))
            self.table_sim.setItem(i, 1, QTableWidgetItem(f"{pos[idx, 0]:.3f}"))
            self.table_sim.setItem(i, 2, QTableWidgetItem(f"{pos[idx, 1]:.3f}"))
            self.table_sim.setItem(i, 3, QTableWidgetItem(f"{pos[idx, 2]:.3f}"))
            self.table_sim.setItem(i, 4, QTableWidgetItem(f"{att[idx, 0]:.2f}"))
            self.table_sim.setItem(i, 5, QTableWidgetItem(f"{att[idx, 1]:.2f}"))
            self.table_sim.setItem(i, 6, QTableWidgetItem(f"{att[idx, 2]:.2f}"))

        QMessageBox.information(
            self, "Simulación Completada",
            f"Se han generado {n_pts} muestras de trayectoria a {rate} Hz exitosamente."
        )

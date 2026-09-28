"""
PyGSN - Console & CLI Dock (PySide6 / Qt)
=========================================
Terminal interactiva CLI integrada en un dock desacoplable:
- Ejecución rápida de comandos (help, status, platforms, sensors, solve, residuals, diag, clear).
- Historial de comandos navegable con flechas arriba/abajo.
"""

from typing import Callable, Optional, List
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QLineEdit, QPushButton, QLabel
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor

from core.project import Project


class ConsoleDock(QDockWidget):
    """Terminal CLI integrada para PyGSN."""

    solve_requested = Signal()
    diagnostics_requested = Signal()
    residuals_requested = Signal()

    def __init__(
        self,
        get_project: Callable[[], Project],
        get_solution: Callable[[], Optional[Any]] = lambda: None,
        parent: Optional[QWidget] = None
    ):
        super().__init__("Consola CLI", parent)
        self.get_project = get_project
        self.get_solution = get_solution
        self.history: List[str] = []
        self.history_idx: int = -1

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
        self.setMinimumWidth(300)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(
            "background-color: #121418; color: #a9b7c6; font-family: 'Consolas', 'Courier New', monospace; font-size: 11px; border: 1px solid #2d313d;"
        )
        layout.addWidget(self.output)

        input_layout = QHBoxLayout()
        prompt_lbl = QLabel("pygsn>")
        prompt_lbl.setStyleSheet("color: #00b4d8; font-weight: bold; font-family: monospace;")
        input_layout.addWidget(prompt_lbl)

        self.input_cmd = QLineEdit()
        self.input_cmd.setStyleSheet(
            "background-color: #1a1c24; color: #ffffff; font-family: 'Consolas', monospace; border: 1px solid #3b4252;"
        )
        self.input_cmd.returnPressed.connect(self._on_command_entered)
        input_layout.addWidget(self.input_cmd)

        btn_run = QPushButton("Ejecutar")
        btn_run.clicked.connect(self._on_command_entered)
        input_layout.addWidget(btn_run)

        layout.addLayout(input_layout)
        self.setWidget(widget)

        self.print_line("PyGSN Interactive Terminal v2.0 (PySide6 / Qt)")
        self.print_line("Escriba 'help' para ver la lista de comandos disponibles.\n")

    def print_line(self, text: str):
        self.output.appendPlainText(text)
        self.output.moveCursor(QTextCursor.End)

    def _on_command_entered(self):
        cmd = self.input_cmd.text().strip()
        if not cmd:
            return
        self.input_cmd.clear()
        self.history.append(cmd)
        self.history_idx = len(self.history)

        self.print_line(f"pygsn> {cmd}")
        self._execute_command(cmd)

    def _execute_command(self, cmd: str):
        parts = cmd.split()
        root_cmd = parts[0].lower()

        if root_cmd in ("help", "?"):
            self.print_line("Comandos disponibles:")
            self.print_line("  help       : Muestra esta ayuda")
            self.print_line("  status     : Estado del proyecto, plataforma y geodesia")
            self.print_line("  platforms  : Lista las plataformas cargadas")
            self.print_line("  sensors    : Lista los sensores de la plataforma activa")
            self.print_line("  solve      : Ejecuta el solver SVD de georreferenciación")
            self.print_line("  residuals  : Inspecciona los residuales del último cálculo")
            self.print_line("  diag       : Auditoría espectral y diagnóstico de matrices")
            self.print_line("  clear      : Limpia la pantalla de la consola\n")

        elif root_cmd == "status":
            proj = self.get_project()
            plat = proj.platform
            self.print_line(f"Proyecto : {proj.name}")
            self.print_line(f"Elipsoide: {proj.ellipsoid_name} | Huso UTM: {proj.config.get('utm_zone', 30)}")
            self.print_line(f"Plat. Act: {plat.name if plat else '(ninguna)'}")
            n_sens = len(plat.sensors) if plat else 0
            self.print_line(f"Sensores : {n_sens}\n")

        elif root_cmd == "platforms":
            proj = self.get_project()
            if not proj.platforms:
                self.print_line("No hay plataformas registradas en el proyecto.\n")
                return
            self.print_line(f"Total plataformas: {len(proj.platforms)}")
            for pid, p in proj.platforms.items():
                active_mark = " [*ACTIVA]" if pid == proj.active_platform_id else ""
                self.print_line(f"  [{pid}] {p.name} ({p.platform_type}){active_mark}")
            self.print_line("")

        elif root_cmd == "sensors":
            proj = self.get_project()
            plat = proj.platform
            if not plat:
                self.print_line("No hay plataforma activa seleccionada.\n")
                return
            if not plat.sensors:
                self.print_line(f"La plataforma '{plat.name}' no tiene sensores montados.\n")
                return
            self.print_line(f"Sensores en '{plat.name}':")
            for c, s in plat.sensors.items():
                arm = s.lever_arm_b
                self.print_line(f"  {c:<6s} [{s.sensor_type.value:<4s}] arm=[{arm[0]:+.3f}, {arm[1]:+.3f}, {arm[2]:+.3f}]m  {s.name}")
            self.print_line("")

        elif root_cmd == "solve":
            self.print_line("Ejecutando resolución de georreferenciación SVD...")
            self.solve_requested.emit()

        elif root_cmd == "residuals":
            self.residuals_requested.emit()

        elif root_cmd == "diag":
            self.diagnostics_requested.emit()

        elif root_cmd in ("clear", "cls"):
            self.output.clear()

        else:
            self.print_line(f"Comando desconocido: '{root_cmd}'. Escriba 'help'.\n")

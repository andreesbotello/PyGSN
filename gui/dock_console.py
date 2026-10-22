"""
PyGSN - Console & CLI Dock (PySide6 / Qt)
=========================================
Terminal interactiva CLI integrada en un dock desacoplable:
- Alimentada directamente por el motor agnóstico CLIEngine (core/cli_engine.py).
- Totalmente sincronizada con el estado de la aplicación, el lienzo CAD y el árbol de capas.
- Historial de comandos navegable con flechas arriba/abajo.
"""

from typing import Callable, Optional, Any
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QLineEdit, QPushButton, QLabel
)
from PySide6.QtCore import Qt, Signal, QLocale, QEvent
from PySide6.QtGui import QTextCursor, QKeyEvent

from core.models import Platform, Sensor, SensorType
from core.project import Project
from core.cli_engine import CLIEngine


class ConsoleDock(QDockWidget):
    """Terminal CLI integrada para PyGSN, respaldada por CLIEngine."""

    solve_requested = Signal()
    diagnostics_requested = Signal()
    residuals_requested = Signal()
    chassis_modified = Signal()
    sensor_modified = Signal()
    platform_created = Signal(str)
    project_changed = Signal()

    def __init__(
        self,
        get_project: Callable[[], Project],
        get_solution: Callable[[], Optional[Any]] = lambda: None,
        parent: Optional[QWidget] = None
    ):
        super().__init__("Consola CLI", parent)
        self.setLocale(QLocale.c())
        self.get_project = get_project
        self.get_solution = get_solution
        self.history: list[str] = []
        self.history_idx: int = -1

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
        self.setMinimumWidth(320)

        # Inicialización del motor agnóstico CLI
        self.engine = CLIEngine(
            project=self.get_project(),
            stdout_callback=self._on_engine_output,
            on_project_modified=self._on_engine_project_modified,
            on_chassis_modified=self.chassis_modified.emit,
            on_sensor_modified=self.sensor_modified.emit,
            on_platform_created=self.platform_created.emit,
            on_solution_computed=self._on_engine_solution_computed
        )

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(
            "background-color: #ffffff; color: #1e293b; font-family: 'Consolas', 'Courier New', monospace; font-size: 11px; border: 1px solid #ced4da;"
        )
        layout.addWidget(self.output)

        input_layout = QHBoxLayout()
        prompt_lbl = QLabel("pygsn>")
        prompt_lbl.setStyleSheet("color: #0077b6; font-weight: bold; font-family: monospace;")
        input_layout.addWidget(prompt_lbl)

        self.input_cmd = QLineEdit()
        self.input_cmd.setStyleSheet(
            "background-color: #f8f9fa; color: #1e293b; font-family: 'Consolas', monospace; border: 1px solid #ced4da;"
        )
        self.input_cmd.returnPressed.connect(self._on_command_entered)
        self.input_cmd.installEventFilter(self)
        input_layout.addWidget(self.input_cmd)

        btn_run = QPushButton("Ejecutar")
        btn_run.clicked.connect(self._on_command_entered)
        input_layout.addWidget(btn_run)

        layout.addLayout(input_layout)
        self.setWidget(widget)

        self.print_line("PyGSN Interactive Terminal v2.0 (PySide6 / Qt)")
        self.print_line("Escriba 'help' para ver la lista de comandos disponibles.\n")

    def sync_project(self):
        """Sincroniza el proyecto activo del engine con el de la ventana principal."""
        self.engine.project = self.get_project()
        sol = self.get_solution()
        if sol is not None:
            self.engine.last_solution = sol

    def print_line(self, text: str = ""):
        self.output.appendPlainText(text)
        self.output.moveCursor(QTextCursor.End)

    def print_warning(self, text: str):
        self.print_line(f"[AVISO] {text}")

    def print_error(self, text: str):
        self.print_line(f"[ERROR] {text}")

    def print_success(self, text: str):
        self.print_line(f"[ÉXITO] {text}")

    def _on_engine_output(self, text: str):
        if text == "[CLEAR]":
            self.output.clear()
        else:
            self.print_line(text)

    def _on_engine_project_modified(self):
        self.project_changed.emit()

    def _on_engine_solution_computed(self, sol: Any):
        self.solve_requested.emit()

    def _execute_command(self, cmd: str):
        """Ejecuta un comando programáticamente a través de CLIEngine."""
        self.sync_project()
        root = cmd.split()[0].lower() if cmd.strip() else ""
        if root in ("clear", "cls"):
            self.output.clear()
            return
        self.engine.execute(cmd)
        self.print_line("")

    def _on_command_entered(self):
        cmd = self.input_cmd.text().strip()
        if not cmd:
            return
        self.input_cmd.clear()
        self.history.append(cmd)
        self.history_idx = len(self.history)

        self.print_line(f"pygsn> {cmd}")
        self._execute_command(cmd)

    def eventFilter(self, obj, event):
        """Navegación del historial con flechas arriba/abajo."""
        if obj == self.input_cmd and event.type() == QEvent.KeyPress:
            key_event: QKeyEvent = event
            if key_event.key() == Qt.Key_Up:
                if self.history and self.history_idx > 0:
                    self.history_idx -= 1
                    self.input_cmd.setText(self.history[self.history_idx])
                    return True
                elif self.history and self.history_idx == 0:
                    self.input_cmd.setText(self.history[0])
                    return True
            elif key_event.key() == Qt.Key_Down:
                if self.history and self.history_idx < len(self.history) - 1:
                    self.history_idx += 1
                    self.input_cmd.setText(self.history[self.history_idx])
                    return True
                else:
                    self.history_idx = len(self.history)
                    self.input_cmd.clear()
                    return True
        return super().eventFilter(obj, event)

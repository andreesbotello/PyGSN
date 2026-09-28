"""
PyGSN - CLI Console Panel
=========================
Panel lateral colapsable (dock derecho) que proporciona una consola de comandos interactiva
y registro cronológico de eventos técnicos, logs de cálculo y salidas de operadores.
"""

from datetime import datetime
from typing import Callable, Any
import dearpygui.dearpygui as dpg
import numpy as np


class ConsolePanel:
    """Consola CLI integrada en la interfaz de PyGSN."""

    def __init__(
        self,
        get_project: Callable[[], Any],
        get_solution: Callable[[], Any],
        on_solve_requested: Callable[[], None],
        on_close_requested: Callable[[], None]
    ):
        self.get_project = get_project
        self.get_solution = get_solution
        self.on_solve_requested = on_solve_requested
        self.on_close_requested = on_close_requested

        # Histórico de logs
        self.history: list[str] = [
            f"[{datetime.now().strftime('%H:%M:%S')}] PyGSN CLI v1.0.0 iniciado.",
            f"[{datetime.now().strftime('%H:%M:%S')}] Escriba 'help' para listar los comandos disponibles."
        ]

    def log(self, message: str, level: str = "INFO"):
        """Registra una línea en la consola con timestamp."""
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] [{level}] {message}"
        self.history.append(entry)
        if len(self.history) > 300:
            self.history.pop(0)
        self._update_text()

    def _update_text(self):
        if dpg.does_item_exist("console_log_text"):
            full_text = "\n".join(self.history)
            dpg.set_value("console_log_text", full_text)

    def clear(self):
        """Limpia el histórico de la consola."""
        self.history = [f"[{datetime.now().strftime('%H:%M:%S')}] Consola reiniciada."]
        self._update_text()

    def execute_command(self, cmd_line: str):
        """Parsea y ejecuta un comando ingresado en la consola."""
        cmd = cmd_line.strip()
        if not cmd:
            return

        self.log(f"> {cmd}", level="CMD")
        tokens = cmd.split()
        verb = tokens[0].lower()

        proj = self.get_project()
        plat = proj.platform if proj else None

        if verb in ("help", "?"):
            help_lines = [
                "Comandos CLI Disponibles en PyGSN:",
                "  help               - Muestra esta lista de comandos",
                "  status             - Muestra estado del proyecto, elipsoide y plataforma",
                "  platforms          - Lista plataformas del proyecto y cuál está activa",
                "  sensors            - Lista sensores de la plataforma activa con sus lever-arms",
                "  solve              - Ejecuta el solver SVD de georreferenciación",
                "  diag               - Muestra diagnóstico espectral y ortonormalidad DCM",
                "  residuals          - Muestra residuales métricos (GNSS vs INS)",
                "  clear              - Limpia la pantalla de la consola",
                "  close / exit       - Cierra el panel de la consola"
            ]
            for h in help_lines:
                self.log(h, level="INFO")

        elif verb == "status":
            if not proj:
                self.log("Sin proyecto cargado.", level="WARN")
                return
            self.log(f"Proyecto: {proj.name} | Elipsoide: {proj.ellipsoid_name}", level="INFO")
            self.log(f"Plataforma activa: [{plat.id}] {plat.name} ({plat.platform_type})", level="INFO")
            self.log(f"Sensores instalados: {len(plat.sensors)}", level="INFO")
            sol = self.get_solution()
            if sol:
                self.log("Solución activa: Resuelta con éxito (SVD Kabsch).", level="INFO")
            else:
                self.log("Solución activa: Ninguna (datos pendientes de resolver).", level="WARN")

        elif verb == "platforms":
            if not proj:
                self.log("Sin proyecto.", level="WARN")
                return
            self.log(f"Plataformas en el Proyecto ({len(proj.platforms)}):", level="INFO")
            for pid, p in proj.platforms.items():
                act = " [*ACTIVA]" if pid == proj.active_platform_id else ""
                fix = " (Fija)" if p.is_fixed else " (Móvil)"
                self.log(f"  - [{pid}] {p.name} [{p.platform_type}]{fix}{act}, {len(p.sensors)} sensores", level="INFO")

        elif verb == "sensors":
            if not plat:
                self.log("Sin plataforma activa.", level="WARN")
                return
            self.log(f"Sensores de [{plat.name}] ({len(plat.sensors)}):", level="INFO")
            for code, s in plat.sensors.items():
                x1, x2, x3 = s.lever_arm_b
                self.log(f"  - [{code}] {s.name} ({s.sensor_type.value}) Arm=[{x1:.3f}, {x2:.3f}, {x3:.3f}]m", level="INFO")

        elif verb == "solve":
            self.log("Ejecutando solver SVD de georreferenciación...", level="INFO")
            self.on_solve_requested()

        elif verb == "diag":
            sol = self.get_solution()
            if not sol:
                self.log("No hay solución calculada. Ejecute 'solve' primero.", level="WARN")
                return
            det = float(np.linalg.det(sol.Cb2n_gnss))
            ortho = float(np.linalg.norm(sol.Cb2n_gnss @ sol.Cb2n_gnss.T - np.eye(3)))
            r, p, y = sol.attitude_gnss_deg
            self.log(f"det(Cb2n) = {det:+.8f} | Error Ortonormalidad = {ortho:.2e}", level="INFO")
            self.log(f"Actitud GNSS: Roll={r:+.4f}°, Pitch={p:+.4f}°, Yaw={y:+.4f}°", level="INFO")

        elif verb == "residuals":
            sol = self.get_solution()
            if not sol or not sol.diff_gnss_ins_utm:
                self.log("Sin residuales calculados. Cargue observaciones y resuelva primero.", level="WARN")
                return
            self.log("Residuales Métricos GNSS vs INS (dE, dN, dH) [m]:", level="INFO")
            for code, (de, dn, dh) in sol.diff_gnss_ins_utm.items():
                self.log(f"  [{code}] dE={de:+7.4f}m, dN={dn:+7.4f}m, dH={dh:+7.4f}m", level="INFO")

        elif verb == "clear":
            self.clear()

        elif verb in ("close", "exit"):
            self.on_close_requested()

        else:
            self.log(f"Comando no reconocido: '{verb}'. Escriba 'help' para ver la lista.", level="ERROR")

    def build_ui(self, parent_tag: str):
        """Construye los widgets del panel de consola."""
        with dpg.group(parent=parent_tag):
            # Cabecera
            with dpg.group(horizontal=True):
                dpg.add_text("Consola CLI", color=(0, 180, 216, 255))
                dpg.add_spacer(width=40)
                dpg.add_button(label="Limpiar", small=True, callback=self.clear)
                dpg.add_button(label="X", small=True, callback=self.on_close_requested)

            dpg.add_separator()
            dpg.add_spacer(height=3)

            # Área con scroll para el registro de texto monospaciado
            with dpg.child_window(height=-45, border=True, tag="child_console_logs"):
                dpg.add_text("\n".join(self.history), tag="console_log_text")

            dpg.add_spacer(height=4)

            # Input interactivo inferior
            with dpg.group(horizontal=True):
                def _cb_submit(sender, app_data):
                    val = dpg.get_value("console_input_box")
                    if val:
                        self.execute_command(val)
                        dpg.set_value("console_input_box", "")

                dpg.add_input_text(
                    hint="Comando CLI (help, status, solve)...",
                    width=-70,
                    on_enter=True,
                    callback=_cb_submit,
                    tag="console_input_box"
                )
                dpg.add_button(label="Enviar", width=60, callback=_cb_submit)

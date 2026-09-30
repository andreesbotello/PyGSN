"""
PyGSN - Console & CLI Dock (PySide6 / Qt)
=========================================
Terminal interactiva CLI integrada en un dock desacoplable:
- Ejecución rápida de comandos (help, status, platforms, sensors, solve, residuals, diag, clear).
- Historial de comandos navegable con flechas arriba/abajo.
"""

import re
import numpy as np
from typing import Callable, Optional, List, Any
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QLineEdit, QPushButton, QLabel
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor

from core.models import Platform, Sensor, SensorType, PlatformType
from core.project import Project


class ConsoleDock(QDockWidget):
    """Terminal CLI integrada para PyGSN."""

    solve_requested = Signal()
    diagnostics_requested = Signal()
    residuals_requested = Signal()
    chassis_modified = Signal()
    sensor_modified = Signal()
    platform_created = Signal(str)

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
        self.setMinimumWidth(320)

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
            self.print_line("Comandos disponibles en PyGSN CLI:")
            self.print_line("  help                                    : Muestra esta ayuda")
            self.print_line("  status                                  : Estado del proyecto, plataforma y geodesia")
            self.print_line("  platforms                               : Lista las plataformas del proyecto")
            self.print_line("  platform add <id> [nom] [tipo] [fija]   : Crea y activa una plataforma en el workspace")
            self.print_line("  platform select <id>                    : Activa una plataforma existente")
            self.print_line("  chassis                                 : Consulta el chasis de la plataforma activa")
            self.print_line("  chassis box <L> <W> <H>                 : Define caja envolvente 3D (Largo, Ancho, Alto en m)")
            self.print_line("  chassis poly [S|F|L] (p1) (p2) ...      : Define polígono 2D por vértices")
            self.print_line("  chassis pts (x,y,z) ...                 : Define vértices 3D con proyección a 3 vistas")
            self.print_line("  chassis move <dx> <dy> [dz]             : Traslada el chasis métricamente")
            self.print_line("  chassis center                          : Centra la geometría del chasis en PLA [0, 0, 0]")
            self.print_line("  chassis rotate <deg> [S|F|L]            : Rota el chasis en el plano ortogonal")
            self.print_line("  chassis scale <fx> <fy> [fz]            : Escala las dimensiones del chasis")
            self.print_line("  chassis clear                           : Elimina el chasis (modo chasis libre)")
            self.print_line("  sensors                                 : Lista los sensores de la plataforma activa")
            self.print_line("  sensor add <code> <tipo> [x] [y] [z]    : Añade un sensor a la plataforma activa")
            self.print_line("  sensor place <code> <x> <y> [z]         : Posiciona lever-arm de un sensor")
            self.print_line("  sensor move <code> <dx> <dy> [dz]       : Traslada lever-arm de un sensor")
            self.print_line("  sensor rotate <code> <dr> <dp> <dy>     : Rota boresight (roll, pitch, yaw deg)")
            self.print_line("  sensor remove <code>                    : Elimina un sensor de la plataforma")
            self.print_line("  solve                                   : Ejecuta el solver SVD de georreferenciación")
            self.print_line("  residuals                               : Inspecciona los residuales del cálculo")
            self.print_line("  diag                                    : Auditoría espectral y diagnóstico DCM")
            self.print_line("  clear                                   : Limpia la pantalla de la terminal\n")

        elif root_cmd == "status":
            proj = self.get_project()
            plat = proj.platform
            self.print_line(f"Proyecto : {proj.name}")
            self.print_line(f"Elipsoide: {proj.ellipsoid_name} | Huso UTM: {proj.config.get('utm_zone', 30)}")
            self.print_line(f"Plat. Act: {plat.name if plat else '(ninguna)'}")
            n_sens = len(plat.sensors) if plat else 0
            self.print_line(f"Sensores : {n_sens}\n")

        elif root_cmd in ("platform", "plat"):
            self._handle_platform_command(parts[1:])

        elif root_cmd == "platforms":
            proj = self.get_project()
            if not proj.platforms:
                self.print_line("No hay plataformas registradas en el proyecto.\n")
                return
            self.print_line(f"Total plataformas: {len(proj.platforms)}")
            for pid, p in proj.platforms.items():
                active_mark = " [*ACTIVA]" if pid == proj.active_platform_id else ""
                dims_str = f" [L={p.length_m:.2f}m, W={p.width_m:.2f}m, H={p.height_m:.2f}m]" if p.has_dimensions else " [Chasis libre]"
                self.print_line(f"  [{pid}] {p.name} ({p.platform_type}){dims_str}{active_mark}")
            self.print_line("")

        elif root_cmd == "chassis":
            self._handle_chassis_command(cmd, parts[1:])

        elif root_cmd in ("sensors", "sensor", "sens"):
            self._handle_sensor_command(cmd, parts[1:])

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

    def _handle_platform_command(self, args: List[str]):
        proj = self.get_project()
        if not args:
            self.print_line("Uso de comando platform:")
            self.print_line("  platform add <id> [nombre] [tipo]")
            self.print_line("  platform select <id>\n")
            return

        sub = args[0].lower()
        if sub in ("add", "create", "new"):
            if len(args) < 2:
                self.print_line("Error: Debe indicar al menos el identificador (ej: platform add V1 'Vehiculo 1' VEHICLE fija).\n")
                return
            pid = args[1].upper()
            pname = args[2] if len(args) >= 3 else pid
            ptype = args[3].upper() if len(args) >= 4 else "GENERIC"
            is_fixed = False
            if len(args) >= 5:
                is_fixed = args[4].lower() in ("true", "1", "fixed", "fija", "si", "yes")

            if pid in proj.platforms:
                self.print_line(f"Aviso: La plataforma '{pid}' ya existe. Seleccionándola como activa.")
            else:
                plat = Platform(id=pid, name=pname, platform_type=ptype, is_fixed=is_fixed)
                proj.add_platform(plat)
                self.print_line(f"[OK] Plataforma creada: [{pid}] {pname} ({ptype}, fija={is_fixed})")
            proj.set_active_platform(pid)
            self.platform_created.emit(pid)
            self.print_line(f"[OK] Plataforma '{pid}' activada en el Workspace CAD.\n")

        elif sub in ("select", "use", "open"):
            if len(args) < 2:
                self.print_line("Error: Indique el identificador (ej: platform select PLAT_1).\n")
                return
            pid = args[1].upper()
            if pid not in proj.platforms:
                self.print_line(f"Error: La plataforma '{pid}' no existe en el proyecto.\n")
                return
            proj.set_active_platform(pid)
            self.platform_created.emit(pid)
            self.print_line(f"[OK] Plataforma activa conmutada a '{pid}'.\n")

        else:
            self.print_line(f"Subcomando desconocido: 'platform {sub}'. Escriba 'help'.\n")

    def _handle_chassis_command(self, full_cmd: str, args: List[str]):
        proj = self.get_project()
        plat = proj.platform
        if not plat:
            self.print_line("Error: No hay plataforma activa. Cree o active una con 'platform add <id>'.\n")
            return

        if not args:
            # Mostrar información del chasis activo
            if not plat.has_dimensions:
                self.print_line(f"Plataforma '{plat.name}': Chasis Libre (sin dimensiones ni caja envolvente).")
                self.print_line("Para definir chasis use:")
                self.print_line("  chassis box <Largo> <Ancho> <Alto>              (ej: chassis box 4.2 1.8 1.4)")
                self.print_line("  chassis poly S (x1,y1) (x2,y2) (x3,y3) (x4,y4)  (ej: chassis poly S (2,-1) (2,1) (-2,1) (-2,-1))")
                self.print_line("  chassis pts (x,y,z) ...                         (vértices 3D con proyección a 3 vistas)\n")
            else:
                self.print_line(f"Chasis activo en '{plat.name}':")
                self.print_line(f"  Dimensiones Envolventes : Largo={plat.length_m:.3f}m, Ancho={plat.width_m:.3f}m, Alto={plat.height_m:.3f}m")
                if plat.chassis_polygon:
                    pts_str = " -> ".join([f"[{p[0]:+.2f}, {p[1]:+.2f}]" for p in plat.chassis_polygon])
                    self.print_line(f"  Polígono 2D Planta (S)  : {len(plat.chassis_polygon)} vértices: {pts_str}")
                else:
                    self.print_line("  Tipo                    : Caja envolvente rectangular centrada en [0, 0, 0]")
                self.print_line("")
            return

        sub = args[0].lower()

        # 1. Limpieza de chasis
        if sub in ("clear", "reset", "free", "none"):
            plat.has_dimensions = False
            plat.length_m = 0.0
            plat.width_m = 0.0
            plat.height_m = 0.0
            plat.chassis_polygon = None
            self.chassis_modified.emit()
            self.print_line(f"[OK] Chasis eliminado en '{plat.name}'. Plataforma en modo chasis libre.\n")
            return

        # 2. Caja envolvente rectangular directa: chassis box <L> <W> <H> o chassis dims <L> <W> <H>
        if sub in ("box", "dims", "caja") or (len(args) >= 3 and self._is_float(args[0]) and self._is_float(args[1]) and self._is_float(args[2])):
            num_args = args[1:] if sub in ("box", "dims", "caja") else args
            if len(num_args) < 3:
                self.print_line("Error: Debe indicar 3 dimensiones numéricas: Largo Ancho Alto (ej: chassis box 4.2 1.8 1.4).\n")
                return
            try:
                l = abs(float(num_args[0]))
                w = abs(float(num_args[1]))
                h = abs(float(num_args[2]))
                plat.length_m = round(l, 4)
                plat.width_m = round(w, 4)
                plat.height_m = round(h, 4)
                plat.has_dimensions = True
                plat.chassis_polygon = None
                self.chassis_modified.emit()
                self.print_line(f"[OK] Chasis definido para '{plat.name}':")
                self.print_line(f"     Largo Xb={l:.3f}m | Ancho Yb={w:.3f}m | Alto Zb={h:.3f}m")
                self.print_line("     Proyectado simétricamente a las vistas Superior, Frontal y Lateral.\n")
            except ValueError:
                self.print_line("Error: Las dimensiones deben ser valores numéricos válidos en metros.\n")
            return

        # 3. Polígono por coordenadas 2D en una vista: chassis poly [S|F|L] (p1) (p2) ...
        if sub in ("poly", "poligono", "polygon"):
            view_code = "S"
            tokens_str = full_cmd
            # Verificar si se especificó vista (S, F o L)
            if len(args) >= 2 and args[1].upper() in ("S", "F", "L"):
                view_code = args[1].upper()

            # Extraer todas las tuplas de números (x, y) del comando
            matches = re.findall(
                r'\(?\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)(?:\s*,\s*([+-]?\d+(?:\.\d+)?))?\s*\)?',
                tokens_str
            )
            if len(matches) < 3:
                self.print_line("Error: Un contorno poligonal requiere al menos 3 vértices.")
                self.print_line("Ejemplo: chassis poly S (2, -1) (2, 1) (-2, 1) (-2, -1)\n")
                return

            pts_2d = [(float(m[0]), float(m[1])) for m in matches]
            u_vals = [p[0] for p in pts_2d]
            v_vals = [p[1] for p in pts_2d]
            extent_u = max(0.05, max(u_vals) - min(u_vals))
            extent_v = max(0.05, max(v_vals) - min(v_vals))

            prev_h = plat.height_m if plat.has_dimensions and plat.height_m > 0 else 0.50
            prev_l = plat.length_m if plat.has_dimensions and plat.length_m > 0 else 2.00
            prev_w = plat.width_m if plat.has_dimensions and plat.width_m > 0 else 1.00

            if view_code == "S":
                # u = Xb (Largo), v = Yb (Ancho)
                plat.length_m = round(extent_u, 4)
                plat.width_m = round(extent_v, 4)
                plat.height_m = round(prev_h, 4)
                plat.chassis_polygon = [[p[0], p[1]] for p in pts_2d]
                view_name = "Superior (Planta: Xb vs Yb)"
            elif view_code == "F":
                # u = Yb (Ancho), v = Zb (Alto)
                plat.width_m = round(extent_u, 4)
                plat.height_m = round(extent_v, 4)
                plat.length_m = round(prev_l, 4)
                view_name = "Frontal (Alzado: Yb vs -Zb)"
            else: # L
                # u = Xb (Largo), v = Zb (Alto)
                plat.length_m = round(extent_u, 4)
                plat.height_m = round(extent_v, 4)
                plat.width_m = round(prev_w, 4)
                view_name = "Lateral (Perfil: Xb vs -Zb)"

            plat.has_dimensions = True
            self.chassis_modified.emit()
            self.print_line(f"[OK] Polígono de chasis definido ({len(pts_2d)} vértices) en vista {view_name}:")
            self.print_line(f"     Dimensiones envolventes: Largo={plat.length_m:.3f}m, Ancho={plat.width_m:.3f}m, Alto={plat.height_m:.3f}m")
            self.print_line("     Geometría proyectada instantáneamente a las 3 vistas ortogonales del Workspace.\n")
            return

        # 4. Puntos 3D globales: chassis pts (x, y, z) (x, y, z) ...
        if sub in ("pts", "puntos", "points", "3d"):
            matches_3d = re.findall(
                r'\(?\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\)?',
                full_cmd
            )
            if len(matches_3d) < 3:
                self.print_line("Error: Debe proporcionar al menos 3 puntos en formato 3D (X, Y, Z).")
                self.print_line("Ejemplo: chassis pts (2, -1, 0) (2, 1, 0) (-2, 1, 0.5) (-2, -1, 0.5)\n")
                return

            pts_3d = [(float(m[0]), float(m[1]), float(m[2])) for m in matches_3d]
            xs = [p[0] for p in pts_3d]
            ys = [p[1] for p in pts_3d]
            zs = [p[2] for p in pts_3d]
            plat.length_m = round(max(0.05, max(xs) - min(xs)), 4)
            plat.width_m = round(max(0.05, max(ys) - min(ys)), 4)
            plat.height_m = round(max(0.05, max(zs) - min(zs)), 4)
            plat.chassis_polygon = [[p[0], p[1]] for p in pts_3d] # Proyección a planta
            plat.has_dimensions = True
            self.chassis_modified.emit()
            self.print_line(f"[OK] Chasis definido a partir de {len(pts_3d)} puntos 3D:")
            self.print_line(f"     Largo={plat.length_m:.3f}m, Ancho={plat.width_m:.3f}m, Alto={plat.height_m:.3f}m")
            self.print_line("     Proyectado a las vistas Superior, Frontal y Lateral.\n")
            return

        # 5. Mover chasis: chassis move <dx> <dy> [dz]
        if sub in ("move", "mover", "trasladar", "desplazar"):
            if len(args) < 3:
                self.print_line("Error: Indique al menos dx y dy (ej: chassis move 0.5 -0.2 [dz]).\n")
                return
            try:
                dx = float(args[1])
                dy = float(args[2])
                dz = float(args[3]) if len(args) > 3 else 0.0
                plat.translate(dx, dy, dz)
                self.chassis_modified.emit()
                c = plat.chassis_center_b
                self.print_line(f"[OK] Chasis desplazado: dx={dx:+.3f}m, dy={dy:+.3f}m, dz={dz:+.3f}m.")
                self.print_line(f"     Nuevo centroide PLA: [{c[0]:.3f}, {c[1]:.3f}, {c[2]:.3f}]m.\n")
            except ValueError:
                self.print_line("Error: Los valores de desplazamiento deben ser numéricos.\n")
            return

        # 6. Centrar chasis al origen PLA: chassis center
        if sub in ("center", "centrar", "origin", "origen"):
            dx, dy, dz = plat.center_to_origin()
            self.chassis_modified.emit()
            self.print_line(f"[OK] Geometría del chasis centrada en el origen PLA [0, 0, 0] (traslación: [{dx:+.3f}, {dy:+.3f}, {dz:+.3f}]m).\n")
            return

        # 7. Rotar chasis en plano ortogonal: chassis rotate <deg> [S|F|L]
        if sub in ("rotate", "rotar", "rot"):
            if len(args) < 2:
                self.print_line("Error: Indique el ángulo en grados (ej: chassis rotate 45 [S|F|L]).\n")
                return
            try:
                ang = float(args[1])
                plane = args[2].upper() if len(args) > 2 else "S"
                if plane not in ("S", "F", "L"):
                    plane = "S"
                plat.rotate_plane(ang, plane)
                self.chassis_modified.emit()
                self.print_line(f"[OK] Chasis rotado {ang:+.2f}° en plano {plane}.")
                self.print_line(f"     Nuevas dimensiones: Largo={plat.length_m:.3f}m, Ancho={plat.width_m:.3f}m.\n")
            except ValueError:
                self.print_line("Error: El ángulo debe ser un valor numérico en grados.\n")
            return

        # 8. Escalar dimensiones de chasis: chassis scale <fx> <fy> [fz]
        if sub in ("scale", "escalar"):
            if len(args) < 3:
                self.print_line("Error: Indique factores fx y fy (y opcional fz). Ej: chassis scale 1.2 1.2 [1.0]\n")
                return
            try:
                fx = float(args[1])
                fy = float(args[2])
                fz = float(args[3]) if len(args) > 3 else 1.0
                plat.scale_dimensions(fx, fy, fz)
                self.chassis_modified.emit()
                self.print_line(f"[OK] Chasis escalado ({fx:.2f}x, {fy:.2f}x, {fz:.2f}x).")
                self.print_line(f"     Nuevas cotas: Largo={plat.length_m:.3f}m, Ancho={plat.width_m:.3f}m, Alto={plat.height_m:.3f}m.\n")
            except ValueError:
                self.print_line("Error: Los factores de escala deben ser numéricos.\n")
            return

        self.print_line(f"Subcomando de chasis desconocido: '{sub}'. Escriba 'help' o 'chassis' sin argumentos.\n")

    def _handle_sensor_command(self, full_cmd: str, args: List[str]):
        proj = self.get_project()
        plat = proj.platform
        if not plat:
            self.print_line("Error: No hay plataforma activa. Active una con 'platform select <id>'.\n")
            return

        if not args or args[0].lower() in ("list", "ls"):
            if not plat.sensors:
                self.print_line(f"La plataforma '{plat.name}' no tiene sensores montados.\n")
                return
            self.print_line(f"Sensores en '{plat.name}':")
            for c, s in plat.sensors.items():
                arm = s.lever_arm_b
                b_deg = s.boresight_deg
                self.print_line(f"  {c:<6s} [{s.sensor_type.value:<6s}] arm=[{arm[0]:+.3f}, {arm[1]:+.3f}, {arm[2]:+.3f}]m  boresight=({b_deg[0]:.1f}, {b_deg[1]:.1f}, {b_deg[2]:.1f})°  {s.name}")
            self.print_line("")
            return

        sub = args[0].lower()

        # 1. sensor add <code> <tipo> [x] [y] [z] [r] [p] [y] [nombre]
        if sub in ("add", "crear", "new"):
            if len(args) < 3:
                self.print_line("Uso: sensor add <code> <tipo> [x] [y] [z] [roll] [pitch] [yaw] [nombre]")
                self.print_line("Tipos válidos: GNSS, INS, CAMERA, LIDAR, ODOMETER, OTHER\n")
                return
            code = args[1].upper()
            stype_str = args[2].upper()
            try:
                stype = SensorType(stype_str)
            except ValueError:
                stype = SensorType.OTHER
                for t in SensorType:
                    if stype_str in t.value or t.value in stype_str:
                        stype = t
                        break

            x = float(args[3]) if len(args) > 3 and self._is_float(args[3]) else 0.0
            y = float(args[4]) if len(args) > 4 and self._is_float(args[4]) else 0.0
            z = float(args[5]) if len(args) > 5 and self._is_float(args[5]) else 0.0

            r = float(args[6]) if len(args) > 6 and self._is_float(args[6]) else 0.0
            p = float(args[7]) if len(args) > 7 and self._is_float(args[7]) else 0.0
            yaw = float(args[8]) if len(args) > 8 and self._is_float(args[8]) else 0.0

            name = " ".join(args[9:]) if len(args) > 9 else f"Sensor {code}"

            sens = Sensor(
                code=code,
                name=name,
                sensor_type=stype,
                lever_arm_b=np.array([x, y, z], dtype=np.float64),
                boresight_deg=(r, p, yaw)
            )
            plat.add_sensor(sens)
            self.sensor_modified.emit()
            self.print_line(f"[OK] Sensor {code} [{stype.value}] añadido a '{plat.name}':")
            self.print_line(f"     lever_arm=[{x:+.3f}, {y:+.3f}, {z:+.3f}]m | boresight=({r:.1f}, {p:.1f}, {yaw:.1f})°\n")
            return

        # 2. sensor place <code> <x> <y> [z]
        if sub in ("place", "ubicar", "set"):
            if len(args) < 4:
                self.print_line("Uso: sensor place <code> <x> <y> [z]\n")
                return
            code = args[1].upper()
            if code not in plat.sensors:
                self.print_line(f"Error: Sensor '{code}' no encontrado en la plataforma activa '{plat.name}'.\n")
                return
            try:
                x = float(args[2])
                y = float(args[3])
                z = float(args[4]) if len(args) > 4 else float(plat.sensors[code].lever_arm_b[2])
                plat.sensors[code].lever_arm_b = np.array([x, y, z], dtype=np.float64)
                self.sensor_modified.emit()
                self.print_line(f"[OK] Lever-arm de sensor {code} posicionado en [{x:.3f}, {y:.3f}, {z:.3f}]m.\n")
            except ValueError:
                self.print_line("Error: Coordenadas métricas no válidas.\n")
            return

        # 3. sensor move <code> <dx> <dy> [dz]
        if sub in ("move", "mover"):
            if len(args) < 4:
                self.print_line("Uso: sensor move <code> <dx> <dy> [dz]\n")
                return
            code = args[1].upper()
            if code not in plat.sensors:
                self.print_line(f"Error: Sensor '{code}' no encontrado en la plataforma activa '{plat.name}'.\n")
                return
            try:
                dx = float(args[2])
                dy = float(args[3])
                dz = float(args[4]) if len(args) > 4 else 0.0
                plat.sensors[code].lever_arm_b += np.array([dx, dy, dz], dtype=np.float64)
                arm = plat.sensors[code].lever_arm_b
                self.sensor_modified.emit()
                self.print_line(f"[OK] Lever-arm de {code} desplazado por [dx={dx:+.3f}, dy={dy:+.3f}, dz={dz:+.3f}]m.")
                self.print_line(f"     Nueva posición: [{arm[0]:.3f}, {arm[1]:.3f}, {arm[2]:.3f}]m.\n")
            except ValueError:
                self.print_line("Error: Los desplazamientos deben ser valores numéricos.\n")
            return

        # 4. sensor rotate <code> <droll> <dpitch> <dyaw>
        if sub in ("rot", "rotate", "rotar"):
            if len(args) < 5:
                self.print_line("Uso: sensor rotate <code> <droll> <dpitch> <dyaw>\n")
                return
            code = args[1].upper()
            if code not in plat.sensors:
                self.print_line(f"Error: Sensor '{code}' no encontrado en la plataforma activa '{plat.name}'.\n")
                return
            try:
                dr = float(args[2])
                dp = float(args[3])
                dy = float(args[4])
                r, p, y = plat.sensors[code].boresight_deg
                plat.sensors[code].boresight_deg = (round(r + dr, 3), round(p + dp, 3), round(y + dy, 3))
                nb = plat.sensors[code].boresight_deg
                self.sensor_modified.emit()
                self.print_line(f"[OK] Boresight de sensor {code} rotado por (dr={dr:+.2f}°, dp={dp:+.2f}°, dy={dy:+.2f}°).")
                self.print_line(f"     Nueva orientación: Roll={nb[0]:.2f}°, Pitch={nb[1]:.2f}°, Yaw={nb[2]:.2f}°.\n")
            except ValueError:
                self.print_line("Error: Los ángulos deben ser valores numéricos en grados.\n")
            return

        # 5. sensor remove <code>
        if sub in ("remove", "rm", "del", "delete", "eliminar"):
            if len(args) < 2:
                self.print_line("Uso: sensor remove <code>\n")
                return
            code = args[1].upper()
            if plat.remove_sensor(code):
                self.sensor_modified.emit()
                self.print_line(f"[OK] Sensor {code} eliminado de la plataforma '{plat.name}'.\n")
            else:
                self.print_line(f"Error: Sensor '{code}' no existe en '{plat.name}'.\n")
            return

        self.print_line(f"Subcomando de sensor desconocido: 'sensor {sub}'. Escriba 'help'.\n")

    @staticmethod
    def _is_float(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False


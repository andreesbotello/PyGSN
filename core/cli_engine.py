"""
PyGSN - Core CLI Engine
=======================
Motor de interpretación y ejecución de comandos CLI desacoplado de la interfaz gráfica:
- Ejecutable en consolas nativas del sistema operativo (headless REPL).
- Reutilizable por el dock gráfico ConsoleDock de PySide6 / Qt.
- Soporta creación de proyectos, configuración de SRT, modelado de chasis,
  montaje de sensores, importación tabular (.xlsx/.csv), resolución SVD Kabsch + INS,
  residuales, diagnósticos y generación de informes técnicos.
"""

import sys
import re
import math
from pathlib import Path
from typing import Callable, Any, Optional
import numpy as np

from .models import Platform, Sensor, SensorType, ReferenceSystem
from .project import Project


class CLIEngine:
    """Motor agnóstico e interactivo de comandos de ingeniería para PyGSN."""

    def __init__(
        self,
        project: Optional[Project] = None,
        stdout_callback: Optional[Callable[[str], None]] = None,
        on_project_modified: Optional[Callable[[], None]] = None,
        on_chassis_modified: Optional[Callable[[], None]] = None,
        on_sensor_modified: Optional[Callable[[], None]] = None,
        on_platform_created: Optional[Callable[[str], None]] = None,
        on_solution_computed: Optional[Callable[[Any], None]] = None,
    ):
        self.project: Project = project if project is not None else Project(name="Proyecto CLI")
        self.stdout_callback: Callable[[str], None] = stdout_callback if stdout_callback is not None else print
        self.on_project_modified = on_project_modified
        self.on_chassis_modified = on_chassis_modified
        self.on_sensor_modified = on_sensor_modified
        self.on_platform_created = on_platform_created
        self.on_solution_computed = on_solution_computed

        self.last_solution: Any = None
        self.current_project_file: Optional[Path] = None
        self.history: list[str] = []

    def set_project(self, project: Project):
        self.project = project
        self.last_solution = getattr(project, "_last_solution", None)
        if self.on_project_modified:
            self.on_project_modified()

    def print_line(self, text: str = ""):
        self.stdout_callback(text)

    def print_warning(self, text: str):
        self.print_line(f"[AVISO] {text}")

    def print_error(self, text: str):
        self.print_line(f"[ERROR] {text}")

    def print_success(self, text: str):
        self.print_line(f"[ÉXITO] {text}")

    def execute(self, cmd_line: str) -> bool:
        """
        Ejecuta una línea de comando.
        Retorna True si el bucle interactivo debe continuar, o False si se solicita salir.
        """
        line = cmd_line.strip()
        if not line:
            return True

        import shlex
        try:
            parts = [t.strip('"\'') for t in shlex.split(line, posix=False)]
        except Exception:
            parts = line.split()

        if not parts:
            return True
        root = parts[0].lower()

        if root in ("exit", "quit", "q"):
            self.print_line("Saliendo de la consola PyGSN...")
            return False

        elif root in ("help", "?"):
            self._cmd_help(parts[1:] if len(parts) > 1 else [])

        elif root in ("clear", "cls"):
            # En terminales nativas se puede limpiar
            if self.stdout_callback == print:
                import os
                os.system("cls" if os.name == "nt" else "clear")
            else:
                self.print_line("[CLEAR]")

        elif root in ("status", "info"):
            self._cmd_status()

        elif root == "project":
            self._cmd_project(parts[1:])

        elif root in ("srt", "srts"):
            self._cmd_srt(parts[1:])

        elif root in ("platforms", "platform", "plat"):
            if root == "platforms" and len(parts) == 1:
                self._cmd_platform(["list"])
            else:
                self._cmd_platform(parts[1:])

        elif root == "chassis":
            self._cmd_chassis(line, parts[1:])

        elif root in ("sensors", "sensor", "sens"):
            if root == "sensors" and len(parts) == 1:
                self._cmd_sensor(line, ["list"])
            else:
                self._cmd_sensor(line, parts[1:])

        elif root == "import":
            self._cmd_import(parts[1:])

        elif root in ("solve", "calcular", "run"):
            self._cmd_solve(parts[1:])

        elif root in ("residuals", "residuos"):
            self._cmd_residuals()

        elif root in ("diag", "diagnostics", "audit"):
            self._cmd_diag()

        elif root in ("report", "informe"):
            self._cmd_report(parts[1:])

        else:
            self.print_error(f"Comando desconocido: '{root}'. Escriba 'help' para ver la lista de comandos disponibles.")

        return True

    # -------------------------------------------------------------------------
    # Implementación de Comandos
    # -------------------------------------------------------------------------
    def _cmd_help(self, args: list[str]):
        self.print_line("================================================================================")
        self.print_line("PyGSN CLI - Comandos disponibles:")
        self.print_line("================================================================================")
        self.print_line("Gestión de Proyectos:")
        self.print_line("  project new <nombre> [elipsoide] [utm] [N] [decl] : Crea un proyecto limpio")
        self.print_line("  project open <archivo.pygsn>                      : Carga un proyecto desde disco")
        self.print_line("  project save [archivo.pygsn]                      : Guarda el proyecto activo")
        self.print_line("  project status                                    : Resumen completo del proyecto")
        self.print_line("")
        self.print_line("Sistemas de Referencia Terrestres (SRT / e-frame):")
        self.print_line("  srt list                                          : Lista los SRT del proyecto")
        self.print_line("  srt add <id> [nombre] [elipsoide] [utm] [N] [dec] : Crea un nuevo SRT y lo activa")
        self.print_line("  srt select <id>                                   : Conmuta el SRT activo")
        self.print_line("")
        self.print_line("Plataformas (Vehículos / Rigs):")
        self.print_line("  platform list                                     : Lista las plataformas del proyecto")
        self.print_line("  platform add <id> [nombre] [tipo] [fija]          : Crea y activa una plataforma")
        self.print_line("  platform select <id>                              : Conmuta la plataforma activa")
        self.print_line("")
        self.print_line("Modelado Cinemático de Chasis:")
        self.print_line("  chassis                                           : Muestra la geometría del chasis")
        self.print_line("  chassis box <L> <W> <H>                           : Define caja envolvente 3D (m)")
        self.print_line("  chassis poly [S|F|L] (x1,y1) (x2,y2) ...          : Define polígono por vértices 2D")
        self.print_line("  chassis pts (x,y,z) ...                           : Define vértices 3D con proyección")
        self.print_line("  chassis move <dx> <dy> [dz]                       : Traslada la carrocería")
        self.print_line("  chassis center                                    : Centra el chasis en el origen PLA [0,0,0]")
        self.print_line("  chassis rotate <deg> [S|F|L]                      : Rota en plano ortogonal")
        self.print_line("  chassis scale <fx> <fy> [fz]                      : Escala las dimensiones métricas")
        self.print_line("  chassis clear                                     : Elimina el chasis (modo chasis libre)")
        self.print_line("")
        self.print_line("Sensores y Calibración:")
        self.print_line("  sensors                                           : Lista los sensores del rig activo")
        self.print_line("  sensor add <code> <tipo> [x] [y] [z] [r] [p] [y]  : Añade un sensor a la plataforma")
        self.print_line("  sensor place <code> <x> <y> [z]                   : Posiciona el lever-arm métrico")
        self.print_line("  sensor move <code> <dx> <dy> [dz]                 : Desplaza el lever-arm")
        self.print_line("  sensor rotate <code> <dr> <dp> <dy>               : Rota boresight (roll, pitch, yaw deg)")
        self.print_line("  sensor remove <code>                              : Elimina un sensor")
        self.print_line("")
        self.print_line("Importación, Cómputo y Reportes:")
        self.print_line("  import table <ruta_archivo>                       : Importa sensores y obs (.xlsx, .csv, .txt)")
        self.print_line("  solve [method]                                    : Resuelve SVD Kabsch + INS")
        self.print_line("  residuals                                         : Inspecciona tabla de residuales GNSS vs INS")
        self.print_line("  diag                                              : Auditoría DCM y condicionamiento numérico")
        self.print_line("  report [ruta_salida.txt]                          : Muestra o exporta el informe técnico")
        self.print_line("  status | clear | exit                             : Control y salida del intérprete")
        self.print_line("================================================================================")

    def _cmd_status(self):
        proj = self.project
        plat = proj.platform
        active_rs = proj.get_active_reference_system()

        self.print_line("--------------------------------------------------------------------------------")
        self.print_line(f"Proyecto         : {proj.name}")
        self.print_line(f"Descripción      : {proj.description}")
        self.print_line(f"Archivo en Disco : {str(self.current_project_file) if self.current_project_file else '(Sin guardar)'}")
        if active_rs:
            self.print_line(f"SRT Activo       : [{active_rs.id}] {active_rs.name} (Elipsoide: {active_rs.ellipsoid}, UTM: {active_rs.utm_zone}{active_rs.utm_hemisphere}, N={active_rs.geoid_undulation_N:.4f}m, Dec={active_rs.magnetic_declination_deg:.4f}°)")
        else:
            self.print_line(f"Elipsoide Global : {proj.ellipsoid_name} | Huso UTM: {proj.config.get('utm_zone', 30)}")

        if plat:
            dims = f"L={plat.length_m:.2f}m, W={plat.width_m:.2f}m, H={plat.height_m:.2f}m" if plat.has_dimensions else "Chasis libre"
            poly_v = f" ({len(plat.chassis_polygon)} vértices)" if plat.chassis_polygon else ""
            self.print_line(f"Plataforma Activa: [{plat.id}] {plat.name} ({plat.platform_type}, {dims}{poly_v})")
            self.print_line(f"Sensores en Rig  : {len(plat.sensors)}")
            if plat.pose_e:
                p = plat.pose_e
                r, pitch, y = p.attitude_rpy_deg
                self.print_line(f"Estado de Cálculo: GEORREFERENCIADA ({p.method})")
                self.print_line(f"  PLA Lat/Lon/h  : {p.lat_deg:.8f}°, {p.lon_deg:.8f}°, {p.h_ellip_m:.3f}m")
                self.print_line(f"  PLA UTM (E, N) : {p.utm_easting_m:.3f}m E, {p.utm_northing_m:.3f}m N (Huso {p.utm_zone}{p.utm_hemisphere})")
                self.print_line(f"  Actitud (R,P,Y): {r:+.4f}°, {pitch:+.4f}°, {y:+.4f}°")
            else:
                self.print_line("Estado de Cálculo: PENDIENTE DE RESOLUCIÓN (Use 'solve')")
        else:
            self.print_line("Plataforma Activa: (Ninguna definida)")
        self.print_line("--------------------------------------------------------------------------------")

    def _cmd_project(self, args: list[str]):
        if not args:
            self.print_line("Uso: project [new | open | save | saveas | status]")
            return

        sub = args[0].lower()
        if sub in ("new", "crear"):
            name = args[1] if len(args) > 1 else "Proyecto PyGSN"
            ellips = args[2].upper() if len(args) > 2 else "GRS80"
            utm_z = int(args[3]) if len(args) > 3 and args[3].lstrip("-").isdigit() else 30
            n_geo = float(args[4]) if len(args) > 4 and self._is_float(args[4]) else 50.0166
            decl = float(args[5]) if len(args) > 5 and self._is_float(args[5]) else -0.700

            proj = Project(name=name, ellipsoid_name=ellips)
            srt = ReferenceSystem(
                id="SRT_01",
                name=f"ETRS89 / UTM {abs(utm_z)}N",
                ellipsoid=ellips,
                utm_zone=abs(utm_z),
                utm_hemisphere="S" if utm_z < 0 else "N",
                geoid_undulation_N=n_geo,
                magnetic_declination_deg=decl,
                is_active=True
            )
            proj.add_reference_system(srt, set_active=True)
            plat = Platform(id="PLAT_01", name="Plataforma Principal", platform_type="VEHICLE")
            proj.add_platform(plat, set_active=True)

            self.set_project(proj)
            self.current_project_file = None
            self.print_success(f"Proyecto '{name}' inicializado con SRT [{srt.id}] y plataforma [{plat.id}].")

        elif sub in ("open", "load", "abrir"):
            if len(args) < 2:
                self.print_error("Debe indicar la ruta del archivo .pygsn (ej: project open data/proyecto.pygsn).")
                return
            p = Path(args[1])
            if not p.exists():
                self.print_error(f"El archivo '{p.resolve()}' no existe.")
                return
            try:
                proj = Project.load(p)
                self.set_project(proj)
                self.current_project_file = p.resolve()
                self.print_success(f"Proyecto '{proj.name}' cargado exitosamente desde: {p.name}")
                self._cmd_status()
            except Exception as e:
                self.print_error(f"Fallo al abrir archivo de proyecto: {e}")

        elif sub in ("save", "guardar", "saveas"):
            target_path = None
            if len(args) > 1:
                target_path = Path(args[1])
            elif self.current_project_file:
                target_path = self.current_project_file
            else:
                target_path = Path(f"{re.sub(r'[^a-zA-Z0-9_-]', '_', self.project.name.lower())}.pygsn")

            try:
                self.project.save(target_path)
                self.current_project_file = target_path.resolve()
                self.print_success(f"Proyecto guardado exitosamente en: {target_path.resolve()}")
            except Exception as e:
                self.print_error(f"Fallo al guardar proyecto: {e}")

        elif sub in ("status", "info"):
            self._cmd_status()

        else:
            self.print_error(f"Subcomando de proyecto desconocido: 'project {sub}'")

    def _cmd_srt(self, args: list[str]):
        proj = self.project
        if not args or args[0].lower() in ("list", "ls"):
            if not proj.reference_systems:
                self.print_line("No hay sistemas de referencia registrados en el proyecto.")
                return
            self.print_line(f"Total Sistemas de Referencia (SRT): {len(proj.reference_systems)}")
            for rid, r in proj.reference_systems.items():
                act_mark = " [*ACTIVO]" if rid == proj.active_reference_system_id else ""
                self.print_line(f"  [{rid}] {r.name} (Elipsoide: {r.ellipsoid}, UTM: {r.utm_zone}{r.utm_hemisphere}, N={r.geoid_undulation_N:.4f}m, Dec={r.magnetic_declination_deg:.4f}°){act_mark}")
            return

        sub = args[0].lower()
        if sub in ("add", "create", "new"):
            if len(args) < 2:
                self.print_error("Uso: srt add <id> [nombre] [elipsoide] [utm_zone] [N] [decl]")
                return
            rid = args[1].upper()
            rname = args[2] if len(args) >= 3 else rid
            ellips = args[3].upper() if len(args) >= 4 else "GRS80"
            utm_z = int(args[4]) if len(args) >= 5 and args[4].isdigit() else 30
            n_geo = float(args[5]) if len(args) >= 6 and self._is_float(args[5]) else 50.0166
            decl = float(args[6]) if len(args) >= 7 and self._is_float(args[6]) else -0.700

            rs = ReferenceSystem(
                id=rid, name=rname, ellipsoid=ellips, utm_zone=utm_z,
                geoid_undulation_N=n_geo, magnetic_declination_deg=decl, is_active=True
            )
            proj.add_reference_system(rs, set_active=True)
            if self.on_project_modified:
                self.on_project_modified()
            self.print_success(f"Sistema de Referencia [{rid}] '{rname}' creado y establecido como activo.")

        elif sub in ("select", "use", "active"):
            if len(args) < 2:
                self.print_error("Indique el ID del SRT a activar (ej: srt select SRT_01).")
                return
            rid = args[1].upper()
            if rid not in proj.reference_systems:
                self.print_error(f"El SRT '{rid}' no existe en el proyecto.")
                return
            proj.set_active_reference_system(rid)
            if self.on_project_modified:
                self.on_project_modified()
            self.print_success(f"SRT activo conmutado a '{rid}'.")

    def _cmd_platform(self, args: list[str]):
        proj = self.project
        if not args or args[0].lower() in ("list", "ls"):
            if not proj.platforms:
                self.print_line("No hay plataformas registradas en el proyecto.")
                return
            self.print_line(f"Total plataformas: {len(proj.platforms)}")
            for pid, p in proj.platforms.items():
                active_mark = " [*ACTIVA]" if pid == proj.active_platform_id else ""
                dims_str = f" [L={p.length_m:.2f}m, W={p.width_m:.2f}m, H={p.height_m:.2f}m]" if p.has_dimensions else " [Chasis libre]"
                self.print_line(f"  [{pid}] {p.name} ({p.platform_type}){dims_str}{active_mark}")
            return

        sub = args[0].lower()
        if sub in ("add", "create", "new"):
            if len(args) < 2:
                self.print_error("Uso: platform add <id> [nombre] [tipo] [fija]")
                return
            pid = args[1].upper()
            pname = args[2] if len(args) >= 3 else pid
            ptype = args[3].upper() if len(args) >= 4 else "VEHICLE"
            is_fixed = args[4].lower() in ("true", "1", "fixed", "fija", "si") if len(args) >= 5 else False

            if pid in proj.platforms:
                self.print_warning(f"La plataforma '{pid}' ya existe. Activándola.")
            else:
                plat = Platform(id=pid, name=pname, platform_type=ptype, is_fixed=is_fixed)
                proj.add_platform(plat)
                self.print_success(f"Plataforma creada: [{pid}] {pname} ({ptype})")

            proj.set_active_platform(pid)
            if self.on_platform_created:
                self.on_platform_created(pid)
            if self.on_project_modified:
                self.on_project_modified()
            self.print_success(f"Plataforma '{pid}' activada en el workspace.")

        elif sub in ("select", "use", "open"):
            if len(args) < 2:
                self.print_error("Indique el ID de la plataforma (ej: platform select PLAT_01).")
                return
            pid = args[1].upper()
            if pid not in proj.platforms:
                self.print_error(f"La plataforma '{pid}' no existe en el proyecto.")
                return
            proj.set_active_platform(pid)
            if self.on_platform_created:
                self.on_platform_created(pid)
            if self.on_project_modified:
                self.on_project_modified()
            self.print_success(f"Plataforma activa conmutada a '{pid}'.")

    def _cmd_chassis(self, full_cmd: str, args: list[str]):
        plat = self.project.platform
        if not plat:
            self.print_error("No hay plataforma activa. Cree o active una con 'platform add <id>'.")
            return

        if not args:
            if not plat.has_dimensions:
                self.print_line(f"Plataforma '{plat.name}': Chasis Libre (sin dimensiones ni caja envolvente).")
                self.print_line("Para definir chasis use:")
                self.print_line("  chassis box <Largo> <Ancho> <Alto>")
                self.print_line("  chassis poly S (x1,y1) (x2,y2) (x3,y3) (x4,y4)")
            else:
                self.print_line(f"Chasis activo en '{plat.name}':")
                self.print_line(f"  Dimensiones Envolventes : Largo={plat.length_m:.3f}m, Ancho={plat.width_m:.3f}m, Alto={plat.height_m:.3f}m")
                if plat.chassis_polygon:
                    pts_str = " -> ".join([f"[{p[0]:+.2f}, {p[1]:+.2f}]" for p in plat.chassis_polygon])
                    self.print_line(f"  Polígono 2D Planta (S)  : {len(plat.chassis_polygon)} vértices: {pts_str}")
                else:
                    self.print_line("  Tipo                    : Caja envolvente rectangular centrada en [0, 0, 0]")
            return

        sub = args[0].lower()
        if sub in ("clear", "reset", "free", "none"):
            plat.has_dimensions = False
            plat.length_m = 0.0
            plat.width_m = 0.0
            plat.height_m = 0.0
            plat.chassis_polygon = None
            if self.on_chassis_modified:
                self.on_chassis_modified()
            self.print_success(f"Chasis eliminado en '{plat.name}'. Plataforma en modo libre.")

        elif sub in ("box", "dims", "caja") or (len(args) >= 3 and self._is_float(args[0]) and self._is_float(args[1]) and self._is_float(args[2])):
            num_args = args[1:] if sub in ("box", "dims", "caja") else args
            if len(num_args) < 3:
                self.print_error("Debe indicar 3 dimensiones numéricas: Largo Ancho Alto (ej: chassis box 1.25 1.0 0.5).")
                return
            try:
                l, w, h = abs(float(num_args[0])), abs(float(num_args[1])), abs(float(num_args[2]))
                plat.length_m = round(l, 4)
                plat.width_m = round(w, 4)
                plat.height_m = round(h, 4)
                plat.has_dimensions = True
                plat.chassis_polygon = None
                if self.on_chassis_modified:
                    self.on_chassis_modified()
                self.print_success(f"Chasis definido para '{plat.name}': L={l:.3f}m, W={w:.3f}m, H={h:.3f}m.")
            except ValueError:
                self.print_error("Las dimensiones deben ser numéricas.")

        elif sub in ("poly", "poligono", "polygon"):
            view_code = "S"
            if len(args) >= 2 and args[1].upper() in ("S", "F", "L"):
                view_code = args[1].upper()

            matches = re.findall(
                r'\(?\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)(?:\s*,\s*([+-]?\d+(?:\.\d+)?))?\s*\)?',
                full_cmd
            )
            if len(matches) < 3:
                self.print_error("Un contorno poligonal requiere al menos 3 vértices (ej: chassis poly S (-0.5,-0.5) (-0.5,0.5) (0.5,0.5) (0.5,-0.5)).")
                return

            pts_2d = [(float(m[0]), float(m[1])) for m in matches]
            u_vals = [p[0] for p in pts_2d]
            v_vals = [p[1] for p in pts_2d]
            extent_u = max(0.05, max(u_vals) - min(u_vals))
            extent_v = max(0.05, max(v_vals) - min(v_vals))

            prev_h = plat.height_m if plat.has_dimensions and plat.height_m > 0 else 0.50
            plat.length_m = round(extent_u, 4)
            plat.width_m = round(extent_v, 4)
            plat.height_m = round(prev_h, 4)
            plat.chassis_polygon = [[p[0], p[1]] for p in pts_2d]
            plat.has_dimensions = True

            if self.on_chassis_modified:
                self.on_chassis_modified()
            self.print_success(f"Polígono de chasis definido ({len(pts_2d)} vértices) en vista {view_code}: L={plat.length_m:.3f}m, W={plat.width_m:.3f}m, H={plat.height_m:.3f}m.")

        elif sub in ("move", "mover", "trasladar"):
            if len(args) < 3:
                self.print_error("Indique al menos dx y dy (ej: chassis move 0.5 -0.2 [dz]).")
                return
            try:
                dx = float(args[1])
                dy = float(args[2])
                dz = float(args[3]) if len(args) > 3 else 0.0
                plat.translate(dx, dy, dz)
                if self.on_chassis_modified:
                    self.on_chassis_modified()
                c = plat.chassis_center_b
                self.print_success(f"Chasis desplazado: dx={dx:+.3f}m, dy={dy:+.3f}m, dz={dz:+.3f}m. Nuevo centroide: [{c[0]:.3f}, {c[1]:.3f}, {c[2]:.3f}]m.")
            except ValueError:
                self.print_error("Los valores de desplazamiento deben ser numéricos.")

        elif sub in ("center", "centrar", "origin"):
            dx, dy, dz = plat.center_to_origin()
            if self.on_chassis_modified:
                self.on_chassis_modified()
            self.print_success(f"Chasis centrado en PLA [0,0,0] (traslación: [{dx:+.3f}, {dy:+.3f}, {dz:+.3f}]m).")

        elif sub in ("rotate", "rotar"):
            if len(args) < 2:
                self.print_error("Indique el ángulo en grados (ej: chassis rotate 45 [S|F|L]).")
                return
            try:
                ang = float(args[1])
                plane = args[2].upper() if len(args) > 2 else "S"
                if plane not in ("S", "F", "L"):
                    plane = "S"
                plat.rotate_plane(ang, plane)
                if self.on_chassis_modified:
                    self.on_chassis_modified()
                self.print_success(f"Chasis rotado {ang:+.2f}° en plano {plane}.")
            except ValueError:
                self.print_error("El ángulo debe ser numérico.")

        elif sub in ("scale", "escalar"):
            if len(args) < 3:
                self.print_error("Indique factores fx y fy (ej: chassis scale 1.2 1.2 [1.0]).")
                return
            try:
                fx = float(args[1])
                fy = float(args[2])
                fz = float(args[3]) if len(args) > 3 else 1.0
                plat.scale_dimensions(fx, fy, fz)
                if self.on_chassis_modified:
                    self.on_chassis_modified()
                self.print_success(f"Chasis escalado ({fx:.2f}x, {fy:.2f}x, {fz:.2f}x).")
            except ValueError:
                self.print_error("Factores de escala no válidos.")

        else:
            self.print_error(f"Subcomando de chasis desconocido: 'chassis {sub}'")

    def _cmd_sensor(self, full_cmd: str, args: list[str]):
        plat = self.project.platform
        if not plat:
            self.print_error("No hay plataforma activa. Active una con 'platform select <id>'.")
            return

        if not args or args[0].lower() in ("list", "ls"):
            if not plat.sensors:
                self.print_line(f"La plataforma '{plat.name}' no tiene sensores montados.")
                return
            self.print_line(f"Sensores en '{plat.name}' ({len(plat.sensors)}):")
            for c, s in plat.sensors.items():
                arm = s.lever_arm_b
                b_deg = s.boresight_deg
                obs_info = ""
                if s.observation:
                    if s.observation.has_geodetic:
                        g = s.observation.geodetic_deg
                        obs_info = f" | Obs Geod: ({g[0]:.6f}°, {g[1]:.6f}°, {g[2]:.2f}m)"
                    elif s.observation.has_attitude:
                        a = s.observation.attitude_rpy_deg
                        obs_info = f" | Obs Att: ({a[0]:.2f}°, {a[1]:.2f}°, {a[2]:.2f}°)"
                self.print_line(f"  {c:<6s} [{s.sensor_type.value:<6s}] arm=[{arm[0]:+.3f}, {arm[1]:+.3f}, {arm[2]:+.3f}]m  boresight=({b_deg[0]:.2f}, {b_deg[1]:.2f}, {b_deg[2]:.2f})°  {s.name}{obs_info}")
            return

        sub = args[0].lower()
        if sub in ("add", "crear", "new"):
            if len(args) < 3:
                self.print_error("Uso: sensor add <code> <tipo> [x] [y] [z] [roll] [pitch] [yaw] [nombre]")
                return
            code = args[1].upper()
            stype_str = args[2].upper()
            try:
                stype = SensorType(stype_str)
            except ValueError:
                stype = SensorType.OTHER
                for t in SensorType:
                    if stype_str in t.value:
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
                code=code, name=name, sensor_type=stype,
                lever_arm_b=np.array([x, y, z], dtype=np.float64),
                boresight_deg=(r, p, yaw)
            )
            plat.add_sensor(sens)
            if self.on_sensor_modified:
                self.on_sensor_modified()
            self.print_success(f"Sensor {code} [{stype.value}] añadido a '{plat.name}'.")

        elif sub in ("place", "set", "ubicar"):
            if len(args) < 4:
                self.print_error("Uso: sensor place <code> <x> <y> [z]")
                return
            code = args[1].upper()
            if code not in plat.sensors:
                self.print_error(f"Sensor '{code}' no encontrado.")
                return
            try:
                x = float(args[2])
                y = float(args[3])
                z = float(args[4]) if len(args) > 4 else float(plat.sensors[code].lever_arm_b[2])
                plat.sensors[code].lever_arm_b = np.array([x, y, z], dtype=np.float64)
                if self.on_sensor_modified:
                    self.on_sensor_modified()
                self.print_success(f"Sensor {code} posicionado en [{x:.3f}, {y:.3f}, {z:.3f}]m.")
            except ValueError:
                self.print_error("Coordenadas no numéricas.")

        elif sub in ("move", "mover"):
            if len(args) < 4:
                self.print_error("Uso: sensor move <code> <dx> <dy> [dz]")
                return
            code = args[1].upper()
            if code not in plat.sensors:
                self.print_error(f"Sensor '{code}' no encontrado.")
                return
            try:
                dx = float(args[2])
                dy = float(args[3])
                dz = float(args[4]) if len(args) > 4 else 0.0
                plat.sensors[code].lever_arm_b += np.array([dx, dy, dz], dtype=np.float64)
                arm = plat.sensors[code].lever_arm_b
                if self.on_sensor_modified:
                    self.on_sensor_modified()
                self.print_success(f"Sensor {code} desplazado a [{arm[0]:.3f}, {arm[1]:.3f}, {arm[2]:.3f}]m.")
            except ValueError:
                self.print_error("Desplazamientos no numéricos.")

        elif sub in ("rotate", "rotar"):
            if len(args) < 5:
                self.print_error("Uso: sensor rotate <code> <droll> <dpitch> <dyaw>")
                return
            code = args[1].upper()
            if code not in plat.sensors:
                self.print_error(f"Sensor '{code}' no encontrado.")
                return
            try:
                dr, dp, dy = float(args[2]), float(args[3]), float(args[4])
                r, p, y = plat.sensors[code].boresight_deg
                plat.sensors[code].boresight_deg = (round(r + dr, 6), round(p + dp, 6), round(y + dy, 6))
                if self.on_sensor_modified:
                    self.on_sensor_modified()
                nb = plat.sensors[code].boresight_deg
                self.print_success(f"Boresight de {code} actualizado a ({nb[0]:.4f}°, {nb[1]:.4f}°, {nb[2]:.4f}°).")
            except ValueError:
                self.print_error("Ángulos no numéricos.")

        elif sub in ("remove", "rm", "del", "delete"):
            if len(args) < 2:
                self.print_error("Uso: sensor remove <code>")
                return
            code = args[1].upper()
            if plat.remove_sensor(code):
                if self.on_sensor_modified:
                    self.on_sensor_modified()
                self.print_success(f"Sensor {code} eliminado de la plataforma.")
            else:
                self.print_error(f"Sensor '{code}' no encontrado.")

        else:
            self.print_error(f"Subcomando de sensor desconocido: 'sensor {sub}'")

    def _cmd_import(self, args: list[str]):
        if not args:
            self.print_error("Uso: import table <ruta_archivo> [o import txt <ruta_archivo>]")
            return

        sub = args[0].lower()
        if sub in ("table", "tabla", "excel", "csv"):
            if len(args) < 2:
                self.print_error("Debe indicar la ruta del archivo (.xlsx, .csv, .txt).")
                return
            fpath = Path(args[1])
            if not fpath.exists():
                self.print_error(f"El archivo '{fpath.resolve()}' no existe.")
                return

            try:
                imported = self.project.import_sensors_from_table(fpath)
                if self.on_sensor_modified:
                    self.on_sensor_modified()
                if self.on_project_modified:
                    self.on_project_modified()
                self.print_success(f"Se han importado {len(imported)} sensores desde: {fpath.name}")
                self._cmd_sensor("", ["list"])
            except Exception as e:
                self.print_error(f"Error durante la importación tabular: {e}")

        elif sub in ("txt", "calibracion"):
            if len(args) < 2:
                self.print_error("Debe indicar la ruta del archivo de texto.")
                return
            fpath = Path(args[1])
            if not fpath.exists():
                self.print_error(f"El archivo '{fpath.resolve()}' no existe.")
                return
            try:
                self.project.import_calibration_txt(fpath)
                if self.on_sensor_modified:
                    self.on_sensor_modified()
                self.print_success(f"Calibración importada desde: {fpath.name}")
            except Exception as e:
                self.print_error(f"Error al importar calibración TXT: {e}")
        else:
            self.print_error(f"Tipo de importación desconocido: '{sub}'. Use 'import table <archivo>'.")

    def _cmd_solve(self, args: list[str]):
        method = args[0].upper() if args else "SVD+INS"
        self.print_line(f"> Ejecutando cálculo de georreferenciación multipunto ({method})...")

        try:
            sol = self.project.solve_georeferencing(method=method, apply_to_platform=True)
            self.last_solution = sol

            rg, pg, yg = sol.attitude_gnss_deg
            ri, pi, yi = sol.attitude_ins_total_deg
            lat_d = float(np.degrees(sol.pla_origin_lat_rad))
            lon_d = float(np.degrees(sol.pla_origin_lon_rad))

            self.print_success("Georreferenciación calculada exitosamente:")
            self.print_line("--------------------------------------------------------------------------------")
            self.print_line(f"1. Actitud GNSS (Cb2n): Roll={rg:+.6f}°, Pitch={pg:+.6f}°, Yaw={yg:+.6f}°")
            self.print_line(f"2. Actitud INS Total  : Roll={ri:+.6f}°, Pitch={pi:+.6f}°, Yaw={yi:+.6f}°")
            self.print_line(f"3. Origen PLA (e-frame): Lat={lat_d:.8f}°, Lon={lon_d:.8f}°, h={sol.pla_origin_h_ellip:.4f}m")
            if self.project.platform and self.project.platform.pose_e:
                p = self.project.platform.pose_e
                self.print_line(f"   UTM Proyectada     : {p.utm_easting_m:.3f}m E, {p.utm_northing_m:.3f}m N (Huso {p.utm_zone}{p.utm_hemisphere}) | H={p.h_ortho_m:.3f}m")
            self.print_line(f"4. Sensores Propagados: {len(sol.results_gnss)} en solución GNSS, {len(sol.results_ins)} en INS.")
            self.print_line("--------------------------------------------------------------------------------")

            if self.on_solution_computed:
                self.on_solution_computed(sol)
            if self.on_project_modified:
                self.on_project_modified()

        except Exception as e:
            self.print_error(f"Error durante la resolución de georreferenciación: {e}")

    def _cmd_residuals(self):
        sol = self.last_solution or getattr(self.project, "_last_solution", None)
        if sol is None:
            self.print_error("No hay una solución calculada en la sesión. Ejecute primero 'solve'.")
            return

        self.print_line("================================================================================")
        self.print_line("RESIDUALES DE CONSISTENCIA Y DISCREPANCIAS (GNSS vs INS)")
        self.print_line("================================================================================")
        self.print_line(f"{'Sensor':<8s} {'dE (m)':>12s} {'dN (m)':>12s} {'dH (m)':>12s} {'Norma 3D (m)':>15s}")
        self.print_line("-" * 65)

        for code, (de, dn, dh) in sol.diff_gnss_ins_utm.items():
            norm_3d = math.sqrt(de**2 + dn**2 + dh**2)
            self.print_line(f"{code:<8s} {de:+12.4f} {dn:+12.4f} {dh:+12.4f} {norm_3d:15.4f}")
        self.print_line("================================================================================")

    def _cmd_diag(self):
        sol = self.last_solution or getattr(self.project, "_last_solution", None)
        if sol is None:
            self.print_error("No hay una solución calculada. Ejecute primero 'solve'.")
            return

        cb2n = sol.Cb2n_gnss
        det = float(np.linalg.det(cb2n))
        ortho_err = float(np.linalg.norm(cb2n @ cb2n.T - np.eye(3)))
        cond_num = float(np.linalg.cond(cb2n))

        self.print_line("================================================================================")
        self.print_line("AUDITORÍA ESPECTRAL Y DIAGNÓSTICO MATRICIAL DCM (Cb2n)")
        self.print_line("================================================================================")
        self.print_line(f"Determinante det(Cb2n)        : {det:.10f}  (Ideal: 1.0000000000)")
        self.print_line(f"Error de Ortonormalidad ||I-C*C^T||: {ortho_err:.2e}  (Ideal: < 1e-12)")
        self.print_line(f"Número de Condición Espectral  : {cond_num:.6f}  (Ideal: 1.000000)")
        self.print_line("\nMatriz DCM Cb2n (GNSS):")
        for row in cb2n:
            self.print_line(f"  [{row[0]:+12.8f}, {row[1]:+12.8f}, {row[2]:+12.8f}]")
        self.print_line("================================================================================")

    def _cmd_report(self, args: list[str]):
        out_file = args[0] if args else None
        try:
            rep = self.project.export_report(output_path=out_file)
            if out_file:
                self.print_success(f"Informe técnico guardado exitosamente en: {Path(out_file).resolve()}")
            else:
                self.print_line(rep)
        except Exception as e:
            self.print_error(f"Error al generar informe técnico: {e}")

    @staticmethod
    def _is_float(s: Any) -> bool:
        try:
            float(str(s).replace(",", "."))
            return True
        except ValueError:
            return False

"""
PyGSN - Cartographic Map Workspace Module (e-frame / UTM 2D)
=============================================================
Lienzo cartográfico vectorial 2D interactivo para visualización territorial
en marco terrestre (e-frame) proyectado en ETRS89 / UTM Huso 30N (EPSG:25830):
- Descargador asíncrono y caché de teselas OpenStreetMap (OSMTileManager).
- Modo offline automático con cuadrícula kilométrica vectorial UTM.
- Representación de plataformas georreferenciadas con silueta de chasis orientada por rumbo (Yaw).
- Representación de sensores con simbología de tipo (GNSS, INS, Cámara).
- Terna local n-frame conmutable entre convención NED (Inercial) y ENU (GeoTop).
- Correspondencia estricta de ejes RGB:
    - Eje 1 (Rojo): Este (E) en Cartografía / Norte (N) en NED / Proa (Xb)
    - Eje 2 (Verde): Norte (N) en Cartografía / Este (E) en NED / Estribor (Yb)
    - Eje 3 (Azul): Cota (Up/Down)
- Rosa de los vientos con Norte de cuadrícula y Norte geográfico (convergencia de meridianos gamma).
- Barra de coordenadas dinámicas bajo el cursor (E, N, Lat, Lon, Escala).
"""

from typing import Optional, Dict, Any, Tuple, List, Callable
from pathlib import Path
import math
import urllib.request
import urllib.error
import concurrent.futures
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QToolButton,
    QLabel, QComboBox, QMenu, QSizePolicy
)
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QSize, Signal, QObject
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPixmap, QImage,
    QPolygonF, QCursor, QTransform, QGuiApplication, QPainterPath
)

from core.models import Platform, Sensor, ReferenceSystem
from core.project import Project
from core.geodesy import GRS80, utm_projection, utm_inverse, rad_to_dms


class OSMTileManager(QObject):
    """
    Gestor asíncrono de teselas de OpenStreetMap con almacenamiento en caché local.
    Convierte coordenadas UTM -> Geodésicas -> Índices de tesela Web Mercator (z, x, y).
    No bloquea jamás el hilo principal de la interfaz gráfica de Qt.
    """
    tile_loaded = Signal(int, int, int)  # z, x, y

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.cache_dir = Path.home() / ".pygsn" / "cache" / "osm_tiles"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._mem_cache: Dict[Tuple[int, int, int], QPixmap] = {}
        self._pending_requests: set[Tuple[int, int, int]] = set()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        self.is_offline = False

    def get_tile(self, z: int, x: int, y: int) -> Optional[QPixmap]:
        """
        Obtiene la tesela para el nivel de zoom z y coordenadas x, y.
        Retorna QPixmap si está en memoria o en disco; si no, lanza la descarga en segundo plano y retorna None.
        """
        key = (z, x, y)
        if key in self._mem_cache:
            return self._mem_cache[key]

        tile_file = self.cache_dir / str(z) / str(x) / f"{y}.png"
        if tile_file.exists():
            try:
                pix = QPixmap(str(tile_file))
                if not pix.isNull():
                    self._mem_cache[key] = pix
                    return pix
            except Exception:
                pass

        # Solicitar descarga asíncrona si no está pendiente y no estamos en fallo permanente
        if key not in self._pending_requests and not self.is_offline:
            self._pending_requests.add(key)
            self._executor.submit(self._download_tile, z, x, y, tile_file)

        return None

    def _download_tile(self, z: int, x: int, y: int, dest_path: Path):
        url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        headers = {
            "User-Agent": "PyGSN-NavigationSuite/1.0 (CartoMap; https://github.com/andreesbotello/PyGSN)"
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = resp.read()
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "wb") as f:
                    f.write(data)
                # Notificar al hilo principal
                self.tile_loaded.emit(z, x, y)
        except Exception:
            # En caso de error de conexión (offline), ignorar silenciosamente
            pass
        finally:
            self._pending_requests.discard((z, x, y))


class CartoMapCanvas(QWidget):
    """
    Lienzo cartográfico vectorial interactivo en proyección UTM (EPSG:25830).
    Soporta pan, zoom, teselas OSM, cuadrícula kilométrica, silueta de plataforma orientada,
    marcadores de sensores y terna local de navegación n-frame.
    """
    coordinates_changed = Signal(float, float, float, float)  # Easting, Northing, Lat_deg, Lon_deg
    basemap_visibility_changed = Signal(str, bool)             # ref_system_id, visible

    def __init__(
        self,
        get_project: Callable[[], Project],
        ref_system_id: str,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.get_project = get_project
        self.ref_system_id = ref_system_id

        # Centro de la vista cartográfica en coordenadas UTM [m]
        # Coordenadas iniciales por defecto centradas en Campus de Vera, UPV (Valencia)
        self.center_e = 725400.0
        self.center_n = 4372800.0

        # Escala: píxeles por metro en pantalla
        # 10.0 px/m = 10 cm/px; 1.0 px/m = 1 m/px; 0.1 px/m = 10 m/px
        self.px_per_m = 12.0

        # Estados de capas visibles
        proj = self.get_project()
        rs = proj.reference_systems.get(self.ref_system_id)
        self.show_osm = getattr(rs, "show_basemap", True) if rs else True
        self.show_chassis = True
        self.show_sensors = True
        self.show_n_frame = True
        self.show_grid = True
        self.show_compass = True
        self.show_scalebar = True
        self.hidden_layers: set[str] = set()
        if not self.show_osm:
            self.hidden_layers.add("basemap")
        self.n_frame_convention = "NED"  # "NED" o "ENU"

        # Interacción
        self._dragging = False
        self._drag_start_pos = QPoint()
        self._drag_start_center_e = 0.0
        self._drag_start_center_n = 0.0

        # Gestor de teselas
        self.tile_mgr = OSMTileManager(self)
        self.tile_mgr.tile_loaded.connect(self._on_tile_downloaded)

        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

        # Centrar si hay alguna plataforma georreferenciada en este SRT
        self.zoom_to_platforms()

    def _on_tile_downloaded(self, z: int, x: int, y: int):
        if self.show_osm and "basemap" not in self.hidden_layers:
            self.update()

    def set_ref_system_id(self, rs_id: str):
        self.ref_system_id = rs_id
        self.zoom_to_platforms()
        self.update()

    def screen_to_utm(self, sx: float, sy: float) -> Tuple[float, float]:
        """Convierte coordenadas de pantalla (píxeles) a UTM Este y Norte en metros."""
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        easting = self.center_e + (sx - cx) / self.px_per_m
        northing = self.center_n - (sy - cy) / self.px_per_m
        return easting, northing

    def utm_to_screen(self, easting: float, northing: float) -> Tuple[float, float]:
        """Convierte coordenadas UTM Este y Norte en metros a pantalla (píxeles)."""
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        sx = cx + (easting - self.center_e) * self.px_per_m
        sy = cy - (northing - self.center_n) * self.px_per_m
        return sx, sy

    def zoom_to_platforms(self):
        """Ajusta el centro y la escala para encuadrar la plataforma o sensores georreferenciados."""
        proj = self.get_project()
        all_e = []
        all_n = []

        for plat in proj.platforms.values():
            if plat.pose_e and plat.pose_e.ref_system_id == self.ref_system_id:
                all_e.append(plat.pose_e.utm_easting_m)
                all_n.append(plat.pose_e.utm_northing_m)
            for s in plat.sensors.values():
                if s.georef and s.georef.ref_system_id == self.ref_system_id:
                    all_e.append(s.georef.utm_easting_m)
                    all_n.append(s.georef.utm_northing_m)

        if all_e and all_n:
            min_e, max_e = min(all_e), max(all_e)
            min_n, max_n = min(all_n), max(all_n)
            self.center_e = (min_e + max_e) / 2.0
            self.center_n = (min_n + max_n) / 2.0
            span_e = max(abs(max_e - min_e), 15.0)
            span_n = max(abs(max_n - min_n), 15.0)

            w = max(self.width() - 80, 200)
            h = max(self.height() - 80, 200)
            self.px_per_m = min(w / span_e, h / span_n, 40.0)
            self.update()

    def zoom_to_fit_extent(self):
        """Encuadre general que abarca todas las plataformas y sensores."""
        self.zoom_to_platforms()

    def zoom_to_bbox(self, min_e: float, max_e: float, min_n: float, max_n: float, margin: float = 0.35):
        """Encuadra la vista en la bounding box métrica [min_e, max_e, min_n, max_n] con margen de seguridad."""
        self.center_e = (min_e + max_e) / 2.0
        self.center_n = (min_n + max_n) / 2.0
        span_e = max(abs(max_e - min_e), 2.0)
        span_n = max(abs(max_n - min_n), 2.0)

        w = max(self.width() - 80, 200)
        h = max(self.height() - 80, 200)
        scale_e = (w / span_e) * (1.0 - margin)
        scale_n = (h / span_n) * (1.0 - margin)
        self.px_per_m = float(np.clip(min(scale_e, scale_n), 0.05, 500.0))
        self.update()

    def contextMenuEvent(self, event):
        """Menú contextual emergente de clic derecho directamente en el lienzo del mapa."""
        menu = QMenu(self)

        act_compass = menu.addAction("Ver rosa de los vientos")
        act_compass.setCheckable(True)
        act_compass.setChecked(self.show_compass)
        act_compass.toggled.connect(self._toggle_compass)

        act_grid = menu.addAction("Ver cuadrícula métrica (UTM)")
        act_grid.setCheckable(True)
        act_grid.setChecked(self.show_grid and ("grid" not in self.hidden_layers))
        act_grid.toggled.connect(self._toggle_grid)

        act_osm = menu.addAction("Ver mapa base (OpenStreetMap)")
        act_osm.setCheckable(True)
        act_osm.setChecked(self.show_osm and ("basemap" not in self.hidden_layers))
        act_osm.toggled.connect(self._toggle_osm)

        act_scale = menu.addAction("Ver escala gráfica")
        act_scale.setCheckable(True)
        act_scale.setChecked(self.show_scalebar)
        act_scale.toggled.connect(self._toggle_scalebar)

        menu.addSeparator()

        act_center = menu.addAction("Centrar vista en plataforma")
        act_center.triggered.connect(self.zoom_to_platforms)

        act_copy = menu.addAction("Copiar coordenadas UTM al portapapeles")
        cur_pos = event.pos()
        e, n = self.screen_to_utm(cur_pos.x(), cur_pos.y())
        act_copy.triggered.connect(lambda: self._copy_coordinates(e, n))

        menu.exec(event.globalPos())

    def _toggle_compass(self, checked: bool):
        self.show_compass = checked
        self.update()

    def _toggle_grid(self, checked: bool):
        self.show_grid = checked
        if checked:
            self.hidden_layers.discard("grid")
        else:
            self.hidden_layers.add("grid")
        self.update()

    def _toggle_osm(self, checked: bool):
        self.show_osm = checked
        if checked:
            self.hidden_layers.discard("basemap")
        else:
            self.hidden_layers.add("basemap")
        self.basemap_visibility_changed.emit(self.ref_system_id, checked)
        self.update()

    def _toggle_scalebar(self, checked: bool):
        self.show_scalebar = checked
        self.update()

    def _copy_coordinates(self, easting: float, northing: float):
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(f"E: {easting:,.3f} m, N: {northing:,.3f} m")

    # =========================================================================
    # EVENTOS DE RATÓN Y TECLADO
    # =========================================================================

    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._dragging = True
            self._drag_start_pos = event.pos()
            self._drag_start_center_e = self.center_e
            self._drag_start_center_n = self.center_n
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        cur_pos = event.pos()
        e, n = self.screen_to_utm(cur_pos.x(), cur_pos.y())

        # Calcular geodésicas instantáneas para la barra de estado
        try:
            lat_rad, lon_rad = utm_inverse(e, n, zone=30, hemisphere="N", ell=GRS80)
            lat_deg = math.degrees(lat_rad)
            lon_deg = math.degrees(lon_rad)
            self.coordinates_changed.emit(e, n, lat_deg, lon_deg)
        except Exception:
            pass

        if self._dragging:
            dx = cur_pos.x() - self._drag_start_pos.x()
            dy = cur_pos.y() - self._drag_start_pos.y()
            self.center_e = self._drag_start_center_e - dx / self.px_per_m
            self.center_n = self._drag_start_center_n + dy / self.px_per_m
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._dragging = False
            self.setCursor(Qt.CrossCursor)

    def wheelEvent(self, event):
        mouse_pos = event.position()
        old_e, old_n = self.screen_to_utm(mouse_pos.x(), mouse_pos.y())

        factor = 1.25 if event.angleDelta().y() > 0 else 0.80
        new_px_per_m = np.clip(self.px_per_m * factor, 0.005, 500.0)
        self.px_per_m = float(new_px_per_m)

        # Mantener el punto bajo el cursor exactamente en la misma coordenada
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        self.center_e = old_e - (mouse_pos.x() - cx) / self.px_per_m
        self.center_n = old_n + (mouse_pos.y() - cy) / self.px_per_m

        self.update()

    # =========================================================================
    # RENDERIZADO GRÁFICO (PAINT EVENT)
    # =========================================================================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        w = self.width()
        h = self.height()

        # Fondo técnico claro
        painter.fillRect(0, 0, w, h, QColor("#f1f5f9"))

        # 1. Capa OpenStreetMap
        if self.show_osm:
            try:
                self._draw_osm_tiles(painter)
            except Exception:
                pass

        # 2. Capa Cuadrícula UTM
        if self.show_grid:
            try:
                self._draw_utm_grid(painter)
            except Exception:
                pass

        # 3. Plataformas georreferenciadas
        if self.show_chassis:
            try:
                self._draw_platforms(painter)
            except Exception:
                pass

        # 4. Sensores georreferenciados
        if self.show_sensors:
            try:
                self._draw_sensors(painter)
            except Exception:
                pass

        # 5. Terna local de navegación n-frame
        if self.show_n_frame:
            try:
                self._draw_n_frame_triad(painter)
            except Exception:
                pass

        # 6. Elementos cartográficos fijos (Rosa de los Vientos y Escala)
        try:
            self._draw_compass_rose(painter)
        except Exception:
            pass
        try:
            self._draw_scale_bar(painter)
        except Exception:
            pass

    def _draw_osm_tiles(self, painter: QPainter):
        """Calcula el rango de teselas OSM visibles, las proyecta con QTransform.quadToQuad continuo y las dibuja."""
        if not self.show_osm or "basemap" in self.hidden_layers:
            return

        w = self.width()
        h = self.height()

        # Calcular las 4 esquinas de la ventana de visualización en UTM
        corners_screen = [(0, 0), (w, 0), (w, h), (0, h)]
        lats = []
        lons = []
        for sx, sy in corners_screen:
            e, n = self.screen_to_utm(sx, sy)
            try:
                lat_rad, lon_rad = utm_inverse(e, n, zone=30, hemisphere="N", ell=GRS80)
                lats.append(math.degrees(lat_rad))
                lons.append(math.degrees(lon_rad))
            except Exception:
                return

        mid_lat = sum(lats) / 4.0
        cos_lat = max(math.cos(math.radians(mid_lat)), 0.01)
        target_z = math.log2(max(156543.03 * cos_lat * self.px_per_m, 1.0))
        z = int(np.clip(round(target_z), 0, 19))

        def deg2tile(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[float, float]:
            lat_rad = math.radians(np.clip(lat_deg, -85.0511, 85.0511))
            n_tiles = 2.0 ** zoom
            xtile = (lon_deg + 180.0) / 360.0 * n_tiles
            ytile = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n_tiles
            return xtile, ytile

        def tile2deg(xtile: float, ytile: float, zoom: int) -> Tuple[float, float]:
            n_tiles = 2.0 ** zoom
            lon_deg = xtile / n_tiles * 360.0 - 180.0
            lat_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * ytile / n_tiles)))
            lat_deg = math.degrees(lat_rad)
            return lat_deg, lon_deg

        # Determinar rango de teselas a partir de las esquinas
        xtiles = []
        ytiles = []
        for lat_d, lon_d in zip(lats, lons):
            xt, yt = deg2tile(lat_d, lon_d, z)
            xtiles.append(xt)
            ytiles.append(yt)

        # Margen de 1 tesela para asegurar cobertura completa en las esquinas rotadas
        x_start = max(int(math.floor(min(xtiles))) - 1, 0)
        x_end = min(int(math.ceil(max(xtiles))) + 1, 2**z)
        y_start = max(int(math.floor(min(ytiles))) - 1, 0)
        y_end = min(int(math.ceil(max(ytiles))) + 1, 2**z)

        if (x_end - x_start) * (y_end - y_start) > 64:
            return

        painter.save()
        painter.setOpacity(0.85)
        base_transform = painter.transform()
        src_quad = QPolygonF([QPointF(0, 0), QPointF(256, 0), QPointF(256, 256), QPointF(0, 256)])

        for tx in range(x_start, x_end):
            for ty in range(y_start, y_end):
                pix = self.tile_mgr.get_tile(z, tx, ty)
                if not pix or pix.isNull():
                    continue

                # Coordenadas geodésicas de las 4 esquinas de la tesela
                lat_top, lon_left = tile2deg(tx, ty, z)
                lat_top_r, lon_right = tile2deg(tx + 1, ty, z)
                lat_bot_r, lon_right_b = tile2deg(tx + 1, ty + 1, z)
                lat_bot, lon_left_b = tile2deg(tx, ty + 1, z)

                try:
                    e_tl, n_tl, _ = utm_projection(math.radians(lat_top), math.radians(lon_left), zone=30, hemisphere="N")
                    e_tr, n_tr, _ = utm_projection(math.radians(lat_top_r), math.radians(lon_right), zone=30, hemisphere="N")
                    e_br, n_br, _ = utm_projection(math.radians(lat_bot_r), math.radians(lon_right_b), zone=30, hemisphere="N")
                    e_bl, n_bl, _ = utm_projection(math.radians(lat_bot), math.radians(lon_left_b), zone=30, hemisphere="N")

                    sx_tl, sy_tl = self.utm_to_screen(e_tl, n_tl)
                    sx_tr, sy_tr = self.utm_to_screen(e_tr, n_tr)
                    sx_br, sy_br = self.utm_to_screen(e_br, n_br)
                    sx_bl, sy_bl = self.utm_to_screen(e_bl, n_bl)

                    dst_quad = QPolygonF([
                        QPointF(sx_tl, sy_tl),
                        QPointF(sx_tr, sy_tr),
                        QPointF(sx_br, sy_br),
                        QPointF(sx_bl, sy_bl)
                    ])

                    trans = QTransform()
                    if QTransform.quadToQuad(src_quad, dst_quad, trans):
                        painter.setTransform(trans * base_transform)
                        painter.drawPixmap(0, 0, pix)
                except Exception:
                    continue

        painter.setTransform(base_transform)
        painter.restore()

    def _draw_utm_grid(self, painter: QPainter):
        """Dibuja una cuadrícula cartográfica métrica UTM adaptativa con cruces y cotas."""
        if not self.show_grid or "grid" in self.hidden_layers:
            return
        w = self.width()
        h = self.height()

        target_grid_px = 140.0
        step_m_raw = target_grid_px / max(self.px_per_m, 1e-6)

        magnitude = 10.0 ** math.floor(math.log10(step_m_raw))
        ratio = step_m_raw / magnitude
        if ratio < 1.5:
            step_m = magnitude
        elif ratio < 3.5:
            step_m = 2.0 * magnitude
        elif ratio < 7.5:
            step_m = 5.0 * magnitude
        else:
            step_m = 10.0 * magnitude

        # Formato numérico adaptativo para no repetir enteros cuando step_m < 1 m
        if step_m >= 1.0:
            fmt_coord = lambda v: f"{v:.0f}"
        elif step_m >= 0.1:
            fmt_coord = lambda v: f"{v:.1f}"
        elif step_m >= 0.01:
            fmt_coord = lambda v: f"{v:.2f}"
        else:
            fmt_coord = lambda v: f"{v:.3f}"

        min_e, max_n = self.screen_to_utm(0, 0)
        max_e, min_n = self.screen_to_utm(w, h)

        start_e = math.floor(min_e / step_m) * step_m
        end_e = math.ceil(max_e / step_m) * step_m
        start_n = math.floor(min_n / step_m) * step_m
        end_n = math.ceil(max_n / step_m) * step_m

        pen_grid = QPen(QColor(148, 163, 184, 110), 1, Qt.DashLine)
        pen_text = QPen(QColor(100, 116, 139))
        font_grid = QFont("Consolas", 8)

        painter.save()
        painter.setFont(font_grid)

        # Líneas verticales (Este)
        cur_e = start_e
        while cur_e <= end_e + 1e-5:
            sx, _ = self.utm_to_screen(cur_e, self.center_n)
            if 0 <= sx <= w:
                painter.setPen(pen_grid)
                painter.drawLine(QPointF(sx, 0), QPointF(sx, h))
                painter.setPen(pen_text)
                painter.drawText(QPointF(sx + 4, h - 6), fmt_coord(cur_e))
            cur_e += step_m

        # Líneas horizontales (Norte)
        cur_n = start_n
        while cur_n <= end_n + 1e-5:
            _, sy = self.utm_to_screen(self.center_e, cur_n)
            if 0 <= sy <= h:
                painter.setPen(pen_grid)
                painter.drawLine(QPointF(0, sy), QPointF(w, sy))
                painter.setPen(pen_text)
                painter.drawText(QPointF(6, sy - 4), fmt_coord(cur_n))
            cur_n += step_m

        painter.restore()

    def _draw_platforms(self, painter: QPainter):
        """Dibuja la huella vectorial de la plataforma georreferenciada orientada por rumbo (Yaw)."""
        if not self.show_chassis or "chassis" in self.hidden_layers:
            return
        proj = self.get_project()
        painter.save()

        for plat_id, plat in proj.platforms.items():
            if not plat.pose_e or plat.pose_e.ref_system_id != self.ref_system_id:
                continue
            if f"plat_{plat_id}" in self.hidden_layers or f"chassis_{plat_id}" in self.hidden_layers:
                continue

            e_pla = plat.pose_e.utm_easting_m
            n_pla = plat.pose_e.utm_northing_m
            sx, sy = self.utm_to_screen(e_pla, n_pla)

            gamma_deg = plat.pose_e.convergence_deg if hasattr(plat.pose_e, "convergence_deg") else 0.0
            heading_grid_deg = plat.pose_e.yaw_deg - gamma_deg

            length_m = plat.length_m if plat.has_dimensions else 2.5
            width_m = plat.width_m if plat.has_dimensions else 1.5

            length_px = length_m * self.px_per_m
            width_px = width_m * self.px_per_m

            painter.save()
            painter.translate(sx, sy)
            painter.rotate(heading_grid_deg)

            # Dibujar geometría exacta del chasis (polígono trazado o caja centrada)
            plat.ensure_polygon()
            if plat.chassis_polygon and len(plat.chassis_polygon) >= 3:
                poly_path = QPainterPath()
                p0_xb = float(plat.chassis_polygon[0][0])
                p0_yb = float(plat.chassis_polygon[0][1])
                poly_path.moveTo(p0_yb * self.px_per_m, -p0_xb * self.px_per_m)
                for pt in plat.chassis_polygon[1:]:
                    poly_path.lineTo(float(pt[1]) * self.px_per_m, -float(pt[0]) * self.px_per_m)
                poly_path.closeSubpath()

                painter.setBrush(QBrush(QColor(2, 132, 199, 45)))
                painter.setPen(QPen(QColor(3, 105, 161), 2))
                painter.drawPath(poly_path)

                max_xb = max(float(pt[0]) for pt in plat.chassis_polygon)
            else:
                cx_b = float(plat.chassis_center_b[0]) if hasattr(plat, "chassis_center_b") else 0.0
                cy_b = float(plat.chassis_center_b[1]) if hasattr(plat, "chassis_center_b") else 0.0
                cx_px = cy_b * self.px_per_m
                cy_px = -cx_b * self.px_per_m
                rect_chassis = QRectF(cx_px - width_px / 2.0, cy_px - length_px / 2.0, width_px, length_px)

                painter.setBrush(QBrush(QColor(2, 132, 199, 45)))
                painter.setPen(QPen(QColor(3, 105, 161), 2))
                painter.drawRoundedRect(rect_chassis, 3, 3)

                max_xb = cx_b + length_m / 2.0

            # Indicador sutil y estilizado de proa (+Xb) en el perímetro frontal del chasis
            fwd_y = -max_xb * self.px_per_m
            fwd_notch = QPolygonF([
                QPointF(0, fwd_y - 6),
                QPointF(-5, fwd_y + 3),
                QPointF(5, fwd_y + 3)
            ])
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(239, 68, 68)))
            painter.drawPolygon(fwd_notch)

            # Origen central PLA (discreto)
            painter.setPen(QPen(QColor(15, 23, 42), 1.2))
            painter.setBrush(QBrush(QColor(2, 132, 199)))
            painter.drawEllipse(QPointF(0, 0), 3.5, 3.5)

            painter.restore()

            # Etiqueta limpia: solo el nombre descriptivo de la plataforma (ej. PLA2)
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.setPen(QPen(QColor(15, 23, 42)))
            painter.drawText(QPointF(sx + 10, sy - 14), plat.name)

        painter.restore()

    def _draw_sensors(self, painter: QPainter):
        """Dibuja cada sensor georreferenciado con su simbología métrica y etiqueta descriptiva."""
        if not self.show_sensors or "sensors" in self.hidden_layers:
            return
        proj = self.get_project()
        painter.save()
        painter.setFont(QFont("Consolas", 8, QFont.Bold))

        for plat_id, plat in proj.platforms.items():
            if f"plat_{plat_id}" in self.hidden_layers or f"sensors_{plat_id}" in self.hidden_layers:
                continue
            for code, s in plat.sensors.items():
                if not s.georef or s.georef.ref_system_id != self.ref_system_id:
                    continue
                if f"sensor_{plat_id}_{code}" in self.hidden_layers:
                    continue

                e_s = s.georef.utm_easting_m
                n_s = s.georef.utm_northing_m
                sx, sy = self.utm_to_screen(e_s, n_s)

                stype = s.sensor_type.value
                if "GNSS" in stype:
                    color = QColor(234, 88, 12)  # Naranja GNSS
                elif "INS" in stype:
                    color = QColor(5, 150, 105)  # Verde esmeralda INS
                elif "CAM" in stype:
                    color = QColor(219, 39, 119) # Fucsia Cámara
                else:
                    color = QColor(2, 132, 199)  # Azul

                box_sz = 9.0
                painter.setPen(QPen(QColor(15, 23, 42), 1.5))
                painter.setBrush(QBrush(color))
                painter.drawRect(QRectF(sx - box_sz / 2.0, sy - box_sz / 2.0, box_sz, box_sz))

                painter.setPen(QPen(color.darker(130)))
                painter.drawText(QPointF(sx + 7, sy + 4), s.name)

        painter.restore()

    def _draw_n_frame_triad(self, painter: QPainter):
        """
        Dibuja la terna local de navegación n-frame en el centro de cada plataforma georreferenciada visible:
        - Si es NED: Eje 1 (Rojo) = Norte (x_n), Eje 2 (Verde) = Este (y_n), Eje 3 (Azul) = Down (z_n, símbolo cruz).
        - Si es ENU: Eje 1 (Rojo) = Este (x_e), Eje 2 (Verde) = Norte (y_n), Eje 3 (Azul) = Up (z_u, símbolo punto).
        """
        if not self.show_n_frame or "n_frame" in self.hidden_layers:
            return
        proj = self.get_project()

        for plat_id, plat in proj.platforms.items():
            if not plat.pose_e or plat.pose_e.ref_system_id != self.ref_system_id:
                continue
            if f"plat_{plat_id}" in self.hidden_layers or f"n_frame_{plat_id}" in self.hidden_layers:
                continue

            e_pla = plat.pose_e.utm_easting_m
            n_pla = plat.pose_e.utm_northing_m
            sx, sy = self.utm_to_screen(e_pla, n_pla)

            painter.save()
            painter.setFont(QFont("Consolas", 8, QFont.Bold))

            triad_len = 45.0

            if self.n_frame_convention == "NED":
                # Eje 1: Norte (x_n) -> Rojo (Hacia arriba en pantalla, -Y)
                pen_n = QPen(QColor(239, 68, 68), 2.5)
                painter.setPen(pen_n)
                painter.drawLine(QPointF(sx, sy), QPointF(sx, sy - triad_len))
                painter.setBrush(QBrush(QColor(239, 68, 68)))
                painter.drawPolygon(QPolygonF([QPointF(sx, sy - triad_len - 6), QPointF(sx - 4, sy - triad_len + 2), QPointF(sx + 4, sy - triad_len + 2)]))
                painter.drawText(QPointF(sx + 5, sy - triad_len - 4), "N (x_n)")

                # Eje 2: Este (y_n) -> Verde (Hacia la derecha en pantalla, +X)
                pen_e = QPen(QColor(16, 185, 129), 2.5)
                painter.setPen(pen_e)
                painter.drawLine(QPointF(sx, sy), QPointF(sx + triad_len, sy))
                painter.setBrush(QBrush(QColor(16, 185, 129)))
                painter.drawPolygon(QPolygonF([QPointF(sx + triad_len + 6, sy), QPointF(sx + triad_len - 2, sy - 4), QPointF(sx + triad_len - 2, sy + 4)]))
                painter.drawText(QPointF(sx + triad_len + 6, sy + 12), "E (y_n)")

                # Eje 3: Down (z_n) -> Azul (Perpendicular hacia dentro de la tierra: símbolo círculo con cruz)
                painter.setPen(QPen(QColor(59, 130, 246), 2))
                painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
                r = 6.0
                painter.drawEllipse(QPointF(sx, sy), r, r)
                painter.drawLine(QPointF(sx - 3.5, sy - 3.5), QPointF(sx + 3.5, sy + 3.5))
                painter.drawLine(QPointF(sx - 3.5, sy + 3.5), QPointF(sx + 3.5, sy - 3.5))
                painter.setPen(QPen(QColor(59, 130, 246)))
                painter.drawText(QPointF(sx - 22, sy + 16), "D (z_n)")

            else:
                # ENU: Eje 1: Este (x_e) -> Rojo
                pen_e = QPen(QColor(239, 68, 68), 2.5)
                painter.setPen(pen_e)
                painter.drawLine(QPointF(sx, sy), QPointF(sx + triad_len, sy))
                painter.setBrush(QBrush(QColor(239, 68, 68)))
                painter.drawPolygon(QPolygonF([QPointF(sx + triad_len + 6, sy), QPointF(sx + triad_len - 2, sy - 4), QPointF(sx + triad_len - 2, sy + 4)]))
                painter.drawText(QPointF(sx + triad_len + 6, sy + 12), "E (x_e)")

                # Eje 2: Norte (y_n) -> Verde
                pen_n = QPen(QColor(16, 185, 129), 2.5)
                painter.setPen(pen_n)
                painter.drawLine(QPointF(sx, sy), QPointF(sx, sy - triad_len))
                painter.setBrush(QBrush(QColor(16, 185, 129)))
                painter.drawPolygon(QPolygonF([QPointF(sx, sy - triad_len - 6), QPointF(sx - 4, sy - triad_len + 2), QPointF(sx + 4, sy - triad_len + 2)]))
                painter.drawText(QPointF(sx + 5, sy - triad_len - 4), "N (y_n)")

                # Eje 3: Up (z_u) -> Azul (Perpendicular hacia afuera: símbolo círculo con punto)
                painter.setPen(QPen(QColor(59, 130, 246), 2))
                painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
                r = 6.0
                painter.drawEllipse(QPointF(sx, sy), r, r)
                painter.setBrush(QBrush(QColor(59, 130, 246)))
                painter.drawEllipse(QPointF(sx, sy), 2.5, 2.5)
                painter.setPen(QPen(QColor(59, 130, 246)))
                painter.drawText(QPointF(sx - 22, sy + 16), "U (z_u)")

            painter.restore()

    def _draw_compass_rose(self, painter: QPainter):
        """Dibuja una elegante rosa de los vientos técnica en la esquina superior derecha."""
        if not self.show_compass or "compass" in self.hidden_layers:
            return
        w = self.width()
        cx = w - 45.0
        cy = 50.0

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.setPen(QPen(QColor(148, 163, 184, 180), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255, 210)))
        painter.drawEllipse(QPointF(cx, cy), 26.0, 26.0)

        poly_n = QPolygonF([QPointF(cx, cy - 20), QPointF(cx - 5, cy), QPointF(cx, cy - 3)])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(239, 68, 68)))
        painter.drawPolygon(poly_n)

        poly_s = QPolygonF([QPointF(cx, cy + 20), QPointF(cx + 5, cy), QPointF(cx, cy + 3)])
        painter.setBrush(QBrush(QColor(71, 85, 105)))
        painter.drawPolygon(poly_s)

        painter.setPen(QPen(QColor(239, 68, 68)))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(QPointF(cx - 4.5, cy - 22.0), "N")

        painter.restore()

    def _draw_scale_bar(self, painter: QPainter):
        """Dibuja una barra de escala gráfica métrica adaptativa en la esquina inferior izquierda."""
        if not self.show_scalebar or "scalebar" in self.hidden_layers:
            return
        h = self.height()
        target_bar_px = 120.0
        bar_m_raw = target_bar_px / max(self.px_per_m, 1e-6)

        magnitude = 10.0 ** math.floor(math.log10(bar_m_raw))
        ratio = bar_m_raw / magnitude
        if ratio < 1.5:
            bar_m = magnitude
        elif ratio < 3.5:
            bar_m = 2.0 * magnitude
        elif ratio < 7.5:
            bar_m = 5.0 * magnitude
        else:
            bar_m = 10.0 * magnitude

        actual_bar_px = bar_m * self.px_per_m
        bx = 20.0
        by = h - 22.0

        painter.save()
        painter.setFont(QFont("Consolas", 8, QFont.Bold))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
        painter.drawRoundedRect(QRectF(bx - 6, by - 16, actual_bar_px + 12, 24), 3, 3)

        painter.setPen(QPen(QColor(15, 23, 42), 2))
        painter.drawLine(QPointF(bx, by), QPointF(bx + actual_bar_px, by))
        painter.drawLine(QPointF(bx, by - 4), QPointF(bx, by + 4))
        painter.drawLine(QPointF(bx + actual_bar_px, by - 4), QPointF(bx + actual_bar_px, by + 4))

        if bar_m < 0.1:
            label = f"{bar_m:.2f} m"
        elif bar_m < 1.0:
            label = f"{bar_m:.1f} m"
        elif bar_m < 1000.0:
            label = f"{bar_m:.0f} m"
        else:
            label = f"{bar_m/1000.0:.1f} km"

        painter.setPen(QPen(QColor(15, 23, 42)))
        painter.drawText(QRectF(bx, by - 16, actual_bar_px, 12), Qt.AlignCenter, label)

        painter.restore()


class CartoMapWidget(QWidget):
    """
    Contenedor completo de la pestaña de Mapa Cartográfico 2D (e-frame).
    Lienzo 100% limpio sin barras de herramientas invasivas y con barra de coordenadas inferior.
    """
    basemap_visibility_changed = Signal(str, bool)

    def __init__(
        self,
        get_project: Callable[[], Project],
        ref_system_id: str,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.get_project = get_project
        self.ref_system_id = ref_system_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Lienzo Cartográfico Central
        self.canvas = CartoMapCanvas(self.get_project, self.ref_system_id, self)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.coordinates_changed.connect(self._on_coordinates_changed)
        self.canvas.basemap_visibility_changed.connect(self.basemap_visibility_changed)
        layout.addWidget(self.canvas, 1)

        # 2. Barra de Coordenadas Inferior
        self.footer = QWidget()
        self.footer.setFixedHeight(24)
        self.footer.setStyleSheet("background-color: #f8fafc; border-top: 1px solid #cbd5e1; font-family: 'Consolas', monospace; font-size: 11px;")
        foot_layout = QHBoxLayout(self.footer)
        foot_layout.setContentsMargins(10, 0, 10, 0)

        self.lbl_coords_utm = QLabel("E: - m | N: - m")
        self.lbl_coords_utm.setStyleSheet("color: #0f172a; font-weight: bold;")
        foot_layout.addWidget(self.lbl_coords_utm)

        foot_layout.addSpacing(16)
        self.lbl_coords_geo = QLabel("Lat: - | Lon: -")
        self.lbl_coords_geo.setStyleSheet("color: #475569;")
        foot_layout.addWidget(self.lbl_coords_geo)

        foot_layout.addStretch()

        proj = self.get_project()
        rs = proj.reference_systems.get(self.ref_system_id)
        rs_label = f"SRT: {rs.name} [{rs.id}] (EPSG:25830)" if rs else f"SRT: {self.ref_system_id}"
        self.lbl_srt_info = QLabel(rs_label)
        self.lbl_srt_info.setStyleSheet("color: #0077b6; font-weight: 500;")
        foot_layout.addWidget(self.lbl_srt_info)

        layout.addWidget(self.footer)

    def refresh(self):
        """Redibuja el lienzo cartográfico actualizando datos del proyecto."""
        self.canvas.update()

    def set_ref_system_id(self, rs_id: str):
        self.ref_system_id = rs_id
        proj = self.get_project()
        rs = proj.reference_systems.get(rs_id)
        rs_label = f"SRT: {rs.name} [{rs.id}] (EPSG:25830)" if rs else f"SRT: {rs_id}"
        self.lbl_srt_info.setText(rs_label)
        self.canvas.set_ref_system_id(rs_id)

    def zoom_to_platform(self, plat_id: str):
        """Encuadra la vista en la bounding box de la plataforma especificada."""
        proj = self.get_project()
        plat = proj.get_platform(plat_id)
        if not plat:
            return
        bbox = plat.get_utm_bounding_box()
        if bbox:
            self.canvas.zoom_to_bbox(bbox["min_e"], bbox["max_e"], bbox["min_n"], bbox["max_n"], margin=0.35)
        else:
            self.canvas.zoom_to_platforms()

    def set_layer_visibility(self, layer_key: str, visible: bool):
        """Actualiza la visibilidad de una capa en el lienzo cartográfico."""
        if visible:
            self.canvas.hidden_layers.discard(layer_key)
            if layer_key == "basemap":
                self.canvas.show_osm = True
        else:
            self.canvas.hidden_layers.add(layer_key)
            if layer_key == "basemap":
                self.canvas.show_osm = False
        self.canvas.update()

    def _on_coordinates_changed(self, easting: float, northing: float, lat_deg: float, lon_deg: float):
        self.lbl_coords_utm.setText(f"E: {easting:,.2f} m | N: {northing:,.2f} m")
        lat_dir = "N" if lat_deg >= 0 else "S"
        lon_dir = "E" if lon_deg >= 0 else "W"
        self.lbl_coords_geo.setText(f"φ: {abs(lat_deg):.6f}°{lat_dir} | λ: {abs(lon_deg):.6f}°{lon_dir}")


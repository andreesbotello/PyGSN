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
    QPolygonF, QCursor
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
        self.show_osm = True
        self.show_chassis = True
        self.show_sensors = True
        self.show_n_frame = True
        self.show_grid = True
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
        if self.show_osm:
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
            self._draw_osm_tiles(painter)

        # 2. Capa Cuadrícula UTM
        if self.show_grid:
            self._draw_utm_grid(painter)

        # 3. Plataformas georreferenciadas
        if self.show_chassis:
            self._draw_platforms(painter)

        # 4. Sensores georreferenciados
        if self.show_sensors:
            self._draw_sensors(painter)

        # 5. Terna local de navegación n-frame
        if self.show_n_frame:
            self._draw_n_frame_triad(painter)

        # 6. Elementos cartográficos fijos (Rosa de los Vientos y Escala)
        self._draw_compass_rose(painter)
        self._draw_scale_bar(painter)

    def _draw_osm_tiles(self, painter: QPainter):
        """Calcula el rango de teselas OSM visibles, las proyecta en pantalla y las dibuja."""
        w = self.width()
        h = self.height()

        # Esquinas visibles en UTM
        min_e, max_n = self.screen_to_utm(0, 0)
        max_e, min_n = self.screen_to_utm(w, h)

        try:
            lat_tl_rad, lon_tl_rad = utm_inverse(min_e, max_n, zone=30, hemisphere="N", ell=GRS80)
            lat_br_rad, lon_br_rad = utm_inverse(max_e, min_n, zone=30, hemisphere="N", ell=GRS80)
            lat_tl, lon_tl = math.degrees(lat_tl_rad), math.degrees(lon_tl_rad)
            lat_br, lon_br = math.degrees(lat_br_rad), math.degrees(lon_br_rad)
        except Exception:
            return

        # Nivel de zoom OSM según px_per_m y latitud media
        mid_lat = (lat_tl + lat_br) / 2.0
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

        x_min_f, y_min_f = deg2tile(lat_tl, lon_tl, z)
        x_max_f, y_max_f = deg2tile(lat_br, lon_br, z)

        x_start = max(int(math.floor(min(x_min_f, x_max_f))), 0)
        x_end = min(int(math.ceil(max(x_min_f, x_max_f))), 2**z)
        y_start = max(int(math.floor(min(y_min_f, y_max_f))), 0)
        y_end = min(int(math.ceil(max(y_min_f, y_max_f))), 2**z)

        if (x_end - x_start) * (y_end - y_start) > 64:
            return

        painter.save()
        painter.setOpacity(0.85)

        for tx in range(x_start, x_end):
            for ty in range(y_start, y_end):
                pix = self.tile_mgr.get_tile(z, tx, ty)
                t_lat_top, t_lon_left = tile2deg(tx, ty, z)
                t_lat_bot, t_lon_right = tile2deg(tx + 1, ty + 1, z)

                try:
                    e_left, n_top, _ = utm_projection(math.radians(t_lat_top), math.radians(t_lon_left), zone=30, hemisphere="N")
                    e_right, n_bot, _ = utm_projection(math.radians(t_lat_bot), math.radians(t_lon_right), zone=30, hemisphere="N")
                    sx_left, sy_top = self.utm_to_screen(e_left, n_top)
                    sx_right, sy_bot = self.utm_to_screen(e_right, n_bot)

                    rect = QRectF(sx_left, sy_top, sx_right - sx_left, sy_bot - sy_top)
                    if pix and not pix.isNull():
                        painter.drawPixmap(rect.toRect(), pix)
                except Exception:
                    continue

        painter.restore()

    def _draw_utm_grid(self, painter: QPainter):
        """Dibuja una cuadrícula cartográfica métrica UTM adaptativa con cruces y cotas."""
        w = self.width()
        h = self.height()

        target_grid_px = 100.0
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

        min_e, max_n = self.screen_to_utm(0, 0)
        max_e, min_n = self.screen_to_utm(w, h)

        start_e = math.floor(min_e / step_m) * step_m
        end_e = math.ceil(max_e / step_m) * step_m
        start_n = math.floor(min_n / step_m) * step_m
        end_n = math.ceil(max_n / step_m) * step_m

        pen_grid = QPen(QColor(148, 163, 184, 120), 1, Qt.DashLine)
        pen_text = QPen(QColor(51, 65, 85, 200))
        font_grid = QFont("Consolas", 8)

        painter.save()
        painter.setFont(font_grid)

        # Líneas verticales (Este)
        cur_e = start_e
        while cur_e <= end_e:
            sx, _ = self.utm_to_screen(cur_e, self.center_n)
            if 0 <= sx <= w:
                painter.setPen(pen_grid)
                painter.drawLine(QPointF(sx, 0), QPointF(sx, h))
                painter.setPen(pen_text)
                painter.drawText(QPointF(sx + 3, h - 8), f"{cur_e:,.0f} m E")
            cur_e += step_m

        # Líneas horizontales (Norte)
        cur_n = start_n
        while cur_n <= end_n:
            _, sy = self.utm_to_screen(self.center_e, cur_n)
            if 0 <= sy <= h:
                painter.setPen(pen_grid)
                painter.drawLine(QPointF(0, sy), QPointF(w, sy))
                painter.setPen(pen_text)
                painter.drawText(QPointF(6, sy - 3), f"{cur_n:,.0f} m N")
            cur_n += step_m

        painter.restore()

    def _draw_platforms(self, painter: QPainter):
        """Dibuja la huella vectorial de la plataforma georreferenciada orientada por rumbo (Yaw)."""
        proj = self.get_project()
        painter.save()

        for plat_id, plat in proj.platforms.items():
            if not plat.pose_e or plat.pose_e.ref_system_id != self.ref_system_id:
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

            rect_chassis = QRectF(-width_px / 2.0, -length_px / 2.0, width_px, length_px)

            painter.setBrush(QBrush(QColor(2, 132, 199, 50)))
            painter.setPen(QPen(QColor(3, 105, 161), 2))
            painter.drawRoundedRect(rect_chassis, 3, 3)

            # Eje de Proa Xb (Rojo)
            pen_xb = QPen(QColor(239, 68, 68), 2.5)
            painter.setPen(pen_xb)
            arrow_len = max(length_px * 0.6, 24.0)
            painter.drawLine(QPointF(0, 0), QPointF(0, -arrow_len))
            painter.setBrush(QBrush(QColor(239, 68, 68)))
            tri_fwd = QPolygonF([QPointF(0, -arrow_len - 5), QPointF(-4, -arrow_len + 3), QPointF(4, -arrow_len + 3)])
            painter.drawPolygon(tri_fwd)

            # Eje de Estribor Yb (Verde)
            pen_yb = QPen(QColor(16, 185, 129), 2.5)
            painter.setPen(pen_yb)
            arrow_w = max(width_px * 0.6, 18.0)
            painter.drawLine(QPointF(0, 0), QPointF(arrow_w, 0))
            painter.setBrush(QBrush(QColor(16, 185, 129)))
            tri_rgt = QPolygonF([QPointF(arrow_w + 5, 0), QPointF(arrow_w - 3, -4), QPointF(arrow_w - 3, 4)])
            painter.drawPolygon(tri_rgt)

            # Origen central PLA (Azul)
            painter.setPen(QPen(QColor(15, 23, 42), 1.5))
            painter.setBrush(QBrush(QColor(2, 132, 199)))
            painter.drawEllipse(QPointF(0, 0), 4.5, 4.5)

            painter.restore()

            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.setPen(QPen(QColor(15, 23, 42)))
            painter.drawText(QPointF(sx + 10, sy - 10), f"PLA: {plat.name} ({plat.id})")

        painter.restore()

    def _draw_sensors(self, painter: QPainter):
        """Dibuja cada sensor georreferenciado con su simbología métrica y etiqueta descriptiva."""
        proj = self.get_project()
        painter.save()
        painter.setFont(QFont("Consolas", 8, QFont.Bold))

        for plat in proj.platforms.values():
            for code, s in plat.sensors.items():
                if not s.georef or s.georef.ref_system_id != self.ref_system_id:
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
        Dibuja la terna local de navegación n-frame en el centro de la plataforma activa:
        - Si es NED: Eje 1 (Rojo) = Norte, Eje 2 (Verde) = Este, Eje 3 (Azul) = Down (símbolo cruz).
        - Si es ENU: Eje 1 (Rojo) = Este, Eje 2 (Verde) = Norte, Eje 3 (Azul) = Up (símbolo punto).
        """
        proj = self.get_project()
        active_plat = proj.get_active_platform()
        if not active_plat or not active_plat.pose_e or active_plat.pose_e.ref_system_id != self.ref_system_id:
            return

        e_pla = active_plat.pose_e.utm_easting_m
        n_pla = active_plat.pose_e.utm_northing_m
        sx, sy = self.utm_to_screen(e_pla, n_pla)

        painter.save()
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))

        triad_len = 50.0

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
            r = 7.0
            painter.drawEllipse(QPointF(sx, sy), r, r)
            painter.drawLine(QPointF(sx - 4, sy - 4), QPointF(sx + 4, sy + 4))
            painter.drawLine(QPointF(sx - 4, sy + 4), QPointF(sx + 4, sy - 4))
            painter.setPen(QPen(QColor(59, 130, 246)))
            painter.drawText(QPointF(sx - 24, sy + 18), "D (z_n)")

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
            r = 7.0
            painter.drawEllipse(QPointF(sx, sy), r, r)
            painter.setBrush(QBrush(QColor(59, 130, 246)))
            painter.drawEllipse(QPointF(sx, sy), 2.5, 2.5)
            painter.setPen(QPen(QColor(59, 130, 246)))
            painter.drawText(QPointF(sx - 24, sy + 18), "U (z_u)")

        painter.restore()

    def _draw_compass_rose(self, painter: QPainter):
        """Dibuja una elegante rosa de los vientos técnica en la esquina superior derecha."""
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

        label = f"{bar_m:,.0f} m" if bar_m < 1000.0 else f"{bar_m/1000.0:,.1f} km"
        painter.setPen(QPen(QColor(15, 23, 42)))
        painter.drawText(QPointF(bx + actual_bar_px / 2.0 - 15, by - 5), label)

        painter.restore()


class CartoMapWidget(QWidget):
    """
    Contenedor completo de la pestaña de Mapa Cartográfico 2D (e-frame).
    Integra la barra de herramientas cartográficas, el lienzo vectorial y la barra de coordenadas inferior.
    """

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

        # 1. Barra de herramientas superior compacta
        self.toolbar = QToolBar("Herramientas de Mapa")
        self.toolbar.setMovable(False)
        self.toolbar.setStyleSheet("QToolBar { background-color: #f8fafc; border-bottom: 1px solid #cbd5e1; padding: 2px 6px; }")

        # Botón Centrar en Plataforma
        self.btn_fit_plat = QToolButton()
        self.btn_fit_plat.setText("Centrar en Plataforma")
        self.btn_fit_plat.setToolTip("Encuadra y centra la vista en la plataforma activa")
        self.btn_fit_plat.clicked.connect(self._on_center_platform)
        self.toolbar.addWidget(self.btn_fit_plat)

        # Botón Zoom Extensión
        self.btn_fit_all = QToolButton()
        self.btn_fit_all.setText("Zoom Extensión")
        self.btn_fit_all.setToolTip("Encuadre general que abarca todas las plataformas y sensores georreferenciados")
        self.btn_fit_all.clicked.connect(self._on_zoom_extent)
        self.toolbar.addWidget(self.btn_fit_all)

        self.toolbar.addSeparator()

        # Botón Toggle Mapa Base (OSM)
        self.btn_toggle_osm = QToolButton()
        self.btn_toggle_osm.setText("Mapa Base: OSM")
        self.btn_toggle_osm.setCheckable(True)
        self.btn_toggle_osm.setChecked(True)
        self.btn_toggle_osm.setToolTip("Activar o desactivar las teselas cartográficas de OpenStreetMap")
        self.btn_toggle_osm.toggled.connect(self._on_toggle_osm)
        self.toolbar.addWidget(self.btn_toggle_osm)

        # Selector de Convención n-frame
        lbl_nframe = QLabel(" Terna local: ")
        lbl_nframe.setStyleSheet("font-size: 11px; font-weight: 500; color: #475569;")
        self.toolbar.addWidget(lbl_nframe)

        self.combo_nframe = QComboBox()
        self.combo_nframe.addItems(["n-frame: NED (Inercial)", "n-frame: ENU (GeoTop)"])
        self.combo_nframe.setToolTip("Convención de navegación local tangente a la plataforma")
        self.combo_nframe.currentIndexChanged.connect(self._on_nframe_convention_changed)
        self.toolbar.addWidget(self.combo_nframe)

        self.toolbar.addSeparator()

        # Menú Capas Visibles
        self.btn_layers = QToolButton()
        self.btn_layers.setText("Capas Visibles")
        self.btn_layers.setPopupMode(QToolButton.InstantPopup)
        menu_layers = QMenu(self)

        self.act_lay_chassis = menu_layers.addAction("Plataformas y Chasis")
        self.act_lay_chassis.setCheckable(True)
        self.act_lay_chassis.setChecked(True)
        self.act_lay_chassis.toggled.connect(self._on_toggle_chassis)

        self.act_lay_sensors = menu_layers.addAction("Sensores Georreferenciados")
        self.act_lay_sensors.setCheckable(True)
        self.act_lay_sensors.setChecked(True)
        self.act_lay_sensors.toggled.connect(self._on_toggle_sensors)

        self.act_lay_triad = menu_layers.addAction("Terna n-frame")
        self.act_lay_triad.setCheckable(True)
        self.act_lay_triad.setChecked(True)
        self.act_lay_triad.toggled.connect(self._on_toggle_triad)

        self.act_lay_grid = menu_layers.addAction("Cuadrícula UTM")
        self.act_lay_grid.setCheckable(True)
        self.act_lay_grid.setChecked(True)
        self.act_lay_grid.toggled.connect(self._on_toggle_grid)

        self.btn_layers.setMenu(menu_layers)
        self.toolbar.addWidget(self.btn_layers)

        layout.addWidget(self.toolbar)

        # 2. Lienzo Cartográfico Central
        self.canvas = CartoMapCanvas(self.get_project, self.ref_system_id, self)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.coordinates_changed.connect(self._on_coordinates_changed)
        layout.addWidget(self.canvas, 1)

        # 3. Barra de Coordenadas Inferior
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

    def _on_center_platform(self):
        self.canvas.zoom_to_platforms()

    def _on_zoom_extent(self):
        self.canvas.zoom_to_fit_extent()

    def _on_toggle_osm(self, checked: bool):
        self.canvas.show_osm = checked
        self.canvas.update()

    def _on_nframe_convention_changed(self, index: int):
        self.canvas.n_frame_convention = "NED" if index == 0 else "ENU"
        self.canvas.update()

    def _on_toggle_chassis(self, checked: bool):
        self.canvas.show_chassis = checked
        self.canvas.update()

    def _on_toggle_sensors(self, checked: bool):
        self.canvas.show_sensors = checked
        self.canvas.update()

    def _on_toggle_triad(self, checked: bool):
        self.canvas.show_n_frame = checked
        self.canvas.update()

    def _on_toggle_grid(self, checked: bool):
        self.canvas.show_grid = checked
        self.canvas.update()

    def _on_coordinates_changed(self, easting: float, northing: float, lat_deg: float, lon_deg: float):
        self.lbl_coords_utm.setText(f"E: {easting:,.2f} m | N: {northing:,.2f} m")
        lat_dir = "N" if lat_deg >= 0 else "S"
        lon_dir = "E" if lon_deg >= 0 else "W"
        self.lbl_coords_geo.setText(f"φ: {abs(lat_deg):.6f}°{lat_dir} | λ: {abs(lon_deg):.6f}°{lon_dir}")

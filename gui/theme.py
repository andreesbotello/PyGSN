"""
PyGSN - GUI Theme and Palette (PySide6 / Qt)
============================================
Estilo visual de alto contraste y precisión para ingeniería y fotogrametría/geodesia.
Tema claro por defecto optimizado para visualización técnica CAD e iconografía SVG nativa.
Incluye soporte desacoplado para conmutación futura a tema oscuro.
"""

from typing import Tuple
from pathlib import Path
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QWidget

ICONS_DIR = Path(__file__).resolve().parent.parent / "icons"
ARROW_DOWN_PATH = (ICONS_DIR / "arrow_down.svg").as_posix()
ARROW_DOWN_LIGHT_PATH = (ICONS_DIR / "arrow_down_light.svg").as_posix()



# ==============================================================================
# PALETA TEMA CLARO (LIGHT THEME) — PREDETERMINADO
# ==============================================================================

# Lienzo CAD (Fondo blanco técnico / tiza de ingeniería)
COLOR_CANVAS_BG: Tuple[int, int, int, int] = (252, 253, 255, 255)
COLOR_GRID_MAJOR: Tuple[int, int, int, int] = (205, 215, 228, 255)       # Líneas principales
COLOR_GRID_MINOR: Tuple[int, int, int, int] = (235, 240, 246, 255)       # Cuadrícula secundaria

# Ejes Body (b-frame) estrictamente RGB:
COLOR_AXIS_X: Tuple[int, int, int, int] = (220, 38, 38, 255)            # Rojo R: +Xb Adelante
COLOR_AXIS_Y: Tuple[int, int, int, int] = (22, 163, 74, 255)            # Verde G: +Yb Derecha
COLOR_AXIS_Z: Tuple[int, int, int, int] = (37, 99, 235, 255)            # Azul B: -Zb Arriba / +Zb Abajo

COLOR_PLATFORM_BODY: Tuple[int, int, int, int] = (2, 132, 199, 220)      # Azul técnico (#0284c7)
COLOR_ORIGIN: Tuple[int, int, int, int] = (15, 23, 42, 255)              # Origen PLA: Pizarra oscura (#0f172a)
COLOR_CENTROID: Tuple[int, int, int, int] = (217, 119, 6, 255)           # Ámbar oscuro (#d97706)

# Sensores en lienzo CAD
COLOR_SENSOR_GNSS: Tuple[int, int, int, int] = (194, 65, 12, 255)        # Ámbar/Naranja oscuro (#c2410c)
COLOR_SENSOR_INS: Tuple[int, int, int, int] = (5, 150, 105, 255)         # Verde esmeralda (#059669)
COLOR_SENSOR_CAM: Tuple[int, int, int, int] = (219, 39, 119, 255)        # Magenta intenso (#db2777)
COLOR_SENSOR_DEFAULT: Tuple[int, int, int, int] = (71, 85, 105, 255)     # Pizarra (#475569)

COLOR_TEXT_PRIMARY: Tuple[int, int, int, int] = (15, 23, 42, 255)        # Pizarra 900
COLOR_TEXT_MUTED: Tuple[int, int, int, int] = (100, 116, 139, 255)       # Pizarra 500

# ==============================================================================
# HOJA DE ESTILOS QT (QSS) — TEMA CLARO
# ==============================================================================

PYGSN_LIGHT_QSS = """
QMainWindow, QDialog {
    background-color: #f1f3f5;
    color: #212529;
}

QWidget {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 12px;
    color: #212529;
}

QMenuBar {
    background-color: #ffffff;
    color: #212529;
    border-bottom: 1px solid #dee2e6;
    padding: 2px;
}

QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}

QMenuBar::item:selected {
    background-color: #e9ecef;
    color: #0077b6;
}

QMenu {
    background-color: #ffffff;
    color: #212529;
    border: 1px solid #ced4da;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px 6px 20px;
    border-radius: 3px;
}

QMenu::item:selected {
    background-color: #0077b6;
    color: #ffffff;
}

QMenu::separator {
    height: 1px;
    background-color: #dee2e6;
    margin: 4px 6px;
}

QToolBar {
    background-color: #f8f9fa;
    border-bottom: 1px solid #dee2e6;
    spacing: 5px;
    padding: 3px 6px;
}

QToolButton {
    background-color: #ffffff;
    color: #212529;
    border: 1px solid #ced4da;
    border-radius: 3px;
    padding: 3px 8px;
    font-weight: 500;
}

QToolButton:hover {
    background-color: #e9ecef;
    border-color: #0077b6;
}

QToolButton:pressed, QToolButton:checked {
    background-color: #0077b6;
    border-color: #005f92;
    color: #ffffff;
}

QToolButton:disabled {
    background-color: #f8f9fa;
    color: #adb5bd;
    border-color: #e9ecef;
}

QDockWidget {
    color: #0077b6;
    font-weight: bold;
}

QDockWidget::title {
    background-color: #e9ecef;
    border: 1px solid #dee2e6;
    padding: 6px;
    text-align: left;
    color: #212529;
}

QTreeWidget, QTreeView, QListWidget {
    background-color: #ffffff;
    border: 1px solid #dee2e6;
    color: #212529;
    outline: none;
    alternate-background-color: #f8f9fa;
}

QTreeWidget::item {
    padding: 3px 2px;
    border-radius: 2px;
}

QTreeWidget::item:hover {
    background-color: #f1f3f5;
}

QTreeWidget::item:selected {
    background-color: #e3f2fd;
    color: #0077b6;
}

QTabWidget::pane {
    border: 1px solid #dee2e6;
    background-color: #ffffff;
}

QTabBar::tab {
    background-color: #e9ecef;
    color: #495057;
    border: 1px solid #dee2e6;
    border-bottom: none;
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:hover {
    background-color: #dee2e6;
    color: #212529;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    color: #0077b6;
    font-weight: bold;
    border-top: 2px solid #0077b6;
}

QStatusBar {
    background-color: #e9ecef;
    border-top: 1px solid #dee2e6;
    color: #495057;
    font-size: 11px;
}

QPushButton {
    background-color: #0077b6;
    color: #ffffff;
    border: 1px solid #005f92;
    border-radius: 3px;
    padding: 5px 12px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #0096c7;
    border-color: #0077b6;
}

QPushButton:pressed {
    background-color: #023e8a;
}

QPushButton:disabled {
    background-color: #e9ecef;
    color: #adb5bd;
    border-color: #dee2e6;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    border: 1px solid #ced4da;
    border-radius: 3px;
    color: #212529;
    padding: 4px 6px;
    selection-background-color: #e3f2fd;
    selection-color: #0077b6;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #0077b6;
}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    background-color: #e9ecef;
    color: #8c96a5;
    border: 1px solid #ced4da;
}

/* Supresión técnica de flechas up/down en todos los spinboxes */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: none;
    width: 0px;
    height: 0px;
}

QComboBox {
    background-color: #ffffff;
    border: 1px solid #ced4da;
    border-radius: 3px;
    color: #212529;
    padding: 4px 24px 4px 6px;
    selection-background-color: #e3f2fd;
    selection-color: #0077b6;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid #ced4da;
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
    background: transparent;
}

QComboBox::down-arrow {
    image: url("__ARROW_DOWN__");
    width: 10px;
    height: 6px;
}

QComboBox::down-arrow:disabled {
    image: url("__ARROW_DOWN__");
    opacity: 0.35;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #ced4da;
    selection-background-color: #e3f2fd;
    color: #212529;
}

QScrollBar:vertical {
    border: none;
    background: #f1f3f5;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #ced4da;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #0077b6;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #f1f3f5;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #ced4da;
    min-width: 20px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #0077b6;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QGroupBox {
    border: 1px solid #ced4da;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 12px;
    font-weight: bold;
    color: #0077b6;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}

QCheckBox {
    spacing: 6px;
    color: #212529;
}

QCheckBox::indicator {
    width: 13px;
    height: 13px;
    background-color: #ffffff;
    border: 1px solid #94a3b8;
    border-radius: 2px;
}

QCheckBox::indicator:hover {
    border-color: #0077b6;
}

QCheckBox::indicator:checked {
    background-color: #0077b6;
    border: 1px solid #005f92;
}

QRadioButton {
    spacing: 6px;
    color: #212529;
}

QRadioButton::indicator {
    width: 13px;
    height: 13px;
    background-color: #ffffff;
    border: 1px solid #94a3b8;
    border-radius: 7px;
}

QRadioButton::indicator:hover {
    border-color: #0077b6;
}

QRadioButton::indicator:checked {
    border: 1px solid #0077b6;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.35, fx:0.5, fy:0.5, stop:0 #0077b6, stop:0.85 #0077b6, stop:0.86 #ffffff, stop:1.0 #ffffff);
}

QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    gridline-color: #e9ecef;
}

QHeaderView::section {
    background-color: #e9ecef;
    color: #212529;
    padding: 4px;
    border: 1px solid #dee2e6;
    font-weight: bold;
}

QTableCornerButton::section {
    background-color: #e9ecef;
    border: 1px solid #dee2e6;
}

QHeaderView::section:checked {
    background-color: #dee2e6;
    color: #0077b6;
}

/* ==========================================================================
   QMessageBox y Diálogos de Alerta / Pop-ups
   ========================================================================== */
QMessageBox {
    background-color: #ffffff;
    color: #212529;
}

QMessageBox QLabel {
    background: transparent;
    color: #212529;
    font-size: 12px;
}

QMessageBox QPushButton {
    background-color: #0077b6;
    color: #ffffff;
    border: 1px solid #005f92;
    border-radius: 4px;
    padding: 5px 14px;
    min-width: 110px;
    min-height: 24px;
    font-size: 11px;
    font-weight: 500;
}

QMessageBox QPushButton:hover {
    background-color: #0096c7;
}

QMessageBox QPushButton:pressed {
    background-color: #023e8a;
}

QMessageBox QPushButton:focus {
    outline: none;
    border: 1px solid #0077b6;
}

QDialogButtonBox QPushButton {
    min-width: 90px;
    padding: 5px 12px;
}
"""

# ==============================================================================
# HOJA DE ESTILOS QT (QSS) — TEMA OSCURO (PRESERVADA PARA FUTURA ACTIVACIÓN)
# ==============================================================================

PYGSN_DARK_QSS = """
QMainWindow, QDialog {
    background-color: #1a1c23;
    color: #e6ebf5;
}

QWidget {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 12px;
    color: #e6ebf5;
}

QMenuBar {
    background-color: #16181e;
    color: #e6ebf5;
    border-bottom: 1px solid #2d313d;
    padding: 2px;
}

QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}

QMenuBar::item:selected {
    background-color: #2b3240;
    color: #00b4d8;
}

QMenu {
    background-color: #1f232b;
    color: #e6ebf5;
    border: 1px solid #3b4252;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px 6px 20px;
    border-radius: 3px;
}

QMenu::item:selected {
    background-color: #2e5b88;
    color: #ffffff;
}

QToolBar {
    background-color: #1a1c23;
    border-bottom: 1px solid #2d313d;
    spacing: 5px;
    padding: 3px 6px;
}

QToolButton {
    background-color: #252a34;
    color: #e6ebf5;
    border: 1px solid #3b4252;
    border-radius: 3px;
    padding: 3px 8px;
    font-weight: 500;
}

QToolButton:hover {
    background-color: #323a48;
    border-color: #00b4d8;
}

QToolButton:pressed, QToolButton:checked {
    background-color: #0077b6;
    border-color: #90e0ef;
    color: #ffffff;
}

QDockWidget {
    color: #00b4d8;
    font-weight: bold;
}

QDockWidget::title {
    background-color: #16181e;
    border: 1px solid #2d313d;
    padding: 6px;
    text-align: left;
}

QTreeWidget, QTreeView, QListWidget {
    background-color: #16181e;
    border: 1px solid #2d313d;
    color: #e6ebf5;
    outline: none;
    alternate-background-color: #1a1c24;
}

QTabWidget::pane {
    border: 1px solid #2d313d;
    background-color: #14161b;
}

QTabBar::tab {
    background-color: #1e222a;
    color: #a0aec0;
    border: 1px solid #2d313d;
    border-bottom: none;
    padding: 6px 14px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #14161b;
    color: #00b4d8;
    font-weight: bold;
    border-top: 2px solid #00b4d8;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #1a1c24;
    border: 1px solid #3b4252;
    border-radius: 3px;
    color: #e6ebf5;
    padding: 4px 6px;
}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    background-color: #16181e;
    color: #64748b;
    border: 1px solid #2d313d;
}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: none;
    width: 0px;
    height: 0px;
}

QStatusBar {
    background-color: #16181e;
    border-top: 1px solid #2d313d;
    color: #8c96a5;
    font-size: 11px;
}

QCheckBox {
    spacing: 6px;
    color: #e6ebf5;
}

QCheckBox::indicator {
    width: 13px;
    height: 13px;
    background-color: #1a1c24;
    border: 1px solid #4b5563;
    border-radius: 2px;
}

QCheckBox::indicator:hover {
    border-color: #00b4d8;
}

QCheckBox::indicator:checked {
    background-color: #00b4d8;
    border: 1px solid #0077b6;
}

QRadioButton {
    spacing: 6px;
    color: #e6ebf5;
}

QRadioButton::indicator {
    width: 13px;
    height: 13px;
    background-color: #1a1c24;
    border: 1px solid #4b5563;
    border-radius: 7px;
}

QRadioButton::indicator:hover {
    border-color: #00b4d8;
}

QRadioButton::indicator:checked {
    border: 1px solid #00b4d8;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.35, fx:0.5, fy:0.5, stop:0 #00b4d8, stop:0.85 #00b4d8, stop:0.86 #1a1c24, stop:1.0 #1a1c24);
}
"""

PYGSN_LIGHT_QSS = PYGSN_LIGHT_QSS.replace("__ARROW_DOWN__", ARROW_DOWN_PATH)
PYGSN_DARK_QSS = PYGSN_DARK_QSS.replace("__ARROW_DOWN__", ARROW_DOWN_LIGHT_PATH)

# Alias por defecto
PYGSN_QSS = PYGSN_LIGHT_QSS


def set_window_titlebar_light(window) -> None:
    """Configura la barra de título nativa de Windows (DWM) en modo claro."""
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import byref, c_int, sizeof
            hwnd = int(window.winId())
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (0 = claro, 1 = oscuro)
            val = c_int(0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(val), sizeof(val))
            # Windows 11 (build 22000+): DWMWA_CAPTION_COLOR = 35, DWMWA_TEXT_COLOR = 36
            bg_color = c_int(0x00FAF9F8)   # BGR para #f8f9fa
            text_color = c_int(0x00292521) # BGR para #212529
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(bg_color), sizeof(bg_color))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, byref(text_color), sizeof(text_color))
        except Exception:
            pass


class LightTitlebarEventFilter(QObject):
    """
    Filtro de eventos global instalado en QApplication que intercepta
    la visualización de ventanas, QMessageBox y diálogos para forzar
    la barra de título clara en Windows 11.
    """
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in (QEvent.Show, QEvent.Polish):
            if isinstance(watched, QWidget) and watched.isWindow():
                set_window_titlebar_light(watched)
        return super().eventFilter(watched, event)


def apply_pyside_theme(app, mode: str = "light") -> None:
    """
    Aplica la hoja de estilos QSS a la aplicación Qt.
    Por defecto aplica el tema claro (mode="light").
    """
    if mode.lower() == "dark":
        app.setStyleSheet(PYGSN_DARK_QSS)
    else:
        app.setStyleSheet(PYGSN_LIGHT_QSS)

    if not hasattr(app, "_light_titlebar_filter"):
        app._light_titlebar_filter = LightTitlebarEventFilter(app)
        app.installEventFilter(app._light_titlebar_filter)



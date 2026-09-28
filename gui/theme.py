"""
PyGSN - GUI Theme and Palette (PySide6 / Qt)
============================================
Estilo visual de alto contraste para ingeniería y fotogrametría/geodesia en PySide6.
"""

from typing import Tuple

# Paleta RGBA pura (Tuplas 0-255)
COLOR_CANVAS_BG: Tuple[int, int, int, int] = (22, 24, 29, 255)
COLOR_GRID_MAJOR: Tuple[int, int, int, int] = (60, 66, 80, 255)
COLOR_GRID_MINOR: Tuple[int, int, int, int] = (35, 38, 46, 255)

# Ejes Body (b-frame) estrictamente RGB:
COLOR_AXIS_X: Tuple[int, int, int, int] = (235, 50, 50, 255)       # Rojo R: +Xb Adelante
COLOR_AXIS_Y: Tuple[int, int, int, int] = (45, 195, 75, 255)      # Verde G: +Yb Derecha
COLOR_AXIS_Z: Tuple[int, int, int, int] = (45, 135, 245, 255)     # Azul B: -Zb Arriba / +Zb Abajo

COLOR_PLATFORM_BODY: Tuple[int, int, int, int] = (0, 180, 216, 200) # Cyan
COLOR_ORIGIN: Tuple[int, int, int, int] = (255, 255, 255, 255)        # Blanco (PLA)
COLOR_CENTROID: Tuple[int, int, int, int] = (255, 183, 3, 255)        # Ámbar / Oro

# Sensores
COLOR_SENSOR_GNSS: Tuple[int, int, int, int] = (255, 209, 102, 255)   # Amarillo
COLOR_SENSOR_INS: Tuple[int, int, int, int] = (6, 214, 160, 255)      # Verde menta
COLOR_SENSOR_CAM: Tuple[int, int, int, int] = (247, 37, 133, 255)     # Rosa intenso
COLOR_SENSOR_DEFAULT: Tuple[int, int, int, int] = (180, 180, 200, 255)

COLOR_TEXT_PRIMARY: Tuple[int, int, int, int] = (230, 235, 245, 255)
COLOR_TEXT_MUTED: Tuple[int, int, int, int] = (140, 150, 165, 255)

# Hoja de estilos Qt (QSS) para una suite de ingeniería oscura y profesional
PYGSN_QSS = """
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

QMenu::separator {
    height: 1px;
    background-color: #3b4252;
    margin: 4px 6px;
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

QToolButton:disabled {
    background-color: #1c1f26;
    color: #6c757d;
    border-color: #282c37;
}

QDockWidget {
    color: #00b4d8;
    font-weight: bold;
    titlebar-close-icon: url(close.png);
    titlebar-normal-icon: url(undock.png);
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

QTreeWidget::item {
    padding: 4px;
    border-radius: 2px;
}

QTreeWidget::item:hover {
    background-color: #242b38;
}

QTreeWidget::item:selected {
    background-color: #1d4e78;
    color: #ffffff;
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
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:hover {
    background-color: #272d38;
    color: #ffffff;
}

QTabBar::tab:selected {
    background-color: #14161b;
    color: #00b4d8;
    font-weight: bold;
    border-top: 2px solid #00b4d8;
}

QTabBar::close-button {
    image: none;
    subcontrol-position: right;
    margin: 2px;
}

QStatusBar {
    background-color: #16181e;
    border-top: 1px solid #2d313d;
    color: #8c96a5;
    font-size: 11px;
}

QPushButton {
    background-color: #285078;
    color: #ffffff;
    border: 1px solid #3b6b9b;
    border-radius: 3px;
    padding: 5px 12px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #336699;
    border-color: #00b4d8;
}

QPushButton:pressed {
    background-color: #1f3f60;
}

QPushButton:disabled {
    background-color: #20242c;
    color: #555e6d;
    border-color: #2d313d;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #21252f;
    border: 1px solid #3b4252;
    border-radius: 3px;
    color: #e6ebf5;
    padding: 4px 6px;
    selection-background-color: #0077b6;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #00b4d8;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #3b4252;
}

QComboBox QAbstractItemView {
    background-color: #21252f;
    border: 1px solid #3b4252;
    selection-background-color: #1d4e78;
    color: #e6ebf5;
}

QScrollBar:vertical {
    border: none;
    background: #16181e;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #3b4252;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #00b4d8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #16181e;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #3b4252;
    min-width: 20px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #00b4d8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QGroupBox {
    border: 1px solid #3b4252;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 12px;
    font-weight: bold;
    color: #00b4d8;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}

QCheckBox, QRadioButton {
    spacing: 6px;
    color: #e6ebf5;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 14px;
    height: 14px;
    background-color: #21252f;
    border: 1px solid #3b4252;
    border-radius: 2px;
}

QCheckBox::indicator:checked {
    background-color: #00b4d8;
    border-color: #90e0ef;
}
"""


def apply_pyside_theme(app) -> None:
    """Aplica la hoja de estilos QSS a la aplicación Qt."""
    app.setStyleSheet(PYGSN_QSS)

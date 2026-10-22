"""
PyGSN - Toast Notification Component (PySide6 / Qt)
===================================================
Notificaciones emergentes no bloqueantes (Toast) para avisos de validación,
éxito de solvers, alertas de importación y diagnósticos operacionales.
"""

from typing import Optional, Literal
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QPushButton,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QColor, QFont


ToastLevel = Literal["info", "warning", "error", "success"]


class ToastNotification(QWidget):
    """Widget de notificación flotante no modal."""

    PALETTE = {
        "info": {
            "border": "#0284c7",
            "accent": "#38bdf8",
            "tag": "INFO",
            "bg": "#0f172a",
        },
        "warning": {
            "border": "#d97706",
            "accent": "#f59e0b",
            "tag": "AVISO",
            "bg": "#0f172a",
        },
        "error": {
            "border": "#dc2626",
            "accent": "#ef4444",
            "tag": "ERROR",
            "bg": "#0f172a",
        },
        "success": {
            "border": "#059669",
            "accent": "#10b981",
            "tag": "ÉXITO",
            "bg": "#0f172a",
        },
    }

    def __init__(
        self,
        message: str,
        title: Optional[str] = None,
        level: ToastLevel = "info",
        duration_ms: int = 3500,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.duration_ms = duration_ms
        theme = self.PALETTE.get(level, self.PALETTE["info"])

        # Atributos de ventana flotante sobre el padre
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(360)

        # Contenedor principal con estilo técnico
        container = QWidget(self)
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(12, 10, 10, 10)
        container_layout.setSpacing(10)

        # Borde lateral de acento de 4px
        container.setStyleSheet(f"""
            QWidget {{
                background-color: {theme['bg']};
                border-left: 4px solid {theme['border']};
                border-top: 1px solid #334155;
                border-right: 1px solid #334155;
                border-bottom: 1px solid #334155;
                border-radius: 6px;
            }}
        """)

        # Sombra sutil
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 90))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        # Layout vertical de textos
        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        text_layout.setContentsMargins(0, 0, 0, 0)

        # Cabecera (Tag y Título)
        header_text = title if title else theme["tag"]
        lbl_title = QLabel(header_text)
        lbl_title.setStyleSheet(f"color: {theme['accent']}; font-weight: 700; font-size: 11px; background: transparent; border: none;")
        text_layout.addWidget(lbl_title)

        # Mensaje descriptivo
        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("color: #f8fafc; font-size: 12px; line-height: 1.3; background: transparent; border: none;")
        text_layout.addWidget(lbl_msg)

        container_layout.addLayout(text_layout, stretch=1)

        # Botón cerrar
        btn_close = QPushButton("×")
        btn_close.setFixedSize(18, 18)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                font-size: 14px;
                font-weight: bold;
                border: none;
                padding: 0;
                margin: 0;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        btn_close.clicked.connect(self.close_animated)
        container_layout.addWidget(btn_close, alignment=Qt.AlignTop)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.addWidget(container)

        # Efecto de opacidad para animación
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        # Animación Fade In
        self.anim_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_in.setDuration(180)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        self.anim_in.setEasingCurve(QEasingCurve.OutCubic)

        # Animación Fade Out
        self.anim_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_out.setDuration(220)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.setEasingCurve(QEasingCurve.InCubic)
        self.anim_out.finished.connect(self.close)

        # Temporizador de auto-cierre
        if duration_ms > 0:
            self.timer = QTimer(self)
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(self.close_animated)

    def show_animated(self, pos: QPoint):
        self.move(pos)
        self.show()
        self.anim_in.start()
        if hasattr(self, "timer"):
            self.timer.start(self.duration_ms)

    def close_animated(self):
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()
        self.anim_out.start()


class ToastManager:
    """Gestiona la pila y posicionamiento de notificaciones en la ventana activa."""

    def __init__(self, parent_window: QWidget):
        self.parent = parent_window
        self.active_toasts: list[ToastNotification] = []

    def show_toast(
        self,
        message: str,
        title: Optional[str] = None,
        level: ToastLevel = "info",
        duration_ms: int = 3500
    ):
        toast = ToastNotification(
            message=message,
            title=title,
            level=level,
            duration_ms=duration_ms,
            parent=self.parent
        )
        self.active_toasts.append(toast)
        toast.destroyed.connect(lambda: self._on_toast_destroyed(toast))
        self._reposition_toasts()
        toast.show_animated(toast.pos())

    def _reposition_toasts(self):
        margin_x = 24
        margin_y = 36  # Espacio sobre la barra de estado
        p_geom = self.parent.geometry()
        cur_y = self.parent.height() - margin_y

        # Posicionar de abajo hacia arriba
        for t in reversed(self.active_toasts):
            t_w = t.width()
            t_h = t.sizeHint().height() if t.sizeHint().isValid() else 70
            t_x = self.parent.width() - t_w - margin_x
            cur_y -= (t_h + 8)
            t.move(t_x, max(cur_y, 10))

    def _on_toast_destroyed(self, toast: ToastNotification):
        if toast in self.active_toasts:
            self.active_toasts.remove(toast)
        self._reposition_toasts()

"""
PyGSN - Hierarchy & Layers Dock (PySide6 / Qt)
==============================================
Panel lateral de capas con árbol jerárquico nativo:
- Clic izquierdo directo sobre la plataforma para abrirla en el Workspace.
- Clic derecho con menú contextual nativo (Abrir, Centrar al Origen, Centrar al Centroide, Añadir Sensor).
- Clic derecho sobre chasis y sensores.
"""

from typing import Callable, Optional
from PySide6.QtWidgets import (
    QDockWidget, QTreeWidget, QTreeWidgetItem, QMenu, QWidget,
    QVBoxLayout, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont

from core.project import Project


class HierarchyDock(QDockWidget):
    """Panel de capas y jerarquía con QTreeWidget nativo."""

    platform_activated = Signal(str)      # plat_id
    chassis_clicked = Signal(str)         # plat_id
    sensor_selected = Signal(str, str)    # plat_id, sensor_code
    center_origin_requested = Signal(str) # plat_id
    center_centroid_requested = Signal(str) # plat_id
    add_sensor_requested = Signal(str)    # plat_id

    def __init__(
        self,
        get_project: Callable[[], Project],
        on_project_changed: Callable[[], None],
        parent: Optional[QWidget] = None
    ):
        super().__init__("Capas / Jerarquía", parent)
        self.get_project = get_project
        self.on_project_changed = on_project_changed

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(260)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        layout.addWidget(self.tree)
        self.setWidget(widget)

    def rebuild_tree(self):
        """Reconstruye el árbol de capas jerárquico: Proyecto -> Plataformas -> Sensores."""
        self.tree.clear()
        proj = self.get_project()

        root = QTreeWidgetItem(self.tree, [f"Proyecto: {proj.name}"])
        root.setData(0, Qt.UserRole, {"type": "project"})
        font_root = root.font(0)
        font_root.setBold(True)
        root.setFont(0, font_root)
        root.setForeground(0, QColor(0, 180, 216))

        if not proj.platforms:
            empty_item = QTreeWidgetItem(root, ["(No hay plataformas cargadas)"])
            empty_item.setForeground(0, QColor(140, 150, 165))
            root.setExpanded(True)
            return

        for plat_id, plat in proj.platforms.items():
            is_active = (plat_id == proj.active_platform_id)
            tag_active = " [*Activa]" if is_active else ""
            type_tag = f"[{plat.platform_type[:4]}]"
            label = f"Plataforma: {plat.name} {type_tag}{tag_active}"

            plat_item = QTreeWidgetItem(root, [label])
            plat_item.setData(0, Qt.UserRole, {"type": "platform", "plat_id": plat_id})
            if is_active:
                f = plat_item.font(0)
                f.setBold(True)
                plat_item.setFont(0, f)
                plat_item.setForeground(0, QColor(255, 209, 102))

            # Chasis
            dim_str = f"({plat.length_m:.2f}x{plat.width_m:.2f}x{plat.height_m:.2f}m)" if plat.has_dimensions else "(libre)"
            chassis_item = QTreeWidgetItem(plat_item, [f"Chasis {dim_str}"])
            chassis_item.setData(0, Qt.UserRole, {"type": "chassis", "plat_id": plat_id})
            chassis_item.setForeground(0, QColor(72, 202, 228))

            # Sensores montados
            n_sens = len(plat.sensors)
            sens_root = QTreeWidgetItem(plat_item, [f"Sensores ({n_sens})"])
            sens_root.setData(0, Qt.UserRole, {"type": "sensors_group", "plat_id": plat_id})
            sens_root.setForeground(0, QColor(180, 190, 205))

            for code, s in plat.sensors.items():
                s_label = f"[*] {code:<6s} [{s.sensor_type.value[:3]}] {s.name}"
                s_item = QTreeWidgetItem(sens_root, [s_label])
                s_item.setData(0, Qt.UserRole, {"type": "sensor", "plat_id": plat_id, "code": code})
                # Colores según tipo
                stype_name = s.sensor_type.value
                if "GNSS" in stype_name:
                    s_item.setForeground(0, QColor(255, 209, 102))
                elif "INS" in stype_name or "IMU" in stype_name:
                    s_item.setForeground(0, QColor(6, 214, 160))
                elif "CAM" in stype_name:
                    s_item.setForeground(0, QColor(247, 37, 133))

            plat_item.setExpanded(True)
            sens_root.setExpanded(True)

        root.setExpanded(True)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        itype = data.get("type")
        plat_id = data.get("plat_id")

        if itype == "platform" and plat_id:
            # Clic directo activa y abre en el Workspace
            proj = self.get_project()
            proj.set_active_platform(plat_id)
            self.platform_activated.emit(plat_id)
        elif itype == "chassis" and plat_id:
            self.chassis_clicked.emit(plat_id)
        elif itype == "sensor" and plat_id:
            code = data.get("code")
            self.sensor_selected.emit(plat_id, code)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        plat_id = data.get("plat_id")
        if plat_id:
            self.platform_activated.emit(plat_id)

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        itype = data.get("type")
        plat_id = data.get("plat_id")
        menu = QMenu(self)

        if itype == "platform" and plat_id:
            act_open = menu.addAction("Abrir en Workspace")
            act_open.triggered.connect(lambda: self.platform_activated.emit(plat_id))

            menu.addSeparator()
            act_origin = menu.addAction("Centrar Vista al Origen [0, 0, 0]")
            act_origin.triggered.connect(lambda: self.center_origin_requested.emit(plat_id))

            act_centroid = menu.addAction("Centrar Vista al Centroide")
            act_centroid.triggered.connect(lambda: self.center_centroid_requested.emit(plat_id))

            menu.addSeparator()
            act_add_sens = menu.addAction("Añadir Sensor al Rig...")
            act_add_sens.triggered.connect(lambda: self.add_sensor_requested.emit(plat_id))

            menu.addSeparator()
            act_del = menu.addAction("Eliminar Plataforma")
            act_del.triggered.connect(lambda: self._delete_platform(plat_id))

        elif itype == "chassis" and plat_id:
            act_origin = menu.addAction("Centrar al Origen [0, 0]")
            act_origin.triggered.connect(lambda: self.center_origin_requested.emit(plat_id))

            act_centroid = menu.addAction("Centrar al Centroide")
            act_centroid.triggered.connect(lambda: self.center_centroid_requested.emit(plat_id))

        elif itype == "sensor" and plat_id:
            code = data.get("code")
            act_del_s = menu.addAction(f"Eliminar Sensor {code}")
            act_del_s.triggered.connect(lambda: self._delete_sensor(plat_id, code))

        menu.exec(self.tree.mapToGlobal(pos))

    def _delete_platform(self, plat_id: str):
        proj = self.get_project()
        plat = proj.get_platform(plat_id)
        if not plat:
            return
        res = QMessageBox.question(
            self, "Confirmar Eliminación",
            f"¿Está seguro de eliminar la plataforma '{plat.name}' y todos sus sensores?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res == QMessageBox.Yes:
            proj.remove_platform(plat_id)
            self.rebuild_tree()
            self.on_project_changed()

    def _delete_sensor(self, plat_id: str, code: str):
        proj = self.get_project()
        plat = proj.get_platform(plat_id)
        if not plat or code not in plat.sensors:
            return
        res = QMessageBox.question(
            self, "Confirmar Eliminación",
            f"¿Está seguro de eliminar el sensor '{code}' de '{plat.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res == QMessageBox.Yes:
            del plat.sensors[code]
            self.rebuild_tree()
            self.on_project_changed()

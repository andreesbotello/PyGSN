"""
PyGSN - Hierarchy & Layers Dock (PySide6 / Qt)
==============================================
Panel lateral de capas con árbol jerárquico nativo:
- Clic izquierdo directo sobre la plataforma para abrirla en el Workspace.
- Clic derecho con menú contextual nativo (Abrir, Centrar al Origen, Centrar al Centroide, Añadir Sensor).
- Clic derecho sobre chasis y sensores.
"""

from pathlib import Path
from typing import Callable, Optional
from PySide6.QtWidgets import (
    QDockWidget, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QMenu, QWidget,
    QVBoxLayout, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QColor, QFont, QIcon

from core.project import Project

ICONS_DIR = Path(__file__).resolve().parent.parent / "icons"


class HierarchyDock(QDockWidget):
    """Panel de capas y jerarquía con QTreeWidget nativo e iconografía vectorial."""

    platform_activated = Signal(str)           # plat_id
    chassis_clicked = Signal(str)              # plat_id (mantenido por compatibilidad)
    sensor_selected = Signal(str, str)         # plat_id, sensor_code
    center_origin_requested = Signal(str)      # plat_id
    center_centroid_requested = Signal(str)    # plat_id
    add_sensor_requested = Signal(str)         # plat_id
    import_sensors_requested = Signal(str)      # plat_id
    platform_properties_requested = Signal(str)# plat_id
    platform_attribute_table_requested = Signal(str) # plat_id
    delete_platform_requested = Signal(str)    # plat_id
    chassis_edit_requested = Signal(str)       # plat_id
    chassis_clear_requested = Signal(str)      # plat_id
    sensor_edit_requested = Signal(str, str)   # plat_id, sensor_code
    sensor_zoom_requested = Signal(str, str)   # plat_id, sensor_code
    sensor_properties_requested = Signal(str, str) # plat_id, sensor_code
    delete_sensor_requested = Signal(str, str) # plat_id, sensor_code

    # Acciones de Plataformas y Sistemas de Referencia Terrestres (SRT)
    create_platform_requested = Signal()
    create_reference_system_requested = Signal()
    reference_system_activated = Signal(str)           # rs_id
    reference_system_selected = Signal(str)            # rs_id
    reference_system_map_requested = Signal(str)       # rs_id
    reference_system_properties_requested = Signal(str)# rs_id
    delete_reference_system_requested = Signal(str)    # rs_id
    platform_zoom_map_requested = Signal(str, str)     # plat_id, rs_id
    layer_visibility_changed = Signal(str, str, bool)   # rs_id, layer_key, is_visible
    n_frame_convention_changed = Signal(str, str)       # rs_id, convention

    def __init__(
        self,
        get_project: Callable[[], Project],
        on_project_changed: Callable[[], None],
        parent: Optional[QWidget] = None
    ):
        super().__init__("Capas", parent)
        self.get_project = get_project
        self.on_project_changed = on_project_changed

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(260)
        self.editing_platform_id: Optional[str] = None
        self.editing_sensor_code: Optional[str] = None

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemChanged.connect(self._on_tree_item_changed)

        layout.addWidget(self.tree)
        self.setWidget(widget)

    def set_editing_context(self, plat_id: Optional[str], sensor_code: Optional[str] = None):
        """Actualiza el contexto de edición para destacar con un '*' la capa en modificación activa."""
        self.editing_platform_id = plat_id
        self.editing_sensor_code = sensor_code
        self.rebuild_tree()

    def rebuild_tree(self):
        """Reconstruye el árbol de capas jerárquico: Proyecto -> Plataformas / Sistemas de Referencia -> Sensores."""
        self.tree.blockSignals(True)
        self.tree.clear()
        proj = self.get_project()

        root = QTreeWidgetItem(self.tree, [f"Proyecto: {proj.name}"])
        root.setData(0, Qt.UserRole, {"type": "project"})
        logo_icon = ICONS_DIR / "Logo.svg"
        if logo_icon.exists():
            root.setIcon(0, QIcon(str(logo_icon)))
        font_root = root.font(0)
        font_root.setBold(True)
        root.setFont(0, font_root)
        root.setForeground(0, QColor(0, 119, 182))

        icon_dron = ICONS_DIR / "Dron.svg"
        icon_chasis = ICONS_DIR / "Chasis.svg"
        icon_sensor = ICONS_DIR / "Sensor.svg"
        icon_gps = ICONS_DIR / "GPS.svg"
        icon_camara = ICONS_DIR / "Camara.svg"
        icon_srt = ICONS_DIR / "SRT.svg"
        if not icon_srt.exists():
            icon_srt = icon_gps

        # Rama 1: Plataformas
        plat_count = len(proj.platforms)
        plat_group = QTreeWidgetItem(root, [f"Plataformas ({plat_count})"])
        plat_group.setData(0, Qt.UserRole, {"type": "platforms_group"})
        if icon_dron.exists():
            plat_group.setIcon(0, QIcon(str(icon_dron)))
        f_plat = plat_group.font(0)
        f_plat.setBold(True)
        plat_group.setFont(0, f_plat)
        plat_group.setForeground(0, QColor(0, 119, 182))

        if not proj.platforms:
            empty_item = QTreeWidgetItem(plat_group, ["(No hay plataformas cargadas)"])
            empty_item.setForeground(0, QColor(108, 117, 125))
        else:
            for plat_id, plat in proj.platforms.items():
                is_active = (plat_id == proj.active_platform_id)
                is_editing_plat = (plat_id == self.editing_platform_id)
                tag_active = " [Activa]" if is_active else ""
                type_tag = f"[{plat.platform_type[:4]}]"
                edit_star = "* " if is_editing_plat else ""
                label = f"{edit_star}Plataforma: {plat.name} {type_tag}{tag_active}"

                plat_item = QTreeWidgetItem(plat_group, [label])
                plat_item.setData(0, Qt.UserRole, {"type": "platform", "plat_id": plat_id})
                if icon_dron.exists():
                    plat_item.setIcon(0, QIcon(str(icon_dron)))
                if is_editing_plat:
                    f = plat_item.font(0)
                    f.setBold(True)
                    plat_item.setFont(0, f)
                    plat_item.setForeground(0, QColor(220, 38, 38)) # Rojo para edición activa
                elif is_active:
                    f = plat_item.font(0)
                    f.setBold(True)
                    plat_item.setFont(0, f)
                    plat_item.setForeground(0, QColor(180, 83, 9))
                else:
                    plat_item.setForeground(0, QColor(30, 41, 59))

                # Chasis
                dim_str = f"({plat.length_m:.2f}x{plat.width_m:.2f}x{plat.height_m:.2f}m)" if plat.has_dimensions else "(libre)"
                chassis_label = f"{'* ' if is_editing_plat else ''}Chasis {dim_str}"
                chassis_item = QTreeWidgetItem(plat_item, [chassis_label])
                chassis_item.setData(0, Qt.UserRole, {"type": "chassis", "plat_id": plat_id})
                if icon_chasis.exists():
                    chassis_item.setIcon(0, QIcon(str(icon_chasis)))
                chassis_item.setForeground(0, QColor(2, 132, 199))

                # Sensores montados
                n_sens = len(plat.sensors)
                sens_root = QTreeWidgetItem(plat_item, [f"Sensores ({n_sens})"])
                sens_root.setData(0, Qt.UserRole, {"type": "sensors_group", "plat_id": plat_id})
                if icon_sensor.exists():
                    sens_root.setIcon(0, QIcon(str(icon_sensor)))
                sens_root.setForeground(0, QColor(71, 85, 105))

                for code, s in plat.sensors.items():
                    is_editing_sens = (plat_id == self.editing_platform_id and code == self.editing_sensor_code)
                    sens_star = "* " if is_editing_sens else ""
                    s_label = f"{sens_star}{s.name} [{s.sensor_type.value[:3]}]"
                    s_item = QTreeWidgetItem(sens_root, [s_label])
                    s_item.setData(0, Qt.UserRole, {"type": "sensor", "plat_id": plat_id, "code": code})
                    if is_editing_sens:
                        f = s_item.font(0)
                        f.setBold(True)
                        s_item.setFont(0, f)

                    # Asignar icono y color de texto contrastado según tipo
                    stype_name = s.sensor_type.value
                    if "GNSS" in stype_name:
                        if icon_gps.exists():
                            s_item.setIcon(0, QIcon(str(icon_gps)))
                        s_item.setForeground(0, QColor(194, 65, 12))
                    elif "CAM" in stype_name:
                        if icon_camara.exists():
                            s_item.setIcon(0, QIcon(str(icon_camara)))
                        s_item.setForeground(0, QColor(219, 39, 119))
                    else:
                        if icon_sensor.exists():
                            s_item.setIcon(0, QIcon(str(icon_sensor)))
                        s_item.setForeground(0, QColor(5, 150, 105))

                plat_item.setExpanded(True)
                sens_root.setExpanded(True)

        # Rama 2: Sistemas de Referencia Terrestres (SRT / e-frame)
        ref_systems = getattr(proj, "reference_systems", {})
        rs_count = len(ref_systems)
        srts_group = QTreeWidgetItem(root, [f"Sistemas de Referencia ({rs_count})"])
        srts_group.setData(0, Qt.UserRole, {"type": "reference_systems_group"})
        if icon_srt.exists():
            srts_group.setIcon(0, QIcon(str(icon_srt)))
        f_rs = srts_group.font(0)
        f_rs.setBold(True)
        srts_group.setFont(0, f_rs)
        srts_group.setForeground(0, QColor(16, 120, 80))

        if not ref_systems:
            empty_rs = QTreeWidgetItem(srts_group, ["(No hay sistemas de referencia configurados)"])
            empty_rs.setForeground(0, QColor(108, 117, 125))
        else:
            for rs_id, rs in ref_systems.items():
                name_part = f": {rs.name}" if rs.name and rs.name != rs.id else ""
                utm_part = f", UTM {rs.utm_zone}{rs.utm_hemisphere}" if rs.utm_zone else ""
                label = f"{rs.id}{name_part} ({rs.ellipsoid}{utm_part})"
                rs_item = QTreeWidgetItem(srts_group, [label])
                rs_item.setData(0, Qt.UserRole, {"type": "reference_system", "rs_id": rs_id})
                if icon_srt.exists():
                    rs_item.setIcon(0, QIcon(str(icon_srt)))
                rs_item.setForeground(0, QColor(16, 120, 80))

                # Subcapa 1: Mapa Base (OpenStreetMap) con checkbox
                basemap_item = QTreeWidgetItem(rs_item, ["Mapa Base (OpenStreetMap)"])
                basemap_item.setData(0, Qt.UserRole, {"type": "srt_basemap", "rs_id": rs_id})
                basemap_item.setFlags(basemap_item.flags() | Qt.ItemIsUserCheckable)
                basemap_item.setCheckState(0, Qt.Checked if getattr(rs, "show_basemap", True) else Qt.Unchecked)
                basemap_item.setForeground(0, QColor(71, 85, 105))

                # Subcapas de plataformas georreferenciadas bajo este SRT
                for plat_id, plat in proj.platforms.items():
                    if plat.pose_e and plat.pose_e.ref_system_id == rs_id:
                        s_plat_item = QTreeWidgetItem(rs_item, [f"Plataforma: {plat.name} (Georreferenciada)"])
                        s_plat_item.setData(0, Qt.UserRole, {"type": "srt_platform", "rs_id": rs_id, "plat_id": plat_id})
                        s_plat_item.setFlags(s_plat_item.flags() | Qt.ItemIsUserCheckable)
                        s_plat_item.setCheckState(0, Qt.Checked)
                        if icon_dron.exists():
                            s_plat_item.setIcon(0, QIcon(str(icon_dron)))
                        s_plat_item.setForeground(0, QColor(2, 132, 199))

                        # Chasis
                        dim_str = f"({plat.length_m:.2f}x{plat.width_m:.2f}m)" if plat.has_dimensions else ""
                        ch_item = QTreeWidgetItem(s_plat_item, [f"Chasis {dim_str}".strip()])
                        ch_item.setData(0, Qt.UserRole, {"type": "srt_chassis", "rs_id": rs_id, "plat_id": plat_id})
                        ch_item.setFlags(ch_item.flags() | Qt.ItemIsUserCheckable)
                        ch_item.setCheckState(0, Qt.Checked)
                        if icon_chasis.exists():
                            ch_item.setIcon(0, QIcon(str(icon_chasis)))
                        ch_item.setForeground(0, QColor(71, 85, 105))

                        # Sensores
                        sens_group_item = QTreeWidgetItem(s_plat_item, [f"Sensores ({len(plat.sensors)})"])
                        sens_group_item.setData(0, Qt.UserRole, {"type": "srt_sensors_group", "rs_id": rs_id, "plat_id": plat_id})
                        sens_group_item.setFlags(sens_group_item.flags() | Qt.ItemIsUserCheckable)
                        sens_group_item.setCheckState(0, Qt.Checked)
                        if icon_sensor.exists():
                            sens_group_item.setIcon(0, QIcon(str(icon_sensor)))
                        sens_group_item.setForeground(0, QColor(71, 85, 105))

                        for scode, s in plat.sensors.items():
                            stag = f"[{s.sensor_type.value[:3]}]"
                            s_node = QTreeWidgetItem(sens_group_item, [f"{s.name} {stag}"])
                            s_node.setData(0, Qt.UserRole, {"type": "srt_sensor", "rs_id": rs_id, "plat_id": plat_id, "code": scode})
                            s_node.setFlags(s_node.flags() | Qt.ItemIsUserCheckable)
                            s_node.setCheckState(0, Qt.Checked)
                            stype_name = s.sensor_type.value
                            if "GNSS" in stype_name and icon_gps.exists():
                                s_node.setIcon(0, QIcon(str(icon_gps)))
                            elif "CAM" in stype_name and icon_camara.exists():
                                s_node.setIcon(0, QIcon(str(icon_camara)))
                            elif icon_sensor.exists():
                                s_node.setIcon(0, QIcon(str(icon_sensor)))
                            s_node.setForeground(0, QColor(71, 85, 105))

                        # Terna n-frame
                        nframe_item = QTreeWidgetItem(s_plat_item, ["Terna n-frame"])
                        nframe_item.setData(0, Qt.UserRole, {"type": "srt_n_frame", "rs_id": rs_id, "plat_id": plat_id})
                        nframe_item.setFlags(nframe_item.flags() | Qt.ItemIsUserCheckable)
                        nframe_item.setCheckState(0, Qt.Checked)
                        nframe_item.setForeground(0, QColor(71, 85, 105))

                        s_plat_item.setExpanded(True)
                        sens_group_item.setExpanded(True)

                rs_item.setExpanded(True)

        plat_group.setExpanded(True)
        srts_group.setExpanded(True)
        root.setExpanded(True)
        self.tree.blockSignals(False)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        itype = data.get("type")
        plat_id = data.get("plat_id")
        rs_id = data.get("rs_id")

        if itype == "platform" and plat_id:
            proj = self.get_project()
            proj.set_active_platform(plat_id)
            self.platform_activated.emit(plat_id)
        elif itype == "chassis" and plat_id:
            proj = self.get_project()
            proj.set_active_platform(plat_id)
            self.platform_activated.emit(plat_id)
        elif itype == "sensor" and plat_id:
            code = data.get("code")
            self.sensor_selected.emit(plat_id, code)
        elif itype == "reference_system" and rs_id:
            self.reference_system_selected.emit(rs_id)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        itype = data.get("type")
        plat_id = data.get("plat_id")
        rs_id = data.get("rs_id")
        if itype in ("srt_platform", "srt_chassis", "srt_sensors_group", "srt_sensor", "srt_n_frame") and plat_id and rs_id:
            self.platform_zoom_map_requested.emit(plat_id, rs_id)
        elif plat_id:
            self.platform_activated.emit(plat_id)
        elif itype == "reference_system" and rs_id:
            self.reference_system_map_requested.emit(rs_id)

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        itype = data.get("type")
        rs_id = data.get("rs_id")
        is_checked = (item.checkState(0) == Qt.Checked)

        if itype == "srt_basemap" and rs_id:
            proj = self.get_project()
            rs = proj.reference_systems.get(rs_id)
            if rs:
                rs.show_basemap = is_checked
            self.layer_visibility_changed.emit(rs_id, "basemap", is_checked)

        elif itype == "srt_platform" and rs_id:
            plat_id = data.get("plat_id")
            self.layer_visibility_changed.emit(rs_id, f"plat_{plat_id}", is_checked)
            self.tree.blockSignals(True)
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, item.checkState(0))
            self.tree.blockSignals(False)

        elif itype == "srt_chassis" and rs_id:
            plat_id = data.get("plat_id")
            self.layer_visibility_changed.emit(rs_id, f"chassis_{plat_id}", is_checked)

        elif itype == "srt_sensors_group" and rs_id:
            plat_id = data.get("plat_id")
            self.layer_visibility_changed.emit(rs_id, f"sensors_{plat_id}", is_checked)
            self.tree.blockSignals(True)
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, item.checkState(0))
            self.tree.blockSignals(False)

        elif itype == "srt_sensor" and rs_id:
            plat_id = data.get("plat_id")
            code = data.get("code")
            self.layer_visibility_changed.emit(rs_id, f"sensor_{plat_id}_{code}", is_checked)

        elif itype == "srt_n_frame" and rs_id:
            plat_id = data.get("plat_id")
            self.layer_visibility_changed.emit(rs_id, f"n_frame_{plat_id}", is_checked)

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        self.tree.setCurrentItem(item)
        item.setSelected(True)
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        itype = data.get("type")
        plat_id = data.get("plat_id")
        rs_id = data.get("rs_id")
        if itype == "sensor" and plat_id:
            code = data.get("code")
            self.sensor_selected.emit(plat_id, code)
        elif itype == "reference_system" and rs_id:
            self.reference_system_selected.emit(rs_id)

        menu = QMenu(self)

        if itype == "platforms_group":
            act_new_plat = menu.addAction("Nueva Plataforma...")
            act_new_plat.triggered.connect(self.create_platform_requested.emit)

        elif itype == "reference_systems_group":
            act_new_rs = menu.addAction("Nuevo Sistema de Referencia...")
            act_new_rs.triggered.connect(self.create_reference_system_requested.emit)

        elif itype == "reference_system" and rs_id:
            act_map = menu.addAction("Abrir Mapa (e-frame)")
            act_map.triggered.connect(lambda: self.reference_system_map_requested.emit(rs_id))
            menu.addSeparator()
            act_props = menu.addAction("Propiedades...")
            act_props.triggered.connect(lambda: self.reference_system_properties_requested.emit(rs_id))
            menu.addSeparator()
            act_del_rs = menu.addAction("Eliminar")
            act_del_rs.triggered.connect(lambda: self.delete_reference_system_requested.emit(rs_id))

        elif itype == "srt_platform" and plat_id:
            act_zoom_plat = menu.addAction("Hacer Zoom a Plataforma")
            act_zoom_plat.triggered.connect(lambda: self.platform_zoom_map_requested.emit(plat_id, rs_id))
            menu.addSeparator()
            act_attr = menu.addAction("Tabla de Atributos (F6)")
            act_attr.triggered.connect(lambda: self.platform_attribute_table_requested.emit(plat_id))

        elif itype == "srt_n_frame" and plat_id:
            act_ned = menu.addAction("Convención: NED (Inercial GSN)")
            act_ned.triggered.connect(lambda: self.n_frame_convention_changed.emit(rs_id, "NED"))
            act_enu = menu.addAction("Convención: ENU (Topocéntrico GeoTop)")
            act_enu.triggered.connect(lambda: self.n_frame_convention_changed.emit(rs_id, "ENU"))

        elif itype == "platform" and plat_id:
            act_open = menu.addAction("Abrir Workspace")
            act_open.triggered.connect(lambda: self.platform_activated.emit(plat_id))

            menu.addSeparator()
            act_origin = menu.addAction("Centrar en Origen")
            act_origin.triggered.connect(lambda: self.center_origin_requested.emit(plat_id))

            act_centroid = menu.addAction("Centrar en Centroide")
            act_centroid.triggered.connect(lambda: self.center_centroid_requested.emit(plat_id))

            menu.addSeparator()
            menu_sens = menu.addMenu("Añadir Sensores")
            act_add_zero = menu_sens.addAction("Nuevo Sensor...")
            act_add_zero.triggered.connect(lambda: self.add_sensor_requested.emit(plat_id))
            act_add_file = menu_sens.addAction("Importar Sensores...")
            act_add_file.triggered.connect(lambda: self.import_sensors_requested.emit(plat_id))

            act_props = menu.addAction("Propiedades...")
            act_props.triggered.connect(lambda: self.platform_properties_requested.emit(plat_id))

            act_attr_table = menu.addAction("Tabla de Atributos (F6)")
            act_attr_table.triggered.connect(lambda: self.platform_attribute_table_requested.emit(plat_id))

            menu.addSeparator()
            act_del = menu.addAction("Eliminar")
            act_del.triggered.connect(lambda: self.delete_platform_requested.emit(plat_id))

        elif itype == "chassis" and plat_id:
            act_edit = menu.addAction("Editar")
            act_edit.triggered.connect(lambda: self.chassis_edit_requested.emit(plat_id))

            menu.addSeparator()
            act_origin = menu.addAction("Centrar en Origen")
            act_origin.triggered.connect(lambda: self.center_origin_requested.emit(plat_id))

            act_centroid = menu.addAction("Centrar en Centroide")
            act_centroid.triggered.connect(lambda: self.center_centroid_requested.emit(plat_id))

            menu.addSeparator()
            act_clear = menu.addAction("Limpiar")
            act_clear.triggered.connect(lambda: self.chassis_clear_requested.emit(plat_id))

        elif itype == "sensors_group" and plat_id:
            menu_create = menu.addMenu("Añadir Sensores")
            act_zero = menu_create.addAction("Nuevo Sensor...")
            act_zero.triggered.connect(lambda: self.add_sensor_requested.emit(plat_id))
            act_file = menu_create.addAction("Importar Sensores...")
            act_file.triggered.connect(lambda: self.import_sensors_requested.emit(plat_id))

        elif itype == "sensor" and plat_id:
            code = data.get("code")
            act_edit = menu.addAction("Editar")
            act_edit.triggered.connect(lambda: self.sensor_edit_requested.emit(plat_id, code))

            act_zoom = menu.addAction("Centrar en Sensor")
            act_zoom.triggered.connect(lambda: self.sensor_zoom_requested.emit(plat_id, code))

            act_props = menu.addAction("Propiedades...")
            act_props.triggered.connect(lambda: self.sensor_properties_requested.emit(plat_id, code))

            menu.addSeparator()
            act_del_s = menu.addAction("Eliminar")
            act_del_s.triggered.connect(lambda: self.delete_sensor_requested.emit(plat_id, code))

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

    def get_selected_sensor_code(self) -> Optional[str]:
        """Devuelve el código del sensor seleccionado en el árbol de capas, o None."""
        item = self.tree.currentItem()
        if item:
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "sensor":
                return data.get("code")
        return None

    def select_sensor_item(self, sensor_code: Optional[str]):
        """Selecciona y resalta el nodo del sensor correspondiente en el árbol."""
        if not sensor_code:
            return
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "sensor" and data.get("code") == sensor_code:
                self.tree.setCurrentItem(item)
                item.setSelected(True)
                return
            it += 1

    def set_basemap_checked(self, rs_id: str, checked: bool):
        """Actualiza el estado de la casilla del mapa base bajo el SRT indicado sin disparar bucle de señales."""
        it = QTreeWidgetItemIterator(self.tree)
        self.tree.blockSignals(True)
        try:
            while it.value():
                item = it.value()
                data = item.data(0, Qt.UserRole)
                if data and data.get("type") == "srt_basemap" and data.get("rs_id") == rs_id:
                    item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                    break
                it += 1
        finally:
            self.tree.blockSignals(False)

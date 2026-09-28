"""
PyGSN - Hierarchy & Layers Panel
================================
Panel lateral (~280 px) con vista en arbol limpia de los elementos del proyecto (Capas):
- Arbol jerarquico de Proyecto y Plataformas.
- Evento de clic izquierdo directo sobre la plataforma para abrirla en el Workspace.
- Evento sobre el chasis para abrir ventana de acciones (Centrar al Origen, Centrar al Centroide).
"""

from typing import Callable
import dearpygui.dearpygui as dpg

from core.project import Project


class HierarchyPanel:
    """Panel de capas y arbol del proyecto."""

    def __init__(
        self,
        get_project: Callable[[], Project],
        on_update_callback: Callable[[], None],
        on_add_sensor_click: Callable[[], None],
        get_obs_count: Callable[[], int] | None = None,
        on_open_platform_tab: Callable[[str], None] | None = None,
        on_chassis_click: Callable[[str], None] | None = None
    ):
        self.get_project = get_project
        self.on_update = on_update_callback
        self.on_add_sensor_click = on_add_sensor_click
        self.get_obs_count = get_obs_count or (lambda: 0)
        self.on_open_platform_tab = on_open_platform_tab
        self.on_chassis_click = on_chassis_click
        self.selected_platform_id: str | None = None

    def build_ui(self, parent_tag: str):
        with dpg.group(parent=parent_tag):
            # Cabecera del panel de capas
            with dpg.group(horizontal=True):
                dpg.add_text("Capas / Jerarquia", color=(0, 180, 216, 255))

            dpg.add_separator()
            dpg.add_spacer(height=3)

            # Contenedor limpio para el arbol que ocupa todo el alto disponible
            with dpg.child_window(height=-1, border=False, tag="child_hierarchy_tree"):
                self.rebuild_tree()

    def rebuild_tree(self):
        """Reconstruye el arbol de capas: Proyecto -> Plataformas -> Sensores."""
        if not dpg.does_item_exist("child_hierarchy_tree"):
            return
        dpg.delete_item("child_hierarchy_tree", children_only=True)
        proj = self.get_project()

        with dpg.tree_node(label=f"Proyecto: {proj.name}", default_open=True, parent="child_hierarchy_tree"):
            if not proj.platforms:
                dpg.add_text("  (No hay plataformas cargadas)", color=(140, 150, 165, 255))
                dpg.add_text("  Cree una con Plataforma -> Crear", color=(100, 110, 125, 255))
                return

            for plat_id, plat in proj.platforms.items():
                is_active = (plat_id == proj.active_platform_id)
                tag_active = " [*Activa]" if is_active else ""
                type_tag = f"[{plat.platform_type[:4]}]"
                label_plat = f"Plataforma: {plat.name} {type_tag}{tag_active}"

                with dpg.tree_node(label=label_plat, default_open=True):
                    # Clic directo para abrir la plataforma en el Workspace
                    dpg.add_selectable(
                        label="  [>] Abrir / Activar en Workspace",
                        default_value=is_active,
                        user_data=plat_id,
                        callback=lambda s, a, u: self._cb_open_platform(u)
                    )

                    # Chasis: Clic abre dialogo de centrado / acciones
                    dim_str = f"({plat.length_m:.2f}x{plat.width_m:.2f}x{plat.height_m:.2f}m)" if plat.has_dimensions else "(libre)"
                    dpg.add_selectable(
                        label=f"  [-] Chasis {dim_str}",
                        user_data=plat_id,
                        callback=lambda s, a, u: self._cb_on_chassis_click(u)
                    )

                    # Sensores Montados en esta Plataforma
                    n_sens = len(plat.sensors)
                    if n_sens > 0:
                        with dpg.tree_node(label=f"Sensores ({n_sens})", default_open=True):
                            for code, s in plat.sensors.items():
                                s_type_tag = f"[{s.sensor_type.value[:3]}]"
                                dpg.add_text(f"    [*] {code:<6s} {s_type_tag} {s.name}", color=(180, 190, 205, 255))
                    else:
                        dpg.add_text("    (Sin sensores montados)", color=(120, 130, 145, 255))

    def _cb_open_platform(self, plat_id: str):
        proj = self.get_project()
        proj.set_active_platform(plat_id)
        self.selected_platform_id = plat_id
        self.rebuild_tree()
        self.on_update()
        if self.on_open_platform_tab:
            self.on_open_platform_tab(plat_id)

    def _cb_on_chassis_click(self, plat_id: str):
        proj = self.get_project()
        proj.set_active_platform(plat_id)
        if self.on_chassis_click:
            self.on_chassis_click(plat_id)

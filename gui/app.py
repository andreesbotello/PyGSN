"""
PyGSN - GUI Application Orchestrator
===================================
Punto de union de la interfaz grafica:
- Viewport de alta definicion (1280 x 780)
- Separacion en Panel de Control (Izquierda) y 3 Vistas Ortogonales 2D (Derecha)
- Enlace reactivo entre editor de vehiculo y lienzo de dibujo
"""

import dearpygui.dearpygui as dpg

from core.georeferencing import create_reference_platform
from gui.theme import apply_pygsn_theme
from gui.views_ortho import OrthoViewCanvas
from gui.editor import PlatformEditor
from gui.panel_georeferencing import GeoreferencingPanel


class PyGSNApp:
    """Aplicacion principal DearPyGui para PyGSN."""

    def __init__(self):
        self.platform = create_reference_platform()
        self.canvas: OrthoViewCanvas | None = None
        self.editor: PlatformEditor | None = None
        self.panel_georef: GeoreferencingPanel | None = None

    def on_platform_changed(self):
        """Callback ejecutado cuando se modifica la geometria o sensores de la plataforma."""
        if self.canvas:
            self.canvas.redraw_all()

    def run(self):
        dpg.create_context()
        apply_pygsn_theme()

        # Viewport de DearPyGui
        dpg.create_viewport(title="PyGSN - Guiado, Sensores y Navegación [UPV 2026]",
                             width=1320, height=800, min_width=1100, min_height=700)
        dpg.setup_dearpygui()

        self.canvas = OrthoViewCanvas(self.platform)
        self.editor = PlatformEditor(self.platform, on_update_callback=self.on_platform_changed)
        self.panel_georef = GeoreferencingPanel(self.platform)

        with dpg.window(label="PyGSN Workspace", tag="main_window", no_title_bar=True, no_move=True):
            # Barra de navegacion superior
            with dpg.group(horizontal=True):
                dpg.add_text(" PyGSN ", color=(0, 180, 216, 255))
                dpg.add_text("| Sistema Universal de Transformación de Coordenadas y Rig de Sensores")
                dpg.add_spacer(width=200)
                dpg.add_text("Convención: Jekeli / Hoffmann / GSN-UPV", color=(140, 150, 165, 255))
            dpg.add_separator()

            # Layout horizontal en dos columnas principales
            with dpg.group(horizontal=True):
                # COLUMNA IZQUIERDA: Paneles de Control y Datos (ancho ~530 px)
                with dpg.child_window(width=530, height=-1, border=True):
                    with dpg.tab_bar():
                        with dpg.tab(label="Georreferenciación & Navegación", tag="tab_georef"):
                            self.panel_georef.build_ui("tab_georef")

                        with dpg.tab(label="Modelado de Plataforma (Rig)", tag="tab_editor"):
                            self.editor.build_ui("tab_editor")

                        with dpg.tab(label="Ayuda & Metodología"):
                            dpg.add_text("Metodología de Trabajo GSN (UPV)", color=(0, 180, 216, 255))
                            dpg.add_text("""
Este software implementa la georreferenciacion rigurosa de sensores y
transformacion entre los 5 marcos de referencia:
  1. i-frame (Inercial / ECI)
  2. e-frame (Terrestre / ECEF - ETRS89 / GRS80)
  3. n-frame (Navegacion Local / NED)
  4. b-frame (Cuerpo / Body de la plataforma)
  5. s-frame (Sensor con desalineamiento y palanca)

Características Principales:
- Núcleo matemático puro en NumPy (float64) desacoplado de la GUI.
- Algoritmo de Procrustes Ortogonal (Kabsch / SVD) para actitud Cb2n.
- Vistas técnicas ortogonales 2D (Planta, Perfil, Alzado) sobre papel CAD.
- Exportación automática del fichero de entrega paso a paso en texto plano.
                            """)

                # COLUMNA DERECHA: 3 Vistas Ortogonales 2D (ancho restante)
                with dpg.child_window(width=-1, height=-1, border=True):
                    # Barra de herramientas del lienzo
                    with dpg.group(horizontal=True):
                        dpg.add_text("Lienzo de Montaje (3 Vistas Ortogonales 2D):", color=(0, 180, 216, 255))
                        dpg.add_spacer(width=20)
                        dpg.add_text("Escala Zoom:")
                        dpg.add_slider_float(default_value=260.0, min_value=100.0, max_value=600.0,
                                             width=140, callback=lambda s, a: self.canvas.set_zoom(a))
                        dpg.add_button(label="Reset Vista", callback=lambda: self.canvas.set_zoom(260.0))
                    dpg.add_separator()

                    # Distribucion de las 3 vistas en cuadricula
                    with dpg.group(horizontal=True):
                        # Vista Superior
                        with dpg.group():
                            dpg.add_text("1. VISTA SUPERIOR (Planta) [Xb Adelante vs Yb Derecha]")
                            with dpg.child_window(width=360, height=310, border=True):
                                dpg.add_drawlist(width=350, height=300, tag=self.canvas.tag_draw_top)

                        # Vista Lateral
                        with dpg.group():
                            dpg.add_text("2. VISTA LATERAL (Perfil) [Xb Adelante vs -Zb Arriba]")
                            with dpg.child_window(width=360, height=310, border=True):
                                dpg.add_drawlist(width=350, height=300, tag=self.canvas.tag_draw_side)

                    with dpg.group(horizontal=True):
                        # Vista Frontal
                        with dpg.group():
                            dpg.add_text("3. VISTA FRONTAL (Alzado) [Yb Derecha vs -Zb Arriba]")
                            with dpg.child_window(width=360, height=310, border=True):
                                dpg.add_drawlist(width=350, height=300, tag=self.canvas.tag_draw_front)

                        # Panel de Leyenda y Ejes
                        with dpg.group():
                            dpg.add_text("Leyenda de Coordenadas y Triedros:")
                            with dpg.child_window(width=360, height=310, border=True):
                                dpg.add_text("Ejes Cartesianos del Body (b-frame):")
                                dpg.add_text("  ■ Eje Xb (Adelante / Longitudinal)", color=(230, 57, 70, 255))
                                dpg.add_text("  ■ Eje Yb (Derecha / Transversal)", color=(42, 157, 143, 255))
                                dpg.add_text("  ■ Eje Zb (Abajo / Vertical)", color=(69, 123, 157, 255))
                                dpg.add_separator()
                                dpg.add_text("Dispositivos:")
                                dpg.add_text("  ● Origen Plataforma (PLA)", color=(255, 255, 255, 255))
                                dpg.add_text("  ● Antenas GNSS (REC2-5)", color=(255, 209, 102, 255))
                                dpg.add_text("  ● Sensor INS (SBG Ellipse)", color=(6, 214, 160, 255))
                                dpg.add_text("  ● Cámaras Fotográficas", color=(247, 37, 133, 255))
                                dpg.add_separator()
                                dpg.add_text("Cuadrícula Técnica:")
                                dpg.add_text("  - Líneas finas cada 10 cm (0.1 m)")
                                dpg.add_text("  - Líneas gruesas cada 50 cm (0.5 m)")

        # Redimensionar main_window al tamaño del viewport
        dpg.set_primary_window("main_window", True)
        dpg.show_viewport()

        # Dibujar por primera vez
        self.canvas.redraw_all()

        dpg.start_dearpygui()
        dpg.destroy_context()

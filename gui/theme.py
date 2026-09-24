"""
PyGSN - GUI Theme and Color Palette
===================================
Tema visual de alto contraste y estetica tecnica moderna para DearPyGui.
"""

import dearpygui.dearpygui as dpg

# Paleta de Colores para Dibujo Tecnico 2D
COLOR_CANVAS_BG = (22, 24, 29, 255)
COLOR_GRID_MAJOR = (55, 60, 72, 255)
COLOR_GRID_MINOR = (35, 38, 46, 255)
COLOR_AXIS_X = (230, 57, 70, 255)       # Rojo (Adelante / Longitudinal)
COLOR_AXIS_Y = (42, 157, 143, 255)      # Verde (Derecha / Transversal)
COLOR_AXIS_Z = (69, 123, 157, 255)      # Azul (Vertical / Altura)
COLOR_PLATFORM_BODY = (0, 180, 216, 200) # Cyan para el chasis
COLOR_ORIGIN = (255, 255, 255, 255)     # Blanco (PLA)
COLOR_CENTROID = (255, 183, 3, 255)     # Ambar / Oro (CENT)

# Colores por Tipo de Sensor
COLOR_SENSOR_GNSS = (255, 209, 102, 255)   # Amarillo
COLOR_SENSOR_INS = (6, 214, 160, 255)      # Verde Menta
COLOR_SENSOR_CAM = (247, 37, 133, 255)     # Rosa Intenso
COLOR_SENSOR_DEFAULT = (180, 180, 200, 255)

COLOR_TEXT_PRIMARY = (230, 235, 245, 255)
COLOR_TEXT_MUTED = (140, 150, 165, 255)


def apply_pygsn_theme():
    """Aplica el tema oscuro tecnico a toda la aplicacion DearPyGui."""
    with dpg.theme() as theme_id:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (26, 28, 35, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (20, 22, 28, 255))
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, (30, 33, 42, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border, (50, 55, 68, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (35, 38, 48, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (50, 55, 70, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (65, 72, 92, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (18, 20, 25, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (32, 36, 46, 255))
            dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, (22, 24, 30, 255))
            
            # Botones
            dpg.add_theme_color(dpg.mvThemeCol_Button, (40, 80, 120, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (50, 105, 155, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (60, 130, 190, 255))
            
            # Pestanas / Tabs
            dpg.add_theme_color(dpg.mvThemeCol_Tab, (30, 34, 44, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (45, 52, 68, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TabActive, (50, 90, 140, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TabUnfocused, (25, 28, 36, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TabUnfocusedActive, (35, 40, 52, 255))

            # Headers
            dpg.add_theme_color(dpg.mvThemeCol_Header, (40, 60, 85, 255))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (50, 75, 110, 255))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (60, 90, 130, 255))

            # Separadores y sliders
            dpg.add_theme_color(dpg.mvThemeCol_Separator, (55, 62, 78, 255))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (0, 180, 216, 255))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (72, 202, 228, 255))
            
            # Estilos
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 6.0)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 4.0)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4.0)
            dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 4.0)
            dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 4.0)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8.0, 5.0)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8.0, 6.0)

    dpg.bind_theme(theme_id)
    return theme_id

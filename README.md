# PyGSN — Sistema de Transformación de Coordenadas y Georreferenciación de Sensores

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Course](https://img.shields.io/badge/UPV-Sistemas%20de%20Navegaci%C3%B3n%20(S3)-red.svg)](https://www.upv.es/)

Herramienta computacional modular de alta precisión para la transformación rigurosa entre sistemas de referencia inerciales, terrestres y de plataforma, y la georreferenciación y calibración de rigs multisensor (GNSS, IMU/INS, Cámaras, LiDAR). Desarrollada en el marco de la asignatura **Sistemas de Navegación (S3)** del Máster en Ingeniería Geomática y Geoinformación de la **Universitat Politècnica de València (UPV)**.

---

## Guía Rápida de Ejecución

El proyecto está diseñado para ejecutarse **de inmediato sin configuración manual ni alteración del entorno global** del sistema:

### Opción A: Lanzamiento en 1 Clic (Windows)
1. Descargue o clone el repositorio de GitHub.
2. Haga **doble clic en `run.bat`**.
   - *El script detecta Python, crea automáticamente un entorno virtual aislado (`.venv`), instala las dependencias (`numpy`, `scipy`, `dearpygui`) y abre la interfaz gráfica.*

### Opción B: Ejecución Directa por Terminal (Modo CLI sin GUI)
Si se requiere procesar por lotes o en entornos headless sin interfaz gráfica:
```bash
python main.py --run --body data/calibracion_vehiculo.txt --output output/Informe_Georreferenciacion.txt
```
*Calcula las transformaciones cinemáticas, la actitud $C_b^n$ por SVD de Kabsch, la propagación a ECEF, Geodésicas y UTM Huso 30 con altitudes ortométricas, y genera el informe técnico tabular paso a paso.*

### Opción C: Ejecución de Tests de Validación Numérica
```bash
python main.py --test
```
*Verifica que las soluciones coinciden exactamente con los algoritmos y datos de referencia.*

---

## Marcos de Referencia Soportados

El software modela la cinemática y la geometría de los 5 marcos de referencia:

```
  [ i-frame ]  (Inercial / ECI: Origen geocéntrico, ejes fijos a estrellas)
       ▲
       │ C_e^i(ω_ie · t)
       ▼
  [ e-frame ]  (Terrestre / ECEF: ETRS89 / GRS80, rota con la Tierra)
       ▲
       │ C_n^e(φ, λ)
       ▼
  [ n-frame ]  (Navegación Local: NED - Norte, Este, Down)
       ▲
       │ C_b^n(roll, pitch, yaw)  [Convención Jekeli / Hoffmann]
       ▼
  [ b-frame ]  (Cuerpo / Body: Solidario a la plataforma del vehículo)
       ▲
       │ C_s^b(α, β, γ)  [Misalignment de montaje / Boresight]
       ▼
  [ s-frame ]  (Sensor: Ejes propios del dispositivo GNSS, INS, Cámara)
```

---

## Interfaz Gráfica: 3 Vistas Ortogonales 2D Técnicas (DearPyGui)

Siguiendo principios de diseño CAD y dibujo técnico, **no se utiliza renderizado 3D perspectivo**, garantizando máxima precisión visual y rapidez:

1. **Vista Superior (Planta / Top-down)**: Plano $X_b$ (Adelante) vs $Y_b$ (Derecha).
2. **Vista Lateral (Perfil / Side)**: Plano $X_b$ (Adelante) vs $-Z_b$ (Arriba / Cota).
3. **Vista Frontal (Alzado / Front)**: Plano $Y_b$ (Derecha) vs $-Z_b$ (Arriba / Cota).

### Características del Rig Builder:
- Cuadrícula milimetrada interactiva con líneas secundarias cada 10 cm y principales cada 50 cm.
- Marcadores de sensores con su código identificativo y triedro cartesiano miniatura RGB reflejando los ángulos de desalineamiento de montaje.
- Constructor universal: permite modelar vehículos terrestres, drones multirotor, aeronaves o rigs de laboratorio de cualquier dimensión.
- Guardado y carga de configuraciones de plataforma tanto en formato JSON como en texto plano `.txt`.

---

## Estructura del Repositorio

```
PyGSN/
├── core/                        # Núcleo matemático puro (CERO dependencias de GUI)
│   ├── geodesy.py               # Elipsoides GRS80/WGS84, ECEF <-> Geodésicas, UTM H30
│   ├── rotations.py             # Matrices DCM, Euler (r,p,y), misalignment, declinación
│   ├── alignment.py             # Algoritmo de Procrustes Ortogonal (SVD de Kabsch)
│   ├── models.py                # Clases Sensor y Platform para rigs universales (.txt / .json)
│   ├── georeferencing.py        # Motor de georreferenciación y actitud multi-sensor
│   └── reporting.py             # Generador de informes técnicos paso a paso (.txt)
├── gui/                         # Capa de Interfaz Gráfica (DearPyGui)
│   ├── theme.py                 # Paleta oscura técnica de alto contraste
│   ├── views_ortho.py           # Lienzo de las 3 vistas ortogonales 2D sobre grid
│   ├── editor.py                # Panel para dimensionar plataforma y añadir sensores
│   ├── panel_georeferencing.py  # Panel de georreferenciación, observaciones y visor TXT
│   └── app.py                   # Ensamblador del viewport y ventana principal
├── data/                        # Ficheros de calibración y observaciones de prueba
│   ├── calibracion_vehiculo.txt # Calibración geométrica del chasis y sensores en b-frame
│   └── observaciones_sensores.txt # Observaciones geodésicas GNSS e inerciales INS
├── tests/                       # Pruebas unitarias de validación cruzada
│   └── test_georeferencing.py   # Validación de algoritmos y consistencia numérica
├── scripts/
│   └── build_exe.py             # Script para compilar ejecutable standalone con PyInstaller
├── main.py                      # Punto de entrada universal (CLI / GUI / Tests)
├── requirements.txt             # Dependencias de Python (NumPy, SciPy, DearPyGui)
├── pyproject.toml               # Configuración de paquete pip estándar
├── run.bat                      # Lanzador de 1 clic para Windows
├── run.sh                       # Lanzador de 1 clic para Linux/macOS
└── LICENSE                      # Licencia GNU General Public License v3
```

---

## Formato del Fichero de Salida (Reporte Técnico de Georreferenciación)

Al ejecutar la resolución (vía GUI o CLI), se genera un fichero `.txt` con formato tabular riguroso que incluye:
- Metadatos del cálculo, fecha, elipsoide de referencia (GRS80/WGS84) y parámetros geodésicos.
- Coordenadas geodésicas y ECEF de cada receptor GNSS.
- Centroide del sistema y cálculo de la matriz $C_e^n$.
- Matriz de covarianza cruzada $H$ y descomposición en valores singulares SVD.
- Matriz de actitud de la plataforma $C_b^n$ y ángulos $(\text{roll}, \text{pitch}, \text{yaw})$.
- Coordenadas geocéntricas y geodésicas del origen de la plataforma ($\text{PLA}$).
- Tabla completa de coordenadas para todos los dispositivos en los 3 sistemas exigidos:
  - **ECEF**: $X, Y, Z$ (m).
  - **Geodésicas**: $\phi, \lambda, h$ (sexagesimales y decimales).
  - **UTM Huso 30**: Easting, Northing con altitud ortométrica $H = h - N$.
- Cadena de rotaciones del sensor INS ($C_s^b$, $C_{mn}^{gn}$, $C_b^n$).
- Tabla final de residuales y diferencias entre el método GNSS y el método INS ($2\text{a} - 2\text{b}$).

---

## Licencia

Este proyecto está bajo la licencia **GNU General Public License v3 (GPLv3)**. Consulte el archivo [LICENSE](LICENSE) para más detalles.

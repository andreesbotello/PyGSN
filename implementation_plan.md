# Plan de Implementación: Reestructuración y Desacoplamiento del Núcleo Matemático de PyGSN

## 1. Contexto y Objetivos

La suite PyGSN dispone de paridad funcional y matemática a través de sus tres interfaces operativas (GUI, CLI y API). La presente reestructuración independiza la capa matemática de la jerarquía de Programación Orientada a Objetos (POO), construyendo una **Batería de Funciones Matemáticas Puras**:

1. **Agnosticismo de POO**: Las funciones numéricas reciben tipos primitivos (`np.ndarray` con `np.float64`, `float`, `int`, `tuple`) y no referencias a objetos de dominio (`Platform`, `Sensor`, `Project`).
2. **Protección Universal en Cascada**: Validación previa de finitud, rangos angulares con normalización modular ($[-\pi, \pi]$, $[0, 2\pi)$), límites físicos de cabeceo (Pitch) y detección de colinealidad/indeterminación antes del cálculo.
3. **Auditabilidad y Documentación Formal**: Cada función cuenta con su formulación matemática en LaTeX, unidades del SI y referencia bibliográfica explícita (Jekeli, Groves, Hofmann, GeoTop).
4. **Inventario Modular (`MATH_INVENTORY.md`)**: Registro maestro que mapea cada operación matemática a su archivo y contrato de entrada/salida.
5. **Modelos Jerárquicos como Contenedores de Estado**: Las clases POO (`Platform`, `Sensor`, `ReferenceSystem`) administran colecciones, persistencia y estado visual, delegando el álgebra en la batería matemática pura.
6. **No-Regresión Absoluta**: Preservación estricta de resultados numéricos y compatibilidad con la suite de pruebas unitarias.

---

## 2. Diagnóstico de Rendimiento Computacional

* **Overhead de Invocación**: La descomposición de métodos monolíticos en funciones puras añade menos de $1\,\mu\text{s}$ por ciclo de cálculo completo, lo que representa menos del 0.006% del presupuesto de 16.6 ms necesario para renderizado a 60 FPS.
* **Memoria y Vistas NumPy**: Se emplea `np.asarray(..., dtype=np.float64)` pasando arrays continuos en C por referencia, evitando duplicaciones de memoria innecesarias.
* **Preparación para Aceleración JIT**: Al ser funciones puras sin dependencias del runtime de clases Python, el núcleo queda habilitado para compilación transparente vía Numba (`@njit`) o Cython para simulaciones masivas.

---

## 3. Arquitectura en Capas

```
+---------------------------------------------------------------------------------------+
| CAPA 1: MODELADO JERÁRQUICO Y ORQUESTACIÓN (POO / Estado del Proyecto)                |
| - Clases de Dominio: Project, Platform, Sensor, ReferenceSystem, PlatformPose         |
| - Operadores de Pipeline: GeoreferencingOperator, TrajectoryKinematicsOperator         |
| - Contextos: GUI (PySide6), CLI (CLIEngine), API de Alto Nivel                        |
+---------------------------------------------------------------------------------------+
                                        │  delega datos primitivos
                                        ▼
+---------------------------------------------------------------------------------------+
| CAPA 0: BATERÍA MATEMÁTICA PURA (Agnóstica de POO, Funciones Deterministas)          |
| - validation.py   : Normalización angular, finitud, límites físicos y colinealidad   |
| - rotations.py    : Matrices pasivas R1/R2/R3, DCM, Euler, Actitud, reortonormalizado |
| - geodesy.py      : Elipsoides, curvaturas Rm/Rn, Geodésicas <-> ECEF, UTM directa/inv|
| - alignment.py    : Procrustes ortogonal SVD de Kabsch y auditoría espectral          |
| - kinematics.py   : Lever-arms 3D, cinemática de plataforma, mecanización geodésica  |
| - georeferencing.py: Pipeline puro de 10 funciones atómicas encadenadas               |
+---------------------------------------------------------------------------------------+
```

---

## 4. Fases de Ejecución Quirúrgica

1. **Fase 1**: Crear `core/MATH_INVENTORY.md` y ampliar `core/validation.py` con normalización angular universal ($[-\pi, \pi]$, $[0, 2\pi)$), validación de cabeceo y divisiones seguras.
2. **Fase 2**: Crear `core/kinematics.py` implementando cinemática pura de lever-arms, ecuaciones de navegación geodésica y transformaciones geométricas de chasis 2D/3D.
3. **Fase 3**: Ampliar `core/rotations.py` (`chain_ins_attitude_matrix`, `audit_dcm_condition`) y `core/geodesy.py` (`parse_coordinate_string`).
4. **Fase 4**: Modularizar `core/georeferencing.py` en 10 funciones atómicas puras y `solve_georeferencing_pipeline`, manteniendo la fachada compatible `solve_multisensor_georeferencing`.
5. **Fase 5**: Refactorizar `core/models.py` y `core/operators/kinematics_operator.py` para delegar en la batería matemática pura.
6. **Fase 6**: Crear `tests/test_math_battery.py` y verificar la suite completa de tests sin regresiones.

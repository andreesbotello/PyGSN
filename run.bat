@echo off
setlocal enabledelayedexpansion

title PyGSN - Guiado, Sensores y Navegacion [UPV 2026]

echo ===============================================================================
echo              PyGSN - Sistema de Transformacion de Coordenadas
echo        Georreferenciacion de Sensores y Navegacion Inercial (UPV - S3)
echo ===============================================================================
echo.

:: 1. Comprobar si Python esta disponible en el sistema
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] No se ha encontrado Python en el sistema.
    echo Por favor, instale Python 3.10 o superior desde https://www.python.org/
    echo y asegurese de marcar la casilla "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

:: 2. Crear entorno virtual aislado si no existe
if not exist ".venv" (
    echo [INFO] Creando entorno virtual aislado (.venv) para no alterar su sistema...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Fallo al crear el entorno virtual.
        pause
        exit /b 1
    )
    echo [INFO] Entorno virtual creado exitosamente.
    echo [INFO] Instalando dependencias de requirements.txt (NumPy, SciPy, DearPyGui)...
    .venv\Scripts\python -m pip install --upgrade pip >nul 2>nul
    .venv\Scripts\pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Fallo en la instalacion de dependencias.
        pause
        exit /b 1
    )
    echo [INFO] Instalacion completada con exito.
    echo.
)

:: 3. Ejecutar PyGSN
echo [INFO] Iniciando aplicacion PyGSN...
.venv\Scripts\python main.py %*

if %errorlevel% neq 0 (
    echo.
    echo [AVISO] La aplicacion ha finalizado con codigo de salida %errorlevel%.
    pause
)

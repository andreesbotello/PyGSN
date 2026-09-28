@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

title PyGSN - Georreferenciacion de Sensores y Navegacion [UPV]

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
    echo y marque la casilla "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

:: 2. Verificar si el Python del sistema ya cuenta con las dependencias
python -c "import numpy, scipy, dearpygui" >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto :RUN_APP
)

:: 3. Si no estan globales, usar/crear entorno virtual aislado (.venv)
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Configurando entorno virtual (.venv) e instalando dependencias...
    python -m venv .venv
    .venv\Scripts\python -m pip install --upgrade pip >nul 2>nul
    .venv\Scripts\pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Fallo al instalar las dependencias en .venv.
        pause
        exit /b 1
    )
    echo [INFO] Entorno virtual preparado con exito.
    echo.
)
set "PYTHON_EXE=.venv\Scripts\python"

:RUN_APP
echo [INFO] Iniciando PyGSN...
%PYTHON_EXE% main.py %*

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] La aplicacion ha finalizado con codigo de error %errorlevel%.
    pause
)

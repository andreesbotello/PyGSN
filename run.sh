#!/usr/bin/env bash
# PyGSN - Lanzador rapido para Linux / macOS

set -e
cd "$(dirname "$0")"

echo "==============================================================================="
echo "             PyGSN - Sistema de Transformación de Coordenadas"
echo "       Georreferenciación de Sensores y Navegación Inercial (UPV - S3)"
echo "==============================================================================="

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 no está instalado en el sistema."
    echo "Instale Python >= 3.10 para continuar."
    exit 1
fi

if python3 -c "import numpy, scipy, PySide6" > /dev/null 2>&1; then
    PYTHON_EXE="python3"
else
    if [ ! -f ".venv/bin/python" ]; then
        echo "[INFO] Configurando entorno virtual (.venv)..."
        python3 -m venv .venv
        .venv/bin/pip install --upgrade pip > /dev/null 2>&1
        .venv/bin/pip install -r requirements.txt
    fi
    PYTHON_EXE=".venv/bin/python"
fi

echo "[INFO] Iniciando PyGSN..."
$PYTHON_EXE main.py "$@"

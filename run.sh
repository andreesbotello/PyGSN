#!/usr/bin/env bash
# PyGSN - Lanzador rapido para Linux / macOS

set -e

echo "==============================================================================="
echo "             PyGSN - Sistema de Transformación de Coordenadas"
echo "       Georreferenciación de Sensores y Navegación Inercial (UPV - S3)"
echo "==============================================================================="

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 no está instalado en el sistema."
    echo "Instale Python >= 3.10 para continuar."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[INFO] Creando entorno virtual aislado (.venv)..."
    python3 -m venv .venv
    echo "[INFO] Instalando dependencias de requirements.txt..."
    .venv/bin/pip install --upgrade pip > /dev/null 2>&1
    .venv/bin/pip install -r requirements.txt
    echo "[INFO] Instalación completada."
fi

echo "[INFO] Iniciando PyGSN..."
.venv/bin/python main.py "$@"

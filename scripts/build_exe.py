"""
PyGSN - Build Standalone Executable Script
==========================================
Genera un ejecutable autocontenido (.exe para Windows) que incluye Python,
DearPyGui, NumPy y SciPy sin requerir instalacion previa de Python.

Uso:
  python scripts/build_exe.py
"""

import sys
import subprocess
from pathlib import Path


def build():
    root = Path(__file__).resolve().parent.parent
    print(f"[BUILD] Generando ejecutable standalone desde: {root}")

    # Verificar si PyInstaller esta instalado
    try:
        import PyInstaller
    except ImportError:
        print("[INFO] Instalando PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=PyGSN",
        "--onedir",
        "--windowed",
        "--clean",
        "--noconfirm",
        f"--paths={root}",
        str(root / "main.py")
    ]
    print(f"[RUN] {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=root)
    print("\n[EXITO] Ejecutable generado en: dist/PyGSN/PyGSN.exe")


if __name__ == "__main__":
    build()

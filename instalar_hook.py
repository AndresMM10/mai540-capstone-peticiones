"""Copia hooks/pre-commit a .git/hooks para que las pruebas corran antes de cada commit.

Uso: python instalar_hook.py
"""
import shutil
import stat
from pathlib import Path

raiz = Path(__file__).resolve().parent
destino = raiz / ".git" / "hooks" / "pre-commit"
shutil.copyfile(raiz / "hooks" / "pre-commit", destino)
destino.chmod(destino.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
print(f"Hook instalado en {destino}")

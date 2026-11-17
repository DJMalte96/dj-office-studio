"""Baut die Desktop-App mit PyInstaller (auf dem jeweiligen Betriebssystem ausführen).

    pip install -r rechnungen/requirements.txt pyinstaller pillow
    python desktop/build.py

Ergebnis in dist/: macOS „DJ Office Studio.app“, Windows Ordner „DJ Office Studio“ mit „DJ Office Studio.exe“.
"""
import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "rechnungen" / "app"
SEP = ";" if sys.platform == "win32" else ":"
OUT = Path(os.environ.get("DJOS_BUILD_DIR") or ROOT)   # wohin dist/ und build/ geschrieben werden

args = [
    str(ROOT / "desktop" / "start.py"),
    "--name", "DJ Office Studio",
    "--windowed",                 # kein Konsolenfenster; macOS: .app-Bundle
    "--noconfirm", "--clean",
    "--paths", str(APP),
    "--hidden-import", "main", "--hidden-import", "db", "--hidden-import", "pdf", "--hidden-import", "importer", "--hidden-import", "mail",
    "--add-data", f"{APP / 'static'}{SEP}static",
    "--add-data", f"{ROOT / 'rechnungen' / 'config.yaml'}{SEP}.",
    "--icon", str(ROOT / "rechnungen" / "icon.png"),
    "--distpath", str(OUT / "dist"), "--workpath", str(OUT / "build"), "--specpath", str(OUT / "build"),
]
if sys.platform == "darwin":
    args += ["--osx-bundle-identifier", "de.djofficestudio.app"]

os.chdir(ROOT)
PyInstaller.__main__.run(args)

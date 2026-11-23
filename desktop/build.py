"""Baut die Desktop-App mit PyInstaller (auf dem jeweiligen Betriebssystem ausführen).

    pip install -r rechnungen/requirements.txt -r desktop/requirements.txt pyinstaller pillow
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
    "--hidden-import", "main", "--hidden-import", "db", "--hidden-import", "pdf", "--hidden-import", "importer", "--hidden-import", "mail", "--hidden-import", "segno",
    "--hidden-import", "finanzen", "--hidden-import", "belege", "--hidden-import", "erechnung", "--hidden-import", "pdflesen", "--hidden-import", "dateilesen", "--hidden-import", "abschluss", "--hidden-import", "abos", "--hidden-import", "grenzen", "--hidden-import", "pypdf", "--hidden-import", "xml.parsers.expat", "--hidden-import", "strecken", "--hidden-import", "paperless", "--hidden-import", "extract_msg", "--hidden-import", "pillow_heif",
    "--collect-data", "extract_msg",
    "--add-data", f"{APP / 'static'}{SEP}static",
    "--add-data", f"{ROOT / 'rechnungen' / 'config.yaml'}{SEP}.",
    "--icon", str(ROOT / "rechnungen" / "icon.png"),
    "--distpath", str(OUT / "dist"), "--workpath", str(OUT / "build"), "--specpath", str(OUT / "build"),
]
# Texterkennung: Modelle, Einstellungen und Lizenzhinweise von RapidOCR, native Bibliotheken
args += ["--hidden-import", "texterkennung", "--collect-data", "rapidocr", "--copy-metadata", "rapidocr",
         "--collect-submodules", "rapidocr.inference_engine.onnxruntime", "--collect-binaries", "onnxruntime",
         "--collect-all", "pypdfium2_raw", "--collect-all", "pypdfium2"]
# Nicht gebraucht (kommt nur über extract-msg → oletools herein) und schädlich: Für Intel-Macs gibt es kein fertiges
# cryptography mehr, pip baut es gegen das OpenSSL des Build-Rechners – die App verlangte dadurch macOS 15.
args += ["--exclude-module", "cryptography", "--exclude-module", "msoffcrypto"]
# Eigenes App-Fenster (pywebview): JavaScript-Teile mitnehmen und die Plattform-Anbindung sicher einbinden
args += ["--collect-data", "webview", "--hidden-import", "webview"]
if sys.platform == "darwin":
    args += ["--osx-bundle-identifier", "de.djofficestudio.app", "--hidden-import", "webview.platforms.cocoa"]
elif sys.platform == "win32":
    args += ["--hidden-import", "webview.platforms.edgechromium", "--hidden-import", "webview.platforms.winforms"]

os.chdir(ROOT)
PyInstaller.__main__.run(args)

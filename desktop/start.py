"""DJ Office Studio als Desktop-App (Windows / macOS) – ohne Home Assistant.

Startet den eingebauten Webserver lokal (nur auf diesem Rechner erreichbar), öffnet die Oberfläche
im Standardbrowser und zeigt ein kleines Fenster zum erneuten Öffnen bzw. Beenden.

Daten liegen im Dokumente-Ordner unter „DJ Office Studio“:
  Daten/  – Datenbank (Kunden, Rechnungen, Angebote, Einstellungen), Protokoll und
            Sicherungen/ (automatisch einmal pro Tag, die letzten 14 Tage)
  PDFs/   – Kopien aller gespeicherten Rechnungen und Angebote
"""
import json
import os
import socket
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "DJ Office Studio"
PORTS = range(8765, 8776)


def dokumente_ordner():
    """Dokumente-Ordner des Benutzers (unter Windows auch bei Umleitung, z. B. auf OneDrive)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)   # CSIDL_PERSONAL
            if buf.value:
                return Path(buf.value)
        except Exception:
            pass
    return Path.home() / "Documents"


BASIS = Path(os.environ.get("DJOS_BASIS") or dokumente_ordner() / APP_NAME)   # DJOS_BASIS: nur für Tests
DATEN = BASIS / "Daten"
PDFS = BASIS / "PDFs"


def laufende_instanz():
    """Port einer bereits laufenden DJ Office Studio-Instanz (Doppelklick auf die App, obwohl sie schon läuft)."""
    for port in PORTS:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/absender", timeout=0.5) as r:
                if "version" in json.loads(r.read()):
                    return port
        except Exception:
            continue
    return None


def freier_port():
    for port in PORTS:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("Kein freier Port zwischen 8765 und 8775 gefunden.")


def automatische_sicherung(db, behalten=14):
    """Einmal pro Tag beim Start eine Kopie der Datenbank in Daten/Sicherungen ablegen (die letzten 14 bleiben)."""
    from datetime import date
    ordner = DATEN / "Sicherungen"
    ordner.mkdir(exist_ok=True)
    ziel = ordner / f"rechnungen_{date.today().isoformat()}.db"
    try:
        if not ziel.exists():
            db.sichern(str(ziel))
        for alt in sorted(ordner.glob("rechnungen_*.db"))[:-behalten]:
            alt.unlink()
    except OSError as e:
        print(f"Automatische Sicherung fehlgeschlagen: {e}")


def ordner_oeffnen(pfad):
    if sys.platform == "win32":
        os.startfile(pfad)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(pfad)])
    else:
        subprocess.Popen(["xdg-open", str(pfad)])


def main():
    port = laufende_instanz()
    if port:   # läuft schon → nur die Oberfläche öffnen
        webbrowser.open(f"http://127.0.0.1:{port}/")
        return

    DATEN.mkdir(parents=True, exist_ok=True)
    PDFS.mkdir(parents=True, exist_ok=True)
    # In der fertigen App gibt es keine Konsole – Ausgaben ins Protokoll schreiben
    if getattr(sys, "frozen", False):
        log = open(DATEN / "protokoll.txt", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log

    os.environ.update({
        "DJOS_DESKTOP": "1",
        "DATA_DIR": str(DATEN),
        "OPTIONS_PATH": str(DATEN / "options.json"),   # gibt es am Desktop nicht – nur der Vollständigkeit halber
        "STANDARD_PDF_ORDNER": str(PDFS),
    })
    # App-Code liegt im Repo unter rechnungen/app (in der fertigen App wird er mitgebündelt)
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rechnungen" / "app"))
    import db
    import main as webapp
    from waitress import create_server

    db.init()
    automatische_sicherung(db)
    port = freier_port()
    server = create_server(webapp.app, host="127.0.0.1", port=port, threads=8)
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"{APP_NAME} {webapp.APP_VERSION} läuft unter {url}", flush=True)
    if os.environ.get("DJOS_TEST") == "1":   # Test/CI: ohne Browser und Fenster, nur Server
        threading.Event().wait()
    webbrowser.open(url)

    fenster(url, webapp.APP_VERSION, server)


def fenster(url, version, server):
    """Kleines Statusfenster: Schließen beendet die App."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(APP_NAME)
    root.resizable(False, False)

    def beenden():
        server.close()
        root.destroy()

    rahmen = ttk.Frame(root, padding=18)
    rahmen.grid()
    ttk.Label(rahmen, text=f"{APP_NAME} läuft", font=("", 15, "bold")).grid(column=0, row=0, columnspan=3, sticky="w")
    ttk.Label(rahmen, text=f"Version {version} · {url}").grid(column=0, row=1, columnspan=3, sticky="w", pady=(2, 4))
    ttk.Label(rahmen, text="Die Oberfläche öffnet sich im Browser. Solange dieses Fenster offen ist,\n"
                           "ist die App erreichbar – zum Beenden das Fenster schließen.",
              foreground="#666").grid(column=0, row=2, columnspan=3, sticky="w", pady=(0, 12))
    ttk.Button(rahmen, text="Im Browser öffnen", command=lambda: webbrowser.open(url)).grid(column=0, row=3, sticky="w")
    ttk.Button(rahmen, text="Daten- und PDF-Ordner", command=lambda: ordner_oeffnen(BASIS)).grid(column=1, row=3, padx=8)
    ttk.Button(rahmen, text="Beenden", command=beenden).grid(column=2, row=3, sticky="e")
    root.protocol("WM_DELETE_WINDOW", beenden)
    root.mainloop()


if __name__ == "__main__":
    main()

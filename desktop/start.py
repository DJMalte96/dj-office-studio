"""DJ Office Studio als Desktop-App (Windows / macOS) – ohne Home Assistant.

Startet den eingebauten Webserver lokal (nur auf diesem Rechner erreichbar) und zeigt die Oberfläche in einem
eigenen App-Fenster (pywebview: WebKit unter macOS, Edge WebView2 unter Windows). Schließen des Fensters beendet
die App. Ist kein eigenes Fenster möglich (z. B. fehlendes WebView2), öffnet sich wie früher der Standardbrowser
mit einem kleinen Statusfenster.

Daten liegen im Dokumente-Ordner unter „DJ Office Studio“:
  Daten/  – Datenbank (Kunden, Rechnungen, Angebote, Einstellungen), Protokoll und
            Sicherungen/ (automatisch einmal pro Tag, die letzten 14 Tage)
  PDFs/   – Kopien aller gespeicherten Rechnungen und Angebote
"""
import base64
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
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


def eigene_dateien_freigeben():
    """Windows: Die Markierung „aus dem Internet geladen“ (Zone.Identifier) von den eigenen Programmdateien entfernen.

    Wird die App als ZIP heruntergeladen und mit Windows entpackt, trägt jede Datei diese Markierung. .NET lädt so
    markierte Bausteine nicht (Python.Runtime.dll für das Edge-Fenster) – das eigene Fenster scheitert dann mit
    „Failed to resolve Python.Runtime.Loader.Initialize“. Das entspricht „Eigenschaften → Zulassen“ und betrifft nur
    die Dateien dieser App."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False) or os.environ.get("DJOS_KEINE_FREIGABE") == "1":
        return 0
    ordner = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    freigegeben = 0
    for datei in ordner.rglob("*"):
        if datei.suffix.lower() not in (".dll", ".exe", ".pyd", ".json"):
            continue
        try:
            os.remove(f"{datei}:Zone.Identifier")   # alternativer Datenstrom mit der Internet-Markierung
            freigegeben += 1
        except OSError:
            pass   # nicht markiert (Normalfall) oder nicht änderbar
    if freigegeben:
        print(f"{freigegeben} Programmdateien freigegeben (Markierung „aus dem Internet“ entfernt)", flush=True)
    return freigegeben


def fenster_moeglich():
    """Kann ein eigenes App-Fenster geöffnet werden? (pywebview und die Plattform-Anbindung vorhanden)"""
    eigene_dateien_freigeben()
    try:
        import webview  # noqa: F401
        if sys.platform == "darwin":
            import webview.platforms.cocoa  # noqa: F401
        elif sys.platform == "win32":
            import webview.platforms.edgechromium  # noqa: F401
        return True
    except Exception as e:   # fehlende Bibliothek, kein .NET o. Ä.
        print(f"Kein eigenes Fenster möglich: {e}", flush=True)
        return False


def main():
    port = laufende_instanz()
    if port:   # läuft schon → ein weiteres Fenster zur laufenden App öffnen
        oberflaeche(f"http://127.0.0.1:{port}/")
        return

    DATEN.mkdir(parents=True, exist_ok=True)
    PDFS.mkdir(parents=True, exist_ok=True)
    # In der fertigen App gibt es keine Konsole – Ausgaben ins Protokoll schreiben
    if getattr(sys, "frozen", False):
        log = open(DATEN / "protokoll.txt", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log

    os.environ.update({
        "DJOS_DESKTOP": "1",
        "DJOS_FENSTER": "1" if fenster_moeglich() else "0",   # zeigt die App für die Oberfläche bzw. den Test an
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
    webapp.finanzen.ordner_waechter_starten()   # Belege-Ordner regelmäßig einlesen
    webapp.finanzen.texterkennung_starten()     # Fotos und Scans im Hintergrund lesen
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"{APP_NAME} {webapp.APP_VERSION} läuft unter {url}", flush=True)
    if os.environ.get("DJOS_TEST") == "1":   # Test/CI: ohne Browser und Fenster, nur Server
        threading.Event().wait()
    oberflaeche(url, server, webapp.APP_VERSION)


# ---------- Eigenes App-Fenster ----------

class DesktopApi:
    """Wird im Fenster als window.pywebview.api angeboten: Dinge, die ein App-Fenster nicht selbst kann
    (PDFs anzeigen, Dateien speichern, externe Links)."""

    def __init__(self, basis_url):
        self._basis = basis_url
        self._fenster = None

    def _laden(self, pfad):
        """Datei von der eigenen App holen (nur relative Pfade wie „api/…“) → (Dateiname, Inhalt)."""
        if "://" in pfad or pfad.startswith("//"):
            raise ValueError("Nur Adressen der App erlaubt")
        with urllib.request.urlopen(self._basis + pfad.lstrip("/"), timeout=120) as r:
            kopf = r.headers.get("Content-Disposition", "")
            m = re.search(r'filename="?([^";]+)"?', kopf)
            name = m.group(1) if m else (urllib.parse.urlparse(pfad).path.rsplit("/", 1)[-1] or "Dokument")
            return _sicherer_name(name), r.read()

    def pdf_oeffnen(self, pfad):
        """PDF der App im PDF-Programm des Systems öffnen (Vorschau, Edge, Acrobat …)."""
        name, daten = self._laden(pfad)
        return self._anzeigen(_als_pdf(name), daten)

    def pdf_daten_oeffnen(self, name, inhalt_base64):
        """Im Browser erzeugtes PDF (z. B. Vorschau) im PDF-Programm des Systems öffnen."""
        return self._anzeigen(_als_pdf(_sicherer_name(name or "Dokument.pdf")), base64.b64decode(inhalt_base64))

    def _anzeigen(self, name, daten):
        ordner = Path(tempfile.gettempdir()) / APP_NAME
        ordner.mkdir(exist_ok=True)
        for alt in ordner.glob("*"):   # alte Ansichten aufräumen (älter als 1 Tag)
            try:
                if time.time() - alt.stat().st_mtime > 86400:
                    alt.unlink()
            except OSError:
                pass
        ziel = ordner / name
        try:
            ziel.write_bytes(daten)
        except OSError:   # z. B. unter Windows noch im PDF-Programm geöffnet → neuer Name
            ziel = ordner / f"{Path(name).stem}_{int(time.time())}{Path(name).suffix}"
            ziel.write_bytes(daten)
        ordner_oeffnen(ziel)
        return ziel.name

    def speichern(self, pfad):
        """Datei der App (Sicherung, Export, ZIP …) über „Speichern unter“ ablegen. Rückgabe: Dateiname oder None."""
        import webview
        name, daten = self._laden(pfad)
        ordner = Path.home() / "Downloads"
        auswahl = self._fenster.create_file_dialog(webview.FileDialog.SAVE, directory=str(ordner if ordner.is_dir() else Path.home()),
                                                    save_filename=name)
        if not auswahl:
            return None
        ziel = Path(auswahl if isinstance(auswahl, str) else auswahl[0])
        ziel.write_bytes(daten)
        return ziel.name

    def extern(self, url):
        """Externe Seite (GitHub, Changelog …) im Standardbrowser öffnen."""
        if url.startswith(("https://", "http://", "mailto:")):
            webbrowser.open(url)
        return True

    def daten_ordner(self):
        ordner_oeffnen(BASIS)
        return True


def _als_pdf(name):
    """Das System öffnet nach der Endung: Ein Beleg „rechnung.hta“ mit PDF-Anfang würde sonst ausgeführt."""
    return name if name.lower().endswith(".pdf") else name + ".pdf"


def _sicherer_name(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .") or "Dokument"
    return name[:120]


def oberflaeche(url, server=None, version=""):
    """App-Fenster öffnen; falls das nicht geht, wie früher Browser + Statusfenster."""
    if os.environ.get("DJOS_FENSTER", "1" if fenster_moeglich() else "0") == "1":
        try:
            import webview
            api = DesktopApi(url)
            api._fenster = webview.create_window(
                APP_NAME, url, js_api=api, width=1320, height=900, min_size=(940, 640),
                text_select=True,      # Texte markieren und kopieren (IBAN, Adressen …)
                zoomable=True,         # Strg/⌘ + / − wie im Browser
                background_color="#f3f3f3")
            gui = "edgechromium" if sys.platform == "win32" else None   # Windows: kein Rückfall auf den alten IE
            webview.start(gui=gui, private_mode=False,        # Hell/Dunkel-Wahl u. Ä. bleiben gespeichert
                          storage_path=str(DATEN / "Fenster"))
            return   # Fenster geschlossen → App endet (der Server läuft als Hintergrund-Thread und endet mit)
        except Exception as e:
            print(f"Eigenes Fenster konnte nicht geöffnet werden, öffne Browser: {e}", flush=True)
    webbrowser.open(url)
    if server:
        fenster(url, version, server)


def fenster(url, version, server):
    """Rückfall ohne eigenes App-Fenster: kleines Statusfenster, Schließen beendet die App."""
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


def texterkennung_kind(pfad, ausgabe):
    """Die App ruft sich für die Texterkennung selbst als Kindprozess auf – ohne Fenster und ohne Server."""
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rechnungen" / "app"))
    import texterkennung
    texterkennung.kind(pfad, ausgabe)


def pdf_lesen_kind(ordner, art):
    """Die App ruft sich zum Lesen fremder PDFs selbst als Kindprozess auf – ohne Fenster und ohne Server."""
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rechnungen" / "app"))
    import pdflesen
    pdflesen.kind(ordner, art)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--pdf-lesen":         # vor allem anderen: sonst öffnet sich ein zweites Fenster
        pdf_lesen_kind(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 4 and sys.argv[1] == "--texterkennung":   # vor allem anderen: sonst öffnet sich ein zweites Fenster
        texterkennung_kind(sys.argv[2], sys.argv[3])
    else:
        main()

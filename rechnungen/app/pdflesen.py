"""Fremde PDFs lesen – je PDF in einem eigenen Prozess mit Grenzen für Speicher und Zeit.

Ein präpariertes PDF (Dekompressionsbombe, Endlosschleife, riesige Tabellen) trifft so nur den Kindprozess.
pypdf aktuell zu halten reicht allein nicht: Dort werden laufend neue Wege gefunden.

Die App ruft nur lesen() auf und importiert selbst nie pypdf. kind() läuft im Kindprozess.
"""
import base64
import collections
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading

SCHALTER = "--pdf-lesen"        # damit startet die gepackte Desktop-App als Kindprozess (siehe desktop/start.py)
SPEICHER_MB = 400               # ein Raspberry Pi mit 1 GB muss daneben Home Assistant tragen
ZEITLIMIT = 20                  # Sekunden je PDF
START_RESERVE = 15              # so viel länger wartet die App (langsamer Start, Virenscanner)
MAX_SEITEN = 100                # darüber: die ersten 90 und die letzten 10
MAX_ZEICHEN = 1_000_000
MAX_AUSGABE = 40 * 1024 * 1024

Ergebnis = collections.namedtuple("Ergebnis", "text anhaenge problem kaputt gekuerzt")


class Abgebrochen(ValueError):
    """Eine Grenze wurde erreicht. Der Text ist für den Nutzer gedacht."""

    def __init__(self, grund):
        super().__init__(f"PDF nicht gelesen: {grund}")
        self.grund = grund


class Kaputt(Exception):
    """Gewöhnlich defektes oder verschlüsseltes PDF."""


# ---------- Aufruf aus der App ----------

_einer = threading.Semaphore(1)     # nie zwei gleichzeitig – sonst gilt die Speichergrenze doppelt
_merker = collections.OrderedDict()


def lesen(daten, layout=False):
    """→ Ergebnis. Wirft nicht. Je Beleg wird mehrmals gefragt (Text, Anhänge, Texterkennung) – ein Prozess genügt."""
    schluessel = (hashlib.sha256(daten).digest(), layout)
    with _einer:
        if schluessel in _merker:
            return _merker[schluessel]
        e, merken = _im_kindprozess(daten, layout)
        if merken and sum(len(d) for _, d in e.anhaenge) + len(e.text) < 2 * 1024 * 1024:
            _merker[schluessel] = e
            while len(_merker) > 8:
                _merker.popitem(last=False)
        return e


def text(daten, layout=False):
    """→ (Text, gekürzt). Wirft Abgebrochen bzw. Kaputt."""
    e = lesen(daten, layout)
    if e.problem:
        raise Abgebrochen(e.problem)
    if e.kaputt:
        raise Kaputt(e.kaputt)
    return e.text, e.gekuerzt


def _befehl():
    if getattr(sys, "frozen", False):
        return [sys.executable, SCHALTER]
    return [sys.executable, "-I", os.path.abspath(__file__), SCHALTER]


def _json(pfad):
    try:
        if os.path.getsize(pfad) <= MAX_AUSGABE:
            with open(pfad, encoding="utf-8") as f:
                return json.load(f)
    except (OSError, ValueError):
        pass
    return None


def _im_kindprozess(daten, layout):
    """→ (Ergebnis, darf gemerkt werden)."""
    import grenzen
    try:
        with tempfile.TemporaryDirectory(prefix="djos-pdf-", ignore_cleanup_errors=True) as tmp:
            with open(os.path.join(tmp, "beleg.pdf"), "wb") as f:
                f.write(daten)
            extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            # ohne das Token des Supervisors: dieser Prozess liest fremde Dateien
            umgebung = {k: v for k, v in os.environ.items() if k not in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN")}
            try:
                code = subprocess.run(_befehl() + [tmp, "layout" if layout else "beleg"], timeout=ZEITLIMIT + START_RESERVE,
                                      env=umgebung, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, **extra).returncode
            except subprocess.TimeoutExpired:
                code = grenzen.ZU_LANGE
            # Die Anhänge schreibt das Kind zuerst: eine E-Rechnung gibt es auch, wenn der Text nicht zu lesen ist
            anhaenge = [(n, base64.b64decode(d)) for n, d in _json(os.path.join(tmp, "anhaenge.json")) or []]
            d = _json(os.path.join(tmp, "text.json"))
    except OSError as e:
        return Ergebnis("", [], f"Lesen ließ sich nicht starten ({type(e).__name__})", None, False), False
    if code or d is None:
        grund = grenzen.GRUENDE.get(code, "Lesen abgebrochen, vermutlich zu aufwendig")
        return Ergebnis("", anhaenge, grund, None, False), code in grenzen.GRUENDE
    return Ergebnis(d.get("text", ""), anhaenge, d.get("problem"), d.get("kaputt"), bool(d.get("gekuerzt"))), True


# ---------- Kindprozess ----------

def _schreiben(ordner, name, inhalt):
    ziel = os.path.join(ordner, name)
    with open(ziel + ".neu", "w", encoding="utf-8") as f:
        json.dump(inhalt, f)
    os.replace(ziel + ".neu", ziel)


def _seitentext(seite, layout):
    if layout:
        try:
            return seite.extract_text(extraction_mode="layout") or ""
        except MemoryError:
            raise
        except Exception:
            pass
    return seite.extract_text() or ""


def _speicher_voll(e):
    """pypdf verpackt MemoryError gelegentlich; seine eigenen Grenzen melden LimitReachedError."""
    while e is not None:
        if isinstance(e, MemoryError) or type(e).__name__ == "LimitReachedError":
            return True
        e = e.__cause__ or e.__context__
    return False


def _auslesen(ordner, layout):
    from pypdf import PdfReader
    import erechnung
    leser = PdfReader(os.path.join(ordner, "beleg.pdf"))
    if not layout:
        anhaenge = [(n, base64.b64encode(d).decode()) for n, d in erechnung.pdf_anhaenge(None, leser)]
        _schreiben(ordner, "anhaenge.json", anhaenge)
    seiten = list(leser.pages)
    gekuerzt = len(seiten) > MAX_SEITEN
    if gekuerzt:
        seiten = seiten[:MAX_SEITEN - 10] + seiten[-10:]
    teile, zeichen = [], 0
    for seite in seiten:
        try:
            t = _seitentext(seite, layout)
        except Exception as e:
            if _speicher_voll(e):
                raise
            continue                    # eine defekte Seite hält den Rest nicht auf
        zeichen += len(t)
        if zeichen > MAX_ZEICHEN:
            return {"problem": "enthält ungewöhnlich viel Text"}
        teile.append(t)
    return {"text": "\n".join(teile).encode("utf-8", "replace").decode("utf-8"), "gekuerzt": gekuerzt}


def kind(ordner, art):
    """Einstieg des Kindprozesses."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # -I: der eigene Ordner fehlt im Suchpfad
    import grenzen
    grenzen.ohne_netz()
    grenzen.prozess_begrenzen(SPEICHER_MB, ZEITLIMIT)
    import logging
    logging.disable(logging.CRITICAL)       # pypdf meldet jede Unstimmigkeit einzeln
    try:
        d = _auslesen(ordner, art == "layout")
    except BaseException as e:
        if _speicher_voll(e):
            os._exit(grenzen.ZU_VIEL_SPEICHER)      # ohne Aufräumen – dafür wäre kein Speicher mehr da
        d = {"kaputt": type(e).__name__}
    _schreiben(ordner, "text.json", d)
    os._exit(0)                             # fertig: kein langes Abbauen riesiger Objektbäume


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == SCHALTER:
    kind(sys.argv[2], sys.argv[3])

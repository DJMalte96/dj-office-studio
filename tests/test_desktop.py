"""Desktop-Version: automatische tägliche Sicherung."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))


def test_automatische_sicherung(app_modul, tmp_path, monkeypatch):
    import db
    import start
    monkeypatch.setattr(start, "DATEN", tmp_path / "Daten")
    (tmp_path / "Daten").mkdir()
    ordner = tmp_path / "Daten" / "Sicherungen"
    ordner.mkdir()
    for tag in range(1, 17):   # 16 alte Sicherungen
        (ordner / f"rechnungen_2020-01-{tag:02d}.db").write_bytes(b"alt")

    start.automatische_sicherung(db)
    start.automatische_sicherung(db)   # zweiter Start am selben Tag: keine weitere Kopie

    dateien = sorted(p.name for p in ordner.iterdir())
    assert len(dateien) == 14
    assert dateien[-1] == f"rechnungen_{date.today().isoformat()}.db"
    assert db.pruefe_sicherung(str(ordner / dateien[-1]))["rechnungen"] == 0


class _Antwort:
    def __init__(self, daten, kopf):
        self._daten, self.headers = daten, kopf

    def read(self):
        return self._daten

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_app_fenster_bruecke(tmp_path, monkeypatch):
    """Brücke des App-Fensters: nur Adressen der eigenen App, sichere Dateinamen, PDFs zum Anzeigen ablegen."""
    import start
    geoeffnet, abgerufen = [], []
    monkeypatch.setattr(start, "ordner_oeffnen", lambda pfad: geoeffnet.append(pfad))
    monkeypatch.setattr(start.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(start.urllib.request, "urlopen", lambda url, timeout=None: (
        abgerufen.append(url) or _Antwort(b"%PDF-1.4 test", {"Content-Disposition": 'inline; filename="Rechnung_037_011126.pdf"'})))
    api = start.DesktopApi("http://127.0.0.1:8765/")

    assert api.pdf_oeffnen("api/rechnungen/1/pdf") == "Rechnung_037_011126.pdf"
    assert abgerufen == ["http://127.0.0.1:8765/api/rechnungen/1/pdf"]
    assert geoeffnet[0].read_bytes().startswith(b"%PDF")
    for fremd in ("https://example.com/x", "//example.com/x"):
        try:
            api.pdf_oeffnen(fremd)
            raise AssertionError("fremde Adresse wurde nicht abgelehnt")
        except ValueError:
            pass
    # im Browser erzeugtes PDF (Vorschau), Name wird entschärft
    assert api.pdf_daten_oeffnen("../Vorschau:037?.pdf", "JVBERi0xLjQ=") == "_Vorschau_037_.pdf"
    assert start._sicherer_name("..") == "Dokument" and start._sicherer_name('a/b\\c"d.zip') == "a_b_c_d.zip"

"""Gemeinsame Test-Hilfen: jede Test-Funktion bekommt eine frische, leere Datenbank in einem Temp-Ordner."""
import io
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

APP = Path(__file__).resolve().parents[1] / "rechnungen" / "app"
sys.path.insert(0, str(APP))


@pytest.fixture
def app_modul(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPTIONS_PATH", str(tmp_path / "options.json"))
    import db
    import main
    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "rechnungen.db"))
    monkeypatch.setattr(main, "OPTIONS_PATH", str(tmp_path / "options.json"))
    monkeypatch.setattr(main, "DESKTOP", False)
    main._update_cache.update(zeit=0, ergebnis=None)
    db.init()
    db.save_settings({"_uebernommen": True, "name": "Max Beispiel", "strasse": "Musterweg 1",
                      "plz_ort": "12345 Musterstadt", "iban": "DE00 1234", "ort_fuer_datum": "Musterstadt",
                      "startnummer": 37, "pdf_ordner": str(tmp_path / "pdf")})
    return main


@pytest.fixture
def client(app_modul):
    c = app_modul.app.test_client()
    c.environ_base["HTTP_X_DJOS"] = "1"   # wie die Oberfläche: ohne diesen Kopf lehnt die App Änderungen ab
    return c


KUNDE = {"name": "Anna Muster", "strasse": "Lindenweg 12", "plz": "12345", "ort": "Musterstadt"}


def neue_rechnung(client, nummer="037", datum="2026-11-01", preis=960, bezahlt=False,
                  zahlungsbedingung="Bitte innerhalb der nächsten 8 Tage überweisen."):
    r = client.post("/api/rechnungen", json={
        "nummer": nummer, "datum": datum, "kunde": KUNDE, "zahlungsbedingung": zahlungsbedingung,
        "positionen": [{"beschreibung": "DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr",
                        "lieferdatum": datum, "preis": preis}],
        "bezahlt": bezahlt})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def pdf_text(daten):
    assert daten[:5] == b"%PDF-"
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(daten)).pages)

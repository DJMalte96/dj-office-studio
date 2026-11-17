"""Rechnungen: anlegen, Nummern, Festschreiben, Storno."""
import sqlite3

from conftest import neue_rechnung, pdf_text


def test_anlegen_nummer_und_pdf(client):
    assert client.get("/api/rechnungen/naechste-nummer").get_json()["nummer"] == "037"
    inv_id = neue_rechnung(client)
    assert client.get("/api/rechnungen/naechste-nummer").get_json()["nummer"] == "038"
    text = pdf_text(client.get(f"/api/rechnungen/{inv_id}/pdf").data)
    assert "Rechnung Nr.: 037" in text and "960,- Euro" in text and "Max Beispiel" in text


def test_doppelte_nummer_wird_abgelehnt(client):
    neue_rechnung(client)
    r = client.post("/api/rechnungen", json={"nummer": "037", "kunde": {"name": "X"}, "zahlungsbedingung": "x",
                                             "positionen": [{"beschreibung": "DJ", "preis": 1}]})
    assert r.status_code == 400 and "bereits vergeben" in r.get_json()["error"]


def test_offene_rechnung_ist_aenderbar_und_loeschbar(client):
    inv_id = neue_rechnung(client)
    inv = client.get(f"/api/rechnungen/{inv_id}").get_json()
    assert inv["festgeschrieben"] is False
    inv["positionen"][0]["preis"] = 900
    assert client.put(f"/api/rechnungen/{inv_id}", json=inv).status_code == 200
    assert client.get(f"/api/rechnungen/{inv_id}").get_json()["gesamt"] == 900
    assert client.delete(f"/api/rechnungen/{inv_id}").status_code == 204


def test_bezahlt_schreibt_fest(client):
    inv_id = neue_rechnung(client)
    client.patch(f"/api/rechnungen/{inv_id}/bezahlt", json={"bezahlt": True})
    inv = client.get(f"/api/rechnungen/{inv_id}").get_json()
    assert inv["bezahlt"] and inv["festgeschrieben"] and inv["bezahlt_am"]
    assert client.put(f"/api/rechnungen/{inv_id}", json=inv).status_code == 409
    assert client.delete(f"/api/rechnungen/{inv_id}").status_code == 409
    # zurück auf offen: Zahlstatus ändert sich, Festschreibung bleibt
    client.patch(f"/api/rechnungen/{inv_id}/bezahlt", json={"bezahlt": False})
    inv = client.get(f"/api/rechnungen/{inv_id}").get_json()
    assert not inv["bezahlt"] and inv["festgeschrieben"] and inv["bezahlt_am"] is None


def test_manuell_festschreiben(client):
    inv_id = neue_rechnung(client)
    assert client.post(f"/api/rechnungen/{inv_id}/festschreiben").status_code == 204
    assert client.delete(f"/api/rechnungen/{inv_id}").status_code == 409


def test_stornieren(client):
    inv_id = neue_rechnung(client)
    r = client.post(f"/api/rechnungen/{inv_id}/stornieren")
    assert r.status_code == 201
    storno_id = r.get_json()["id"]
    assert r.get_json()["nummer"] == "038"

    orig = client.get(f"/api/rechnungen/{inv_id}").get_json()
    storno = client.get(f"/api/rechnungen/{storno_id}").get_json()
    assert orig["storniert_durch"] == storno_id and orig["storniert_durch_nummer"] == "038" and orig["festgeschrieben"]
    assert storno["storno_von"] == inv_id and storno["gesamt"] == -960 and storno["festgeschrieben"]
    assert storno["positionen"][0]["preis"] == -960

    text = pdf_text(client.get(f"/api/rechnungen/{storno_id}/pdf").data)
    assert "Stornorechnung Nr.: 038" in text and "Rechnung Nr. 037" in text and "-960,- Euro" in text
    assert any(r["name"].startswith("Stornorechnung_038") for r in client.get("/api/rechnungen").get_json())

    # kein zweites Storno, kein Storno vom Storno, kein Zahlstatus
    assert client.post(f"/api/rechnungen/{inv_id}/stornieren").status_code == 400
    assert client.post(f"/api/rechnungen/{storno_id}/stornieren").status_code == 400
    assert client.patch(f"/api/rechnungen/{inv_id}/bezahlt", json={"bezahlt": True}).status_code == 400


def test_migration_alter_datenbank(app_modul, tmp_path):
    """Datenbank aus einer Version vor 0.12: bezahlte Rechnungen werden beim Start festgeschrieben."""
    import db
    alt = tmp_path / "alt.db"
    con = sqlite3.connect(alt)
    con.executescript("""
        CREATE TABLE rechnungen (id INTEGER PRIMARY KEY AUTOINCREMENT, nummer TEXT NOT NULL UNIQUE,
          datum TEXT NOT NULL, kunde_id INTEGER, kunde_json TEXT NOT NULL, positionen_json TEXT NOT NULL,
          zahlungsbedingung TEXT NOT NULL, gesamt REAL NOT NULL, bezahlt INTEGER DEFAULT 0,
          erstellt TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO rechnungen (nummer, datum, kunde_json, positionen_json, zahlungsbedingung, gesamt, bezahlt)
          VALUES ('001', '2025-01-01', '{"name": "A"}', '[]', 'x', 100, 1),
                 ('002', '2025-02-01', '{"name": "B"}', '[]', 'x', 200, 0);
    """)
    con.commit()
    con.close()
    db.DB_PATH = str(alt)
    db.init()
    status = {r["nummer"]: r["festgeschrieben"] for r in db.list_invoices()}
    assert status == {"001": True, "002": False}


def test_ohne_daten_verstaendlicher_fehler_statt_absturz(client):
    """Fehlende oder kaputte JSON-Daten führen zu 400 mit Meldung, nicht zu einem Serverfehler."""
    for methode, url in (("post", "/api/rechnungen"), ("post", "/api/angebote"), ("post", "/api/vorschau"),
                         ("post", "/api/kunden"), ("put", "/api/einstellungen"), ("post", "/api/versand")):
        r = getattr(client, methode)(url, data="kein json", content_type="text/plain")
        assert r.status_code < 500, (url, r.status_code)

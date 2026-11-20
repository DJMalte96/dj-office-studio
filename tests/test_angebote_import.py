"""Angebote, Import alter PDFs, Paperless, Download."""
import io
import zipfile

from conftest import KUNDE, neue_rechnung, pdf_text

ANGEBOT = {"art": "angebot", "nummer": "001", "datum": "2026-11-01", "gueltig_bis": "2026-12-01", "kunde": KUNDE,
           "positionen": [{"beschreibung": "DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr",
                           "lieferdatum": "2027-06-12", "preis": 900}],
           "hinweise": "Jede weitere angefangene Stunde wird mit 80,- Euro berechnet."}


def test_angebot_und_umwandlung(client):
    r = client.post("/api/angebote", json=ANGEBOT)
    assert r.status_code == 201
    aid = r.get_json()["id"]
    text = pdf_text(client.get(f"/api/angebote/{aid}/pdf").data)
    assert "Angebot Nr.: 001" in text and "gültig bis zum 01.12.2026" in text and "80,- Euro" in text
    inv = {**ANGEBOT, "art": "rechnung", "nummer": "037", "zahlungsbedingung": "8 Tage", "angebot_id": aid}
    assert client.post("/api/rechnungen", json=inv).status_code == 201
    a = client.get(f"/api/angebote/{aid}").get_json()
    assert a["status"] == "angenommen" and a["rechnung_id"]


def test_import_erkennt_rechnung_und_angebot(client):
    inv_id = neue_rechnung(client, nummer="030")
    aid = client.post("/api/angebote", json=ANGEBOT).get_json()["id"]
    dateien = [(io.BytesIO(client.get(f"/api/rechnungen/{inv_id}/pdf").data), "r.pdf"),
               (io.BytesIO(client.get(f"/api/angebote/{aid}/pdf").data), "a.pdf")]
    client.delete(f"/api/rechnungen/{inv_id}")
    client.delete(f"/api/angebote/{aid}")

    r = client.post("/api/import/analyse", data={"dateien": dateien}, content_type="multipart/form-data")
    d = r.get_json()
    assert not d["fehler"]
    assert [x["nummer"] for x in d["rechnungen"]] == ["030"] and d["rechnungen"][0]["gesamt"] == 960
    assert d["angebote"][0]["gueltig_bis"] == "2026-12-01" and "80,- Euro" in d["angebote"][0]["hinweise"]

    client.post("/api/import/uebernehmen", json={"rechnungen": d["rechnungen"], "angebote": d["angebote"],
                                                 "bezahlt": True})
    inv = client.get("/api/rechnungen").get_json()[0]
    assert inv["nummer"] == "030" and inv["festgeschrieben"]   # importierte Rechnungen sind abgeschlossen
    assert inv["bezahlt"] and inv["bezahlt_am"] == inv["datum"]   # Zahlungsdatum unbekannt → Rechnungsdatum


def test_download_zip(client):
    a = neue_rechnung(client, nummer="037")
    b = neue_rechnung(client, nummer="038")
    zf = zipfile.ZipFile(io.BytesIO(client.get(f"/api/rechnungen/download?ids={a},{b}").data))
    assert len(zf.namelist()) == 2


def test_paperless_eingangsordner(client, tmp_path):
    ordner = tmp_path / "consume"
    ordner.mkdir()
    inv_id = neue_rechnung(client)
    assert client.post("/api/paperless", json={"ids": [inv_id]}).status_code == 400   # nicht aktiviert
    client.put("/api/einstellungen", json={"paperless_installiert": True, "paperless_eingangsordner": str(ordner)})
    r = client.post("/api/paperless", json={"ids": [inv_id]}).get_json()
    assert r["ok"] == [inv_id]
    assert [p.name for p in ordner.iterdir()] == ["Rechnung_037_011126.pdf"]
    inv = client.get(f"/api/rechnungen/{inv_id}").get_json()
    assert inv["paperless_am"] and inv["festgeschrieben"]

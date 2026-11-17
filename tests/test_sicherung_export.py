"""Datensicherung (Backup/Wiederherstellung) und Export für den Steuerberater."""
import csv
import io
import os
import zipfile

from conftest import neue_rechnung


def test_sicherung_und_wiederherstellung(client, tmp_path):
    neue_rechnung(client, nummer="037")
    r = client.get("/api/backup")
    assert r.mimetype == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    assert set(zf.namelist()) == {"rechnungen.db", "info.json"}
    sicherung = r.data

    # Danach weiterarbeiten …
    neue_rechnung(client, nummer="038")
    client.put("/api/einstellungen", json={"name": "Neuer Name"})
    assert len(client.get("/api/rechnungen").get_json()) == 2

    # … und die Sicherung wieder einspielen
    r = client.post("/api/backup", data={"datei": (io.BytesIO(sicherung), "sicherung.zip")},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["anzahl"]["rechnungen"] == 1
    assert [x["nummer"] for x in client.get("/api/rechnungen").get_json()] == ["037"]
    assert client.get("/api/einstellungen").get_json()["name"] == "Max Beispiel"
    # vorheriger Stand wurde automatisch gesichert
    assert os.path.exists(r.get_json()["vorher_gesichert"])


def test_ungueltige_sicherung(client):
    for inhalt, name in ((b"kein backup", "x.db"), (b"PK\x03\x04kaputt", "x.zip")):
        r = client.post("/api/backup", data={"datei": (io.BytesIO(inhalt), name)}, content_type="multipart/form-data")
        assert r.status_code == 400
    assert client.get("/api/rechnungen").status_code == 200   # Datenbank unverändert nutzbar


def test_export_fuer_steuerberater(client):
    bezahlt = neue_rechnung(client, nummer="037", datum="2026-03-01", preis=960)
    client.patch(f"/api/rechnungen/{bezahlt}/bezahlt", json={"bezahlt": True})
    neue_rechnung(client, nummer="038", datum="2026-04-01", preis=450)
    storniert = neue_rechnung(client, nummer="039", datum="2026-05-01", preis=300)
    client.post(f"/api/rechnungen/{storniert}/stornieren")
    neue_rechnung(client, nummer="030", datum="2025-12-01", preis=100)   # anderes Jahr

    r = client.get("/api/export?jahr=2026")
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    namen = zf.namelist()
    assert "Rechnungen_2026.csv" in namen
    assert sorted(n for n in namen if n.startswith("PDFs/"))[:3] == [
        "PDFs/Rechnung_037_010326.pdf", "PDFs/Rechnung_038_010426.pdf", "PDFs/Rechnung_039_010526.pdf"]
    assert len([n for n in namen if n.startswith("PDFs/")]) == 4   # 037, 038, 039 + Storno 040

    text = zf.read("Rechnungen_2026.csv").decode("utf-8")
    assert text.startswith("﻿")
    zeilen = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))
    daten = {z[0]: z for z in zeilen[1:] if z and z[0].isdigit()}
    assert daten["037"][6] == "bezahlt" and daten["037"][7]
    assert daten["038"][6] == "offen"
    assert daten["039"][6] == "storniert" and daten["039"][8] == "storniert durch 040"
    assert daten["040"][6] == "Storno" and daten["040"][5] == "-300,00"
    assert "030" not in daten
    summe = next(z for z in zeilen if z and z[0].startswith("Summe"))
    assert summe[5] == "1410,00"   # 960 + 450 + 300 - 300


def test_erinnerung_merkt_letzte_sicherung(client):
    s = client.get("/api/absender").get_json()["sicherung"]
    assert s == {"letzte": None, "erinnerung_tage": 30, "automatisch": None}
    sicherung = client.get("/api/backup").data
    letzte = client.get("/api/absender").get_json()["sicherung"]["letzte"]
    assert letzte and letzte[:10] == __import__("datetime").date.today().isoformat()
    # Einspielen einer (älteren) Sicherung dreht den Zeitpunkt nicht zurück
    import db
    db.save_settings({"_letzte_sicherung": "2099-01-01T10:00:00"})
    client.post("/api/backup", data={"datei": (io.BytesIO(sicherung), "s.zip")}, content_type="multipart/form-data")
    assert client.get("/api/absender").get_json()["sicherung"]["letzte"] == "2099-01-01T10:00:00"
    # 0 = keine Erinnerung ist erlaubt, negative Werte nicht
    assert client.put("/api/einstellungen", json={"sicherung_erinnerung_tage": 0}).status_code == 200
    assert client.get("/api/absender").get_json()["sicherung"]["erinnerung_tage"] == 0
    assert client.put("/api/einstellungen", json={"sicherung_erinnerung_tage": -1}).status_code == 400


def test_desktop_kennt_automatische_sicherung(app_modul, client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_modul, "DESKTOP", True)
    ordner = tmp_path / "Sicherungen"
    ordner.mkdir(exist_ok=True)
    for tag in ("2026-11-15", "2026-11-17", "2026-11-16"):
        (ordner / f"rechnungen_{tag}.db").write_bytes(b"")
    (ordner / "vor-wiederherstellung_2026-12-01_10-00-00.db").write_bytes(b"")
    assert client.get("/api/absender").get_json()["sicherung"]["automatisch"] == "2026-11-17"

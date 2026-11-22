"""Umsatzsteuer für Nutzer ohne Kleinunternehmerregelung: Netto + USt = Brutto, je Beleg gespeichert."""
import csv
import io
import zipfile

from conftest import KUNDE, neue_rechnung, pdf_text

import pdf

UST = {"kleinunternehmer": False, "ust_satz": 19, "steuernummer": "12/345/67890"}


def text(client, url):
    return " ".join(pdf_text(client.get(url).data).split())


def test_rechnung_mit_umsatzsteuer(client):
    client.put("/api/einstellungen", json=UST)
    inv = neue_rechnung(client, preis=1000)
    r = client.get(f"/api/rechnungen/{inv}").get_json()
    assert r["gesamt"] == 1190 and r["ust_satz"] == 19 and not r["kleinunternehmer"]
    t = text(client, f"/api/rechnungen/{inv}/pdf")
    assert "Nettobetrag 1.000,- Euro" in t and "zzgl. 19 % Umsatzsteuer 190,- Euro" in t
    assert "Gesamtbetrag 1.190,- Euro" in t and "§ 19" not in t and "§19" not in t
    # GiroCode und Mahnung verwenden den Bruttobetrag
    assert "EUR1190.00" in pdf.girocode_fuer_rechnung(r, {"name": "Max", "iban": "DE00 1234"})
    m = client.post(f"/api/rechnungen/{inv}/mahnung").get_json()
    assert "1.190,- Euro" in text(client, f"/api/mahnungen/{m['id']}/pdf")


def test_cent_betraege_und_anderer_satz(client):
    client.put("/api/einstellungen", json=UST | {"ust_satz": 7})
    inv = neue_rechnung(client, preis=99.99)
    assert client.get(f"/api/rechnungen/{inv}").get_json()["gesamt"] == 106.99   # 99,99 + 7,00
    assert "zzgl. 7 % Umsatzsteuer 7,- Euro" in text(client, f"/api/rechnungen/{inv}/pdf")


def test_einstellung_aendert_alte_belege_nicht(client):
    alt = neue_rechnung(client, nummer="037", preis=500)          # Kleinunternehmer (Standard)
    client.put("/api/einstellungen", json=UST | {"schon_verschickt": []})  # Entwurf da, Absender geändert → Antwort auf die Rückfrage
    neu = neue_rechnung(client, nummer="038", preis=500)
    assert client.get(f"/api/rechnungen/{alt}").get_json()["gesamt"] == 500
    assert client.get(f"/api/rechnungen/{neu}").get_json()["gesamt"] == 595
    assert "Umsatzsteuer" not in text(client, f"/api/rechnungen/{alt}/pdf")


def test_storno_angebot_und_export(client):
    client.put("/api/einstellungen", json=UST)
    inv = neue_rechnung(client, nummer="037", datum="2026-03-01", preis=1000)
    client.post(f"/api/rechnungen/{inv}/festschreiben")
    storno = client.post(f"/api/rechnungen/{inv}/stornieren").get_json()["id"]
    s = client.get(f"/api/rechnungen/{storno}").get_json()
    assert s["gesamt"] == -1190 and s["ust_satz"] == 19
    assert "zzgl. 19 % Umsatzsteuer -190,- Euro" in text(client, f"/api/rechnungen/{storno}/pdf")
    a = client.post("/api/angebote", json={"nummer": "010", "datum": "2026-03-01", "kunde": KUNDE,
                                           "positionen": [{"beschreibung": "DJ", "preis": 500}]}).get_json()["id"]
    assert client.get(f"/api/angebote/{a}").get_json()["gesamt"] == 595
    assert "Gesamtbetrag 595,- Euro" in text(client, f"/api/angebote/{a}/pdf")
    zf = zipfile.ZipFile(io.BytesIO(client.get("/api/export?jahr=2026").data))
    zeilen = list(csv.reader(io.StringIO(zf.read("Rechnungen_2026.csv").decode("utf-8").lstrip("﻿")), delimiter=";"))
    sp = {n: i for i, n in enumerate(zeilen[0])}
    z = next(z for z in zeilen if z and z[0] == "037")
    assert (z[sp["Netto (EUR)"]], z[sp["USt-Satz"]], z[sp["USt (EUR)"]], z[sp["Betrag (EUR)"]]) == \
        ("1000,00", "19 %", "190,00", "1190,00")


def test_fehlende_absenderdaten(client):
    client.put("/api/einstellungen", json={"strasse": "", "plz_ort": ""})
    abs_ = client.get("/api/absender").get_json()
    assert not abs_["vollstaendig"] and abs_["fehlt"] == ["Straße", "PLZ und Ort"]
    client.put("/api/einstellungen", json={"strasse": "Musterweg 1", "plz_ort": "12345 Musterstadt"})
    assert client.get("/api/absender").get_json()["vollstaendig"] is True        # Kleinunternehmer: keine StNr nötig
    client.put("/api/einstellungen", json={"kleinunternehmer": False})
    abs_ = client.get("/api/absender").get_json()
    assert abs_["fehlt"] == ["Steuernummer oder USt-IdNr."] and not abs_["vollstaendig"]
    client.put("/api/einstellungen", json={"ust_idnr": "DE123456789"})
    assert client.get("/api/absender").get_json()["vollstaendig"] is True
    inv = neue_rechnung(client)
    assert "USt-IdNr.: DE123456789" in text(client, f"/api/rechnungen/{inv}/pdf")

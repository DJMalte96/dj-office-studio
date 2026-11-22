"""Pflichtangaben auf Rechnungen: vollständige Kundenanschrift, Lieferdatum, §19-Hinweis mit Stichtag."""
from conftest import KUNDE, neue_rechnung, pdf_text

import pdf

POS = {"beschreibung": "DJ – Tätigkeit Hochzeit", "lieferdatum": "2026-11-14", "preis": 960}
ZB = "Bitte innerhalb der nächsten 8 Tage überweisen."


def rechnung(client, kunde=KUNDE, positionen=(POS,), nummer="037", datum="2026-11-20"):
    return client.post("/api/rechnungen", json={"nummer": nummer, "datum": datum, "kunde": kunde,
                                                 "positionen": list(positionen), "zahlungsbedingung": ZB})


def test_kundenanschrift_ist_pflicht(client):
    r = rechnung(client, kunde={"name": "Anna Muster", "ort": "Musterstadt"})
    assert r.status_code == 400 and "Straße, PLZ fehlt" in r.get_json()["error"]
    assert rechnung(client).status_code == 201


def test_lieferdatum_ist_pflicht(client):
    r = rechnung(client, positionen=[POS, {"beschreibung": "Fahrtkosten", "preis": 60}])
    assert r.status_code == 400 and "Lieferdatum" in r.get_json()["error"] and "Fahrtkosten" in r.get_json()["error"]


def test_auch_beim_aendern_aber_nicht_in_vorschau_und_angebot(client):
    inv = neue_rechnung(client)
    r = client.put(f"/api/rechnungen/{inv}", json={"nummer": "037", "datum": "2026-11-20", "kunde": {"name": "Anna"},
                                                   "positionen": [POS], "zahlungsbedingung": ZB})
    assert r.status_code == 400
    # PDF-Vorschau geht auch unvollständig (zum Ausprobieren)
    r = client.post("/api/vorschau", json={"kunde": {"name": "Anna"}, "zahlungsbedingung": ZB,
                                           "positionen": [{"beschreibung": "DJ", "preis": 5}]})
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    # Angebote dürfen ohne Anschrift und Datum sein
    r = client.post("/api/angebote", json={"nummer": "010", "datum": "2026-11-20", "kunde": {"name": "Anna"},
                                           "positionen": [{"beschreibung": "DJ", "preis": 500}]})
    assert r.status_code == 201


def test_hinweis19_ab_stichtag(client):
    client.put("/api/einstellungen", json={"kleinunternehmer": True})
    alt = neue_rechnung(client, nummer="036", datum="2026-11-17")
    neu = neue_rechnung(client, nummer="037", datum=pdf.HINWEIS19_STICHTAG)
    text_alt = " ".join(pdf_text(client.get(f"/api/rechnungen/{alt}/pdf").data).split())
    text_neu = " ".join(pdf_text(client.get(f"/api/rechnungen/{neu}/pdf").data).split())
    assert "nicht umsatzsteuerpflichtig" in text_alt and "Steuerbefreiung" not in text_alt
    assert "Steuerbefreiung nach § 19 UStG" in text_neu and "nicht umsatzsteuerpflichtig" not in text_neu
    # Mahnungen richten sich nach ihrem eigenen Datum (heute)
    from datetime import date
    m = client.post(f"/api/rechnungen/{alt}/mahnung").get_json()
    erwartet = pdf.hinweis19(date.today().isoformat())[0]
    assert erwartet in " ".join(pdf_text(client.get(f"/api/mahnungen/{m['id']}/pdf").data).split())
    # Umschalten ändert gespeicherte Rechnungen nicht – neue Rechnungen ohne Kleinunternehmer haben keinen Hinweis
    client.put("/api/einstellungen", json={"kleinunternehmer": False, "steuernummer": "12/345/67890", "schon_verschickt": []})  # Entwurf da, Absender geändert → Antwort auf die Rückfrage
    assert "Steuerbefreiung" in " ".join(pdf_text(client.get(f"/api/rechnungen/{neu}/pdf").data).split())
    neuer = neue_rechnung(client, nummer="038", datum=pdf.HINWEIS19_STICHTAG)
    text = pdf_text(client.get(f"/api/rechnungen/{neuer}/pdf").data)
    assert "§ 19" not in text and "§19" not in text

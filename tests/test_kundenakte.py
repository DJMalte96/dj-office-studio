"""Seit 1.14: Vertrag → Feier → Rechnung, „Bar bezahlt“ (Quittung von Hand) und die Jahres-Erinnerung der Kundenakte."""
import csv
import io
import os
import zipfile

from conftest import KUNDE
from test_abschluss import Y, _abschliessen, jahr  # noqa: F401  (Fixture)

HOCHZEIT = "DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def angebot(client, nummer="012", preis=1250, feier="2027-06-13"):
    r = client.post("/api/angebote", json={"nummer": nummer, "datum": "2026-11-20", "gueltig_bis": "2026-12-20", "kunde": KUNDE,
                                           "positionen": [{"beschreibung": HOCHZEIT, "lieferdatum": feier, "preis": preis}]})
    return r.get_json()["id"]


def bar(client, **felder):
    return client.post("/api/barzahlungen", data={k: str(v) for k, v in felder.items() if k != "beleg"} |
                       ({"beleg": felder["beleg"]} if "beleg" in felder else {}), content_type="multipart/form-data")


def angebot_status(client, aid):
    return next(a for a in client.get("/api/angebote").get_json() if a["id"] == aid)["status"]


# ---------- Bar bezahlt ----------

def test_bar_bezahlt_aus_angebot(client):
    aid = angebot(client)
    r = bar(client, angebot_id=aid, betrag="1.250,00", datum="2026-11-22", quittung_nr="0347")
    assert r.status_code == 201, r.get_json()
    b = r.get_json()
    assert (b["betrag"], b["datum"], b["quittung_nr"], b["anlass"], b["feier_datum"]) == (1250, "2026-11-22", "0347", "Hochzeit", "2027-06-13")
    assert b["kunde"]["name"] == "Anna Muster" and b["angebot_id"] == aid and b["ust_satz"] is None and not b["hat_beleg"]
    assert angebot_status(client, aid) == "angenommen"            # bar bezahlt heißt angenommen
    assert [x["id"] for x in client.get("/api/barzahlungen").get_json()] == [b["id"]]

    # zählt als Einnahme: EÜR, Grenze der Kleinunternehmerregelung
    e = client.get("/api/finanzen/euer?jahr=2026").get_json()
    zeilen = {z["id"]: z["betrag"] for z in e["einnahmen_zeilen"]}
    assert zeilen["bar"] == 1250 and e["einnahmen"] == 1250 and e["monate"][10]["einnahmen"] == 1250
    assert e["grenzen"]["umsatz"] == 1250
    assert client.get("/api/finanzen/euer?jahr=2027").get_json()["einnahmen"] == 0   # Feier 2027 – Geld kam 2026


def test_bar_bezahlt_aus_vertrag_mit_umsatzsteuer(client):
    client.put("/api/einstellungen", json={"kleinunternehmer": False, "steuernummer": "1", "ust_satz": 19})
    v = client.post("/api/vertraege", json={}).get_json()["vertrag"]
    client.put(f"/api/vertraege/{v['id']}", json={"kunde": {"name": "Carla Test", "ort": "Testdorf"}, "anlass": "Geburtstagsfeier",
                                                 "datum": "2026-10-03", "gage": 595})
    b = bar(client, vertrag_id=v["id"], betrag=595, datum="2026-10-03").get_json()
    assert (b["vertrag_id"], b["anlass"], b["feier_datum"], b["ust_satz"], b["kunde"]["name"]) == \
        (v["id"], "Geburtstagsfeier", "2026-10-03", 19, "Carla Test")
    zeilen = {z["id"]: z["betrag"] for z in client.get("/api/finanzen/euer?jahr=2026").get_json()["einnahmen_zeilen"]}
    assert zeilen["bar"] == 500 and zeilen["umsatzsteuer"] == 95


def test_bar_bezahlt_ohne_vertrag_und_angebot(client):
    assert bar(client, betrag=200, datum="2026-05-01").status_code == 400            # Kunde fehlt
    r = bar(client, betrag=200, datum="2026-05-01", kunde='{"name": "Ben Beispiel", "ort": "Musterstadt"}', anlass="Grillfest")
    assert r.status_code == 201 and r.get_json()["kunde"]["name"] == "Ben Beispiel" and r.get_json()["anlass"] == "Grillfest"


def test_bar_bezahlt_pruefungen(client):
    aid = angebot(client)
    for falsch in ({"betrag": 0}, {"betrag": "viel"}, {"betrag": -5}, {"datum": "2026-02-30"}, {"datum": ""}):
        assert bar(client, **({"angebot_id": aid, "betrag": 100, "datum": "2026-11-22"} | falsch)).status_code == 400
    assert bar(client, angebot_id=999, betrag=100, datum="2026-11-22").status_code == 404
    assert bar(client, vertrag_id=999, betrag=100, datum="2026-11-22").status_code == 404
    # Foto vom Durchschlag: nur echte Bilder/PDFs, Endung muss zum Inhalt passen
    for name, inhalt in (("quittung.php", PNG), ("quittung.png", b"<html><script>alert(1)</script>"), ("quittung.pdf.html", PNG)):
        assert bar(client, angebot_id=aid, betrag=100, datum="2026-11-22", beleg=(io.BytesIO(inhalt), name)).status_code == 400
    assert client.get("/api/barzahlungen").get_json() == []
    assert angebot_status(client, aid) != "angenommen"             # abgelehnte Eingabe ändert nichts


def test_foto_vom_durchschlag(client, app_modul):
    import db
    aid = angebot(client)
    b = bar(client, angebot_id=aid, betrag=500, datum="2026-11-22", beleg=(io.BytesIO(PNG), "durchschlag.png")).get_json()
    assert b["hat_beleg"]
    r = client.get(f"/api/barzahlungen/{b['id']}/beleg")
    assert r.data == PNG and r.mimetype == "image/png" and "attachment" in r.headers["Content-Disposition"]
    ordner = os.path.join(db.DATA_DIR, "barzahlungen")
    assert len(os.listdir(ordner)) == 1

    # im Export: Zeile in Einnahmen und das Foto
    zf = zipfile.ZipFile(io.BytesIO(client.get("/api/export?jahr=2026").data))
    zeilen = list(csv.reader(io.StringIO(zf.read("Einnahmen_2026.csv").decode("utf-8").lstrip("﻿")), delimiter=";"))
    zeile = next(z for z in zeilen if z[1] == "Bar bezahlt (Quittung von Hand)")
    assert zeile[0] == "2026-11-22" and zeile[3] == "Anna Muster" and zeile[4] == "500,00" and "Hochzeit" in zeile[2]
    fotos = [n for n in zf.namelist() if n.startswith("Barzahlungen/")]
    assert len(fotos) == 1 and zf.read(fotos[0]) == PNG and fotos[0] in zeile[2]

    # Löschen entfernt das Foto
    assert client.delete(f"/api/barzahlungen/{b['id']}").status_code == 204
    assert os.listdir(ordner) == [] and client.get(f"/api/barzahlungen/{b['id']}/beleg").status_code == 404
    assert client.delete(f"/api/barzahlungen/{b['id']}").status_code == 404


def test_sicherung_enthaelt_barzahlungen(client, app_modul):
    import db
    b = bar(client, angebot_id=angebot(client), betrag=500, datum="2026-11-22", beleg=(io.BytesIO(PNG), "d.png")).get_json()
    sicherung = client.get("/api/backup").data
    assert any(n.startswith("barzahlungen/") for n in zipfile.ZipFile(io.BytesIO(sicherung)).namelist())
    client.delete(f"/api/barzahlungen/{b['id']}")
    r = client.post("/api/backup", data={"datei": (io.BytesIO(sicherung), "s.zip")}, content_type="multipart/form-data")
    assert r.status_code == 200
    assert client.get(f"/api/barzahlungen/{b['id']}/beleg").data == PNG
    assert os.path.isdir(os.path.join(db.DATA_DIR, "barzahlungen"))


def test_abgeschlossenes_jahr_gesperrt(client, jahr):   # noqa: F811
    b = bar(client, betrag=300, datum=f"{Y}-08-01", kunde='{"name": "Ben Beispiel"}').get_json()
    _abschliessen(client)
    assert bar(client, betrag=100, datum=f"{Y}-09-01", kunde='{"name": "Ben Beispiel"}').status_code == 409
    assert client.delete(f"/api/barzahlungen/{b['id']}").status_code == 409
    liste = client.get("/api/barzahlungen").get_json()
    assert len(liste) == 1 and liste[0]["gesperrt"]
    import db
    import sqlite3
    try:   # auch am Server vorbei (Trigger)
        with db.connect() as con:
            con.execute("DELETE FROM barzahlungen")
        assert False, "Trigger fehlt"
    except sqlite3.IntegrityError:
        pass


# ---------- Vertrag → Rechnung ----------

def test_rechnung_aus_vertrag_gehoert_zu_vertrag_und_angebot(client):
    aid = angebot(client)
    v = client.post("/api/vertraege", json={"angebot_id": aid}).get_json()["vertrag"]
    r = client.post("/api/rechnungen", json={"nummer": "040", "datum": "2027-06-14", "kunde": KUNDE, "vertrag_id": v["id"],
                                            "zahlungsbedingung": "x", "positionen": [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-06-13", "preis": 1250}]})
    assert r.status_code == 201, r.get_json()
    inv = client.get(f"/api/rechnungen/{r.get_json()['id']}").get_json()
    assert inv["vertrag_id"] == v["id"] and inv["angebot_id"] == aid
    assert angebot_status(client, aid) == "angenommen"


def test_rechnung_aus_angebot_mit_vertrag_findet_den_vertrag(client):
    aid = angebot(client)
    v = client.post("/api/vertraege", json={"angebot_id": aid}).get_json()["vertrag"]
    r = client.post("/api/rechnungen", json={"nummer": "040", "datum": "2027-06-14", "kunde": KUNDE, "angebot_id": aid,
                                            "zahlungsbedingung": "x", "positionen": [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-06-13", "preis": 1250}]})
    inv = client.get(f"/api/rechnungen/{r.get_json()['id']}").get_json()
    assert inv["vertrag_id"] == v["id"]
    # Bearbeiten ohne vertrag_id behält die Verknüpfung
    client.put(f"/api/rechnungen/{inv['id']}", json={"nummer": "040", "datum": "2027-06-14", "kunde": KUNDE, "zahlungsbedingung": "x",
                                                    "positionen": [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-06-13", "preis": 1300}]})
    assert client.get(f"/api/rechnungen/{inv['id']}").get_json()["vertrag_id"] == v["id"]


def test_rechnung_ohne_vertrag(client):
    r = client.post("/api/rechnungen", json={"nummer": "040", "datum": "2026-11-01", "kunde": KUNDE, "vertrag_id": 77,
                                            "zahlungsbedingung": "x", "positionen": [{"beschreibung": "DJ", "lieferdatum": "2026-10-31", "preis": 100}]})
    assert r.status_code == 201, r.get_json()
    assert client.get(f"/api/rechnungen/{r.get_json()['id']}").get_json()["vertrag_id"] is None


# ---------- Jahres-Erinnerung ----------

def test_erinnerung_ausblenden(client):
    assert client.get("/api/kunden/erinnerung").get_json() == {}
    assert client.put("/api/kunden/erinnerung", json={"name": "  Anna   Muster ", "ruhe": "2027-06-13"}).status_code == 204
    assert client.put("/api/kunden/erinnerung", json={"name": "Ben Beispiel", "ruhe": "nie"}).status_code == 204
    assert client.get("/api/kunden/erinnerung").get_json() == {"anna muster": "2027-06-13", "ben beispiel": "nie"}
    client.put("/api/kunden/erinnerung", json={"name": "ANNA MUSTER", "ruhe": "nie"})
    client.put("/api/kunden/erinnerung", json={"name": "Ben Beispiel", "ruhe": None})          # wieder einschalten
    assert client.get("/api/kunden/erinnerung").get_json() == {"anna muster": "nie"}
    for falsch in ({"name": "", "ruhe": "nie"}, {"name": "X", "ruhe": "morgen"}, {"name": "X", "ruhe": "2027-13-01"}):
        assert client.put("/api/kunden/erinnerung", json=falsch).status_code == 400

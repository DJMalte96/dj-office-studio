"""Finanzen – EÜR: Zufluss/Abfluss, Stornos, Privatanteil, Fahrten, Abschreibung, Prüfliste, Umsatzsteuer."""
import io

from conftest import KUNDE

ZB = "Bitte innerhalb der nächsten 8 Tage überweisen."


def rechnung(client, nummer, datum, preis, bezahlt_am=None):
    r = client.post("/api/rechnungen", json={"nummer": nummer, "datum": datum, "kunde": KUNDE, "zahlungsbedingung": ZB,
                                             "fahrt_erfassen": False,
                                             "positionen": [{"beschreibung": "DJ", "lieferdatum": datum, "preis": preis}]})
    inv = r.get_json()["id"]
    if bezahlt_am:
        client.patch(f"/api/rechnungen/{inv}/bezahlt", json={"bezahlt": True})
        assert client.put(f"/api/rechnungen/{inv}/bezahlt_am", json={"bezahlt_am": bezahlt_am}).status_code == 204
    return inv


def ausgabe(client, datum, betrag, kategorie, **extra):
    r = client.post("/api/ausgaben", json={"belegdatum": datum, "lieferant": "Shop", "betrag": betrag, "kategorie": kategorie,
                                           "notiz": "Testbeleg", **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def test_euer_kleinunternehmer(client):
    rechnung(client, "037", "2026-10-31", 960, bezahlt_am="2026-11-05")      # zählt 2026
    rechnung(client, "038", "2026-11-14", 450)                                # offen → zählt nicht
    rechnung(client, "030", "2025-12-20", 800, bezahlt_am="2026-01-05")      # Rechnung 2025, bezahlt 2026 → zählt 2026
    rechnung(client, "029", "2025-11-15", 700, bezahlt_am="2025-11-20")      # bezahlt 2025 → nicht 2026
    bezahlt_storniert = rechnung(client, "039", "2026-02-01", 300, bezahlt_am="2026-02-10")
    client.post(f"/api/rechnungen/{bezahlt_storniert}/stornieren")           # Storno in 2026 → −300 (Erstattung)
    offen_storniert = rechnung(client, "041", "2026-03-01", 500)
    client.post(f"/api/rechnungen/{offen_storniert}/festschreiben")
    client.post(f"/api/rechnungen/{offen_storniert}/stornieren")             # nie bezahlt → keine Geldbewegung
    client.post("/api/einnahmen", json={"datum": "2026-06-01", "beschreibung": "Altes Mischpult verkauft", "betrag": "100"})

    ausgabe(client, "2026-11-01", 29.99, "musik")
    ausgabe(client, "2026-11-14", 54.80, "technik")
    ausgabe(client, "2026-04-01", 40.00, "telefon", privatanteil=50)          # nur 20 € betrieblich
    ausgabe(client, "2026-03-12", 2380, "anschaffung", beschreibung="Aktivboxen (Paar)")   # → Abschreibung 283,33
    ausgabe(client, "2025-12-30", 99, "technik")                              # Vorjahr
    neu = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(b"%PDF-1.4 leer"), "neu.pdf")]},
                      content_type="multipart/form-data").get_json()
    assert neu["neu"]                                                         # ungeprüft → zählt nicht
    client.post("/api/fahrten", json={"datum": "2026-10-31", "ziel": "Feldweg 3, 12350 Lindenau", "km_einfach": 31})

    e = client.get("/api/finanzen/euer?jahr=2026").get_json()
    ein = {z["id"]: z["betrag"] for z in e["einnahmen_zeilen"]}
    aus = {z["id"]: z["betrag"] for z in e["ausgaben_zeilen"]}
    assert ein == {"rechnungen": 960 + 800 + 300 - 300, "sonstige": 100.0}   # 039 bezahlt und erstattet → null
    assert aus == {"musik": 29.99, "technik": 54.80, "telefon": 20.0, "afa": 283.33, "fahrten": 18.6}
    assert e["einnahmen"] == 1860.0 and e["ausgaben"] == 406.72 and e["gewinn"] == 1453.28
    assert e["anzahl_rechnungen"] == 3
    monat = {m["monat"]: m for m in e["monate"]}
    import datetime
    storno_monat = datetime.date.today().month                              # Storno trägt das heutige Datum
    assert monat[1]["einnahmen"] == 800 and monat[2]["einnahmen"] == 300
    assert sum(m["einnahmen"] for m in e["monate"]) == 1860.0
    erwartet_nov = 960 - (300 if storno_monat == 11 else 0)     # November: 960 €, ggf. abzüglich Storno
    assert monat[11]["einnahmen"] == erwartet_nov and monat[6]["einnahmen"] == 100   # sonstige Einnahme im Juni
    stufen = {p["text"].split(" ")[0] + p["stufe"] for p in e["pruefliste"]}
    assert "1warn" in stufen                                                  # 1 Beleg noch nicht geprüft
    assert any(p["stufe"] == "info" and "noch offen" in p["text"] for p in e["pruefliste"])


def test_betriebsfahrzeug_ohne_kilometerpauschale_und_tankbeleg_warnung(client):
    client.post("/api/fahrten", json={"datum": "2026-10-31", "ziel": "X", "km_einfach": 31})
    ausgabe(client, "2026-10-01", 60, "fahrzeug")
    e = client.get("/api/finanzen/euer?jahr=2026").get_json()
    assert {z["id"] for z in e["ausgaben_zeilen"]} == {"fahrzeug", "fahrten"}
    assert any("Tankbelege" in p["text"] and p["stufe"] == "warn" for p in e["pruefliste"])
    client.put("/api/einstellungen", json={"fahrzeug": "betrieb"})
    e = client.get("/api/finanzen/euer?jahr=2026").get_json()
    assert {z["id"] for z in e["ausgaben_zeilen"]} == {"fahrzeug"} and e["fahrtkosten"] == 0


def test_umsatzsteuerpflichtig_netto_mit_steuerzeilen(client):
    client.put("/api/einstellungen", json={"kleinunternehmer": False, "steuernummer": "1"})
    rechnung(client, "037", "2026-05-01", 1000, bezahlt_am="2026-05-10")     # 1.190 brutto
    ausgabe(client, "2026-05-02", 119, "technik", ust_satz=19)
    e = client.get("/api/finanzen/euer?jahr=2026").get_json()
    ein = {z["id"]: z["betrag"] for z in e["einnahmen_zeilen"]}
    aus = {z["id"]: z["betrag"] for z in e["ausgaben_zeilen"]}
    assert ein == {"rechnungen": 1000.0, "umsatzsteuer": 190.0} and aus == {"technik": 100.0, "vorsteuer": 19.0}
    assert e["gewinn"] == 1071.0


def test_bezahlt_datum_nachtragen(client):
    inv = rechnung(client, "037", "2026-05-01", 500)
    import db
    with db.connect() as con:                                                 # wie ein alter Import: bezahlt, aber ohne Datum
        con.execute("UPDATE rechnungen SET bezahlt = 1, bezahlt_am = NULL WHERE id = ?", (inv,))
    assert [r["nummer"] for r in client.get("/api/finanzen/ohne-bezahltdatum").get_json()] == ["037"]
    assert client.get("/api/finanzen/euer?jahr=2026").get_json()["einnahmen"] == 0
    assert client.put(f"/api/rechnungen/{inv}/bezahlt_am", json={"bezahlt_am": "x"}).status_code == 400
    client.put(f"/api/rechnungen/{inv}/bezahlt_am", json={"bezahlt_am": "2026-05-20"})
    assert client.get("/api/finanzen/euer?jahr=2026").get_json()["einnahmen"] == 500


def test_bezahlt_datum_bei_allen_aus_rechnungsdatum(client):
    a = rechnung(client, "037", "2026-05-01", 500)
    b = rechnung(client, "038", "2025-12-20", 300)
    c = rechnung(client, "039", "2026-06-01", 200, bezahlt_am="2026-06-15")   # hat schon ein Datum → bleibt
    offen = rechnung(client, "040", "2026-07-01", 100)                         # offen → bleibt ohne Datum
    import db
    with db.connect() as con:
        con.execute("UPDATE rechnungen SET bezahlt = 1, bezahlt_am = NULL WHERE id IN (?, ?)", (a, b))
    assert client.post("/api/finanzen/bezahlt-am-rechnungsdatum").get_json() == {"anzahl": 2}
    assert client.get("/api/finanzen/ohne-bezahltdatum").get_json() == []
    daten = {r["id"]: r["bezahlt_am"] for r in client.get("/api/rechnungen").get_json()}
    assert daten[a] == "2026-05-01" and daten[b] == "2025-12-20" and daten[c] == "2026-06-15" and daten[offen] is None
    assert client.get("/api/finanzen/euer?jahr=2026").get_json()["einnahmen"] == 700


def test_export_enthaelt_finanzen_und_belege(client):
    import csv
    import zipfile
    from pathlib import Path
    rechnung(client, "037", "2026-10-31", 960, bezahlt_am="2026-11-05")
    mail = (Path(__file__).parent / "beispiele" / "mails" / "beatport.eml").read_bytes()
    a = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(mail), "beatport.eml")]},
                    content_type="multipart/form-data").get_json()["neu"][0]
    client.put(f"/api/ausgaben/{a['id']}", json={"uebernehmen": True})
    ausgabe(client, "2026-03-12", 2380, "anschaffung", beschreibung="Aktivboxen (Paar)")
    client.post("/api/fahrten", json={"datum": "2026-10-31", "ziel": "Feldweg 3, 12350 Lindenau", "km_einfach": 31})
    r = client.get("/api/export?jahr=2026")
    assert 'filename="Export_2026.zip"' in r.headers["Content-Disposition"]
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    namen = set(zf.namelist())
    assert {"Rechnungen_2026.csv", "EUeR_2026.csv", "Einnahmen_2026.csv", "Ausgaben_2026.csv", "Fahrten_2026.csv",
            "Anlagenverzeichnis_2026.csv"} <= namen
    beleg = "Belege/2026-10-31_Beatport_5,33.eml"
    assert beleg in namen and zf.read(beleg) == mail
    def lesen(n):
        return list(csv.reader(io.StringIO(zf.read(n).decode("utf-8").lstrip("﻿")), delimiter=";"))
    euer_csv = {(z[0], z[1]): z[-1] for z in lesen("EUeR_2026.csv") if len(z) >= 4}
    assert euer_csv[("Betriebseinnahmen", "Summe")] == "960,00" and euer_csv[("Betriebsausgaben", "Abschreibungen")] == "283,33"
    assert euer_csv[("Gewinn", "")] == "652,74"     # 960 − 5,33 (Beatport) − 283,33 (Abschreibung) − 18,60 (Fahrt)
    aus = lesen("Ausgaben_2026.csv")
    beatport = next(z for z in aus if z[2] == "Beatport")
    assert beatport[9] == "2026-10-31_Beatport_5,33.eml" and [z[0] for z in aus[1:]] == sorted(z[0] for z in aus[1:])
    assert lesen("Anlagenverzeichnis_2026.csv")[1][:2] == ["Aktivboxen (Paar)", "2026-03-12"]
    assert lesen("Fahrten_2026.csv")[1][7] == "62"

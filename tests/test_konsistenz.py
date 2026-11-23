"""Logik-Stichprobe mit Zufallsdaten: Passen Monatswerte, Jahressummen, Export und Kennzahlen der Startseite zusammen?"""
import csv
import io
import random
import zipfile
from datetime import date, timedelta

import pytest

from conftest import KUNDE

JAHR = date.today().year - 1


def _zufall(client, seed, ku=True):
    rnd = random.Random(seed)
    client.put("/api/einstellungen", json={"kleinunternehmer": ku, "schon_verschickt": []})
    # gilt seit 1.8 nur fürs laufende Jahr – das Vorjahr gezielt umstellen
    client.put(f"/api/abschluss/{JAHR}/einstellungen", json={"kleinunternehmer": ku, "fahrzeug": "privat"})
    bezahlt = 0.0
    for i in range(rnd.randint(3, 12)):
        tag = date(JAHR, 1, 1) + timedelta(days=rnd.randint(0, 364))
        preis = round(rnd.uniform(50, 2000), 2)
        r = client.post("/api/rechnungen", json={
            "nummer": f"{seed}{i:03d}", "datum": tag.isoformat(), "kunde": KUNDE, "zahlungsbedingung": "8 Tage", "fahrt_erfassen": False,
            "positionen": [{"beschreibung": "DJ", "lieferdatum": tag.isoformat(), "preis": preis}]}).get_json()
        if rnd.random() < .8:
            am = min(tag + timedelta(days=rnd.randint(0, 40)), date(JAHR, 12, 31))
            client.patch(f"/api/rechnungen/{r['id']}/bezahlt", json={"bezahlt": True})
            client.put(f"/api/rechnungen/{r['id']}/bezahlt_am", json={"bezahlt_am": am.isoformat()})
            bezahlt += client.get(f"/api/rechnungen/{r['id']}").get_json()["gesamt"]
    for i in range(rnd.randint(2, 10)):
        tag = date(JAHR, 1, 1) + timedelta(days=rnd.randint(0, 364))
        client.post("/api/ausgaben", json={"belegdatum": tag.isoformat(), "lieferant": f"Laden {i}", "betrag": round(rnd.uniform(5, 700), 2),
                                           "kategorie": rnd.choice(["technik", "musik", "telefon", "buero", "werbung"]),
                                           "privatanteil": rnd.choice([0, 0, 20, 50]), "ust_satz": rnd.choice([None, 19, 7]),
                                           "beschreibung": "x", "notiz": "x"})
    for i in range(rnd.randint(0, 4)):
        client.post("/api/fahrten", json={"datum": (date(JAHR, 1, 1) + timedelta(days=rnd.randint(0, 364))).isoformat(), "ziel": "Ort",
                                          "km_einfach": rnd.randint(1, 80)})
    if rnd.random() < .7:
        client.post("/api/anlagen", json={"bezeichnung": "Gerät", "anschaffung_am": f"{JAHR}-{rnd.randint(1, 12):02d}-15",
                                          "kosten": round(rnd.uniform(900, 3000), 2), "nutzungsdauer": rnd.choice([1, 3, 5, 7])})
    if rnd.random() < .5:
        client.post("/api/einnahmen", json={"datum": f"{JAHR}-06-01", "beschreibung": "Verkauf", "betrag": "120"})
    return bezahlt


@pytest.mark.parametrize("seed", range(8))
def test_monate_ergeben_das_jahr(client, seed):
    bezahlt = _zufall(client, seed)
    e = client.get(f"/api/finanzen/euer?jahr={JAHR}").get_json()
    assert round(sum(m["einnahmen"] for m in e["monate"]), 2) == e["einnahmen"]
    assert round(sum(m["ausgaben"] for m in e["monate"]), 2) == e["ausgaben"]
    assert round(e["einnahmen"] - e["ausgaben"], 2) == e["gewinn"]
    assert round(sum(z["betrag"] for z in e["einnahmen_zeilen"]), 2) == e["einnahmen"]
    assert round(sum(z["betrag"] for z in e["ausgaben_zeilen"]), 2) == e["ausgaben"]
    rechnungen = next(z["betrag"] for z in e["einnahmen_zeilen"] if z["id"] == "rechnungen")
    assert round(rechnungen, 2) == round(bezahlt, 2)       # Kleinunternehmer: brutto = Zahlungseingang


@pytest.mark.parametrize("seed", range(4))
def test_umsatzsteuerpflichtig_gewinn_stimmt(client, seed):
    _zufall(client, 100 + seed, ku=False)
    e = client.get(f"/api/finanzen/euer?jahr={JAHR}").get_json()
    assert e["kleinunternehmer"] is False
    assert round(e["einnahmen"] - e["ausgaben"], 2) == e["gewinn"]
    assert round(sum(z["betrag"] for z in e["einnahmen_zeilen"]), 2) == e["einnahmen"]
    assert round(sum(z["betrag"] for z in e["ausgaben_zeilen"]), 2) == e["ausgaben"]


@pytest.mark.parametrize("seed", range(4))
def test_export_entspricht_der_euer(client, seed):
    _zufall(client, 200 + seed)
    e = client.get(f"/api/finanzen/euer?jahr={JAHR}").get_json()
    zf = zipfile.ZipFile(io.BytesIO(client.get(f"/api/export?jahr={JAHR}").data))
    zeilen = list(csv.reader(io.StringIO(zf.read(f"EUeR_{JAHR}.csv").decode("utf-8-sig")), delimiter=";"))
    gewinn = next(z for z in zeilen if z and z[0] == "Gewinn")[3]
    assert float(gewinn.replace(",", ".")) == e["gewinn"]
    aus = list(csv.reader(io.StringIO(zf.read(f"Ausgaben_{JAHR}.csv").decode("utf-8-sig")), delimiter=";"))[1:]
    with_kat = client.get(f"/api/ausgaben?jahr={JAHR}").get_json()
    assert len(aus) == len([a for a in with_kat if a["status"] == "ok"])

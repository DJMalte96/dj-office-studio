"""1.8.0 Jahresabschluss: prüfen, Paket mit Prüfsumme, Sperre auf allen Wegen, wieder öffnen, Einstellungen je Jahr."""
import hashlib
import io
import json
import zipfile
from datetime import date

import pytest
from pypdf import PdfReader

from conftest import neue_rechnung

Y = date.today().year - 1          # Vorjahr: lässt sich (nach dem 10. Januar) abschließen
HEUTE_JAHR = Y + 1


def _euer(client, jahr=Y):
    d = client.get(f"/api/finanzen/euer?jahr={jahr}").get_json()
    return {k: d[k] for k in ("einnahmen", "ausgaben", "gewinn", "einnahmen_zeilen", "ausgaben_zeilen", "afa", "fahrtkosten")}


@pytest.fixture
def jahr(client, app_modul, monkeypatch):
    """Ein fertiges Vorjahr: bezahlte und offene Rechnung, Ausgaben, Fahrt, Gerät (gekauft im Jahr davor), Einnahme."""
    import abschluss
    if date.today() < abschluss.abschliessbar_ab(Y):   # 1.–10. Januar: Frist ein paar Tage weiterdrehen
        monkeypatch.setattr(abschluss, "abschliessbar_ab", lambda j: date(int(j) + 1, 1, 1))
    r1 = neue_rechnung(client, nummer="101", datum=f"{Y}-03-01", preis=1000, bezahlt=True)
    assert client.put(f"/api/rechnungen/{r1}/bezahlt_am", json={"bezahlt_am": f"{Y}-03-10"}).status_code == 204
    r2 = neue_rechnung(client, nummer="102", datum=f"{Y}-10-01", preis=500)
    r3 = neue_rechnung(client, nummer="103", datum=f"{Y}-12-20", preis=300, bezahlt=True)
    client.put(f"/api/rechnungen/{r3}/bezahlt_am", json={"bezahlt_am": f"{HEUTE_JAHR}-01-05"})
    aus = client.post("/api/ausgaben", json={"belegdatum": f"{Y}-04-01", "lieferant": "Kabelwelt", "betrag": 119,
                                             "kategorie": "technik", "beschreibung": "Kabel", "notiz": "Beleg per Post"}).get_json()
    tel = client.post("/api/ausgaben", json={"belegdatum": f"{Y}-12-30", "lieferant": "Mobilfunk Muster", "betrag": 29.99,
                                             "kategorie": "telefon", "beschreibung": "Januar", "notiz": "Lastschrift"}).get_json()
    weg = client.post("/api/ausgaben", json={"belegdatum": f"{Y}-05-01", "lieferant": "Doppelt", "betrag": 10,
                                             "kategorie": "buero", "beschreibung": "x", "notiz": "x"}).get_json()
    client.delete(f"/api/ausgaben/{weg['id']}")      # liegt vor dem Abschluss im Papierkorb
    anl = client.post("/api/anlagen", json={"bezeichnung": "Mischpult", "anschaffung_am": f"{Y - 1}-06-01",
                                            "kosten": 1200, "nutzungsdauer": 3}).get_json()
    ein = client.post("/api/einnahmen", json={"datum": f"{Y}-06-01", "beschreibung": "Altes Kabel", "betrag": "100"}).get_json()
    fahrt = client.post("/api/fahrten", json={"datum": f"{Y}-05-01", "ziel": "Feldweg 3, 12350 Lindenau", "km_einfach": 20}).get_json()
    for f in client.get(f"/api/fahrten?jahr={Y}").get_json()["fahrten"]:   # automatische Fahrten der Rechnungen: km nachtragen
        if f["km_einfach"] is None:
            client.put(f"/api/fahrten/{f['id']}", json={"km_einfach": 7})
    return {"r1": r1, "r2": r2, "r3": r3, "aus": aus["id"], "tel": tel["id"], "weg": weg["id"], "anl": anl["id"],
            "ein": ein["id"], "fahrt": fahrt["id"]}


def _abschliessen(client, jahr=Y):
    r = client.post(f"/api/abschluss/{jahr}", json={"bestaetigt": True})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# ---------- Ablauf ----------

def test_pruefung_und_abschluss(client, jahr, app_modul, tmp_path):
    p = client.get(f"/api/abschluss/{Y}/pruefung").get_json()
    assert p["offen"] == 0 and p["status"]["status"] == "offen"
    arten = {x.get("art") for x in p["punkte"]}
    assert {"offen", "zehn_tage", "einstellungen"} <= arten
    assert any("103" in x["text"] and str(HEUTE_JAHR) in x["klein"] for x in p["punkte"])   # bezahlt im Folgejahr: Hinweis
    assert p["zahlen"]["gewinn"] == _euer(client)["gewinn"] and p["vorjahr"]["afa"] == 233.33   # Kauf im Juni: 7 von 36 Monaten

    assert client.post(f"/api/abschluss/{Y}", json={}).status_code == 400     # ohne Bestätigung nicht
    vorher = _euer(client)
    st = _abschliessen(client)
    assert st["status"] == "zu" and st["aktuell"]["fassung"] == 1 and not st["abweichung"]

    paket = client.get(f"/api/abschluss/{Y}/paket")
    assert paket.status_code == 200 and f"Jahresabschluss_{Y}_Fassung_1.zip" in paket.headers["Content-Disposition"]
    zf = zipfile.ZipFile(io.BytesIO(paket.data))
    namen = set(zf.namelist())
    assert {"Abschlussblatt.pdf", "Pruefsummen.txt", "abschluss.json", f"EUeR_{Y}.csv", f"Rechnungen_{Y}.csv",
            f"Ausgaben_{Y}.csv", f"Fahrten_{Y}.csv", f"Anlagenverzeichnis_{Y}.csv"} <= namen
    assert any(n.startswith("PDFs/") for n in namen)
    # Prüfsumme nachrechnen: über alle Dateien außer Blatt und Liste
    zeilen = [f"{hashlib.sha256(zf.read(n)).hexdigest()}  {n}" for n in sorted(namen - {"Abschlussblatt.pdf", "Pruefsummen.txt"})]
    summe = hashlib.sha256(("\n".join(zeilen) + "\n").encode()).hexdigest()
    assert summe == st["aktuell"]["pruefsumme"]
    assert summe in zf.read("Pruefsummen.txt").decode()
    blatt = "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(zf.read("Abschlussblatt.pdf"))).pages)
    assert f"Jahresabschluss {Y}" in blatt and summe in blatt.replace("\n", "") and "Fassung 1" in blatt
    daten = json.loads(zf.read("abschluss.json"))
    assert daten["euer"]["gewinn"] == vorher["gewinn"] and daten["kleinunternehmer"] is True
    assert client.get(f"/api/abschluss/{Y}/blatt").data[:5] == b"%PDF-"
    assert (tmp_path / "abschluesse" / f"Jahresabschluss_{Y}_Fassung_1.zip").is_file()
    assert client.post(f"/api/abschluss/{Y}", json={"bestaetigt": True}).status_code == 409    # nicht doppelt


def test_rote_punkte_verhindern_abschluss(client, jahr):
    client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(b"%PDF-1.4 kaputt"), "neu.pdf")]},
                content_type="multipart/form-data")
    p = client.get(f"/api/abschluss/{Y}/pruefung").get_json()
    assert p["offen"] == 1 and any(x["stufe"] == "rot" and x["aktion"] == "ausgaben" for x in p["punkte"])
    r = client.post(f"/api/abschluss/{Y}", json={"bestaetigt": True})
    assert r.status_code == 409 and "rot markierten" in r.get_json()["error"]


def test_laufendes_jahr_nicht_abschliessbar(client):
    st = client.get(f"/api/abschluss/{HEUTE_JAHR}/pruefung").get_json()["status"]
    assert st["status"] == "laeuft" and st["abschliessbar_ab"] == f"{HEUTE_JAHR + 1}-01-11"
    r = client.post(f"/api/abschluss/{HEUTE_JAHR}", json={"bestaetigt": True})
    assert r.status_code == 409 and "erst ab dem 11.01." in r.get_json()["error"]


def test_nie_von_selbst_gesperrt(client, jahr):
    """Ein vergangenes Jahr bleibt offen und änderbar, bis man es selbst abschließt."""
    assert client.get("/api/abschluss").get_json()["hinweis"] == Y
    assert client.put(f"/api/ausgaben/{jahr['aus']}", json={"betrag": 120}).status_code == 200


# ---------- Sperre: jede Änderung am abgeschlossenen Jahr wird abgewiesen, die EÜR bleibt auf den Cent gleich ----------

AENDERUNGEN = {
    "Bezahlt-Haken entfernen": lambda c, j: c.patch(f"/api/rechnungen/{j['r1']}/bezahlt", json={"bezahlt": False}),
    "Bezahlt-Datum ins Folgejahr": lambda c, j: c.put(f"/api/rechnungen/{j['r1']}/bezahlt_am", json={"bezahlt_am": f"{HEUTE_JAHR}-02-01"}),
    "Bezahlt-Datum ins abgeschlossene Jahr": lambda c, j: c.put(f"/api/rechnungen/{j['r3']}/bezahlt_am", json={"bezahlt_am": f"{Y}-12-28"}),
    "Rechnung mit Fahrt im Jahr anlegen": lambda c, j: c.post("/api/rechnungen", json={
        "nummer": "190", "datum": f"{Y}-11-11", "kunde": {"name": "Nachzügler", "strasse": "Weg 1", "plz": "12345", "ort": "Ort"},
        "zahlungsbedingung": "8 Tage", "positionen": [{"beschreibung": "DJ", "lieferdatum": f"{Y}-11-11", "preis": 100}]}),
    "Offene Rechnung bearbeiten (Fahrt im Jahr)": lambda c, j: c.put(f"/api/rechnungen/{j['r2']}", json={
        **c.get(f"/api/rechnungen/{j['r2']}").get_json(), "positionen": [{"beschreibung": "DJ", "lieferdatum": f"{Y}-10-01", "preis": 600}]}),
    "Offene Rechnung löschen (Fahrt im Jahr)": lambda c, j: c.delete(f"/api/rechnungen/{j['r2']}"),
    "Betrag einer Ausgabe": lambda c, j: c.put(f"/api/ausgaben/{j['aus']}", json={"betrag": 1}),
    "Kategorie einer Ausgabe": lambda c, j: c.put(f"/api/ausgaben/{j['aus']}", json={"kategorie": "musik"}),
    "Ausgabe ins Folgejahr datieren": lambda c, j: c.put(f"/api/ausgaben/{j['aus']}", json={"bezahlt_am": f"{HEUTE_JAHR}-01-02"}),
    "Ausgabe löschen (Papierkorb)": lambda c, j: c.delete(f"/api/ausgaben/{j['aus']}"),
    "Ausgabe aus dem Papierkorb holen": lambda c, j: c.post(f"/api/papierkorb/{j['weg']}/wiederherstellen"),
    "Neue Ausgabe im Jahr": lambda c, j: c.post("/api/ausgaben", json={"belegdatum": f"{Y}-07-01", "lieferant": "Spät", "betrag": 5,
                                                                    "kategorie": "buero", "beschreibung": "x", "notiz": "x"}),
    "10-Tage-Regel ins Folgejahr": lambda c, j: c.put(f"/api/ausgaben/{j['tel']}/euer-jahr", json={"jahr": HEUTE_JAHR}),
    "Kilometer einer Fahrt": lambda c, j: c.put(f"/api/fahrten/{j['fahrt']}", json={"km_einfach": 99}),
    "Fahrt löschen": lambda c, j: c.delete(f"/api/fahrten/{j['fahrt']}"),
    "Fahrt im Jahr ergänzen": lambda c, j: c.post("/api/fahrten", json={"datum": f"{Y}-08-01", "ziel": "Ort", "km_einfach": 3}),
    "Nutzungsdauer eines Geräts": lambda c, j: c.put(f"/api/anlagen/{j['anl']}", json={"nutzungsdauer": 5}),
    "Gerät löschen": lambda c, j: c.delete(f"/api/anlagen/{j['anl']}"),
    "Gerät im Jahr anlegen": lambda c, j: c.post("/api/anlagen", json={"bezeichnung": "Boxen", "anschaffung_am": f"{Y}-09-01",
                                                                        "kosten": 900, "nutzungsdauer": 3}),
    "Gerät im Jahr verkaufen": lambda c, j: c.put(f"/api/anlagen/{j['anl']}", json={"abgang_am": f"{Y}-12-01", "abgang_erloes": 500}),
    "Sonstige Einnahme im Jahr": lambda c, j: c.post("/api/einnahmen", json={"datum": f"{Y}-02-02", "beschreibung": "x", "betrag": "50"}),
    "Sonstige Einnahme löschen": lambda c, j: c.delete(f"/api/einnahmen/{j['ein']}"),
    "Kleinunternehmer im Jahr ausschalten": lambda c, j: c.put(f"/api/abschluss/{Y}/einstellungen",
                                                               json={"kleinunternehmer": False, "fahrzeug": "privat"}),
    "Fahrten nachberechnen im Jahr": lambda c, j: c.post("/api/fahrten/nachberechnen", json={"jahr": Y}),
}


@pytest.mark.parametrize("name", list(AENDERUNGEN))
def test_sperre(client, jahr, name, app_modul):
    if name == "Fahrten nachberechnen im Jahr":   # braucht eine Rechnung ohne Fahrt
        with app_modul.db.connect() as con:
            con.execute("DELETE FROM fahrten WHERE rechnung_id = ?", (jahr["r2"],))
    _abschliessen(client)
    vorher = _euer(client)
    r = AENDERUNGEN[name](client, jahr)
    assert r.status_code == 409, (name, r.status_code, r.get_json())
    assert str(Y) in r.get_json()["error"] and r.get_json()["gesperrt"] == [Y]
    assert _euer(client) == vorher, name
    assert client.get(f"/api/abschluss/{Y}/pruefung").get_json()["status"]["abweichung"] is False


def test_wieder_geoeffnet_geht_alles_wieder(client, jahr):
    _abschliessen(client)
    assert client.post(f"/api/abschluss/{Y}/oeffnen", json={"grund": "  "}).status_code == 400
    st = client.post(f"/api/abschluss/{Y}/oeffnen", json={"grund": "Beleg nachgereicht · Rechnung vom Musikhaus fehlte"}).get_json()
    assert st["status"] == "offen" and st["fassungen"][0]["grund"] == "Beleg nachgereicht · Rechnung vom Musikhaus fehlte"
    zuletzt = ("Bezahlt-Haken entfernen", "Gerät löschen")    # danach gingen andere Schritte nicht mehr
    for name in [n for n in AENDERUNGEN if n not in zuletzt] + list(zuletzt):
        aenderung = AENDERUNGEN[name]
        if name == "Fahrten nachberechnen im Jahr":
            continue
        assert aenderung(client, jahr).status_code in (200, 201, 204), name
    assert client.get("/api/abschluss").get_json()["gruende"] == ["Rechnung vom Musikhaus fehlte"]   # eigener Grund gemerkt


def test_zweite_fassung_zeigt_grund_und_differenz(client, jahr):
    _abschliessen(client)
    client.post(f"/api/abschluss/{Y}/oeffnen", json={"grund": "Beleg nachgereicht"})
    client.post("/api/ausgaben", json={"belegdatum": f"{Y}-12-28", "lieferant": "Musikhaus", "betrag": 70,
                                       "kategorie": "technik", "beschreibung": "Ständer", "notiz": "x"})
    st = _abschliessen(client)
    assert st["aktuell"]["fassung"] == 2 and [f["fassung"] for f in st["fassungen"]] == [1, 2]
    blatt = "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(client.get(f"/api/abschluss/{Y}/blatt").data)).pages)
    assert "Fassung 1" in blatt and "Fassung 2" in blatt and "Beleg nachgereicht" in blatt and "70,00" in blatt
    erste = zipfile.ZipFile(io.BytesIO(client.get(f"/api/abschluss/{Y}/paket?fassung=1").data))
    assert json.loads(erste.read("abschluss.json"))["fassung"] == 1      # das alte Paket bleibt


# ---------- Was weitergeht ----------

def test_erlaubt_bleibt(client, jahr):
    _abschliessen(client)
    vorher = _euer(client)
    # offene Rechnung des Jahres heute bezahlen → zählt im Zahlungsjahr
    assert client.patch(f"/api/rechnungen/{jahr['r2']}/bezahlt", json={"bezahlt": True}).status_code == 204
    # Notiz einer Ausgabe, Mahnung, Storno, Lesen, Export
    assert client.put(f"/api/ausgaben/{jahr['aus']}", json={"notiz": "Beleg liegt im Ordner"}).status_code == 200
    assert client.post(f"/api/rechnungen/{jahr['r1']}/stornieren").status_code == 201
    assert client.get(f"/api/export?jahr={Y}").status_code == 200
    # Gerät aus dem Vorvorjahr im laufenden Jahr verkaufen
    assert client.put(f"/api/anlagen/{jahr['anl']}", json={"abgang_am": f"{HEUTE_JAHR}-02-01", "abgang_erloes": 300}).status_code == 200
    # Neues im laufenden Jahr
    assert client.post("/api/ausgaben", json={"belegdatum": f"{HEUTE_JAHR}-02-01", "lieferant": "Neu", "betrag": 5,
                                              "kategorie": "buero", "beschreibung": "x", "notiz": "x"}).status_code == 201
    assert _euer(client) == vorher


def test_listen_kennzeichnen_gesperrtes(client, jahr):
    _abschliessen(client)
    aus = {a["id"]: a for a in client.get(f"/api/ausgaben?jahr={Y}").get_json()}
    assert aus[jahr["aus"]]["gesperrt"] is True
    assert all(f["gesperrt"] for f in client.get(f"/api/fahrten?jahr={Y}").get_json()["fahrten"])
    assert all(e["gesperrt"] for e in client.get(f"/api/einnahmen?jahr={Y}").get_json())
    anl = client.get(f"/api/anlagen?jahr={HEUTE_JAHR}").get_json()[0]
    assert anl["gesperrt"] is True and anl["abgang_gesperrt"] is False
    r = {x["id"]: x for x in client.get("/api/rechnungen").get_json()}
    assert r[jahr["r1"]]["gesperrt"] and not r[jahr["r2"]]["gesperrt"] and not r[jahr["r3"]]["gesperrt"]
    assert client.get(f"/api/ausgaben/{jahr['aus']}").get_json()["gesperrt"] is True


# ---------- 10-Tage-Regel ----------

def test_zehn_tage_regel(client, jahr):
    vorher, folge = _euer(client), _euer(client, HEUTE_JAHR)
    r = client.put(f"/api/ausgaben/{jahr['tel']}/euer-jahr", json={"jahr": HEUTE_JAHR})
    assert r.status_code == 200 and r.get_json()["jahr"] == str(HEUTE_JAHR)
    assert round(vorher["ausgaben"] - _euer(client)["ausgaben"], 2) == 29.99
    assert round(_euer(client, HEUTE_JAHR)["ausgaben"] - folge["ausgaben"], 2) == 29.99
    assert jahr["tel"] in [a["id"] for a in client.get(f"/api/ausgaben?jahr={HEUTE_JAHR}").get_json()]
    assert client.put(f"/api/ausgaben/{jahr['tel']}/euer-jahr", json={"jahr": Y}).get_json()["jahr"] == str(Y)
    assert client.put(f"/api/ausgaben/{jahr['aus']}/euer-jahr", json={"jahr": HEUTE_JAHR}).status_code == 400   # April: nein
    assert client.put(f"/api/ausgaben/{jahr['tel']}/euer-jahr", json={"jahr": Y - 1}).status_code == 400


# ---------- Kleinunternehmer und Fahrzeug je Jahr ----------

def test_einstellungen_wirken_nicht_zurueck(client, jahr, app_modul):
    import abschluss
    vorher = _euer(client)
    r = client.put("/api/einstellungen", json={"kleinunternehmer": False, "fahrzeug": "betrieb", "schon_verschickt": []}).get_json()
    assert any("gelten ab" in h for h in r["hinweise"])
    assert _euer(client) == vorher                      # Vorjahr: weiter Kleinunternehmer mit Privatauto
    st = client.get("/api/abschluss").get_json()
    vj = next(x for x in st["jahre"] if x["jahr"] == Y)
    assert vj["kleinunternehmer"] is True and vj["fahrzeug"] == "privat"
    assert client.get(f"/api/finanzen/euer?jahr={HEUTE_JAHR}").get_json()["kleinunternehmer"] is False
    # offenes Vorjahr lässt sich gezielt ändern, das laufende nicht hier
    assert client.put(f"/api/abschluss/{Y}/einstellungen", json={"kleinunternehmer": True, "fahrzeug": "betrieb"}).status_code == 200
    assert _euer(client)["fahrtkosten"] == 0
    assert client.put(f"/api/abschluss/{HEUTE_JAHR}/einstellungen", json={"kleinunternehmer": True, "fahrzeug": "privat"}).status_code == 400
    assert abschluss.jahre_festhalten() == 0             # schon alle vergangenen Jahre festgehalten


def test_jahre_festhalten_beim_update(app_modul, client):
    import abschluss
    neue_rechnung(client, nummer="050", datum=f"{Y - 2}-05-01")
    n = abschluss.jahre_festhalten()
    with app_modul.db.connect() as con:
        jahre = {r[0] for r in con.execute("SELECT jahr FROM jahr_einstellungen")}
    assert n >= 3 and {Y - 2, Y - 1, Y} <= jahre and HEUTE_JAHR not in jahre


# ---------- Sicherung, Datenbank, Hintergrund ----------

def test_sicherung_nimmt_abschluss_mit(client, jahr, app_modul, tmp_path):
    _abschliessen(client)
    sicherung = client.get("/api/backup").data
    assert f"abschluesse/Jahresabschluss_{Y}_Fassung_1.zip" in zipfile.ZipFile(io.BytesIO(sicherung)).namelist()
    client.post(f"/api/abschluss/{Y}/oeffnen", json={"grund": "Test"})
    (tmp_path / "abschluesse" / f"Jahresabschluss_{Y}_Fassung_1.zip").unlink()
    r = client.post("/api/backup", data={"datei": (io.BytesIO(sicherung), "s.zip")}, content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()
    assert client.get(f"/api/abschluss/{Y}/pruefung").get_json()["status"]["status"] == "zu"
    assert client.get(f"/api/abschluss/{Y}/paket").status_code == 200
    assert client.put(f"/api/ausgaben/{jahr['aus']}", json={"betrag": 1}).status_code == 409   # Trigger wieder aktiv


def test_trigger_nach_alter_sicherung(app_modul, client, jahr):
    """Eine Datenbank ohne Trigger (z. B. eine Sicherung von 1.7) bekommt sie beim Start."""
    _abschliessen(client)
    with app_modul.db.connect() as con:
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
            con.execute(f"DROP TRIGGER {name}")
    app_modul.db.init()
    assert client.put(f"/api/ausgaben/{jahr['aus']}", json={"betrag": 1}).status_code == 409


def test_hintergrund_berechnung_laesst_abgeschlossene_jahre(client, jahr, app_modul, monkeypatch):
    import finanzen
    with app_modul.db.connect() as con:
        con.execute("UPDATE fahrten SET km_einfach = NULL WHERE id = ?", (jahr["fahrt"],))   # vor dem Abschluss: Lücke
        con.execute("UPDATE fahrten SET km_einfach = 3 WHERE km_einfach IS NULL AND id != ?", (jahr["fahrt"],))
    monkeypatch.setattr(abschluss_mod(), "pruefung", lambda j: {"offen": 0, "punkte": []})
    _abschliessen(client)
    app_modul.db.save_settings({"kartendienst": True})
    anfragen = []
    monkeypatch.setattr(finanzen.strecken, "strecke_km", lambda *a: anfragen.append(a) or 42.0)
    assert finanzen.offene_berechnen() == 0
    assert anfragen == []                    # nicht einmal beim Kartendienst nachgefragt
    with app_modul.db.connect() as con:
        assert con.execute("SELECT km_einfach FROM fahrten WHERE id = ?", (jahr["fahrt"],)).fetchone()[0] is None


def abschluss_mod():
    import abschluss
    return abschluss


def test_abweichung_wird_erkannt(client, jahr, app_modul):
    _abschliessen(client)
    with app_modul.db.connect() as con:   # an der Sperre vorbei (z. B. Datenbank von Hand bearbeitet)
        con.execute("DROP TRIGGER sperre_ausgaben_aendern")
        con.execute("UPDATE ausgaben SET betrag = 1 WHERE id = ?", (jahr["aus"],))
    assert client.get(f"/api/finanzen/euer?jahr={Y}").status_code == 200
    assert client.get(f"/api/abschluss/{Y}/pruefung").get_json()["status"]["abweichung"] is True


def test_hinweis_ausblenden(client, jahr):
    assert client.get("/api/abschluss").get_json()["hinweis"] == Y
    assert client.post("/api/abschluss/hinweis-aus", json={"jahr": Y}).status_code == 204
    assert client.get("/api/abschluss").get_json()["hinweis"] is None


def test_paket_pfad_aus_der_datenbank_wird_geprueft(client, jahr, app_modul):
    """Der Pfad steht in der Datenbank – sie kann aus einer fremden Sicherung stammen: nur Dateien unter abschluesse/."""
    _abschliessen(client)
    for pfad in ("rechnungen.db", "../" + __import__("os").path.basename(app_modul.db.DATA_DIR) + "/rechnungen.db", "abschluesse/../rechnungen.db"):
        with app_modul.db.connect() as con:
            con.execute("UPDATE jahresabschluss SET datei = ?", (pfad,))
        assert client.get(f"/api/abschluss/{Y}/paket").status_code == 404, pfad


def test_datenbank_sperrt_auch_ohne_oberflaeche(client, jahr, app_modul):
    """Die Trigger sind das Sicherheitsnetz für Wege, die keine eigene Prüfung haben."""
    import db
    _abschliessen(client)
    for sql, werte in (("DELETE FROM rechnungen WHERE id = ?", (jahr["r1"],)),
                       (f"UPDATE jahr_einstellungen SET fahrzeug = 'betrieb' WHERE jahr = {Y}", ()),
                       (f"DELETE FROM jahr_einstellungen WHERE jahr = {Y}", ()),
                       ("UPDATE anlagen SET abgang_am = ? WHERE id = ?", (f"{Y}-06-01", jahr["anl"]))):
        with pytest.raises(Exception) as e:
            with db.connect() as con:
                con.execute(sql, werte)
        assert db.ist_gesperrt_fehler(e.value), sql
    with db.connect() as con:      # Spalten ohne Einfluss auf Beträge bleiben frei
        con.execute("UPDATE rechnungen SET paperless_am = '2026-01-01' WHERE id = ?", (jahr["r1"],))


def test_zweimal_oeffnen_behaelt_den_ersten_grund(client, jahr):
    _abschliessen(client)
    client.post(f"/api/abschluss/{Y}/oeffnen", json={"grund": "Erster Grund"})
    assert client.post(f"/api/abschluss/{Y}/oeffnen", json={"grund": "nochmal"}).status_code == 400   # ist schon offen
    _abschliessen(client)
    client.post(f"/api/abschluss/{Y}/oeffnen", json={"grund": "Zweiter Grund"})
    f = client.get(f"/api/abschluss/{Y}/pruefung").get_json()["status"]["fassungen"]
    assert [x["grund"] for x in f] == ["Erster Grund", "Zweiter Grund"]

"""Seit 1.11: Anzahlungs- und Schlussrechnung, Nachfrage zum Angebot."""
import csv
import io
import zipfile

from conftest import KUNDE, pdf_text
from test_mail import EINRICHTUNG, smtp  # noqa: F401  (Fixture)

HOCHZEIT = "DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr"


def rechnung(client, nummer, art="normal", positionen=None, kunde=KUNDE, angebot_id=None, erwartet=201, **extra):
    r = client.post("/api/rechnungen", json={
        "nummer": nummer, "datum": "2026-11-01", "kunde": kunde, "zahlungsbedingung": "Bitte innerhalb von 8 Tagen überweisen.",
        "rechnungsart": art, "angebot_id": angebot_id, "fahrt_erfassen": True,
        "positionen": positionen or [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}]} | extra)
    assert r.status_code == erwartet, r.get_json()
    return r.get_json()


def anzahlung(client, nummer="037", betrag=360, **kw):
    return rechnung(client, nummer, "anzahlung",
                    [{"beschreibung": "Anzahlung 30 % für DJ – Tätigkeit Hochzeit am 08.05.2027", "lieferdatum": "2027-05-08",
                      "preis": betrag}], **kw)["id"]


def abzug(aid, preis=-1):
    return {"beschreibung": "abzüglich Anzahlung laut Rechnung 037", "lieferdatum": "2027-05-08", "preis": preis, "anzahlung_id": aid}


def test_anzahlung_und_schlussrechnung(client):
    aid = anzahlung(client)
    a = client.get(f"/api/rechnungen/{aid}").get_json()
    assert a["rechnungsart"] == "anzahlung" and a["gesamt"] == 360 and not a["fahrt_erfassen"]
    assert "Anzahlungsrechnung Nr.: 037" in pdf_text(client.get(f"/api/rechnungen/{aid}/pdf").data)
    # Betrag des Abzugs kommt immer vom Server, nicht aus dem Browser
    sid = rechnung(client, "038", "schluss", [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(aid, -1)])["id"]
    s = client.get(f"/api/rechnungen/{sid}").get_json()
    assert s["gesamt"] == 840 and s["positionen"][1]["preis"] == -360 and s["positionen"][1]["anzahlung_id"] == aid
    t = pdf_text(client.get(f"/api/rechnungen/{sid}/pdf").data)
    assert "Schlussrechnung Nr.: 038" in t and "Restbetrag" in t and "abzüglich Anzahlung" in t


def test_anzahlung_nur_einmal_abziehbar(client):
    aid = anzahlung(client)
    rechnung(client, "038", "schluss", [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(aid)])
    f = rechnung(client, "039", "schluss", [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(aid)], erwartet=400)
    assert "schon in Rechnung 038 abgezogen" in f["error"]


def test_abzug_nur_von_echter_anzahlung_desselben_kunden(client):
    normal = rechnung(client, "037")["id"]
    f = rechnung(client, "038", "schluss", [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(normal)], erwartet=400)
    assert "gibt es nicht" in f["error"]
    aid = anzahlung(client, "039")
    fremd = KUNDE | {"name": "Jonas Beispiel"}
    f = rechnung(client, "040", "schluss", [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(aid)],
                 kunde=fremd, erwartet=400)
    assert "anderen Kunden" in f["error"]
    f = rechnung(client, "040", "normal", [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(aid)], erwartet=400)
    assert "nur in einer Schlussrechnung" in f["error"]
    f = rechnung(client, "040", "schluss", erwartet=400)
    assert "mindestens eine abgezogene Anzahlung" in f["error"]
    f = rechnung(client, "040", "schluss", [{"beschreibung": "Kleinigkeit", "lieferdatum": "2027-05-08", "preis": 100}, abzug(aid)], erwartet=400)
    assert "höher als die Schlussrechnung" in f["error"]
    assert rechnung(client, "040", "quatsch", erwartet=400)["error"].startswith("Unbekannte Rechnungsart")


def test_gebundene_anzahlung_ist_geschuetzt(client):
    aid = anzahlung(client)
    sid = rechnung(client, "038", "schluss", [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(aid)])["id"]
    assert client.delete(f"/api/rechnungen/{aid}").status_code == 409
    assert client.post(f"/api/rechnungen/{aid}/stornieren").status_code == 409
    r = client.put(f"/api/rechnungen/{aid}", json={"nummer": "037", "datum": "2026-11-01", "kunde": KUNDE, "zahlungsbedingung": "x",
                                                   "rechnungsart": "anzahlung", "positionen": [{"beschreibung": "Anzahlung", "lieferdatum": "2027-05-08", "preis": 500}]})
    assert r.status_code == 409
    # Schlussrechnung storniert → Anzahlung wieder frei; die Stornorechnung trägt keinen Anzahlungs-Bezug
    client.post(f"/api/rechnungen/{sid}/stornieren")
    storno = next(r for r in client.get("/api/rechnungen").get_json() if r["storno_von"] == sid)
    assert all("anzahlung_id" not in p for p in storno["positionen"])
    rechnung(client, "040", "schluss", [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(aid)])


def test_umsatzsteuer_abzug_netto(client):
    client.put("/api/einstellungen", json={"kleinunternehmer": False, "ust_satz": 19, "schon_verschickt": []})
    aid = anzahlung(client, betrag=300)                                  # 300 netto → 357 brutto
    assert client.get(f"/api/rechnungen/{aid}").get_json()["gesamt"] == 357
    sid = rechnung(client, "038", "schluss", [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1000}, abzug(aid)])["id"]
    s = client.get(f"/api/rechnungen/{sid}").get_json()
    assert s["positionen"][1]["preis"] == -300 and s["gesamt"] == 833    # (1000 − 300) × 1,19
    assert 357 + 833 == round(1000 * 1.19)


def test_angebot_bleibt_mit_anzahlung_verknuepft(client):
    ang = client.post("/api/angebote", json={"nummer": "010", "datum": "2026-10-01", "gueltig_bis": "2026-11-01", "kunde": KUNDE,
                                             "positionen": [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}]}).get_json()["id"]
    aid = anzahlung(client, angebot_id=ang)
    assert client.get(f"/api/rechnungen/{aid}").get_json()["angebot_id"] == ang
    a = client.get(f"/api/angebote/{ang}").get_json()
    assert a["status"] == "angenommen" and a["rechnung_id"] == aid
    sid = rechnung(client, "038", "schluss", [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(aid)],
                   angebot_id=ang)["id"]
    assert client.get(f"/api/angebote/{ang}").get_json()["rechnung_id"] == sid
    assert client.get(f"/api/rechnungen/{sid}").get_json()["angebot_id"] == ang
    rechnung(client, "039", angebot_id="1 OR 1=1")   # Unsinn wird ignoriert


def test_euer_zaehlt_anzahlung_und_rest(client):
    aid = anzahlung(client)
    client.patch(f"/api/rechnungen/{aid}/bezahlt", json={"bezahlt": True})
    client.put(f"/api/rechnungen/{aid}/bezahlt_am", json={"bezahlt_am": "2026-11-05"})
    sid = rechnung(client, "038", "schluss", [{"beschreibung": HOCHZEIT, "lieferdatum": "2026-11-20", "preis": 1200}, abzug(aid)])["id"]
    client.patch(f"/api/rechnungen/{sid}/bezahlt", json={"bezahlt": True})
    client.put(f"/api/rechnungen/{sid}/bezahlt_am", json={"bezahlt_am": "2026-11-22"})
    e = client.get("/api/finanzen/euer?jahr=2026").get_json()
    assert next(z["betrag"] for z in e["einnahmen_zeilen"] if z["id"] == "rechnungen") == 1200
    zf = zipfile.ZipFile(io.BytesIO(client.get("/api/export?jahr=2026").data))
    zeilen = list(csv.reader(io.StringIO(zf.read("Rechnungen_2026.csv").decode("utf-8-sig")), delimiter=";"))
    text = "\n".join(";".join(z) for z in zeilen)
    assert "Anzahlungsrechnung" in text and "Schlussrechnung, abzgl. Anzahlung 037" in text


def test_vorschau_schlussrechnung(client):
    aid = anzahlung(client)
    r = client.post("/api/vorschau", json={"nummer": "038", "datum": "2026-11-01", "kunde": KUNDE, "zahlungsbedingung": "x",
                                           "rechnungsart": "schluss",
                                           "positionen": [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(aid, 0)]})
    assert r.status_code == 200
    assert "Restbetrag" in pdf_text(r.data) and "840" in pdf_text(r.data)


def test_vorschau_einer_gespeicherten_schlussrechnung(client):
    aid = anzahlung(client)
    pos = [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}, abzug(aid)]
    sid = rechnung(client, "038", "schluss", pos)["id"]
    daten = {"nummer": "038", "datum": "2026-11-01", "kunde": KUNDE, "zahlungsbedingung": "x", "rechnungsart": "schluss", "positionen": pos}
    assert client.post("/api/vorschau", json=daten | {"id": sid}).status_code == 200
    assert client.post("/api/vorschau", json=daten).status_code == 400      # ohne Bezug: wirklich schon abgezogen


# ---------- Nachfrage zum Angebot ----------

def angebot(client):
    return client.post("/api/angebote", json={"nummer": "011", "datum": "2026-11-01", "gueltig_bis": "2026-12-01", "kunde": KUNDE,
                                              "positionen": [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-05-08", "preis": 1200}]}).get_json()["id"]


def test_nachfrage_per_mail(client, smtp):  # noqa: F811
    client.put("/api/einstellungen", json=EINRICHTUNG)
    aid = angebot(client)
    e = client.get(f"/api/versand/entwurf?art=nachfrage&id={aid}").get_json()
    assert e["betreff"] == "Kurze Nachfrage zu meinem Angebot 011"
    assert "Angebot 011 über 1.200,00 €" in e["text"].replace("1.200,- Euro", "1.200,00 €") or "Angebot 011" in e["text"]
    assert "bis zum 01.12.2026 frei" in e["text"] and e["anhaenge"] == ["Angebot_011_080527.pdf"]
    r = client.post("/api/versand", json={"art": "nachfrage", "id": aid, "an": "anna@example.de", "betreff": e["betreff"],
                                          "text": e["text"], "anhang": False})
    assert r.status_code == 200 and r.get_json()["anhaenge"] == []
    assert not smtp.gesendet[-1]["msg"].get_payload() or not any(
        p.get_filename() for p in smtp.gesendet[-1]["msg"].iter_attachments())
    a = client.get(f"/api/angebote/{aid}").get_json()
    assert a["nachgefragt_am"] and "anna@example.de" in a["nachgefragt_wie"]
    assert a["status"] == "offen" and a["versand"] == []      # das Angebot selbst gilt nicht als erneut verschickt


def test_nachfrage_von_hand_und_zuruecknehmen(client):
    aid = angebot(client)
    assert client.post(f"/api/angebote/{aid}/nachgefragt", json={"wie": "angerufen"}).status_code == 204
    assert client.get(f"/api/angebote/{aid}").get_json()["nachgefragt_wie"] == "angerufen"
    client.post(f"/api/angebote/{aid}/nachgefragt", json={"nachgefragt": False})
    a = client.get(f"/api/angebote/{aid}").get_json()
    assert a["nachgefragt_am"] is None and a["nachgefragt_wie"] is None
    assert client.post("/api/angebote/999/nachgefragt", json={}).status_code == 404


def test_nachfassen_tage_einstellbar(client):
    assert client.get("/api/einstellungen").get_json()["nachfassen_tage"] == 7
    client.put("/api/einstellungen", json={"nachfassen_tage": 0})
    assert client.get("/api/einstellungen").get_json()["nachfassen_tage"] == 0

"""Seit 1.16: Nachlass, Kunden zusammenführen, Vertrag vor Ort unterschreiben."""
import base64
import io

import pytest
from PIL import Image, ImageDraw

from conftest import KUNDE, pdf_text

POS = {"beschreibung": "DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr", "lieferdatum": "2026-11-21", "preis": 1200}


def beleg(client, positionen, art="rechnungen", nummer="037", kunde=KUNDE, **mehr):
    daten = {"nummer": nummer, "datum": "2026-11-22", "kunde": kunde, "positionen": positionen,
             "zahlungsbedingung": "Bitte innerhalb von 8 Tagen überweisen.", **mehr}
    if art == "angebote":
        daten |= {"gueltig_bis": "2026-12-22"}
    return client.post(f"/api/{art}", json=daten)


# ---------- Nachlass ----------

def test_nachlass_prozent_vom_server_berechnet(client):
    r = beleg(client, [POS, {"beschreibung": "Stammkundenrabatt 10 %", "preis": 999, "nachlass": {"art": "prozent", "wert": 10}}])
    assert r.status_code == 201, r.get_json()
    inv = client.get(f"/api/rechnungen/{r.get_json()['id']}").get_json()
    nl = inv["positionen"][1]
    assert nl["preis"] == -120 and nl["nachlass"] == {"art": "prozent", "wert": 10} and nl["lieferdatum"] == "2026-11-21"
    assert inv["gesamt"] == 1080
    t = pdf_text(client.get(f"/api/rechnungen/{inv['id']}/pdf").data)
    assert "Stammkundenrabatt 10 %" in t and "1.080,- Euro" in t


def test_nachlass_betrag_und_angebot_mit_umsatzsteuer(client):
    client.put("/api/einstellungen", json={"kleinunternehmer": False, "steuernummer": "1", "ust_satz": 19})
    r = beleg(client, [POS, {"beschreibung": "Nachlass", "nachlass": {"art": "betrag", "wert": "100,00"}}], art="angebote", nummer="012")
    assert r.status_code == 201, r.get_json()
    a = client.get(f"/api/angebote/{r.get_json()['id']}").get_json()
    assert a["positionen"][1]["preis"] == -100 and a["gesamt"] == round(1100 * 1.19, 2)


@pytest.mark.parametrize("nachlass, text", [
    ({"art": "prozent", "wert": 0}, "größer als 0"), ({"art": "prozent", "wert": 120}, "größer als 0"),
    ({"art": "betrag", "wert": 2000}, "höchstens"), ({"art": "irgendwas", "wert": 5}, "ungültig"), ({"art": "betrag", "wert": "viel"}, "Wert")])
def test_nachlass_pruefungen(client, nachlass, text):
    r = beleg(client, [POS, {"beschreibung": "Nachlass", "nachlass": nachlass}])
    assert r.status_code == 400 and text in r.get_json()["error"]


def test_nur_ein_nachlass(client):
    r = beleg(client, [POS, {"beschreibung": "A", "nachlass": {"art": "prozent", "wert": 5}}, {"beschreibung": "B", "nachlass": {"art": "prozent", "wert": 5}}])
    assert r.status_code == 400 and "nur einen" in r.get_json()["error"]


def test_nachlass_in_e_rechnung_gueltig(client):
    import erechnung
    import facturx
    client.put("/api/einstellungen", json={"steuernummer": "12/345/67890"})
    r = beleg(client, [POS, {"beschreibung": "Vereinsrabatt", "nachlass": {"art": "prozent", "wert": 15}}], erechnung=True,
              kunde={"name": "Sportverein e. V.", "strasse": "Sportplatz 1", "plz": "12345", "ort": "Musterstadt"})
    assert r.status_code == 201, r.get_json()
    xml = dict(erechnung.pdf_anhaenge(client.get(f"/api/rechnungen/{r.get_json()['id']}/pdf").data))["factur-x.xml"]
    assert facturx.xml_check_xsd(xml, flavor="factur-x", level="en16931") and erechnung.lesen(xml)["brutto"] == 1020


# ---------- Kunden zusammenführen ----------

def _kunden(client):
    return {k["name"]: k for k in client.get("/api/kunden").get_json()}


def test_duplikate_erkennen_und_zusammenfuehren(client):
    anna = dict(KUNDE)                                              # Anna Muster, Lindenweg 12, 12345 Musterstadt
    ana = dict(KUNDE, name="Ana Muster")                            # Tippfehler, gleiche Anschrift
    lea = {"name": "Lea Probe", "strasse": "Gartenstr. 8", "plz": "12360", "ort": "Birkenfeld"}
    for nr, k in (("037", anna), ("038", anna), ("039", ana), ("040", lea)):
        assert beleg(client, [POS], nummer=nr, kunde=k).status_code == 201
    angebot = beleg(client, [POS], art="angebote", nummer="012", kunde=ana).get_json()["id"]
    client.put(f"/api/kunden/{_kunden(client)['Ana Muster']['id']}/notiz", json={"notiz": "Parken hinterm Haus"})
    paare = client.get("/api/kunden/duplikate").get_json()
    assert len(paare) == 1 and {paare[0]["a"]["name"], paare[0]["b"]["name"]} == {"Anna Muster", "Ana Muster"}
    assert "Tippfehler" in paare[0]["grund"]
    k = _kunden(client)
    rechnungen_vorher = {r["id"]: (r["kunde"], r["gesamt"]) for r in client.get("/api/rechnungen").get_json()}
    r = client.post("/api/kunden/zusammenfuehren", json={"behalten": k["Anna Muster"]["id"], "weg": k["Ana Muster"]["id"]})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["verschoben"]["rechnungen"] == 1 and r.get_json()["weitere_namen"] == ["Ana Muster"]
    # keine Rechnung verschwindet, keine ändert sich – sie gehören nur zum verbleibenden Kunden
    nachher = client.get("/api/rechnungen").get_json()
    assert {x["id"]: (x["kunde"], x["gesamt"]) for x in nachher} == rechnungen_vorher
    assert sum(x["kunde_id"] == k["Anna Muster"]["id"] for x in nachher) == 3
    assert client.get(f"/api/angebote/{angebot}").get_json()["kunde_id"] == k["Anna Muster"]["id"]
    k2 = _kunden(client)
    assert "Ana Muster" not in k2 and k2["Anna Muster"]["notiz"] == "Parken hinterm Haus"
    assert client.get("/api/kunden/duplikate").get_json() == []


def test_kein_duplikat_merken(client):
    beleg(client, [POS], nummer="037", kunde=KUNDE)
    beleg(client, [POS], nummer="038", kunde=dict(KUNDE, ort="Musterstadt-Nord"))
    paare = client.get("/api/kunden/duplikate").get_json()
    assert len(paare) == 1
    assert client.post("/api/kunden/kein-duplikat", json={"a": paare[0]["b"]["id"], "b": paare[0]["a"]["id"]}).status_code == 204
    assert client.get("/api/kunden/duplikate").get_json() == []


def test_zusammenfuehren_auch_im_abgeschlossenen_jahr(client, app_modul):
    """Die Zuordnung ändert keinen Betrag – auch festgeschriebene Rechnungen wandern mit."""
    r1 = beleg(client, [POS], nummer="037").get_json()["id"]
    beleg(client, [POS], nummer="038", kunde=dict(KUNDE, name="Ana Muster"))
    client.patch(f"/api/rechnungen/{r1}/bezahlt", json={"bezahlt": True})          # festgeschrieben
    k = _kunden(client)
    r = client.post("/api/kunden/zusammenfuehren", json={"behalten": k["Ana Muster"]["id"], "weg": k["Anna Muster"]["id"]})
    assert r.status_code == 200, r.get_json()
    inv = client.get(f"/api/rechnungen/{r1}").get_json()
    assert inv["kunde"]["name"] == "Anna Muster" and inv["festgeschrieben"]          # Rechnung unverändert
    assert client.post("/api/kunden/zusammenfuehren", json={"behalten": 1, "weg": 1}).status_code == 400
    assert client.post("/api/kunden/zusammenfuehren", json={"behalten": 1, "weg": 999}).status_code == 404


# ---------- Vertrag vor Ort unterschreiben ----------

def _unterschrift(linie=True):
    b = Image.new("RGBA", (500, 170), (0, 0, 0, 0))
    if linie:
        ImageDraw.Draw(b).line([(40, 120), (120, 80), (200, 125), (320, 70), (420, 110)], fill=(20, 33, 61, 255), width=4)
    out = io.BytesIO()
    b.save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def _vertrag(client):
    v = client.post("/api/vertraege", json={}).get_json()["vertrag"]
    client.put(f"/api/vertraege/{v['id']}", json={"kunde": {"name": "Carla Test", "strasse": "Rosenstr. 8", "plz": "12347", "ort": "Testdorf"},
                                                 "anlass": "Geburtstagsfeier", "datum": "2027-03-20", "von": "19:00", "bis": "01:00", "gage": 650})
    return v["id"]


def test_vor_ort_unterschreiben(client):
    vid = _vertrag(client)
    leer = client.post(f"/api/vertraege/{vid}/unterschrieben", data={"weg": "hier", "am": "2026-11-26", "sig_kunde": _unterschrift(),
                                                                    "sig_dj": _unterschrift(False)}, content_type="multipart/form-data")
    assert leer.status_code == 400 and "beide" in leer.get_json()["error"]
    kaputt = client.post(f"/api/vertraege/{vid}/unterschrieben", data={"weg": "hier", "sig_kunde": "data:image/png;base64,PGh0bWw+",
                                                                      "sig_dj": _unterschrift()}, content_type="multipart/form-data")
    assert kaputt.status_code == 400
    r = client.post(f"/api/vertraege/{vid}/unterschrieben", data={"weg": "hier", "am": "2026-11-26", "ort": "Musterstadt",
                                                                 "sig_kunde": _unterschrift(), "sig_dj": _unterschrift()},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()
    j = client.get(f"/api/vertraege/{vid}").get_json()
    assert j["vertrag"]["status"] == "unterschrieben" and j["unterschriften"]["datum"] == "Musterstadt, 26.11.2026"
    bild = client.get("/" + j["unterschriften"]["kunde"])
    assert bild.mimetype == "image/png" and Image.open(io.BytesIO(bild.data)).size[0] < 500   # auf die Striche zugeschnitten
    pdf = client.get(f"/api/vertraege/{vid}/pdf").data
    assert pdf.count(b"/Subtype /Image") >= 2 and "Musterstadt, 26.11.2026 · Unterschrift Veranstalter" in pdf_text(pdf)
    assert client.get(f"/api/vertraege/{vid}/unterschrift/fremd").status_code == 404
    # Sicherung enthält die Bilder
    import zipfile
    namen = zipfile.ZipFile(io.BytesIO(client.get("/api/backup").data)).namelist()
    assert sum(n.startswith("vertraege/unterschrieben/") and n.endswith(".png") for n in namen) == 2

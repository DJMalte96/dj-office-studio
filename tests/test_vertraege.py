"""Seit 1.13: Booking-Verträge – aus Angebot oder frei, Vorlage, eigene Abschnitte, Hochladen, Anlagen, Versand, Unterschrift."""
import io
import zipfile

from conftest import KUNDE, pdf_text
from test_mail import EINRICHTUNG, smtp  # noqa: F401  (Fixture)

HOCHZEIT = "DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr"


def angebot(client, preis=1250):
    r = client.post("/api/angebote", json={"nummer": "012", "datum": "2026-11-20", "gueltig_bis": "2026-12-20", "kunde": KUNDE,
                                           "positionen": [{"beschreibung": HOCHZEIT, "lieferdatum": "2027-06-13", "preis": preis}]})
    return r.get_json()["id"]


def neu(client, **json):
    r = client.post("/api/vertraege", json=json)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def text(inhalt):
    return "\n".join(a["titel"] + "\n" + a.get("text", "") + "\n" + "\n".join(" ".join(z) for z in a.get("tabelle", []))
                     for a in inhalt["abschnitte"])


def test_vertrag_aus_angebot(client):
    aid = angebot(client)
    j = neu(client, angebot_id=aid)
    v, t = j["vertrag"], text(j["inhalt"])
    assert v["name"] == "Vertrag zu Angebot 012" and v["nummer"] == "V001" and v["status"] == "entwurf"
    assert (v["anlass"], v["datum"], v["von"], v["bis"], v["gage"]) == ("Hochzeit", "2027-06-13", "17:00", "02:00", 1250)
    assert "Anna Muster" in t and "Sonntag, 13. Juni 2027" in t and "17:00 bis 2:00 Uhr" in t
    assert "**1.250,00 €**" in t and "**375,00 €**" in t and "**875,00 €**" in t
    titel = [a["titel"] for a in j["inhalt"]["abschnitte"]]
    assert titel == ["§ 1 Vertragspartner", "§ 2 Leistung", "§ 3 Gage und Zahlung", "§ 4 Verpflegung", "§ 5 Ausfall des DJs, Ersatz-DJ",
                     "§ 6 GEMA", "§ 7 Schäden durch Gäste", "§ 8 Schlussbestimmungen"]


def test_vertrag_ohne_angebot_und_aendern(client):
    v = neu(client)["vertrag"]
    assert v["name"] == "Vertrag V001" and v["angebot_id"] is None
    r = client.put(f"/api/vertraege/{v['id']}", json={"kunde": {"name": "Carla Test", "strasse": "Rosenstr. 8", "plz": "12347", "ort": "Testdorf"},
                                                    "anlass": "Geburtstagsfeier", "datum": "2027-03-20", "von": "19:00", "bis": "01:00", "gage": 650,
                                                    "felder": {"zahlung": "bar", "anzahlung": 20, "gema": "dj", "verpflegung": "für 2 Personen",
                                                               "aufbau": "17:30", "kontakt": "Lisa <0170>"}})
    assert r.status_code == 200, r.get_json()
    t = text(r.get_json()["inhalt"])
    assert "Carla Test" in t and "**130,00 €**" in t and "bar bezahlt" in t and "übernimmt der DJ" in t and "(für 2 Personen)" in t
    assert "17:30 Uhr" in t and "Lisa <0170>" in t
    for falsch in ({"datum": "2027-02-30"}, {"von": "25:00"}, {"gage": "viel"}, {"felder": {"zahlung": "irgendwas"}}):
        assert client.put(f"/api/vertraege/{v['id']}", json=falsch).status_code == 400
    assert neu(client)["vertrag"]["nummer"] == "V002"


def test_abschnitte_platzhalter_und_reihenfolge(client):
    vl = client.get("/api/vertragsvorlage").get_json()["abschnitte"]
    assert len(vl) == 20 and [a["id"] for a in vl if a["an"]] == ["verpflegung", "ersatz", "gema", "haftung"]
    vl.insert(0, {"titel": "Dresscode", "text": "Der DJ erscheint am {datum} bei {veranstalter} – {unbekannt} bleibt.", "an": True})
    vl[1]["an"] = False                                    # Verpflegung aus
    vl[2]["text"] = "Geänderter Text zum Ersatz-DJ."
    r = client.put("/api/vertragsvorlage/abschnitte", json={"abschnitte": vl})
    assert r.status_code == 200
    vl = r.get_json()["abschnitte"]
    assert vl[0]["titel"] == "Dresscode" and vl[0]["herkunft"] == "eigen"
    j = neu(client, angebot_id=angebot(client))
    t = text(j["inhalt"])
    assert "§ 4 Dresscode" in t and "am 13.06.2027 bei Anna Muster – {unbekannt} bleibt." in t
    assert "Verpflegung" not in t and "Geänderter Text zum Ersatz-DJ." in t
    # eigenen Abschnitt löschen; eingebaute lassen sich nur ausschalten
    ohne = [a for a in vl if a["titel"] not in ("Dresscode", "Höhere Gewalt")]
    vl = client.put("/api/vertragsvorlage/abschnitte", json={"abschnitte": ohne}).get_json()["abschnitte"]
    assert not any(a["titel"] == "Dresscode" for a in vl)
    assert next(a for a in vl if a["id"] == "gewalt")["an"] is False
    assert client.put("/api/vertragsvorlage/abschnitte", json={"abschnitte": [{"titel": "", "text": "x"}]}).status_code == 400


def test_eigenen_vertrag_hochladen(client):
    xml = "".join(f"<w:p><w:r><w:t>{a}</w:t></w:r></w:p>" for a in
                  ["DJ-Vertrag", "§ 1 Vertragspartner", "Wie unten.", "§ 2 Anfahrt", "Bis 30 km inklusive.", "§ 3 Musikwünsche",
                   "Gern bis zwei Wochen vorher.", "Liste &amp; Wünsche.", "§ 4 Schlussbestimmungen", "Textform."])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="x"><w:body>{xml}</w:body></w:document>')
    r = client.post("/api/vertragsvorlage/lesen", data={"datei": (io.BytesIO(buf.getvalue()), "mein_vertrag.docx")},
                    content_type="multipart/form-data")
    j = r.get_json()
    assert r.status_code == 200, j
    assert [(a["titel"], a["fest"]) for a in j["abschnitte"]] == [("Vertragspartner", True), ("Anfahrt", False),
                                                                    ("Musikwünsche", False), ("Schlussbestimmungen", True)]
    assert j["abschnitte"][2]["text"] == "Gern bis zwei Wochen vorher. Liste & Wünsche."
    r = client.post("/api/vertragsvorlage/lesen", data={"datei": (io.BytesIO("1. Anfahrt\nBis 30 km.\n".encode()), "v.txt")},
                    content_type="multipart/form-data")
    assert r.get_json()["abschnitte"][0]["titel"] == "Anfahrt"
    r = client.post("/api/vertragsvorlage/lesen", data={"datei": (io.BytesIO(b"x"), "alt.doc")}, content_type="multipart/form-data")
    assert r.status_code == 400 and ".docx" in r.get_json()["error"]
    r = client.post("/api/vertragsvorlage/lesen", data={"datei": (io.BytesIO(b"PK kaputt"), "k.docx")}, content_type="multipart/form-data")
    assert r.status_code == 400


def test_anlagen_nur_pdf_und_im_versand(client, smtp):  # noqa: F811
    client.put("/api/einstellungen", json=EINRICHTUNG)
    r = client.post("/api/vertragsvorlage/anlagen", data={"datei": (io.BytesIO(b"Word"), "AGB.docx")}, content_type="multipart/form-data")
    assert r.status_code == 400
    r = client.post("/api/vertragsvorlage/anlagen", data={"datei": (io.BytesIO(b"%PDF-1.4 AGB"), "AGB.pdf")}, content_type="multipart/form-data")
    assert r.status_code == 201 and r.get_json()["anlagen"][0]["name"] == "AGB.pdf"
    v = neu(client, angebot_id=angebot(client))
    assert v["inhalt"]["anlagen"] == ["AGB.pdf"]
    vid = v["vertrag"]["id"]
    e = client.get(f"/api/versand/entwurf?art=vertrag&id={vid}").get_json()
    assert e["anhaenge"] == ["Vertrag_Angebot_012_130627.pdf", "AGB.pdf"] and "13.06.2027" in e["betreff"]
    r = client.post("/api/versand", json={"art": "vertrag", "id": vid, "an": "anna@example.de", "betreff": e["betreff"], "text": e["text"]})
    assert r.status_code == 200, r.get_json()
    msg = smtp.gesendet[-1]["msg"]
    assert [p.get_filename() for p in msg.iter_attachments()] == ["Vertrag_Angebot_012_130627.pdf", "AGB.pdf"]
    v = client.get(f"/api/vertraege/{vid}").get_json()["vertrag"]
    assert v["status"] == "verschickt" and v["verschickt_am"]
    aid = client.get("/api/vertragsvorlage").get_json()["anlagen"][0]["id"]
    assert client.delete(f"/api/vertragsvorlage/anlagen/{aid}").status_code == 204


def test_verschickt_haelt_text_fest(client):
    v = neu(client, angebot_id=angebot(client))["vertrag"]
    assert client.post(f"/api/vertraege/{v['id']}/status", json={"status": "verschickt"}).status_code == 200
    vl = client.get("/api/vertragsvorlage").get_json()["abschnitte"]
    vl[0]["text"] = "Neue Verpflegungsregel."
    client.put("/api/vertragsvorlage/abschnitte", json={"abschnitte": vl})
    t = text(client.get(f"/api/vertraege/{v['id']}").get_json()["inhalt"])
    assert "Neue Verpflegungsregel." not in t and "alkoholfreie Getränke" in t
    assert client.put(f"/api/vertraege/{v['id']}", json={"gage": 1}).status_code == 409
    assert client.post(f"/api/vertraege/{v['id']}/status", json={"status": "entwurf"}).status_code == 200
    assert "Neue Verpflegungsregel." in text(client.get(f"/api/vertraege/{v['id']}").get_json()["inhalt"])


def test_ohne_angaben_nicht_verschicken(client):
    v = neu(client)["vertrag"]
    r = client.post(f"/api/vertraege/{v['id']}/status", json={"status": "verschickt"})
    assert r.status_code == 400 and "Veranstalter" in r.get_json()["error"]


def test_unterschrieben_mit_datei_und_angebot_annehmen(client):
    aid = angebot(client)
    v = neu(client, angebot_id=aid)["vertrag"]
    r = client.post(f"/api/vertraege/{v['id']}/unterschrieben", data={"weg": "datei", "am": "2026-11-26"}, content_type="multipart/form-data")
    assert r.status_code == 400
    r = client.post(f"/api/vertraege/{v['id']}/unterschrieben", data={"weg": "datei", "am": "2026-11-26", "angebot_annehmen": "1",
                                                                     "datei": (io.BytesIO(b"<html>"), "x.html")}, content_type="multipart/form-data")
    assert r.status_code == 400
    r = client.post(f"/api/vertraege/{v['id']}/unterschrieben", data={"weg": "datei", "am": "2026-11-26", "angebot_annehmen": "1",
                                                                     "datei": (io.BytesIO(b"%PDF-1.4 unterschrieben"), "zurueck.pdf")},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()
    v = r.get_json()["vertrag"]
    assert v["status"] == "unterschrieben" and v["unterschrieben"]["dateiname"] == "zurueck.pdf" and v["hat_unterschrift_datei"]
    assert client.get(f"/api/angebote/{aid}").get_json()["status"] == "angenommen"
    d = client.get(f"/api/vertraege/{v['id']}/unterschrift")
    assert d.data == b"%PDF-1.4 unterschrieben" and "attachment" in d.headers["Content-Disposition"]
    assert client.delete(f"/api/vertraege/{v['id']}").status_code == 409
    assert client.post(f"/api/vertraege/{v['id']}/status", json={"status": "entwurf"}).status_code == 409


def test_unterschrieben_per_mail_ohne_datei(client):
    v = neu(client, angebot_id=angebot(client))["vertrag"]
    r = client.post(f"/api/vertraege/{v['id']}/unterschrieben", data={"weg": "mail", "am": "2026-11-26", "notiz": "einverstanden"},
                    content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["vertrag"]["unterschrieben"]["weg"] == "mail"
    assert client.get(f"/api/vertraege/{v['id']}/unterschrift").status_code == 404


def test_pdf(client):
    v = neu(client, angebot_id=angebot(client))["vertrag"]
    r = client.get(f"/api/vertraege/{v['id']}/pdf")
    t = " ".join(pdf_text(r.data).split())
    assert "DJ-Vertrag" in t and "Anna Muster" in t and "Schäden durch Gäste" in t and "Unterschrift Veranstalter" in t
    assert "1.250,00 €" in t and "**" not in t


def test_sicherung_enthaelt_vertragsdateien(client, tmp_path):
    client.post("/api/vertragsvorlage/anlagen", data={"datei": (io.BytesIO(b"%PDF-1.4 AGB"), "AGB.pdf")}, content_type="multipart/form-data")
    v = neu(client, angebot_id=angebot(client))["vertrag"]
    client.post(f"/api/vertraege/{v['id']}/unterschrieben", data={"weg": "datei", "am": "2026-11-26",
                                                                 "datei": (io.BytesIO(b"%PDF-1.4 zurueck"), "z.pdf")}, content_type="multipart/form-data")
    sicherung = client.get("/api/backup").data
    namen = zipfile.ZipFile(io.BytesIO(sicherung)).namelist()
    assert any(n.startswith("vertraege/anlagen/") for n in namen) and any(n.startswith("vertraege/unterschrieben/") for n in namen)
    r = client.post("/api/backup", data={"datei": (io.BytesIO(sicherung), "s.zip")}, content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()
    assert client.get(f"/api/vertraege/{v['id']}/unterschrift").data == b"%PDF-1.4 zurueck"


def test_manipulierter_dateipfad(client):
    import db
    v = neu(client, angebot_id=angebot(client))["vertrag"]
    with db.connect() as con:
        con.execute("UPDATE vertraege SET unterschrift_datei = '../../rechnungen.db' WHERE id = ?", (v["id"],))
    assert client.get(f"/api/vertraege/{v['id']}/unterschrift").status_code == 404


def test_angebot_unbekannt(client):
    assert client.post("/api/vertraege", json={"angebot_id": 999}).status_code == 404
    assert client.post("/api/vertraege", json={"angebot_id": "1 OR 1=1"}).status_code == 404

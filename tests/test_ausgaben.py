"""Finanzen – Ausgaben: Belege hochladen, prüfen, übernehmen, verwerfen; Vorschau; Lernen der Kategorie."""
import io
import os
from pathlib import Path

MAILS = Path(__file__).parent / "beispiele" / "mails"


def hochladen(client, *namen):
    dateien = [(io.BytesIO((MAILS / n).read_bytes()), n) for n in namen]
    r = client.post("/api/ausgaben/belege", data={"dateien": dateien}, content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_hochladen_doppelt_und_ablage(client, tmp_path):
    r = hochladen(client, "beatport.eml", "apple.eml")
    assert [a["lieferant"] for a in r["neu"]] == ["Beatport", "Apple"] and not r["doppelt"]
    a = r["neu"][0]
    assert a["status"] == "neu" and a["betrag"] == 5.33 and a["kategorie"] == "musik" and a["beleg_typ"] == "mail"
    assert a["erkannt"]["fundstellen"]["betrag"] == "Total … €5.33"
    assert (tmp_path / a["beleg_datei"]).read_bytes() == (MAILS / "beatport.eml").read_bytes()   # Original unverändert
    # dieselbe Mail noch einmal → als doppelt erkannt
    r = hochladen(client, "beatport.eml")
    assert not r["neu"] and r["doppelt"][0]["id"] == a["id"]


def test_uebernehmen_pflichtfelder_und_jahr(client):
    a = hochladen(client, "qobuz.eml")["neu"][0]
    r = client.put(f"/api/ausgaben/{a['id']}", json={"lieferant": "", "uebernehmen": True})
    assert r.status_code == 400 and "Lieferant" in r.get_json()["error"]
    r = client.put(f"/api/ausgaben/{a['id']}", json={"beschreibung": "2 Titel", "uebernehmen": True})
    assert r.status_code == 200 and r.get_json()["status"] == "ok" and r.get_json()["bezahlt_am"] == "2026-11-09"
    liste = client.get("/api/ausgaben?jahr=2026").get_json()
    assert [x["id"] for x in liste] == [a["id"]]
    assert client.get("/api/ausgaben?jahr=2025").get_json() == []


def test_ohne_beleg_braucht_notiz(client):
    basis = {"belegdatum": "2026-10-03", "lieferant": "Parkhaus Altstadt", "betrag": "8,00", "kategorie": "reise"}
    r = client.post("/api/ausgaben", json=basis)
    assert r.status_code == 400 and "Notiz" in r.get_json()["error"]
    r = client.post("/api/ausgaben", json=basis | {"notiz": "Parkautomat, kein Beleg"})
    assert r.status_code == 201 and r.get_json()["betrag"] == 8.0 and r.get_json()["status"] == "ok"
    assert client.post("/api/ausgaben", json=basis | {"notiz": "x", "kategorie": "quatsch"}).status_code == 400
    assert client.post("/api/ausgaben", json=basis | {"notiz": "x", "privatanteil": 150}).status_code == 400


def test_verwerfen_dann_endgueltig_loescht_datei(client, tmp_path):
    a = hochladen(client, "apple.eml")["neu"][0]
    datei = tmp_path / a["beleg_datei"]
    assert datei.exists()
    assert client.delete(f"/api/ausgaben/{a['id']}").status_code == 204
    assert datei.exists() and client.get("/api/ausgaben").get_json() == []          # erst nur im Papierkorb
    assert client.delete(f"/api/papierkorb/{a['id']}").status_code == 204
    assert not datei.exists() and client.get(f"/api/ausgaben/{a['id']}").status_code == 404


def test_mail_vorschau_ist_abgesichert(client):
    a = hochladen(client, "beatport.eml")["neu"][0]
    r = client.get(f"/api/ausgaben/{a['id']}/ansicht")
    assert r.mimetype == "text/html" and "default-src 'none'" in r.headers["Content-Security-Policy"]
    seite = r.get_data(as_text=True)
    assert "Betreff:" in seite and "<script" not in seite.lower() and "€5.33" in seite
    original = client.get(f"/api/ausgaben/{a['id']}/beleg")
    assert original.data == (MAILS / "beatport.eml").read_bytes() and "attachment" in original.headers["Content-Disposition"]


def test_kategorie_lernt_pro_lieferant(client):
    a = hochladen(client, "amazon.eml")["neu"][0]          # Amazon Music → musik (aus dem Inhalt)
    client.put(f"/api/ausgaben/{a['id']}", json={"kategorie": "technik", "uebernehmen": True})
    # nächster Amazon-Beleg (hier als PDF) bekommt die zuletzt gewählte Kategorie
    from fpdf import FPDF
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Helvetica", size=11)
    for z in ("Amazon", "Rechnung", "Gesamtbetrag 23,99 EUR"):
        pdf.cell(0, 6, z, new_x="LMARGIN", new_y="NEXT")
    r = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(bytes(pdf.output())), "amazon.pdf")]},
                    content_type="multipart/form-data").get_json()
    assert r["neu"][0]["lieferant"] == "Amazon" and r["neu"][0]["kategorie"] == "technik"


def test_beleg_pfad_kann_nicht_ausbrechen(client, tmp_path, app_modul):
    import db
    a = hochladen(client, "apple.eml")["neu"][0]
    geheim = tmp_path / "geheim.txt"
    geheim.write_text("x")
    with db.connect() as con:
        con.execute("UPDATE ausgaben SET beleg_datei = ? WHERE id = ?", (os.path.join("belege", "..", "geheim.txt"), a["id"]))
    assert client.get(f"/api/ausgaben/{a['id']}/beleg").status_code == 404


def test_heic_foto_vorschau(client):
    """iPhone-Fotos (HEIC) werden für die Vorschau in JPEG umgewandelt; das Original bleibt unverändert."""
    import pytest
    pillow_heif = pytest.importorskip("pillow_heif")
    from PIL import Image
    pillow_heif.register_heif_opener()
    buf = io.BytesIO()
    Image.new("RGB", (60, 80), (200, 30, 30)).save(buf, format="HEIF")
    r = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(buf.getvalue()), "IMG_0001.HEIC")]},
                    content_type="multipart/form-data").get_json()
    a = r["neu"][0]
    assert a["beleg_typ"] == "bild"
    v = client.get(f"/api/ausgaben/{a['id']}/ansicht")
    assert v.status_code == 200 and v.mimetype == "image/jpeg" and v.data[:3] == b"\xff\xd8\xff"
    assert client.get(f"/api/ausgaben/{a['id']}/beleg").data == buf.getvalue()

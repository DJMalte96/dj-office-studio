"""E-Rechnungen in der App: Wege hinein, Warnungen, Export, Update."""
import csv
import io
import json
import os
import zipfile

import pytest

import belege
import db
import finanzen
from erechnung_muster import cii, mail, pdf, ubl


def hoch(client, *dateien):
    return client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(d), n) for n, d in dateien]},
                       content_type="multipart/form-data").get_json()


def einer(client, name="r.xml", daten=None):
    e = hoch(client, (name, daten or ubl()))
    assert len(e["neu"]) == 1, e
    return e["neu"][0]


def test_xml_hochladen(client):
    a = einer(client)
    assert (a["beleg_typ"], a["lieferant"], a["betrag"], a["belegdatum"], a["bezahlt_am"], a["ust_satz"], a["ocr"]) == \
        ("xml", "Musikhaus Probe GmbH", 119, "2026-03-14", "2026-03-14", 19, None)
    assert a["status"] == "neu" and a["beschreibung"] == "XLR-Kabel · Nr. R-1"


def test_hybrid_scan_braucht_keine_texterkennung(client):
    a = einer(client, "r.pdf", pdf([], [("factur-x.xml", ubl(waehrung="USD"))]))
    assert a["betrag"] is None and a["ocr"] is None


@pytest.mark.parametrize("daten, grund", [(b"<playlist/>", "keine E-Rechnung"), (b"<kaputt", "beschädigt")])
def test_anderes_xml_wird_abgelehnt(client, daten, grund):
    e = hoch(client, ("x.xml", daten))
    assert not e["neu"] and grund in e["fehler"][0]["fehler"]
    assert not client.get("/api/ausgaben").get_json()


def test_original_nur_als_download(client):
    a = einer(client)
    r = client.get(f"/api/ausgaben/{a['id']}/beleg")
    assert r.data == ubl() and r.headers["Content-Disposition"].startswith("attachment")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.mimetype == "application/xml"


def test_lesefassungen(client):
    for name, daten in (("r.xml", ubl()), ("k.eml", mail(("r.xml", ubl("R-2"))))):
        r = client.get(f"/api/ausgaben/{einer(client, name, daten)['id']}/ansicht")
        assert "Lesefassung" in r.get_data(as_text=True) and "default-src 'none'" in r.headers["Content-Security-Policy"]
    p = einer(client, "r.pdf", pdf(["Gesamt 53,50 EUR"], [("factur-x.xml", cii())]))
    assert client.get(f"/api/ausgaben/{p['id']}/ansicht").mimetype == "application/pdf"
    assert "C-7" in client.get(f"/api/ausgaben/{p['id']}/ansicht?daten=1").get_data(as_text=True)


# ---------- Warnungen

@pytest.mark.parametrize("werte, einstellung", [
    ({"verkaeufer": "Max Beispiel"}, {}),
    ({"verkaeufer": "DJ Probe", "steuer_id": "DE 222 222 222"}, {"ust_idnr": "DE222222222"}),
    ({"verkaeufer": "DJ Probe", "steuer_id": "12/345/67890"}, {"steuernummer": "12 345 67890"}),
    ({"verkaeufer": "DJ Probe", "mail": "Post@example.org"}, {"absender_email": "post@example.org"})])
def test_man_selbst_ist_verkaeufer(client, werte, einstellung):
    db.save_settings(einstellung)
    a = einer(client, daten=ubl(**werte))
    assert a["lieferant"] == "" and a["erkannt"]["hinweise"][0] == finanzen.EIGENE_ERECHNUNG


def test_selbst_auch_bei_paperless_korrespondent(app_modul):
    a, _ = finanzen.beleg_aufnehmen("r.xml", ubl(verkaeufer="Max Beispiel"), paperless={
        "id": 4, "korrespondent": "Kunde Probe", "titel": "Rechnung", "datum": None, "text": ""})
    assert a["lieferant"] == ""


def test_paperless_text_ueberschreibt_fremdwaehrung_nicht(app_modul):
    a, _ = finanzen.beleg_aufnehmen("r.xml", ubl(waehrung="USD"), paperless={
        "id": 5, "korrespondent": None, "titel": "x", "datum": None, "text": "Gesamt 119,00"})
    assert a["betrag"] is None


@pytest.mark.parametrize("ku, da", [(True, False), (False, True)])
def test_gemischte_steuer_warnt_nur_mit_vorsteuer(client, ku, da):
    db.save_settings({"kleinunternehmer": ku})
    a = einer(client, daten=ubl(brutto="226", netto="200", steuer="26", steuern=[("100", "19", "19"), ("100", "7", "7")]))
    assert any("Vorsteuer" in h for h in a["erkannt"]["hinweise"]) == da and a["ust_satz"] is None


def verdacht(client, a):
    return client.get(f"/api/ausgaben/{a['id']}").get_json()["doppelt_verdacht"]


def test_dieselbe_nummer_ist_sicher_doppelt(client):
    a = einer(client)
    b = einer(client, "k.eml", mail(("r.xml", ubl())))
    assert verdacht(client, b)["sicher"] and verdacht(client, b)["id"] == a["id"]
    assert verdacht(client, a)["id"] == b["id"]          # in beide Richtungen
    client.delete(f"/api/ausgaben/{a['id']}")
    assert verdacht(client, b) is None                   # Papierkorb zählt nie


@pytest.mark.parametrize("datum, betrag, da", [("2026-03-16", 119, True), ("2026-03-24", 119, True), ("2026-03-25", 119, False),
                                               ("2026-03-16", 118.99, False)])
def test_vermutlich_schon_als_pdf_da(client, datum, betrag, da):
    client.post("/api/ausgaben", json={"belegdatum": datum, "lieferant": "Musikhaus", "betrag": betrag, "notiz": "x"})
    v = verdacht(client, einer(client))
    assert bool(v) == da and (not v or not v["sicher"])


def test_zwei_kaeufe_sind_nicht_doppelt(client):
    einer(client, daten=ubl("A"))
    assert verdacht(client, einer(client, daten=ubl("B"))) is None


def test_gleiche_nummer_anderer_verkaeufer(client):
    einer(client)
    assert verdacht(client, einer(client, daten=ubl(verkaeufer="Anderer Laden"))) is None


# ---------- Gutschrift, Export

def test_gutschrift_mindert_ausgaben(client):
    client.post("/api/ausgaben", json={"belegdatum": "2026-01-05", "lieferant": "Musikhaus Probe GmbH", "betrag": 500,
                                       "kategorie": "technik", "notiz": "x"})
    a = einer(client, daten=ubl(gutschrift=True))
    assert a["betrag"] == -119
    assert client.put(f"/api/ausgaben/{a['id']}", json={"uebernehmen": True}).status_code == 200
    assert client.get("/api/finanzen/euer?jahr=2026").get_json()["ausgaben"] == 381


def test_gutschrift_lernt_nicht_anschaffung(client):
    client.post("/api/ausgaben", json={"belegdatum": "2026-01-05", "lieferant": "Musikhaus Probe GmbH", "betrag": 1500,
                                       "kategorie": "anschaffung", "notiz": "x"})
    a = einer(client, daten=ubl(gutschrift=True))
    assert a["kategorie"] == "sonstiges"
    r = client.put(f"/api/ausgaben/{a['id']}", json={"uebernehmen": True, "kategorie": "anschaffung"})
    assert r.status_code == 400 and "Gutschrift" in r.get_json()["error"]
    r = client.post("/api/ausgaben", json={"belegdatum": "2026-01-05", "lieferant": "X", "betrag": -5,
                                           "kategorie": "anschaffung", "notiz": "x"})
    assert r.status_code == 400


def test_export_mit_original_und_ohne_formeln(client):
    a = einer(client, "ohne-endung", ubl(posten="=HYPERLINK(0)", gutschrift=True))
    client.put(f"/api/ausgaben/{a['id']}", json={"uebernehmen": True})
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/export?jahr=2026").data))
    [name] = [n for n in z.namelist() if n.startswith("Belege/")]
    assert name.endswith(".xml") and z.read(name) == ubl(posten="=HYPERLINK(0)", gutschrift=True)
    zeile = list(csv.reader(io.StringIO(z.read("Ausgaben_2026.csv").decode("utf-8-sig")), delimiter=";"))[1]
    assert zeile[3].startswith("'=HYPERLINK") and zeile[5] == "-119,00"


@pytest.mark.parametrize("wert, soll", [("=1+1", "'=1+1"), ("+49", "'+49"), ("@SUM(A1)", "'@SUM(A1)"), ("-2+3", "'-2+3"),
                                        ("\t=1", "'\t=1"), ("-12,00", "-12,00"), ("Laden", "Laden"), (7, 7)])
def test_zelle(wert, soll):
    assert finanzen._zelle(wert) == soll


# ---------- Belege-Ordner

@pytest.fixture
def ordner(client, tmp_path, monkeypatch):
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    monkeypatch.setattr(finanzen, "_unpassend", {})
    finanzen._ordner_stand.update(neu=0, doppelt=0, fehler=[], problem=None, uebergangen=[], uebergangen_anzahl=0)
    o = tmp_path / "eingang"
    o.mkdir()
    db.save_settings({"belege_ordner": str(o), "belege_ordner_verschieben": True})
    return o


def lesen(client):
    return client.post("/api/belege-ordner/einlesen").get_json()


def test_ordner_liest_xml(client, ordner):
    (ordner / "r.XML").write_bytes(ubl())
    assert lesen(client)["neu"] == 1 and (ordner / "übernommen" / "r.XML").exists()


@pytest.mark.parametrize("verschieben", [True, False])
def test_ordner_meldet_was_liegen_bleibt(client, ordner, verschieben):
    db.save_settings({"belege_ordner_verschieben": verschieben})
    for name, inhalt in (("liste.xml", b"<playlist/>"), ("kaputt.xml", b"<kaputt"), ("brief.docx", b"x"),
                         ("Thumbs.db", b"x"), ("halb.pdf.part", b"x"), (".versteckt", b"x"), ("~$brief.docx", b"x")):
        (ordner / name).write_bytes(inhalt)
    for _ in range(3):                                          # bleibt gemeldet, wird nie angefasst
        st = lesen(client)
        m = {x["datei"]: x["grund"] for x in st["uebergangen"]}
        assert set(m) == {"liste.xml", "kaputt.xml", "brief.docx"} and st["uebergangen_anzahl"] == 3
        assert "keine E-Rechnung" in m["liste.xml"] and "beschädigt" in m["kaputt.xml"]
        assert st["neu"] == 0 and (ordner / "liste.xml").exists() and not (ordner / "nicht lesbar").exists()


def test_fremdes_xml_wird_nicht_jede_minute_gelesen(client, ordner, monkeypatch):
    (ordner / "liste.xml").write_bytes(b"<playlist/>")
    lesen(client)
    monkeypatch.setattr(finanzen, "dateien_aufnehmen", lambda *a, **k: pytest.fail("noch einmal gelesen"))
    assert lesen(client)["uebergangen_anzahl"] == 1


def test_reparierte_xml_wird_gelesen(client, ordner):
    (ordner / "r.xml").write_bytes(b"<kaputt")
    lesen(client)
    (ordner / "r.xml").write_bytes(ubl())
    st = lesen(client)
    assert st["neu"] == 1 and st["uebergangen_anzahl"] == 0


def test_nicht_lesbar_wird_gemeldet(client, ordner):
    (ordner / "nicht lesbar").mkdir()
    (ordner / "nicht lesbar" / "alt.msg").write_bytes(b"x")
    assert "nicht lesbar" in lesen(client)["uebergangen"][0]["grund"]


def test_nur_lesen_versucht_fehler_noch_einmal(client, ordner, monkeypatch):
    db.save_settings({"belege_ordner_verschieben": False})
    (ordner / "r.xml").write_bytes(ubl())
    echt = finanzen.beleg_aufnehmen
    monkeypatch.setattr(finanzen, "beleg_aufnehmen", lambda *a, **k: 1 / 0)
    assert lesen(client)["uebergangen_anzahl"] == 1
    monkeypatch.setattr(finanzen, "beleg_aufnehmen", echt)
    st = lesen(client)
    assert st["neu"] == 1 and st["uebergangen_anzahl"] == 0 and (ordner / "r.xml").exists()


def test_bisher_uebersprungene_xml_kommt_nach(client, ordner):
    db.save_settings({"belege_ordner_verschieben": False, finanzen.ABGLEICH_ERLEDIGT: "2026-11-22"})
    (ordner / "alt.xml").write_bytes(ubl())
    os.utime(ordner / "alt.xml", (1_700_000_000, 1_700_000_000))
    assert lesen(client)["neu"] == 1
    assert client.get("/api/ausgaben").get_json()[0]["status"] == "neu"


def test_abgleich_von_16_fasst_xml_nicht_an(client, ordner):
    (ordner / "übernommen").mkdir()
    (ordner / "übernommen" / "r.xml").write_bytes(ubl())
    lesen(client)
    assert not client.get("/api/papierkorb").get_json()


# ---------- Update: vorhandene Belege

def altbestand(monkeypatch, name, daten):
    """So, wie 1.6 den Beleg angelegt hätte."""
    with monkeypatch.context() as m:
        m.setattr(belege, "erechnungen", lambda typ, d: ([], []))
        if name.endswith(".xml"):
            m.setattr(belege, "typ_von", lambda n, d: "unbekannt")
        a, _ = finanzen.beleg_aufnehmen(name, daten)
    return a["id"]


@pytest.mark.parametrize("name, daten", [("r.xml", ubl()), ("k.eml", mail(("r.xml", ubl()))),
                                         ("r.pdf", pdf(["Alt GmbH", "Gesamt 5,00 EUR"], [("factur-x.xml", ubl())]))])
def test_update_liest_ungepruefte_nach(app_modul, monkeypatch, name, daten):
    aid = altbestand(monkeypatch, name, daten)
    assert finanzen.holen(aid)["betrag"] != 119
    assert finanzen._nachlesen_17() == 1
    a = finanzen.holen(aid)
    assert (a["betrag"], a["lieferant"], a["belegdatum"], a["bezahlt_am"], a["ust_satz"]) == \
        (119, "Musikhaus Probe GmbH", "2026-03-14", "2026-03-14", 19)
    assert a["status"] == "neu" and a["beleg_typ"] != "unbekannt"
    assert finanzen._nachlesen_17() == 0                        # nur einmal


def test_update_laesst_getipptes_stehen(app_modul, monkeypatch):
    aid = altbestand(monkeypatch, "r.xml", ubl())
    with db.connect() as con:
        con.execute("UPDATE ausgaben SET betrag = 42, lieferant = 'Von Hand', belegdatum = '2025-01-01',"
                    " bezahlt_am = '2025-01-02', beschreibung = 'meins' WHERE id = ?", (aid,))
    finanzen._nachlesen_17()
    a = finanzen.holen(aid)
    assert (a["betrag"], a["lieferant"], a["belegdatum"], a["bezahlt_am"], a["beschreibung"], a["ust_satz"]) == \
        (42, "Von Hand", "2025-01-01", "2025-01-02", "meins", None)


@pytest.mark.parametrize("status, vorher", [("ok", None), ("papierkorb", "ok")])
def test_update_aendert_nichts_uebernommenes(app_modul, monkeypatch, status, vorher):
    aid = altbestand(monkeypatch, "r.xml", ubl())
    with db.connect() as con:
        con.execute("UPDATE ausgaben SET status = ?, status_vorher = ? WHERE id = ?", (status, vorher, aid))
    alt = finanzen.holen(aid)
    finanzen._nachlesen_17()
    assert finanzen.holen(aid) == alt | {"beleg_typ": "xml"}    # nur die Lesefassung kommt dazu


def test_update_behaelt_korrespondent(app_modul, monkeypatch):
    aid = altbestand(monkeypatch, "r.pdf", pdf(["Alt GmbH"], [("factur-x.xml", ubl())]))
    with db.connect() as con:
        e = json.loads(con.execute("SELECT erkannt_json FROM ausgaben WHERE id = ?", (aid,)).fetchone()[0])
        e["lieferant"] = "Korrespondent"
        con.execute("UPDATE ausgaben SET paperless_id = 9, lieferant = 'Korrespondent', erkannt_json = ? WHERE id = ?", (json.dumps(e), aid))
    finanzen._nachlesen_17()
    assert finanzen.holen(aid)["lieferant"] == "Korrespondent"


def test_update_laeuft_auch_ohne_ordner(client, monkeypatch):
    aid = altbestand(monkeypatch, "r.xml", ubl())
    db.save_settings({"belege_ordner": ""})
    finanzen.ordner_einlesen()
    assert finanzen.holen(aid)["betrag"] == 119


def test_update_liest_keine_pfade_ausserhalb(app_modul, monkeypatch, tmp_path):
    aid = altbestand(monkeypatch, "r.xml", ubl())
    (tmp_path / "geheim.xml").write_bytes(ubl(verkaeufer="Darf nicht"))
    with db.connect() as con:
        con.execute("UPDATE ausgaben SET beleg_datei = 'geheim.xml' WHERE id = ?", (aid,))
    assert finanzen._nachlesen_17() == 0 and finanzen.holen(aid)["lieferant"] == ""


# ---------- Paperless

@pytest.mark.parametrize("daten, original", [(pdf(["Rechnung"], [("factur-x.xml", cii())]), True),
                                             (pdf([], [("factur-x.xml", cii())]), True),
                                             (pdf(["Lange Textzeile einer gewoehnlichen Rechnung " * 2] * 3), True),
                                             (pdf([]), False)])
def test_paperless_original_ausser_bei_scans(app_modul, monkeypatch, daten, original):
    import paperless
    db.save_settings({"paperless_url": "http://paperless", "paperless_token": "t", "paperless_tag": 7})
    geladen = []

    def laden(url, token, nr, k=None, original=False):
        geladen.append(original)
        return (daten if original else pdf(["Archivfassung"]), "r.pdf", "application/pdf")

    monkeypatch.setattr(paperless, "dokumente", lambda *a: [{"id": 3, "title": "R", "mime_type": "application/pdf"}])
    monkeypatch.setattr(paperless, "korrespondenten", lambda *a: {})
    monkeypatch.setattr(paperless, "herunterladen", laden)
    finanzen._pl_status.clear()
    finanzen._pl_status.update(laeuft=True, gesamt=None, fertig=0, neu=0, doppelt=0, vorhanden=0, verworfen=0, fehler=[], abbruch=None)
    finanzen._pl_sperre.acquire()
    finanzen.paperless_abholen()
    assert geladen[-1] == original and finanzen._pl_status["neu"] == 1


def test_paperless_adresse(monkeypatch):
    import paperless
    pfade = []
    monkeypatch.setattr(paperless, "_anfrage", lambda url, token, pfad, **k: pfade.append(pfad))
    paperless.herunterladen("u", "t", 3)
    paperless.herunterladen("u", "t", 3, original=True)
    assert pfade == ["/api/documents/3/download/", "/api/documents/3/download/?original=true"]


@pytest.mark.parametrize("dok, soll", [({"mime_type": "application/pdf"}, True), ({"mime_type": "text/xml"}, True),
                                       ({"mime_type": "image/jpeg"}, False), ({"original_file_name": "R.PDF"}, True), ({}, False)])
def test_original_noetig(dok, soll):
    import paperless
    assert paperless.original_noetig(dok) == soll


# ---------- Desktop

@pytest.mark.parametrize("name, soll", [("r.pdf", "r.pdf"), ("R.PDF", "R.PDF"), ("rechnung.hta", "rechnung.hta.pdf"), ("a", "a.pdf")])
def test_desktop_oeffnet_nur_als_pdf(name, soll):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("djos_start", Path(__file__).resolve().parents[1] / "desktop" / "start.py")
    start = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(start)
    assert start._als_pdf(name) == soll
    api = start.DesktopApi("http://127.0.0.1/")
    gezeigt = []
    api._laden = lambda pfad: (name, b"%PDF-")
    api._anzeigen = lambda n, d: gezeigt.append(n)
    api.pdf_oeffnen("api/ausgaben/1/beleg")
    assert gezeigt == [soll]

"""Ein ausgestellter Beleg ändert sich nie – auch nicht nach Umzug oder Kontowechsel."""
import io
import json
import os
import random
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfReader

import db
from conftest import KUNDE, neue_rechnung, pdf_text

WURZEL = Path(__file__).resolve().parents[1]
UMZUG = {"name": "Max Neu", "strasse": "Neuer Weg 9", "plz_ort": "54321 Neustadt", "ort_fuer_datum": "Neustadt",
         "telefon": "0170/9999999", "bank_name": "Neue Bank", "kontoinhaber": "Max Neu-Konto",
         "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "girocode": False, "steuernummer": "99/999/99999",
         "ust_idnr": "DE999999999"}


def inhalt(daten):
    """Alles Gezeichnete: Text und der GiroCode (Vektorgrafik). Ohne Erstelldatum."""
    return [p.get_contents().get_data() for p in PdfReader(io.BytesIO(daten)).pages]


def pdf(client, inv):
    r = client.get(f"/api/rechnungen/{inv}/pdf")
    assert r.status_code == 200
    return inhalt(r.data)


def aendern(client, verschickt=(), **werte):
    r = client.put("/api/einstellungen", json=(werte or UMZUG) | {"schon_verschickt": list(verschickt)})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def holen(client, inv):
    return client.get(f"/api/rechnungen/{inv}").get_json()


@pytest.fixture
def paperless(client, tmp_path):
    o = tmp_path / "consume"
    o.mkdir()
    db.save_settings({"paperless_installiert": True, "paperless_eingangsordner": str(o)})
    return o


@pytest.fixture
def post(app_modul, monkeypatch):
    raus = []
    monkeypatch.setattr(app_modul.mail, "senden", lambda a, an, betreff, text, anhaenge, **k: raus.append(anhaenge))
    return raus


def senden(client, inv, art="rechnung", **mehr):
    return client.post("/api/versand", json={"art": art, "id": inv, "an": "anna@example.org", "betreff": "x", "text": "y"} | mehr)


# ---------- jeder Weg zum Festschreiben

def w_schloss(client, inv):
    assert client.post(f"/api/rechnungen/{inv}/festschreiben").status_code == 204


def w_bezahlt(client, inv):
    assert client.patch(f"/api/rechnungen/{inv}/bezahlt", json={"bezahlt": True}).status_code == 204


def w_storno(client, inv):
    assert client.post(f"/api/rechnungen/{inv}/stornieren").status_code == 201


def w_mahnung(client, inv):
    assert client.post(f"/api/rechnungen/{inv}/mahnung").status_code == 201


def w_mail(client, inv):
    assert senden(client, inv).status_code == 200


def w_paperless(client, inv):
    assert client.post("/api/paperless", json={"ids": [inv]}).get_json()["ok"] == [inv]


@pytest.mark.parametrize("weg", [w_schloss, w_bezahlt, w_storno, w_mahnung, w_mail, w_paperless])
@pytest.mark.parametrize("feld", [None, *UMZUG])
def test_festgeschrieben_aendert_sich_nie(client, paperless, post, weg, feld):
    inv = neue_rechnung(client)
    weg(client, inv)
    vorher = pdf(client, inv)
    aendern(client, **({feld: UMZUG[feld]} if feld else {}))
    assert pdf(client, inv) == vorher
    assert holen(client, inv)["absender"]["strasse"] == "Musterweg 1"


def test_jeder_weg_hinaus_nimmt_den_festgehaltenen(client, paperless, post):
    a, b = neue_rechnung(client, "037"), neue_rechnung(client, "038")
    for i in (a, b):
        w_schloss(client, i)
    soll = pdf(client, a)
    aendern(client)
    assert inhalt(client.get(f"/api/rechnungen/download?ids={a}").data) == soll
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/rechnungen/download?ids={a},{b}").data))
    assert inhalt(z.read(next(n for n in z.namelist() if "037" in n))) == soll
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/export?jahr=2026").data))
    assert inhalt(z.read(next(n for n in z.namelist() if n.startswith("PDFs/") and "037" in n))) == soll
    w_mail(client, a)
    assert inhalt(post[0][0][1]) == soll
    w_paperless(client, a)
    assert inhalt(next(paperless.iterdir()).read_bytes()) == soll


def test_mahnung_behaelt_ihren_eigenen(client, post):
    inv = neue_rechnung(client)
    rechnung = pdf(client, inv)
    m1 = client.post(f"/api/rechnungen/{inv}/mahnung").get_json()
    eins = inhalt(client.get(f"/api/mahnungen/{m1['id']}/pdf").data)
    assert inhalt(Path(m1["datei"]).read_bytes()) == eins
    aendern(client)
    assert inhalt(client.get(f"/api/mahnungen/{m1['id']}/pdf").data) == eins
    m2 = client.post(f"/api/rechnungen/{inv}/mahnung").get_json()
    assert "Neuer Weg 9" in pdf_text(client.get(f"/api/mahnungen/{m2['id']}/pdf").data)     # neues Schreiben
    assert "Neuer Weg 9" in pdf_text(Path(m2["datei"]).read_bytes())
    assert pdf(client, inv) == rechnung
    assert senden(client, inv, "mahnung", mahnung_id=m1["id"]).status_code == 200
    assert inhalt(post[-1][0][1]) == eins and inhalt(post[-1][1][1]) == rechnung


def test_storno_ist_ein_neues_dokument(client):
    inv = neue_rechnung(client)
    w_schloss(client, inv)
    vorher = pdf(client, inv)
    aendern(client)
    storno = client.post(f"/api/rechnungen/{inv}/stornieren").get_json()
    assert "Neuer Weg 9" in pdf_text(client.get(f"/api/rechnungen/{storno['id']}/pdf").data)
    assert pdf(client, inv) == vorher
    s = pdf(client, storno["id"])
    assert inhalt(Path(storno["datei"]).read_bytes()) == s
    aendern(client, strasse="Dritter Weg 3")
    assert pdf(client, storno["id"]) == s


def test_abgelegte_kopie_gleich_wie_abruf(client):
    r = client.post("/api/rechnungen", json={"nummer": "040", "datum": "2026-11-01", "kunde": KUNDE, "zahlungsbedingung": "8 Tage",
                                             "positionen": [{"beschreibung": "DJ", "lieferdatum": "2026-11-01", "preis": 5}]}).get_json()
    assert inhalt(Path(r["datei"]).read_bytes()) == pdf(client, r["id"])


def test_haken_weg_und_wieder_hin(client):
    inv = neue_rechnung(client)
    w_bezahlt(client, inv)
    vorher = pdf(client, inv)
    client.patch(f"/api/rechnungen/{inv}/bezahlt", json={"bezahlt": False})
    aendern(client)
    w_bezahlt(client, inv)
    assert pdf(client, inv) == vorher


@pytest.mark.parametrize("weg", [w_schloss, w_bezahlt, w_storno, w_mahnung, w_mail, w_paperless])
def test_noch_einmal_festschreiben_ueberschreibt_nicht(client, paperless, post, weg):
    inv = neue_rechnung(client)
    w_schloss(client, inv)
    vorher = pdf(client, inv)
    aendern(client)
    weg(client, inv)
    assert pdf(client, inv) == vorher


def test_alte_rechnung_ohne_steuerangabe_behaelt_hinweis(app_modul, client):
    inv = neue_rechnung(client)
    with db.connect() as con:
        con.execute("UPDATE rechnungen SET kleinunternehmer = NULL WHERE id = ?", (inv,))
    w_schloss(client, inv)
    vorher = pdf(client, inv)
    db.save_settings({"kleinunternehmer": False})
    assert pdf(client, inv) == vorher


def test_girocode_am_bildschirm_nimmt_aktuelles_konto(client):
    inv = neue_rechnung(client)
    w_schloss(client, inv)
    aendern(client)
    assert client.get(f"/api/rechnungen/{inv}/girocode?info=1").get_json()["iban"] == UMZUG["iban"]


def test_angebot_folgt_den_einstellungen(client):
    a = client.post("/api/angebote", json={"nummer": "010", "datum": "2026-11-01", "kunde": KUNDE,
                                           "positionen": [{"beschreibung": "DJ", "preis": 5}]}).get_json()["id"]
    assert client.put("/api/einstellungen", json=UMZUG).status_code == 200      # keine Rückfrage
    assert "Neuer Weg 9" in pdf_text(client.get(f"/api/angebote/{a}/pdf").data)


# ---------- die Rückfrage

def test_entwurf_folgt_wenn_nicht_verschickt(client):
    inv = neue_rechnung(client)
    aendern(client)
    assert "Neuer Weg 9" in pdf_text(client.get(f"/api/rechnungen/{inv}/pdf").data)
    assert not holen(client, inv)["festgeschrieben"] and holen(client, inv)["absender"] is None


def test_schon_verschickt_behaelt_den_bisherigen(client):
    a, b = neue_rechnung(client, "037"), neue_rechnung(client, "038")
    vorher = pdf(client, a)
    aendern(client, verschickt=[a])
    assert pdf(client, a) == vorher and holen(client, a)["festgeschrieben"]
    assert not holen(client, b)["festgeschrieben"]


@pytest.mark.parametrize("antwort", [None, "alle", ["1"], [True], 1])
def test_ohne_gueltige_antwort_wird_nichts_gespeichert(client, antwort):
    inv = neue_rechnung(client)
    r = client.put("/api/einstellungen", json=UMZUG | ({} if antwort is None else {"schon_verschickt": antwort}))
    assert r.status_code == 409
    assert [x["id"] for x in r.get_json()["offene_rechnungen"]] == [inv]
    assert client.get("/api/einstellungen").get_json()["strasse"] == "Musterweg 1"
    assert not holen(client, inv)["festgeschrieben"]


@pytest.mark.parametrize("werte", [{"strasse": "  Musterweg  1 "}, {"km_satz": 0.38}, {"kleinunternehmer": False, "ust_satz": 19},
                                   {"girocode": True}, {"startnummer": 99}, {"paperless_tag_name": "Ausgaben"}, {}])
def test_keine_rueckfrage_wenn_der_absender_gleich_bleibt(client, werte):
    neue_rechnung(client)
    assert client.put("/api/einstellungen", json=werte).status_code == 200


def test_ungueltige_eingabe_schreibt_nichts_fest(client):
    inv = neue_rechnung(client)
    r = client.put("/api/einstellungen", json=UMZUG | {"km_satz": 99, "schon_verschickt": [inv]})
    assert r.status_code == 400 and not holen(client, inv)["festgeschrieben"]


def test_fremde_und_festgeschriebene_ids_bleiben_unberuehrt(client):
    fest, offen = neue_rechnung(client, "037"), neue_rechnung(client, "038")
    w_schloss(client, fest)
    aendern(client, verschickt=[fest, 999])
    assert holen(client, fest)["absender"]["quelle"] == "festgeschrieben" and not holen(client, offen)["festgeschrieben"]


def test_hinweis_nach_kontowechsel(client):
    w_schloss(client, neue_rechnung(client))
    assert any("bisherige Konto" in h for h in aendern(client, iban="DE99")["hinweise"])
    assert not any("bisherige Konto" in h for h in aendern(client, telefon="0170/1")["hinweise"])


def test_erste_einrichtung_fragt_nicht_und_traegt_nach(app_modul, client):
    db.save_settings({"strasse": "", "plz_ort": ""})
    inv = neue_rechnung(client)
    w_schloss(client, inv)
    assert holen(client, inv)["absender"] is None
    neue_rechnung(client, "038")
    assert client.put("/api/einstellungen", json={"strasse": "Musterweg 1", "plz_ort": "12345 Musterstadt"}).status_code == 200
    assert holen(client, inv)["absender"]["quelle"] == "nachgetragen"


# ---------- Bestand, Sicherung, Import

def wie_vor_172(inv=None):
    with db.connect() as con:
        con.execute("UPDATE rechnungen SET absender_json = NULL")
        con.execute("UPDATE mahnungen SET absender_json = NULL")


def test_bestand_wird_einmal_nachgetragen(app_modul, client):
    fest, offen = neue_rechnung(client, "037"), neue_rechnung(client, "038")
    m = client.post(f"/api/rechnungen/{fest}/mahnung").get_json()["id"]
    wie_vor_172()
    r, mahn = pdf(client, fest), inhalt(client.get(f"/api/mahnungen/{m}/pdf").data)
    assert app_modul.absender_festhalten() == 2 and app_modul.absender_festhalten() == 0
    assert holen(client, fest)["absender"]["quelle"] == "nachgetragen" and holen(client, offen)["absender"] is None
    aendern(client)
    assert pdf(client, fest) == r and inhalt(client.get(f"/api/mahnungen/{m}/pdf").data) == mahn


def test_spalten_kommen_bei_altem_schema(app_modul, client):
    w_schloss(client, neue_rechnung(client))
    with db.connect() as con:
        for t in ("rechnungen", "mahnungen"):
            con.execute(f"ALTER TABLE {t} DROP COLUMN absender_json")
    db.init()
    assert app_modul.absender_festhalten() == 1


def test_alte_sicherung_bekommt_ihren_eigenen_absender(client, tmp_path):
    inv = neue_rechnung(client)
    w_schloss(client, inv)
    vorher = pdf(client, inv)
    alt = tmp_path / "alt.db"
    db.sichern(str(alt))
    con = sqlite3.connect(alt)
    for t in ("rechnungen", "mahnungen"):
        con.execute(f"ALTER TABLE {t} DROP COLUMN absender_json")
    con.commit()
    con.close()
    aendern(client)
    r = client.post("/api/backup", data={"datei": (io.BytesIO(alt.read_bytes()), "alt.db")}, content_type="multipart/form-data")
    assert r.status_code == 200
    assert holen(client, inv)["absender"]["strasse"] == "Musterweg 1"
    aendern(client)
    assert pdf(client, inv) == vorher


def test_sicherung_nimmt_den_festgehaltenen_mit(client):
    inv = neue_rechnung(client)
    w_schloss(client, inv)
    vorher = pdf(client, inv)
    aendern(client)
    zf = client.get("/api/backup").data
    r = client.post("/api/backup", data={"datei": (io.BytesIO(zf), "s.zip")}, content_type="multipart/form-data")
    assert r.status_code == 200 and pdf(client, inv) == vorher


@pytest.mark.parametrize("kaputt", ["{kaputt", "[]", '"text"', '{"name": {"a": 1}, "iban": 5}'])
def test_manipulierte_sicherung_legt_nichts_lahm(client, kaputt):
    inv = neue_rechnung(client)
    w_schloss(client, inv)
    with db.connect() as con:
        con.execute("UPDATE rechnungen SET absender_json = ?", (kaputt,))
    assert client.get("/api/rechnungen").status_code == 200 and pdf(client, inv)


def test_import_haelt_fest_mit_quelle(client):
    client.post("/api/import/uebernehmen", json={"rechnungen": [{"nummer": "007", "datum": "2024-05-01", "kunde": KUNDE,
                "positionen": [{"beschreibung": "DJ", "lieferdatum": "2024-05-01", "preis": 5}]}]})
    inv = client.get("/api/rechnungen").get_json()[0]
    assert inv["absender"]["quelle"] == "import"
    vorher = pdf(client, inv["id"])
    aendern(client)
    assert pdf(client, inv["id"]) == vorher


def test_keine_geheimnisse_im_festgehaltenen(client):
    db.save_settings({"smtp_passwort": "geheim123", "paperless_token": "geheim456"})
    w_schloss(client, neue_rechnung(client))
    assert "geheim" not in json.dumps(client.get("/api/rechnungen").get_json())


# ---------- zufällige Abläufe

@pytest.mark.parametrize("saat", range(14))
def test_kein_ausgestelltes_dokument_aendert_sich_je(app_modul, client, paperless, post, saat):
    z = random.Random(saat)
    rechnungen, soll = [], {}
    for schritt in range(22):
        was = z.choice(("neu", "neu", "weg", "weg", "umzug", "umzug", "haken", "start", "sichern"))
        if was == "neu":
            rechnungen.append(neue_rechnung(client, nummer=f"{100 + schritt}", preis=100 + schritt))
        elif was == "weg" and rechnungen:
            z.choice([w_schloss, w_bezahlt, lambda c, i: c.post(f"/api/rechnungen/{i}/stornieren"),
                      lambda c, i: c.post(f"/api/rechnungen/{i}/mahnung"), w_mail, w_paperless,
                      ])(client, z.choice(rechnungen)) if z.random() < .5 else client.post(f"/api/rechnungen/{z.choice(rechnungen)}/mahnung")
        elif was == "haken" and rechnungen:
            client.patch(f"/api/rechnungen/{z.choice(rechnungen)}/bezahlt", json={"bezahlt": False})
        elif was == "umzug":
            feld = z.choice([k for k in UMZUG if k != "girocode"])
            aendern(client, verschickt=[i for i in rechnungen if z.random() < .5], **{feld: f"{UMZUG[feld]} {schritt}"})
        elif was == "start":
            db.init()
            app_modul.absender_festhalten()
        elif was == "sichern":
            zf = client.get("/api/backup").data
            assert client.post("/api/backup", data={"datei": (io.BytesIO(zf), "s.zip")}, content_type="multipart/form-data").status_code == 200
        for inv in client.get("/api/rechnungen").get_json():
            if inv["festgeschrieben"]:
                jetzt = pdf(client, inv["id"])
                assert soll.setdefault(("r", inv["id"]), jetzt) == jetzt, (saat, schritt, was)
            for m in inv["mahnungen"]:
                jetzt = inhalt(client.get(f"/api/mahnungen/{m['id']}/pdf").data)
                assert soll.setdefault(("m", m["id"]), jetzt) == jetzt, (saat, schritt, was)


# ---------- Programmstart

def test_home_assistant_traegt_beim_start_nach(app_modul, client, tmp_path):
    w_schloss(client, neue_rechnung(client))
    wie_vor_172()
    db.save_settings({"belege_ordner": ""})
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen([sys.executable, "-B", str(WURZEL / "rechnungen" / "app" / "main.py")],
                         env=os.environ | {"DATA_DIR": str(tmp_path), "PORT": str(port)},
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                r = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/rechnungen", timeout=2))
                break
            except OSError:
                time.sleep(0.25)
        assert r[0]["absender"]["quelle"] == "nachgetragen"
    finally:
        p.terminate()
        p.wait(20)


def test_desktop_traegt_nach_der_tageskopie_nach(tmp_path):
    code = f"""import sys
sys.path[:0] = [{str(WURZEL / 'desktop')!r}, {str(WURZEL / 'rechnungen' / 'app')!r}]
import start, main
folge = []
start.laufende_instanz = lambda: None
start.automatische_sicherung = lambda db: folge.append("sicherung")
main.absender_festhalten = lambda: folge.append("festhalten")
def stopp():
    print(",".join(folge), file=sys.__stdout__)
    raise SystemExit(0)
start.freier_port = stopp
start.main()"""
    r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=90,
                       env=os.environ | {"DJOS_BASIS": str(tmp_path), "DJOS_TEST": "1", "DATA_DIR": str(tmp_path)})
    assert "sicherung,festhalten" in r.stdout, r.stdout + r.stderr

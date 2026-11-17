"""E-Mail-Versand: Einstellungen (Passwort bleibt geheim), Entwurf aus Vorlagen, Versand mit Anhang, Fehler."""
import io
import smtplib
import sqlite3
import zipfile

import pytest

from conftest import KUNDE, neue_rechnung

import mail


class FakeSMTP:
    """Ersetzt smtplib.SMTP / SMTP_SSL und merkt sich, was verschickt wurde."""
    gesendet = []
    login_fehler = False

    def __init__(self, server, port, context=None, timeout=None):
        self.server, self.port, self.tls = server, port, False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        self.tls = True

    def login(self, benutzer, passwort):
        if FakeSMTP.login_fehler:
            raise smtplib.SMTPAuthenticationError(535, b"Authentication failed")
        self.benutzer, self.passwort = benutzer, passwort

    def send_message(self, msg, from_addr, to_addrs):
        FakeSMTP.gesendet.append({"msg": msg, "von": from_addr, "an": to_addrs, "tls": self.tls,
                                  "server": f"{self.server}:{self.port}", "login": getattr(self, "benutzer", None)})


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.gesendet, FakeSMTP.login_fehler = [], False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


EINRICHTUNG = {"absender_email": "max@example.org", "smtp_server": "smtp.example.org", "smtp_port": 587,
               "smtp_sicherheit": "starttls", "smtp_benutzer": "", "smtp_passwort": "geheim123",
               "telefon": "0170/1234567"}


def einrichten(client, **extra):
    r = client.put("/api/einstellungen", json=EINRICHTUNG | extra)
    assert r.status_code == 200, r.get_json()


def test_passwort_wird_nie_ausgeliefert(client):
    einrichten(client)
    e = client.get("/api/einstellungen").get_json()
    assert e["smtp_passwort"] == "" and e["smtp_passwort_gesetzt"] is True
    assert client.get("/api/absender").get_json()["mail"] is True
    # Leeres Passwortfeld beim Speichern = Passwort behalten
    client.put("/api/einstellungen", json={"smtp_passwort": "", "name": "Max Beispiel"})
    import db
    assert db.get_settings()["smtp_passwort"] == "geheim123"
    # null = löschen
    client.put("/api/einstellungen", json={"smtp_passwort": None})
    assert client.get("/api/einstellungen").get_json()["smtp_passwort_gesetzt"] is False


def test_einstellungen_pruefen_adresse_und_verschluesselung(client):
    r = client.put("/api/einstellungen", json={"absender_email": "keine-adresse"})
    assert r.status_code == 400
    r = client.put("/api/einstellungen", json={"smtp_sicherheit": "irgendwas"})
    assert r.status_code == 400
    # leere Vorlage → Standardtext
    client.put("/api/einstellungen", json={"mail_text_rechnung": "  "})
    assert client.get("/api/einstellungen").get_json()["mail_text_rechnung"] == mail.VORLAGEN["mail_text_rechnung"]


def test_sicherung_enthaelt_kein_passwort(client, tmp_path):
    einrichten(client)
    r = client.get("/api/backup")
    pfad = tmp_path / "aus_zip.db"
    pfad.write_bytes(zipfile.ZipFile(io.BytesIO(r.data)).read("rechnungen.db"))
    con = sqlite3.connect(pfad)
    try:
        schluessel = {s for (s,) in con.execute("SELECT schluessel FROM einstellungen")}
    finally:
        con.close()
    assert "smtp_passwort" not in schluessel and "smtp_server" in schluessel
    assert b"geheim123" not in pfad.read_bytes()
    # Einspielen behält das aktuell gespeicherte Passwort
    client.post("/api/backup", data={"datei": (io.BytesIO(r.data), "s.zip")}, content_type="multipart/form-data")
    assert client.get("/api/einstellungen").get_json()["smtp_passwort_gesetzt"] is True


def test_vorlagen_platzhalter_und_leere_zeilen():
    t = mail.fuellen("Hallo {kunde},\nbitte bis zum {faellig} zahlen.\nGruß {absender}\n{unbekannt}",
                     {"kunde": "Anna", "faellig": "", "absender": "Max"})
    assert t == "Hallo Anna,\nGruß Max\n{unbekannt}"
    assert mail.adressen("a@b.de; c@d.org") == ["a@b.de", "c@d.org"]
    with pytest.raises(ValueError):
        mail.adressen("a@b")


def test_entwurf_und_versand_rechnung(client, smtp):
    einrichten(client)
    inv = neue_rechnung(client, datum="2026-11-01")
    # E-Mail-Adresse fehlt noch beim Kunden
    e = client.get(f"/api/versand/entwurf?art=rechnung&id={inv}").get_json()
    assert e["an"] == "" and e["konfiguriert"] and e["kopie"] is True
    assert e["betreff"] == "Rechnung 037 vom 01.11.2026"
    assert "Hallo Anna Muster," in e["text"] and "960,- Euro" in e["text"] and "bis zum 09.11.2026" in e["text"]
    assert e["text"].endswith("Max Beispiel\n0170/1234567")
    assert e["anhaenge"] == ["Rechnung_037_011126.pdf"]

    r = client.post("/api/versand", json={"art": "rechnung", "id": inv, "an": "anna@example.de",
                                           "betreff": e["betreff"], "text": e["text"], "kopie": True,
                                           "email_speichern": True})
    assert r.status_code == 200, r.get_json()
    s = smtp.gesendet[0]
    assert s["an"] == ["anna@example.de", "max@example.org"]          # Kopie an mich (BCC)
    assert "max@example.org" not in s["msg"]["To"] and s["msg"].get("Bcc") is None
    assert s["tls"] and s["login"] == "max@example.org" and s["server"] == "smtp.example.org:587"
    assert s["msg"]["From"] == "Max Beispiel <max@example.org>"
    anhang = next(s["msg"].iter_attachments())
    assert anhang.get_filename() == "Rechnung_037_011126.pdf" and anhang.get_content()[:5] == b"%PDF-"

    rechnung = client.get(f"/api/rechnungen/{inv}").get_json()
    assert rechnung["festgeschrieben"] and rechnung["versand"][0]["an"] == "anna@example.de"
    kunde = next(k for k in client.get("/api/kunden").get_json() if k["name"] == KUNDE["name"])
    assert kunde["email"] == "anna@example.de"
    # Nächster Entwurf kennt die Adresse
    assert client.get(f"/api/versand/entwurf?art=rechnung&id={inv}").get_json()["an"] == "anna@example.de"


def test_versand_mahnung_mit_beiden_pdfs(client, smtp):
    einrichten(client, smtp_sicherheit="ssl", smtp_port=465)
    inv = neue_rechnung(client, datum="2026-10-01")
    m = client.post(f"/api/rechnungen/{inv}/mahnung").get_json()
    e = client.get(f"/api/versand/entwurf?art=mahnung&id={inv}&mahnung_id={m['id']}").get_json()
    assert e["betreff"] == "Zahlungserinnerung zur Rechnung 037"
    assert e["anhaenge"][0].startswith("Zahlungserinnerung_037") and e["anhaenge"][1].startswith("Rechnung_037")
    r = client.post("/api/versand", json={"art": "mahnung", "id": inv, "mahnung_id": m["id"], "an": "anna@example.de",
                                           "betreff": e["betreff"], "text": e["text"], "kopie": False})
    assert r.status_code == 200
    assert len(list(smtp.gesendet[0]["msg"].iter_attachments())) == 2 and not smtp.gesendet[0]["tls"]
    assert smtp.gesendet[0]["an"] == ["anna@example.de"]
    assert client.get(f"/api/rechnungen/{inv}").get_json()["versand"][0]["mahnung_id"] == m["id"]


def test_versand_angebot_bleibt_offen(client, smtp):
    einrichten(client)
    r = client.post("/api/angebote", json={"nummer": "010", "datum": "2026-11-01", "gueltig_bis": "2026-12-01",
                                           "kunde": KUNDE, "positionen": [{"beschreibung": "DJ", "preis": 900}]})
    aid = r.get_json()["id"]
    e = client.get(f"/api/versand/entwurf?art=angebot&id={aid}").get_json()
    assert "gilt bis zum 01.12.2026" in e["text"]
    client.post("/api/versand", json={"art": "angebot", "id": aid, "an": "anna@example.de",
                                      "betreff": e["betreff"], "text": e["text"]})
    a = client.get(f"/api/angebote/{aid}").get_json()
    assert a["status"] == "offen" and len(a["versand"]) == 1


def test_fehler_werden_verstaendlich_gemeldet(client, smtp):
    inv = neue_rechnung(client)
    daten = {"art": "rechnung", "id": inv, "an": "anna@example.de", "betreff": "x", "text": "y"}
    r = client.post("/api/versand", json=daten)   # noch nicht eingerichtet
    assert r.status_code == 502 and "nicht eingerichtet" in r.get_json()["error"]
    einrichten(client)
    assert client.post("/api/versand", json=daten | {"an": "kaputt"}).status_code == 400
    smtp.login_fehler = True
    r = client.post("/api/versand", json=daten)
    assert r.status_code == 502 and "App-Passwort" in r.get_json()["error"]
    # nichts verschickt → nicht festgeschrieben, kein Protokoll
    rechnung = client.get(f"/api/rechnungen/{inv}").get_json()
    assert not rechnung["festgeschrieben"] and rechnung["versand"] == []


def test_testmail_mit_formularwerten(client, smtp):
    r = client.post("/api/versand/test", json=EINRICHTUNG | {"smtp_server": "mail.eigener-server.de", "smtp_port": "2525"})
    assert r.status_code == 200, r.get_json()
    assert smtp.gesendet[0]["server"] == "mail.eigener-server.de:2525" and smtp.gesendet[0]["an"] == ["max@example.org"]

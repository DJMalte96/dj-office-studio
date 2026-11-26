"""Seit 1.16: Belege aus dem Postfach (IMAP) nach eigenen Regeln – mit nachgestelltem IMAP-Server."""
import imaplib
import json
from pathlib import Path

import pytest

MAILS = Path(__file__).parent / "beispiele" / "mails"


class FakeIMAP:
    """Kleiner IMAP-Server zum Testen: Ordner mit Trenner, Mails mit UID und \\Seen."""
    letzte = None

    def __init__(self, host, port=993, ssl_context=None, timeout=None, trenner="/"):
        self.host, self.trenner, self.gewaehlt, self.angemeldet = host, trenner, None, False
        t = trenner
        self.ordner = {   # echter Name (modifiziertes UTF-7) → {uid: [bytes, gelesen]}
            "INBOX": {1: [self._mail("Kino", "freund@example.com"), False]},
            f"Gesch&AOQ-ftlich{t}Belege{t}Musik": {
                5: [(MAILS / "beatport.eml").read_bytes(), False],
                6: [(MAILS / "apple.eml").read_bytes(), True],          # schon am Handy gelesen
            },
            f"Gesch&AOQ-ftlich{t}Belege{t}Technik": {9: [(MAILS / "amazon.eml").read_bytes(), False]},
            f"Gesch&AOQ-ftlich{t}Kunden": {3: [self._mail("Anfrage Hochzeit", "kunde@example.com"), False]},
        }
        FakeIMAP.letzte = self

    @staticmethod
    def _mail(betreff, von):
        return (f"From: {von}\r\nTo: max@example.com\r\nSubject: {betreff}\r\nDate: Mon, 09 Nov 2026 10:00:00 +0000\r\n"
                f"Message-ID: <{betreff.replace(' ', '')}@example.invalid>\r\n\r\nHallo\r\n").encode()

    def login(self, benutzer, passwort):
        if passwort != "geheim":
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        self.angemeldet = True
        return "OK", [b"ok"]

    def list(self):
        return "OK", [f'(\\HasChildren) "{self.trenner}" "{n}"'.encode() for n in self.ordner] + \
            [f'(\\Noselect) "{self.trenner}" "Gesch&AOQ-ftlich"'.encode()]

    def select(self, name, readonly=False):
        name = name.strip('"')
        if name not in self.ordner:
            return "NO", [b"no such folder"]
        self.gewaehlt = name
        return "OK", [str(len(self.ordner[name])).encode()]

    def response(self, code):
        return code, [b"4711"]

    def uid(self, befehl, *args):
        mails = self.ordner[self.gewaehlt]
        if befehl == "SEARCH":
            return "OK", [" ".join(str(u) for u in sorted(mails)).encode()]
        u = int(args[0])
        if befehl == "FETCH":
            roh = mails[u][0]
            if "HEADER.FIELDS" in args[1]:
                roh = roh.split(b"\r\n\r\n")[0].split(b"\n\n")[0] + b"\r\n\r\n"
            return "OK", [(f"{u} (UID {u} BODY[] {{{len(roh)}}}".encode(), roh), b")"]
        if befehl == "STORE":
            mails[u][1] = True
            return "OK", [b""]
        raise AssertionError(befehl)

    def logout(self):
        return "BYE", [b""]


@pytest.fixture
def imap(monkeypatch, client):
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeIMAP)
    client.put("/api/einstellungen", json={"absender_email": "max@example.com", "smtp_server": "smtp.web.de",
                                           "smtp_passwort": "geheim", "postfach_an": True, "postfach_ab": "2026-10-01"})
    return FakeIMAP


def regeln(client, *liste):
    r = client.put("/api/einstellungen", json={"postfach_regeln": json.dumps(list(liste))})
    assert r.status_code == 200, r.get_json()


def test_server_aus_anbieter(client):
    import postfach
    assert postfach.imap_server({"smtp_server": "smtp.web.de"}) == "imap.web.de"
    assert postfach.imap_server({"smtp_server": "smtp.gmail.com"}) == "imap.gmail.com"
    assert postfach.imap_server({"smtp_server": "smtp.mein-server.de"}) == "imap.mein-server.de"
    assert postfach.imap_server({"smtp_server": "smtp.web.de", "imap_server": "mail.eigen.de"}) == "mail.eigen.de"


def test_ordnernamen_utf7():
    import postfach
    for name in ("Geschäftlich", "Rechnungen & Belege", "Ärger/Übersicht", "Kasse € 2026", "Posteingang"):
        assert postfach._utf7_lesen(postfach._utf7_kodieren(name)) == name
    assert postfach._utf7_kodieren("Geschäftlich") == "Gesch&AOQ-ftlich"


def test_regeln_werden_geprueft(client):
    assert client.put("/api/einstellungen", json={"postfach_regeln": "kaputt"}).status_code == 400
    assert client.put("/api/einstellungen", json={"postfach_regeln": json.dumps([{"ordner": "x"}] * 31)}).status_code == 400
    regeln(client, {"an": True, "ordner": " Geschäftlich / Belege/ ", "von": "  ", "betreff": ""}, {"ordner": "", "von": "", "betreff": ""})
    import db
    assert json.loads(db.get_settings()["postfach_regeln"]) == [{"an": True, "ordner": "Geschäftlich/Belege", "von": "", "betreff": ""}]


def test_ordner_liste(client, imap):
    d = client.post("/api/postfach/ordner").get_json()
    assert d["ordner"][0] == "Posteingang"
    assert "Geschäftlich/Belege/Musik" in d["ordner"] and "Geschäftlich" not in d["ordner"]   # \Noselect fällt weg


@pytest.mark.parametrize("trenner", ["/", "."])
def test_abholen_nach_regeln(client, imap, monkeypatch, trenner):
    monkeypatch.setattr(imaplib, "IMAP4_SSL", lambda *a, **k: FakeIMAP(*a, trenner=trenner, **k))
    regeln(client, {"an": True, "ordner": "geschäftlich/belege/musik", "von": "", "betreff": ""},
           {"an": True, "ordner": "Geschäftlich/Belege/Technik", "von": "amazon", "betreff": ""},
           {"an": False, "ordner": "Posteingang", "von": "", "betreff": ""},
           {"an": True, "ordner": "Gibt/Es/Nicht", "von": "", "betreff": ""})
    st = client.post("/api/postfach/abholen").get_json()
    assert st["neu"] == 3 and st["doppelt"] == 0, st
    assert any("Gibt/Es/Nicht" in f for f in st["fehler"])
    fake = FakeIMAP.letzte
    musik = fake.ordner[f"Gesch&AOQ-ftlich{trenner}Belege{trenner}Musik"]
    assert musik[5][1] and musik[6][1]                         # als gelesen markiert (auch die schon gelesene geholt)
    assert not fake.ordner["INBOX"][1][1]                     # abgeschaltete Regel: Posteingang unberührt
    assert not fake.ordner[f"Gesch&AOQ-ftlich{trenner}Kunden"][3][1]
    lieferanten = sorted(a["lieferant"] for a in client.get("/api/ausgaben").get_json())
    assert len(lieferanten) == 3 and any("Amazon" in l for l in lieferanten)
    # zweiter Lauf: nichts doppelt
    st = client.post("/api/postfach/abholen").get_json()
    assert st["neu"] == 0 and st["doppelt"] == 0
    assert len(client.get("/api/ausgaben").get_json()) == 3
    assert client.get("/api/postfach").get_json()["stand"]["ordner"] == ["geschäftlich/belege/musik", "Geschäftlich/Belege/Technik"]


def test_filter_absender_und_betreff(client, imap):
    regeln(client, {"an": True, "ordner": "Geschäftlich/Belege/Musik", "von": "beatport", "betreff": ""})
    assert client.post("/api/postfach/abholen").get_json()["neu"] == 1
    regeln(client, {"an": True, "ordner": "Geschäftlich/Belege/Musik", "von": "", "betreff": "gibt es nicht"})
    assert client.post("/api/postfach/abholen").get_json()["neu"] == 0


def test_regeln_pruefen(client, imap):
    regeln(client, {"an": True, "ordner": "Geschäftlich/Belege/Musik", "von": "", "betreff": ""},
           {"an": True, "ordner": "Geschäftlich/Belege/Falsch", "von": "", "betreff": ""})
    r = client.post("/api/postfach/pruefen").get_json()["regeln"]
    assert r == [{"ordner": "Geschäftlich/Belege/Musik", "gefunden": True, "passend": 2},
                 {"ordner": "Geschäftlich/Belege/Falsch", "gefunden": False, "passend": 0}]
    assert not FakeIMAP.letzte.ordner["Gesch&AOQ-ftlich/Belege/Musik"][5][1]   # Prüfen markiert nichts als gelesen


def test_falsches_passwort_und_nicht_eingerichtet(client, imap):
    client.put("/api/einstellungen", json={"smtp_passwort": "falsch"})
    regeln(client, {"an": True, "ordner": "Posteingang", "von": "", "betreff": ""})
    st = client.post("/api/postfach/abholen").get_json()
    assert st["neu"] == 0 and "Anmeldung" in st["fehler"][0]
    assert "Anmeldung" in client.post("/api/postfach/ordner").get_json()["error"]
    client.put("/api/einstellungen", json={"smtp_passwort": None})
    assert "einrichten" in client.post("/api/postfach/pruefen").get_json()["error"]

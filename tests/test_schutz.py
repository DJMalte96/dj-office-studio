"""1.7.3: Schutz vor fremden Webseiten, anderen Add-ons und präparierten Sicherungen; Geheimnisse nur an bekannte Server."""
import base64
import http.server
import io
import os
import re
import socket
import threading
import zipfile
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "rechnungen" / "app" / "static"
FREMD = {"Origin": "https://boese.example", "Sec-Fetch-Site": "cross-site"}


def _roh(app_modul):
    """Client wie eine fremde Webseite: ohne den Kopf der App."""
    return app_modul.app.test_client()


# ---------- Kopf, Herkunft, Host, Absender-Adresse ----------

@pytest.mark.parametrize("methode, pfad", [("post", "/api/rechnungen"), ("put", "/api/einstellungen"),
                                           ("delete", "/api/rechnungen/1"), ("post", "/api/backup"),
                                           ("post", "/api/ausgaben/belege"), ("post", "/api/import/analyse"),
                                           ("patch", "/api/rechnungen/1/bezahlt")])
def test_aendernde_anfragen_ohne_kopf_abgewiesen(app_modul, methode, pfad):
    r = getattr(_roh(app_modul), methode)(pfad, headers=FREMD)
    assert r.status_code == 403
    assert "nicht aus DJ Office Studio" in r.get_json()["error"]


def test_fremde_seite_kann_keine_sicherung_einspielen(app_modul, client):
    vorher = client.get("/api/einstellungen").get_json()["name"]
    sicherung = client.get("/api/backup").data
    client.put("/api/einstellungen", json={"name": "Neu Name"})
    r = _roh(app_modul).post("/api/backup", data={"datei": (io.BytesIO(sicherung), "s.zip")},
                             content_type="multipart/form-data", headers=FREMD)
    assert r.status_code == 403
    assert client.get("/api/einstellungen").get_json()["name"] == "Neu Name" != vorher


def test_fremde_seite_kann_keine_belege_einschleusen(app_modul, client):
    r = _roh(app_modul).post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(b"%PDF-1.4 x"), "x.pdf")]},
                             content_type="multipart/form-data")
    assert r.status_code == 403
    assert client.get("/api/ausgaben").get_json() == []


def test_kopf_allein_reicht_nicht_bei_fremder_herkunft(client):
    assert client.put("/api/einstellungen", json={"name": "X"}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.put("/api/einstellungen", json={"name": "X"}, headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert client.put("/api/einstellungen", json={"name": "X"}, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_lesen_ohne_kopf_moeglich(app_modul):
    assert _roh(app_modul).get("/api/absender").status_code == 200
    assert _roh(app_modul).get("/").status_code == 200


@pytest.mark.parametrize("host, erlaubt", [("127.0.0.1:8765", True), ("localhost:8766", True), ("127.0.0.1", True),
                                           ("LOCALHOST:8765", True), ("boese.example:8765", False),
                                           ("127.0.0.1.boese.example:8765", False), ("[::1]:8765", False)])
def test_desktop_nur_ueber_127_0_0_1(app_modul, client, monkeypatch, host, erlaubt):
    monkeypatch.setattr(app_modul, "DESKTOP", True)
    r = client.get("/api/backup", headers={"Host": host})
    assert (r.status_code == 200) is erlaubt
    if not erlaubt:
        assert r.status_code == 403 and not r.data.startswith(b"PK")


def test_home_assistant_nur_ueber_ingress(app_modul, client, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "x")
    for adresse, erlaubt in (("172.30.32.2", True), ("127.0.0.1", True), ("172.30.33.7", False), ("172.30.32.1", False)):
        r = client.get("/api/backup", environ_base={"REMOTE_ADDR": adresse, "HTTP_X_DJOS": "1"})
        assert (r.status_code == 200) is erlaubt, adresse
    monkeypatch.delenv("SUPERVISOR_TOKEN")
    assert client.get("/api/absender", environ_base={"REMOTE_ADDR": "172.30.33.7"}).status_code == 200


def test_oberflaeche_schickt_den_kopf_bei_jeder_aenderung():
    """Jeder fetch(), der etwas ändert, muss den Kopf tragen – sonst ginge der Knopf in der App nicht mehr."""
    for datei in ("app.js", "finanzen.js"):
        text = (STATIC / datei).read_text(encoding="utf-8")
        for m in re.finditer(r"fetch\(([^;]*)", text):
            aufruf = m.group(1)
            if "method:" in aufruf:
                assert "SCHUTZ" in aufruf, (datei, aufruf[:80])
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'const SCHUTZ = { "X-DJOS": "1" };' in app
    assert re.search(r'headers: opts\.body \? \{ "Content-Type": "application/json", \.\.\.SCHUTZ \} : SCHUTZ', app)


# ---------- Geheimnisse nur an den gespeicherten Server ----------

class _Paperless(http.server.BaseHTTPRequestHandler):
    gesehen = []

    def do_GET(self):
        _Paperless.gesehen.append((self.server.server_port, self.path, self.headers.get("Authorization")))
        if self.path.startswith("/weiter"):
            self.send_response(302)
            self.send_header("Location", self.path.split("ziel=", 1)[1])
            self.end_headers()
            return
        self.send_response(200 if self.headers.get("Authorization") or self.path == "/api/" else 401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"count":0,"next":null,"results":[]}')

    def log_message(self, *a):
        pass


@pytest.fixture
def paperless_server():
    _Paperless.gesehen = []
    server = [http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Paperless) for _ in range(2)]
    for s in server:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    yield [f"http://127.0.0.1:{s.server_port}" for s in server]
    for s in server:
        s.shutdown()


def test_paperless_token_nur_an_gespeicherte_adresse(app_modul, client, paperless_server):
    eigen, fremd = paperless_server
    app_modul.db.save_settings({"paperless_url": eigen, "paperless_token": "GEHEIM123"})
    r = client.post("/api/paperless/verbinden", json={"url": fremd})
    assert r.status_code == 200 and r.get_json()["tags"] is None   # → neu anmelden
    assert not any(auth for _, _, auth in _Paperless.gesehen)
    r = client.post("/api/paperless/verbinden", json={"url": eigen})
    assert r.get_json()["tags"] == []
    assert ("Token GEHEIM123") in [auth for _, _, auth in _Paperless.gesehen]
    # frisch eingegebener Token darf an die neue Adresse
    _Paperless.gesehen.clear()
    assert client.post("/api/paperless/verbinden", json={"url": fremd, "token": "NEU"}).get_json()["tags"] == []
    assert [auth for _, _, auth in _Paperless.gesehen if auth] == ["Token NEU"]


def test_paperless_umleitung_auf_anderen_rechner_ohne_token(paperless_server, app_modul):
    import paperless
    eigen, _ = paperless_server
    anderer = eigen.replace("127.0.0.1", "localhost")
    with pytest.raises(paperless.PaperlessFehler):   # dort ohne Token → 401
        paperless._anfrage(eigen, "GEHEIM123", f"/weiter?ziel={anderer}/api/tags/")
    assert _Paperless.gesehen[-1][2] is None
    # gleicher Rechner: Token bleibt
    assert paperless._anfrage(eigen, "GEHEIM123", f"/weiter?ziel={eigen}/api/tags/")["results"] == []
    assert _Paperless.gesehen[-1][2] == "Token GEHEIM123"


def test_paperless_antworten_begrenzt(monkeypatch, app_modul):
    import paperless

    class Endlos:
        def read(self, n=-1):
            return b"x" * n
    with pytest.raises(paperless.PaperlessFehler, match="zu groß"):
        paperless._lesen(Endlos(), 1000)
    seiten = []
    monkeypatch.setattr(paperless, "_anfrage", lambda *a, **k: seiten.append(1) or {"results": [1], "next": "/api/tags/?page=2"})
    with pytest.raises(paperless.PaperlessFehler, match="viele Seiten"):
        paperless._alle("http://x", "t", "/api/tags/")
    assert len(seiten) == paperless.MAX_SEITEN


def _smtp_falle():
    """Mini-SMTP-Server, der ein AUTH PLAIN mitliest."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(2)
    gelesen = []

    def laufen():
        while True:
            try:
                k, _ = s.accept()
            except OSError:
                return
            f = k.makefile("rwb")

            def w(x):
                f.write(x.encode() + b"\r\n")
                f.flush()
            w("220 hallo")
            while True:
                zeile = f.readline().decode().strip()
                if not zeile:
                    break
                if zeile.upper().startswith("EHLO"):
                    w("250-hallo")
                    w("250 AUTH PLAIN")
                elif zeile.upper().startswith("AUTH PLAIN"):
                    gelesen.append(base64.b64decode(zeile.split()[-1]).split(b"\0")[-1].decode())
                    w("535 nein")
                elif zeile.upper().startswith("QUIT"):
                    w("221 tschuess")
                    break
                else:
                    w("250 ok")
            k.close()
    threading.Thread(target=laufen, daemon=True).start()
    return s, s.getsockname()[1], gelesen


def test_mailpasswort_nie_an_anderen_server(app_modul, client):
    s, port, gelesen = _smtp_falle()
    app_modul.db.save_settings({"absender_email": "max@example.com", "smtp_server": "smtp.example.com", "smtp_port": 587,
                                "smtp_benutzer": "max", "smtp_passwort": "GEHEIMPASSWORT"})
    r = client.post("/api/versand/test", json={"smtp_server": "127.0.0.1", "smtp_port": port, "smtp_sicherheit": "keine"})
    assert r.status_code == 502 and "Passwort neu eingeben" in r.get_json()["error"]
    r = client.post("/api/versand/test", json={"smtp_server": "smtp.example.com", "smtp_benutzer": "anderer"})
    assert r.status_code == 502 and "Passwort neu eingeben" in r.get_json()["error"]
    assert gelesen == []
    # frisch eingegebenes Passwort darf zum neuen Server
    client.post("/api/versand/test", json={"smtp_server": "127.0.0.1", "smtp_port": port, "smtp_sicherheit": "keine",
                                           "smtp_passwort": "NEU"})
    assert gelesen == ["NEU"]
    # gespeicherter Server (Groß-/Kleinschreibung egal) → gespeichertes Passwort
    app_modul.db.save_settings({"smtp_server": "127.0.0.1"})
    client.post("/api/versand/test", json={"smtp_server": " 127.0.0.1 ", "smtp_benutzer": "MAX", "smtp_port": port,
                                           "smtp_sicherheit": "keine"})
    assert gelesen == ["NEU", "GEHEIMPASSWORT"]
    # ohne Benutzer meldet sich die App mit der Absenderadresse an – auch dann nicht an einen neuen Server
    app_modul.db.save_settings({"smtp_server": "smtp.example.com", "smtp_benutzer": ""})
    r = client.post("/api/versand/test", json={"smtp_server": "127.0.0.1", "smtp_port": port, "smtp_sicherheit": "keine"})
    assert r.status_code == 502 and "Passwort neu eingeben" in r.get_json()["error"]
    assert gelesen == ["NEU", "GEHEIMPASSWORT"]
    # ohne gespeichertes Passwort darf der Test zu jedem Server (ohne Anmeldung)
    app_modul.db.save_settings({"smtp_passwort": ""})
    r = client.post("/api/versand/test", json={"smtp_server": "127.0.0.1", "smtp_port": port, "smtp_sicherheit": "keine"})
    assert "Passwort" not in r.get_json().get("error", "")   # bis zum Server gekommen (der Test-Server kann kein DATA)
    assert gelesen == ["NEU", "GEHEIMPASSWORT"]
    s.close()


def test_einstellungen_neuer_server_verwirft_passwort(app_modul, client):
    app_modul.db.save_settings({"smtp_server": "smtp.example.com", "smtp_benutzer": "max", "smtp_passwort": "P",
                                "paperless_url": "http://paperless:8000", "paperless_token": "T"})
    get = app_modul.db.get_settings
    # Port, Schreibweise, gleiche Paperless-Adresse in anderer Form → bleibt
    r = client.put("/api/einstellungen", json={"smtp_server": "SMTP.example.com ", "smtp_port": 465,
                                               "paperless_url": "paperless:8000/api/"}).get_json()
    assert get()["smtp_passwort"] == "P" and get()["paperless_token"] == "T"
    assert not any("Passwort" in h or "Paperless-Adresse" in h for h in r["hinweise"])
    r = client.put("/api/einstellungen", json={"smtp_server": "mail.anders.de", "paperless_url": "http://anders:8000"}).get_json()
    assert get()["smtp_passwort"] == "" and get()["paperless_token"] == ""
    assert any("E-Mail-Passwort wurde entfernt" in h for h in r["hinweise"])
    assert any("Paperless-Adresse geändert" in h for h in r["hinweise"])
    assert r["einstellungen"]["smtp_passwort_gesetzt"] is False
    # neuer Server mit neuem Passwort → wird gespeichert
    client.put("/api/einstellungen", json={"smtp_server": "mail.dritter.de", "smtp_passwort": "Q", "smtp_benutzer": "neu"})
    assert get()["smtp_passwort"] == "Q"


# ---------- Sicherungen ----------

def _zip(dateien):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, inhalt in dateien.items():
            z.writestr(name, inhalt)
    return buf.getvalue()


def test_zip_bombe_wird_nicht_eingespielt(app_modul, client, tmp_path):
    from conftest import neue_rechnung
    neue_rechnung(client)
    db_bytes = zipfile.ZipFile(io.BytesIO(client.get("/api/backup").data)).read("rechnungen.db")
    assert client.put("/api/einstellungen", json={"name": "Stand vorher", "schon_verschickt": []}).status_code == 200
    bombe = _zip({"rechnungen.db": db_bytes, "belege/2026/gross.bin": b"\0" * (200 * 1024 * 1024)})
    assert len(bombe) < 2 * 1024 * 1024
    r = client.post("/api/backup", data={"datei": (io.BytesIO(bombe), "s.zip")}, content_type="multipart/form-data")
    assert r.status_code == 413 and "ungewöhnlich groß" in r.get_json()["error"]
    assert client.get("/api/einstellungen").get_json()["name"] == "Stand vorher"
    assert not (tmp_path / "belege" / "2026" / "gross.bin").exists()
    # auch die Datenbank selbst zählt
    r = client.post("/api/backup", data={"datei": (io.BytesIO(_zip({"rechnungen.db": b"\0" * (200 * 1024 * 1024)})), "s.zip")},
                    content_type="multipart/form-data")
    assert r.status_code == 413


def test_zu_viele_dateien(app_modul, client, monkeypatch):
    monkeypatch.setattr(app_modul, "SICHERUNG_MAX_DATEIEN", 5)
    db_bytes = zipfile.ZipFile(io.BytesIO(client.get("/api/backup").data)).read("rechnungen.db")
    z = _zip({"rechnungen.db": db_bytes} | {f"belege/{i}.pdf": b"%PDF" for i in range(6)})
    assert client.post("/api/backup", data={"datei": (io.BytesIO(z), "s.zip")},
                       content_type="multipart/form-data").status_code == 413


def test_echte_sicherung_mit_belegen_geht_weiter(app_modul, client, tmp_path):
    """Belege (kaum packbar) und eine große, gut packbare Datenbank liegen weit unter der Grenze."""
    client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(os.urandom(3 * 1024 * 1024)), "foto.jpg")]},
                content_type="multipart/form-data")
    sicherung = client.get("/api/backup").data
    for f in (tmp_path / "belege").rglob("*"):
        if f.is_file():
            f.unlink()
    r = client.post("/api/backup", data={"datei": (io.BytesIO(sicherung), "s.zip")}, content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["belege"] == 1


def test_kein_platz(app_modul, client, monkeypatch):
    import shutil
    sicherung = client.get("/api/backup").data
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(10**9, 10**9 - 1000, 1000))
    r = client.post("/api/backup", data={"datei": (io.BytesIO(sicherung), "s.zip")}, content_type="multipart/form-data")
    assert r.status_code == 507

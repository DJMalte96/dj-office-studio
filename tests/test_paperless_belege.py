"""Finanzen – Belege aus Paperless-ngx abholen (gegen einen nachgebauten Paperless-Server)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from fpdf import FPDF

TOKEN = "geheim123"


def _pdf(zeilen):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for z in zeilen:
        pdf.cell(0, 8, z, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _scan():
    pdf = FPDF()
    pdf.add_page()
    pdf.rect(20, 20, 100, 60)          # nur Grafik, kein Text – wie ein Foto/Scan ohne Textebene
    return bytes(pdf.output())


DOKUMENTE = {
    11: {"title": "Kabel und Adapter", "created": "2026-03-04", "correspondent": 5, "tags": [7],
         "datei": "kabel.pdf", "daten": _pdf(["Musterhaus Technik GmbH", "Rechnung Nr. 4711", "Datum: 04.03.2026",
                                              "2x XLR-Kabel 10 m   39,80 EUR", "Gesamtbetrag 39,80 EUR"]),
         "content": "Musterhaus Technik GmbH Rechnung 4711 Gesamtbetrag 39,80 EUR"},
    12: {"title": "Parkhaus Beleg", "created": "2026-05-09", "correspondent": None, "tags": [7],
         "datei": "scan.pdf", "daten": _scan(), "content": "PARKHAUS AM MARKT\n09.05.2026\nSumme EUR 12,50\nVielen Dank"},
    13: {"title": "Stromrechnung privat", "created": "2026-01-02", "correspondent": 6, "tags": [8],
         "datei": "strom.pdf", "daten": _pdf(["Stadtwerke", "Gesamt 80,00 EUR"]), "content": "Gesamt 80,00 EUR"},
}


class FakePaperless(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, daten, code=200):
        roh = json.dumps(daten).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(roh)

    def do_POST(self):
        if self.path == "/api/token/":
            laenge = int(self.headers.get("Content-Length") or 0)
            q = {k: v[0] for k, v in parse_qs(self.rfile.read(laenge).decode()).items()}
            if q.get("username") == "max" and q.get("password") == "pw":
                return self._json({"token": TOKEN})
            return self._json({"non_field_errors": ["Unable to log in with provided credentials."]}, 400)
        self._json({"detail": "Nicht gefunden."}, 404)

    def do_GET(self):
        teile = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(teile.query).items()}
        if self.headers.get("Authorization") != f"Token {TOKEN}":
            return self._json({"detail": "Ungültiges Token."}, 401)
        if teile.path == "/api/tags/":
            return self._json({"next": None, "results": [{"id": 7, "name": "Ausgaben DJ", "document_count": 2},
                                                         {"id": 8, "name": "Privat", "document_count": 1}]})
        if teile.path == "/api/correspondents/":
            return self._json({"next": None, "results": [{"id": 5, "name": "Musterhaus Technik"}, {"id": 6, "name": "Stadtwerke"}]})
        if teile.path == "/api/documents/":
            treffer = [{"id": i, **{k: d[k] for k in ("title", "created", "correspondent", "content")},
                        "original_file_name": d["datei"]}
                       for i, d in sorted(DOKUMENTE.items()) if int(q["tags__id__all"]) in d["tags"]]
            seite = int(q.get("page", 1))                         # 1 Dokument je Seite → Seitenaufteilung wird geprüft
            naechste = f"http://anderer-host:9999/api/documents/?{teile.query.split('&page=')[0]}&page={seite + 1}" \
                if seite < len(treffer) else None
            return self._json({"count": len(treffer), "next": naechste, "results": treffer[seite - 1:seite]})
        if teile.path.startswith("/api/documents/") and teile.path.endswith("/download/"):
            d = DOKUMENTE[int(teile.path.split("/")[3])]
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'attachment; filename="{d["datei"]}"')
            self.end_headers()
            self.wfile.write(d["daten"])
            return
        self._json({"detail": "Nicht gefunden."}, 404)


@pytest.fixture()
def paperless_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakePaperless)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture()
def eingerichtet(client, paperless_server, monkeypatch):
    import finanzen
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    client.put("/api/einstellungen", json={"paperless_installiert": True, "paperless_url": paperless_server + "/api/", "paperless_token": TOKEN,
                                           "paperless_tag": "7", "paperless_tag_name": "Ausgaben DJ"})
    return paperless_server


def test_verbinden_laedt_tags_und_prueft_token(client, paperless_server):
    r = client.post("/api/paperless/verbinden", json={"url": paperless_server, "token": "falsch"})
    assert r.status_code == 400 and "Token" in r.get_json()["error"]
    r = client.post("/api/paperless/verbinden", json={"url": paperless_server, "token": TOKEN}).get_json()
    assert [t["name"] for t in r["tags"]] == ["Ausgaben DJ", "Privat"]
    r = client.post("/api/paperless/verbinden", json={"url": paperless_server}).get_json()      # ohne Token
    assert r["tags"] is None and "anmelden" in r["hinweis"]
    r = client.post("/api/paperless/verbinden", json={"url": "http://127.0.0.1:9", "token": TOKEN})
    assert r.status_code == 400 and "antwortet kein Paperless" in r.get_json()["error"]


def test_token_bleibt_geheim(client, eingerichtet):
    e = client.get("/api/einstellungen").get_json()
    assert e["paperless_token"] == "" and e["paperless_token_gesetzt"] and e["paperless_url"].endswith("/api/")
    assert client.get("/api/absender").get_json()["paperless_belege"]
    client.put("/api/einstellungen", json={"paperless_installiert": False})                    # ohne Haken kein Knopf
    assert not client.get("/api/absender").get_json()["paperless_belege"]
    client.put("/api/einstellungen", json={"paperless_token": ""})                             # leer = behalten
    assert client.get("/api/einstellungen").get_json()["paperless_token_gesetzt"]
    import db
    assert "paperless_token" in db.GEHEIM                                                       # nicht in Sicherungen


def test_abholen_uebernimmt_dokumente_mit_tag(client, eingerichtet):
    st = client.post("/api/paperless/abholen").get_json()
    assert not st["laeuft"] and st["abbruch"] is None and st["neu"] == 2 and st["gesamt"] == 2 and not st["fehler"]
    neu = {a["paperless_id"]: a for a in client.get("/api/ausgaben").get_json() if a["paperless_id"]}
    assert set(neu) == {11, 12}                                                                 # „Privat“-Tag nicht
    kabel, park = neu[11], neu[12]
    assert kabel["status"] == "neu" and kabel["lieferant"] == "Musterhaus Technik" and kabel["betrag"] == 39.80
    assert kabel["belegdatum"] == "2026-03-04" and kabel["beleg_typ"] == "pdf"
    assert park["betrag"] == 12.50 and park["lieferant"] == "Parkhaus Beleg"                    # Betrag aus Paperless-Texterkennung
    assert any("Texterkennung von Paperless" in h for h in park["erkannt"]["hinweise"])
    assert client.get(f"/api/ausgaben/{kabel['id']}/beleg").data[:5] == b"%PDF-"                 # Kopie liegt in der App
    # zweites Abholen: nichts Neues
    st = client.post("/api/paperless/abholen").get_json()
    assert st["neu"] == 0 and st["vorhanden"] == 2 and st["gesamt"] == 0


def test_von_hand_hochgeladener_beleg_wird_verknuepft(client, eingerichtet):
    import io
    client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(DOKUMENTE[11]["daten"]), "kabel.pdf")]},
                content_type="multipart/form-data")
    st = client.post("/api/paperless/abholen").get_json()
    assert st["neu"] == 1 and st["doppelt"] == 1
    assert sorted(a["paperless_id"] for a in client.get("/api/ausgaben").get_json()) == [11, 12]


def test_abholen_ohne_einrichtung_und_mit_falschem_token(client, paperless_server, monkeypatch):
    import finanzen
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    st = client.post("/api/paperless/abholen").get_json()
    assert "nicht eingerichtet" in st["abbruch"]
    client.put("/api/einstellungen", json={"paperless_url": paperless_server, "paperless_token": "falsch", "paperless_tag": 7})
    st = client.post("/api/paperless/abholen").get_json()
    assert "Token" in st["abbruch"] and not st["laeuft"]
    assert client.post("/api/paperless/abholen").get_json()["abbruch"]                         # Sperre wieder frei


def _supervisor_mit(monkeypatch, port, state="started"):
    """Home Assistant nachbilden: ein installiertes Paperless-Add-on, dessen Container-Port auf den Testserver zeigt."""
    import paperless
    monkeypatch.setenv("SUPERVISOR_TOKEN", "sv")
    antworten = {"/info": {"addons": [{"slug": "dbcd1234_samba", "name": "Samba share"},
                                        {"slug": "ca5234a0_paperless-ngx", "name": "Paperless-ngx", "state": state}]},
                 "/addons/ca5234a0_paperless-ngx/info": {"hostname": "127.0.0.1", "network": {f"{port}/tcp": None},
                                                         "ingress_port": 8099, "state": state}}
    monkeypatch.setattr(paperless, "_supervisor", lambda pfad: antworten.get(pfad))
    monkeypatch.setattr(paperless, "KANDIDATEN", ())


def test_findet_addon_und_meldet_mit_benutzer_an(client, paperless_server, monkeypatch):
    _supervisor_mit(monkeypatch, paperless_server.rsplit(":", 1)[1])
    r = client.post("/api/paperless/verbinden", json={"benutzer": "max", "passwort": "pw"}).get_json()
    assert r["url"] == paperless_server and "Paperless-ngx" in r["gefunden"] and r["token_gespeichert"]
    assert [t["name"] for t in r["tags"]] == ["Ausgaben DJ", "Privat"]
    r = client.post("/api/paperless/verbinden", json={"benutzer": "max", "passwort": "falsch"})   # Adresse jetzt gemerkt
    assert r.status_code == 400 and "Passwort" in r.get_json()["error"]
    e = client.get("/api/einstellungen").get_json()                                          # Adresse und Token gemerkt,
    assert e["paperless_url"] == paperless_server and e["paperless_token_gesetzt"]           # Passwort nicht
    import db
    assert "pw" not in json.dumps(db.get_settings())
    client.put("/api/einstellungen", json={"paperless_tag": "7", "paperless_tag_name": "Ausgaben DJ"})
    import finanzen
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    assert client.post("/api/paperless/abholen").get_json()["neu"] == 2


def test_addon_laeuft_nicht(client, monkeypatch):
    _supervisor_mit(monkeypatch, 9, state="stopped")
    r = client.post("/api/paperless/verbinden", json={"benutzer": "max", "passwort": "pw"})
    assert r.status_code == 400 and "läuft aber nicht" in r.get_json()["error"]


def test_ohne_home_assistant_klare_meldung(client, monkeypatch):
    import paperless
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setattr(paperless, "KANDIDATEN", ())
    r = client.post("/api/paperless/verbinden", json={})
    assert r.status_code == 400 and "nicht gefunden" in r.get_json()["error"]


class IngressSperre(BaseHTTPRequestHandler):
    """Wie der Ingress-Eingang vieler Add-ons: nur Home Assistant darf rein, alle anderen bekommen 403 als HTML."""
    def log_message(self, *a):
        pass

    def _sperre(self):
        self.send_response(403)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h1>403 Forbidden</h1>nginx</body></html>")

    do_GET = do_POST = _sperre


def test_ingress_eingang_wird_uebersprungen(client, paperless_server, monkeypatch):
    """403 vom Ingress-Eingang zählt nicht als Paperless; eine früher falsch gespeicherte Adresse blockiert nicht."""
    import paperless
    sperre = ThreadingHTTPServer(("127.0.0.1", 0), IngressSperre)
    threading.Thread(target=sperre.serve_forever, daemon=True).start()
    try:
        gesperrt = f"http://127.0.0.1:{sperre.server_address[1]}"
        assert not paperless.erreichbar(gesperrt) and paperless.erreichbar(paperless_server)
        monkeypatch.setenv("SUPERVISOR_TOKEN", "sv")
        antworten = {"/info": {"addons": [{"slug": "ca5234a0_paperless-ngx", "name": "Paperless-ngx", "state": "started"}]},
                     "/addons/ca5234a0_paperless-ngx/info": {   # Ingress-Port zuerst im „network“, echter Port danach
                         "hostname": "127.0.0.1", "state": "started",
                         "network": {f"{sperre.server_address[1]}/tcp": None, f"{paperless_server.rsplit(':', 1)[1]}/tcp": None}}}
        monkeypatch.setattr(paperless, "_supervisor", lambda pfad: antworten.get(pfad))
        monkeypatch.setattr(paperless, "KANDIDATEN", ())
        client.put("/api/einstellungen", json={"paperless_url": gesperrt})                  # wie nach Version 1.2.1
        r = client.post("/api/paperless/verbinden", json={"url": gesperrt, "benutzer": "max", "passwort": "pw"}).get_json()
        assert r["url"] == paperless_server and r["tags"]
        assert client.get("/api/einstellungen").get_json()["paperless_url"] == paperless_server
    finally:
        sperre.shutdown()

"""Seit 1.13.1: Sicherheits-Header, Inhaltsprüfung unterschriebener Verträge, Längen in den Stammdaten."""
import io
import re
from pathlib import Path

from conftest import KUNDE

STATIC = Path(__file__).resolve().parents[1] / "rechnungen" / "app" / "static"


def test_header_an_jeder_antwort(client):
    for pfad in ("/", "/api/absender", "/static/app.js", "/api/rechnungen"):
        r = client.get(pfad)
        assert r.headers["X-Content-Type-Options"] == "nosniff", pfad
        assert r.headers["X-Frame-Options"] == "SAMEORIGIN", pfad
        assert r.headers["Referrer-Policy"] == "same-origin", pfad
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'self'" in csp and "object-src 'none'" in csp
    assert "unsafe-eval" not in csp and "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]


def test_oberflaeche_ohne_inline_code():
    """Die CSP verbietet Inline-Skripte und on…=-Attribute – sonst bliebe die Oberfläche leer."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in html and not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert not re.search(r"\son[a-z]+\s*=\s*[\"']", html)
    for js in STATIC.glob("*.js"):
        text = js.read_text(encoding="utf-8")
        assert not re.search(r"\son(error|load|click|mouseover|focus)=[\"']", text), js.name
        assert "eval(" not in text and "new Function(" not in text, js.name


def test_mailvorschau_behaelt_strenge_csp(client):
    r = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(b"From: a@example.de\nContent-Type: text/html\n\n<script>x()</script>Summe 5 EUR"),
                                                                "m.eml")]}, content_type="multipart/form-data")
    assert r.status_code == 200
    aid = client.get("/api/ausgaben").get_json()[0]["id"]
    csp = client.get(f"/api/ausgaben/{aid}/ansicht").headers["Content-Security-Policy"]
    assert csp.startswith("default-src 'none'") and "frame-ancestors 'self'" in csp


def test_unterschrift_inhalt_muss_passen(client):
    a = client.post("/api/angebote", json={"nummer": "012", "datum": "2026-11-20", "gueltig_bis": "2026-12-20", "kunde": KUNDE,
                                           "positionen": [{"beschreibung": "DJ", "lieferdatum": "2027-06-13", "preis": 900}]}).get_json()["id"]
    vid = client.post("/api/vertraege", json={"angebot_id": a}).get_json()["vertrag"]["id"]
    for name, daten in (("vertrag.pdf", b"<html><script>alert(1)</script>"), ("foto.jpg", b"%PDF-1.4"), ("x.png", b"GIF89a"),
                        ("y.heic", b"\0\0\0\x18ftypmp42")):
        r = client.post(f"/api/vertraege/{vid}/unterschrieben", data={"weg": "datei", "datei": (io.BytesIO(daten), name)},
                        content_type="multipart/form-data")
        assert r.status_code == 400, name
    for name, daten in (("foto.jpg", b"\xff\xd8\xff\xe0JFIF"),):
        r = client.post(f"/api/vertraege/{vid}/unterschrieben", data={"weg": "datei", "datei": (io.BytesIO(daten), name)},
                        content_type="multipart/form-data")
        assert r.status_code == 200


def test_stammdaten_laenge_begrenzt(client):
    r = client.post("/api/kunden", json={"name": "A" * 100_000, "ort": "B" * 1000})
    k = next(x for x in client.get("/api/kunden").get_json() if x["id"] == r.get_json()["id"])
    assert len(k["name"]) == 300 and len(k["ort"]) == 300
    r = client.post("/api/textbausteine", json={"titel": "T" * 1000, "text": "x" * 20_000})
    t = next(x for x in client.get("/api/textbausteine").get_json() if x["id"] == r.get_json()["id"])
    assert len(t["titel"]) == 200 and len(t["text"]) == 5000

"""Seit 1.16: Handbuch (README) in der App – Kopie aktuell, Bilder vorhanden, Darstellung."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KOPIE = ROOT / "rechnungen" / "app" / "handbuch"


def test_kopie_passt_zur_readme():
    """Schlägt fehl, wenn die README geändert wurde: dann `python docs/handbuch.py` ausführen."""
    assert (KOPIE / "README.md").read_text(encoding="utf-8") == (ROOT / "README.md").read_text(encoding="utf-8"), \
        "Handbuch veraltet – bitte `python docs/handbuch.py` ausführen"
    for name in set(re.findall(r"docs/bilder/([\w.-]+)\.png", (ROOT / "README.md").read_text(encoding="utf-8"))):
        assert (KOPIE / "bilder" / f"{name}.webp").is_file(), f"Bild {name} fehlt im Handbuch"


def test_handbuch_in_der_app(client):
    h = client.get("/api/handbuch").get_json()["html"]
    assert '<h2 id="funktionen">' in h and '<h2 id="daten--backup">' in h and 'id="sicherungs-passwort"' in h
    assert "Lokale Entwicklung" not in h and "logo.png" not in h and 'id="inhalt"' not in h
    bilder = re.findall(r'src="(api/handbuch/bilder/[^"]+)"', h)
    assert len(bilder) > 20
    r = client.get("/" + bilder[0])
    assert r.status_code == 200 and r.mimetype == "image/webp" and r.data[:4] == b"RIFF"
    for boese in ("../README.md", "..%2Fhandbuch.py", "x.png", "%2e%2e%2fmain.py"):
        assert client.get(f"/api/handbuch/bilder/{boese}").status_code == 404

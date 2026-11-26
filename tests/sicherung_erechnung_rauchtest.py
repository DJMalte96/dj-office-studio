"""Rauchtest seit 1.15 gegen die laufende, gepackte App: E-Rechnung (ZUGFeRD) und verschlüsselte Sicherung.

Prüft, dass factur-x (Schema, XMP-Vorlagen) und cryptography im Paket stecken und funktionieren.
Aufruf: python tests/sicherung_erechnung_rauchtest.py http://127.0.0.1:8765
"""
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rechnungen" / "app"))
import erechnung  # noqa: E402
import verschluesselung  # noqa: E402

URL = sys.argv[1].rstrip("/") + "/"
PW = "Rauchtest-Passwort-2026"


def anfrage(pfad, daten=None, methode=None):
    req = urllib.request.Request(URL + pfad, data=json.dumps(daten).encode() if daten is not None else None,
                                 method=methode or ("POST" if daten is not None else "GET"),
                                 headers={"X-DJOS": "1", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        inhalt = r.read()
        return json.loads(inhalt) if r.headers.get("Content-Type", "").startswith("application/json") else inhalt


anfrage("api/einstellungen", {"steuernummer": "12/345/67890", "schon_verschickt": []}, "PUT")
r = anfrage("api/rechnungen", {"nummer": "901", "datum": "2026-01-02", "erechnung": True, "zahlungsbedingung": "8 Tage",
                               "kunde": {"name": "Sportverein Rauchtest e. V.", "strasse": "Sportplatz 1", "plz": "12345", "ort": "Teststadt"},
                               "positionen": [{"beschreibung": "DJ", "lieferdatum": "2026-01-02", "preis": 700}]})
pdf = anfrage(f"api/rechnungen/{r['id']}/pdf")
xml = dict(erechnung.pdf_anhaenge(pdf)).get("factur-x.xml")
assert xml, "E-Rechnung: kein factur-x.xml im PDF (factur-x im Paket?)"
assert erechnung.lesen(xml)["brutto"] == 700
print("E-Rechnung ok:", len(xml), "Byte XML")

anfrage("api/sicherung/passwort", {"neu": PW})
bereit = anfrage("api/sicherung/vorbereiten", {"passwort": PW})
djos = anfrage(bereit["url"])
assert verschluesselung.ist_verschluesselt(djos), "Sicherung nicht verschlüsselt"
out = io.BytesIO()
verschluesselung.entschluesseln(io.BytesIO(djos), out, PW)
assert "rechnungen.db" in zipfile.ZipFile(io.BytesIO(out.getvalue())).namelist()
print("Verschlüsselte Sicherung ok:", len(djos), "Byte")

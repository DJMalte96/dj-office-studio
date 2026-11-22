"""Rauchtest gegen die gebaute App bzw. das Image (nur Standardbibliothek): Outlook-Mail und HEIC-Vorschau.

    python tests/dateien_rauchtest.py http://127.0.0.1:8765
"""
import json
import sys
import urllib.request
import uuid
from pathlib import Path

basis = sys.argv[1].rstrip("/")
DATEIEN = Path(__file__).resolve().parent / "beispiele" / "dateien"


def hochladen(name):
    grenze = uuid.uuid4().hex
    roh = (f'--{grenze}\r\nContent-Disposition: form-data; name="dateien"; filename="{name}"\r\n'
           "Content-Type: application/octet-stream\r\n\r\n").encode() + (DATEIEN / name).read_bytes() + f"\r\n--{grenze}--\r\n".encode()
    anfrage = urllib.request.Request(f"{basis}/api/ausgaben/belege", roh,
                                     {"Content-Type": f"multipart/form-data; boundary={grenze}"})
    return json.load(urllib.request.urlopen(anfrage, timeout=120))["neu"][0]


def ansicht(a):
    r = urllib.request.urlopen(f"{basis}/api/ausgaben/{a['id']}/ansicht", timeout=120)
    return r.headers.get_content_type(), r.read()


a = hochladen("kauf.msg")
assert (a["beleg_typ"], a["betrag"]) == ("msg", 119), a
typ, seite = ansicht(a)
assert b"MSG-1" in seite and b"Kauf Kabel" in seite, seite[:300]
typ, bild = ansicht(hochladen("foto.heic"))
assert typ == "image/jpeg" and bild[:3] == b"\xff\xd8\xff", typ
print("Outlook und HEIC ok")

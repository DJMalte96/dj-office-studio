"""Rauchtest gegen die gebaute App bzw. das Image (nur Standardbibliothek): E-Rechnung hochladen und Lesefassung prüfen.

    python tests/erechnung_rauchtest.py http://127.0.0.1:8765
"""
import json
import sys
import urllib.request
import uuid

from erechnung_muster import ubl

basis = sys.argv[1].rstrip("/")
grenze = uuid.uuid4().hex
daten = (f'--{grenze}\r\nContent-Disposition: form-data; name="dateien"; filename="rechnung.xml"\r\n'
         f"Content-Type: application/xml\r\n\r\n").encode() + ubl(nummer="RAUCH-1") + f"\r\n--{grenze}--\r\n".encode()
anfrage = urllib.request.Request(f"{basis}/api/ausgaben/belege", daten, {"Content-Type": f"multipart/form-data; boundary={grenze}", "X-DJOS": "1"})
antwort = json.load(urllib.request.urlopen(anfrage, timeout=60))
assert len(antwort["neu"]) == 1, antwort
a = antwort["neu"][0]
assert (a["beleg_typ"], a["betrag"], a["lieferant"]) == ("xml", 119, "Musikhaus Probe GmbH"), a
seite = urllib.request.urlopen(f"{basis}/api/ausgaben/{a['id']}/ansicht", timeout=60).read().decode()
assert "Lesefassung" in seite and "RAUCH-1" in seite, seite[:300]
print("E-Rechnung ok")

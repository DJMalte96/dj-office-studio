"""Rauchtest gegen die gebaute App bzw. das Image (nur Standardbibliothek): präparierte PDFs hochladen –
die App muss währenddessen antworten und danach noch richtig lesen.

    python tests/pdf_rauchtest.py http://127.0.0.1:8765
"""
import json
import sys
import threading
import time
import urllib.request
import uuid

import pdf_muster

basis = sys.argv[1].rstrip("/")


def hochladen(name, daten):
    grenze = uuid.uuid4().hex
    roh = (f'--{grenze}\r\nContent-Disposition: form-data; name="dateien"; filename="{name}"\r\n'
           "Content-Type: application/pdf\r\n\r\n").encode() + daten + f"\r\n--{grenze}--\r\n".encode()
    anfrage = urllib.request.Request(f"{basis}/api/ausgaben/belege", roh,
                                     {"Content-Type": f"multipart/form-data; boundary={grenze}"})
    return json.load(urllib.request.urlopen(anfrage, timeout=120))["neu"][0]


for name, bau, abgebrochen in (("flate.pdf", pdf_muster.flate_bombe, True), ("doppelt.pdf", pdf_muster.doppelt_gepackt, True),
                               ("seitenbaum.pdf", pdf_muster.seitenbaum, True), ("schleife.pdf", pdf_muster.xref_schleife, False),
                               ("ziffern.pdf", lambda: pdf_muster.mit_text(b"1" * 200_000), False)):
    daten, ergebnis = bau(), {}

    def lauf():
        try:
            ergebnis["beleg"] = hochladen(name, daten)
        except Exception as e:
            ergebnis["fehler"] = repr(e)

    t, anfang, langsamste = threading.Thread(target=lauf, daemon=True), time.time(), 0
    t.start()
    while t.is_alive():
        a = time.time()
        urllib.request.urlopen(f"{basis}/api/absender", timeout=10).read()
        langsamste = max(langsamste, time.time() - a)
        assert time.time() - anfang < 90, f"{name}: Hochladen hängt"
        time.sleep(0.1)
    assert "beleg" in ergebnis, f"{name}: {ergebnis}"
    hinweise = " ".join(ergebnis["beleg"]["erkannt"]["hinweise"])
    assert not abgebrochen or "Sicherheitsgr" in hinweise, f"{name}: {hinweise!r}"
    assert langsamste < 5, f"{name}: App antwortete erst nach {langsamste:.1f} s"
    print(f"{name}: {time.time() - anfang:.1f} s, App antwortete nach hoechstens {langsamste:.2f} s")

a = hochladen("gut.pdf", pdf_muster.mit_text(b"Musterladen Probe Gesamtbetrag 47,11 EUR"))
assert a["betrag"] == 47.11, a
print("PDF-Schutz ok")

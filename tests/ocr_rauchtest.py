"""Rauchtest der Texterkennung gegen eine laufende App (Docker-Image bzw. gepackte Desktop-App).

    python tests/ocr_rauchtest.py http://127.0.0.1:8765
"""
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

SCANS = Path(__file__).parent / "beispiele" / "scans"
SOLL = {"bon_quer.jpg": (42.46, "2026-03-14"), "bon_kopfueber.jpg": (42.46, "2026-03-14"),
        "bon_ohne_euro.jpg": (11.40, "2026-09-11"), "rechnung_scan.pdf": (788.48, "2019-10-07")}


def anfrage(url, daten=None, typ=None):
    req = urllib.request.Request(url, data=daten, headers={"Content-Type": typ} if typ else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main(basis):
    for _ in range(90):
        try:
            anfrage(f"{basis}/api/absender")
            break
        except OSError:
            time.sleep(1)
    grenze = uuid.uuid4().hex
    teile = [f'--{grenze}\r\nContent-Disposition: form-data; name="dateien"; filename="{n}"\r\n'
             "Content-Type: application/octet-stream\r\n\r\n".encode() + (SCANS / n).read_bytes() + b"\r\n" for n in SOLL]
    r = anfrage(f"{basis}/api/ausgaben/belege", b"".join(teile) + f"--{grenze}--\r\n".encode(),
                f"multipart/form-data; boundary={grenze}")
    ids = {a["id"] for a in r["neu"]}
    assert len(ids) == len(SOLL), r
    beginn = time.time()
    while time.time() - beginn < 360:
        belege = [a for a in anfrage(f"{basis}/api/ausgaben") if a["id"] in ids]
        if not any(a["ocr"] in ("wartet", "laeuft") for a in belege):
            break
        time.sleep(2)
    falsch = 0
    for a in belege:
        ok = (a["betrag"], a["belegdatum"]) == SOLL[a["beleg_name"]] and a["ocr"] == "fertig"
        falsch += not ok
        print("OK    " if ok else "FALSCH", a["beleg_name"], a["ocr"], a["betrag"], a["belegdatum"], "" if ok else a["erkannt"]["hinweise"])
    print(f"Texterkennung: {len(belege) - falsch} von {len(SOLL)} richtig in {time.time() - beginn:.0f} s")
    return 1 if falsch else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1].rstrip("/")))

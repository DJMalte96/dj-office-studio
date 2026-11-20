"""Finanzen – Belege-Ordner: Dateien werden automatisch eingelesen und danach verschoben."""
import os
import time
from pathlib import Path

import pytest

MAILS = Path(__file__).parent / "beispiele" / "mails"


@pytest.fixture()
def ordner(client, tmp_path, monkeypatch):
    import finanzen
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    finanzen._ordner_stand.update(neu=0, doppelt=0, fehler=[], problem=None)
    o = tmp_path / "eingang"
    client.put("/api/einstellungen", json={"belege_ordner": str(o)})
    return o


def einlesen(client):
    return client.post("/api/belege-ordner/einlesen").get_json()


def test_ordner_wird_angelegt_und_eingelesen(client, ordner):
    st = einlesen(client)
    assert ordner.is_dir() and st["problem"] is None and st["ordner"] == str(ordner)   # beim ersten Mal angelegt
    (ordner / "beatport.eml").write_bytes((MAILS / "beatport.eml").read_bytes())
    unter = ordner / "Scans" / "2026"
    unter.mkdir(parents=True)
    (unter / "apple.eml").write_bytes((MAILS / "apple.eml").read_bytes())
    (ordner / "notizen.txt").write_text("kein Beleg")                                    # wird ignoriert
    (ordner / ".DS_Store").write_bytes(b"x")
    st = einlesen(client)
    assert st["neu"] == 2 and not st["fehler"]
    neu = client.get("/api/ausgaben").get_json()
    assert {a["lieferant"] for a in neu} == {"Beatport", "Apple"} and all(a["status"] == "neu" for a in neu)
    assert (ordner / "übernommen" / "beatport.eml").exists() and (ordner / "übernommen" / "Scans" / "2026" / "apple.eml").exists()
    assert not (ordner / "Scans").exists()                                               # leerer Unterordner aufgeräumt
    assert (ordner / "notizen.txt").exists()
    # dieselbe Mail noch einmal → als doppelt erkannt, trotzdem verschoben, nichts überschrieben
    (ordner / "beatport.eml").write_bytes((MAILS / "beatport.eml").read_bytes())
    st = einlesen(client)
    assert st["doppelt"] == 1 and len(client.get("/api/ausgaben").get_json()) == 2
    assert (ordner / "übernommen" / "beatport (2).eml").exists() and not (ordner / "beatport.eml").exists()


def test_apple_mail_export_und_unlesbares(client, ordner):
    from test_belege import _mbox
    export = ordner / "Musikkäufe.mbox"
    export.mkdir(parents=True)
    (export / "mbox").write_bytes(_mbox((MAILS / "qobuz.eml").read_bytes(), (MAILS / "beatport.eml").read_bytes()))
    (export / "table_of_contents").write_bytes(b"\x00\x01")
    (ordner / "kaputt.msg").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 kein echtes Outlook")
    st = einlesen(client)
    assert st["neu"] >= 2
    assert (ordner / "übernommen" / "Musikkäufe.mbox" / "mbox").exists()
    namen = {a["lieferant"] for a in client.get("/api/ausgaben").get_json()}
    assert {"Qobuz", "Beatport"} <= namen


def test_frische_dateien_warten(client, ordner):
    import finanzen
    ordner.mkdir()
    (ordner / "beatport.eml").write_bytes((MAILS / "beatport.eml").read_bytes())   # gerade erst geschrieben
    finanzen.ordner_einlesen(ruhe=60)
    assert (ordner / "beatport.eml").exists() and not client.get("/api/ausgaben").get_json()
    alt = time.time() - 120
    os.utime(ordner / "beatport.eml", (alt, alt))
    finanzen.ordner_einlesen(ruhe=60)
    assert not (ordner / "beatport.eml").exists() and len(client.get("/api/ausgaben").get_json()) == 1


def test_ordner_fehlt_und_ausgeschaltet(client, tmp_path, monkeypatch):
    import finanzen
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    client.put("/api/einstellungen", json={"belege_ordner": str(tmp_path / "gibt" / "es" / "nicht")})
    assert "nicht gefunden" in einlesen(client)["problem"]
    client.put("/api/einstellungen", json={"belege_ordner": ""})
    st = einlesen(client)
    assert st["ordner"] == "" and st["problem"] is None


def test_paperless_ablage_nur_lesen(client, tmp_path, monkeypatch):
    """Ordner „Ausgaben“ aus der Ablage von Paperless: finden, alle Jahre per *, Dateien bleiben liegen."""
    import finanzen
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    finanzen._ordner_stand.update(neu=0, doppelt=0, fehler=[], problem=None)
    originals = tmp_path / "share" / "paperless" / "media" / "documents" / "originals" / "DJ"
    for jahr, mail in (("2025", "qobuz.eml"), ("2026", "beatport.eml")):
        (originals / jahr / "Ausgaben").mkdir(parents=True)
        (originals / jahr / "Ausgaben" / f"{jahr} {mail}").write_bytes((MAILS / mail).read_bytes())
    (originals / "2026" / "Einnahmen").mkdir()
    (originals / "2026" / "Einnahmen" / "Rechnung 037.eml").write_bytes((MAILS / "apple.eml").read_bytes())   # darf nicht kommen
    (tmp_path / "share" / "paperless" / "media" / "documents" / "thumbnails").mkdir()

    r = client.post("/api/belege-ordner/suchen", json={"wurzeln": [str(tmp_path / "share")]}).get_json()
    assert r["ordner"] == str(originals / "*" / "Ausgaben") and r["anzahl"] == 2
    client.put("/api/einstellungen", json={"belege_ordner": r["ordner"], "belege_ordner_verschieben": False})
    st = einlesen(client)
    assert st["neu"] == 2 and st["problem"] is None
    assert {a["lieferant"] for a in client.get("/api/ausgaben").get_json()} == {"Qobuz", "Beatport"}
    assert (originals / "2026" / "Ausgaben" / "2026 beatport.eml").exists()                  # nichts verschoben
    assert not any(p.name == "übernommen" for p in tmp_path.rglob("*"))
    # zweiter Durchlauf: nichts Neues, auch nicht als „doppelt“ gezählt (schon gesehen)
    assert einlesen(client)["doppelt"] == 0
    (originals / "2026" / "Ausgaben" / "2026 apple.eml").write_bytes((MAILS / "apple.eml").read_bytes())
    os.utime(originals / "2026" / "Ausgaben" / "2026 apple.eml", (time.time() - 60, time.time() - 60))
    assert einlesen(client)["neu"] == 3


def test_eigene_ablage_der_app_ist_gesperrt(client, tmp_path, monkeypatch):
    import db
    import finanzen
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    client.put("/api/einstellungen", json={"belege_ordner": os.path.join(db.DATA_DIR, "belege")})
    assert "Ablage der App" in einlesen(client)["problem"]
    client.put("/api/einstellungen", json={"belege_ordner": db.DATA_DIR})
    assert "Ablage der App" in einlesen(client)["problem"]


def test_suchen_ohne_treffer(client, tmp_path):
    r = client.post("/api/belege-ordner/suchen", json={"wurzeln": [str(tmp_path)]})
    assert r.status_code == 400 and "Kein Ordner" in r.get_json()["error"]

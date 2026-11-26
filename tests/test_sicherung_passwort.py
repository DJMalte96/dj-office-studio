"""Seit 1.15: Sicherungs-Passwort, verschlüsselte Sicherungen herunterladen/einspielen, Tageskopie, Desktop-Sicherung."""
import io
import os
import sys
import zipfile
from datetime import date
from pathlib import Path

from conftest import neue_rechnung

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
PW = "Plattenkiste-1987!"


def passwort(client, neu=PW, alt=None):
    return client.post("/api/sicherung/passwort", json={"neu": neu, **({"alt": alt} if alt else {})})


def herunterladen(client, pw=PW):
    r = client.post("/api/sicherung/vorbereiten", json={"passwort": pw})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    datei = client.get("/" + d["url"])
    assert datei.status_code == 200 and d["name"].endswith(".djos")
    return datei.data


def einspielen(client, daten, pw=None, name="s.djos"):
    return client.post("/api/backup", data={"datei": (io.BytesIO(daten), name), **({"passwort": pw} if pw else {})},
                       content_type="multipart/form-data")


def test_ohne_passwort_wie_bisher(client):
    assert client.get("/api/sicherung").get_json()["gesetzt"] is False
    assert client.get("/api/backup").data[:2] == b"PK"
    assert client.post("/api/sicherung/vorbereiten", json={"passwort": PW}).status_code == 400


def test_passwort_festlegen(client):
    assert passwort(client, "kurz").status_code == 400
    st = passwort(client).get_json()
    assert st["gesetzt"] and st["seit"] == date.today().isoformat()
    import db
    einst = db.get_settings()
    assert PW not in str(einst)                       # das Passwort selbst wird nicht gespeichert
    assert client.get("/api/backup").status_code == 409   # unverschlüsselt geht nicht mehr
    assert "_sicherung_priv" not in client.get("/api/einstellungen").get_json()


def test_herunterladen_und_einspielen(client):
    neue_rechnung(client, nummer="037")
    passwort(client)
    assert client.post("/api/sicherung/vorbereiten", json={"passwort": "falsch-falsch"}).get_json()["passwort"] is True
    r = client.post("/api/sicherung/vorbereiten", json={"passwort": PW}).get_json()
    datei = client.get("/" + r["url"])
    djos = datei.data
    datei.close()
    assert djos.startswith(b"DJOS-SICHERUNG") and b"Anna Muster" not in djos
    assert client.get("/" + r["url"]).status_code == 404            # nur einmal abholbar
    import db
    assert db.get_settings()["_letzte_sicherung"][:10] == date.today().isoformat()
    assert not os.listdir(os.path.join(db.DATA_DIR, "sicherungen", "bereit"))   # nichts liegen geblieben

    neue_rechnung(client, nummer="038")
    antwort = einspielen(client, djos)
    assert antwort.status_code == 400 and antwort.get_json()["passwort"] is True
    assert einspielen(client, djos, "falsch-falsch").get_json()["passwort"] is True
    antwort = einspielen(client, djos, PW)
    assert antwort.status_code == 200, antwort.get_json()
    assert [r["nummer"] for r in client.get("/api/rechnungen").get_json()] == ["037"]
    assert client.get("/api/sicherung").get_json()["gesetzt"]        # Schlüssel kommt mit


def test_auf_neuem_rechner_nur_mit_passwort(client, app_modul):
    """Frische Installation ohne Schlüssel: die Sicherung öffnet sich allein mit dem Passwort."""
    neue_rechnung(client, nummer="037")
    passwort(client)
    djos = herunterladen(client)
    import db
    with db.connect() as con:
        con.execute("DELETE FROM einstellungen WHERE schluessel LIKE '_sicherung%'")
        con.execute("DELETE FROM rechnungen")
    assert einspielen(client, djos, PW).status_code == 200
    assert len(client.get("/api/rechnungen").get_json()) == 1


def test_passwort_aendern(client):
    passwort(client)
    alt = herunterladen(client)
    assert passwort(client, "Neues-Passwort-2027", alt="falsch-falsch").status_code == 400
    assert passwort(client, "Neues-Passwort-2027", alt=PW).status_code == 200
    neu = herunterladen(client, "Neues-Passwort-2027")
    assert client.post("/api/sicherung/vorbereiten", json={"passwort": PW}).status_code == 400
    assert einspielen(client, neu, PW).status_code == 400
    assert einspielen(client, alt, PW).status_code == 200             # ältere Sicherung: bisheriges Passwort


def test_kaputte_verschluesselte_datei(client):
    passwort(client)
    djos = herunterladen(client)
    r = einspielen(client, djos[:-50], PW)
    assert r.status_code == 400 and "nicht öffnen" in r.get_json()["error"]


def test_tageskopie_in_ordner(client, tmp_path):
    import db
    import sicherung
    ordner = tmp_path / "Cloud"
    assert sicherung.tageskopie() is None                             # kein Ordner eingestellt
    client.put("/api/einstellungen", json={"sicherung_kopie_ordner": str(ordner)})
    assert sicherung.tageskopie() is None and "Passwort" in db.get_settings()["_kopie_fehler"]
    passwort(client)
    assert sicherung.tageskopie() is None and "nicht erreichbar" in db.get_settings()["_kopie_fehler"]
    ordner.mkdir()
    for tag in range(1, 10):                                          # 9 ältere Kopien + eine fremde Datei
        (ordner / f"DJ-Office-Studio-Sicherung_2020-01-{tag:02d}.djos").write_bytes(b"alt")
    (ordner / "Urlaubsfoto.jpg").write_bytes(b"bleibt")
    name = sicherung.tageskopie()
    assert name == f"DJ-Office-Studio-Sicherung_{date.today():%Y-%m-%d}.djos"
    dateien = sorted(p.name for p in ordner.iterdir())
    assert len(dateien) == 8 and "Urlaubsfoto.jpg" in dateien and dateien[-2] == name
    st = client.get("/api/sicherung").get_json()
    assert st["kopie_am"][:10] == date.today().isoformat() and not st["kopie_fehler"]
    # Inhalt: vollständige Sicherung (ZIP mit Datenbank), nur mit Passwort
    import verschluesselung
    out = io.BytesIO()
    with open(ordner / name, "rb") as f:
        verschluesselung.entschluesseln(f, out, PW)
    assert "rechnungen.db" in zipfile.ZipFile(io.BytesIO(out.getvalue())).namelist()
    assert client.post("/api/sicherung/kopie").get_json()["datei"] == name   # „Jetzt kopieren“


def test_desktop_sicherung_verschluesselt(app_modul, tmp_path, monkeypatch, client):
    import db
    import start
    import verschluesselung
    monkeypatch.setattr(start, "DATEN", Path(db.DATA_DIR))   # wie am Desktop: Sicherungen im Datenordner
    passwort(client)
    start.automatische_sicherung(db)
    ordner = Path(db.DATA_DIR) / "Sicherungen"
    dateien = [p.name for p in ordner.iterdir()]
    assert dateien == [f"rechnungen_{date.today().isoformat()}.db.djos"]
    out = io.BytesIO()
    with open(ordner / dateien[0], "rb") as f:
        verschluesselung.entschluesseln(f, out, PW)
    assert out.getvalue()[:16] == b"SQLite format 3\x00"
    monkeypatch.setattr(app_modul, "DESKTOP", True)
    assert client.get("/api/einstellungen").status_code == 200
    assert app_modul._letzte_auto_sicherung() == date.today().isoformat()
    # einspielen wie jede andere Sicherung
    r = einspielen(client, (ordner / dateien[0]).read_bytes(), PW, name=dateien[0])
    assert r.status_code == 200, r.get_json()

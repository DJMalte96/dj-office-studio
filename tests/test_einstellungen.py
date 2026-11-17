"""Einstellungen, Übernahme aus Home Assistant, Update-Prüfung (Desktop)."""
import io
import json

import pdf


def test_einstellungen_speichern_und_pruefen(client):
    r = client.put("/api/einstellungen", json={"name": "Moritz", "startnummer": 50, "kleinunternehmer": False})
    assert r.status_code == 200
    e = client.get("/api/einstellungen").get_json()
    assert e["name"] == "Moritz" and e["startnummer"] == 50 and e["kleinunternehmer"] is False
    assert client.get("/api/rechnungen/naechste-nummer").get_json()["nummer"] == "050"
    assert client.put("/api/einstellungen", json={"startnummer": "abc"}).status_code == 400
    assert client.put("/api/einstellungen", json={"mahnfrist_tage": 0}).status_code == 400


def test_uebernahme_aus_home_assistant(app_modul, tmp_path):
    import db
    with db.connect() as con:
        con.execute("DELETE FROM einstellungen")
    (tmp_path / "options.json").write_text(json.dumps({"name": "Aus HA", "iban": "DE99", "startnummer": 12}))
    c = app_modul.app.test_client()
    e = c.get("/api/einstellungen").get_json()
    assert (e["name"], e["iban"], e["startnummer"]) == ("Aus HA", "DE99", 12)
    (tmp_path / "options.json").write_text("{}")   # spätere Änderungen in HA wirken nicht mehr
    assert c.get("/api/einstellungen").get_json()["name"] == "Aus HA"


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_update_pruefung(app_modul, monkeypatch):
    c = app_modul.app.test_client()
    assert c.get("/api/update").get_json() == {"aktiv": False}   # Home Assistant: keine Prüfung

    monkeypatch.setattr(app_modul, "DESKTOP", True)
    monkeypatch.setattr(app_modul, "APP_VERSION", "0.11.1")
    antwort = {"tag_name": "desktop-v0.12.0", "html_url": "https://example.invalid/release"}
    monkeypatch.setattr(app_modul.urllib.request, "urlopen",
                        lambda *a, **k: _Antwort(json.dumps(antwort).encode()))
    u = c.get("/api/update").get_json()
    assert u["verfuegbar"] and u["neueste"] == "0.12.0"

    app_modul._update_cache.update(zeit=0, ergebnis=None)
    def offline(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(app_modul.urllib.request, "urlopen", offline)
    assert c.get("/api/update").get_json()["fehler"] is True


def test_betraege_formatieren():
    assert pdf.fmt_euro(960) == "960,- Euro"
    assert pdf.fmt_euro(1234.5) == "1.234,50 Euro"
    assert pdf.fmt_euro(-960) == "-960,- Euro"


def test_hinweis_beim_ersten_start(client):
    assert client.get("/api/absender").get_json()["hinweis_bestaetigt"] is False
    assert client.post("/api/hinweis").status_code == 204
    assert client.get("/api/absender").get_json()["hinweis_bestaetigt"] is True
    # Neue Textversion → erscheint einmal erneut
    import main
    main.HINWEIS_VERSION += 1
    try:
        assert client.get("/api/absender").get_json()["hinweis_bestaetigt"] is False
    finally:
        main.HINWEIS_VERSION -= 1

"""Seit 1.12: Rundgang nur bei neuer Installation anbieten."""
import sqlite3


def test_neue_installation_bietet_rundgang_an(client):
    assert client.get("/api/absender").get_json()["rundgang_anbieten"] is True
    assert client.post("/api/rundgang").status_code == 204
    assert client.get("/api/absender").get_json()["rundgang_anbieten"] is False


def test_bestehende_installation_nicht(app_modul, tmp_path):
    import db
    # alte Datenbank: Tabellen gibt es schon, der Merker fehlt → nach dem Update kein Angebot
    with db.connect() as con:
        con.execute("DELETE FROM einstellungen WHERE schluessel = '_rundgang_anbieten'")
    db.init()
    c = app_modul.app.test_client()
    assert c.get("/api/absender").get_json()["rundgang_anbieten"] is False


def test_einmal_beantwortet_bleibt_beantwortet(client):
    import db
    client.post("/api/rundgang")
    db.init()                     # Neustart der App
    assert client.get("/api/absender").get_json()["rundgang_anbieten"] is False


def test_ohne_kopf_abgelehnt(app_modul):
    c = app_modul.app.test_client()          # ohne X-DJOS – wie eine fremde Webseite
    assert c.post("/api/rundgang").status_code in (400, 403)

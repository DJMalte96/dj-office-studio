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


def test_datenbank_wartet_bei_sperre(app_modul):
    import db
    with db.connect() as con:
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 30000


def test_lesen_waehrend_langem_schreiben(app_modul):
    """Ein Schreibvorgang hält die Datenbank kurz exklusiv – eine Abfrage wartet, statt mit Fehler 500 abzubrechen."""
    import threading
    import time
    import db
    gesperrt = threading.Event()

    def schreiben():                                      # eigene Verbindung im eigenen Thread
        con = db.connect()
        con.execute("BEGIN EXCLUSIVE")
        gesperrt.set()
        time.sleep(6)                                     # länger als die alten 5 s
        con.commit()
        con.close()

    t = threading.Thread(target=schreiben)
    t.start()
    gesperrt.wait(5)
    c = app_modul.app.test_client()
    t0 = time.time()
    assert c.get("/api/ausgaben").status_code == 200
    assert time.time() - t0 >= 5
    t.join()


def test_ohne_kopf_abgelehnt(app_modul):
    c = app_modul.app.test_client()          # ohne X-DJOS – wie eine fremde Webseite
    assert c.post("/api/rundgang").status_code in (400, 403)

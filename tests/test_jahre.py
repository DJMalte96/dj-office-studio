"""Jahresmenüs: alle Jahre aus dem Bestand, nicht nur die des gewählten Jahres."""
from datetime import date

import pytest

import db
import finanzen

HEUTE = date(2026, 11, 22)


def sql(befehl, *werte):
    with db.connect() as con:
        return con.execute(befehl, werte).lastrowid


def ausgabe(belegdatum, bezahlt_am=None, status="ok"):
    return sql("INSERT INTO ausgaben (status, belegdatum, bezahlt_am, lieferant, kategorie, betrag) VALUES (?, ?, ?, 'Laden', 'sonstiges', 10)",
               status, belegdatum, bezahlt_am)


def test_leer_wie_bisher_vier_jahre(app_modul):
    assert finanzen.jahre(HEUTE) == [2026, 2025, 2024, 2023]


@pytest.mark.parametrize("status", ["ok", "neu"])
def test_alte_ausgabe_lueckenlos_bis_heute(app_modul, status):
    ausgabe("2019-03-10", "2019-03-10", status)
    assert finanzen.jahre(HEUTE) == list(range(2026, 2018, -1))


def test_ausgabe_zaehlt_nach_bezahlt_datum_sonst_belegdatum(app_modul):
    ausgabe("2018-12-30", "2019-01-02")
    assert min(finanzen.jahre(HEUTE)) == 2019
    ausgabe("2017-05-01")
    assert min(finanzen.jahre(HEUTE)) == 2017


def test_rechnung_und_zahlungseingang(app_modul, client):
    from conftest import neue_rechnung
    rid = neue_rechnung(client)
    sql("UPDATE rechnungen SET datum = '2020-12-20' WHERE id = ?", rid)
    assert min(finanzen.jahre(HEUTE)) == 2020
    sql("UPDATE rechnungen SET bezahlt_am = '2028-01-03' WHERE id = ?", rid)
    assert max(finanzen.jahre(HEUTE)) == 2028


def test_fahrten(app_modul):
    sql("INSERT INTO fahrten (datum) VALUES ('2016-06-01')")
    assert min(finanzen.jahre(HEUTE)) == 2016


def test_sonstige_einnahmen(app_modul):
    sql("INSERT INTO einnahmen_sonstige (datum, beschreibung, betrag) VALUES ('2015-06-01', 'Verkauf', 5)")
    assert min(finanzen.jahre(HEUTE)) == 2015


@pytest.mark.parametrize("spalte, wert", [("anschaffung_am", "2014-02-01"), ("start_jahr", 2014), ("abgang_am", "2014-09-01")])
def test_anlagen(app_modul, spalte, wert):
    sql(f"INSERT INTO anlagen (bezeichnung, {spalte}) VALUES ('Boxen', ?)", wert)
    assert min(finanzen.jahre(HEUTE)) == 2014


def test_papierkorb_samt_anlage_zaehlt_nicht(app_modul):
    aid = ausgabe("2012-01-01", "2012-01-01", "papierkorb")
    sql("INSERT INTO anlagen (bezeichnung, anschaffung_am, ausgabe_id) VALUES ('Pult', '2012-01-01', ?)", aid)
    assert finanzen.jahre(HEUTE) == [2026, 2025, 2024, 2023]


def test_ausreisser_einzeln_und_kaputtes_ignoriert(app_modul, client):
    for d in ("1970-01-01", "2062-03-01", "0019-03-01", "irgendwas", ""):
        ausgabe(d)
    assert finanzen.jahre(HEUTE) == [2062, 2026, 2025, 2024, 2023, 1970]


def test_jedes_angebotene_jahr_laesst_sich_oeffnen(app_modul, client):
    for d in ("1000-01-01", "2019-03-10", "9999-12-31"):
        ausgabe(d)
    angebot = client.get("/api/finanzen/jahre").get_json()
    assert {1000, 2019, 9999} <= set(angebot)
    for j in (1000, 2019, 9999):
        for pfad in ("ausgaben", "fahrten", "anlagen", "finanzen/euer", "export"):
            assert client.get(f"/api/{pfad}?jahr={j}").status_code == 200, (pfad, j)
    assert [a["jahr"] for a in client.get("/api/ausgaben?jahr=2019").get_json()] == ["2019"]

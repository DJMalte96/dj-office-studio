"""Der eigene Name ist nie ein vorgeschlagener Lieferant."""
import pytest

import belege
import db
import finanzen

ICH = {"name": "Max Beispiel", "strasse": "Musterstraße 1", "plz_ort": "12345 Musterstadt"}


@pytest.mark.parametrize("text", ["Max Beispiel", "MAX BEISPIEL", "Beispiel, Max", "Herrn Max Beispiel", "MaxBeispiel",
                                  "Max Beispiel Veranstaltungstechnik", "Musterstr. 1", "Musterstrasse 1",
                                  "12345 Musterstadt", "Musterstraße 1, 12345 Musterstadt"])
def test_erkennt_sich_selbst(text):
    assert belege.ist_eigen(text, ICH)


@pytest.mark.parametrize("text", ["Musterladen GmbH", "Max Musikhaus", "Beispiel Audio", "Maxi Beispielhaus", "Musterstraße 12",
                                  "Musikhaus Musterstadt", "", None])
def test_laesst_haendler_in_ruhe(text):
    assert not belege.ist_eigen(text, ICH)


def test_umlaute_kontoinhaber_und_namenszusatz():
    assert belege.ist_eigen("JUERGEN MULLER", {"name": "Jürgen Müller"})
    assert belege.ist_eigen("Max Beispiel", {"name": "DJ Maxx", "kontoinhaber": "Max Beispiel"})
    assert belege.ist_eigen("Max Beispiel", {"name": "DJ Maxx – Max Beispiel"})


def test_einteiliger_name_nur_allein():
    assert belege.ist_eigen("maxx", {"name": "Maxx"})
    assert belege.ist_eigen("Herrn Maxx", {"name": "Maxx"})
    assert not belege.ist_eigen("Maxx Musikhaus", {"name": "Maxx"})


def test_ohne_einstellungen_trifft_nichts():
    assert not belege.ist_eigen("Musterladen", {})
    assert not belege.ist_eigene_adresse("", {})


def erkannt(monkeypatch, lieferant, **mehr):
    monkeypatch.setattr(belege, "auswerten", lambda name, daten: {
        "typ": "pdf", "lieferant": lieferant, "belegdatum": "2025-12-11", "betrag": 32.5, "ust_satz": None, "ust_betrag": None,
        "beschreibung": None, "kategorie": None, "message_id": None, "fundstellen": {}, "hinweise": [], **mehr})


def test_pdf_mit_eigenem_namen_oben(app_modul, monkeypatch):
    erkannt(monkeypatch, "Max Beispiel")
    a, _ = finanzen.beleg_aufnehmen("r.pdf", b"%PDF-eins")
    assert a["lieferant"] == "" and a["erkannt"]["lieferant"] is None
    assert finanzen.EIGENER_NAME in a["erkannt"]["hinweise"]


def test_fremder_lieferant_bleibt_ohne_hinweis(app_modul, monkeypatch):
    erkannt(monkeypatch, "Musterladen GmbH")
    a, _ = finanzen.beleg_aufnehmen("r.pdf", b"%PDF-zwei")
    assert a["lieferant"] == "Musterladen GmbH" and finanzen.EIGENER_NAME not in a["erkannt"]["hinweise"]


def mail(von, nr):
    return (f"From: {von}\nDate: Wed, 10 Dec 2025 10:00:00 +0100\nMessage-ID: <{nr}@example.org>\n"
            f"Subject: Fwd: Kauf\n\nGesamt 32,00 EUR\n").encode()


def test_weitergeleitete_mail_mit_eigenem_namen(app_modul):
    a, _ = finanzen.beleg_aufnehmen("k.eml", mail("Max Beispiel <max@example.org>", 1))
    assert a["lieferant"] == "" and a["betrag"] == 32


def test_weitergeleitete_mail_von_eigener_adresse(app_modul):
    db.save_settings(db.get_settings() | {"absender_email": "Post@Example.org"})
    a, _ = finanzen.beleg_aufnehmen("k.eml", mail("Maxl <POST@example.org>", 2))
    assert a["lieferant"] == "" and finanzen.EIGENER_NAME in a["erkannt"]["hinweise"]
    assert "absender_adresse" not in a["erkannt"]


def test_fremde_mail_bleibt(app_modul):
    a, _ = finanzen.beleg_aufnehmen("k.eml", mail("Musterladen <shop@example.org>", 3))
    assert a["lieferant"] == "Musterladen"


@pytest.mark.parametrize("korrespondent, aus_pdf, soll", [
    ("Max Beispiel", "Musterladen", "Musterladen"), ("Musterladen", "Max Beispiel", "Musterladen"),
    ("Max Beispiel", None, ""), (None, "Max Beispiel", ""), (None, None, "Rechnung Dezember")])
def test_paperless(app_modul, monkeypatch, korrespondent, aus_pdf, soll):
    erkannt(monkeypatch, aus_pdf)
    a, _ = finanzen.beleg_aufnehmen("r.pdf", b"%PDF-drei", paperless={
        "id": 7, "korrespondent": korrespondent, "titel": "Rechnung Dezember", "datum": "2025-12-11", "text": ""})
    assert a["lieferant"] == soll


def test_texterkennung_ueberspringt_namen_und_anschrift():
    t = belege.ocr_vorschlaege("Max Beispiel\nMusterstr. 1\nMusterladen GmbH\nSumme 12,00 EUR\n", ICH)
    assert t["lieferant"] == "Musterladen GmbH"


def test_texterkennung_bekommt_die_einstellungen(app_modul, monkeypatch):
    gesehen = []
    monkeypatch.setattr(belege, "ocr_vorschlaege", lambda text, absender=None: gesehen.append(absender) or {})
    finanzen._ocr_uebernehmen(0, "x", "fertig", text="Text")
    assert gesehen[0]["name"] == "Max Beispiel"


def test_vorschlagsliste_ohne_eigenen_namen(app_modul, client):
    with db.connect() as con:
        for n in ("Max Beispiel", "Musterladen"):
            con.execute("INSERT INTO ausgaben (status, lieferant, kategorie) VALUES ('ok', ?, 'sonstiges')", (n,))
    assert client.get("/api/ausgaben/lieferanten").get_json() == ["Musterladen"]

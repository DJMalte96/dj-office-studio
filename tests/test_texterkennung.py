"""Texterkennung für Fotos und Scans: Auswerteregeln, Warteschlange, Schutz der Eingaben und echte Erkennung."""
import io
from pathlib import Path

import pytest

import belege

SCANS = Path(__file__).parent / "beispiele" / "scans"


# ---------- Auswerteregeln ----------

@pytest.mark.parametrize("text, betrag", [
    ("DROGERIE\nBatterien 7,95\nSUMME 11,40\nBAR 20,00\nRÜCKGELD 8,60", 11.40),
    ("SUMME EUR 42,46\nGegeben Bar EUR 50,00", 42.46),
    ("KIOSK\nGegeben EUR 50,00\nRückgeld EUR 31,20", None),                  # nie das Bargeld
    ("Gesamt 662,59 125,89\nTotal EUR inkI. MwSt. 788,48", 788.48),           # „inkI.“ = verlesenes „inkl.“
    ("Zwischensumme 160,00\nSumme MwSt 30,40\nSumme 190,40", 190.40),
    ("Summe Rabatt 20,00\nSumme 139,00", 139.00),
    ("SUMME 42, 46", 42.46),
    ("SUMME\n11,40", 11.40),
    ("Kartenzahlung\nBetrag EUR 129,00", 129.00),
    ("Notiz\nKabel abholen 12.11.2026", None),
])
def test_gesamtbetrag_aus_erkanntem_text(text, betrag):
    assert belege.ocr_vorschlaege(text)["betrag"] == betrag


def test_hoechster_betrag_gilt_als_unsicher():
    assert belege.ocr_vorschlaege("Parkschein\n4,50 €")["unsicher"]
    assert not belege.ocr_vorschlaege("Summe 4,50 €")["unsicher"]


def test_datum_kurz_und_verlesen():
    assert belege.ocr_vorschlaege("11.09.26 18:20")["belegdatum"] == "2026-09-11"
    assert belege.ocr_vorschlaege("Fällig 17.10.19\nDatum 07.10.2019")["belegdatum"] == "2019-10-07"
    assert belege.ocr_vorschlaege("Datum 14.03.2086")["belegdatum"] is None
    assert belege.ocr_vorschlaege("Datum 14.03.1926")["belegdatum"] is None


def test_steuer_nur_wenn_sie_rechnerisch_passt():
    t = belege.ocr_vorschlaege("SUMME 42,46\nMwSt 19% Netto 35,68 Steuer 6,78")
    assert (t["ust_satz"], t["ust_betrag"]) == (19.0, 6.78)
    assert belege.ocr_vorschlaege("Summe 29,49\n19% 21,00 3,99\n7% 4,21 0,29")["ust_satz"] is None


def test_lieferant_ist_nicht_der_eigene_name():
    t = belege.ocr_vorschlaege("Max Beispiel\nMusikhaus Probe GmbH\nSumme 5,00", "Max Beispiel")
    assert t["lieferant"] == "Musikhaus Probe GmbH"


def test_zeilen_aus_textkaesten():
    from texterkennung import zeilen_bilden
    k = lambda x, y: [(x, y), (x + 100, y), (x + 100, y + 20), (x, y + 20)]
    kaesten, texte = [k(400, 102), k(10, 160), k(10, 100)], ["42,46", "Danke", "SUMME EUR"]
    assert zeilen_bilden(kaesten, texte) == ["SUMME EUR 42,46", "Danke"]
    gedreht = [[(1000 - x, 1000 - y) for x, y in kasten] for kasten in kaesten]
    gedreht = [[p[2], p[3], p[0], p[1]] for p in gedreht]
    assert zeilen_bilden(gedreht, texte, kopfueber=True) == ["SUMME EUR 42,46", "Danke"]


# ---------- Warteschlange ----------

TEXT = "BAUMARKT BEISPIEL\nSUMME EUR 42,46\nMwSt 19% Netto 35,68 Steuer 6,78\n14.03.2026"


@pytest.fixture()
def ocr(client, monkeypatch):
    """Erkennung nachgebildet; gibt (durchlauf, setze_verhalten) zurück."""
    import finanzen
    monkeypatch.setattr(finanzen.texterkennung, "lesen", lambda pfad: TEXT)

    def verhalten(funktion):
        monkeypatch.setattr(finanzen.texterkennung, "lesen", funktion)
    return finanzen.texterkennung_durchlauf, verhalten


def foto(client, inhalt=b"1"):
    r = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(b"\xff\xd8\xff\xe0" + inhalt), "IMG_1.jpg")]},
                    content_type="multipart/form-data").get_json()
    return r["neu"][0]


def holen(client, a):
    return client.get(f"/api/ausgaben/{a['id']}").get_json()


def test_foto_wird_im_hintergrund_gelesen(client, ocr):
    a = foto(client)
    assert a["ocr"] == "wartet" and a["betrag"] is None       # Hochladen wartet nicht auf die Erkennung
    assert ocr[0]() == 1
    b = holen(client, a)
    assert (b["ocr"], b["status"], b["betrag"], b["ust_satz"]) == ("fertig", "neu", 42.46, 19.0)
    assert b["belegdatum"] == b["bezahlt_am"] == "2026-03-14" and b["lieferant"] == "BAUMARKT BEISPIEL"
    assert b["erkannt"]["fundstellen"]["betrag"] == "SUMME EUR 42,46"
    assert any("Texterkennung" in h for h in b["erkannt"]["hinweise"])


def test_eingaben_bleiben_erhalten(client, ocr):
    a = foto(client)
    eigen = {"lieferant": "Eigener Laden", "betrag": "40,00", "bezahlt_am": "2026-04-01"}
    assert client.put(f"/api/ausgaben/{a['id']}", json=eigen).status_code == 200
    ocr[0]()
    b = holen(client, a)
    assert (b["lieferant"], b["betrag"], b["bezahlt_am"], b["ust_satz"]) == ("Eigener Laden", 40.0, "2026-04-01", None)
    assert b["belegdatum"] == "2026-03-14"                     # das war noch der Platzhalter


def test_waehrend_des_lesens_uebernommen(client, ocr):
    a = foto(client)

    def lesen(pfad):
        client.put(f"/api/ausgaben/{a['id']}", json={"lieferant": "Ich", "betrag": "9,99", "belegdatum": "2026-01-02",
                                                     "bezahlt_am": "2026-01-02", "uebernehmen": True})
        return TEXT
    ocr[1](lesen)
    ocr[0]()
    b = holen(client, a)
    assert (b["status"], b["lieferant"], b["betrag"], b["belegdatum"]) == ("ok", "Ich", 9.99, "2026-01-02")


def test_waehrend_des_lesens_verworfen(client, ocr):
    a = foto(client)
    ocr[1](lambda pfad: client.delete(f"/api/ausgaben/{a['id']}") and TEXT)
    assert ocr[0]() == 1 and client.get("/api/ausgaben").get_json() == []
    b = client.post(f"/api/papierkorb/{a['id']}/wiederherstellen").get_json()
    assert (b["status"], b["betrag"], b["belegdatum"]) == ("neu", 42.46, "2026-03-14")      # Ergebnis nicht verloren


def test_waehrend_des_lesens_endgueltig_geloescht(client, ocr):
    a = foto(client)

    def lesen(pfad):
        client.delete(f"/api/ausgaben/{a['id']}")
        client.delete(f"/api/papierkorb/{a['id']}")
        return TEXT
    ocr[1](lesen)
    assert ocr[0]() == 1 and client.get(f"/api/ausgaben/{a['id']}").status_code == 404


def test_wartende_erkennung_ueberlebt_den_papierkorb(client, ocr):
    a = foto(client)
    client.delete(f"/api/ausgaben/{a['id']}")
    assert ocr[0]() == 0                                       # im Papierkorb wird nicht gelesen …
    assert client.post(f"/api/papierkorb/{a['id']}/wiederherstellen").get_json()["ocr"] == "wartet"
    assert ocr[0]() == 1 and holen(client, a)["betrag"] == 42.46


def test_gleiche_id_anderer_beleg_wird_nicht_beschrieben(client, ocr):
    import db
    a = foto(client)

    def lesen(pfad):                                           # z. B. Sicherung eingespielt
        with db.connect() as con:
            con.execute("UPDATE ausgaben SET beleg_pruefsumme = 'anders' WHERE id = ?", (a["id"],))
        return TEXT
    ocr[1](lesen)
    ocr[0]()
    assert holen(client, a)["betrag"] is None


def test_fehler_und_erneut_versuchen(client, ocr):
    import texterkennung
    a = foto(client)
    foto(client, b"2")

    def kaputt(pfad):
        raise texterkennung.NichtVerfuegbar("ImportError")
    ocr[1](kaputt)
    assert ocr[0]() == 2
    x = holen(client, a)
    assert x["ocr"] == "nicht_verfuegbar" and "nicht verfügbar" in " ".join(x["erkannt"]["hinweise"])
    assert ocr[0]() == 0                                        # keine Endlosschleife
    ocr[1](lambda pfad: TEXT)
    assert client.post(f"/api/ausgaben/{a['id']}/texterkennung").get_json()["ocr"] == "wartet"
    ocr[0]()
    x = holen(client, a)
    assert x["betrag"] == 42.46 and "nicht verfügbar" not in " ".join(x["erkannt"]["hinweise"])


def test_abgebrochene_erkennung_hoechstens_einmal_wiederholen(client, ocr):
    import db
    a, b = foto(client), foto(client, b"2")
    with db.connect() as con:
        con.execute("UPDATE ausgaben SET ocr = 'laeuft', ocr_versuche = 1 WHERE id = ?", (a["id"],))
        con.execute("UPDATE ausgaben SET ocr = 'laeuft', ocr_versuche = 2 WHERE id = ?", (b["id"],))
    assert ocr[0]() == 1
    assert (holen(client, a)["ocr"], holen(client, b)["ocr"]) == ("fertig", "fehler")


def test_digitale_pdf_und_mail_ohne_texterkennung(client, ocr):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, "Gesamtbetrag 39,80 EUR")
    r = client.post("/api/ausgaben/belege", data={"dateien": [
        (io.BytesIO(bytes(pdf.output())), "digital.pdf"),
        (io.BytesIO((SCANS.parent / "mails" / "qobuz.eml").read_bytes()), "qobuz.eml")]},
        content_type="multipart/form-data").get_json()
    assert [a["ocr"] for a in r["neu"]] == [None, None] and ocr[0]() == 0


def test_datei_ausserhalb_der_ablage_wird_nicht_gelesen(client, ocr):
    import db
    a = foto(client)
    with db.connect() as con:                                  # z. B. manipulierte Sicherung
        con.execute("UPDATE ausgaben SET beleg_datei = '../../../../etc/hosts' WHERE id = ?", (a["id"],))
    ocr[1](lambda pfad: pytest.fail("darf nicht gelesen werden"))
    ocr[0]()
    assert holen(client, a)["ocr"] == "fehler"


def test_update_reiht_alte_ungepruefte_scans_ein(client, ocr):
    """Belege aus 1.4: nachträglich lesen, übernommene nicht anfassen."""
    import db
    a, b = foto(client), foto(client, b"2")
    client.put(f"/api/ausgaben/{b['id']}", json={"lieferant": "X", "betrag": "5", "uebernehmen": True})
    with db.connect() as con:
        con.execute("UPDATE ausgaben SET erkannt_json = '{}'")     # ohne Platzhalter-Vermerk, wie vor 1.5
        con.execute("ALTER TABLE ausgaben DROP COLUMN ocr")
    db.init()
    assert (holen(client, a)["ocr"], holen(client, b)["ocr"]) == ("wartet", None)
    ocr[0]()
    x = holen(client, a)
    assert (x["betrag"], x["belegdatum"]) == (42.46, "2026-03-14")


# ---------- echte Erkennung ----------

def test_echte_erkennung_der_beispiele(client):
    pytest.importorskip("rapidocr")
    from ocr_rauchtest import SOLL
    import texterkennung
    for name, soll in SOLL.items():
        t = belege.ocr_vorschlaege(texterkennung.lesen(str(SCANS / name)))
        assert (t["betrag"], t["belegdatum"]) == soll, name


def test_kaputte_datei(tmp_path):
    pytest.importorskip("rapidocr")
    import texterkennung
    p = tmp_path / "kaputt.jpg"
    p.write_bytes(b"\xff\xd8\xff kein Bild")
    with pytest.raises(texterkennung.Fehlgeschlagen):
        texterkennung.lesen(str(p))

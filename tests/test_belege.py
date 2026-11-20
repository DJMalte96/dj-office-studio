"""Belege auslesen: echte (bereinigte) Kauf-Mails, PDF-Rechnungen, Fotos und Beträge in allen Schreibweisen."""
from pathlib import Path

import pytest

import belege

MAILS = Path(__file__).parent / "beispiele" / "mails"


@pytest.mark.parametrize("datei, lieferant, datum, betrag, satz, steuer", [
    ("apple.eml", "Apple", "2026-11-09", 1.29, 19.0, 0.21),
    ("amazon.eml", "Amazon", "2026-11-07", 1.29, 19.0, 0.21),
    ("beatport.eml", "Beatport", "2026-10-31", 5.33, 19.0, 0.85),
    ("qobuz.eml", "Qobuz", "2026-11-09", 3.63, None, None),
])
def test_kauf_mails(datei, lieferant, datum, betrag, satz, steuer):
    v = belege.auswerten(datei, (MAILS / datei).read_bytes())
    assert v["typ"] == "mail" and v["lieferant"] == lieferant and v["belegdatum"] == datum
    assert v["betrag"] == betrag and v["ust_satz"] == satz and v["ust_betrag"] == steuer
    assert v["kategorie"] == "musik" and v["message_id"]


def test_beatport_titel_und_amazon_hinweis():
    assert belege.auswerten("x.eml", (MAILS / "beatport.eml").read_bytes())["beschreibung"] == "2 Titel (AIFF)"
    v = belege.auswerten("x.eml", (MAILS / "amazon.eml").read_bytes())
    assert any("Amazon-Konto" in h for h in v["hinweise"])


@pytest.mark.parametrize("text, wert", [
    ("1.234,56 €", 1234.56), ("EUR 1,29", 1.29), ("€5.33", 5.33), ("3.63€", 3.63), ("960,- Euro", 960.0),
    ("1,234.56 EUR", 1234.56), ("12 €", 12.0), ("Summe: 54,80 EUR", 54.80)])
def test_betraege(text, wert):
    assert belege.betraege(text) == [wert]


def test_kein_betrag_in_woertern():
    assert belege.betraege("Euroland 5 Europa") == []


def _pdf(zeilen):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for z in zeilen:
        pdf.cell(0, 6, z, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_pdf_rechnung():
    daten = _pdf(["Musterhaus Technik GmbH", "Industriestr. 1, 12345 Musterstadt", "Rechnung Nr. 4711",
                  "Rechnungsdatum: 14.11.2026", "2 x XLR-Kabel 10 m      46,05 EUR", "Zwischensumme 46,05 EUR",
                  "zzgl. 19 % MwSt. 8,75 EUR", "Gesamtbetrag 54,80 EUR"])
    v = belege.auswerten("rechnung.pdf", daten)
    assert v["typ"] == "pdf" and v["lieferant"] == "Musterhaus Technik GmbH"
    assert v["belegdatum"] == "2026-11-14" and v["betrag"] == 54.80 and (v["ust_satz"], v["ust_betrag"]) == (19.0, 8.75)


def test_foto_und_scan():
    jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    v = belege.auswerten("IMG_2041.jpg", jpg)
    assert v["typ"] == "bild" and v["betrag"] is None and v["hinweise"]
    leer = _pdf([])   # PDF ohne Text (wie ein Scan)
    v = belege.auswerten("scan.pdf", leer)
    assert v["typ"] == "pdf" and v["betrag"] is None and "Scan" in v["hinweise"][0]
    assert belege.typ_von("foto.HEIC", b"....ftypheic") == "bild"


def test_mail_mit_pdf_anhang_hat_vorrang():
    from email.message import EmailMessage
    m = EmailMessage()
    m["From"], m["Subject"], m["Date"] = "Shop <rechnung@shop.example>", "Ihre Rechnung", "Fri, 13 Nov 2026 10:00:00 +0100"
    m["Message-ID"] = "<abc@shop.example>"
    m.set_content("Vielen Dank für Ihren Einkauf! Bestellwert ca. 99,00 EUR")
    m.add_attachment(_pdf(["Shop GmbH", "Rechnung", "Gesamtbetrag 119,00 EUR", "darin 19 % MwSt. 19,00 EUR"]),
                     maintype="application", subtype="pdf", filename="Rechnung.pdf")
    v = belege.auswerten("x.eml", m.as_bytes())
    assert v["betrag"] == 119.0 and v["lieferant"] == "Shop" and v["belegdatum"] == "2026-11-13"
    assert any("angehängten PDF" in h for h in v["hinweise"])


def _mbox(*mails):
    """Postfach-Export wie aus Apple Mail: „From “-Zeile vor jeder Mail, Leerzeile dazwischen, „>From “ im Text."""
    teile = []
    for m in mails:
        m = m.replace(b"\r\n", b"\n").rstrip(b"\n") + b"\n"
        teile.append(b"From ???@??? Fri Nov 20 13:18:00 2026\n" + m)
    return b"\n".join(teile)


def test_postfach_export_mbox(client):
    import io
    from pathlib import Path
    ordner = Path(__file__).parent / "beispiele" / "mails"
    mails = [(ordner / n).read_bytes() for n in ("beatport.eml", "apple.eml", "qobuz.eml")]
    mails[0] = mails[0].replace(b"\n\n", b"\n\n>From der Redaktion: Danke!\n\n", 1)    # escapte Zeile im Text
    mbox = _mbox(*mails)
    r = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(mbox), "mbox")]},
                    content_type="multipart/form-data").get_json()
    assert len(r["neu"]) == 3 and not r["fehler"]
    assert {a["lieferant"] for a in r["neu"]} >= {"Beatport", "Qobuz"}
    assert all(a["beleg_name"].endswith(".eml") for a in r["neu"])
    # derselbe Export noch einmal (z. B. später mit neuen Mails) → alles doppelt
    r = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(mbox), "Musikkäufe.mbox")]},
                    content_type="multipart/form-data").get_json()
    assert not r["neu"] and len(r["doppelt"]) == 3


def test_mbox_aufteilen_trennt_nur_an_echten_grenzen():
    import belege
    mbox = b"From a@b Fri Nov 20 2026\nSubject: Eins\n\nText\nFrom hier geht es weiter\n\nFrom c@d Fri Nov 20 2026\nSubject: Zwei\n\n>From zitiert\n"
    teile = belege.mbox_aufteilen(mbox)
    assert [n for n, _ in teile] == ["Eins (1).eml", "Zwei (2).eml"]
    assert b"From hier geht es weiter" in teile[0][1] and teile[1][1].endswith(b"\nFrom zitiert\n")

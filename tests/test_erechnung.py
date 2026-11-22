"""E-Rechnungen lesen: Formate, Vorschläge, feindliche Dateien."""
import io
import time
import zlib
from email.message import EmailMessage

import pytest

import belege
import erechnung
from erechnung_muster import cii, mail, pdf, ubl, zugferd1


def test_xrechnung_ubl():
    r = erechnung.lesen(ubl())
    assert (r["format"], r["nummer"], r["datum"], r["brutto"], r["netto"], r["steuer"]) == ("XRechnung", "R-1", "2026-03-14", 119, 100, 19)
    assert r["verkaeufer"]["name"] == "Musikhaus Probe GmbH" and r["kaeufer"]["name"] == "Max Beispiel"
    assert r["posten"][0] | {"je": None} == {"name": "XLR-Kabel", "menge": 1, "einheit": "C62", "preis": 100, "je": None, "satz": 19, "summe": 100}
    assert erechnung.ust_satz(r) == 19 and erechnung.beschreibung(r) == "XLR-Kabel · Nr. R-1"


def test_cii_waehlt_steuer_in_rechnungswaehrung():
    r = erechnung.lesen(cii())
    assert (r["format"], r["nummer"], r["datum"], r["brutto"], r["steuer"]) == ("ZUGFeRD/Factur-X", "C-7", "2026-05-02", 53.5, 3.5)
    assert erechnung.ust_satz(r) == 7 and erechnung.beschreibung(r) == "Nr. C-7" and r["verkaeufer"]["name"] == "Notenladen Probe KG"


def test_zugferd_1():
    r = erechnung.lesen(zugferd1())
    assert (r["format"], r["datum"], r["brutto"], r["steuer"], r["verkaeufer"]["name"]) == ("ZUGFeRD/Factur-X", "2019-10-07", 119, 19, "Altladen Probe")
    assert r["posten"][0]["name"] == "Stativ" and erechnung.ust_satz(r) == 19


@pytest.mark.parametrize("daten", [ubl(gutschrift=True), ubl(art=381), cii(art="381"),
                                   ubl(gutschrift=True, brutto="-119.00", netto="-100.00", steuer="-19.00")])
def test_gutschrift_ist_negativ(daten):
    r = erechnung.lesen(daten)
    assert r["gutschrift"] and erechnung.ausgabe_betrag(r) < 0 and erechnung.ust_satz(r)
    assert any("Gutschrift" in h for h in erechnung.hinweise(r))


def test_korrekturrechnung_behaelt_ihr_vorzeichen():
    assert erechnung.ausgabe_betrag(erechnung.lesen(ubl(brutto="-11.90"))) == -11.9


def test_fremdwaehrung_ohne_euro_betrag():
    r = erechnung.lesen(ubl(waehrung="USD"))
    assert erechnung.ausgabe_betrag(r) is None and erechnung.ust_satz(r) is None
    assert "119,00 USD" in " ".join(erechnung.hinweise(r))


def test_gemischte_steuer_ohne_satz():
    r = erechnung.lesen(ubl(brutto="226.00", netto="200.00", steuer="26.00", steuern=[("100", "19", "19"), ("100", "7", "7")]))
    assert erechnung.ust_satz(r) is None and erechnung.kurz(r)["steuer_gemischt"]


def test_teils_steuerfrei_ohne_satz():
    r = erechnung.lesen(ubl(brutto="219.00", netto="200.00", steuer="19.00", steuern=[("100", "19", "19"), ("100", "0", "0")]))
    assert erechnung.ust_satz(r) is None


def test_auslaendischer_satz_ohne_satz():
    assert erechnung.ust_satz(erechnung.lesen(ubl(brutto="120.00", steuer="20.00", satz="20"))) is None


@pytest.mark.parametrize("kategorie, da", [("AE", True), ("K", True), ("S", False)])
def test_steuerschuld_des_empfaengers(kategorie, da):
    h = " ".join(erechnung.hinweise(erechnung.lesen(ubl(brutto="100", steuer="0", satz="0", kategorie=kategorie))))
    assert ("§ 13b" in h) == da


def test_anzahlung():
    h = " ".join(erechnung.hinweise(erechnung.lesen(ubl(angezahlt="50.00", zahlbar="69.00"))))
    assert "50,00 €" in h and "69,00 €" in h
    assert not erechnung.hinweise(erechnung.lesen(ubl(angezahlt="119.00", zahlbar="0.00")))     # schlicht bezahlt
    assert not erechnung.hinweise(erechnung.lesen(ubl(angezahlt="-5.00", zahlbar="124.00")))


def test_summe_passt_nicht():
    assert any("ergeben" in h for h in erechnung.hinweise(erechnung.lesen(ubl(brutto="150.00"))))


@pytest.mark.parametrize("wert", ["NaN", "Infinity", "1e999", "12,50", "99999999999999999999999999", "9999999999", "abc"])
def test_unsinnige_betraege(wert):
    assert erechnung.lesen(ubl(brutto=wert, netto="x", zahlbar="y"))["brutto"] is None


@pytest.mark.parametrize("datum", ["0001-01-01", "9999-12-31", "2026-02-30", "../../etc", ""])
def test_unsinniges_datum(datum):
    r = erechnung.lesen(ubl(datum=datum))
    assert r["datum"] is None and any("Datum" in h for h in erechnung.hinweise(r))


def test_kodierungen():
    text = ubl(verkaeufer="Müller Bühnenbedarf").decode()
    for kod in ("utf-16", "iso-8859-1", "windows-1252", "utf-8-sig"):
        daten = text.replace('encoding="UTF-8"', f'encoding="{kod.replace("-sig", "")}"').encode(kod)
        assert erechnung.ist_xml("ohne-endung", daten), kod
        assert erechnung.lesen(daten)["verkaeufer"]["name"] == "Müller Bühnenbedarf", kod


# ---------- feindliche Dateien

LACHEN = '<!DOCTYPE x [<!ENTITY a "haha"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;">]>'


@pytest.mark.parametrize("dtd", [LACHEN, '<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]>',
                                 '<!DOCTYPE x SYSTEM "http://127.0.0.1:9/x.dtd">'])
@pytest.mark.parametrize("kod", ["utf-8", "utf-16"])
def test_doctype_wird_nie_gelesen(dtd, kod):
    daten = ubl(kopf=dtd).decode().replace('encoding="UTF-8"', f'encoding="{kod}"').encode(kod)
    with pytest.raises(erechnung.Unlesbar, match="DOCTYPE"):
        erechnung.lesen(daten)


def test_zu_tief():
    with pytest.raises(erechnung.Unlesbar, match="verschachtelt"):
        erechnung.lesen(b"<a>" * 5000 + b"</a>" * 5000)


def test_zu_viele_elemente(monkeypatch):
    monkeypatch.setattr(erechnung, "MAX_ELEMENTE", 1000)
    with pytest.raises(erechnung.Unlesbar, match="zu groß"):
        erechnung.lesen(b"<a>" + b"<b/>" * 2000 + b"</a>")


def test_zu_gross(monkeypatch):
    monkeypatch.setattr(erechnung, "MAX_BYTES", 100)
    with pytest.raises(erechnung.Unlesbar, match="20 MB"):
        erechnung.lesen(ubl())


def test_langer_namensraum_vervielfacht_keinen_speicher():
    daten = b'<a xmlns="' + b"u" * 1_000_000 + b'">' + b"<b/>" * 100_000 + b"</a>"
    anfang = time.time()
    with pytest.raises(erechnung.Unlesbar, match="Namensr"):
        erechnung.lesen(daten)
    assert time.time() - anfang < 5


@pytest.mark.parametrize("daten", [b"", b"<", b"\x00\x01\x02", ubl()[:300], b'<?xml version="1.0" encoding="gibtsnicht"?><a/>',
                                   b'<?xml version="1.0" encoding="shift_jis"?><a/>'])
def test_kaputtes_xml(daten):
    with pytest.raises(erechnung.Unlesbar):
        erechnung.lesen(daten)


@pytest.mark.parametrize("kod", ["utf-8", "utf-16"])
@pytest.mark.parametrize("gleich", ['="x>y"', " = 'x'"])
def test_zu_viele_attribute_in_einem_tag(kod, gleich, monkeypatch):
    text = "<?xml version='1.0' encoding='%s'?><a " % kod + " ".join(f"a{i}{gleich}" for i in range(6000)) + "/>"
    monkeypatch.setattr(erechnung.expat, "ParserCreate", lambda **k: pytest.fail("kam bis zum Parser"))
    with pytest.raises(erechnung.Unlesbar, match="Attribute"):
        erechnung.lesen(text.encode(kod))


def test_zu_viele_attribute_insgesamt(monkeypatch):
    monkeypatch.setattr(erechnung, "MAX_ELEMENTE", 1000)
    with pytest.raises(erechnung.Unlesbar, match="Attribute"):
        erechnung.lesen(b"<a>" + b'<b p="1" q="2" r="3"/>' * 500 + b"</a>")


def test_grosser_eingebetteter_anhang_ist_erlaubt():
    anhang = '<cac:AdditionalDocumentReference><cac:Attachment><cbc:EmbeddedDocumentBinaryObject filename="r.pdf">' \
        + "QUJD=\n" * 400_000 + "</cbc:EmbeddedDocumentBinaryObject></cac:Attachment></cac:AdditionalDocumentReference>"
    assert erechnung.lesen(ubl(zusatz=anhang))["anlagen"] == ["r.pdf"]


def test_fremdes_xml():
    with pytest.raises(erechnung.KeineRechnung):
        erechnung.lesen(b"<playlist><track/></playlist>")
    with pytest.raises(erechnung.KeineRechnung):
        erechnung.lesen(b"<Invoice><ID>1</ID></Invoice>")       # ohne Namensraum


def test_lesefassung_maskiert_alles():
    boese = "&lt;script&gt;alert(1)&lt;/script&gt;&lt;img src=x onerror=alert(2)&gt;"
    r = erechnung.lesen(ubl(nummer=boese, verkaeufer=boese, posten=boese, steuer_id=boese,
                            zusatz=f"<cbc:Note>{boese}</cbc:Note>"))
    seite = erechnung.lesefassung(r)
    assert "<script" not in seite and "<img" not in seite and "&lt;script&gt;" in seite and "href" not in seite


def test_pdf_bombe_wird_nicht_entpackt():
    class Strom(dict):
        pass

    s = Strom({"/Filter": "/FlateDecode"})
    s._data = zlib.compress(b" " * (erechnung.MAX_BYTES + 5000), 9)
    assert erechnung._entpacken(s) is None


def test_pdf_anhaenge_zusammen_begrenzt(monkeypatch):
    daten = pdf(anhaenge=[(f"a{i}.xml", b"<a>" + b"x" * 400 + b"</a>") for i in range(5)])
    monkeypatch.setattr(erechnung, "MAX_BYTES", 1000)
    assert len(erechnung.pdf_anhaenge(daten)) == 2


# ---------- aus PDF und Mail

def test_bekannter_name_zuerst():
    assert erechnung.pdf_anhaenge(pdf(anhaenge=[("a.xml", b"<a/>"), ("factur-x.xml", cii())]))[0][0] == "factur-x.xml"


def test_namensbaum_mit_kids_und_nur_af():
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, TextStringObject

    for weg in ("kids", "af"):
        w = PdfWriter()
        w.append(PdfReader(io.BytesIO(pdf())))
        strom = DecodedStreamObject()
        strom.set_data(cii())
        spec = w._add_object(DictionaryObject({
            NameObject("/F"): TextStringObject("factur-x.xml"),
            NameObject("/EF"): DictionaryObject({NameObject("/F"): w._add_object(strom)})}))
        if weg == "af":
            w._root_object[NameObject("/AF")] = ArrayObject([spec])
        else:
            blatt = w._add_object(DictionaryObject({NameObject("/Names"): ArrayObject([TextStringObject("factur-x.xml"), spec])}))
            w._root_object[NameObject("/Names")] = DictionaryObject({
                NameObject("/EmbeddedFiles"): DictionaryObject({NameObject("/Kids"): ArrayObject([blatt])})})
        aus = io.BytesIO()
        w.write(aus)
        assert erechnung.pdf_anhaenge(aus.getvalue()) == [("factur-x.xml", cii())], weg


def test_zugferd_schlaegt_sichtbaren_text():
    v = belege.auswerten("r.pdf", pdf(["Notenladen", "Zwischensumme 50,00 EUR", "Gesamt 53,50 EUR"], [("factur-x.xml", cii())]))
    assert (v["betrag"], v["lieferant"], v["belegdatum"], v["hinweise"]) == (53.5, "Notenladen Probe KG", "2026-05-02", [])


@pytest.mark.parametrize("zeile", ["Gesamt 9,99 EUR", "Rechnungsbetrag 9,99"])
def test_versteckte_xml_weicht_vom_pdf_ab(zeile):
    v = belege.auswerten("r.pdf", pdf([zeile], [("factur-x.xml", cii())]))
    assert any("sichtbaren PDF" in h for h in v["hinweise"])


@pytest.mark.parametrize("betrag, text, da", [(1234.5, "1.234,50 EUR", True), (1234.5, "1,234.50", True), (1234.5, "1 234,50", True),
                                              (119, "119 EUR", True), (119, "119,- EUR", True), (19, "119,00", False),
                                              (119, "119,50", False), (-11.9, "-11,90", True)])
def test_betrag_im_text(betrag, text, da):
    assert belege._betrag_im_text(betrag, text) == da


def test_kaputte_xml_im_pdf_faellt_auf_text_zurueck():
    v = belege.auswerten("r.pdf", pdf(["Laden", "Gesamt 9,99 EUR"], [("factur-x.xml", b"<kaputt")]))
    assert v["betrag"] == 9.99 and any("nicht lesbar" in h for h in v["hinweise"])


def test_mail_mit_xml_und_rechnungsdatum():
    v = belege.auswerten("k.eml", mail(("r.xml", ubl())))
    assert (v["betrag"], v["lieferant"], v["belegdatum"]) == (119, "Musikhaus Probe GmbH", "2026-03-14")
    assert "absender_adresse" not in v


def test_mail_mit_zugferd_pdf():
    v = belege.auswerten("k.eml", mail(("r.pdf", pdf(anhaenge=[("factur-x.xml", cii())]))))
    assert v["betrag"] == 53.5 and v["erechnung"]["nummer"] == "C-7"


def test_mail_zaehlt_dieselbe_rechnung_einmal():
    v = belege.auswerten("k.eml", mail(("r.xml", cii()), ("r.pdf", pdf(anhaenge=[("factur-x.xml", cii())]))))
    assert v["betrag"] == 53.5 and "mehrere" not in v["erechnung"]


def test_mail_mit_zwei_rechnungen_ohne_betrag():
    v = belege.auswerten("k.eml", mail(("a.xml", ubl("A")), ("b.xml", ubl("B"))))
    assert v["betrag"] is None and v["erechnung"]["mehrere"] == 2


def test_weitergeleitete_mail_als_anhang():
    m = EmailMessage()
    m["From"], m["Subject"] = "Max Beispiel <max@example.org>", "Fwd"
    m.set_content("siehe Anhang")
    m.add_attachment(__import__("email").message_from_bytes(mail(("r.xml", ubl())), policy=__import__("email").policy.default))
    assert belege.auswerten("k.eml", m.as_bytes())["betrag"] == 119


def test_mail_die_nur_aus_der_xml_besteht():
    m = EmailMessage()
    m["From"], m["Subject"] = "Laden <laden@example.org>", "Rechnung"
    m.set_content(ubl(), maintype="application", subtype="xml")
    assert belege.auswerten("k.eml", m.as_bytes())["betrag"] == 119


def test_shopname_bleibt():
    v = belege.auswerten("k.eml", mail(("r.xml", ubl(verkaeufer="Beatport LLC")), von="Beatport <info@beatport.com>"))
    assert (v["lieferant"], v["kategorie"]) == ("Beatport", "musik")

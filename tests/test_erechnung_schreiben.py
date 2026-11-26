"""Seit 1.15: E-Rechnung schreiben – ZUGFeRD/Factur-X (EN 16931) im Rechnungs-PDF."""
import io

import facturx
import pytest
from lxml import etree

from conftest import KUNDE
import erechnung

VEREIN = {"name": "Sportverein Musterstadt e. V.", "strasse": "Sportplatz 1", "plz": "12345", "ort": "Musterstadt"}
POS = [{"beschreibung": "DJ – Tätigkeit Vereinsfeier – 19:00 Uhr bis 1:00 Uhr", "lieferdatum": "2026-10-31", "preis": 700}]


@pytest.fixture
def steuer(client):
    client.put("/api/einstellungen", json={"steuernummer": "12/345/67890"})


def rechnung(client, erechnung=True, kunde=VEREIN, positionen=POS, nummer="037", **mehr):
    return client.post("/api/rechnungen", json={"nummer": nummer, "datum": "2026-11-01", "kunde": kunde, "positionen": positionen,
                                               "zahlungsbedingung": "Bitte innerhalb der nächsten 8 Tage überweisen.",
                                               "erechnung": erechnung, **mehr})


def xml_aus(pdf):
    anh = erechnung.pdf_anhaenge(pdf)
    return dict(anh).get("factur-x.xml")


def test_e_rechnung_im_pdf(client, steuer):
    r = rechnung(client)
    assert r.status_code == 201, r.get_json()
    inv = client.get(f"/api/rechnungen/{r.get_json()['id']}").get_json()
    assert inv["erechnung"]
    pdf = client.get(f"/api/rechnungen/{inv['id']}/pdf").data
    xml = xml_aus(pdf)
    assert xml and facturx.xml_check_xsd(xml, flavor="factur-x", level="en16931")
    gelesen = erechnung.lesen(xml)
    assert (gelesen["nummer"], gelesen["datum"], gelesen["brutto"], gelesen["faellig"]) == ("037", "2026-11-01", 700, "2026-11-09")
    assert gelesen["profil"] == "urn:cen.eu:en16931:2017"
    assert b"12/345/67890" in xml and "§ 19 UStG".encode() in xml and b"<ram:CategoryCode>E</ram:CategoryCode>" in xml
    assert b"<ram:IBANID>DE001234</ram:IBANID>" in xml      # IBAN aus den Test-Einstellungen, ohne Leerzeichen
    assert facturx.get_level(etree.fromstring(xml)) == "en16931"


def test_mit_umsatzsteuer(client):
    client.put("/api/einstellungen", json={"kleinunternehmer": False, "steuernummer": "12/345/67890", "ust_satz": 19})
    r = rechnung(client)
    pdf = client.get(f"/api/rechnungen/{r.get_json()['id']}/pdf").data
    gelesen = erechnung.lesen(xml_aus(pdf))
    assert (gelesen["netto"], gelesen["steuer"], gelesen["brutto"]) == (700, 133, 833)


def test_ohne_haken_kein_xml(client, steuer):
    r = rechnung(client, erechnung=False)
    assert xml_aus(client.get(f"/api/rechnungen/{r.get_json()['id']}/pdf").data) is None


def test_fehlende_angaben(client):
    r = rechnung(client)
    assert r.status_code == 400 and "Steuernummer" in r.get_json()["error"]
    client.put("/api/einstellungen", json={"steuernummer": "12/345/67890"})
    assert rechnung(client).status_code == 201


def test_storno_einer_e_rechnung(client, steuer):
    rid = rechnung(client).get_json()["id"]
    sid = client.post(f"/api/rechnungen/{rid}/stornieren").get_json()["id"]
    xml = xml_aus(client.get(f"/api/rechnungen/{sid}/pdf").data)
    assert xml and b"<ram:IssuerAssignedID>037</ram:IssuerAssignedID>" in xml and b'unitCode="C62">-1<' in xml
    assert erechnung.lesen(xml)["brutto"] == -700


def test_schlussrechnung_abzug_mit_menge_minus_eins(client, steuer):
    anz = client.post("/api/rechnungen", json={"nummer": "030", "datum": "2026-10-01", "kunde": VEREIN, "erechnung": True,
                                              "rechnungsart": "anzahlung", "zahlungsbedingung": "8 Tage",
                                              "positionen": [{"beschreibung": "Anzahlung 30 %", "lieferdatum": "2026-10-31", "preis": 210}]})
    assert anz.status_code == 201, anz.get_json()
    aid = anz.get_json()["id"]
    assert b"<ram:TypeCode>386</ram:TypeCode>" in xml_aus(client.get(f"/api/rechnungen/{aid}/pdf").data)
    r = rechnung(client, rechnungsart="schluss", positionen=POS + [{"beschreibung": "abzüglich Anzahlung", "lieferdatum": "2026-10-01",
                                                                    "preis": -210, "anzahlung_id": aid}])
    assert r.status_code == 201, r.get_json()
    xml = xml_aus(client.get(f"/api/rechnungen/{r.get_json()['id']}/pdf").data)
    assert erechnung.lesen(xml)["brutto"] == 490 and b"<ram:ChargeAmount>-" not in xml


def test_angebote_nie(client, steuer):
    a = client.post("/api/angebote", json={"nummer": "012", "datum": "2026-11-20", "gueltig_bis": "2026-12-20", "kunde": KUNDE,
                                           "positionen": POS, "erechnung": True}).get_json()
    assert xml_aus(client.get(f"/api/angebote/{a['id']}/pdf").data) is None


def test_sonderzeichen_sicher(client, steuer):
    kunde = dict(VEREIN, name="Müller & Söhne <GmbH> \"Musik\"")
    r = rechnung(client, kunde=kunde)
    xml = xml_aus(client.get(f"/api/rechnungen/{r.get_json()['id']}/pdf").data)
    assert facturx.xml_check_xsd(xml, flavor="factur-x", level="en16931")
    assert "Müller &amp; Söhne &lt;GmbH&gt;".encode() in xml


def test_pdf_bleibt_lesbar(client, steuer):
    from pypdf import PdfReader
    r = rechnung(client)
    pdf = client.get(f"/api/rechnungen/{r.get_json()['id']}/pdf").data
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Rechnung Nr.: 037" in text and "Sportverein" in text

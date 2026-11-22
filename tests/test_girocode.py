"""GiroCode (EPC-QR-Code) auf Rechnungen und Mahnungen und zum Anzeigen in der App."""
import io

from pypdf import PdfReader

from conftest import neue_rechnung, pdf_text

import pdf


def bilder(daten):
    return sum(len(p.images) for p in PdfReader(io.BytesIO(daten)).pages)


def qr_im_pdf(daten):
    """Erkennt den gezeichneten GiroCode an seiner Beschriftung."""
    return "Bequem bezahlen" in pdf_text(daten)


ABS = {"name": "Max Beispiel", "iban": "DE02 1203 0000 0000 2020 51", "bic": "BYLADEM1001"}


def test_inhalt_nach_epc_standard():
    d = pdf.girocode_daten(ABS, 1020, "Rechnung 037").split("\n")
    assert d == ["BCD", "002", "1", "SCT", "BYLADEM1001", "Max Beispiel", "DE02120300000000202051",
                 "EUR1020.00", "", "", "Rechnung 037"]
    assert pdf.girocode_daten(ABS | {"kontoinhaber": "Max B. GbR"}, 99.5, "x").split("\n")[5:8] == \
        ["Max B. GbR", "DE02120300000000202051", "EUR99.50"]
    assert pdf.girocode_daten(ABS | {"iban": ""}, 100, "x") is None
    assert pdf.girocode_daten(ABS, 0, "x") is None and pdf.girocode_daten(ABS, -50, "x") is None
    assert pdf.girocode_daten(ABS | {"girocode": False}, 100, "x") is None


def test_qr_code_nur_wo_ueberwiesen_wird(client):
    client.put("/api/einstellungen", json={"iban": ABS["iban"]})
    offen = neue_rechnung(client, nummer="037")
    bar = neue_rechnung(client, nummer="038", zahlungsbedingung="Den Rechnungsbetrag habe ich dankend in bar erhalten.")
    assert qr_im_pdf(client.get(f"/api/rechnungen/{offen}/pdf").data)
    assert not qr_im_pdf(client.get(f"/api/rechnungen/{bar}/pdf").data)
    storno = client.post(f"/api/rechnungen/{offen}/stornieren").get_json()["id"]
    assert not qr_im_pdf(client.get(f"/api/rechnungen/{storno}/pdf").data)
    a = client.post("/api/angebote", json={"nummer": "010", "datum": "2026-11-01", "kunde": {"name": "X"},
                                           "positionen": [{"beschreibung": "DJ", "preis": 500}]}).get_json()["id"]
    assert not qr_im_pdf(client.get(f"/api/angebote/{a}/pdf").data)
    # abschaltbar
    neu = neue_rechnung(client, nummer="045")
    client.put("/api/einstellungen", json={"girocode": False, "schon_verschickt": []})  # Entwurf da, Absender geändert → Antwort auf die Rückfrage
    assert not qr_im_pdf(client.get(f"/api/rechnungen/{neu}/pdf").data)


def test_qr_code_in_mahnung(client):
    inv = neue_rechnung(client, datum="2026-10-01")
    m = client.post(f"/api/rechnungen/{inv}/mahnung").get_json()
    assert qr_im_pdf(client.get(f"/api/mahnungen/{m['id']}/pdf").data)


def test_anzeigen_in_der_app(client):
    inv = neue_rechnung(client, nummer="037", preis=960)
    r = client.get(f"/api/rechnungen/{inv}/girocode")
    assert r.status_code == 200 and r.mimetype == "image/svg+xml" and b"<svg" in r.data
    info = client.get(f"/api/rechnungen/{inv}/girocode?info=1").get_json()
    assert info["betrag"] == 960 and info["zweck"] == "Rechnung 037" and info["empfaenger"] == "Max Beispiel"
    # auch wenn der Druck im PDF abgeschaltet ist
    client.put("/api/einstellungen", json={"girocode": False})
    assert client.get(f"/api/rechnungen/{inv}/girocode").status_code == 200
    # bezahlt → kein QR-Code mehr
    client.patch(f"/api/rechnungen/{inv}/bezahlt", json={"bezahlt": True})
    assert client.get(f"/api/rechnungen/{inv}/girocode").status_code == 400
    # ohne IBAN → verständlicher Hinweis
    client.put("/api/einstellungen", json={"iban": ""})
    r = client.get(f"/api/rechnungen/{neue_rechnung(client, nummer='040')}/girocode")
    assert r.status_code == 400 and "IBAN" in r.get_json()["error"]


def test_qr_code_ist_lesbar(client):
    """Das PDF so darstellen, wie es ein Viewer tut (PDFium), und den QR-Code mit einem echten Decoder lesen."""
    import pytest
    pdfium = pytest.importorskip("pypdfium2")
    zxingcpp = pytest.importorskip("zxingcpp")
    client.put("/api/einstellungen", json={"iban": ABS["iban"], "bic": ABS["bic"]})
    inv = neue_rechnung(client, nummer="037", preis=1020)
    seite = pdfium.PdfDocument(client.get(f"/api/rechnungen/{inv}/pdf").data)[0]
    treffer = zxingcpp.read_barcodes(seite.render(scale=200 / 72).to_pil())
    assert [t.text for t in treffer] == ["\n".join(["BCD", "002", "1", "SCT", "BYLADEM1001", "Max Beispiel",
                                                    "DE02120300000000202051", "EUR1020.00", "", "", "Rechnung 037"])]
    # Vektorgrafik statt eingebettetem Bild (Schwarz-Weiß-Bilder wurden teils fehlerhaft dargestellt)
    assert bilder(client.get(f"/api/rechnungen/{inv}/pdf").data) == 0

"""Baukasten für erfundene E-Rechnungen (Tests und Rauchtest)."""
import io

UBL = "urn:oasis:names:specification:ubl:schema:xsd:"
RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"


def ubl(nummer="R-1", datum="2026-03-14", brutto="119.00", netto="100.00", steuer="19.00", satz="19", waehrung="EUR",
        verkaeufer="Musikhaus Probe GmbH", steuer_id="DE111111111", mail="rechnung@example.org", gutschrift=False,
        kategorie="S", posten="XLR-Kabel", angezahlt=None, zahlbar=None, art=None, steuern=None, kopf="", zusatz=""):
    was = "CreditNote" if gutschrift else "Invoice"
    menge = "CreditedQuantity" if gutschrift else "InvoicedQuantity"
    g = f'currencyID="{waehrung}"'
    teile = steuern or [(netto, steuer, satz)]
    sub = "".join(f"<cac:TaxSubtotal><cbc:TaxableAmount {g}>{n}</cbc:TaxableAmount><cbc:TaxAmount {g}>{s}</cbc:TaxAmount>"
                  f"<cac:TaxCategory><cbc:ID>{kategorie}</cbc:ID><cbc:Percent>{p}</cbc:Percent></cac:TaxCategory></cac:TaxSubtotal>"
                  for n, s, p in teile)
    vor = f"<cbc:PrepaidAmount {g}>{angezahlt}</cbc:PrepaidAmount>" if angezahlt is not None else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>{kopf}
<{was} xmlns="{UBL}{was}-2" xmlns:cac="{UBL}CommonAggregateComponents-2" xmlns:cbc="{UBL}CommonBasicComponents-2">
<cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0</cbc:CustomizationID>
<cbc:ID>{nummer}</cbc:ID><cbc:IssueDate>{datum}</cbc:IssueDate>
<cbc:{was}TypeCode>{art or (381 if gutschrift else 380)}</cbc:{was}TypeCode>{zusatz}
<cbc:DocumentCurrencyCode>{waehrung}</cbc:DocumentCurrencyCode>
<cac:AccountingSupplierParty><cac:Party><cbc:EndpointID schemeID="EM">{mail}</cbc:EndpointID>
<cac:PartyTaxScheme><cbc:CompanyID>{steuer_id}</cbc:CompanyID></cac:PartyTaxScheme>
<cac:PartyLegalEntity><cbc:RegistrationName>{verkaeufer}</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party></cac:AccountingSupplierParty>
<cac:AccountingCustomerParty><cac:Party><cac:PartyLegalEntity><cbc:RegistrationName>Max Beispiel</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party></cac:AccountingCustomerParty>
<cac:TaxTotal><cbc:TaxAmount {g}>{steuer}</cbc:TaxAmount>{sub}</cac:TaxTotal>
<cac:LegalMonetaryTotal><cbc:TaxExclusiveAmount {g}>{netto}</cbc:TaxExclusiveAmount>
<cbc:TaxInclusiveAmount {g}>{brutto}</cbc:TaxInclusiveAmount>{vor}
<cbc:PayableAmount {g}>{zahlbar or brutto}</cbc:PayableAmount></cac:LegalMonetaryTotal>
<cac:{was}Line><cbc:ID>1</cbc:ID><cbc:{menge} unitCode="C62">1</cbc:{menge}><cbc:LineExtensionAmount {g}>{netto}</cbc:LineExtensionAmount>
<cac:Item><cbc:Name>{posten}</cbc:Name><cac:ClassifiedTaxCategory><cbc:Percent>{satz}</cbc:Percent></cac:ClassifiedTaxCategory></cac:Item>
<cac:Price><cbc:PriceAmount {g}>{netto}</cbc:PriceAmount></cac:Price></cac:{was}Line>
</{was}>""".encode()


def cii(nummer="C-7", datum="20260502", brutto="53.50", netto="50.00", steuer="3.50", satz="7", art="380",
        verkaeufer="Notenladen Probe KG"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" xmlns:ram="{RAM}" xmlns:udt="{UDT}">
<rsm:ExchangedDocumentContext><ram:GuidelineSpecifiedDocumentContextParameter><ram:ID>urn:factur-x.eu:1p0:basicwl</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter></rsm:ExchangedDocumentContext>
<rsm:ExchangedDocument><ram:ID>{nummer}</ram:ID><ram:TypeCode>{art}</ram:TypeCode>
<ram:IssueDateTime><udt:DateTimeString format="102">{datum}</udt:DateTimeString></ram:IssueDateTime></rsm:ExchangedDocument>
<rsm:SupplyChainTradeTransaction><ram:ApplicableHeaderTradeAgreement><ram:SellerTradeParty><ram:Name>{verkaeufer}</ram:Name></ram:SellerTradeParty></ram:ApplicableHeaderTradeAgreement>
<ram:ApplicableHeaderTradeSettlement><ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
<ram:ApplicableTradeTax><ram:CalculatedAmount>{steuer}</ram:CalculatedAmount><ram:BasisAmount>{netto}</ram:BasisAmount><ram:CategoryCode>S</ram:CategoryCode><ram:RateApplicablePercent>{satz}</ram:RateApplicablePercent></ram:ApplicableTradeTax>
<ram:SpecifiedTradeSettlementHeaderMonetarySummation><ram:TaxBasisTotalAmount>{netto}</ram:TaxBasisTotalAmount>
<ram:TaxTotalAmount currencyID="USD">9.99</ram:TaxTotalAmount><ram:TaxTotalAmount currencyID="EUR">{steuer}</ram:TaxTotalAmount>
<ram:GrandTotalAmount>{brutto}</ram:GrandTotalAmount><ram:DuePayableAmount>{brutto}</ram:DuePayableAmount>
</ram:SpecifiedTradeSettlementHeaderMonetarySummation></ram:ApplicableHeaderTradeSettlement></rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>""".encode()


def zugferd1():
    return b"""<?xml version="1.0"?>
<rsm:CrossIndustryDocument xmlns:rsm="urn:ferd:CrossIndustryDocument:invoice:1p0" xmlns:ram="urn:ram:12" xmlns:udt="urn:udt:15">
<rsm:HeaderExchangedDocument><ram:ID>Z1-9</ram:ID><ram:TypeCode>380</ram:TypeCode>
<ram:IssueDateTime><udt:DateTimeString format="102">20191007</udt:DateTimeString></ram:IssueDateTime></rsm:HeaderExchangedDocument>
<rsm:SpecifiedSupplyChainTradeTransaction><ram:ApplicableSupplyChainTradeAgreement><ram:SellerTradeParty><ram:Name>Altladen Probe</ram:Name></ram:SellerTradeParty></ram:ApplicableSupplyChainTradeAgreement>
<ram:ApplicableSupplyChainTradeSettlement><ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
<ram:ApplicableTradeTax><ram:CalculatedAmount currencyID="EUR">19.00</ram:CalculatedAmount><ram:ApplicablePercent>19.00</ram:ApplicablePercent></ram:ApplicableTradeTax>
<ram:SpecifiedTradeSettlementMonetarySummation><ram:TaxTotalAmount currencyID="EUR">19.00</ram:TaxTotalAmount>
<ram:GrandTotalAmount currencyID="EUR">119.00</ram:GrandTotalAmount></ram:SpecifiedTradeSettlementMonetarySummation></ram:ApplicableSupplyChainTradeSettlement>
<ram:IncludedSupplyChainTradeLineItem><ram:SpecifiedTradeProduct><ram:Name>Stativ</ram:Name></ram:SpecifiedTradeProduct></ram:IncludedSupplyChainTradeLineItem>
</rsm:SpecifiedSupplyChainTradeTransaction></rsm:CrossIndustryDocument>"""


def pdf(zeilen=("Rechnung",), anhaenge=()):
    from fpdf import FPDF
    from pypdf import PdfReader, PdfWriter
    f = FPDF()
    f.add_page()
    f.set_font("Helvetica", size=12)
    for z in zeilen:
        f.cell(0, 8, z, new_x="LMARGIN", new_y="NEXT")
    roh = bytes(f.output())
    if not anhaenge:
        return roh
    w = PdfWriter()
    w.append(PdfReader(io.BytesIO(roh)))
    for name, daten in anhaenge:
        w.add_attachment(name, daten)
    aus = io.BytesIO()
    w.write(aus)
    return aus.getvalue()


def mail(*anhaenge, von="Laden <laden@example.org>", nummer=1, text="Anbei die Rechnung."):
    from email.message import EmailMessage
    m = EmailMessage()
    m["From"], m["Subject"], m["Message-ID"] = von, "Ihre Rechnung", f"<{nummer}@example.org>"
    m["Date"] = "Wed, 18 Mar 2026 10:00:00 +0100"
    m.set_content(text)
    for name, daten in anhaenge:
        m.add_attachment(daten, maintype="application", subtype="pdf" if name.endswith(".pdf") else "xml", filename=name)
    return m.as_bytes()

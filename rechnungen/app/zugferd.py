"""E-Rechnung schreiben (seit 1.15): ZUGFeRD / Factur-X im Profil EN 16931.

Das Rechnungs-PDF bleibt, wie es ist (für Menschen); eingebettet wird die maschinenlesbare Rechnung (factur-x.xml,
CII-Syntax). Das XML ist die eigentliche E-Rechnung – Buchhaltungsprogramme von Firmen und Vereinen lesen es ein.

Abbildung:
- Rechnung 380, Anzahlungsrechnung 386, Stornorechnung 380 mit Bezug auf die stornierte Rechnung (BT-25).
- Jede Position mit Menge 1 (C62); negative Positionen (Abzug einer Anzahlung, Storno) mit Menge −1 – EN 16931
  erlaubt keine negativen Einzelpreise (BR-27).
- Kleinunternehmer: Steuerkategorie E (befreit) mit Befreiungsgrund § 19 UStG, sonst S mit dem Satz der Rechnung.
- Zahlung per Überweisung (58) mit IBAN/BIC, Zahlungsbedingung als Text, Fälligkeit wenn erkennbar.
"""
import re
from xml.sax.saxutils import escape

KU_GRUND = "Kleinunternehmer gemäß § 19 UStG – keine Umsatzsteuer"
NS = ('xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" '
      'xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" '
      'xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100" '
      'xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"')


def _t(v, laenge=300):
    return escape(re.sub(r"\s+", " ", str(v or "")).strip()[:laenge])


def _betrag(v):
    return f"{v:.2f}"


def _datum(iso):
    return f'<udt:DateTimeString format="102">{iso.replace("-", "")}</udt:DateTimeString>'


def _plz_ort(text):
    m = re.match(r"\s*(\d{4,5})\s+(.+)", text or "")
    return (m.group(1), m.group(2).strip()) if m else ("", (text or "").strip())


def fehlende_angaben(inv, a):
    """Was für eine gültige E-Rechnung noch fehlt (leere Liste = alles da)."""
    fehlt = []
    plz, ort = _plz_ort(a.get("plz_ort"))
    for wert, text in ((a.get("name"), "dein Name"), (a.get("strasse"), "deine Straße"), (ort, "dein Ort"),
                       (plz, "deine Postleitzahl (bei „PLZ und Ort“)"),
                       ((a.get("steuernummer") or a.get("ust_idnr") or "").strip(), "Steuernummer oder USt-IdNr."),
                       (inv["kunde"].get("name"), "Name des Kunden"), (inv["kunde"].get("ort"), "Ort des Kunden")):
        if not str(wert or "").strip():
            fehlt.append(text)
    return fehlt


def xml(inv, a, faellig=None, storno_von=None):
    """CII-XML (Factur-X/ZUGFeRD EN 16931) einer Rechnung. inv wie für das PDF, a = Absender des Belegs."""
    ku = inv.get("kleinunternehmer")
    ku = bool(a.get("kleinunternehmer")) if ku is None else bool(ku)
    satz = 0.0 if ku else float(inv.get("ust_satz") or a.get("ust_satz") or 19)
    kat = "E" if ku else "S"
    art = inv.get("rechnungsart")
    typ = "386" if art == "anzahlung" and not inv.get("storno_von") else "380"

    zeilen, summe = [], 0.0
    for i, p in enumerate(inv["positionen"], 1):
        preis = round(float(p.get("preis") or 0), 2)
        summe += preis
        menge = "-1" if preis < 0 else "1"
        zeilen.append(f"""
    <ram:IncludedSupplyChainTradeLineItem>
      <ram:AssociatedDocumentLineDocument><ram:LineID>{i}</ram:LineID></ram:AssociatedDocumentLineDocument>
      <ram:SpecifiedTradeProduct><ram:Name>{_t(p.get("beschreibung") or "Leistung")}</ram:Name></ram:SpecifiedTradeProduct>
      <ram:SpecifiedLineTradeAgreement>
        <ram:NetPriceProductTradePrice><ram:ChargeAmount>{_betrag(abs(preis))}</ram:ChargeAmount></ram:NetPriceProductTradePrice>
      </ram:SpecifiedLineTradeAgreement>
      <ram:SpecifiedLineTradeDelivery><ram:BilledQuantity unitCode="C62">{menge}</ram:BilledQuantity></ram:SpecifiedLineTradeDelivery>
      <ram:SpecifiedLineTradeSettlement>
        <ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>{kat}</ram:CategoryCode><ram:RateApplicablePercent>{satz:g}</ram:RateApplicablePercent></ram:ApplicableTradeTax>
        <ram:SpecifiedTradeSettlementLineMonetarySummation><ram:LineTotalAmount>{_betrag(preis)}</ram:LineTotalAmount></ram:SpecifiedTradeSettlementLineMonetarySummation>
      </ram:SpecifiedLineTradeSettlement>
    </ram:IncludedSupplyChainTradeLineItem>""")
    summe = round(summe, 2)
    steuer = 0.0 if ku else round(summe * satz / 100, 2)
    brutto = round(summe + steuer, 2)

    plz, ort = _plz_ort(a.get("plz_ort"))
    k = inv["kunde"]
    lieferung = max((p.get("lieferdatum") or "" for p in inv["positionen"]), default="") or inv["datum"]
    steuer_ids = "".join(f'<ram:SpecifiedTaxRegistration><ram:ID schemeID="{s}">{_t(v, 40)}</ram:ID></ram:SpecifiedTaxRegistration>'
                         for s, v in (("VA", a.get("ust_idnr")), ("FC", a.get("steuernummer"))) if (v or "").strip())
    mail = (f'<ram:URIUniversalCommunication><ram:URIID schemeID="EM">{_t(a.get("absender_email"), 200)}</ram:URIID></ram:URIUniversalCommunication>'
            if (a.get("absender_email") or "").strip() else "")
    kunden_mail = (f'<ram:URIUniversalCommunication><ram:URIID schemeID="EM">{_t(k.get("email"), 200)}</ram:URIID></ram:URIUniversalCommunication>'
                   if (k.get("email") or "").strip() else "")
    # BT-29: ohne USt-IdNr. braucht der Käufer eine Kennung des Verkäufers (BR-CO-26) – die Steuernummer
    kennung = (f"<ram:ID>{_t(a.get('steuernummer'), 40)}</ram:ID>"
               if not (a.get("ust_idnr") or "").strip() and (a.get("steuernummer") or "").strip() else "")
    iban = re.sub(r"\s+", "", a.get("iban") or "")
    bic = re.sub(r"\s+", "", a.get("bic") or "")
    zahlung = ""
    if iban and brutto > 0:
        inhaber = a.get("kontoinhaber") or a.get("name")
        zahlung = ("<ram:SpecifiedTradeSettlementPaymentMeans><ram:TypeCode>58</ram:TypeCode>"
                   f"<ram:PayeePartyCreditorFinancialAccount><ram:IBANID>{_t(iban, 34)}</ram:IBANID>"
                   + (f"<ram:AccountName>{_t(inhaber, 70)}</ram:AccountName>" if inhaber else "")
                   + "</ram:PayeePartyCreditorFinancialAccount>"
                   + (f"<ram:PayeeSpecifiedCreditorFinancialInstitution><ram:BICID>{_t(bic, 11)}</ram:BICID>"
                      "</ram:PayeeSpecifiedCreditorFinancialInstitution>" if bic else "")
                   + "</ram:SpecifiedTradeSettlementPaymentMeans>")
    grund = f"<ram:ExemptionReason>{_t(KU_GRUND)}</ram:ExemptionReason>" if ku else ""
    bedingung = _t(inv.get("zahlungsbedingung"), 1000)
    termine = ""
    if bedingung or faellig:
        termine = ("<ram:SpecifiedTradePaymentTerms>"
                   + (f"<ram:Description>{bedingung}</ram:Description>" if bedingung else "")
                   + (f"<ram:DueDateDateTime>{_datum(faellig)}</ram:DueDateDateTime>" if faellig else "")
                   + "</ram:SpecifiedTradePaymentTerms>")
    bezug = (f"<ram:InvoiceReferencedDocument><ram:IssuerAssignedID>{_t(storno_von['nummer'], 40)}</ram:IssuerAssignedID>"
             f"<ram:FormattedIssueDateTime><qdt:DateTimeString format=\"102\">{storno_von['datum'].replace('-', '')}</qdt:DateTimeString>"
             f"</ram:FormattedIssueDateTime></ram:InvoiceReferencedDocument>") if storno_von else ""
    notiz = []
    if ku:
        notiz.append(KU_GRUND)
    if storno_von:
        notiz.append(f"Stornorechnung zu Rechnung {storno_von['nummer']}")
    ort_v = inv.get("veranstaltungsort")
    if ort_v:
        notiz.append("Veranstaltungsort: " + ", ".join(x for x in (ort_v.get("name"), ort_v.get("strasse"),
                                                                   " ".join(y for y in (ort_v.get("plz"), ort_v.get("ort")) if y)) if x))
    notizen = "".join(f"<ram:IncludedNote><ram:Content>{_t(n, 500)}</ram:Content></ram:IncludedNote>" for n in notiz)
    kunden_adresse = "".join(x for x in (
        f"<ram:PostcodeCode>{_t(k.get('plz'), 10)}</ram:PostcodeCode>" if (k.get("plz") or "").strip() else "",
        f"<ram:LineOne>{_t(k.get('strasse'), 100)}</ram:LineOne>" if (k.get("strasse") or "").strip() else "",
        f"<ram:LineTwo>{_t(k.get('zusatz'), 100)}</ram:LineTwo>" if (k.get("zusatz") or "").strip() else "",
        f"<ram:CityName>{_t(k.get('ort'), 60)}</ram:CityName>" if (k.get("ort") or "").strip() else ""))

    text = f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice {NS}>
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter><ram:ID>urn:cen.eu:en16931:2017</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>{_t(inv["nummer"], 40)}</ram:ID>
    <ram:TypeCode>{typ}</ram:TypeCode>
    <ram:IssueDateTime>{_datum(inv["datum"])}</ram:IssueDateTime>{notizen}
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>{"".join(zeilen)}
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty>
        {kennung}<ram:Name>{_t(a.get("name"), 100)}</ram:Name>
        <ram:PostalTradeAddress>{f"<ram:PostcodeCode>{_t(plz, 10)}</ram:PostcodeCode>" if plz else ""}<ram:LineOne>{_t(a.get("strasse"), 100)}</ram:LineOne><ram:CityName>{_t(ort, 60)}</ram:CityName><ram:CountryID>DE</ram:CountryID></ram:PostalTradeAddress>
        {mail}{steuer_ids}
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty>
        <ram:Name>{_t(k.get("name"), 100)}</ram:Name>
        <ram:PostalTradeAddress>{kunden_adresse}<ram:CountryID>DE</ram:CountryID></ram:PostalTradeAddress>
        {kunden_mail}
      </ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery>
      <ram:ActualDeliverySupplyChainEvent><ram:OccurrenceDateTime>{_datum(lieferung)}</ram:OccurrenceDateTime></ram:ActualDeliverySupplyChainEvent>
    </ram:ApplicableHeaderTradeDelivery>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      {zahlung}
      <ram:ApplicableTradeTax><ram:CalculatedAmount>{_betrag(steuer)}</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode>{grund}<ram:BasisAmount>{_betrag(summe)}</ram:BasisAmount><ram:CategoryCode>{kat}</ram:CategoryCode><ram:RateApplicablePercent>{satz:g}</ram:RateApplicablePercent></ram:ApplicableTradeTax>
      {termine}
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>{_betrag(summe)}</ram:LineTotalAmount>
        <ram:TaxBasisTotalAmount>{_betrag(summe)}</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">{_betrag(steuer)}</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>{_betrag(brutto)}</ram:GrandTotalAmount>
        <ram:DuePayableAmount>{_betrag(brutto)}</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
      {bezug}
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>
"""
    return text.encode("utf-8")


def einbetten(pdf_bytes, xml_bytes, inv, a):
    """XML als factur-x.xml ins PDF (PDF/A-3-Anhang mit XMP-Kennzeichnung), XML gegen das XSD geprüft."""
    import facturx
    return facturx.generate_from_binary(
        pdf_bytes, xml_bytes, flavor="factur-x", level="en16931", check_xsd=True, lang="de-DE",
        pdf_metadata={"author": a.get("name") or "", "keywords": "Factur-X, ZUGFeRD, E-Rechnung",
                      "title": f"Rechnung {inv['nummer']}", "subject": f"Rechnung {inv['nummer']} vom {inv['datum']}"})


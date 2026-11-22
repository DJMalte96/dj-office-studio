"""E-Rechnungen lesen: XRechnung (UBL und CII) sowie ZUGFeRD/Factur-X (CII, in PDFs eingebettet; auch ZUGFeRD 1.0).

Liest nur, prüft nicht amtlich (dafür bräuchte es den Java-Validator der KoSIT). Ohne Importe aus der App.

Die Dateien kommen von Fremden:
- keine DOCTYPE/Entities (damit kein Nachladen und keine „Billion Laughs“)
- Grenzen für Größe, Elemente, Tiefe und Namensräume
- eingebettete Anhänge werden nur begrenzt entpackt
- in der Lesefassung ist alles maskiert, es gibt keine Links
"""
import html
import io
import re
import zlib
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree
from xml.parsers import expat

MAX_BYTES = 20 * 1024 * 1024
MAX_ELEMENTE = 200_000
MAX_TIEFE = 64
MAX_ATTRIBUTE_JE_TAG = 5000
MAX_NAMENSRAUM = 300        # expat hängt die Adresse an jeden Namen – lange vervielfachen den Speicher
MAX_ANHAENGE = 10
MAX_ZEILEN = 500            # in der Lesefassung

UBL_RECHNUNG = ("urn:oasis:names:specification:ubl:schema:xsd:Invoice-2", "Invoice")
UBL_GUTSCHRIFT = ("urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2", "CreditNote")
CII = ("urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100", "CrossIndustryInvoice")
ZUGFERD_1 = ("urn:ferd:CrossIndustryDocument:invoice:1p0", "CrossIndustryDocument")

GUTSCHRIFT_CODES = {"81", "83", "261", "262", "296", "308", "381", "396", "420", "458", "532"}     # UNTDID 1001
BEKANNTE_NAMEN = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml")
EINHEITEN = {"C62": "Stk.", "H87": "Stk.", "XPP": "Stk.", "HUR": "Std.", "MIN": "Min.", "DAY": "Tage", "MON": "Monate",
             "ANN": "Jahre", "KMT": "km", "MTR": "m", "KGM": "kg", "LS": "pauschal", "P1": "%"}


class Unlesbar(ValueError):
    """XML, das sich nicht (sicher) lesen lässt. Der Text ist für den Nutzer gedacht."""


class KeineRechnung(Unlesbar):
    """Lesbares XML, aber keine E-Rechnung."""


def ist_xml(name, daten):
    if (name or "").lower().endswith(".xml"):
        return True
    kopf = daten[:200]
    if kopf[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return kopf.decode("utf-16", "replace").lstrip().startswith("<?xml")
    return kopf.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<?xml")


# ---------- XML sicher lesen ----------

def _zu_viele_attribute(daten):
    """Vor dem Parser: expat legt alle Attribute eines Tags an, bevor es sich meldet (1,5 Mio. kosten über 500 MB).
    „<“ kann in keinem Tag stehen – also reicht es, lange Abschnitte zwischen zwei „<“ anzusehen."""
    roh = daten.replace(b"\0", b"") if b"\0" in daten[:200] else daten     # UTF-16
    for teil in re.finditer(rb"<[^<]{%d,}" % (MAX_ATTRIBUTE_JE_TAG * 4), roh):
        for i, _ in enumerate(re.finditer(rb"=\s*[\"']", teil.group())):
            if i >= MAX_ATTRIBUTE_JE_TAG:
                return True
    return False


def _baum(daten):
    """→ (Namensraum der Wurzel, Baum mit Namen ohne Namensraum)."""
    if len(daten) > MAX_BYTES:
        raise Unlesbar("XML-Datei ist zu groß (über 20 MB)")
    if _zu_viele_attribute(daten):
        raise Unlesbar("XML mit zu vielen Attributen")
    bau = ElementTree.TreeBuilder()
    p = expat.ParserCreate(namespace_separator="}")
    p.buffer_text = True
    stand = {"n": 0, "attribute": 0, "tiefe": 0, "ns": 0, "wurzel": ""}

    def verboten(*_):
        raise Unlesbar("XML mit DOCTYPE wird aus Sicherheitsgründen nicht gelesen")

    def namensraum(_kuerzel, uri):
        stand["ns"] += 1
        if len(uri or "") > MAX_NAMENSRAUM or stand["ns"] > MAX_ELEMENTE:
            raise Unlesbar("XML mit unzulässigen Namensräumen")

    def anfang(name, attribute):
        stand["n"] += 1
        stand["tiefe"] += 1
        stand["attribute"] += len(attribute)
        if stand["attribute"] > MAX_ELEMENTE:
            raise Unlesbar("XML mit zu vielen Attributen")
        if stand["n"] > MAX_ELEMENTE or stand["tiefe"] > MAX_TIEFE:
            raise Unlesbar("XML ist zu groß oder zu tief verschachtelt")
        uri, _, lokal = name.rpartition("}")
        if stand["n"] == 1:
            stand["wurzel"] = uri
        bau.start(lokal, {k.rpartition("}")[2]: v for k, v in attribute.items()})

    def ende(name):
        stand["tiefe"] -= 1
        bau.end(name.rpartition("}")[2])

    p.StartDoctypeDeclHandler = verboten
    p.EntityDeclHandler = verboten
    p.StartNamespaceDeclHandler = namensraum
    p.StartElementHandler = anfang
    p.EndElementHandler = ende
    p.CharacterDataHandler = bau.data
    try:
        p.Parse(daten, True)
        return stand["wurzel"], bau.close()
    except Unlesbar:
        raise
    except (expat.ExpatError, LookupError, ValueError) as e:
        raise Unlesbar("XML-Datei ist beschädigt oder unvollständig") from e


def _finde(el, *pfade):
    """Erstes Element unter einem der Pfade. Achtung: Elemente ohne Kinder sind „falsch“ → immer „is not None“."""
    if el is not None:
        for p in pfade:
            x = el.find(p)
            if x is not None:
                return x
    return None


def _alle(el, *pfade):
    if el is not None:
        for p in pfade:
            x = el.findall(p)
            if x:
                return x
    return []


def _text(el, *pfade, laenge=300):
    if el is not None:
        for p in pfade:
            x = el.find(p)
            t = re.sub(r"\s+", " ", (x.text or "")[:laenge * 4]).strip() if x is not None else ""
            if t:
                return t[:laenge]
    return None


def _zahl(el, *pfade):
    t = _text(el, *pfade, laenge=40)
    if not t or len(t) > 24 or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", t):
        return None         # auch kein NaN, kein 1e999, kein Komma
    z = float(Decimal(t))
    return z if abs(z) < 1e9 else None


def _datum(el, *pfade):
    t = _text(el, *pfade, laenge=40) or ""
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)", t) or re.fullmatch(r"(\d{4})(\d\d)(\d\d)(?:\d{4}(?:\d\d)?)?", t)
    if m:
        try:
            d = date(*(int(x) for x in m.groups()))
            if 1990 <= d.year <= date.today().year + 5:     # sonst landet der Beleg in einem unmöglichen EÜR-Jahr
                return d.isoformat()
        except ValueError:
            pass
    return None


def _in_waehrung(elemente, waehrung):
    """Steht der Steuerbetrag doppelt da (auch in der Abrechnungswährung), zählt der in der Rechnungswährung."""
    for x in elemente:
        if x.get("currencyID") == waehrung:
            return x
    return next((x for x in elemente if not x.get("currencyID")), None)


# ---------- UBL ----------

def _ubl_partei(p):
    anschrift = _finde(p, "PostalAddress")
    return {
        "name": _text(p, "PartyLegalEntity/RegistrationName", "PartyName/Name"),
        "handelsname": _text(p, "PartyName/Name"),
        "strasse": _text(anschrift, "StreetName"),
        "ort": " ".join(x for x in (_text(anschrift, "PostalZone"), _text(anschrift, "CityName")) if x) or None,
        "land": _text(anschrift, "Country/IdentificationCode"),
        "steuer_ids": [t for x in _alle(p, "PartyTaxScheme")[:5] if (t := _text(x, "CompanyID"))],
        "mails": [t for t in (_text(p, "Contact/ElectronicMail"), _text(p, "EndpointID")) if t and "@" in t],
    }


def _ubl(w, gutschrift):
    waehrung = _text(w, "DocumentCurrencyCode", laenge=3) or "EUR"
    summen = _finde(w, "LegalMonetaryTotal")
    steuer_el = _in_waehrung(_alle(w, "TaxTotal/TaxAmount"), waehrung)
    block = next((t for t in _alle(w, "TaxTotal") if steuer_el is not None and _finde(t, "TaxAmount") is steuer_el), None)
    art = _text(w, "CreditNoteTypeCode" if gutschrift else "InvoiceTypeCode", laenge=10)
    zeilen = _alle(w, "CreditNoteLine" if gutschrift else "InvoiceLine")
    posten = []
    for z in zeilen[:MAX_ZEILEN]:
        menge = _finde(z, "CreditedQuantity" if gutschrift else "InvoicedQuantity")
        posten.append({
            "name": _text(z, "Item/Name", "Item/Description", "Note"),
            "menge": _zahl(z, "CreditedQuantity" if gutschrift else "InvoicedQuantity"),
            "einheit": (menge.get("unitCode") or "")[:10] if menge is not None else "",
            "preis": _zahl(z, "Price/PriceAmount"), "je": _zahl(z, "Price/BaseQuantity"),
            "satz": _zahl(z, "Item/ClassifiedTaxCategory/Percent"),
            "summe": _zahl(z, "LineExtensionAmount"),
        })
    return {
        "syntax": "UBL", "profil": _text(w, "CustomizationID"),
        "nummer": _text(w, "ID", laenge=80), "datum": _datum(w, "IssueDate"),
        "faellig": _datum(w, "DueDate") or _datum(w, "PaymentMeans/PaymentDueDate"),
        "leistung": [_datum(w, "InvoicePeriod/StartDate") or _datum(w, "Delivery/ActualDeliveryDate"),
                     _datum(w, "InvoicePeriod/EndDate")],
        "waehrung": waehrung, "art": art, "gutschrift": gutschrift or art in GUTSCHRIFT_CODES,
        "verkaeufer": _ubl_partei(_finde(w, "AccountingSupplierParty/Party")),
        "kaeufer": _ubl_partei(_finde(w, "AccountingCustomerParty/Party")),
        "netto": _zahl(summen, "TaxExclusiveAmount"), "brutto": _zahl(summen, "TaxInclusiveAmount"),
        "angezahlt": _zahl(summen, "PrepaidAmount"), "rundung": _zahl(summen, "PayableRoundingAmount"),
        "zahlbar": _zahl(summen, "PayableAmount"),
        "nachlass": _zahl(summen, "AllowanceTotalAmount"), "zuschlag": _zahl(summen, "ChargeTotalAmount"),
        "steuer": _zahl(steuer_el, "."),
        "steuern": [{"satz": _zahl(s, "TaxCategory/Percent"), "basis": _zahl(s, "TaxableAmount"),
                     "betrag": _zahl(s, "TaxAmount"), "kategorie": _text(s, "TaxCategory/ID", laenge=5)}
                    for s in _alle(block, "TaxSubtotal")[:20]],
        "posten": posten, "posten_gesamt": len(zeilen),
        "iban": _text(w, "PaymentMeans/PayeeFinancialAccount/ID", laenge=40),
        "bedingung": _text(w, "PaymentTerms/Note", laenge=1000),
        "notizen": [t for n in _alle(w, "Note")[:10] if (t := _text(n, ".", laenge=2000))],
        "anlagen": [t for a in _alle(w, "AdditionalDocumentReference/Attachment/EmbeddedDocumentBinaryObject")[:20]
                    if (t := (a.get("filename") or "")[:120])],
    }


# ---------- CII (XRechnung CII, ZUGFeRD, Factur-X) ----------

def _cii_partei(p):
    anschrift = _finde(p, "PostalTradeAddress")
    return {
        "name": _text(p, "Name", "SpecifiedLegalOrganization/TradingBusinessName"),
        "handelsname": _text(p, "SpecifiedLegalOrganization/TradingBusinessName"),
        "strasse": _text(anschrift, "LineOne"),
        "ort": " ".join(x for x in (_text(anschrift, "PostcodeCode"), _text(anschrift, "CityName")) if x) or None,
        "land": _text(anschrift, "CountryID"),
        "steuer_ids": [t for x in _alle(p, "SpecifiedTaxRegistration")[:5] if (t := _text(x, "ID"))],
        "mails": [t for t in (_text(p, "DefinedTradeContact/EmailURIUniversalCommunication/URIID"),
                              _text(p, "URIUniversalCommunication/URIID")) if t and "@" in t],
    }


def _cii(w):
    # jeweils zuerst der Name seit ZUGFeRD 2, danach der aus ZUGFeRD 1.0
    kopf = _finde(w, "ExchangedDocument", "HeaderExchangedDocument")
    handel = _finde(w, "SupplyChainTradeTransaction", "SpecifiedSupplyChainTradeTransaction")
    vertrag = _finde(handel, "ApplicableHeaderTradeAgreement", "ApplicableSupplyChainTradeAgreement")
    lieferung = _finde(handel, "ApplicableHeaderTradeDelivery", "ApplicableSupplyChainTradeDelivery")
    abr = _finde(handel, "ApplicableHeaderTradeSettlement", "ApplicableSupplyChainTradeSettlement")
    summen = _finde(abr, "SpecifiedTradeSettlementHeaderMonetarySummation", "SpecifiedTradeSettlementMonetarySummation")
    waehrung = _text(abr, "InvoiceCurrencyCode", laenge=3) or "EUR"
    art = _text(kopf, "TypeCode", laenge=10)
    zeilen = _alle(handel, "IncludedSupplyChainTradeLineItem")
    posten = []
    for z in zeilen[:MAX_ZEILEN]:
        zv = _finde(z, "SpecifiedLineTradeAgreement", "SpecifiedSupplyChainTradeAgreement")
        zl = _finde(z, "SpecifiedLineTradeDelivery", "SpecifiedSupplyChainTradeDelivery")
        za = _finde(z, "SpecifiedLineTradeSettlement", "SpecifiedSupplyChainTradeSettlement")
        menge = _finde(zl, "BilledQuantity")
        posten.append({
            "name": _text(z, "SpecifiedTradeProduct/Name", "AssociatedDocumentLineDocument/IncludedNote/Content"),
            "menge": _zahl(zl, "BilledQuantity"),
            "einheit": (menge.get("unitCode") or "")[:10] if menge is not None else "",
            "preis": _zahl(zv, "NetPriceProductTradePrice/ChargeAmount"),
            "je": _zahl(zv, "NetPriceProductTradePrice/BasisQuantity"),
            "satz": _zahl(za, "ApplicableTradeTax/RateApplicablePercent", "ApplicableTradeTax/ApplicablePercent"),
            "summe": _zahl(za, "SpecifiedTradeSettlementLineMonetarySummation/LineTotalAmount",
                           "SpecifiedTradeSettlementMonetarySummation/LineTotalAmount"),
        })
    return {
        "syntax": "CII",
        "profil": _text(w, "ExchangedDocumentContext/GuidelineSpecifiedDocumentContextParameter/ID",
                        "SpecifiedExchangedDocumentContext/GuidelineSpecifiedDocumentContextParameter/ID"),
        "nummer": _text(kopf, "ID", laenge=80), "datum": _datum(kopf, "IssueDateTime/DateTimeString"),
        "faellig": _datum(abr, "SpecifiedTradePaymentTerms/DueDateDateTime/DateTimeString"),
        "leistung": [_datum(abr, "BillingSpecifiedPeriod/StartDateTime/DateTimeString")
                     or _datum(lieferung, "ActualDeliverySupplyChainEvent/OccurrenceDateTime/DateTimeString"),
                     _datum(abr, "BillingSpecifiedPeriod/EndDateTime/DateTimeString")],
        "waehrung": waehrung, "art": art, "gutschrift": art in GUTSCHRIFT_CODES,
        "verkaeufer": _cii_partei(_finde(vertrag, "SellerTradeParty")),
        "kaeufer": _cii_partei(_finde(vertrag, "BuyerTradeParty")),
        "netto": _zahl(summen, "TaxBasisTotalAmount"), "brutto": _zahl(summen, "GrandTotalAmount"),
        "angezahlt": _zahl(summen, "TotalPrepaidAmount"), "rundung": _zahl(summen, "RoundingAmount"),
        "zahlbar": _zahl(summen, "DuePayableAmount"),
        "nachlass": _zahl(summen, "AllowanceTotalAmount"), "zuschlag": _zahl(summen, "ChargeTotalAmount"),
        "steuer": _zahl(_in_waehrung(_alle(summen, "TaxTotalAmount"), waehrung), "."),
        "steuern": [{"satz": _zahl(s, "RateApplicablePercent", "ApplicablePercent"), "basis": _zahl(s, "BasisAmount"),
                     "betrag": _zahl(s, "CalculatedAmount"), "kategorie": _text(s, "CategoryCode", laenge=5)}
                    for s in _alle(abr, "ApplicableTradeTax")[:20]],
        "posten": posten, "posten_gesamt": len(zeilen),
        "iban": _text(abr, "SpecifiedTradeSettlementPaymentMeans/PayeePartyCreditorFinancialAccount/IBANID", laenge=40),
        "bedingung": _text(abr, "SpecifiedTradePaymentTerms/Description", laenge=1000),
        "notizen": [t for n in _alle(kopf, "IncludedNote/Content")[:10] if (t := _text(n, ".", laenge=2000))],
        "anlagen": [t for a in _alle(vertrag, "AdditionalReferencedDocument/AttachmentBinaryObject")[:20]
                    if (t := (a.get("filename") or "")[:120])],
    }


def lesen(daten):
    """XML → dict mit allen Angaben der Rechnung. Wirft KeineRechnung bzw. Unlesbar."""
    ns, w = _baum(daten)
    wurzel = (ns, w.tag)
    if wurzel in (UBL_RECHNUNG, UBL_GUTSCHRIFT):
        r = _ubl(w, wurzel == UBL_GUTSCHRIFT)
    elif wurzel in (CII, ZUGFERD_1):
        r = _cii(w)
    else:
        raise KeineRechnung("XML, aber keine E-Rechnung (XRechnung, ZUGFeRD)")
    if not r["nummer"] and r["brutto"] is None and r["zahlbar"] is None:
        raise Unlesbar("E-Rechnung ohne Nummer und Betrag – vermutlich unvollständig")
    if r["brutto"] is None:
        if r["netto"] is not None and r["steuer"] is not None:
            r["brutto"] = round(r["netto"] + r["steuer"], 2)
        elif r["zahlbar"] is not None and not r["angezahlt"]:
            r["brutto"] = r["zahlbar"]
    profil = (r["profil"] or "").lower()
    r["format"] = ("XRechnung" if "xrechnung" in profil
                   else "ZUGFeRD/Factur-X" if re.search(r"factur-x|zugferd|ferd:", profil) or wurzel == ZUGFERD_1
                   else f"E-Rechnung ({r['syntax']})")
    return r


# ---------- in PDFs eingebettet ----------

def _aufloesen(x):
    return x.get_object() if x is not None and hasattr(x, "get_object") else x


def _entpacken(strom):
    roh = getattr(strom, "_data", None)     # absichtlich nicht get_data(): pypdf entpackt unbegrenzt
    if not isinstance(roh, bytes):
        return None
    f = _aufloesen(strom.get("/Filter"))
    filter_ = [str(_aufloesen(x)) for x in f] if isinstance(f, list) else [str(f)] if f else []
    if not filter_:
        return roh if len(roh) <= MAX_BYTES else None
    if filter_ != ["/FlateDecode"]:
        return None
    try:
        aus = zlib.decompressobj().decompress(roh, MAX_BYTES + 1)
    except zlib.error:
        return None
    return aus if len(aus) <= MAX_BYTES else None


def pdf_anhaenge(daten, leser=None):
    """Eingebettete XML-Dateien → [(name, bytes)], bekannte Namen zuerst. Eigener Durchlauf: findet auch /AF und
    entpackt begrenzt. Öffnet das PDF selbst – deshalb nur im Kindprozess von pdflesen aufrufen."""
    try:
        if leser is None:
            from pypdf import PdfReader
            leser = PdfReader(io.BytesIO(daten))
        katalog = _aufloesen(leser.trailer["/Root"])
        specs = []
        namen = _aufloesen(katalog.get("/Names"))
        offen = [namen.get("/EmbeddedFiles")] if namen else []
        for _ in range(1000):
            if not offen:
                break
            knoten = _aufloesen(offen.pop())
            if not isinstance(knoten, dict):
                continue
            paare = _aufloesen(knoten.get("/Names")) or []
            specs += list(paare[1::2])[:200]
            offen += list(_aufloesen(knoten.get("/Kids")) or [])[:200]
        specs += list(_aufloesen(katalog.get("/AF")) or [])[:200]
        funde = {}
        for spec in specs[:1000]:
            s = _aufloesen(spec)
            if not isinstance(s, dict):
                continue
            name = str(_aufloesen(s.get("/UF")) or _aufloesen(s.get("/F")) or "")
            ef = _aufloesen(s.get("/EF"))
            if name.lower().endswith(".xml") and isinstance(ef, dict):
                funde.setdefault(name, ef.get("/F") or ef.get("/UF"))
        aus, gesamt = [], 0
        for name in sorted(funde, key=lambda n: n.lower() not in BEKANNTE_NAMEN)[:MAX_ANHAENGE]:
            inhalt = _entpacken(_aufloesen(funde[name]))
            if inhalt is not None:
                gesamt += len(inhalt)
                if gesamt > MAX_BYTES:      # zusammen, nicht nur je Anhang
                    break
                aus.append((name, inhalt))
        return aus
    except MemoryError:
        raise
    except Exception:       # kaputtes oder verschlüsseltes PDF: dann eben ohne E-Rechnung
        return []


def suchen(teile, aus_pdf=pdf_anhaenge):
    """[(name, bytes)] (XML oder PDF) → (verschiedene Rechnungen, Probleme). Doppelt Mitgeschicktes zählt einmal."""
    def kandidaten():       # nacheinander, damit nie alle entpackten Anhänge zugleich im Speicher liegen
        for name, daten in teile:
            if daten[:5] == b"%PDF-":
                yield from aus_pdf(daten)
            elif ist_xml(name, daten):
                yield name, daten

    funde, probleme = {}, []
    for i, (name, daten) in enumerate(kandidaten()):
        if i >= MAX_ANHAENGE:
            probleme.append(f"nur die ersten {MAX_ANHAENGE} XML-Anhänge gelesen")
            break
        try:
            r = lesen(daten)
        except KeineRechnung:
            continue        # z. B. andere Anhänge, DMARC-Berichte
        except Unlesbar as e:
            probleme.append(f"{name[:80]}: {e}")
            continue
        schluessel = (r["nummer"], r["datum"], (r["verkaeufer"]["name"] or "").lower())
        funde.setdefault(schluessel, r)
    return list(funde.values()), probleme


# ---------- Vorschläge für die Ausgabe ----------

def ausgabe_betrag(r):
    """Bruttobetrag als Ausgabe in Euro; Gutschriften negativ. Fremdwährung → None."""
    if r["brutto"] is None or r["waehrung"] != "EUR":
        return None
    return round(-abs(r["brutto"]) if r["gutschrift"] else r["brutto"], 2)


def ust_satz(r):
    """Nur, wenn ein einziger Satz für den ganzen Betrag gilt – die EÜR rechnet die Vorsteuer aus dem Brutto."""
    saetze = {s["satz"] for s in r["steuern"] if s["satz"]}
    if len(saetze) != 1 or r["brutto"] is None or r["steuer"] is None or r["waehrung"] != "EUR":
        return None
    satz = saetze.pop()
    if satz not in (7.0, 19.0):
        return None
    passt = abs(abs(r["steuer"]) - abs(r["brutto"]) * satz / (100 + satz)) <= 0.05
    return satz if passt else None


def beschreibung(r):
    erster = next((p["name"] for p in r["posten"] if p["name"]), "")
    if len(erster) > 70:
        erster = erster[:69] + "…"
    if erster and r["posten_gesamt"] > 1:
        erster += " u. a."
    nr = f"Nr. {r['nummer'][:40]}" if r["nummer"] else ""
    return " · ".join(x for x in (erster, nr) if x) or None


def kurz(r):
    """Was bei der Ausgabe gespeichert wird – die Lesefassung liest immer das Original."""
    v = r["verkaeufer"]
    return {"format": r["format"], "nummer": r["nummer"], "datum": r["datum"], "waehrung": r["waehrung"],
            "brutto": r["brutto"], "gutschrift": r["gutschrift"], "verkaeufer": v["name"],
            "steuer_ids": v["steuer_ids"], "mails": v["mails"],
            "steuer_gemischt": bool(r["steuer"]) and ust_satz(r) is None and r["waehrung"] == "EUR"}


def hinweise(r):
    h = []
    if r["gutschrift"]:
        h.append("Gutschrift – als negativer Betrag vorgeschlagen, sie mindert deine Ausgaben. "
                 "Als „Bezahlt am“ bitte den Tag der Erstattung eintragen.")
    if r["waehrung"] != "EUR":
        betrag = f" ({geld(r['brutto'], r['waehrung'])})" if r["brutto"] is not None else ""
        h.append(f"Fremdwährung{betrag} – bitte den tatsächlich abgebuchten Euro-Betrag eintragen")
    elif r["brutto"] is None:
        h.append("Die E-Rechnung nennt keinen Gesamtbetrag – bitte eintragen")
    if not r["datum"]:
        h.append("Die E-Rechnung nennt kein gültiges Datum – bitte eintragen")
    if r["waehrung"] == "EUR" and (r["angezahlt"] or 0) > 0 and (r["zahlbar"] or 0) > 0:
        h.append(f"{geld(r['angezahlt'], r['waehrung'])} sind schon angezahlt, vorgeschlagen ist der ganze Betrag. "
                 f"Ist die Anzahlung schon als Ausgabe erfasst, hier nur {geld(r['zahlbar'], r['waehrung'])} eintragen.")
    if None not in (r["brutto"], r["netto"], r["steuer"]) and abs(r["netto"] + r["steuer"] - r["brutto"]) > 0.02:
        h.append("Netto und Umsatzsteuer ergeben in der E-Rechnung nicht den Gesamtbetrag – bitte genau prüfen")
    if any(s["kategorie"] in ("AE", "K") for s in r["steuern"]):
        h.append("Rechnung ohne Umsatzsteuer, die Steuer schuldet womöglich der Empfänger (§ 13b UStG bzw. "
                 "innergemeinschaftlicher Erwerb) – das kann auch Kleinunternehmer treffen, bitte mit dem Steuerberater klären")
    return h


# ---------- Lesefassung ----------

def geld(wert, waehrung="EUR"):
    if wert is None:
        return ""
    z = f"{wert:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{z} {'€' if waehrung == 'EUR' else waehrung}"


def _menge(wert):
    return "" if wert is None else f"{wert:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def _de(iso):
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}" if iso else ""


def lesefassung(r):
    """HTML-Abschnitt ohne Skripte und Links; jeder Wert aus der Datei ist maskiert."""
    e = lambda x: html.escape(str(x if x is not None else ""))
    w = r["waehrung"]
    rechts = "text-align:right;white-space:nowrap;padding:5px 6px"
    links = "text-align:left;padding:5px 6px"

    def partei(titel, p):
        zeilen = [p["strasse"], p["ort"], p["land"], *p["steuer_ids"]]
        return (f"<td style='vertical-align:top;width:50%;padding:0 8px 12px 0'><div style='color:#666'>{titel}</div>"
                f"<b>{e(p['name'])}</b>{''.join(f'<br>{e(z)}' for z in zeilen if z)}</td>")

    def summe(titel, wert, fett=False):
        if wert is None:
            return ""
        t, z = e(titel), e(geld(wert, w))
        if fett:
            t, z = f"<b>{t}</b>", f"<b>{z}</b>"
        return f"<tr><td style='{links}'>{t}</td><td style='{rechts}'>{z}</td></tr>"

    posten = ""
    for p in r["posten"]:
        je = f" / {_menge(p['je'])}" if p["je"] and p["je"] != 1 else ""
        menge = f"{_menge(p['menge'])} {EINHEITEN.get(p['einheit'], p['einheit'])}"
        satz = f"{_menge(p['satz'])} %" if p["satz"] is not None else ""
        posten += (f"<tr style='border-top:1px solid #e5e5e5'><td style='{links};word-break:break-word'>{e(p['name'])}</td>"
                   f"<td style='{rechts}'>{e(menge)}</td><td style='{rechts}'>{e(geld(p['preis'], w) + je)}</td>"
                   f"<td style='{rechts}'>{e(satz)}</td><td style='{rechts}'>{e(geld(p['summe'], w))}</td></tr>")
    if posten:
        posten = (f"<table style='width:100%;border-collapse:collapse;margin:6px 0 12px'><tr style='color:#666'>"
                  f"<td style='{links}'>Position</td><td style='{rechts}'>Menge</td><td style='{rechts}'>Preis netto</td>"
                  f"<td style='{rechts}'>USt</td><td style='{rechts}'>Summe</td></tr>{posten}</table>")
        if r["posten_gesamt"] > len(r["posten"]):
            posten += f"<p>… und {r['posten_gesamt'] - len(r['posten'])} weitere Positionen (im Original)</p>"
    else:
        posten = "<p style='color:#666'>Die E-Rechnung enthält keine Positionen.</p>"

    steuern = ""
    for s in r["steuern"]:
        titel = f"Umsatzsteuer {_menge(s['satz'])} %" if s["satz"] is not None else "Umsatzsteuer"
        if s["basis"] is not None:
            titel += f" auf {geld(s['basis'], w)}"
        steuern += summe(titel, s["betrag"])
    summen = (summe("Nachlässe", -r["nachlass"] if r["nachlass"] else None) + summe("Zuschläge", r["zuschlag"] or None)
              + summe("Netto", r["netto"]) + (steuern or summe("Umsatzsteuer", r["steuer"]))
              + summe("Gesamt brutto", r["brutto"], True)
              + summe("Schon gezahlt", -r["angezahlt"] if r["angezahlt"] else None)
              + summe("Rundung", r["rundung"] or None) + summe("Zu zahlen", r["zahlbar"], True))

    von, bis = r["leistung"]
    kopf = [("Datum", _de(r["datum"])), ("Fällig", _de(r["faellig"])),
            ("Leistung", f"{_de(von)} – {_de(bis)}" if von and bis and von != bis else _de(von or bis))]
    fuss = [("IBAN", r["iban"]), ("Zahlung", r["bedingung"]), *(("Hinweis", n) for n in r["notizen"]),
            ("Anlagen in der Datei", ", ".join(r["anlagen"]))]
    return (
        "<div style='font:13px/1.45 Arial,sans-serif;color:#111'>"
        f"<div style='color:#666'>Lesefassung · {e(r['format'])} · maßgeblich ist die XML-Datei</div>"
        f"<h1 style='font-size:19px;margin:6px 0;word-break:break-word'>{'Gutschrift' if r['gutschrift'] else 'Rechnung'} {e(r['nummer'])}</h1>"
        f"<p style='margin:0 0 12px'>{' · '.join(f'{t}: {e(v)}' for t, v in kopf if v)}</p>"
        f"<table style='width:100%;border-collapse:collapse'><tr>{partei('Verkäufer', r['verkaeufer'])}"
        f"{partei('Käufer', r['kaeufer'])}</tr></table>"
        f"{posten}<table style='margin-left:auto;border-collapse:collapse'>{summen}</table>"
        + "".join(f"<p style='margin:8px 0;word-break:break-word'><span style='color:#666'>{t}:</span> {e(v)}</p>"
                  for t, v in fuss if v)
        + "</div>")

"""Belege auslesen: PDF-Rechnungen, E-Rechnungen, Kauf-Mails (.eml/.msg) und Fotos.

Liefert Vorschläge für eine Ausgabe – Lieferant, Datum, Gesamtbetrag, Umsatzsteuer, Beschreibung, Kategorie –
die der Nutzer in der App bestätigt. Für die häufigsten Musik-Shops gibt es eigene Regeln (deren Mails sind immer
gleich aufgebaut), sonst eine allgemeine Suche nach „Gesamt“, „Summe“, „Total“ …
"""
import email
import hashlib
import html
import re
import unicodedata
from datetime import date, datetime, timedelta
from email import policy
from email.utils import parsedate_to_datetime, parseaddr

import erechnung

# ---------- Beträge ----------

# 1.234,56 · 1,29 · 5.33 · 1,234.56 · 960,- · 12
_ZAHL = r"\d{1,3}(?:[.,  ]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?|\d+,-"
BETRAG = re.compile(
    rf"(?:(?:EUR|€)\s*(?P<v>{_ZAHL})|(?P<n>{_ZAHL})\s*(?:EUR|€|Euro)(?![a-z]))", re.I)


def zahl(text):
    """„1.234,56“ / „1,234.56“ / „5.33“ / „1,29“ / „960,-“ → float."""
    t = text.strip().replace(" ", "").replace(" ", "").replace(",-", "")
    if re.fullmatch(r"\d+", t):
        return float(t)
    komma, punkt = t.rfind(","), t.rfind(".")
    if komma > punkt:          # deutsches Format: Punkt = Tausender, Komma = Dezimal
        t = t.replace(".", "").replace(",", ".")
    else:                      # englisches Format: Komma = Tausender
        t = t.replace(",", "")
    return float(t)


def betraege(text):
    """Alle Euro-Beträge in einem Text, in Reihenfolge."""
    out = []
    for m in BETRAG.finditer(text):
        try:
            out.append(zahl(m.group("v") or m.group("n")))
        except ValueError:
            continue
    return out


# Betrag ohne Währungszeichen, aber mit genau zwei Nachkommastellen (1.234,56 · 788,48 · 788.48)
ZAHL_OHNE = re.compile(r"(?<![\d.,])(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?![\d,])|(?<![\d.,])\d+\.\d{2}(?![\d.])")
WAEHRUNG = re.compile(r"(?i)(?<![a-z])(?:eur|euro)(?![a-z])|€")


def zahlen_ohne_waehrung(text):
    out = []
    for m in ZAHL_OHNE.finditer(text):
        try:
            out.append(zahl(m.group(0)))
        except ValueError:
            continue
    return out


def _betrag_nach(zeilen, i, umfang=3, mit_stelle=False):
    """Erster Euro-Betrag in Zeile i oder den folgenden Zeilen (optional mit der Fundstelle als Text).
    Steht die Währung nur in der Beschriftung (z. B. „Total EUR inkl. MwSt.  788,48“), zählen auch Zahlen ohne €:
    in derselben Zeile die letzte, in den folgenden Zeilen die erste."""
    ohne = bool(WAEHRUNG.search(zeilen[i]))
    for j, z in enumerate(zeilen[i:i + umfang]):
        b = betraege(z)
        if not b and ohne:
            nackt = zahlen_ohne_waehrung(z)
            b = nackt[-1:] if j == 0 else nackt[:1]
        if b:
            stelle = zeilen[i] if j == 0 else f"{zeilen[i]} … {z}"
            return (b[0], stelle) if mit_stelle else b[0]
    return (None, None) if mit_stelle else None


GESAMT_WOERTER = [r"gesamtbetrag", r"gesamtsumme", r"rechnungsbetrag", r"zu zahlen(?:der betrag)?", r"endbetrag",
                  r"zahlbetrag", r"bruttobetrag", r"gesamt(?:preis)?", r"summe", r"order total", r"grand total", r"total"]
STEUER_WOERTER = r"(?:mwst\.?|mehrwertsteuer|ust\.?|umsatzsteuer|vat|erhobene steuer|steuer|tax)"


def gesamt_vorschlag(zeilen):
    """Gesamtbetrag: erstes Schlüsselwort nach Priorität (z. B. „Gesamtsumme“ vor „Summe“); sonst höchster Betrag.
    Zeilen mit „Zwischensumme“, „vor Steuern“, „netto“ werden übersprungen."""
    # Vorrang: ausdrücklich Bruttobetrag („Total EUR inkl. MwSt.“, „Gesamt brutto“) – sonst greift „Gesamt“
    # womöglich in der Steuertabelle den Nettobetrag ab
    brutto = re.compile(r"(?i)(?:gesamt|summe|total|betrag|zu zahlen).*(?:inkl|incl|brutto)|(?:inkl|incl|brutto).*(?:gesamt|summe|total)")
    for i, z in enumerate(zeilen):
        if brutto.search(z) and not re.search(r"(?i)zwischen|sub\s*total|subtotal|einzelpreis", z):
            b, stelle = _betrag_nach(zeilen, i, umfang=2, mit_stelle=True)
            if b is not None:
                return b, stelle[:80]
    for wort in GESAMT_WOERTER:
        muster = re.compile(rf"(?<![a-zäöü]){wort}(?![a-zäöü])", re.I)
        for i, z in enumerate(zeilen):
            if muster.search(z) and not re.search(r"(?i)zwischen|sub\s*total|subtotal|vor steuern|netto|ohne", z):
                b, stelle = _betrag_nach(zeilen, i, mit_stelle=True)
                if b is not None:
                    return b, stelle[:80]
    alle = [b for z in zeilen for b in betraege(z)]
    return (max(alle), "höchster Betrag im Beleg") if alle else (None, None)


def steuer_vorschlag(zeilen, gesamt=None):
    """Umsatzsteuer: (Satz in %, Betrag) – Satz aus „19 %“, sonst aus Verhältnis Steuer/Gesamt geschätzt."""
    # Steuertabelle ohne Währungszeichen: „19 %   662,59   125,89“ (Satz, Netto, Steuer) – passt die Steuer zum Gesamtbetrag?
    if gesamt:
        for z in zeilen:
            m = re.match(r"\s*(19|7)(?:[.,]0+)?\s*%", z)
            nackt = zahlen_ohne_waehrung(z[m.end():]) if m else []
            if m and nackt:
                satz, steuer = float(m.group(1)), nackt[-1]
                if abs(steuer - gesamt * satz / (100 + satz)) <= 0.05:
                    return satz, steuer
    for i, z in enumerate(zeilen):
        if re.search(rf"(?i)(?<![a-zäöü]){STEUER_WOERTER}(?![a-zäöü])", z) and not re.search(r"(?i)ust-?id|vat id|steuernummer", z):
            satz = re.search(r"(\d{1,2})(?:[.,]\d+)?\s*%", z)
            betrag = _betrag_nach(zeilen, i, 2)
            if betrag is None:
                continue
            if satz:
                return float(satz.group(1)), betrag
            if gesamt:
                anteil = betrag / max(gesamt - betrag, 0.01) * 100
                for s in (19.0, 7.0):
                    if abs(anteil - s) < 1.0:
                        return s, betrag
            return None, betrag
    return None, None


# ---------- Datum ----------

DATUM_KURZ = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{2})(?![\d.])")   # Kassenbons: 02.07.26
DATUM_DE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
DATUM_US = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
DATUM_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def datum_vorschlag(zeilen):
    """Rechnungsdatum (bevorzugt neben „Rechnungsdatum“/„Datum“), sonst erstes Datum im Text → ISO."""
    def iso(z):
        for muster, reihenfolge in ((DATUM_ISO, "ymd"), (DATUM_DE, "dmy"), (DATUM_US, "mdy")):
            m = muster.search(z)
            if m:
                a, b, c = (int(x) for x in m.groups())
                y, mo, d = {"ymd": (a, b, c), "dmy": (c, b, a), "mdy": (c, a, b)}[reihenfolge]
                try:
                    return datetime(y, mo, d).date().isoformat()
                except ValueError:
                    continue
        return None
    for i, z in enumerate(zeilen):
        if re.search(r"(?i)rechnungsdatum|belegdatum|datum|date", z):
            for zz in zeilen[i:i + 2]:
                d = iso(zz)
                if d:
                    return d
    for z in zeilen:
        d = iso(z)
        if d:
            return d
    for z in zeilen:        # zweistellige Jahre nur, wenn es kein vollständiges Datum gibt
        for m in DATUM_KURZ.finditer(z):
            t, mo, j = (int(x) for x in m.groups())
            if 15 <= j <= date.today().year % 100 + 1:
                try:
                    return date(2000 + j, mo, t).isoformat()
                except ValueError:
                    continue
    return None


# ---------- Shops ----------

# Absender-Domain → (Name, Kategorie). Für diese Shops gibt es eigene Regeln bzw. sie sind sicher Musik.
SHOPS = {
    "apple.com": ("Apple", "musik"), "itunes.com": ("Apple", "musik"),
    "amazon.de": ("Amazon", None), "amazon.com": ("Amazon", None),
    "beatport.com": ("Beatport", "musik"), "qobuz.com": ("Qobuz", "musik"),
    "bandcamp.com": ("Bandcamp", "musik"), "traxsource.com": ("Traxsource", "musik"),
    "junodownload.com": ("Juno Download", "musik"), "7digital.com": ("7digital", "musik"),
}
MUSIK_HINWEIS = re.compile(r"(?i)musik|music|track|album|song|mp3|aiff|wav|flac|titel")


def shop_aus_absender(absender):
    m = re.search(r"@([\w.-]+)", absender or "")
    if not m:
        return None
    domain = m.group(1).lower()
    for d, info in SHOPS.items():
        if domain == d or domain.endswith("." + d):
            return info
    return None


# ---------- Text aus Belegen ----------

def html_zu_text(roh):
    roh = re.sub(r"(?is)<(style|script|head)[^>]*>.*?</\1>", " ", roh)
    roh = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|table)>", "\n", roh)
    roh = re.sub(r"(?i)</t[dh]>", "\n", roh)
    text = html.unescape(re.sub(r"<[^>]+>", " ", roh))
    return text


def zeilen_aus(text):
    zeilen = []
    for z in text.replace("\r", "").split("\n"):
        z = re.sub(r"[ \t ‌​͏]+", " ", z).strip()
        if z:
            zeilen.append(z)
    return zeilen


def pdf_text(daten):
    from pypdf import PdfReader
    import io
    seiten = []
    for seite in PdfReader(io.BytesIO(daten)).pages:
        try:
            seiten.append(seite.extract_text() or "")
        except Exception:
            continue
    return "\n".join(seiten)


def mail_lesen(daten):
    """.eml → dict(absender, betreff, datum, message_id, text, html, anhaenge=[(name, typ, bytes)])."""
    msg = email.message_from_bytes(daten, policy=policy.default)
    text_teil = msg.get_body(preferencelist=("plain",))
    html_teil = msg.get_body(preferencelist=("html",))
    anhaenge = []
    for teil in msg.iter_attachments():
        name = teil.get_filename()
        if name:
            anhaenge.append((name, teil.get_content_type(), teil.get_payload(decode=True) or b""))
    try:
        datum = parsedate_to_datetime(msg["Date"]).astimezone().date().isoformat() if msg["Date"] else None
    except (TypeError, ValueError):
        datum = None
    return {"absender": str(msg["From"] or ""), "betreff": str(msg["Subject"] or "").strip(), "datum": datum,
            "message_id": str(msg["Message-ID"] or "").strip() or None,
            "text": text_teil.get_content() if text_teil else "",
            "html": html_teil.get_content() if html_teil else ""}, anhaenge


def mail_teile(daten):
    """PDF- und XML-Teile einer Mail → [(name, bytes)] – auch ohne Dateinamen, in weitergeleiteten Mails oder wenn
    die Mail nur aus der Datei besteht (das alles übersieht iter_attachments)."""
    aus = []
    for teil in email.message_from_bytes(daten, policy=policy.default).walk():
        if teil.is_multipart():
            continue
        roh = teil.get_payload(decode=True) or b""
        name = teil.get_filename() or ("anhang.xml" if teil.get_content_type() in ("application/xml", "text/xml") else "")
        if roh[:5] == b"%PDF-" or erechnung.ist_xml(name, roh):
            aus.append((name or "Anhang", roh))
    return aus[:50]


def erechnungen(typ, daten):
    """E-Rechnungen in einem Beleg → (Rechnungen, Probleme)."""
    try:
        if typ == "xml":
            return [erechnung.lesen(daten)], []
        if typ == "pdf":
            return erechnung.suchen([("Beleg.pdf", daten)])
        if typ == "mail":
            return erechnung.suchen(mail_teile(daten))
        if typ == "msg":
            return erechnung.suchen([(n, d) for n, _, d in msg_lesen(daten)[1]])
    except erechnung.Unlesbar as e:
        return [], [str(e)]
    except Exception:       # kaputte Mail: meldet die normale Auswertung
        pass
    return [], []


def ist_mbox(name, daten):
    """Postfach-Export (Apple Mail „Postfach exportieren“, Thunderbird …): viele Mails in einer Datei."""
    n = (name or "").lower().rsplit("/", 1)[-1]
    return daten[:5] == b"From " and (n.endswith(".mbox") or n == "mbox" or daten.count(b"\nFrom ") > 0)


def mbox_aufteilen(daten):
    """mbox → [(dateiname, bytes)] je Mail. Trenner ist eine „From “-Zeile am Anfang oder nach einer Leerzeile."""
    daten = daten.replace(b"\r\n", b"\n")
    teile = re.split(rb"(?:\A|\n\n)From [^\n]*\n", daten)
    mails = []
    for teil in teile:
        if not teil.strip():
            continue
        teil = re.sub(rb"(?m)^>(>*From )", rb"\1", teil)          # mboxrd: „>From “ im Text zurückwandeln
        kopf = email.message_from_bytes(teil.split(b"\n\n", 1)[0] + b"\n\n", policy=policy.default)
        betreff = re.sub(r"[^\w äöüÄÖÜß.,()+-]+", " ", str(kopf["Subject"] or ""))[:60].strip(" ,.(-") or "Mail"
        mails.append((f"{betreff} ({len(mails) + 1}).eml", teil))
    return mails


def msg_lesen(daten):
    """Outlook-.msg → wie mail_lesen (benötigt das Paket extract-msg)."""
    import extract_msg
    m = extract_msg.openMsg(daten)
    try:
        anhaenge = [(a.longFilename or a.shortFilename or "Anhang", a.mimetype or "", a.data or b"")
                    for a in m.attachments if getattr(a, "data", None) and isinstance(a.data, bytes)]
        datum = m.date.astimezone().date().isoformat() if getattr(m, "date", None) else None
        body_html = m.htmlBody.decode("utf-8", "replace") if isinstance(m.htmlBody, bytes) else (m.htmlBody or "")
        return {"absender": m.sender or "", "betreff": (m.subject or "").strip(), "datum": datum,
                "message_id": (m.messageId or "").strip() or None, "text": m.body or "", "html": body_html}, anhaenge
    finally:
        m.close()


# ---------- Auswertung ----------

def pruefsumme(daten):
    return hashlib.sha256(daten).hexdigest()


def typ_von(name, daten):
    n = (name or "").lower()
    if daten[:5] == b"%PDF-" or n.endswith(".pdf"):
        return "pdf"
    if erechnung.ist_xml(name, daten):
        return "xml"
    if n.endswith(".eml") or (b"\nFrom:" in daten[:4000] and b"\nSubject:" in daten[:8000]) or daten[:5] in (b"From:", b"Recei", b"Retur", b"Deliv"):
        return "mail"
    if n.endswith(".msg") or daten[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "msg"
    if n.endswith((".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp")) or daten[:3] == b"\xff\xd8\xff" or daten[:8] == b"\x89PNG\r\n\x1a\n":
        return "bild"
    return "unbekannt"


def auswerten(name, daten):
    """Beleg auswerten → dict mit Vorschlägen (Werte können None sein) und Fundstellen zum Anzeigen."""
    typ = typ_von(name, daten)
    v = {"typ": typ, "lieferant": None, "belegdatum": None, "betrag": None, "ust_satz": None, "ust_betrag": None,
         "beschreibung": None, "kategorie": None, "message_id": None, "fundstellen": {}, "hinweise": []}
    if typ == "bild":
        v["hinweise"].append("Foto – bitte Betrag eintragen")
        return v
    if typ == "unbekannt":
        v["hinweise"].append("Dateityp nicht erkannt – bitte Werte eintragen")
        return v
    rechnungen, probleme = erechnungen(typ, daten)
    v["hinweise"] += [f"E-Rechnung nicht lesbar ({p}) – bitte Werte prüfen" for p in probleme]
    if typ == "xml":
        if rechnungen:
            _aus_erechnung(v, rechnungen)
        return v

    if typ == "pdf":
        try:
            text = pdf_text(daten)
        except Exception:
            text = ""
        if rechnungen:
            _aus_erechnung(v, rechnungen)
            # Die eingebettete XML sieht man nicht – weicht sie vom sichtbaren PDF ab, muss das auffallen
            if len(rechnungen) == 1 and v["betrag"] and (BETRAG.search(text) or ZAHL_OHNE.search(text)) and not _betrag_im_text(v["betrag"], text):
                v["hinweise"].append("Der Betrag aus der eingebetteten E-Rechnung steht so nicht im sichtbaren PDF – bitte vergleichen")
            return v
        if not text.strip():
            v["hinweise"].append("PDF ohne Text (Scan) – bitte Betrag eintragen")
            return v
        zeilen = zeilen_aus(text)
        v["lieferant"] = _lieferant_aus_pdf(zeilen)
    else:
        try:
            mail, anhaenge = mail_lesen(daten) if typ == "mail" else msg_lesen(daten)
        except Exception:
            v["hinweise"].append("Mail konnte nicht gelesen werden – im Mailprogramm als .eml speichern oder Werte eintragen")
            return v
        v["message_id"] = mail["message_id"]
        v["belegdatum"] = mail["datum"]
        shop = shop_aus_absender(mail["absender"])
        if not shop:
            v["absender_adresse"] = parseaddr(mail["absender"] or "")[1]
        v["lieferant"] = shop[0] if shop else _anzeigename(mail["absender"])
        v["kategorie"] = shop[1] if shop else None
        v["beschreibung"] = mail["betreff"][:120] or None
        if rechnungen:
            _aus_erechnung(v, rechnungen, shop)
            return v
        # Angehängte PDF-Rechnung hat Vorrang vor dem Mailtext
        pdf_anhang = next((d for n, t, d in anhaenge if d[:5] == b"%PDF-"), None)
        text = ""
        if pdf_anhang:
            try:
                text = pdf_text(pdf_anhang)
            except Exception:
                text = ""
            if text.strip():
                v["hinweise"].append("Werte aus der angehängten PDF-Rechnung")
        if not text.strip():
            text = mail["text"] if mail["text"].strip() and BETRAG.search(mail["text"]) else html_zu_text(mail["html"])
        zeilen = zeilen_aus(text)
        if shop and shop[0] == "Amazon":
            v["hinweise"].append("Amazon-Bestellbestätigung – die Rechnung gibt es im Amazon-Konto unter Bestellungen. "
                                 "Für Kleinunternehmer reicht die Mail meist als Nachweis.")
            if MUSIK_HINWEIS.search(" ".join(zeilen)):
                v["kategorie"] = "musik"
        if shop and shop[1] == "musik":
            n = _anzahl_titel(shop[0], zeilen)
            if n:
                v["beschreibung"] = f"{n} Titel" + (f" ({_format(zeilen)})" if _format(zeilen) else "")

    betrag, fundstelle = gesamt_vorschlag(zeilen)
    v["betrag"], v["fundstellen"]["betrag"] = betrag, fundstelle
    v["ust_satz"], v["ust_betrag"] = steuer_vorschlag(zeilen, betrag)
    if not v["belegdatum"]:
        v["belegdatum"] = datum_vorschlag(zeilen)
    if re.search(r"\$|USD|£|GBP|CHF", " ".join(zeilen)) and not re.search(r"€|EUR", " ".join(zeilen)):
        v["hinweise"].append("Fremdwährung – bitte den tatsächlich abgebuchten Euro-Betrag eintragen")
    if betrag is None:
        v["hinweise"].append("Gesamtbetrag nicht gefunden – bitte eintragen")
    return v


def _aus_erechnung(v, rechnungen, shop=None):
    """Werte aus der E-Rechnung statt aus dem Text. Bei Mails bleibt der Name bekannter Shops (Gruppierung, Kategorie)."""
    r = rechnungen[0]
    verkaeufer = {x["verkaeufer"]["name"] for x in rechnungen}
    v["erechnung"] = erechnung.kurz(r)
    if len(verkaeufer) == 1 and r["verkaeufer"]["name"]:
        v.pop("absender_adresse", None)     # der Verkäufer zählt, nicht wer die Mail weitergeleitet hat
        if not shop:
            v["lieferant"] = r["verkaeufer"]["name"][:80]
    if len(rechnungen) > 1:
        v["erechnung"]["mehrere"] = len(rechnungen)
        v["hinweise"].append(f"{len(rechnungen)} verschiedene E-Rechnungen in einer Datei – bitte die Anhänge einzeln "
                             "hochladen und diesen Beleg verwerfen, oder die Summe von Hand eintragen")
        return
    v["belegdatum"] = r["datum"] or v["belegdatum"]
    v["beschreibung"] = erechnung.beschreibung(r) or v["beschreibung"]
    v["betrag"] = erechnung.ausgabe_betrag(r)
    if v["betrag"] is not None:
        v["fundstellen"]["betrag"] = f"{r['format']}, Gesamt brutto {erechnung.geld(r['brutto'])}"
        v["ust_satz"] = erechnung.ust_satz(r)
        v["ust_betrag"] = abs(r["steuer"]) if v["ust_satz"] else None
    v["hinweise"] += erechnung.hinweise(r)


def _betrag_im_text(betrag, text):
    ganz, cent = f"{abs(betrag):.2f}".split(".")
    gruppen = []
    while ganz:
        ganz, g = ganz[:-3], ganz[-3:]
        gruppen.insert(0, g)
    muster = r"[.,'\s]?".join(gruppen) + (r"(?:[.,]00|,-|[.,]?(?![\d.,]))" if cent == "00" else rf"[.,]{cent}")
    return bool(re.search(rf"(?<!\d){muster}(?!\d)", text))


def text_vorschlaege(text):
    """Betrag, Umsatzsteuer und Datum aus reinem Text (z. B. der Texterkennung von Paperless)."""
    return ocr_vorschlaege(text)


# ---------- Texterkennung (Fotos, Scans) ----------

HOECHSTER = "höchster Betrag im Beleg"
OCR_KEINE_SUMME = re.compile(r"(?i)zwischen|sub\s*total|netto|rabatt|ersparnis|gespart|übertrag|punkte|vor steuern")
OCR_BARGELD = re.compile(r"(?i)(?<![a-zäöü])(?:gegeben|bar|bargeld|rückgeld|ruckgeld|rueckgeld|zurück|wechselgeld|erhalten)(?![a-zäöü])")
OCR_STEUER = re.compile(r"(?i)mwst|mehrwertsteuer|ust|umsatzsteuer|steuer|%")


def ocr_bereinigen(text):
    """Typische Lesefehler: „inkI.“ (großes i statt l), Leerzeichen hinter dem Dezimalkomma („42, 46“)."""
    text = re.sub(r"(?<![A-Za-z])([Ii])nk[I1|](?![A-Za-z])", r"\1nkl", text or "")
    return re.sub(r"(\d), (\d{2})(?!\d)", r"\1,\2", text)


def ocr_gesamt(zeilen):
    """Gesamtbetrag auf Fotos, Scans und Kassenbons: oft ohne Währung; gegebenes Bargeld ist nie die Summe."""
    def in_zeile(z):
        ohne_prozent = re.sub(r"\d+(?:[.,]\d+)?\s*%", " ", z)
        b = betraege(ohne_prozent)
        return b[0] if b else (zahlen_ohne_waehrung(ohne_prozent) or [None])[-1]

    brutto = re.compile(r"(?i)inkl|incl|brutto")
    summe = re.compile(r"(?i)gesamt|summe|total|betrag|zu zahlen")
    kandidaten = [(i, z) for i, z in enumerate(zeilen) if not OCR_KEINE_SUMME.search(z) and not OCR_BARGELD.search(z)
                  and (brutto.search(z) or not OCR_STEUER.search(z))]
    for i, z in kandidaten:
        if brutto.search(z) and summe.search(z) and "einzelpreis" not in z.lower():
            b = in_zeile(z)
            if b is not None:
                return b, z[:80]
    for wort in GESAMT_WOERTER + ["betrag"]:
        muster = re.compile(rf"(?<![a-zäöü]){wort}(?![a-zäöü])", re.I)
        for i, z in kandidaten:
            if not muster.search(z):
                continue
            b = in_zeile(z)
            if b is not None:
                return b, z[:80]
            # Betrag allein in der nächsten Zeile
            if i + 1 < len(zeilen) and re.fullmatch(r"[\s€EURO\d.,]+", zeilen[i + 1]):
                b = in_zeile(zeilen[i + 1])
                if b is not None:
                    return b, f"{z} … {zeilen[i + 1]}"[:80]
    alle = [b for z in zeilen if not OCR_BARGELD.search(z) for b in betraege(z)]
    return (max(alle), HOECHSTER) if alle else (None, None)


def ocr_steuer(zeilen, gesamt):
    """Steuersatz nur, wenn der gelesene Steuerbetrag rechnerisch zum Gesamtbetrag passt."""
    if gesamt:
        for z in zeilen:
            for m in re.finditer(r"(?<![\d,.])(19|7)(?:[.,]0+)?\s*%", z):
                satz = float(m.group(1))
                soll = gesamt * satz / (100 + satz)
                for zahl_ in zahlen_ohne_waehrung(z) + betraege(z):
                    if abs(zahl_ - soll) <= .02:
                        return satz, zahl_
    return None, None


def ocr_vorschlaege(text, absender=None):
    """Vorschläge aus erkanntem Text. Lieber kein Wert als ein falscher – unsichere werden gekennzeichnet."""
    zeilen = zeilen_aus(ocr_bereinigen(text))
    betrag, stelle = ocr_gesamt(zeilen)
    satz, steuer = ocr_steuer(zeilen, betrag)
    datum = datum_vorschlag(zeilen)
    if datum and not "2000-01-01" <= datum <= (date.today() + timedelta(days=31)).isoformat():
        datum = None        # verlesenes Datum würde den Beleg ins falsche EÜR-Jahr schieben
    kopf = [z for z in zeilen[:10] if re.search(r"[A-Za-zÄÖÜäöü]{3}", z) and not ist_eigen(z, absender or {})]
    return {"betrag": betrag, "fundstelle": stelle, "ust_satz": satz, "ust_betrag": steuer, "belegdatum": datum,
            "lieferant": _lieferant_aus_pdf(kopf), "unsicher": stelle == HOECHSTER}


def braucht_texterkennung(typ, betrag, daten):
    """Foto, oder PDF ohne (nennenswerten) Text, in dem kein Betrag gefunden wurde."""
    if betrag is not None:
        return False
    if typ == "bild":
        return True
    if typ != "pdf":
        return False
    try:
        return len("".join(pdf_text(daten).split())) < 100
    except Exception:
        return True     # pypdf scheitert – das Rendern als Bild kann trotzdem gelingen


def _woerter(text):
    """Wörter zum Vergleichen von Namen: ohne Groß/Klein und Akzente; ü = ue = u, Straße = Str."""
    t = re.sub(r"strasse|str\.", "str ", (text or "").casefold())
    t = "".join(z for z in unicodedata.normalize("NFKD", t) if not unicodedata.combining(z))
    return re.findall(r"[^\W_]+", re.sub(r"([aou])e", r"\1", t))


def ist_eigen(text, absender):
    """Bezeichnet der Text den Nutzer selbst (Name, Kontoinhaber, Anschrift)? Dann ist er kein Lieferant.
    Mehrteilige Namen zählen in beliebiger Reihenfolge, auch mit Zusatz; einteilige und die Anschrift nur allein –
    sonst würde „Max“ auch „Max Musikhaus“ treffen."""
    w = [x for x in _woerter(text) if x not in ("herr", "herrn", "frau")]
    if not w:
        return False
    zeile = "".join(w)
    namen = [n for k in ("name", "kontoinhaber") for n in re.split(r"\s[-–—|/]\s|[|()]", absender.get(k) or "")]
    for n in map(_woerter, namen):
        if n and (zeile == "".join(n) or (len(n) > 1 and set(n) <= set(w))):
            return True
    strasse, ort = ("".join(_woerter(absender.get(k))) for k in ("strasse", "plz_ort"))
    return zeile in {x for x in (strasse, ort, strasse + ort) if x}


def ist_eigener_verkaeufer(er, absender):
    """E-Rechnung von einem selbst: am Namen, an Steuernummer bzw. USt-IdNr. oder an der Mailadresse erkannt."""
    def kennung(x):
        return re.sub(r"[^0-9A-Z]", "", (x or "").upper())

    eigene = {k for k in (kennung(absender.get("steuernummer")), kennung(absender.get("ust_idnr"))) if len(k) >= 8}
    return (ist_eigen(er.get("verkaeufer"), absender)
            or any(kennung(x) in eigene for x in er.get("steuer_ids") or [])
            or any(ist_eigene_adresse(m, absender) for m in er.get("mails") or []))


def ist_eigene_adresse(adresse, absender):
    """Mail von einem selbst, z. B. eine weitergeleitete Kauf-Mail."""
    eigene = {(absender.get(k) or "").strip().lower() for k in ("absender_email", "mail_antwort_an", "smtp_benutzer")}
    return "@" in (adresse or "") and adresse.lower() in eigene


def _anzeigename(absender):
    m = re.match(r'\s*"?([^"<]+?)"?\s*<', absender or "")
    return m.group(1).strip() if m else (absender or "").split("@")[0] or None


def _lieferant_aus_pdf(zeilen):
    """Erste sinnvolle Zeile (meist Firmenname im Briefkopf)."""
    for z in zeilen[:8]:
        if len(z) >= 3 and not re.search(r"(?i)rechnung|invoice|seite|page|datum|^\d", z) and not BETRAG.search(z):
            return z[:60]
    return None


def _anzahl_titel(shop, zeilen):
    """Anzahl gekaufter Titel – nur wo die Mail das eindeutig hergibt (Beatport: eine Formatzeile je Titel)."""
    if shop == "Beatport":
        return sum(1 for z in zeilen if z in ("AIFF", "WAV", "MP3", "FLAC")) or None
    return None


def _format(zeilen):
    for f in ("AIFF", "WAV", "FLAC", "MP3"):
        if f in zeilen:
            return f
    return None

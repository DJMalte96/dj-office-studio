"""Belege auslesen: PDF-Rechnungen, Kauf-Mails (.eml/.msg) und Fotos.

Liefert Vorschläge für eine Ausgabe – Lieferant, Datum, Gesamtbetrag, Umsatzsteuer, Beschreibung, Kategorie –
die der Nutzer in der App bestätigt. Für die häufigsten Musik-Shops gibt es eigene Regeln (deren Mails sind immer
gleich aufgebaut), sonst eine allgemeine Suche nach „Gesamt“, „Summe“, „Total“ …
"""
import email
import hashlib
import html
import re
from datetime import datetime
from email import policy
from email.utils import parsedate_to_datetime

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
        v["hinweise"].append("Foto – keine automatische Erkennung, bitte Betrag eintragen")
        return v
    if typ == "unbekannt":
        v["hinweise"].append("Dateityp nicht erkannt – bitte Werte eintragen")
        return v

    if typ == "pdf":
        try:
            text = pdf_text(daten)
        except Exception:
            text = ""
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
        v["lieferant"] = shop[0] if shop else _anzeigename(mail["absender"])
        v["kategorie"] = shop[1] if shop else None
        v["beschreibung"] = mail["betreff"][:120] or None
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


def text_vorschlaege(text):
    """Betrag, Umsatzsteuer und Datum aus reinem Text (z. B. der Texterkennung von Paperless)."""
    zeilen = zeilen_aus(text or "")
    betrag, fundstelle = gesamt_vorschlag(zeilen)
    ust_satz, ust_betrag = steuer_vorschlag(zeilen, betrag)
    return {"betrag": betrag, "fundstelle": fundstelle, "ust_satz": ust_satz, "ust_betrag": ust_betrag,
            "belegdatum": datum_vorschlag(zeilen)}


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

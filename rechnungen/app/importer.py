"""Import alter Rechnungs- und Angebots-PDFs: Text auslesen und Empfänger, Positionen usw. herausziehen.

Das Parsen orientiert sich am Aufbau der bisherigen Vorlage:
  Absenderzeile (mit " | ") → Empfängeradresse → "Rechnung Nr.: …  Ort, den TT.MM.JJ"
  → Tabelle "Beschreibung | Lieferdatum | Preis" → "Gesamt" → Zahlungsbedingung → "Vielen Dank …"
Angebote sind gleich aufgebaut ("Angebot Nr.: …"); nach der Tabelle folgen dort
„gültig bis …“ und Hinweise statt der Zahlungsbedingung.
"""
import io
import re
from datetime import date

from pypdf import PdfReader

# Preis: "960,- Euro", "1.234,50 Euro", "45 Euro", "45,50 €" – aber NICHT "750€ für 6 Stunden" (kein Komma)
PRICE = re.compile(
    r"(?P<a>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<ac>\d{2}|-{1,2}|–))?\s*(?:Euro|EUR)\b"
    r"|(?P<b>\d{1,3}(?:\.\d{3})+|\d+),(?P<bc>\d{2}|-{1,2}|–)\s*€"
)
DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})\b")
PLZ_LINE = re.compile(r"^(\d{5})\s+(.+)$")
NUMMER = re.compile(r"(Rechnung|Angebot)\s*-?\s*(?:Nr\.?|Nummer)\s*:?\s*([A-Za-z0-9][A-Za-z0-9\-/]*)", re.I)
ANGEBOT_TITEL = re.compile(r"^Angebot\b", re.I)          # Angebot ohne Nummer, z. B. „Angebot Hochzeit …“
GUELTIG = re.compile(r"(gültig|Gültigkeit|Bindefrist|bindend)", re.I)
GUELTIG_DAUER = re.compile(r"(\d+)\s*(Tage|Wochen|Monate)", re.I)
TABELLENKOPF = re.compile(r"(Beschreibung|Leistung|Position|Bezeichnung).*(Preis|Betrag)", re.I)
SCHLUSS = re.compile(r"^(Vielen Dank|Mit freundlichen|Ich freue mich|Wir freuen uns|Für Rückfragen|"
                     r"Bei Fragen|Über eine (positive )?Rückmeldung)", re.I)
PRICE_PAREN = re.compile(r"\s*\([^)]*\d\s*€[^)]*\)")  # "(750€ für 6 Stunden, …)"
TIMES = re.compile(r"(\d{1,2}[:.]\d{2})(\s*Uhr\s*(?:bis|-|–)\s*)(\d{1,2}[:.]\d{2})(\s*Uhr)?")


def pdf_text(data):
    """Text mit Layout-Erhalt: Word-PDFs liefern im Standardmodus einzelne Wörter pro Zeile."""
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text(extraction_mode="layout") or "")
        except Exception:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _iso(m):
    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    y = int(y) + (2000 if len(y) == 2 else 0)
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


def _price(m):
    whole = (m.group("a") or m.group("b")).replace(".", "")
    cents = m.group("ac") or m.group("bc") or ""
    return round(float(whole) + (int(cents) / 100 if cents.isdigit() else 0), 2)


def _norm(s):
    return " ".join(s.split())


def _add_days(iso, n, einheit):
    from datetime import timedelta
    tage = n * {"tage": 1, "wochen": 7, "monate": 30}[einheit.lower()]
    try:
        return (date.fromisoformat(iso) + timedelta(days=tage)).isoformat()
    except ValueError:
        return ""


def parse_document(text):
    """Gibt dict mit art ("rechnung"/"angebot"), nummer, datum, kunde, positionen, zahlungsbedingung,
    gesamt zurück – bei Angeboten zusätzlich gueltig_bis und hinweise."""
    lines = [_norm(l) for l in text.splitlines() if l.strip()]
    out = {"art": "rechnung", "nummer": "", "datum": "", "kunde": {}, "positionen": [],
           "zahlungsbedingung": "", "gesamt": 0.0}

    # --- Art + Nummer + Datum ---
    idx_nr = next((i for i, l in enumerate(lines) if NUMMER.search(l)), None)
    if idx_nr is not None:
        m = NUMMER.search(lines[idx_nr])
        out["art"] = "angebot" if m.group(1).lower() == "angebot" else "rechnung"
        out["nummer"] = m.group(2)
    else:
        # Angebote haben in alten Vorlagen nicht immer eine Nummer – dann vergibt die App eine
        idx_nr = next((i for i, l in enumerate(lines) if ANGEBOT_TITEL.match(l)), None)
        if idx_nr is None:
            raise ValueError("Weder „Rechnung Nr.“ noch „Angebot“ gefunden – ist das ein Dokument im Vorlagen-Layout?")
        out["art"] = "angebot"
    angebot = out["art"] == "angebot"
    for l in lines[idx_nr:idx_nr + 3]:
        m = re.search(r"den\s+" + DATE.pattern, l) or DATE.search(l)
        if m:
            out["datum"] = _iso(DATE.search(m.group(0)))
            break

    # --- Empfänger: Zeilen zwischen Absenderzeile und "Rechnung Nr." ---
    head = lines[:idx_nr]
    plz_idx = max((i for i, l in enumerate(head) if PLZ_LINE.match(l) and "|" not in l), default=None)
    if plz_idx is not None:
        sender_idx = max((i for i, l in enumerate(head[:plz_idx]) if "|" in l), default=None)
        start = sender_idx + 1 if sender_idx is not None else max(0, plz_idx - 3)
        block = head[start:plz_idx]
        plz, ort = PLZ_LINE.match(head[plz_idx]).groups()
        kunde = {"name": "", "zusatz": "", "strasse": "", "plz": plz, "ort": ort}
        if block:
            kunde["name"] = block[0]
            if len(block) >= 2:
                kunde["strasse"] = block[-1]
                kunde["zusatz"] = " ".join(block[1:-1])
        out["kunde"] = kunde

    # --- Positionen: zwischen Tabellenkopf und "Gesamt" ---
    rest = lines[idx_nr + 1:]
    h = next((i for i, l in enumerate(rest) if TABELLENKOPF.search(l)), None)
    if h is None:
        h = next((i for i, l in enumerate(rest) if re.search(r"in Rechnung|Anfrage|anbieten|Angebot", l)), -1)
    g = next((i for i, l in enumerate(rest) if i > h and re.match(r"^Gesamt\b", l, re.I)), len(rest))
    # Tabellenzeilen: Eine Zeile mit Preis beginnt eine neue Position (Datum + Preis stehen oben
    # in der Zeile), Zeilen ohne Preis setzen die Beschreibung fort. Zeilen vor dem ersten Preis
    # (Preis vertikal weiter unten) werden der ersten Position vorangestellt.
    rows, pending = [], []
    for line in rest[h + 1:g]:
        pm, dm = PRICE.search(line), DATE.search(line)
        cut = min((m.start() for m in (pm, dm) if m), default=len(line))
        text = line[:cut]
        if pm:
            rows.append({"teile": pending + [text], "lieferdatum": _iso(dm) if dm else "",
                         "preis": _price(pm)})
            pending = []
        elif rows:
            rows[-1]["teile"].append(text)
        else:
            pending.append(text)
    for row in rows:
        beschreibung = _norm(" ".join(row["teile"])).strip(" –-")
        if beschreibung:
            out["positionen"].append({"beschreibung": beschreibung, "lieferdatum": row["lieferdatum"],
                                      "preis": row["preis"]})
    out["gesamt"] = round(sum(p["preis"] for p in out["positionen"]), 2)

    # --- Text nach der "Gesamt"-Zeile bis zum Schluss ("Vielen Dank", "Mit freundlichen" …) ---
    nach = []
    for l in rest[g + 1:]:
        if SCHLUSS.match(l):
            break
        nach.append(l)

    if not angebot:
        out["zahlungsbedingung"] = _norm(" ".join(nach))
        return out

    # Angebot: Zeile mit „gültig bis …“ / „Bindefrist …“ auswerten, der Rest sind Hinweise
    out["gueltig_bis"], hinweise = "", []
    for l in nach:
        if GUELTIG.search(l) and not out["gueltig_bis"]:
            dm = DATE.search(l)
            dauer = GUELTIG_DAUER.search(l)
            if dm:
                out["gueltig_bis"] = _iso(dm)
                continue
            if dauer and out["datum"]:
                out["gueltig_bis"] = _add_days(out["datum"], int(dauer.group(1)), dauer.group(2))
                continue
        hinweise.append(l)
    out["hinweise"] = "\n".join(hinweise)
    return out


parse_invoice = parse_document   # alter Name


def textbaustein_vorschlag(beschreibung):
    """Uhrzeiten durch {von}/{bis} ersetzen und einen kurzen Titel ableiten."""
    text = TIMES.sub(lambda m: "{von}" + m.group(2) + "{bis}" + (m.group(4) or ""), beschreibung)
    text = _norm(PRICE_PAREN.sub("", text))  # Preis wird individuell festgelegt → nicht in die Vorlage
    titel = text.split("{von}")[0].strip(" –-")
    # Anlass-Name: "DJ – Tätigkeit Hochzeit (…)" → "Hochzeit", "DJ – Tätigkeit (Kofferjob)" → "Kofferjob"
    anlass = re.sub(r"^DJ\s*[–-]\s*Tätigkeit\s*", "", titel, flags=re.I)
    anlass = PRICE_PAREN.sub("", anlass)
    anlass = anlass.strip(" ()–-")
    if anlass:
        titel = anlass
    if len(titel) > 40:
        titel = titel.split("(")[0].strip(" –-")
    if len(titel) > 40:
        titel = titel[:40].rsplit(" ", 1)[0] + " …"
    return {"titel": titel or text[:40], "text": text}

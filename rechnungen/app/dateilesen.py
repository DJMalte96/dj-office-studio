"""Outlook-Mails (.msg) und Fotos für die Vorschau lesen – wie PDFs im begrenzten Kindprozess von pdflesen.

Die App importiert extract_msg, pillow_heif und PIL dafür nie selbst: extract_msg entpackt komprimiertes RTF und
baut daraus HTML (3 MB reichten für über 25 Sekunden und 750 MB), ein 48-MP-HEIC braucht knapp 800 MB.
"""
import os

import pdflesen

MAX_TEXT = 2_000_000            # Zeichen je Klartext bzw. HTML
MAX_ANHAENGE = 200
MAX_ANHANG_BYTES = 60 * 1024 * 1024     # zusammen
VORSCHAU = 2000                 # längere Bildseite in Pixeln


# ---------- Aufruf aus der App ----------

def msg(daten):
    """→ (mail, [(name, typ, bytes)]). Inhalt gibt es nur für PDF und XML, von anderen Anhängen nur den Namen.
    Wirft pdflesen.Abgebrochen bzw. pdflesen.Kaputt."""
    def lauf():
        try:
            with pdflesen.kindlauf(daten, "msg") as (tmp, code):
                d = pdflesen.json_lesen(os.path.join(tmp, "ergebnis.json"))
                if code or d is None:
                    return {"problem": pdflesen.abbruchgrund(code)}, False
                if "kaputt" in d:
                    return d, True
                anhaenge, gesamt = [], 0
                for i, (name, typ, mit_inhalt) in enumerate(d["anhaenge"][:MAX_ANHAENGE]):
                    inhalt = b""
                    if mit_inhalt:
                        with open(os.path.join(tmp, f"anhang{i}"), "rb") as f:
                            inhalt = f.read(MAX_ANHANG_BYTES)
                    gesamt += len(inhalt)
                    anhaenge.append((name, typ, inhalt))
                klein = gesamt + len(d["mail"]["text"]) + len(d["mail"]["html"]) < pdflesen.MERKEN_BIS
                return {"mail": d["mail"], "anhaenge": anhaenge}, klein
        except OSError as e:
            return {"problem": f"Lesen ließ sich nicht starten ({type(e).__name__})"}, False

    e = pdflesen.gemerkt(daten, "msg", lauf)
    if "problem" in e:
        raise pdflesen.Abgebrochen(e["problem"], "Outlook-Mail")
    if "kaputt" in e:
        raise pdflesen.Kaputt(e["kaputt"])
    return dict(e["mail"]), list(e["anhaenge"])


def als_jpeg(daten):
    """Foto, das Browser nicht zeigen (HEIC), als verkleinertes JPEG → bytes | None."""
    def lauf():
        try:
            with pdflesen.kindlauf(daten, "foto") as (tmp, code):
                if code:
                    return None, False
                try:
                    with open(os.path.join(tmp, "vorschau.jpg"), "rb") as f:
                        jpeg = f.read()
                except FileNotFoundError:
                    return None, True
                return jpeg, len(jpeg) < pdflesen.MERKEN_BIS
        except OSError:
            return None, False

    return pdflesen.gemerkt(daten, "foto", lauf)


# ---------- Kindprozess ----------

def _kuerzen(text):
    text = text or ""
    if len(text) > MAX_TEXT:            # Mitte weg: die Summe steht oft am Ende
        text = f"{text[:MAX_TEXT * 4 // 5]}\n{text[-MAX_TEXT // 5:]}"
    return text.encode("utf-8", "replace").decode("utf-8")


def msg_auslesen(ordner):
    import extract_msg

    import erechnung
    m = extract_msg.openMsg(os.path.join(ordner, "eingabe"))
    anhaenge, gesamt = [], 0
    for a in m.attachments[:MAX_ANHAENGE]:
        inhalt = getattr(a, "data", None)
        if not isinstance(inhalt, bytes):
            continue                    # eingebettete Mails u. Ä.
        name = _kuerzen(str(a.longFilename or a.shortFilename or "Anhang"))[:300]
        brauchbar = inhalt[:5] == b"%PDF-" or erechnung.ist_xml(name, inhalt)
        if brauchbar and gesamt + len(inhalt) <= MAX_ANHANG_BYTES:
            gesamt += len(inhalt)
            with open(os.path.join(ordner, f"anhang{len(anhaenge)}"), "wb") as f:
                f.write(inhalt)
        else:
            brauchbar = False
        anhaenge.append([name, str(a.mimetype or "")[:100], brauchbar])
    html = m.htmlBody
    html = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
    return {"anhaenge": anhaenge, "mail": {
        "absender": _kuerzen(str(m.sender or "")), "betreff": _kuerzen(str(m.subject or "")).strip(),
        "datum": m.date.astimezone().date().isoformat() if getattr(m, "date", None) else None,
        "message_id": _kuerzen(str(m.messageId or "")).strip() or None,
        "text": _kuerzen(m.body), "html": _kuerzen(html)}}


def foto_umwandeln(ordner):
    import grenzen
    bild = grenzen.bild_oeffnen(os.path.join(ordner, "eingabe"))
    bild.thumbnail((VORSCHAU, VORSCHAU))
    ziel = os.path.join(ordner, "vorschau.jpg")
    bild.convert("RGB").save(ziel + ".neu", "JPEG", quality=85)
    os.replace(ziel + ".neu", ziel)
    return {}

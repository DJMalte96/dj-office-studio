"""Belege aus dem Postfach (seit 1.16): Rechnungsmails per IMAP nach eigenen Regeln abholen.

Jede Regel: Ordner (Pfad wie im Mailprogramm, Unterordner mit „/“), optional „Absender enthält“ und „Betreff enthält“.
Abgeholte Mails gehen wie hochgeladene .eml-Dateien in die Ausgaben (Anhänge, E-Rechnungen, Kauf-Mails werden
erkannt) und werden im Postfach als gelesen markiert. Jede abgeholte Mail wird gemerkt (Message-ID bzw.
Ordner/UIDVALIDITY/UID) – auch schon gelesene Mails kommen so nicht doppelt.

Zugang: dasselbe Postfach wie der E-Mail-Versand (Benutzer, Passwort); IMAP-Server aus dem Anbieter abgeleitet
oder selbst eingetragen.
"""
import base64
import email
import email.header
import imaplib
import json
import re
import threading
import time
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify

import db

bp = Blueprint("postfach", __name__)
TAKT = 30 * 60                     # alle 30 Minuten
MAX_JE_LAUF = 200                  # höchstens so viele Mails je Lauf (der Rest beim nächsten Mal)
MAX_MAIL = 60 * 1024 * 1024
MAX_REGELN = 30
IMAP_ZU_SMTP = {                   # bekannte Anbieter: SMTP-Server → IMAP-Server
    "smtp.web.de": "imap.web.de", "mail.gmx.net": "imap.gmx.net", "smtp.gmail.com": "imap.gmail.com",
    "smtp-mail.outlook.com": "outlook.office365.com", "smtp.office365.com": "outlook.office365.com",
    "smtp.mail.me.com": "imap.mail.me.com", "securesmtp.t-online.de": "secureimap.t-online.de",
    "smtp.mail.yahoo.com": "imap.mail.yahoo.com", "mail.freenet.de": "mx.freenet.de",
    "smtp.ionos.de": "imap.ionos.de", "smtp.strato.de": "imap.strato.de", "smtp.posteo.de": "posteo.de",
    "smtp.mailbox.org": "imap.mailbox.org",
}
_sperre = threading.Lock()
_waechter = []


class PostfachFehler(Exception):
    pass


# ---------- Regeln ----------

def regeln_pruefen(text):
    """Regeln aus den Einstellungen (JSON) prüfen und bereinigt als JSON zurückgeben. ValueError bei Unsinn."""
    try:
        roh = json.loads(text or "[]")
    except ValueError:
        raise ValueError("Die Abholregeln sind ungültig") from None
    if not isinstance(roh, list) or len(roh) > MAX_REGELN:
        raise ValueError(f"Höchstens {MAX_REGELN} Abholregeln")
    aus = []
    for r in roh:
        if not isinstance(r, dict):
            raise ValueError("Die Abholregeln sind ungültig")
        regel = {"an": bool(r.get("an", True)),
                 **{k: re.sub(r"\s+", " ", str(r.get(k) or "")).strip()[:200] for k in ("ordner", "von", "betreff")}}
        regel["ordner"] = "/".join(t.strip() for t in regel["ordner"].strip("/").split("/") if t.strip())
        if regel["ordner"] or regel["von"] or regel["betreff"]:
            aus.append(regel)
    return json.dumps(aus, ensure_ascii=False)


def regeln(a=None):
    a = a or db.get_settings()
    try:
        return json.loads(a.get("postfach_regeln") or "[]")
    except ValueError:
        return []


# ---------- IMAP-Ordnernamen (modifiziertes UTF-7, RFC 3501) ----------

def _utf7_kodieren(text):
    aus, puffer = [], []

    def leeren():
        if puffer:
            b = base64.b64encode("".join(puffer).encode("utf-16-be")).rstrip(b"=").decode().replace("/", ",")
            aus.append("&" + b + "-")
            puffer.clear()
    for ch in text:
        if 0x20 <= ord(ch) <= 0x7E:
            leeren()
            aus.append("&-" if ch == "&" else ch)
        else:
            puffer.append(ch)
    leeren()
    return "".join(aus)


def _utf7_lesen(text):
    def teil(m):
        b = m.group(1)
        if not b:
            return "&"
        b = b.replace(",", "/")
        return base64.b64decode(b + "=" * (-len(b) % 4)).decode("utf-16-be")
    return re.sub(r"&([A-Za-z0-9+,]*)-", teil, text)


def _quoten(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------- Verbindung ----------

def imap_server(a):
    eigen = (a.get("imap_server") or "").strip()
    if eigen:
        return eigen
    smtp = (a.get("smtp_server") or "").strip().lower()
    return IMAP_ZU_SMTP.get(smtp) or (("imap." + smtp[5:]) if smtp.startswith("smtp.") else smtp)


def _verbinden(a):
    import main
    server = imap_server(a)
    benutzer = a.get("smtp_benutzer") or a.get("absender_email")
    if not server or not benutzer or not a.get("smtp_passwort"):
        raise PostfachFehler("Bitte zuerst den E-Mail-Versand einrichten (Adresse, Passwort) – das Postfach ist dasselbe.")
    port = int(a.get("imap_port") or 993)
    try:
        if port == 993:
            con = imaplib.IMAP4_SSL(server, port, ssl_context=main._ssl_kontext(), timeout=30)
        else:
            con = imaplib.IMAP4(server, port, timeout=30)
            con.starttls(ssl_context=main._ssl_kontext())
    except (OSError, imaplib.IMAP4.error) as e:
        raise PostfachFehler(f"Postfach {server} nicht erreichbar ({e.__class__.__name__}).") from None
    try:
        con.login(benutzer, a["smtp_passwort"])
    except imaplib.IMAP4.error:
        _abmelden(con)
        raise PostfachFehler("Anmeldung am Postfach fehlgeschlagen – Benutzer und Passwort beim E-Mail-Versand prüfen. "
                             "Manche Anbieter verlangen, dass IMAP im Postfach erst erlaubt wird.") from None
    return con


def _abmelden(con):
    try:
        con.logout()
    except Exception:   # noqa: BLE001
        pass


LIST_ZEILE = re.compile(rb'\((?P<flags>[^)]*)\)\s+(?P<trenner>"(?:\\.|[^"])*"|NIL)\s+(?P<name>.+)$')


def ordner_liste(con):
    """[(anzeige, echter Name)] – Anzeige mit „/“ als Trenner und „Posteingang“ statt INBOX."""
    typ, daten = con.list()
    if typ != "OK":
        raise PostfachFehler("Die Ordner des Postfachs konnten nicht gelesen werden.")
    aus = []
    for z in daten or []:
        if isinstance(z, tuple):          # Name als Literal
            z = z[0] + b" " + z[1]
        m = LIST_ZEILE.match(z or b"")
        if not m or b"\\noselect" in m.group("flags").lower():
            continue
        trenner = m.group("trenner").strip(b'"').decode() if m.group("trenner") != b"NIL" else ""
        roh = m.group("name").strip()
        name = roh[1:-1].replace(b'\\"', b'"').replace(b"\\\\", b"\\") if roh.startswith(b'"') else roh
        echt = name.decode("utf-8", "replace")
        teile = _utf7_lesen(echt).split(trenner) if trenner else [_utf7_lesen(echt)]
        if teile[0].upper() == "INBOX":
            teile[0] = "Posteingang"
        aus.append(("/".join(teile), echt))
    return sorted(aus, key=lambda x: (x[0].lower() != "posteingang", x[0].lower()))


def _aufloesen(pfad, liste):
    pfad = "/".join(t.strip() for t in pfad.split("/") if t.strip()).lower()
    if pfad in ("inbox",):
        pfad = "posteingang"
    return next((echt for anzeige, echt in liste if anzeige.lower() == pfad), None)


def _kopf(roh, feld):
    m = email.message_from_bytes(roh)
    wert = m.get(feld, "")
    try:
        return str(email.header.make_header(email.header.decode_header(wert)))
    except Exception:   # noqa: BLE001
        return str(wert)


def _uids(con, seit):
    typ, daten = con.uid("SEARCH", "SINCE", f"{seit.day:02d}-{MONATE[seit.month - 1]}-{seit.year}")
    if typ != "OK":
        return []
    return (daten[0] or b"").split()


MONATE = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]   # IMAP: englisch


def _abrufen(con, uid, teil):
    typ, daten = con.uid("FETCH", uid, f"(UID {teil})")
    if typ != "OK" or not daten:
        return None
    for x in daten:
        if isinstance(x, tuple) and len(x) >= 2:
            return x[1]
    return None


# ---------- Abholen ----------

def _ab(a):
    try:
        return date.fromisoformat(a.get("postfach_ab") or "")
    except ValueError:
        return date.today() - timedelta(days=30)


def _passt(regel, kopf_von, kopf_betreff):
    return ((not regel["von"] or regel["von"].lower() in kopf_von.lower())
            and (not regel["betreff"] or regel["betreff"].lower() in kopf_betreff.lower()))


def pruefen():
    """Je Regel: Ordner vorhanden? Wie viele Mails passen seit „Mails ab“? → [{ordner, gefunden, passend}]"""
    a = db.get_settings()
    con = _verbinden(a)
    try:
        liste = ordner_liste(con)
        aus = []
        for r in regeln(a):
            echt = _aufloesen(r["ordner"] or "Posteingang", liste)
            if not echt:
                aus.append({"ordner": r["ordner"], "gefunden": False, "passend": 0})
                continue
            con.select(_quoten(echt), readonly=True)
            passend = 0
            for uid in _uids(con, _ab(a))[-500:]:
                kopf = _abrufen(con, uid, "BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)]") or b""
                passend += _passt(r, _kopf(kopf, "From"), _kopf(kopf, "Subject"))
            aus.append({"ordner": r["ordner"], "gefunden": True, "passend": passend})
        return aus
    finally:
        _abmelden(con)


def abholen():
    """Alle aktiven Regeln abarbeiten. Rückgabe: {neu, doppelt, fehler, ordner} – und als Stand gespeichert."""
    import finanzen
    if not _sperre.acquire(blocking=False):
        return {"laeuft": True}
    stand = {"am": datetime.now().isoformat(timespec="seconds"), "neu": 0, "doppelt": 0, "fehler": [], "ordner": []}
    try:
        a = db.get_settings()
        aktiv = [r for r in regeln(a) if r.get("an")]
        if not aktiv:
            stand["fehler"].append("Keine aktive Abholregel")
            return stand
        con = _verbinden(a)
        try:
            liste = ordner_liste(con)
            anzahl = 0
            for r in aktiv:
                echt = _aufloesen(r["ordner"] or "Posteingang", liste)
                if not echt:
                    stand["fehler"].append(f"Ordner „{r['ordner']}“ gibt es im Postfach nicht")
                    continue
                typ, daten = con.select(_quoten(echt))
                if typ != "OK":
                    stand["fehler"].append(f"Ordner „{r['ordner']}“ lässt sich nicht öffnen")
                    continue
                gueltig = (con.response("UIDVALIDITY")[1] or [b"0"])[0]
                gueltig = gueltig.decode() if isinstance(gueltig, bytes) else str(gueltig)
                stand["ordner"].append(r["ordner"])
                for uid in _uids(con, _ab(a)):
                    if anzahl >= MAX_JE_LAUF:
                        break
                    u = uid.decode()
                    schl_uid = f"{echt}|{gueltig}|{u}"
                    if _schon(schl_uid):
                        continue
                    kopf = _abrufen(con, uid, "BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID)]") or b""
                    if not _passt(r, _kopf(kopf, "From"), _kopf(kopf, "Subject")):
                        continue
                    mid = _kopf(kopf, "Message-ID").strip()
                    if mid and _schon("mid|" + mid):
                        _merken(schl_uid, echt)
                        continue
                    roh = _abrufen(con, uid, "BODY.PEEK[]")
                    if not roh or len(roh) > MAX_MAIL:
                        stand["fehler"].append(f"Mail „{_kopf(kopf, 'Subject')[:60]}“ zu groß oder leer")
                        continue
                    betreff = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", _kopf(kopf, "Subject") or "Mail")[:80] or "Mail"
                    erg = finanzen.dateien_aufnehmen([(f"{betreff}.eml", roh)], automatisch=True)
                    if erg["fehler"]:
                        stand["fehler"].append(f"„{betreff[:60]}“: {erg['fehler'][0].get('fehler')}")
                        continue
                    stand["neu"] += len(erg["neu"])
                    stand["doppelt"] += len(erg["doppelt"])
                    anzahl += 1
                    con.uid("STORE", uid, "+FLAGS", "(\\Seen)")   # im Postfach als gelesen markieren
                    _merken(schl_uid, echt)
                    if mid:
                        _merken("mid|" + mid, echt)
        finally:
            _abmelden(con)
    except PostfachFehler as e:
        stand["fehler"].append(str(e))
    except (OSError, imaplib.IMAP4.error) as e:
        stand["fehler"].append(f"Verbindung zum Postfach abgebrochen ({e.__class__.__name__})")
    finally:
        db.save_settings({"_postfach_stand": stand})
        _sperre.release()
    return stand


def _schon(schluessel):
    with db.connect() as con:
        return bool(con.execute("SELECT 1 FROM postfach_abgeholt WHERE schluessel = ?", (schluessel[:500],)).fetchone())


def _merken(schluessel, ordner):
    with db.connect() as con:
        con.execute("INSERT OR IGNORE INTO postfach_abgeholt (schluessel, ordner) VALUES (?, ?)", (schluessel[:500], ordner[:300]))


# ---------- Hintergrund ----------

def _schleife():
    time.sleep(20)   # nach dem Start erst kurz Ruhe
    while True:
        try:
            a = db.get_settings()
            if a.get("postfach_an") and any(r.get("an") for r in regeln(a)):
                abholen()
        except Exception:   # noqa: BLE001 – der Wächter darf nie sterben
            pass
        time.sleep(TAKT)


def waechter_starten():
    """Nur beim echten Programmstart (main.py bzw. Desktop-App), nie in den Tests."""
    import finanzen
    if finanzen.HINTERGRUND and not _waechter:
        t = threading.Thread(target=_schleife, daemon=True, name="postfach")
        _waechter.append(t)
        t.start()


# ---------- API ----------

def _fehler(text, code=400):
    return jsonify({"error": text}), code


@bp.get("/api/postfach")
def stand_lesen():
    a = db.get_settings()
    return jsonify({"an": bool(a.get("postfach_an")), "regeln": regeln(a), "server": imap_server(a),
                    "stand": a.get("_postfach_stand"), "versand_eingerichtet": bool(a.get("smtp_passwort"))})


@bp.post("/api/postfach/ordner")
def ordner_api():
    try:
        con = _verbinden(db.get_settings())
    except PostfachFehler as e:
        return _fehler(str(e))
    try:
        return jsonify({"ordner": [anzeige for anzeige, _ in ordner_liste(con)]})
    except (PostfachFehler, OSError, imaplib.IMAP4.error) as e:
        return _fehler(str(e) if isinstance(e, PostfachFehler) else "Die Ordner konnten nicht gelesen werden.")
    finally:
        _abmelden(con)


@bp.post("/api/postfach/pruefen")
def pruefen_api():
    try:
        return jsonify({"regeln": pruefen()})
    except PostfachFehler as e:
        return _fehler(str(e))
    except (OSError, imaplib.IMAP4.error):
        return _fehler("Verbindung zum Postfach abgebrochen.")


@bp.post("/api/postfach/abholen")
def abholen_api():
    stand = abholen()
    if stand.get("laeuft"):
        return _fehler("Das Postfach wird gerade schon abgefragt – bitte kurz warten.", 409)
    return jsonify(stand)

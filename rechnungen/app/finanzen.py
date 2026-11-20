"""Finanzen: Ausgaben mit Belegen (Stufe 1 von Version 1.1).

Belege (PDF, Fotos, Kauf-Mails) werden unverändert im Datenordner unter belege/<Jahr>/ abgelegt;
die Datenbank speichert Pfad, Prüfsumme und die bestätigten Werte. Neu hochgeladene Belege haben den
Status „neu“, bis sie in der App geprüft und übernommen wurden. Die Tabellen stehen in db.SCHEMA.
"""
import json
import os
import re
from datetime import date

from flask import Blueprint, Response, abort, jsonify, request

import belege
import db

bp = Blueprint("finanzen", __name__)

# Schlüssel → (Anzeige, Zuordnung zur Anlage EÜR). Die genauen Zeilen der Anlage EÜR werden je Steuerjahr geprüft.
KATEGORIEN = {
    "technik": ("Technik (Kleingeräte, Verbrauch)", "Geringwertige Wirtschaftsgüter / laufende Betriebsausgaben"),
    "anschaffung": ("Anschaffung über 800 €", "Absetzung für Abnutzung (AfA)"),
    "miete": ("Miete Technik", "Miete / Leasing beweglicher Wirtschaftsgüter"),
    "musik": ("Musik & Lizenzen", "Übrige Betriebsausgaben (Lizenzen, Musik)"),
    "fahrzeug": ("Fahrzeug", "Kfz-Kosten (nur Betriebsfahrzeug)"),
    "reise": ("Reisekosten", "Reisekosten (Parken, Maut, Übernachtung)"),
    "telefon": ("Telefon & Internet", "Telekommunikation"),
    "werbung": ("Werbung", "Werbekosten"),
    "versicherung": ("Versicherungen & Beiträge", "Versicherungen und Beiträge"),
    "fortbildung": ("Fortbildung", "Fortbildungskosten"),
    "buero": ("Bürobedarf & Gebühren", "Bürobedarf, Porto, Kontoführung"),
    "ust": ("Umsatzsteuer an das Finanzamt", "Gezahlte Umsatzsteuer (nur ohne Kleinunternehmerregelung)"),
    "sonstiges": ("Sonstiges", "Übrige Betriebsausgaben"),
}

FELDER = ("belegdatum", "bezahlt_am", "lieferant", "beschreibung", "kategorie", "betrag", "ust_satz", "privatanteil",
          "notiz", "rechnung_id")


def _belege_ordner():
    return os.path.join(db.DATA_DIR, "belege")


def _zeile(r):
    d = dict(r)
    d["erkannt"] = json.loads(d.pop("erkannt_json") or "{}")
    d["kategorie_name"] = KATEGORIEN.get(d["kategorie"], (d["kategorie"],))[0]
    d["jahr"] = (d.get("bezahlt_am") or d.get("belegdatum") or "")[:4]
    return d


def liste(jahr=None):
    """Alle neuen (ungeprüften) Ausgaben + die übernommenen des Jahres (nach Bezahlt-Datum)."""
    with db.connect() as con:
        if jahr:
            rows = con.execute("SELECT * FROM ausgaben WHERE status = 'neu' OR COALESCE(bezahlt_am, belegdatum) LIKE ?"
                               " ORDER BY status = 'ok', COALESCE(bezahlt_am, belegdatum) DESC, id DESC", (f"{jahr}%",))
        else:
            rows = con.execute("SELECT * FROM ausgaben ORDER BY status = 'ok', COALESCE(bezahlt_am, belegdatum) DESC, id DESC")
        return [_zeile(r) for r in rows]


def holen(aid):
    with db.connect() as con:
        r = con.execute("SELECT * FROM ausgaben WHERE id = ?", (aid,)).fetchone()
        return _zeile(r) if r else None


def _kategorie_fuer(lieferant):
    """Zuletzt verwendete Kategorie beim selben Lieferanten (lernt mit)."""
    if not lieferant:
        return None
    with db.connect() as con:
        r = con.execute("SELECT kategorie FROM ausgaben WHERE status = 'ok' AND lieferant = ? COLLATE NOCASE"
                        " ORDER BY id DESC LIMIT 1", (lieferant,)).fetchone()
        return r["kategorie"] if r else None


def _doppelt(pruefsumme, message_id):
    with db.connect() as con:
        r = con.execute("SELECT id FROM ausgaben WHERE beleg_pruefsumme = ? OR (? IS NOT NULL AND mail_message_id = ?)",
                        (pruefsumme, message_id, message_id)).fetchone()
        return r["id"] if r else None


def _dateiname(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name or "Beleg").strip(" .") or "Beleg"
    return name[-100:]


def beleg_aufnehmen(name, daten, paperless=None):
    """Beleg speichern und auswerten → (neue Ausgabe | None, ID der vorhandenen bei Duplikat).
    paperless: Angaben aus Paperless (id, korrespondent, datum, titel, text) – haben Vorrang vor der eigenen Auswertung."""
    pruef = belege.pruefsumme(daten)
    schon = _doppelt(pruef, None)
    if schon:
        return None, schon
    v = belege.auswerten(name, daten)
    vorhanden = _doppelt(pruef, v["message_id"])
    if vorhanden:
        return None, vorhanden
    pl_id = None
    if paperless:
        pl_id = paperless["id"]
        if v["betrag"] is None and (paperless.get("text") or "").strip():   # z. B. Foto/Scan: Texterkennung von Paperless nutzen
            t = belege.text_vorschlaege(paperless["text"])
            v["betrag"], v["ust_satz"], v["ust_betrag"] = t["betrag"], t["ust_satz"], t["ust_betrag"]
            v["fundstellen"]["betrag"] = t["fundstelle"]
            v["belegdatum"] = v["belegdatum"] or t["belegdatum"]
            v["hinweise"] = [h for h in v["hinweise"] if "bitte Betrag eintragen" not in h and "Gesamtbetrag nicht" not in h]
            v["hinweise"].append("Werte aus der Texterkennung von Paperless" if t["betrag"] is not None
                                 else "Gesamtbetrag nicht gefunden – bitte eintragen")
        v["lieferant"] = paperless.get("korrespondent") or v["lieferant"] or paperless.get("titel")
        v["belegdatum"] = paperless.get("datum") or v["belegdatum"]
        v["beschreibung"] = v["beschreibung"] or paperless.get("titel")
        v["hinweise"].append(f"Aus Paperless (Dokument {pl_id})")
    kategorie = _kategorie_fuer(v["lieferant"]) or v["kategorie"] or "sonstiges"
    belegdatum = v["belegdatum"] or date.today().isoformat()
    with db.connect() as con:
        aid = con.execute(
            "INSERT INTO ausgaben (status, belegdatum, bezahlt_am, lieferant, beschreibung, kategorie, betrag, ust_satz,"
            " beleg_name, beleg_typ, beleg_pruefsumme, mail_message_id, erkannt_json, paperless_id)"
            " VALUES ('neu', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (belegdatum, belegdatum, v["lieferant"] or "", v["beschreibung"] or "", kategorie, v["betrag"], v["ust_satz"],
             name, v["typ"], pruef, v["message_id"], json.dumps(v), pl_id)).lastrowid
        rel = os.path.join("belege", belegdatum[:4], f"{aid}_{_dateiname(name)}")
        ziel = os.path.join(db.DATA_DIR, rel)
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "wb") as f:
            f.write(daten)
        con.execute("UPDATE ausgaben SET beleg_datei = ? WHERE id = ?", (rel, aid))
    return holen(aid), None


def _pruefen(d, ohne_beleg=False):
    """Eingaben einer Ausgabe prüfen und normalisieren → (werte, fehler)."""
    fehler, w = [], {}
    for k in FELDER:
        if k in d:
            w[k] = d[k]
    for k in ("belegdatum", "bezahlt_am"):
        if k in w:
            w[k] = (w[k] or "").strip() or None
            if w[k] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", w[k]):
                fehler.append(f"Ungültiges Datum: {w[k]}")
    for k in ("lieferant", "beschreibung", "notiz"):
        if k in w:
            w[k] = (w[k] or "").strip()
    if "kategorie" in w and w["kategorie"] not in KATEGORIEN:
        fehler.append("Unbekannte Kategorie")
    for k in ("betrag", "ust_satz", "privatanteil"):
        if k in w:
            if w[k] in (None, ""):
                w[k] = None if k != "privatanteil" else 0
                continue
            try:
                w[k] = round(float(str(w[k]).replace(",", ".")), 2)
            except ValueError:
                fehler.append(f"„{k}“ muss eine Zahl sein")
    if w.get("privatanteil") is not None and not 0 <= w["privatanteil"] <= 100:
        fehler.append("Privatanteil muss zwischen 0 und 100 % liegen")
    if "rechnung_id" in w:
        w["rechnung_id"] = int(w["rechnung_id"]) if str(w["rechnung_id"] or "").isdigit() else None
    return w, fehler


def _pflicht(a):
    """Vor dem Übernehmen: Datum, Lieferant, Betrag – ohne Beleg zusätzlich eine Notiz."""
    fehlt = [t for k, t in (("belegdatum", "Belegdatum"), ("lieferant", "Lieferant"), ("betrag", "Betrag")) if a.get(k) in (None, "")]
    if not a.get("beleg_datei") and not (a.get("notiz") or "").strip():
        fehlt.append("Notiz (warum kein Beleg)")
    return fehlt


def _fehler(text, code=400):
    return jsonify({"error": text}), code


def _daten():
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


# ---------- Schnittstellen ----------

@bp.get("/api/finanzen/kategorien")
def kategorien():
    return jsonify([{"id": k, "name": n, "euer": e} for k, (n, e) in KATEGORIEN.items()])


@bp.get("/api/ausgaben")
def ausgaben_liste():
    jahr = request.args.get("jahr")
    return jsonify(liste(jahr if jahr and jahr.isdigit() else None))


@bp.get("/api/ausgaben/lieferanten")
def lieferanten():
    with db.connect() as con:
        return jsonify([r[0] for r in con.execute(
            "SELECT lieferant FROM ausgaben WHERE lieferant != '' GROUP BY lieferant COLLATE NOCASE ORDER BY COUNT(*) DESC, lieferant")])


@bp.post("/api/ausgaben/belege")
def belege_hochladen():
    """Mehrere Belege auf einmal: speichern, auswerten, als „neu“ anlegen. Doppelte werden erkannt."""
    return jsonify(dateien_aufnehmen((f.filename or "Beleg", f.read()) for f in request.files.getlist("dateien")))


def dateien_aufnehmen(eingang):
    """[(name, bytes)] → {neu, doppelt, fehler}. Postfach-Exporte (.mbox) werden in einzelne Mails aufgeteilt."""
    neu, doppelt, fehler = [], [], []
    dateien = []
    for name, daten in eingang:
        if not daten:
            continue
        if belege.ist_mbox(name, daten):          # Postfach-Export → jede Mail ein eigener Beleg
            try:
                dateien += belege.mbox_aufteilen(daten)
            except Exception as e:
                fehler.append({"datei": name, "fehler": f"Postfach konnte nicht gelesen werden ({type(e).__name__})"})
        else:
            dateien.append((name, daten))
    for name, daten in dateien:
        try:
            a, vorhanden = beleg_aufnehmen(name, daten)
        except Exception as e:   # defekte Datei darf den Rest nicht aufhalten
            fehler.append({"datei": name, "fehler": f"Konnte nicht gelesen werden ({type(e).__name__})"})
            continue
        if vorhanden:
            doppelt.append({"datei": name, "id": vorhanden})
        else:
            neu.append(a)
    return {"neu": neu, "doppelt": doppelt, "fehler": fehler}


@bp.post("/api/ausgaben")
def ausgabe_anlegen():
    """Ausgabe ohne Beleg (z. B. Parkautomat) – direkt übernommen."""
    w, fehler = _pruefen(_daten(), ohne_beleg=True)
    w.setdefault("kategorie", "sonstiges")
    w.setdefault("bezahlt_am", w.get("belegdatum"))
    fehlt = _pflicht(w)
    if fehler or fehlt:
        return _fehler("; ".join(fehler + ([f"Bitte ergänzen: {', '.join(fehlt)}"] if fehlt else [])))
    spalten = list(w)
    with db.connect() as con:
        aid = con.execute(f"INSERT INTO ausgaben (status, {', '.join(spalten)}) VALUES ('ok', {', '.join('?' * len(spalten))})",
                          [w[k] for k in spalten]).lastrowid
    anlage_zur_ausgabe(aid)
    return jsonify(holen(aid)), 201


@bp.get("/api/ausgaben/<int:aid>")
def ausgabe_holen(aid):
    return jsonify(holen(aid) or abort(404))


@bp.put("/api/ausgaben/<int:aid>")
def ausgabe_aendern(aid):
    """Werte speichern; mit {"uebernehmen": true} wird eine neue Ausgabe bestätigt (Status ok)."""
    alt = holen(aid) or abort(404)
    d = _daten()
    w, fehler = _pruefen(d)
    gesamt = {**alt, **w}
    if d.get("uebernehmen") or alt["status"] == "ok":
        fehlt = _pflicht(gesamt)
        if fehlt:
            fehler.append(f"Bitte ergänzen: {', '.join(fehlt)}")
    if fehler:
        return _fehler("; ".join(fehler))
    if d.get("uebernehmen"):
        w["status"] = "ok"
        if not gesamt.get("bezahlt_am"):
            w["bezahlt_am"] = gesamt.get("belegdatum")
    if w:
        with db.connect() as con:
            con.execute(f"UPDATE ausgaben SET {', '.join(k + ' = ?' for k in w)} WHERE id = ?", [*w.values(), aid])
    anlage_zur_ausgabe(aid)
    return jsonify(holen(aid))


@bp.delete("/api/ausgaben/<int:aid>")
def ausgabe_loeschen(aid):
    """Verwerfen (neu) bzw. löschen – die Belegdatei wird mit entfernt."""
    a = holen(aid) or abort(404)
    with db.connect() as con:
        con.execute("DELETE FROM ausgaben WHERE id = ?", (aid,))
        con.execute("DELETE FROM anlagen WHERE ausgabe_id = ?", (aid,))
    if a.get("beleg_datei"):
        try:
            os.remove(os.path.join(db.DATA_DIR, a["beleg_datei"]))
        except OSError:
            pass
    return "", 204


def _beleg_bytes(a):
    if not a.get("beleg_datei"):
        abort(404)
    pfad = os.path.realpath(os.path.join(db.DATA_DIR, a["beleg_datei"]))
    if not pfad.startswith(os.path.realpath(_belege_ordner()) + os.sep) or not os.path.isfile(pfad):
        abort(404)
    with open(pfad, "rb") as f:
        return f.read()


MIME = {"pdf": "application/pdf", "mail": "message/rfc822", "msg": "application/vnd.ms-outlook"}


@bp.get("/api/ausgaben/<int:aid>/beleg")
def beleg_original(aid):
    """Originaldatei (PDF, Foto, .eml/.msg) – PDFs und Bilder inline, Mails zum Herunterladen."""
    a = holen(aid) or abort(404)
    daten = _beleg_bytes(a)
    name = a["beleg_name"] or "Beleg"
    typ = MIME.get(a["beleg_typ"]) or _bild_mime(daten) or "application/octet-stream"
    inline = a["beleg_typ"] in ("pdf", "bild")
    return Response(daten, mimetype=typ, headers={
        "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{_ascii(name)}"; filename*=UTF-8\'\'{_url(name)}'})


def _ascii(s):
    return s.encode("ascii", "replace").decode().replace('"', "'")


def _url(s):
    from urllib.parse import quote
    return quote(s)


def _bild_mime(daten):
    if daten[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if daten[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if daten[8:12] == b"WEBP":
        return "image/webp"
    return None


# Vorschau für Mails: keine Skripte, keine nachgeladenen Inhalte (Tracking-Pixel), nur eingebettete Bilder
MAIL_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:"


@bp.get("/api/ausgaben/<int:aid>/ansicht")
def beleg_ansicht(aid):
    """Vorschau zum Prüfen: PDF/Bild direkt, Mails als bereinigtes HTML, HEIC-Fotos als JPEG (falls möglich)."""
    a = holen(aid) or abort(404)
    daten = _beleg_bytes(a)
    if a["beleg_typ"] == "pdf":
        return Response(daten, mimetype="application/pdf")
    if a["beleg_typ"] == "bild":
        mime = _bild_mime(daten)
        if mime:
            return Response(daten, mimetype=mime)
        jpeg = _heic_als_jpeg(daten)
        if jpeg:
            return Response(jpeg, mimetype="image/jpeg")
        return _fehler("Für dieses Foto ist keine Vorschau möglich – über „Original öffnen“ ansehen.", 415)
    if a["beleg_typ"] in ("mail", "msg"):
        mail, anhaenge = belege.mail_lesen(daten) if a["beleg_typ"] == "mail" else belege.msg_lesen(daten)
        inhalt = _html_bereinigen(mail["html"]) if mail["html"].strip() else \
            f"<pre style='white-space:pre-wrap;font:13px/1.45 Arial,sans-serif'>{_esc(mail['text'])}</pre>"
        kopf = (f"<div style='font:12px/1.5 Arial,sans-serif;color:#555;border-bottom:1px solid #e5e5e5;padding:0 0 10px;margin:0 0 14px'>"
                f"Von: {_esc(mail['absender'])}<br>Betreff: {_esc(mail['betreff'])}<br>Datum: {_esc(_de_datum(mail['datum']))}"
                + (f"<br>Anhänge: {_esc(', '.join(n for n, _, _ in anhaenge))}" if anhaenge else "") + "</div>")
        seite = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body style='margin:16px;background:#fff;color:#111'>{kopf}{inhalt}</body></html>"
        return Response(seite, mimetype="text/html", headers={"Content-Security-Policy": MAIL_CSP,
                                                             "X-Content-Type-Options": "nosniff"})
    return _fehler("Keine Vorschau für diesen Dateityp.", 415)


def _de_datum(iso):
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}" if iso and len(iso) >= 10 else ""


def _esc(s):
    import html
    return html.escape(s or "")


def _html_bereinigen(roh):
    roh = re.sub(r"(?is)<(script|iframe|object|embed|form|link|meta|base)[^>]*>.*?</\1\s*>", "", roh)
    roh = re.sub(r"(?is)<(script|iframe|object|embed|form|link|meta|base)[^>]*/?>", "", roh)
    roh = re.sub(r"(?i)\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", roh)       # onclick, onload …
    roh = re.sub(r"(?i)(href|src)\s*=\s*([\"'])\s*javascript:[^\"']*\2", r'\1="#"', roh)
    return roh


def _heic_als_jpeg(daten):
    try:
        import io
        import pillow_heif
        from PIL import Image
        pillow_heif.register_heif_opener()
        bild = Image.open(io.BytesIO(daten))
        bild.thumbnail((2000, 2000))
        out = io.BytesIO()
        bild.convert("RGB").save(out, "JPEG", quality=85)
        return out.getvalue()
    except Exception:
        return None


# ======================= Fahrten =======================

import threading  # noqa: E402

import strecken  # noqa: E402


def _einstellungen():
    from main import absender   # zur Laufzeit (main bindet dieses Modul ein)
    return absender()


def _ssl():
    from main import _ssl_kontext
    return _ssl_kontext()


HINTERGRUND = True   # Tests: False → Berechnung sofort statt im Hintergrund-Thread


def _im_hintergrund(funktion, *args):
    if HINTERGRUND:
        threading.Thread(target=funktion, args=args, daemon=True).start()
    else:
        funktion(*args)


def startadresse(a):
    return (a.get("startadresse") or "").strip() or strecken.adresse_text({"strasse": a.get("strasse"), "plz_ort": a.get("plz_ort")})


def zieladresse(beleg):
    """Veranstaltungsort, sonst Kundenadresse."""
    return strecken.adresse_text(beleg.get("veranstaltungsort") or beleg.get("kunde") or {})


def _fahrt_zeile(r):
    d = dict(r)
    d["hin_zurueck"] = bool(d["hin_zurueck"])
    d["km_gesamt"] = None if d["km_einfach"] is None else round(d["km_einfach"] * (2 if d["hin_zurueck"] else 1), 1)
    d["betrag"] = None if d["km_gesamt"] is None else round(d["km_gesamt"] * (d["km_satz"] or 0), 2)
    return d


def fahrten_liste(jahr=None):
    with db.connect() as con:
        rows = con.execute(
            "SELECT f.*, r.nummer AS rechnung_nummer, r.kunde_json, r.storniert_durch, r.positionen_json, r.veranstaltungsort_json"
            " FROM fahrten f LEFT JOIN rechnungen r ON r.id = f.rechnung_id"
            + (" WHERE f.datum LIKE ?" if jahr else "") + " ORDER BY f.datum DESC, f.id DESC", ((f"{jahr}%",) if jahr else ()))
        out = []
        for r in rows:
            d = _fahrt_zeile(r)
            kunde = json.loads(d.pop("kunde_json") or "{}")
            d["kunde"] = kunde.get("name", "")
            pos = json.loads(d.pop("positionen_json") or "[]")
            text = pos[0]["beschreibung"].split(" – ")[1] if pos and " – " in pos[0].get("beschreibung", "") else ""
            d["rechnung_text"] = re.sub(r"^(DJ[- ]?)?Tätigkeit\s+", "", text).strip()
            ort = json.loads(d.pop("veranstaltungsort_json") or "null") or {}
            d["ziel_name"] = ort.get("name") or ""
            d["rechnung_storniert"] = bool(d.pop("storniert_durch"))
            out.append(d)
        return out


def _fahrt_holen(fid):
    with db.connect() as con:
        r = con.execute("SELECT * FROM fahrten WHERE id = ?", (fid,)).fetchone()
        return _fahrt_zeile(r) if r else None


def fahrt_aktualisieren(inv_id, a, berechnen=True):
    """Automatische Fahrt zur Rechnung anlegen bzw. anpassen (nach dem Speichern einer Rechnung)."""
    inv = db.get_invoice(inv_id)
    if not inv or inv.get("storno_von"):
        return None
    with db.connect() as con:
        vorhanden = con.execute("SELECT * FROM fahrten WHERE rechnung_id = ? AND quelle IN ('auto', 'korrigiert')"
                                " ORDER BY id LIMIT 1", (inv_id,)).fetchone()
        if not inv.get("fahrt_erfassen"):
            con.execute("DELETE FROM fahrten WHERE rechnung_id = ? AND quelle IN ('auto', 'korrigiert')", (inv_id,))
            return None
        datum = next((p.get("lieferdatum") for p in inv["positionen"] if p.get("lieferdatum")), inv["datum"])
        ziel, start = zieladresse(inv), startadresse(a)
        anlass = f"Rechnung {inv['nummer']}"
        if vorhanden:
            neu_berechnen = vorhanden["quelle"] == "auto" and (vorhanden["ziel"] != ziel or vorhanden["start"] != start)
            con.execute("UPDATE fahrten SET datum = ?, anlass = ?, ziel = ?, start = ?" + (", km_einfach = NULL, fehler = NULL" if neu_berechnen else "")
                        + " WHERE id = ?", (datum, anlass, ziel, start, vorhanden["id"]))
            fid = vorhanden["id"]
        else:
            fid = con.execute("INSERT INTO fahrten (rechnung_id, datum, anlass, start, ziel, km_satz, quelle) VALUES (?, ?, ?, ?, ?, ?, 'auto')",
                              (inv_id, datum, anlass, start, ziel, float(a.get("km_satz") or 0.30))).lastrowid
    if berechnen and a.get("kartendienst"):
        _im_hintergrund(offene_berechnen, [fid])
    return fid


def fahrten_der_rechnung_entfernen(inv_id):
    """Rechnung wird gelöscht: automatische Fahrt entfernen, von Hand ergänzte behalten (ohne Bezug)."""
    with db.connect() as con:
        con.execute("DELETE FROM fahrten WHERE rechnung_id = ? AND quelle IN ('auto', 'korrigiert')", (inv_id,))
        con.execute("UPDATE fahrten SET rechnung_id = NULL WHERE rechnung_id = ?", (inv_id,))


_berechnung = threading.Lock()


def offene_berechnen(ids=None):
    """Fahrten ohne Kilometer über den Kartendienst berechnen (nur wenn eingeschaltet)."""
    if not _einstellungen().get("kartendienst"):
        return 0
    with _berechnung:
        with db.connect() as con:
            sql = "SELECT id, start, ziel FROM fahrten WHERE km_einfach IS NULL"
            rows = [dict(r) for r in con.execute(sql + (f" AND id IN ({','.join('?' * len(ids))})" if ids else ""), ids or ())]
        fertig = 0
        for f in rows:
            try:
                km, fehler = strecken.strecke_km(f["start"], f["ziel"], _ssl()), None
            except strecken.StreckenFehler as e:
                km, fehler = None, str(e)
            except Exception as e:   # Unerwartetes darf den Hintergrund-Thread nicht lautlos beenden („wird berechnet …“ für immer)
                km, fehler = None, f"Berechnung fehlgeschlagen ({type(e).__name__})"
            with db.connect() as con:
                con.execute("UPDATE fahrten SET km_einfach = ?, fehler = ? WHERE id = ?", (km, fehler, f["id"]))
            fertig += km is not None
        return fertig


@bp.get("/api/fahrten")
def fahrten_api_liste():
    jahr = request.args.get("jahr")
    a = _einstellungen()
    liste_ = fahrten_liste(jahr if jahr and jahr.isdigit() else None)
    # Offene Fahrten ohne laufende Berechnung (Kartendienst später eingeschaltet, App neu gestartet …) → jetzt anstoßen
    offen = [f["id"] for f in liste_ if f["km_einfach"] is None and not f["fehler"]]
    if offen and a.get("kartendienst") and not _berechnung.locked():
        _im_hintergrund(offene_berechnen, offen)
        liste_ = fahrten_liste(jahr if jahr and jahr.isdigit() else None)
    ohne = []
    if jahr and jahr.isdigit():
        with db.connect() as con:
            mit = {r[0] for r in con.execute("SELECT rechnung_id FROM fahrten WHERE rechnung_id IS NOT NULL")}
            ohne = [{"id": r["id"], "nummer": r["nummer"], "kunde": json.loads(r["kunde_json"]).get("name", "")}
                    for r in con.execute("SELECT id, nummer, kunde_json FROM rechnungen WHERE datum LIKE ? AND storno_von IS NULL"
                                         " AND fahrt_erfassen = 0 ORDER BY nummer", (f"{jahr}%",)) if r["id"] not in mit]
    return jsonify({"fahrten": liste_, "ohne_fahrt": ohne, "fahrzeug": a.get("fahrzeug"), "km_satz": a.get("km_satz"),
                    "start": startadresse(a), "kartendienst": bool(a.get("kartendienst"))})


def _fahrt_werte(d):
    fehler, w = [], {}
    if "datum" in d:
        w["datum"] = (d.get("datum") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", w["datum"]):
            fehler.append("Bitte ein Datum angeben")
    for k in ("anlass", "ziel", "start"):
        if k in d:
            w[k] = (d.get(k) or "").strip()
    if "km_einfach" in d:
        v = d.get("km_einfach")
        if v in (None, ""):
            w["km_einfach"] = None
        else:
            try:
                w["km_einfach"] = round(float(str(v).replace(",", ".")), 1)
                if not 0 <= w["km_einfach"] <= 2000:
                    fehler.append("Kilometer zwischen 0 und 2000")
            except ValueError:
                fehler.append("Kilometer müssen eine Zahl sein")
    if "hin_zurueck" in d:
        w["hin_zurueck"] = int(bool(d.get("hin_zurueck")))
    if "rechnung_id" in d:
        w["rechnung_id"] = int(d["rechnung_id"]) if str(d.get("rechnung_id") or "").isdigit() else None
    return w, fehler


@bp.post("/api/fahrten")
def fahrt_anlegen():
    """Fahrt von Hand ergänzen (z. B. Aufbau am Vortag). Ohne km und mit Kartendienst wird berechnet."""
    a = _einstellungen()
    w, fehler = _fahrt_werte(_daten())
    if not w.get("ziel"):
        fehler.append("Bitte ein Ziel angeben")
    if fehler:
        return _fehler("; ".join(fehler))
    w.setdefault("start", startadresse(a))
    w.setdefault("hin_zurueck", 1)
    w["km_satz"], w["quelle"] = float(a.get("km_satz") or 0.30), "hand"
    with db.connect() as con:
        fid = con.execute(f"INSERT INTO fahrten ({', '.join(w)}) VALUES ({', '.join('?' * len(w))})", list(w.values())).lastrowid
    if w.get("km_einfach") is None and a.get("kartendienst"):
        offene_berechnen([fid])
    return jsonify(_fahrt_holen(fid)), 201


@bp.put("/api/fahrten/<int:fid>")
def fahrt_aendern(fid):
    alt = _fahrt_holen(fid) or abort(404)
    w, fehler = _fahrt_werte(_daten())
    if fehler:
        return _fehler("; ".join(fehler))
    if alt["quelle"] == "auto" and "km_einfach" in w and w["km_einfach"] != alt["km_einfach"]:
        w["quelle"] = "korrigiert"   # von Hand geändert → bleibt beim erneuten Speichern der Rechnung erhalten
    if w:
        with db.connect() as con:
            con.execute(f"UPDATE fahrten SET {', '.join(k + ' = ?' for k in w)} WHERE id = ?", [*w.values(), fid])
    return jsonify(_fahrt_holen(fid))


@bp.delete("/api/fahrten/<int:fid>")
def fahrt_loeschen(fid):
    """Fahrt entfernen. Gehört sie automatisch zu einer Rechnung, wird dort „Fahrt erfassen“ ausgeschaltet,
    damit sie nicht wieder angelegt wird."""
    f = _fahrt_holen(fid) or abort(404)
    with db.connect() as con:
        con.execute("DELETE FROM fahrten WHERE id = ?", (fid,))
        if f["rechnung_id"] and f["quelle"] in ("auto", "korrigiert"):
            con.execute("UPDATE rechnungen SET fahrt_erfassen = 0 WHERE id = ?", (f["rechnung_id"],))
    return "", 204


@bp.post("/api/fahrten/nachberechnen")
def fahrten_nachberechnen():
    """Fahrten für Rechnungen des Jahres anlegen, die noch keine haben (außer „Fahrt erfassen“ aus), und offene berechnen."""
    jahr = str(_daten().get("jahr") or date.today().year)
    a = _einstellungen()
    with db.connect() as con:
        ids = [r[0] for r in con.execute(
            "SELECT id FROM rechnungen WHERE datum LIKE ? AND storno_von IS NULL AND fahrt_erfassen != 0"
            " AND id NOT IN (SELECT rechnung_id FROM fahrten WHERE rechnung_id IS NOT NULL)", (f"{jahr}%",))]
    for inv_id in ids:
        fahrt_aktualisieren(inv_id, a, berechnen=False)
    with db.connect() as con:
        offen = con.execute("SELECT COUNT(*) FROM fahrten WHERE km_einfach IS NULL").fetchone()[0]
    if a.get("kartendienst") and offen:
        _im_hintergrund(offene_berechnen)
    return jsonify({"angelegt": len(ids), "offen": offen, "kartendienst": bool(a.get("kartendienst"))})


@bp.get("/api/fahrten/vorschau")
def fahrt_vorschau():
    """Für den Editor: Entfernung zu einer Adresse (nur mit Kartendienst; meist aus dem Zwischenspeicher)."""
    a = _einstellungen()
    ziel = strecken.adresse_text({k: request.args.get(k, "") for k in ("strasse", "plz", "ort")})
    satz = float(a.get("km_satz") or 0.30)
    antwort = {"kartendienst": bool(a.get("kartendienst")), "fahrzeug": a.get("fahrzeug"), "km_satz": satz, "ziel": ziel}
    if not a.get("kartendienst") or not ziel:
        return jsonify(antwort)
    try:
        km = strecken.strecke_km(startadresse(a), ziel, _ssl())
        return jsonify(antwort | {"km_einfach": km, "km_gesamt": round(km * 2, 1), "betrag": round(km * 2 * satz, 2)})
    except strecken.StreckenFehler as e:
        return jsonify(antwort | {"fehler": str(e)})


# ======================= Anschaffungen (Abschreibung) =======================

GWG_GRENZE = 800.0                              # netto: bis hier sofort absetzbar (geringwertiges Wirtschaftsgut)
COMPUTER = re.compile(r"(?i)laptop|notebook|macbook|computer|\bpc\b|imac|mac mini|tablet|ipad|monitor|drucker|software|lizenz")


def nutzungsdauer_vorschlag(text):
    """Vorschlag: Computer/Software 1 Jahr, sonstige Technik 7 Jahre (mit dem Steuerberater abstimmen)."""
    return 1 if COMPUTER.search(text or "") else 7


def _monat(iso):
    return int(iso[5:7]) if iso and len(iso) >= 7 else 1


def afa_plan(a):
    """Abschreibung je Jahr → [(jahr, betrag, restwert_ende)]. Linear, im ersten Jahr anteilig nach Monaten;
    Nutzungsdauer 1 Jahr = voll im Kaufjahr; im Abgangsjahr anteilig bis zum Abgangsmonat."""
    if a.get("restwert_start") is not None and a.get("start_jahr"):
        jahr, rest, nd = int(a["start_jahr"]), float(a["restwert_start"]), max(1, int(a.get("rest_nutzungsdauer") or 1))
        raten = [(jahr + i, 12) for i in range(nd)]
        basis = rest
    else:
        if not a.get("anschaffung_am") or not a.get("kosten"):
            return []
        jahr, basis, nd = int(a["anschaffung_am"][:4]), float(a["kosten"]), max(1, int(a.get("nutzungsdauer") or 1))
        rest = basis
        if nd == 1:
            raten = [(jahr, 12)]
        else:
            erste = 13 - _monat(a["anschaffung_am"])          # Monate im Kaufjahr (März → 10)
            monate, raten, j = nd * 12, [], jahr
            while monate > 0:
                m = min(12 if j != jahr else erste, monate)
                raten.append((j, m))
                monate -= m
                j += 1
    abgang_jahr = int(a["abgang_am"][:4]) if a.get("abgang_am") else None
    gesamt_monate = sum(m for _, m in raten)
    plan = []
    for i, (j, m) in enumerate(raten):
        if abgang_jahr and j > abgang_jahr:
            break
        if abgang_jahr and j == abgang_jahr:
            erstes = i == 0 and a.get("restwert_start") is None
            m = min(m, _monat(a["abgang_am"]) - ((13 - m) - 1 if erstes else 0))   # nur bis zum Abgangsmonat
        betrag = rest if i == len(raten) - 1 and not (abgang_jahr and j == abgang_jahr) else round(basis * m / gesamt_monate, 2)
        betrag = min(round(betrag, 2), round(rest, 2))
        rest = round(rest - betrag, 2)
        plan.append((j, betrag, rest))
        if abgang_jahr and j == abgang_jahr:
            break
    return plan


def anlage_im_jahr(a, jahr):
    """Werte für ein Jahr: Wert am Jahresanfang bzw. Zugang, Abschreibung, Restwert am Jahresende, Abgang."""
    jahr = int(jahr)
    plan = afa_plan(a)
    vorjahre = [r for j, _, r in plan if j < jahr]
    if a.get("restwert_start") is not None and a.get("start_jahr"):
        anfang = float(a["restwert_start"]) if jahr == int(a["start_jahr"]) else (vorjahre[-1] if vorjahre else 0.0)
    else:
        kaufjahr = int((a.get("anschaffung_am") or "0")[:4])
        anfang = float(a.get("kosten") or 0) if jahr == kaufjahr else (vorjahre[-1] if vorjahre else 0.0)
    afa = round(sum(b for j, b, _ in plan if j == jahr), 2)
    ende = next((r for j, _, r in plan if j == jahr), vorjahre[-1] if vorjahre else anfang)
    abgang = bool(a.get("abgang_am")) and a["abgang_am"][:4] == str(jahr)
    return {"afa": afa, "restwert_anfang": round(anfang, 2), "restwert_ende": 0.0 if abgang else round(ende, 2),
            "abgang_restwert": round(ende, 2) if abgang else 0.0,
            "abgang_erloes": round(float(a.get("abgang_erloes") or 0), 2) if abgang else 0.0}


def anlagen_liste(jahr=None):
    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT an.*, au.lieferant AS ausgabe_lieferant, au.beleg_datei IS NOT NULL AS ausgabe_mit_beleg FROM anlagen an"
            " LEFT JOIN ausgaben au ON au.id = an.ausgabe_id ORDER BY COALESCE(an.anschaffung_am, an.start_jahr || '-01-01') DESC, an.id DESC")]
    if not jahr:
        return rows
    out = []
    for a in rows:
        kauf = int((a.get("anschaffung_am") or f"{a.get('start_jahr') or 0}")[:4] or 0)
        abgang = int(a["abgang_am"][:4]) if a.get("abgang_am") else 9999
        if kauf <= int(jahr) <= abgang:
            out.append(a | anlage_im_jahr(a, jahr) | {"plan": afa_plan(a)})
    return out


def _anlage_werte(d):
    fehler, w = [], {}
    for k in ("bezeichnung", "notiz"):
        if k in d:
            w[k] = (d.get(k) or "").strip()
    for k in ("anschaffung_am", "abgang_am"):
        if k in d:
            w[k] = (d.get(k) or "").strip() or None
            if w[k] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", w[k]):
                fehler.append(f"Ungültiges Datum: {w[k]}")
    for k in ("kosten", "restwert_start", "abgang_erloes"):
        if k in d:
            v = d.get(k)
            try:
                w[k] = None if v in (None, "") else round(float(str(v).replace(".", "").replace(",", ".") if "," in str(v) else v), 2)
            except ValueError:
                fehler.append(f"„{k}“ muss ein Betrag sein")
    for k in ("nutzungsdauer", "start_jahr", "rest_nutzungsdauer"):
        if k in d:
            v = d.get(k)
            w[k] = int(v) if str(v or "").strip().isdigit() else None
    return w, fehler


def _anlage_pruefen(a):
    if not a.get("bezeichnung"):
        return "Bitte eine Bezeichnung angeben"
    if a.get("restwert_start") is not None:
        if not a.get("start_jahr") or not a.get("rest_nutzungsdauer"):
            return "Bei übernommenem Restwert bitte Jahr und verbleibende Nutzungsdauer angeben"
    elif not (a.get("anschaffung_am") and a.get("kosten") and a.get("nutzungsdauer")):
        return "Bitte Kaufdatum, Kosten und Nutzungsdauer angeben"
    if a.get("abgang_am") and a.get("anschaffung_am") and a["abgang_am"] < a["anschaffung_am"]:
        return "Der Abgang kann nicht vor dem Kauf liegen"
    return None


@bp.get("/api/anlagen")
def anlagen_api():
    jahr = request.args.get("jahr")
    return jsonify(anlagen_liste(jahr if jahr and jahr.isdigit() else None))


@bp.post("/api/anlagen")
def anlage_anlegen():
    w, fehler = _anlage_werte(_daten())
    fehler_text = "; ".join(fehler) or _anlage_pruefen(w)
    if fehler_text:
        return _fehler(fehler_text)
    with db.connect() as con:
        aid = con.execute(f"INSERT INTO anlagen ({', '.join(w)}) VALUES ({', '.join('?' * len(w))})", list(w.values())).lastrowid
        r = dict(con.execute("SELECT * FROM anlagen WHERE id = ?", (aid,)).fetchone())
    return jsonify(r | {"plan": afa_plan(r)}), 201


@bp.put("/api/anlagen/<int:aid>")
def anlage_aendern(aid):
    with db.connect() as con:
        alt = con.execute("SELECT * FROM anlagen WHERE id = ?", (aid,)).fetchone() or abort(404)
    w, fehler = _anlage_werte(_daten())
    fehler_text = "; ".join(fehler) or _anlage_pruefen(dict(alt) | w)
    if fehler_text:
        return _fehler(fehler_text)
    with db.connect() as con:
        if w:
            con.execute(f"UPDATE anlagen SET {', '.join(k + ' = ?' for k in w)} WHERE id = ?", [*w.values(), aid])
        r = dict(con.execute("SELECT * FROM anlagen WHERE id = ?", (aid,)).fetchone())
    return jsonify(r | {"plan": afa_plan(r)})


@bp.delete("/api/anlagen/<int:aid>")
def anlage_loeschen(aid):
    with db.connect() as con:
        a = con.execute("SELECT * FROM anlagen WHERE id = ?", (aid,)).fetchone() or abort(404)
        if a["ausgabe_id"]:
            return _fehler("Dieses Gerät stammt aus einer Ausgabe – bitte dort die Kategorie ändern oder die Ausgabe löschen.", 409)
        con.execute("DELETE FROM anlagen WHERE id = ?", (aid,))
    return "", 204


def anlage_zur_ausgabe(aid):
    """Ausgabe der Kategorie „Anschaffung über 800 €“ → Gerät im Anlagenverzeichnis anlegen bzw. abgleichen;
    andere Kategorie → automatisch angelegtes Gerät wieder entfernen."""
    a = holen(aid)
    if not a or a["status"] != "ok":
        return
    with db.connect() as con:
        vorhanden = con.execute("SELECT id FROM anlagen WHERE ausgabe_id = ?", (aid,)).fetchone()
        if a["kategorie"] != "anschaffung":
            if vorhanden:
                con.execute("DELETE FROM anlagen WHERE id = ?", (vorhanden["id"],))
                con.execute("UPDATE ausgaben SET anlage_id = NULL WHERE id = ?", (aid,))
            return
        a_ein = _einstellungen()
        kosten = a["betrag"] or 0
        if not a_ein.get("kleinunternehmer") and a.get("ust_satz"):
            kosten = round(kosten / (1 + a["ust_satz"] / 100), 2)    # Umsatzsteuerpflichtige schreiben netto ab
        bezeichnung = a["beschreibung"] or a["lieferant"]
        datum = a["bezahlt_am"] or a["belegdatum"]
        if vorhanden:
            con.execute("UPDATE anlagen SET kosten = ?, anschaffung_am = ? WHERE id = ?", (kosten, datum, vorhanden["id"]))
        else:
            nid = con.execute("INSERT INTO anlagen (bezeichnung, anschaffung_am, kosten, nutzungsdauer, ausgabe_id) VALUES (?, ?, ?, ?, ?)",
                              (bezeichnung, datum, kosten, nutzungsdauer_vorschlag(f"{bezeichnung} {a['lieferant']}"), aid)).lastrowid
            con.execute("UPDATE ausgaben SET anlage_id = ? WHERE id = ?", (nid, aid))


# ======================= EÜR (Einnahmen-Überschuss-Rechnung) =======================

def _r2(v):
    return round(v + 0.0, 2)


def euer(jahr, a=None):
    """EÜR eines Jahres: Einnahmen nach Zahlungseingang, Ausgaben nach Bezahlt-Datum, Fahrten, Abschreibung.
    Kleinunternehmer rechnen brutto; Umsatzsteuerpflichtige netto mit Umsatzsteuer/Vorsteuer als eigenen Zeilen."""
    a = a or _einstellungen()
    jahr = str(jahr)
    ku = bool(a.get("kleinunternehmer"))
    monate = {m: {"einnahmen": 0.0, "ausgaben": 0.0} for m in range(1, 13)}

    # --- Einnahmen ---
    rechnungen = db.list_invoices()
    erloese = umsatzsteuer = 0.0
    anzahl = 0
    for r in rechnungen:
        netto = sum(float(p.get("preis") or 0) for p in r["positionen"])
        ust = r["gesamt"] - netto if r.get("ust_satz") else 0.0
        if r.get("storno_von"):
            orig = next((x for x in rechnungen if x["id"] == r["storno_von"]), None)
            if not (orig and orig["bezahlt"] and r["datum"].startswith(jahr)):
                continue                      # unbezahlte Rechnung storniert → keine Geldbewegung
            datum = r["datum"]
        elif r["bezahlt"] and r.get("bezahlt_am", "") and r["bezahlt_am"].startswith(jahr):
            datum = r["bezahlt_am"]
            anzahl += 1
        else:
            continue
        erloese += netto if not ku else r["gesamt"]
        umsatzsteuer += 0 if ku else ust
        monate[int(datum[5:7])]["einnahmen"] += r["gesamt"]
    with db.connect() as con:
        sonstige = [dict(x) for x in con.execute("SELECT * FROM einnahmen_sonstige WHERE datum LIKE ? ORDER BY datum", (f"{jahr}%",))]
    sonstige_summe = 0.0
    for e in sonstige:
        brutto = e["betrag"]
        netto = brutto / (1 + e["ust_satz"] / 100) if e.get("ust_satz") and not ku else brutto
        sonstige_summe += netto
        umsatzsteuer += brutto - netto
        monate[int(e["datum"][5:7])]["einnahmen"] += brutto

    # --- Anschaffungen: Abschreibung, Abgänge ---
    anlagen = anlagen_liste(jahr)
    afa = sum(x["afa"] for x in anlagen)
    abgang_restwert = sum(x["abgang_restwert"] for x in anlagen)
    abgang_erloes = sum(x["abgang_erloes"] for x in anlagen)
    monate[12]["ausgaben"] += afa + abgang_restwert
    monate[12]["einnahmen"] += abgang_erloes

    # --- Ausgaben ---
    kategorien = {k: 0.0 for k in KATEGORIEN}
    vorsteuer = 0.0
    with db.connect() as con:
        ausgaben = [dict(x) for x in con.execute(
            "SELECT * FROM ausgaben WHERE status = 'ok' AND COALESCE(bezahlt_am, belegdatum) LIKE ?", (f"{jahr}%",))]
    for x in ausgaben:
        if x["kategorie"] == "anschaffung":
            continue                          # über die Abschreibung
        brutto = (x["betrag"] or 0) * (1 - (x.get("privatanteil") or 0) / 100)
        netto = brutto / (1 + x["ust_satz"] / 100) if x.get("ust_satz") and not ku and x["kategorie"] != "ust" else brutto
        kategorien[x["kategorie"]] = kategorien.get(x["kategorie"], 0) + netto
        vorsteuer += brutto - netto
        monate[int((x["bezahlt_am"] or x["belegdatum"])[5:7])]["ausgaben"] += brutto

    privat = a.get("fahrzeug", "privat") != "betrieb"
    fahrten = fahrten_liste(jahr)
    fahrtkosten = sum(f["betrag"] or 0 for f in fahrten) if privat else 0.0
    if privat:
        for f in fahrten:
            monate[int(f["datum"][5:7])]["ausgaben"] += f["betrag"] or 0

    zeilen_aus = [{"id": k, "name": KATEGORIEN[k][0], "euer": KATEGORIEN[k][1], "betrag": _r2(v)}
                  for k, v in kategorien.items() if v and k != "anschaffung"]
    if fahrtkosten:
        zeilen_aus.append({"id": "fahrten", "name": "Fahrten (Kilometerpauschale)", "euer": "Fahrten mit dem Privatfahrzeug", "betrag": _r2(fahrtkosten)})
    if afa:
        zeilen_aus.append({"id": "afa", "name": "Abschreibungen", "euer": "Absetzung für Abnutzung (AfA)", "betrag": _r2(afa)})
    if abgang_restwert:
        zeilen_aus.append({"id": "abgang", "name": "Restwert verkaufter/verschrotteter Geräte", "euer": "Restbuchwert ausgeschiedener Anlagegüter", "betrag": _r2(abgang_restwert)})
    if vorsteuer:
        zeilen_aus.append({"id": "vorsteuer", "name": "Gezahlte Vorsteuer", "euer": "Vorsteuerbeträge", "betrag": _r2(vorsteuer)})
    zeilen_aus.sort(key=lambda z: -z["betrag"])
    zeilen_ein = [z for z in (
        {"id": "rechnungen", "name": "Rechnungen (nach Zahlungseingang)" + ("" if ku else ", netto"), "betrag": _r2(erloese)},
        {"id": "sonstige", "name": "Sonstige Einnahmen", "betrag": _r2(sonstige_summe)},
        {"id": "abgang_erloes", "name": "Verkauf von Geräten", "betrag": _r2(abgang_erloes)},
        {"id": "umsatzsteuer", "name": "Vereinnahmte Umsatzsteuer", "betrag": _r2(umsatzsteuer)}) if z["betrag"] or z["id"] == "rechnungen"]
    einnahmen = _r2(sum(z["betrag"] for z in zeilen_ein))
    ausgaben_summe = _r2(sum(z["betrag"] for z in zeilen_aus))
    return {"jahr": int(jahr), "kleinunternehmer": ku, "einnahmen": einnahmen, "ausgaben": ausgaben_summe,
            "gewinn": _r2(einnahmen - ausgaben_summe), "einnahmen_zeilen": zeilen_ein, "ausgaben_zeilen": zeilen_aus,
            "anzahl_rechnungen": anzahl, "fahrtkosten": _r2(fahrtkosten), "afa": _r2(afa), "sonstige": sonstige,
            "monate": [{"monat": m, "einnahmen": _r2(v["einnahmen"]), "ausgaben": _r2(v["ausgaben"])} for m, v in monate.items()],
            "pruefliste": pruefliste(jahr, a, rechnungen)}


def pruefliste(jahr, a, rechnungen=None):
    """Hinweise vor dem Export: (stufe ok|warn|info, text, aktion)."""
    rechnungen = rechnungen if rechnungen is not None else db.list_invoices()
    jahr = str(jahr)
    p = []
    with db.connect() as con:
        neu = con.execute("SELECT COUNT(*) FROM ausgaben WHERE status = 'neu'").fetchone()[0]
        ohne_beleg = con.execute("SELECT COUNT(*) FROM ausgaben WHERE status = 'ok' AND beleg_datei IS NULL"
                                 " AND COALESCE(bezahlt_am, belegdatum) LIKE ?", (f"{jahr}%",)).fetchone()[0]
        tank = con.execute("SELECT COUNT(*) FROM ausgaben WHERE status = 'ok' AND kategorie = 'fahrzeug'"
                           " AND COALESCE(bezahlt_am, belegdatum) LIKE ?", (f"{jahr}%",)).fetchone()[0]
        km_fehlen = con.execute("SELECT COUNT(*) FROM fahrten WHERE km_einfach IS NULL AND datum LIKE ?", (f"{jahr}%",)).fetchone()[0]
    ohne_datum = [r for r in rechnungen if r["bezahlt"] and not r.get("bezahlt_am") and not r.get("storno_von")
                  and r["datum"][:4] in (jahr, str(int(jahr) - 1))]
    offen = [r for r in rechnungen if not r["bezahlt"] and not r.get("storno_von") and not r.get("storniert_durch") and r["datum"].startswith(jahr)]
    p.append(("warn", f"{neu} Beleg{'' if neu == 1 else 'e'} noch nicht geprüft", "ausgaben") if neu else ("ok", "Alle Belege geprüft", None))
    if ohne_datum:
        p.append(("warn", f"{len(ohne_datum)} bezahlte Rechnung{'' if len(ohne_datum) == 1 else 'en'} ohne Bezahlt-Datum – zählen erst, wenn das Datum nachgetragen ist", "bezahlt_am"))
    if km_fehlen:
        p.append(("warn", f"{km_fehlen} Fahrt{'' if km_fehlen == 1 else 'en'} ohne Kilometer", "fahrten"))
    if a.get("fahrzeug", "privat") != "betrieb":
        p.append(("warn", f"{tank} Ausgabe{'' if tank == 1 else 'n'} in der Kategorie „Fahrzeug“ – beim Privatfahrzeug dürfen Tankbelege usw. "
                          "nicht zusätzlich zur Kilometerpauschale angesetzt werden", "ausgaben") if tank else ("ok", "Keine Tankbelege (Privatfahrzeug)", None))
    if ohne_beleg:
        p.append(("info", f"{ohne_beleg} Ausgabe{'' if ohne_beleg == 1 else 'n'} ohne Beleg – mit Notiz", None))
    if offen:
        p.append(("info", f"{len(offen)} Rechnung{'' if len(offen) == 1 else 'en'} des Jahres noch offen – zählen erst bei Zahlung", None))
    if not a.get("kleinunternehmer"):
        p.append(("info", "Umsatzsteuer-Zahlungen an das Finanzamt bitte als Ausgabe (Kategorie „Umsatzsteuer an das Finanzamt“) erfassen", None))
    return [{"stufe": s, "text": t, "aktion": x} for s, t, x in p]


@bp.get("/api/finanzen/euer")
def euer_api():
    jahr = request.args.get("jahr") or str(date.today().year)
    if not jahr.isdigit():
        abort(400)
    return jsonify(euer(jahr))


@bp.get("/api/finanzen/ohne-bezahltdatum")
def ohne_bezahltdatum():
    return jsonify([{"id": r["id"], "nummer": r["nummer"], "datum": r["datum"], "kunde": r["kunde"].get("name", ""), "gesamt": r["gesamt"]}
                    for r in db.list_invoices() if r["bezahlt"] and not r.get("bezahlt_am") and not r.get("storno_von")])


@bp.post("/api/finanzen/bezahlt-am-rechnungsdatum")
def bezahlt_am_aus_rechnungsdatum():
    """Alle bezahlten Rechnungen ohne Bezahlt-Datum bekommen ihr Rechnungsdatum (z. B. nach einem Import)."""
    with db.connect() as con:
        n = con.execute("UPDATE rechnungen SET bezahlt_am = datum WHERE bezahlt = 1 AND bezahlt_am IS NULL"
                        " AND storno_von IS NULL").rowcount
    return jsonify({"anzahl": n})


@bp.put("/api/rechnungen/<int:inv_id>/bezahlt_am")
def bezahlt_am_setzen(inv_id):
    d = (_daten().get("bezahlt_am") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return _fehler("Bitte ein Datum angeben")
    with db.connect() as con:
        if not con.execute("UPDATE rechnungen SET bezahlt_am = ? WHERE id = ? AND bezahlt = 1", (d, inv_id)).rowcount:
            return _fehler("Nur bei bezahlten Rechnungen möglich", 404)
    return "", 204


@bp.get("/api/einnahmen")
def einnahmen_liste():
    jahr = request.args.get("jahr") or str(date.today().year)
    with db.connect() as con:
        return jsonify([dict(x) for x in con.execute("SELECT * FROM einnahmen_sonstige WHERE datum LIKE ? ORDER BY datum DESC", (f"{jahr}%",))])


@bp.post("/api/einnahmen")
def einnahme_anlegen():
    d = _daten()
    datum, text = (d.get("datum") or "").strip(), (d.get("beschreibung") or "").strip()
    try:
        betrag = round(float(str(d.get("betrag")).replace(".", "").replace(",", ".") if "," in str(d.get("betrag")) else d.get("betrag")), 2)
    except (TypeError, ValueError):
        return _fehler("Bitte einen Betrag angeben")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum) or not text:
        return _fehler("Bitte Datum und Beschreibung angeben")
    satz = float(d["ust_satz"]) if str(d.get("ust_satz") or "").replace(".", "").isdigit() else None
    with db.connect() as con:
        eid = con.execute("INSERT INTO einnahmen_sonstige (datum, beschreibung, betrag, ust_satz) VALUES (?, ?, ?, ?)",
                          (datum, text, betrag, satz)).lastrowid
    return jsonify({"id": eid}), 201


@bp.delete("/api/einnahmen/<int:eid>")
def einnahme_loeschen(eid):
    with db.connect() as con:
        con.execute("DELETE FROM einnahmen_sonstige WHERE id = ?", (eid,))
    return "", 204


# ======================= Export für den Steuerberater =======================

def _csv(zeilen):
    import csv
    import io
    buf = io.StringIO()
    csv.writer(buf, delimiter=";").writerows(zeilen)
    return "﻿" + buf.getvalue()           # BOM: Excel erkennt Umlaute


def _b(v):
    return "" if v is None else f"{v:.2f}".replace(".", ",")


def export_finanzen(zf, jahr, a):
    """EÜR, Einnahmen, Ausgaben, Fahrten, Anlagenverzeichnis als CSV und alle Ausgaben-Belege in die Export-ZIP."""
    e = euer(jahr, a)
    zeilen = [["Bereich", "Position", "Zuordnung Anlage EÜR", "Betrag (EUR)"]]
    zeilen += [["Betriebseinnahmen", z["name"], "", _b(z["betrag"])] for z in e["einnahmen_zeilen"]]
    zeilen.append(["Betriebseinnahmen", "Summe", "", _b(e["einnahmen"])])
    zeilen += [["Betriebsausgaben", z["name"], z.get("euer", ""), _b(z["betrag"])] for z in e["ausgaben_zeilen"]]
    zeilen.append(["Betriebsausgaben", "Summe", "", _b(e["ausgaben"])])
    zeilen += [[], ["Gewinn", "", "", _b(e["gewinn"])], [],
               [f"Erstellt mit DJ Office Studio am {date.today():%d.%m.%Y} – "
                f"{'Kleinunternehmer (brutto)' if e['kleinunternehmer'] else 'umsatzsteuerpflichtig (netto)'}; ohne Gewähr, bitte prüfen."]]
    zf.writestr(f"EUeR_{jahr}.csv", _csv(zeilen))

    ein = [["Zahlungsdatum", "Art", "Nummer / Beschreibung", "Kunde", "Betrag (EUR)"]]
    for r in sorted(db.list_invoices(), key=lambda r: r.get("bezahlt_am") or r["datum"]):
        if r["bezahlt"] and not r.get("storno_von") and (r.get("bezahlt_am") or "").startswith(str(jahr)):
            ein.append([r["bezahlt_am"], "Rechnung", r["nummer"], r["kunde"].get("name", ""), _b(r["gesamt"])])
        elif r.get("storno_von") and r["datum"].startswith(str(jahr)) and r["gesamt"]:
            orig = db.get_invoice(r["storno_von"])
            if orig and orig["bezahlt"]:
                ein.append([r["datum"], "Storno (Erstattung)", r["nummer"], r["kunde"].get("name", ""), _b(r["gesamt"])])
    ein += [[x["datum"], "Sonstige Einnahme", x["beschreibung"], "", _b(x["betrag"])] for x in e["sonstige"]]
    zf.writestr(f"Einnahmen_{jahr}.csv", _csv(ein))

    aus = [["Bezahlt am", "Belegdatum", "Lieferant", "Beschreibung", "Kategorie", "Betrag brutto (EUR)", "USt-Satz",
            "Privatanteil %", "Betrieblich (EUR)", "Beleg-Datei", "Notiz"]]
    benutzt = set()
    with db.connect() as con:
        liste_ = [_zeile(x) for x in con.execute("SELECT * FROM ausgaben WHERE status = 'ok' AND COALESCE(bezahlt_am, belegdatum) LIKE ?"
                                                 " ORDER BY COALESCE(bezahlt_am, belegdatum), id", (f"{jahr}%",))]
    for x in liste_:
        datei = ""
        if x.get("beleg_datei"):
            pfad = os.path.join(db.DATA_DIR, x["beleg_datei"])
            if os.path.isfile(pfad):
                endung = os.path.splitext(x["beleg_name"] or x["beleg_datei"])[1].lower() or ".dat"
                stamm = _dateiname(f"{x['bezahlt_am'] or x['belegdatum']}_{x['lieferant']}_{_b(x['betrag'])}")
                datei, n = f"{stamm}{endung}", 2
                while datei in benutzt:
                    datei, n = f"{stamm}_{n}{endung}", n + 1
                benutzt.add(datei)
                zf.write(pfad, f"Belege/{datei}")
        betrieblich = (x["betrag"] or 0) * (1 - (x.get("privatanteil") or 0) / 100)
        aus.append([x["bezahlt_am"] or "", x["belegdatum"] or "", x["lieferant"], x["beschreibung"], x["kategorie_name"],
                    _b(x["betrag"]), f"{x['ust_satz']:g} %" if x.get("ust_satz") else "", f"{x.get('privatanteil') or 0:g}",
                    _b(betrieblich), datei, x.get("notiz") or ""])
    zf.writestr(f"Ausgaben_{jahr}.csv", _csv(aus))

    fa = [["Datum", "Anlass", "Kunde", "Start", "Ziel", "km einfach", "Hin und zurück", "km gesamt", "Satz (EUR/km)", "Betrag (EUR)", "Quelle"]]
    for f in sorted(fahrten_liste(jahr), key=lambda f: f["datum"]):
        fa.append([f["datum"], f["anlass"], f.get("kunde") or "", f["start"], f["ziel"], _b(f["km_einfach"]).replace(",00", ""),
                   "ja" if f["hin_zurueck"] else "nein", _b(f["km_gesamt"]).replace(",00", ""), _b(f["km_satz"]),
                   _b(f["betrag"]), {"auto": "automatisch", "korrigiert": "korrigiert", "hand": "von Hand"}.get(f["quelle"], f["quelle"])])
    if a.get("fahrzeug") == "betrieb":
        fa.append(["Hinweis: Betriebsfahrzeug – Fahrten nur als Nachweis, nicht als Ausgabe angesetzt."])
    zf.writestr(f"Fahrten_{jahr}.csv", _csv(fa))

    an = [["Gerät", "Kaufdatum", "Kosten (EUR)", "Nutzungsdauer (Jahre)", "Wert 1.1. bzw. Zugang (EUR)", f"Abschreibung {jahr} (EUR)",
           "Restwert 31.12. (EUR)", "Abgang am", "Restwert bei Abgang (EUR)", "Verkaufserlös (EUR)"]]
    for x in anlagen_liste(jahr):
        an.append([x["bezeichnung"], x.get("anschaffung_am") or f"(übernommen, Restwert 1.1.{x.get('start_jahr')})", _b(x.get("kosten")),
                   x.get("nutzungsdauer") or (f"noch {x.get('rest_nutzungsdauer')}" if x.get("rest_nutzungsdauer") else ""),
                   _b(x["restwert_anfang"]), _b(x["afa"]), _b(x["restwert_ende"]), x.get("abgang_am") or "",
                   _b(x["abgang_restwert"]) if x.get("abgang_am") else "", _b(x["abgang_erloes"]) if x.get("abgang_am") else ""])
    zf.writestr(f"Anlagenverzeichnis_{jahr}.csv", _csv(an))


# ---------- Paperless-ngx: Belege mit einem Tag abholen (nur per Knopf) ----------

import paperless  # noqa: E402

_pl_sperre = threading.Lock()
_pl_status = {"laeuft": False}


def _pl_zugang(d=None):
    """Adresse und Token – aus der Anfrage (Einstellungen noch nicht gespeichert) oder den gespeicherten Einstellungen."""
    a, d = _einstellungen(), d or {}
    url = paperless.adresse(d.get("url") if d.get("url") is not None else a.get("paperless_url"))
    token = (d.get("token") or "").strip() or a.get("paperless_token") or ""
    return url, token


def _pl_https(url):
    return _ssl() if url.lower().startswith("https") else None


def paperless_abholen():
    """Alle Dokumente mit dem Tag holen, die noch nicht übernommen sind (läuft im Hintergrund, Stand in _pl_status)."""
    st = _pl_status
    try:
        a = _einstellungen()
        url, token = _pl_zugang()
        tag = int(a.get("paperless_tag") or 0)
        if not url or not token or not tag:
            raise paperless.PaperlessFehler("Paperless ist noch nicht eingerichtet (⚙ Einstellungen → Paperless)")
        ssl_k = _pl_https(url)
        st["meldung"] = "Dokumente werden gesucht …"
        docs = paperless.dokumente(url, token, tag, ssl_k)
        with db.connect() as con:
            schon = {r[0] for r in con.execute("SELECT paperless_id FROM ausgaben WHERE paperless_id IS NOT NULL")}
        offen = [d for d in docs if d["id"] not in schon]
        st.update(gesamt=len(offen), vorhanden=len(docs) - len(offen), meldung="")
        namen = paperless.korrespondenten(url, token, ssl_k) if offen else {}
        for d in offen:
            try:
                daten, name, _typ = paperless.herunterladen(url, token, d["id"], ssl_k)
                name = name or d.get("original_file_name") or f"{d.get('title') or 'Paperless'}.pdf"
                datum = str(d.get("created_date") or d.get("created") or "")[:10] or None
                a_neu, vorhanden = beleg_aufnehmen(name, daten, {
                    "id": d["id"], "korrespondent": namen.get(d.get("correspondent")), "datum": datum,
                    "titel": (d.get("title") or "").strip() or None, "text": d.get("content") or ""})
                if a_neu:
                    st["neu"] += 1
                else:   # gleicher Beleg schon von Hand hochgeladen → mit Paperless verknüpfen, damit er nicht erneut kommt
                    with db.connect() as con:
                        con.execute("UPDATE ausgaben SET paperless_id = ? WHERE id = ? AND paperless_id IS NULL", (d["id"], vorhanden))
                    st["doppelt"] += 1
            except paperless.PaperlessFehler:
                raise
            except Exception as e:   # ein kaputtes Dokument hält den Rest nicht auf
                st["fehler"].append(f"{d.get('title') or d['id']} ({type(e).__name__})")
            st["fertig"] += 1
    except paperless.PaperlessFehler as e:
        st["abbruch"] = str(e)
    except Exception as e:
        st["abbruch"] = f"Abholen fehlgeschlagen ({type(e).__name__})"
    finally:
        st["laeuft"] = False
        _pl_sperre.release()


@bp.post("/api/paperless/abholen")
def paperless_abholen_start():
    if not _pl_sperre.acquire(blocking=False):
        return jsonify(_pl_status)
    _pl_status.clear()
    _pl_status.update(laeuft=True, gesamt=None, fertig=0, neu=0, doppelt=0, vorhanden=0, fehler=[], abbruch=None,
                      meldung="Verbindung zu Paperless …")
    _im_hintergrund(paperless_abholen)
    return jsonify(_pl_status)


@bp.get("/api/paperless/abholen")
def paperless_abholen_stand():
    return jsonify(_pl_status)


@bp.post("/api/paperless/verbinden")
def paperless_verbinden():
    """Einstellungen: Verbindung prüfen und Tags laden. Ohne Adresse wird nach Paperless gesucht."""
    d = _daten()
    url, token = _pl_zugang(d)
    benutzer, passwort = (d.get("benutzer") or "").strip(), d.get("passwort") or ""
    versucht, gefunden, erster_fehler = [], None, None
    # Zuerst die eingetragene/gespeicherte Adresse; antwortet dort kein Paperless, wird gesucht (eine früher
    # automatisch gefundene, aber falsche Adresse blockiert so nichts). Gespeichert wird erst nach Erfolg.
    while True:
        if not url or (versucht and url in versucht):
            url, gefunden = paperless.suchen(ausser=versucht)
            if not url:
                return _fehler(erster_fehler or gefunden)
        versucht.append(url)
        if not paperless.erreichbar(url):
            erster_fehler = erster_fehler or f"Unter {url} antwortet kein Paperless."
            url = None
            continue
        try:
            neu = paperless.token_holen(url, benutzer, passwort, _pl_https(url)) if benutzer and passwort else None
            if not (neu or token):
                return jsonify({"url": url, "gefunden": gefunden, "tags": None,
                                "hinweis": f"{gefunden or 'Paperless erreichbar'} – jetzt mit Benutzername und Passwort anmelden."})
            tags = paperless.tags(url, neu or token, _pl_https(url))
        except paperless.PaperlessFehler as e:
            return _fehler(str(e))
        db.save_settings({"paperless_url": url} | ({"paperless_token": neu} if neu else {}))
        return jsonify({"url": url, "gefunden": gefunden, "token_gespeichert": bool(neu), "tags": tags})


# ---------- Belege-Ordner: alles, was dort landet, automatisch einlesen ----------

import glob  # noqa: E402
import shutil  # noqa: E402
import time  # noqa: E402

BELEG_ENDUNGEN = (".pdf", ".eml", ".msg", ".mbox", ".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp")
UEBERNOMMEN, NICHT_LESBAR = "übernommen", "nicht lesbar"
ORDNER_TAKT = 60          # Sekunden zwischen zwei Durchläufen im Hintergrund
_ordner_sperre = threading.Lock()
_ordner_stand = {"laeuft": False, "geprueft": None, "neu": 0, "doppelt": 0, "fehler": [], "problem": None}


def belege_ordner(a=None):
    return ((a or _einstellungen()).get("belege_ordner") or "").strip()


def _ordner_liste(muster):
    """Pfad mit Platzhaltern (z. B. …/DJ/*/Ausgaben für alle Jahre) → vorhandene Ordner."""
    if glob.has_magic(muster):
        return sorted(p for p in glob.glob(muster) if os.path.isdir(p))
    return [muster] if os.path.isdir(muster) else []


def _schon_gesehen(pfad):
    """Nur-lesen-Modus: Datei unverändert seit dem letzten Einlesen?"""
    s = os.stat(pfad)
    with db.connect() as con:
        r = con.execute("SELECT groesse, geaendert FROM belege_ordner_dateien WHERE pfad = ?", (pfad,)).fetchone()
    return bool(r) and r["groesse"] == s.st_size and r["geaendert"] == s.st_mtime


def _gesehen_merken(pfad):
    s = os.stat(pfad)
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO belege_ordner_dateien (pfad, groesse, geaendert) VALUES (?, ?, ?)",
                    (pfad, s.st_size, s.st_mtime))


def _ordner_dateien(ordner, ruhe=5):
    """Belegdateien im Ordner (auch in Unterordnern), ohne „übernommen“/„nicht lesbar“, versteckte Dateien und
    Dateien, die gerade noch geschrieben werden (in den letzten Sekunden geändert)."""
    jetzt = time.time()
    for wurzel, ordner_namen, namen in os.walk(ordner):
        ordner_namen[:] = [o for o in ordner_namen if not o.startswith(".") and
                           not (wurzel == ordner and o in (UEBERNOMMEN, NICHT_LESBAR))]
        for n in sorted(namen):
            pfad = os.path.join(wurzel, n)
            if n.startswith(".") or not (n.lower().endswith(BELEG_ENDUNGEN) or n == "mbox"):
                continue
            try:
                if jetzt - os.path.getmtime(pfad) >= ruhe:
                    yield pfad
            except OSError:
                continue


def _verschieben(pfad, ordner, ziel_name):
    """Datei nach <ordner>/<ziel_name>/<relativer Pfad> verschieben, ohne etwas zu überschreiben."""
    rel = os.path.relpath(pfad, ordner)
    ziel = os.path.join(ordner, ziel_name, rel)
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    stamm, endung = os.path.splitext(ziel)
    n = 2
    while os.path.exists(ziel):
        ziel = f"{stamm} ({n}){endung}"
        n += 1
    shutil.move(pfad, ziel)
    quelle = os.path.dirname(pfad)          # leer gewordene Unterordner aufräumen (nur leere, nie den Ordner selbst)
    while os.path.abspath(quelle) != os.path.abspath(ordner):
        try:
            os.rmdir(quelle)
        except OSError:
            break
        quelle = os.path.dirname(quelle)


def ordner_einlesen(ruhe=5):
    """Einen Durchlauf machen. Gibt den Stand zurück; läuft schon einer, passiert nichts."""
    st = _ordner_stand
    if not _ordner_sperre.acquire(blocking=False):
        return st
    try:
        st["laeuft"] = True
        a = _einstellungen()
        muster = belege_ordner(a)
        verschieben = a.get("belege_ordner_verschieben", True)
        st["problem"] = None
        if not muster:
            return st
        if not glob.has_magic(muster) and not os.path.isdir(muster) and verschieben:
            try:   # z. B. /share/belege beim ersten Start anlegen, wenn /share existiert
                if os.path.isdir(os.path.dirname(os.path.abspath(muster))):
                    os.makedirs(muster, exist_ok=True)
            except OSError:
                pass
        ordner_liste = _ordner_liste(muster)
        eigene = os.path.realpath(os.path.join(db.DATA_DIR, "belege"))   # Belegablage der App selbst
        if any(os.path.realpath(o) == eigene or os.path.realpath(o).startswith(eigene + os.sep) or
               eigene.startswith(os.path.realpath(o) + os.sep) for o in ordner_liste):
            st["problem"] = "Der Belege-Ordner darf nicht die Ablage der App selbst sein – bitte einen anderen Ordner wählen"
            return st
        if not ordner_liste:
            st["problem"] = f"Belege-Ordner {muster} wurde nicht gefunden"
            return st
        for ordner, pfad in [(o, p) for o in ordner_liste for p in _ordner_dateien(o, ruhe)]:
            if not verschieben and _schon_gesehen(pfad):
                continue
            name = os.path.basename(pfad)
            if name == "mbox":   # Apple-Mail-Export „Name.mbox/mbox“ → Name des Postfachs verwenden
                name = os.path.basename(os.path.dirname(pfad)) or name
            try:
                with open(pfad, "rb") as f:
                    daten = f.read()
                e = dateien_aufnehmen([(name, daten)])
            except Exception as x:
                e = {"neu": [], "doppelt": [], "fehler": [{"datei": name, "fehler": type(x).__name__}]}
            st["neu"] += len(e["neu"])
            st["doppelt"] += len(e["doppelt"])
            st["fehler"] = (st["fehler"] + [f["datei"] for f in e["fehler"]])[-20:]
            if not verschieben:   # fremde Ablage (z. B. Paperless): nichts anfassen, nur merken
                _gesehen_merken(pfad)
                continue
            try:
                _verschieben(pfad, ordner, NICHT_LESBAR if e["fehler"] and not (e["neu"] or e["doppelt"]) else UEBERNOMMEN)
            except OSError as x:
                st["problem"] = f"Konnte {name} nicht verschieben ({type(x).__name__}) – bitte Schreibrechte des Ordners prüfen"
                break
        return st
    finally:
        st["laeuft"] = False
        st["geprueft"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _ordner_sperre.release()


_ordner_waechter = []


def _ordner_schleife():
    while True:
        try:
            ordner_einlesen()
        except Exception:   # der Wächter darf nie sterben
            pass
        time.sleep(ORDNER_TAKT)


@bp.before_app_request
def _ordner_waechter_starten():
    """Beim ersten Aufruf der App den Hintergrund-Wächter starten (in Tests ausgeschaltet)."""
    if HINTERGRUND and not _ordner_waechter:
        t = threading.Thread(target=_ordner_schleife, daemon=True, name="belege-ordner")
        _ordner_waechter.append(t)
        t.start()


@bp.post("/api/belege-ordner/einlesen")
def ordner_jetzt_einlesen():
    """Beim Öffnen der Ausgaben: sofort nachsehen (im Hintergrund), Stand zurückgeben."""
    vorher = (_ordner_stand["neu"], _ordner_stand["doppelt"])
    if HINTERGRUND:
        threading.Thread(target=ordner_einlesen, daemon=True).start()
        time.sleep(0.05)
    else:
        ordner_einlesen(ruhe=0)
    return jsonify(_ordner_status(vorher))


@bp.get("/api/belege-ordner")
def ordner_stand():
    return jsonify(_ordner_status())


def _ordner_status(vorher=None):
    return {**_ordner_stand, "ordner": belege_ordner(),
            "start_neu": vorher[0] if vorher else None, "start_doppelt": vorher[1] if vorher else None}


SUCH_WURZELN = ("/share", "/media")


@bp.post("/api/belege-ordner/suchen")
def ordner_suchen():
    """Ablage von Paperless finden: Ordner „Ausgaben“ unterhalb von …/documents/originals (in /share oder /media).
    Liegen sie je Jahr (DJ/2025/Ausgaben, DJ/2026/Ausgaben), wird daraus ein Muster mit * für alle Jahre."""
    wurzeln = [w for w in (_daten().get("wurzeln") or SUCH_WURZELN) if os.path.isdir(w)]
    funde = []
    for w in wurzeln:
        for wurzel, ordner_namen, _ in os.walk(w):
            tiefe = wurzel[len(w):].count(os.sep)
            if tiefe > 8 or os.path.basename(wurzel) in ("thumbnails", "archive", "consume", "trash", UEBERNOMMEN):
                ordner_namen[:] = []
                continue
            ordner_namen[:] = [o for o in ordner_namen if not o.startswith(".")]
            if "originals" in wurzel.split(os.sep):
                for o in ordner_namen:
                    if o.lower() == "ausgaben":
                        funde.append(os.path.join(wurzel, o))
    muster = []
    for p in funde:   # Jahreszahl im Pfad → *
        teile = p.split(os.sep)
        m = os.sep.join("*" if re.fullmatch(r"(19|20)\d\d", t) else t for t in teile)
        if m not in muster:
            muster.append(m)
    if not muster:
        return _fehler("Kein Ordner „Ausgaben“ in der Ablage von Paperless gefunden (gesucht in "
                       + ", ".join(wurzeln or SUCH_WURZELN) + "). Bitte den Pfad von Hand eintragen.")
    return jsonify({"muster": muster, "ordner": muster[0], "anzahl": sum(len(list(_ordner_dateien(o, 0)))
                                                                       for o in _ordner_liste(muster[0]))})

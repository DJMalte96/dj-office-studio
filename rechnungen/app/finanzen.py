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


def beleg_aufnehmen(name, daten):
    """Beleg speichern und auswerten → (neue Ausgabe | None, ID der vorhandenen bei Duplikat)."""
    pruef = belege.pruefsumme(daten)
    v = belege.auswerten(name, daten)
    vorhanden = _doppelt(pruef, v["message_id"])
    if vorhanden:
        return None, vorhanden
    kategorie = _kategorie_fuer(v["lieferant"]) or v["kategorie"] or "sonstiges"
    belegdatum = v["belegdatum"] or date.today().isoformat()
    with db.connect() as con:
        aid = con.execute(
            "INSERT INTO ausgaben (status, belegdatum, bezahlt_am, lieferant, beschreibung, kategorie, betrag, ust_satz,"
            " beleg_name, beleg_typ, beleg_pruefsumme, mail_message_id, erkannt_json) VALUES ('neu', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (belegdatum, belegdatum, v["lieferant"] or "", v["beschreibung"] or "", kategorie, v["betrag"], v["ust_satz"],
             name, v["typ"], pruef, v["message_id"], json.dumps(v))).lastrowid
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
    neu, doppelt, fehler = [], [], []
    for f in request.files.getlist("dateien"):
        daten = f.read()
        if not daten:
            continue
        try:
            a, vorhanden = beleg_aufnehmen(f.filename or "Beleg", daten)
        except Exception as e:   # defekte Datei darf den Rest nicht aufhalten
            fehler.append({"datei": f.filename, "fehler": f"Konnte nicht gelesen werden ({type(e).__name__})"})
            continue
        if vorhanden:
            doppelt.append({"datei": f.filename, "id": vorhanden})
        else:
            neu.append(a)
    return jsonify({"neu": neu, "doppelt": doppelt, "fehler": fehler})


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
    return jsonify(holen(aid))


@bp.delete("/api/ausgaben/<int:aid>")
def ausgabe_loeschen(aid):
    """Verwerfen (neu) bzw. löschen – die Belegdatei wird mit entfernt."""
    a = holen(aid) or abort(404)
    with db.connect() as con:
        con.execute("DELETE FROM ausgaben WHERE id = ?", (aid,))
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
            with db.connect() as con:
                con.execute("UPDATE fahrten SET km_einfach = ?, fehler = ? WHERE id = ?", (km, fehler, f["id"]))
            fertig += km is not None
        return fertig


@bp.get("/api/fahrten")
def fahrten_api_liste():
    jahr = request.args.get("jahr")
    a = _einstellungen()
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

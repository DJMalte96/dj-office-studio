"""Jahresabschluss (seit 1.8): Jahr prüfen, Paket mit Prüfsumme ablegen, Jahr sperren, wieder öffnen.

Ein Jahr wird nie von selbst gesperrt – nur, wenn man es unter Finanzen → EÜR & Export abschließt. Die Sperre selbst
sitzt in der Datenbank (Trigger in db.py): Sie weist jede Änderung ab, die die EÜR des Jahres verändern würde.
Ansehen, Herunterladen, erneut Verschicken und das Bezahlen offener Rechnungen in einem späteren Jahr gehen weiter.
"""
import hashlib
import io
import json
import os
import re
import tempfile
import threading
import zipfile
from datetime import date, datetime

from flask import Blueprint, Response, abort, jsonify, request, send_file

import db
import finanzen

bp = Blueprint("abschluss", __name__)

ORDNER = "abschluesse"
FRIST_TAGE = 10           # 10-Tage-Regel: Abschluss erst ab dem 11. Januar des Folgejahres
VORSCHLAEGE = ["Beleg nachgereicht", "Korrektur vom Steuerberater", "Tippfehler", "Zahlung falsch zugeordnet",
               "Rechnung storniert", "Fahrt nachgetragen"]
MAX_EIGENE_GRUENDE = 8
# Kategorien regelmäßiger Zahlungen, für die die 10-Tage-Regel infrage kommt (Abos, Verträge, Vorauszahlungen)
REGELMAESSIG = ("miete", "telefon", "versicherung", "buero", "musik", "ust")


class Gesperrt(Exception):
    """Eine Änderung würde ein abgeschlossenes Jahr verändern."""

    def __init__(self, jahre):
        self.jahre = sorted({int(j) for j in jahre})
        super().__init__(meldung(self.jahre))


def meldung(jahre):
    if not jahre:
        return "Diese Änderung betrifft ein abgeschlossenes Jahr."
    j = " und ".join(str(x) for x in jahre)
    eins = len(jahre) == 1
    return (f"{j} {'ist' if eins else 'sind'} abgeschlossen – diese Änderung würde {'das Jahr' if eins else 'sie'} verändern. "
            f"Zum Ändern unter Finanzen → EÜR & Export „{jahre[-1]} wieder öffnen“.")


def zu_jahre():
    return db.abgeschlossene_jahre()


def pruefen(*jahre):
    """Gesperrt auslösen, wenn eines der Jahre abgeschlossen ist (für Wege, die mehrere Schritte speichern)."""
    zu = zu_jahre()
    treffer = [int(j) for j in jahre if str(j or "").isdigit() and int(j) in zu]
    if treffer:
        raise Gesperrt(treffer)


def abschliessbar_ab(jahr):
    if int(jahr) >= date.max.year:      # vertipptes Jahr (z. B. 9999): nie abschließbar, aber kein Absturz
        return date.max
    return date(int(jahr) + 1, 1, FRIST_TAGE + 1)


def _app():
    import main   # zur Laufzeit (main bindet dieses Modul ein)
    return main


def fassungen(jahr):
    with db.connect() as con:
        return [dict(r) for r in con.execute("SELECT jahr, fassung, abgeschlossen_am, gewinn, pruefsumme, version, geoeffnet_am, grund"
                                             " FROM jahresabschluss WHERE jahr = ? ORDER BY fassung", (int(jahr),))]


def status(jahr, heute=None, abweichung=True):
    """offen | zu | laeuft (noch nicht abschließbar). Mit Fassungen und – falls zu – ob die EÜR heute noch dazu passt."""
    jahr = int(jahr)
    heute = heute or date.today()
    liste = fassungen(jahr)
    aktuell = liste[-1] if liste and not liste[-1]["geoeffnet_am"] else None
    st = "zu" if aktuell else ("offen" if heute >= abschliessbar_ab(jahr) else "laeuft")
    w = finanzen.einstellungen_im_jahr(jahr)
    out = {"jahr": jahr, "status": st, "abschliessbar_ab": abschliessbar_ab(jahr).isoformat(), "fassungen": liste,
           "aktuell": aktuell, "kleinunternehmer": bool(w.get("kleinunternehmer")), "fahrzeug": w.get("fahrzeug") or "privat"}
    if aktuell and abweichung:
        e = finanzen.euer(jahr)
        alt = json.loads(_euer_json(jahr, aktuell["fassung"]))
        out["abweichung"] = any(round(e[k] - alt.get(k, 0), 2) for k in ("einnahmen", "ausgaben", "gewinn"))
    return out


def _euer_json(jahr, fassung):
    with db.connect() as con:
        r = con.execute("SELECT euer_json FROM jahresabschluss WHERE jahr = ? AND fassung = ?", (int(jahr), int(fassung))).fetchone()
        return r[0] if r else "{}"


# ---------- Kleinunternehmer und Fahrzeug je Jahr ----------

def jahre_festhalten(a=None):
    """Vergangene Jahre ohne eigenen Eintrag bekommen die Einstellungen von jetzt (bzw. die übergebenen, z. B. die
    bisherigen vor einer Änderung). So wirkt eine spätere Änderung nicht mehr auf frühere Jahre zurück."""
    a = a or finanzen._einstellungen()
    aktuell = date.today().year
    zu = zu_jahre()
    with db.connect() as con:
        da = {r[0] for r in con.execute("SELECT jahr FROM jahr_einstellungen")}
        neu = [(j, int(bool(a.get("kleinunternehmer"))), a.get("fahrzeug") or "privat")
               for j in finanzen.jahre() if j < aktuell and j not in da and j not in zu]
        con.executemany("INSERT INTO jahr_einstellungen (jahr, kleinunternehmer, fahrzeug) VALUES (?, ?, ?)", neu)
    return len(neu)


# ---------- Prüfen ----------

def _de(iso):
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}" if iso and len(iso) >= 10 else (iso or "")


def _euro(v):
    return finanzen._euro(v or 0)


def zehn_tage_kandidaten(jahr):
    """Regelmäßige Zahlungen kurz vor bzw. nach dem Jahreswechsel → Ausgaben, die evtl. ins andere Jahr gehören."""
    jahr = int(jahr)
    with db.connect() as con:
        rows = [finanzen._zeile(r) for r in con.execute(
            "SELECT * FROM ausgaben WHERE status = 'ok' AND abo_id IS NULL AND kategorie IN (" + ",".join("?" * len(REGELMAESSIG)) + ")"
            " AND COALESCE(bezahlt_am, belegdatum) BETWEEN ? AND ? ORDER BY COALESCE(bezahlt_am, belegdatum)",
            (*REGELMAESSIG, f"{jahr}-12-{31 - FRIST_TAGE + 1:02d}", f"{jahr + 1}-01-{FRIST_TAGE:02d}"))]
    return rows


def pruefung(jahr):
    """Schritt 1 (Punkte) und Schritt 2 (Zahlen) des Assistenten."""
    jahr = int(jahr)
    e = finanzen.euer(jahr)
    vor = finanzen.euer(jahr - 1)
    rechnungen = db.list_invoices()
    punkte = []
    for p in e["pruefliste"]:
        if p["aktion"] == "grenzen":
            punkte.append({"stufe": "gelb", "text": p["text"]})
        elif p["stufe"] == "warn":
            punkte.append({"stufe": "rot", "text": p["text"], "aktion": p["aktion"]})
        elif p["stufe"] == "info" and "noch offen" in p["text"]:
            for r in rechnungen:
                if (not r["bezahlt"] and not r.get("storno_von") and not r.get("storniert_durch")
                        and r["datum"].startswith(str(jahr))):
                    punkte.append({"stufe": "gelb", "art": "offen", "id": r["id"],
                                   "text": f"Rechnung {r['nummer']} ({r['kunde'].get('name', '')}, {_euro(r['gesamt'])}) ist noch offen",
                                   "klein": f"Wurde sie {jahr} bezahlt? Sonst zählt sie, wenn das Geld kommt."})
        else:
            punkte.append({"stufe": "ok" if p["stufe"] == "ok" else "info", "text": p["text"]})
    import abos   # zur Laufzeit (abos bindet finanzen ein)
    offen = abos.offene_im_jahr(jahr)
    if offen:   # nicht bestätigte Abo-Abbuchungen: bestätigen oder „nicht abgebucht“ – sonst fehlen Ausgaben
        punkte.insert(0, {"stufe": "rot", "aktion": "ausgaben",
                          "text": f"{len(offen)} Abo-Abbuchung{'' if len(offen) == 1 else 'en'} {jahr} nicht bestätigt",
                          "klein": " · ".join(f"{f['lieferant']} {_de(f['datum'])}" for f in offen[:6]) + (" …" if len(offen) > 6 else "")})
    for a in zehn_tage_kandidaten(jahr):
        tag = a["bezahlt_am"] or a["belegdatum"]
        punkte.append({"stufe": "gelb", "art": "zehn_tage", "id": a["id"], "jahre": [jahr, jahr + 1], "gewaehlt": int(a["jahr"]),
                       "text": f"{a['lieferant'] or a['beschreibung'] or 'Ausgabe'}, {_euro(a['betrag'])}, bezahlt {_de(tag)}",
                       "klein": "Regelmäßige Zahlung um den Jahreswechsel (10-Tage-Regel): Zu welchem Jahr gehört sie?"})
    for r in rechnungen:
        if (r["bezahlt"] and not r.get("storno_von") and r["datum"].startswith(str(jahr))
                and (r.get("bezahlt_am") or "").startswith(str(jahr + 1))):
            punkte.append({"stufe": "ok", "text": f"Rechnung {r['nummer']} vom {_de(r['datum'])}, bezahlt {_de(r['bezahlt_am'])}",
                           "klein": f"Zählt nach dem Zahlungseingang zu {jahr + 1}."})
    w = finanzen.einstellungen_im_jahr(jahr)
    punkte.append({"stufe": "ok", "art": "einstellungen",
                   "text": f"{jahr}: {'Kleinunternehmer' if w.get('kleinunternehmer') else 'umsatzsteuerpflichtig'} · "
                           f"{'Betriebsfahrzeug' if w.get('fahrzeug') == 'betrieb' else 'Privatfahrzeug'}",
                   "klein": f"gilt nur für {jahr}"})
    with db.connect() as con:
        n_aus = con.execute(f"SELECT COUNT(*) FROM ausgaben WHERE status = 'ok' AND {finanzen.AUS_JAHR} = ?", (str(jahr),)).fetchone()[0]
    fahrten = finanzen.fahrten_liste(jahr)
    anlagen = [a for a in finanzen.anlagen_liste(jahr) if (a.get("anschaffung_am") or "").startswith(str(jahr))]
    zahl = lambda x: {k: x[k] for k in ("einnahmen", "ausgaben", "gewinn", "afa", "fahrtkosten", "anzahl_rechnungen")}
    return {"jahr": jahr, "status": status(jahr), "punkte": punkte, "offen": sum(p["stufe"] == "rot" for p in punkte),
            "zahlen": zahl(e) | {"ausgaben_anzahl": n_aus, "fahrten_anzahl": len(fahrten),
                                 "km": round(sum(f["km_gesamt"] or 0 for f in fahrten)), "anlagen_anzahl": len(anlagen)},
            "vorjahr": zahl(vor), "grenzen": (e.get("grenzen") or {}).get("hinweise", [])[:1]}


# ---------- Abschließen ----------

def _paket_name(jahr, fassung):
    return f"Jahresabschluss_{jahr}_Fassung_{fassung}.zip"


def _pruefsumme(summen):
    """{Dateiname: SHA-256} → (Gesamtsumme über die sortierte Liste, Liste als Text)."""
    text = "".join(f"{h}  {name}\n" for name, h in sorted(summen.items()))
    return hashlib.sha256(text.encode()).hexdigest(), text


_sperre = threading.Lock()     # immer nur ein Abschluss bzw. Wiederöffnen zur selben Zeit (zwei Geräte, Doppelklick)


def abschliessen(jahr, heute=None):
    if not _sperre.acquire(blocking=False):
        raise ValueError("Gerade wird schon ein Jahr abgeschlossen – bitte einen Moment warten und dann neu laden.")
    try:
        return _abschliessen(int(jahr), heute or date.today())
    finally:
        _sperre.release()


def _abschliessen(jahr, heute):
    st = status(jahr, heute, abweichung=False)
    if st["status"] == "zu":
        raise ValueError(f"{jahr} ist schon abgeschlossen.")
    if st["status"] == "laeuft":
        raise ValueError(f"{jahr} kann erst ab dem {_de(st['abschliessbar_ab'])} abgeschlossen werden.")
    p = pruefung(jahr)
    if p["offen"]:
        raise ValueError("Erst die rot markierten Punkte erledigen: " + "; ".join(x["text"] for x in p["punkte"] if x["stufe"] == "rot"))
    a = finanzen._einstellungen()
    w = finanzen.einstellungen_im_jahr(jahr, a)
    main = _app()
    vorher = fassungen(jahr)
    fassung = (vorher[-1]["fassung"] if vorher else 0) + 1
    jetzt = datetime.now().isoformat(timespec="seconds")
    # Erst sperren, dann rechnen und packen: Was in diesen Sekunden auf einem anderen Gerät geändert würde, weist die
    # Datenbank ab – das Paket zeigt also genau den gesperrten Stand.
    with db.connect() as con:
        con.execute("INSERT OR IGNORE INTO jahr_einstellungen (jahr, kleinunternehmer, fahrzeug) VALUES (?, ?, ?)",
                    (jahr, int(bool(w.get("kleinunternehmer"))), w.get("fahrzeug") or "privat"))
        con.execute("INSERT INTO jahresabschluss (jahr, fassung, abgeschlossen_am, gewinn, euer_json, pruefsumme, datei, version)"
                    " VALUES (?, ?, ?, 0, '{}', '', '', ?)", (jahr, fassung, jetzt, main.APP_VERSION))
    rel = os.path.join(ORDNER, _paket_name(jahr, fassung))
    ziel = os.path.join(db.DATA_DIR, rel)
    teil = ziel + ".teil"
    try:
        e = finanzen.euer(jahr)
        daten = {"app": "DJ Office Studio", "version": main.APP_VERSION, "jahr": jahr, "fassung": fassung, "abgeschlossen_am": jetzt,
                 "kleinunternehmer": bool(w.get("kleinunternehmer")), "fahrzeug": w.get("fahrzeug") or "privat",
                 "euer": {k: e[k] for k in ("einnahmen", "ausgaben", "gewinn", "einnahmen_zeilen", "ausgaben_zeilen", "afa", "fahrtkosten",
                                            "anzahl_rechnungen")}}
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        summen = {}
        # Stück für Stück: Belege werden nie ganz in den Arbeitsspeicher geladen
        with tempfile.TemporaryFile() as export:
            main.export_zip(str(jahr), a, ziel=export)
            export.seek(0)
            with zipfile.ZipFile(export) as quelle, zipfile.ZipFile(teil, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as paket:
                for info in quelle.infolist():
                    if info.is_dir() or info.filename in summen:
                        continue
                    h = hashlib.sha256()
                    with quelle.open(info) as src, paket.open(info.filename, "w", force_zip64=True) as dst:
                        while block := src.read(1024 * 1024):
                            h.update(block)
                            dst.write(block)
                    summen[info.filename] = h.hexdigest()
                inhalt = json.dumps(daten, ensure_ascii=False, indent=2).encode()
                summen["abschluss.json"] = hashlib.sha256(inhalt).hexdigest()
                paket.writestr("abschluss.json", inhalt)
                summe, liste = _pruefsumme(summen)
                verlauf = vorher + [{"fassung": fassung, "abgeschlossen_am": jetzt, "gewinn": e["gewinn"], "geoeffnet_am": None, "grund": None}]
                paket.writestr("Abschlussblatt.pdf", abschlussblatt(jahr, e, w, verlauf, summe, main.absender()))
                paket.writestr("Pruefsummen.txt", f"SHA-256 je Datei. Gesamt-Prüfsumme (SHA-256 dieser Liste ohne diese Kopfzeilen): {summe}\n"
                                                  "Das Abschlussblatt und diese Liste selbst sind nicht enthalten.\n\n" + liste)
        os.replace(teil, ziel)      # erst jetzt an seinen Platz – ein abgebrochener Versuch überschreibt nichts
        with db.connect() as con:
            con.execute("UPDATE jahresabschluss SET gewinn = ?, euer_json = ?, pruefsumme = ?, datei = ? WHERE jahr = ? AND fassung = ?",
                        (e["gewinn"], json.dumps(daten["euer"], ensure_ascii=False), summe, rel, jahr, fassung))
    except BaseException:
        with db.connect() as con:   # schiefgegangen: Sperre wieder aufheben
            con.execute("DELETE FROM jahresabschluss WHERE jahr = ? AND fassung = ?", (jahr, fassung))
        if os.path.exists(teil):
            os.remove(teil)
        raise
    return status(jahr, heute)


def oeffnen(jahr, grund):
    with _sperre:
        return _oeffnen(int(jahr), grund)


def _oeffnen(jahr, grund):
    grund = " ".join((grund or "").split())[:300]
    if not grund:
        raise ValueError("Bitte einen Grund angeben.")
    jetzt = datetime.now().isoformat(timespec="seconds")
    with db.connect() as con:
        n = con.execute("UPDATE jahresabschluss SET geoeffnet_am = ?, grund = ? WHERE jahr = ? AND geoeffnet_am IS NULL",
                        (jetzt, grund, jahr)).rowcount
    if not n:
        raise ValueError(f"{jahr} ist nicht abgeschlossen.")
    eigene = [t.strip() for t in grund.split(" · ") if t.strip() and t.strip() not in VORSCHLAEGE]
    if eigene:
        bisher = [g for g in db.get_settings().get("_abschluss_gruende") or [] if g not in eigene]
        db.save_settings({"_abschluss_gruende": (bisher + eigene)[-MAX_EIGENE_GRUENDE:]})
    return status(jahr)


# ---------- Abschlussblatt (PDF) ----------

def _zeit(iso):
    return f"{_de(iso[:10])}" if iso else ""


def abschlussblatt(jahr, e, w, verlauf, summe, absender):
    from fpdf import FPDF

    from pdf import _find_fonts
    reg, bold = _find_fonts()
    pdf = FPDF(format="A4")
    pdf.set_margins(22, 22, 22)
    pdf.set_auto_page_break(True, 22)
    pdf.add_font("Body", "", reg)
    pdf.add_font("Body", "B", bold)
    pdf.add_page()
    breite = pdf.w - 44

    def text(t, groesse=10.5, fett=False, farbe=(17, 17, 17), h=5.6):
        pdf.set_font("Body", "B" if fett else "", groesse)
        pdf.set_text_color(*farbe)
        pdf.multi_cell(breite, h, t, new_x="LMARGIN", new_y="NEXT")

    def zeile(links, rechts, fett=False, linie=True):
        pdf.set_font("Body", "B" if fett else "", 10.5)
        pdf.set_text_color(17, 17, 17)
        pdf.cell(breite - 40, 7.5, links)
        pdf.cell(40, 7.5, rechts, align="R", new_x="LMARGIN", new_y="NEXT")
        if linie:
            pdf.set_draw_color(220, 220, 220)
            pdf.line(22, pdf.get_y(), 22 + breite, pdf.get_y())

    text(f"Jahresabschluss {jahr}", 18, True, h=9)
    adresse = " · ".join(x for x in (absender.get("name"), absender.get("strasse"), absender.get("plz_ort")) if x)
    status_text = ("Kleinunternehmer (§ 19 UStG)" if w.get("kleinunternehmer") else "umsatzsteuerpflichtig (netto)") + " · " + \
                  ("Betriebsfahrzeug" if w.get("fahrzeug") == "betrieb" else "Privatfahrzeug")
    text(f"{adresse}\n{status_text}", 9.5, farbe=(85, 85, 85), h=5)
    pdf.ln(5)
    for z in e["einnahmen_zeilen"]:
        zeile(z["name"], _euro(z["betrag"]))
    zeile("Betriebseinnahmen gesamt", _euro(e["einnahmen"]), fett=True)
    pdf.ln(2)
    for z in e["ausgaben_zeilen"]:
        zeile(z["name"], _euro(z["betrag"]))
    zeile("Betriebsausgaben gesamt", _euro(e["ausgaben"]), fett=True)
    pdf.ln(1.5)
    pdf.set_draw_color(17, 17, 17)
    pdf.set_line_width(0.5)
    pdf.line(22, pdf.get_y(), 22 + breite, pdf.get_y())
    pdf.set_line_width(0.2)
    zeile("Gewinn", _euro(e["gewinn"]), fett=True, linie=False)

    pdf.ln(5)
    text("FASSUNGEN", 9.5, True, (60, 60, 60))
    pdf.ln(1)
    vorher = None
    for i, f in enumerate(verlauf):
        neu = i == len(verlauf) - 1
        diff = f" ({'+' if f['gewinn'] >= vorher else '−'}{_euro(abs(f['gewinn'] - vorher))})" if vorher is not None else ""
        text(f"Fassung {f['fassung']} · abgeschlossen am {_zeit(f['abgeschlossen_am'])} · Gewinn {_euro(f['gewinn'])}{diff}",
             10, neu, (17, 17, 17) if neu else (90, 90, 90))
        if f.get("geoeffnet_am"):
            text(f"Wieder geöffnet am {_zeit(f['geoeffnet_am'])}: „{f.get('grund') or ''}“", 10, farbe=(90, 90, 90))
        vorher = f["gewinn"]

    pdf.ln(5)
    text("PRÜFSUMME", 9.5, True, (60, 60, 60))
    text("SHA-256 über alle Dateien des Pakets (Liste in Pruefsummen.txt):", 10)
    pdf.set_font("Courier", "", 8.5)
    pdf.multi_cell(breite, 4.5, summe, new_x="LMARGIN", new_y="NEXT")
    text("Ändert sich eine Datei im Paket, stimmt die Prüfsumme nicht mehr.", 10)
    pdf.ln(6)
    text(f"Erstellt mit DJ Office Studio {_app().APP_VERSION} am {date.today():%d.%m.%Y}. Die Zuordnung zur Anlage EÜR ist ein "
         "Vorschlag und ersetzt keine Steuerberatung.", 8.5, farbe=(120, 120, 120), h=4.5)
    return bytes(pdf.output())


def _datei(jahr, fassung=None):
    with db.connect() as con:
        r = con.execute("SELECT datei, fassung FROM jahresabschluss WHERE jahr = ?" + (" AND fassung = ?" if fassung else "")
                        + " ORDER BY fassung DESC LIMIT 1", (int(jahr), int(fassung)) if fassung else (int(jahr),)).fetchone()
    if not r:
        abort(404)
    pfad = os.path.realpath(os.path.join(db.DATA_DIR, r["datei"]))
    if not pfad.startswith(os.path.realpath(os.path.join(db.DATA_DIR, ORDNER)) + os.sep) or not os.path.isfile(pfad):
        abort(404)
    return pfad, r["fassung"]


# ---------- Schnittstellen ----------

def _fehler(text, code=400):
    return jsonify({"error": text}), code


@bp.get("/api/abschluss")
def uebersicht():
    a = finanzen._einstellungen()
    heute = date.today()
    jahre = [status(j, heute, abweichung=False) for j in sorted(finanzen.jahre()) if j <= heute.year]
    offen = [s["jahr"] for s in jahre if s["status"] == "offen"]
    aus = db.get_settings().get("_abschluss_hinweis_aus")
    return jsonify({"jahre": jahre, "vorschlaege": VORSCHLAEGE, "gruende": db.get_settings().get("_abschluss_gruende") or [],
                    "hinweis": offen[-1] if offen and offen[-1] != aus else None,
                    "aktuell": {"kleinunternehmer": bool(a.get("kleinunternehmer")), "fahrzeug": a.get("fahrzeug") or "privat"}})


@bp.get("/api/abschluss/zu")
def zu_api():
    return jsonify(sorted(zu_jahre()))


@bp.get("/api/abschluss/<int:jahr>/pruefung")
def pruefung_api(jahr):
    return jsonify(pruefung(jahr))


@bp.post("/api/abschluss/<int:jahr>")
def abschliessen_api(jahr):
    if not (request.get_json(silent=True) or {}).get("bestaetigt"):
        return _fehler("Bitte bestätigen, dass die Zahlen geprüft sind.")
    try:
        return jsonify(abschliessen(jahr)), 201
    except ValueError as e:
        return _fehler(str(e), 409)


@bp.post("/api/abschluss/<int:jahr>/oeffnen")
def oeffnen_api(jahr):
    try:
        return jsonify(oeffnen(jahr, (request.get_json(silent=True) or {}).get("grund")))
    except ValueError as e:
        return _fehler(str(e))


@bp.post("/api/abschluss/hinweis-aus")
def hinweis_aus():
    jahr = (request.get_json(silent=True) or {}).get("jahr")
    db.save_settings({"_abschluss_hinweis_aus": int(jahr) if str(jahr or "").isdigit() else None})
    return "", 204


@bp.get("/api/abschluss/<int:jahr>/paket")
def paket(jahr):
    pfad, fassung = _datei(jahr, request.args.get("fassung", type=int))
    return send_file(pfad, mimetype="application/zip", as_attachment=True, download_name=_paket_name(jahr, fassung))


@bp.get("/api/abschluss/<int:jahr>/blatt")
def blatt(jahr):
    pfad, fassung = _datei(jahr, request.args.get("fassung", type=int))
    with zipfile.ZipFile(pfad) as zf:
        daten = zf.read("Abschlussblatt.pdf")
    return Response(daten, mimetype="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="Abschlussblatt_{jahr}_Fassung_{fassung}.pdf"'})


@bp.put("/api/abschluss/<int:jahr>/einstellungen")
def jahr_einstellungen(jahr):
    """Kleinunternehmer und Fahrzeug für ein vergangenes, offenes Jahr (das laufende folgt den Einstellungen oben)."""
    if jahr >= date.today().year:
        return _fehler("Für das laufende Jahr gelten die Einstellungen oben.")
    d = request.get_json(silent=True) or {}
    if d.get("fahrzeug") not in ("privat", "betrieb") or not isinstance(d.get("kleinunternehmer"), bool):
        return _fehler("Bitte Kleinunternehmer (ja/nein) und Fahrzeug (privat/betrieb) angeben.")
    with db.connect() as con:   # abgeschlossenes Jahr: Trigger weist ab
        con.execute("INSERT INTO jahr_einstellungen (jahr, kleinunternehmer, fahrzeug) VALUES (?, ?, ?)"
                    " ON CONFLICT(jahr) DO UPDATE SET kleinunternehmer = excluded.kleinunternehmer, fahrzeug = excluded.fahrzeug",
                    (jahr, int(d["kleinunternehmer"]), d["fahrzeug"]))
    return jsonify(status(jahr))


@bp.put("/api/ausgaben/<int:aid>/euer-jahr")
def euer_jahr(aid):
    """10-Tage-Regel: regelmäßige Zahlung um den Jahreswechsel dem anderen Jahr zuordnen (oder zurück)."""
    a = finanzen.holen(aid) or abort(404)
    tag = a["bezahlt_am"] or a["belegdatum"] or ""
    if a["status"] != "ok" or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", tag):
        return _fehler("Nur bei übernommenen Ausgaben mit Datum möglich.")
    jahr = (request.get_json(silent=True) or {}).get("jahr")
    j = int(tag[:4])
    dez, jan = tag[5:] >= f"12-{31 - FRIST_TAGE + 1:02d}", tag[5:] <= f"01-{FRIST_TAGE:02d}"
    erlaubt = {j} | ({j + 1} if dez else set()) | ({j - 1} if jan else set())
    if not str(jahr or "").isdigit() or int(jahr) not in erlaubt:
        return _fehler("Nur Zahlungen in den 10 Tagen um den Jahreswechsel lassen sich dem anderen Jahr zuordnen.")
    with db.connect() as con:   # abgeschlossenes Jahr (alt oder neu): Trigger weist ab
        con.execute("UPDATE ausgaben SET euer_jahr = ? WHERE id = ?", (None if int(jahr) == j else str(jahr), aid))
    return jsonify(finanzen.holen(aid))

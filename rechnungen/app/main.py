"""DJ Office Studio – Weboberfläche + REST-API.

Läuft als Home-Assistant-App (Ingress) oder als Desktop-App (desktop/start.py setzt DJOS_DESKTOP=1).
"""
import csv
import hashlib
import io
import shutil
import tempfile
import json
import os
import re
import ssl
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import db
import importer
import mail
from pdf import MAHNSTUFEN, build_invoice_pdf, girocode_fuer_rechnung, girocode_svg, build_mahnung_pdf, fmt_euro, mahnung_filename, pdf_filename

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")
DESKTOP = os.environ.get("DJOS_DESKTOP") == "1"   # Desktop-Version (Windows/Mac) statt Home Assistant
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(__name__, static_folder=None)


def _daten():
    """JSON aus der Anfrage – fehlt es oder ist es ungültig, ein leeres dict (→ verständliche Fehlermeldung statt 500)."""
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # Upload alter Rechnungen


# Einstellungen der App: Name → (Typ, Standardwert). Gespeichert in der Datenbank, bearbeitbar unter ⚙ Einstellungen.
FELDER = {
    "name": (str, ""), "strasse": (str, ""), "plz_ort": (str, ""), "telefon": (str, ""),
    "ort_fuer_datum": (str, ""),
    "bank_name": (str, ""), "kontoinhaber": (str, ""), "iban": (str, ""), "bic": (str, ""),
    "girocode": (bool, True),         # QR-Code zum Bezahlen auf Rechnungen und Mahnungen
    "steuernummer": (str, ""), "kleinunternehmer": (bool, True),
    "ust_satz": (int, 19),            # nur ohne Kleinunternehmerregelung: Umsatzsteuersatz in %
    "ust_idnr": (str, ""),            # Umsatzsteuer-Identifikationsnummer (optional)
    "startnummer": (int, 1), "angebot_startnummer": (int, 1), "angebot_gueltigkeit_tage": (int, 30),
    "pdf_ordner": (str, os.environ.get("STANDARD_PDF_ORDNER", "/share/rechnungen")),
    "paperless_installiert": (bool, False),
    "paperless_eingangsordner": (str, "" if DESKTOP else "/share/paperless/consume"),
    "update_pruefen": (bool, True),   # nur Desktop-Version: beim Start nach neuer Version suchen
    "mahnfrist_tage": (int, 7),       # Frist in Zahlungserinnerung/Mahnung (Tage ab Datum)
    "sicherung_erinnerung_tage": (int, 30),   # Startseite erinnert an eine Sicherung nach so vielen Tagen (0 = nie)
    # E-Mail-Versand über das eigene Postfach (beliebiger Anbieter / eigener Server)
    "absender_email": (str, ""), "smtp_server": (str, ""), "smtp_port": (int, 587),
    "smtp_sicherheit": (str, "starttls"), "smtp_benutzer": (str, ""), "smtp_passwort": (str, ""),
    "mail_antwort_an": (str, ""), "mail_kopie_an_mich": (bool, True),
    **{k: (str, v) for k, v in mail.VORLAGEN.items()},
}
GEHEIM = set(db.GEHEIM)   # wird nie an den Browser zurückgegeben


def _ohne_geheimnisse(a):
    return {k: ("" if k in GEHEIM else v) for k, v in a.items()} | {"smtp_passwort_gesetzt": bool(a.get("smtp_passwort"))}


def _app_version():
    """Version aus config.yaml (im Container nach /app kopiert, lokal eine Ebene höher)."""
    hier = os.path.dirname(os.path.abspath(__file__))
    for pfad in (os.path.join(hier, "config.yaml"), os.path.join(hier, "..", "config.yaml")):
        try:
            with open(pfad, encoding="utf-8") as f:
                for zeile in f:
                    if zeile.startswith("version:"):
                        return zeile.split(":", 1)[1].strip().strip('"\'')
        except OSError:
            continue
    return "unbekannt"


APP_VERSION = _app_version()


def _ha_optionen():
    """Werte aus der App-Konfiguration in Home Assistant (nur noch für die einmalige Übernahme)."""
    try:
        with open(OPTIONS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def absender():
    """Alle Einstellungen (Absender, Bank, Nummernkreise, Paperless …) mit Standardwerten."""
    gespeichert = db.get_settings()
    if "_uebernommen" not in gespeichert:
        # Erster Start mit Einstellungen in der App: bisherige Home-Assistant-Konfiguration übernehmen
        ha = _ha_optionen()
        gespeichert = {k: ha[k] for k in FELDER if ha.get(k) is not None}
        db.save_settings(gespeichert | {"_uebernommen": True})
    return {k: gespeichert.get(k, standard) for k, (_, standard) in FELDER.items()}


def pdf_dir():
    return absender().get("pdf_ordner") or os.path.join(db.DATA_DIR, "pdf")


# ---------- Frontend ----------

def _asset_version(name):
    """Kurzer Inhalts-Hash – ändert sich bei jedem Update, damit Browser keine alten Dateien nutzen."""
    with open(os.path.join(STATIC_DIR, name), "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:10]


@app.get("/")
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        html = f.read()
    for name in ("style.css", "app.js"):
        html = html.replace(f'"static/{name}"', f'"static/{name}?v={_asset_version(name)}"')
    return Response(html, mimetype="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/static/<path:name>")
def static_files(name):
    resp = send_from_directory(STATIC_DIR, name)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# ---------- Einstellungen ----------

@app.get("/api/einstellungen")
def settings_get():
    return jsonify(_ohne_geheimnisse(absender()))


@app.put("/api/einstellungen")
def settings_put():
    daten = _daten()
    werte, fehler = {}, []
    for k, (typ, standard) in FELDER.items():
        if k not in daten:
            continue
        v = daten[k]
        if k in GEHEIM:
            if v is None:          # ausdrücklich löschen
                werte[k] = ""
            elif v:                # leeres Feld = gespeichertes Passwort behalten
                werte[k] = v
            continue
        if typ is bool:
            werte[k] = bool(v)
        elif typ is int:
            try:
                werte[k] = int(v)
            except (TypeError, ValueError):
                fehler.append(f"„{k}“ muss eine Zahl sein")
                continue
            if werte[k] < (0 if k == "sicherung_erinnerung_tage" else 1):
                fehler.append(f"„{k}“ muss mindestens {0 if k == 'sicherung_erinnerung_tage' else 1} sein")
        elif k.startswith("mail_text_"):
            werte[k] = (v or "").rstrip() if (v or "").strip() else standard   # leere Vorlage → Standardtext
        else:
            werte[k] = (v or "").strip()
            if k.startswith("mail_betreff_") and not werte[k]:
                werte[k] = standard
    if werte.get("smtp_sicherheit", "starttls") not in mail.SICHERHEIT:
        fehler.append("Unbekannte Verschlüsselung")
    for k in ("absender_email", "mail_antwort_an"):
        if werte.get(k):
            try:
                mail.adressen(werte[k])
            except ValueError:
                fehler.append(f"Ungültige E-Mail-Adresse: {werte[k]}")
    if fehler:
        return jsonify({"error": "; ".join(fehler)}), 400
    db.save_settings(werte)
    a = absender()
    # Hinweise zu Ordnern (kein Fehler – der Ordner kann z. B. erst später angelegt werden)
    hinweise = []
    if a["paperless_installiert"] and not os.path.isdir(a["paperless_eingangsordner"] or "-"):
        hinweise.append(f"Paperless-Eingangsordner {a['paperless_eingangsordner'] or '(leer)'} wurde nicht gefunden.")
    return jsonify({"einstellungen": _ohne_geheimnisse(a), "hinweise": hinweise})


# ---------- Update-Prüfung (nur Desktop-Version) ----------

UPDATE_URL = os.environ.get("DJOS_UPDATE_URL",
                            "https://api.github.com/repos/DJMalte96/dj-office-studio/releases/latest")
_update_cache = {"zeit": 0, "ergebnis": None}


def _version_tupel(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def _ssl_kontext():
    """Zertifikate aus certifi: Die gebündelte Desktop-App findet die System-Zertifikate sonst nicht."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


@app.get("/api/update")
def update_check():
    """Neuestes Release auf GitHub mit der installierten Version vergleichen (höchstens alle 6 Stunden)."""
    if not DESKTOP or not absender()["update_pruefen"]:
        return jsonify({"aktiv": False})
    if _update_cache["ergebnis"] and time.time() - _update_cache["zeit"] < 6 * 3600:
        return jsonify(_update_cache["ergebnis"])
    try:
        req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": "DJ-Office-Studio-Desktop",
                                                          "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=5, context=_ssl_kontext()) as r:
            daten = json.loads(r.read())
        neueste = re.sub(r"^[^\d]*", "", daten.get("tag_name", ""))   # „desktop-v0.11.0“ → „0.11.0“
        ergebnis = {"aktiv": True, "installiert": APP_VERSION, "neueste": neueste,
                    "verfuegbar": _version_tupel(neueste) > _version_tupel(APP_VERSION),
                    "url": daten.get("html_url")}
    except Exception as e:   # offline o. Ä. – kein Fehler für den Nutzer, nur kein Hinweis
        app.logger.warning("Update-Prüfung nicht möglich: %s", e)
        return jsonify({"aktiv": True, "fehler": True, "installiert": APP_VERSION})
    _update_cache.update(zeit=time.time(), ergebnis=ergebnis)
    return jsonify(ergebnis)


def _absender_fehlt(a):
    """Angaben, ohne die eine Rechnung nicht vollständig ist (Absender, Bank, ggf. Steuernummer)."""
    fehlt = [t for k, t in (("name", "Name"), ("strasse", "Straße"), ("plz_ort", "PLZ und Ort"), ("iban", "IBAN"))
             if not (a.get(k) or "").strip()]
    if not a.get("kleinunternehmer") and not (a.get("steuernummer") or a.get("ust_idnr") or "").strip():
        fehlt.append("Steuernummer oder USt-IdNr.")
    return fehlt


@app.get("/api/absender")
def get_absender():
    a = absender()
    fehlt = _absender_fehlt(a)
    return jsonify({k: a.get(k) for k in ("name", "strasse", "plz_ort", "ort_fuer_datum")}
                   | {"vollstaendig": not fehlt, "fehlt": fehlt,
                      "kleinunternehmer": bool(a.get("kleinunternehmer")), "ust_satz": a.get("ust_satz") or 19,
                      "paperless": bool(a.get("paperless_installiert")),
                      "angebot_gueltigkeit_tage": a.get("angebot_gueltigkeit_tage") or 30,
                      "mail": mail.konfiguriert(a),
                      "sicherung": _sicherung_status(a),
                      "hinweis_bestaetigt": db.get_settings().get("_hinweis_bestaetigt", 0) >= HINWEIS_VERSION,
                      "version": APP_VERSION,
                      "fenster": DESKTOP and os.environ.get("DJOS_FENSTER") == "1",
                      "desktop": DESKTOP})


# Hinweis „Nutzung ohne Gewähr“ beim ersten Start. Bei einer inhaltlichen Änderung des Textes
# HINWEIS_VERSION erhöhen – dann erscheint er einmal erneut.
HINWEIS_VERSION = 1


@app.post("/api/hinweis")
def notice_confirm():
    db.save_settings({"_hinweis_bestaetigt": HINWEIS_VERSION,
                      "_hinweis_bestaetigt_am": datetime.now().isoformat(timespec="seconds")})
    return "", 204


# ---------- Stammdaten (Kunden, Textbausteine, Zahlungsbedingungen) ----------

def _clean(table, data):
    out = {}
    for col in db.TABLES[table]:
        v = data.get(col)
        if col in ("preis", "grundpreis", "grundstunden", "stundensatz"):
            v = float(v) if v not in (None, "") else None
        elif col == "sortierung":
            v = int(v or 0)
        elif col == "erledigt":
            v = 1 if v in (True, 1, "1", "true", "on") else 0
        else:
            v = (v or "").strip()
        out[col] = v
    if table == "textbausteine" and out["titel"] and not out["text"]:
        out["text"] = db.anlass_text(out["titel"])  # Anlass ohne eigene Vorlage → Standardtext
    required = {"kunden": "name", "textbausteine": "titel", "zahlungsbedingungen": "text",
                "aufgaben": "titel"}[table]
    if not out[required]:
        abort(Response(json.dumps({"error": f"Feld '{required}' fehlt"}), 400,
                       mimetype="application/json"))
    if table != "kunden" and not out.get("titel"):
        out["titel"] = out["text"][:40]
    return out


def _register_crud(table):
    def list_():
        return jsonify(db.list_items(table, request.args.get("q")))

    def create():
        return jsonify({"id": db.save_item(table, _clean(table, _daten()))}), 201

    def update(item_id):
        db.save_item(table, _clean(table, _daten()), item_id)
        return jsonify({"id": item_id})

    def delete(item_id):
        db.delete_item(table, item_id)
        return "", 204

    app.add_url_rule(f"/api/{table}", f"{table}_list", list_, methods=["GET"])
    app.add_url_rule(f"/api/{table}", f"{table}_create", create, methods=["POST"])
    app.add_url_rule(f"/api/{table}/<int:item_id>", f"{table}_update", update, methods=["PUT"])
    app.add_url_rule(f"/api/{table}/<int:item_id>", f"{table}_delete", delete, methods=["DELETE"])


for _t in db.TABLES:
    _register_crud(_t)


# ---------- Rechnungen ----------

def _validate_invoice(data, inv_id=None, check_number=True, art="rechnung", pflicht=True):
    """pflicht=False (PDF-Vorschau): Pflichtangaben einer Rechnung noch nicht erzwingen."""
    angebot = art == "angebot"
    wort = "Angebotsnummer" if angebot else "Rechnungsnummer"
    errors = []
    kunde = data.get("kunde") or {}
    if not (kunde.get("name") or "").strip():
        errors.append("Kundenname fehlt")
    nummer = (data.get("nummer") or "").strip()
    if not nummer:
        errors.append(f"{wort} fehlt")
    elif check_number and db.number_taken(nummer, inv_id, "angebote" if angebot else "rechnungen"):
        errors.append(f"{wort} {nummer} ist bereits vergeben")
    positionen = [p for p in data.get("positionen") or [] if (p.get("beschreibung") or "").strip()]
    if not positionen:
        errors.append("Mindestens eine Position mit Beschreibung angeben")
    for p in positionen:
        try:
            p["preis"] = round(float(p.get("preis") or 0), 2)
        except (TypeError, ValueError):
            errors.append(f"Ungültiger Preis bei '{p['beschreibung'][:30]}'")
    if not angebot and not (data.get("zahlungsbedingung") or "").strip():
        errors.append("Zahlungsbedingung fehlt")
    if not angebot and pflicht:
        # Pflichtangaben einer Rechnung: vollständige Anschrift des Kunden und Datum der Leistung
        fehlt = [t for k, t in (("strasse", "Straße"), ("plz", "PLZ"), ("ort", "Ort")) if not (kunde.get(k) or "").strip()]
        if fehlt and (kunde.get("name") or "").strip():
            errors.append(f"Anschrift des Kunden unvollständig – {', '.join(fehlt)} fehlt (Pflichtangabe auf Rechnungen)")
        ohne_datum = [p for p in positionen if not p.get("lieferdatum")]
        if ohne_datum:
            errors.append("Bitte bei jeder Position das Lieferdatum (Datum der Veranstaltung) eintragen "
                          f"(fehlt bei „{ohne_datum[0]['beschreibung'][:40]}“)")
    if errors:
        abort(Response(json.dumps({"error": "; ".join(errors)}), 400, mimetype="application/json"))
    doc = {
        "nummer": nummer,
        "datum": data.get("datum") or date.today().isoformat(),
        "kunde": {k: (kunde.get(k) or "").strip() for k in db.TABLES["kunden"]},
        "kunde_id": kunde.get("id"),
        "positionen": [{"beschreibung": p["beschreibung"].strip(),
                        "lieferdatum": p.get("lieferdatum") or "",
                        "preis": p["preis"]} for p in positionen],
        "zahlungsbedingung": (data.get("zahlungsbedingung") or "").strip(),
    }
    doc |= _steuer(sum(p["preis"] for p in positionen))
    if angebot:
        doc |= {"art": "angebot", "gueltig_bis": data.get("gueltig_bis") or "",
                "hinweise": (data.get("hinweise") or "").strip()}
    else:
        doc["bezahlt"] = bool(data.get("bezahlt"))
    return doc


def _steuer(netto, a=None):
    """Steuer eines neuen bzw. bearbeiteten Belegs nach den aktuellen Einstellungen.
    Gesamtbetrag = Bruttobetrag (das, was der Kunde zahlt); Positionspreise sind Nettopreise."""
    a = a or absender()
    if a.get("kleinunternehmer"):
        return {"kleinunternehmer": True, "ust_satz": None, "gesamt": round(netto, 2)}
    satz = float(a.get("ust_satz") or 19)
    return {"kleinunternehmer": False, "ust_satz": satz, "gesamt": round(netto + round(netto * satz / 100, 2), 2)}


def _write_pdf_file(inv):
    """Legt eine Kopie des PDFs im konfigurierten Ordner ab (z. B. /share/rechnungen)."""
    try:
        target = pdf_dir()
        os.makedirs(target, exist_ok=True)
        path = os.path.join(target, pdf_filename(inv))
        with open(path, "wb") as f:
            f.write(build_invoice_pdf(inv, absender()))
        return path
    except OSError as e:
        app.logger.warning("PDF konnte nicht gespeichert werden: %s", e)
        return None


@app.get("/api/rechnungen")
def invoices_list():
    # "name" = Dateiname ohne Endung, z. B. "Rechnung_037_311026" – gleicher Name wie das PDF
    return jsonify([inv | {"name": pdf_filename(inv).removesuffix(".pdf")} for inv in db.list_invoices()])


@app.get("/api/rechnungen/naechste-nummer")
def invoices_next():
    return jsonify({"nummer": db.next_number(absender().get("startnummer") or 1)})


@app.get("/api/rechnungen/<int:inv_id>")
def invoices_get(inv_id):
    inv = db.get_invoice(inv_id) or abort(404)
    return jsonify(inv)


@app.post("/api/rechnungen")
def invoices_create():
    inv = _validate_invoice(_daten())
    inv["kunde_id"] = db.upsert_customer({**inv["kunde"], "id": inv["kunde_id"]})
    inv_id = db.save_invoice(inv)
    angebot_id = _daten().get("angebot_id")
    if angebot_id and db.get_offer(angebot_id):
        db.set_offer_status(angebot_id, "angenommen", inv_id)
    return jsonify({"id": inv_id, "datei": _write_pdf_file(inv)}), 201


def _fehler(text, code=400):
    return jsonify({"error": text}), code


FESTGESCHRIEBEN = ("Die Rechnung ist festgeschrieben und kann nicht mehr geändert oder gelöscht werden – "
                   "zum Korrigieren bitte stornieren und neu erstellen.")


@app.put("/api/rechnungen/<int:inv_id>")
def invoices_update(inv_id):
    alt = db.get_invoice(inv_id) or abort(404)
    if alt["festgeschrieben"]:
        return _fehler(FESTGESCHRIEBEN, 409)
    inv = _validate_invoice(_daten(), inv_id)
    inv["kunde_id"] = db.upsert_customer({**inv["kunde"], "id": inv["kunde_id"]})
    db.save_invoice(inv, inv_id)
    return jsonify({"id": inv_id, "datei": _write_pdf_file(inv)})


@app.delete("/api/rechnungen/<int:inv_id>/paperless")
def invoices_paperless_reset(inv_id):
    """Markierung „an Paperless übertragen“ zurücksetzen (z. B. weil das Dokument dort gelöscht wurde)."""
    db.set_paperless(inv_id, None)
    return "", 204


@app.delete("/api/angebote/<int:offer_id>/paperless")
def offers_paperless_reset(offer_id):
    db.set_paperless(offer_id, None, "angebote")
    return "", 204


@app.patch("/api/rechnungen/<int:inv_id>/bezahlt")
def invoices_paid(inv_id):
    inv = db.get_invoice(inv_id) or abort(404)
    if inv["storno_von"] or inv["storniert_durch"]:
        return _fehler("Stornierte Rechnungen und Stornorechnungen haben keinen Zahlstatus.")
    db.set_paid(inv_id, _daten().get("bezahlt"))
    return "", 204


@app.delete("/api/rechnungen/<int:inv_id>")
def invoices_delete(inv_id):
    inv = db.get_invoice(inv_id) or abort(404)
    if inv["festgeschrieben"]:
        return _fehler(FESTGESCHRIEBEN, 409)
    db.delete_invoice(inv_id)
    return "", 204


@app.post("/api/rechnungen/<int:inv_id>/festschreiben")
def invoices_lock(inv_id):
    db.get_invoice(inv_id) or abort(404)
    db.festschreiben(inv_id)
    return "", 204


@app.post("/api/rechnungen/<int:inv_id>/stornieren")
def invoices_cancel(inv_id):
    """Stornorechnung mit eigener Nummer erzeugen (alle Beträge negativ) und die Rechnung als storniert markieren."""
    inv = db.get_invoice(inv_id) or abort(404)
    if inv["storno_von"]:
        return _fehler("Eine Stornorechnung kann nicht storniert werden.")
    if inv["storniert_durch"]:
        return _fehler(f"Die Rechnung wurde bereits storniert (Stornorechnung {inv['storniert_durch_nummer']}).")
    storno = {
        "nummer": db.next_number(absender().get("startnummer") or 1),
        "datum": date.today().isoformat(),
        "kunde": inv["kunde"], "kunde_id": inv["kunde_id"],
        "positionen": [{**p, "preis": -round(float(p.get("preis") or 0), 2)} for p in inv["positionen"]],
        "zahlungsbedingung": "", "gesamt": -inv["gesamt"],
        "kleinunternehmer": inv.get("kleinunternehmer"), "ust_satz": inv.get("ust_satz"),
        "bezahlt": True, "festgeschrieben": True, "storno_von": inv_id,
    }
    storno_id = db.save_invoice(storno)
    db.set_storniert(inv_id, storno_id)
    storno = db.get_invoice(storno_id)
    return jsonify({"id": storno_id, "nummer": storno["nummer"], "datei": _write_pdf_file(storno)}), 201


# ---------- Zahlungserinnerung / Mahnung ----------

def _faellig_am(inv):
    """Fälligkeitsdatum aus der Zahlungsbedingung („… innerhalb der nächsten 8 Tage …“)."""
    m = re.search(r"(\d+)\s*Tage?n?\b", inv.get("zahlungsbedingung") or "", re.I)
    try:
        return (date.fromisoformat(inv["datum"]) + timedelta(days=int(m.group(1)))).isoformat() if m else None
    except ValueError:
        return None


@app.post("/api/rechnungen/<int:inv_id>/mahnung")
def invoices_dunning(inv_id):
    """Nächste Stufe erzeugen: Zahlungserinnerung → 1. Mahnung → 2. Mahnung."""
    inv = db.get_invoice(inv_id) or abort(404)
    if inv["bezahlt"] or inv["storno_von"] or inv["storniert_durch"]:
        return _fehler("Für diese Rechnung ist keine Mahnung möglich (bezahlt oder storniert).")
    stufe = len(inv["mahnungen"]) + 1
    if stufe > 3:
        return _fehler("Es wurden bereits Zahlungserinnerung, 1. und 2. Mahnung erstellt.")
    heute = date.today()
    frist = (heute + timedelta(days=absender()["mahnfrist_tage"] or 7)).isoformat()
    mahnung_id = db.add_mahnung(inv_id, stufe, heute.isoformat(), frist)
    db.festschreiben(inv_id)
    mahnung = db.get_mahnung(mahnung_id)
    datei = None
    try:   # Kopie im PDF-Ordner ablegen
        os.makedirs(pdf_dir(), exist_ok=True)
        datei = os.path.join(pdf_dir(), mahnung_filename(inv, mahnung))
        with open(datei, "wb") as f:
            f.write(build_mahnung_pdf(inv, mahnung, absender(), _faellig_am(inv)))
    except OSError as e:
        app.logger.warning("Mahnung konnte nicht gespeichert werden: %s", e)
        datei = None
    return jsonify({"id": mahnung_id, "stufe": stufe, "bezeichnung": MAHNSTUFEN[stufe], "datei": datei}), 201


@app.get("/api/mahnungen/<int:mahnung_id>/pdf")
def dunning_pdf(mahnung_id):
    mahnung = db.get_mahnung(mahnung_id) or abort(404)
    inv = db.get_invoice(mahnung["rechnung_id"]) or abort(404)
    return Response(build_mahnung_pdf(inv, mahnung, absender(), _faellig_am(inv)), mimetype="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{mahnung_filename(inv, mahnung)}"'})


# ---------- Datensicherung & Export ----------

def _letzte_auto_sicherung():
    """Desktop-Version: Datum der neuesten automatischen Tageskopie (Daten/Sicherungen/rechnungen_JJJJ-MM-TT.db)."""
    if not DESKTOP:
        return None
    try:
        namen = [n for n in os.listdir(os.path.join(db.DATA_DIR, "Sicherungen"))
                 if re.fullmatch(r"rechnungen_\d{4}-\d{2}-\d{2}\.db", n)]
    except OSError:
        return None
    return max(namen)[11:21] if namen else None


def _sicherung_status(a):
    return {"letzte": db.get_settings().get("_letzte_sicherung"),   # letzte heruntergeladene Sicherung
            "erinnerung_tage": a.get("sicherung_erinnerung_tage", 30),
            "automatisch": _letzte_auto_sicherung()}


@app.get("/api/backup")
def backup_download():
    """Komplette Datenbank als ZIP (Kunden, Rechnungen, Angebote, Einstellungen …)."""
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "rechnungen.db")
        db.sichern(pfad)
        db.geheimnisse_entfernen(pfad)   # Mail-Passwort nicht in die herunterladbare Datei
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(pfad, "rechnungen.db")
            zf.writestr("info.json", json.dumps({"app": "DJ Office Studio", "version": APP_VERSION,
                                                 "erstellt": datetime.now().isoformat(timespec="seconds")}))
    db.save_settings({"_letzte_sicherung": datetime.now().isoformat(timespec="seconds")})   # für die Erinnerung
    name = f"DJ-Office-Studio-Sicherung_{date.today():%Y-%m-%d}.zip"
    return Response(buf.getvalue(), mimetype="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/backup")
def backup_restore():
    """Sicherung (ZIP oder .db) einspielen. Der bisherige Stand wird vorher automatisch gesichert."""
    datei = request.files.get("datei") or abort(400)
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "upload.db")
        inhalt = datei.read()
        if inhalt[:2] == b"PK":   # ZIP
            try:
                with zipfile.ZipFile(io.BytesIO(inhalt)) as zf:
                    with zf.open("rechnungen.db") as src, open(pfad, "wb") as dst:
                        shutil.copyfileobj(src, dst)
            except (KeyError, zipfile.BadZipFile):
                return _fehler("Die ZIP-Datei enthält keine Sicherung von DJ Office Studio.")
        else:
            with open(pfad, "wb") as f:
                f.write(inhalt)
        try:
            anzahl = db.pruefe_sicherung(pfad)
        except ValueError as e:
            return _fehler(str(e))
        ordner = os.path.join(db.DATA_DIR, "sicherungen")
        os.makedirs(ordner, exist_ok=True)
        vorher = os.path.join(ordner, f"vor-wiederherstellung_{datetime.now():%Y-%m-%d_%H-%M-%S}.db")
        db.sichern(vorher)
        letzte = db.get_settings().get("_letzte_sicherung")
        db.wiederherstellen(pfad)
        if letzte and letzte > (db.get_settings().get("_letzte_sicherung") or ""):
            db.save_settings({"_letzte_sicherung": letzte})   # Zeitpunkt der letzten Sicherung nicht zurückdrehen
    return jsonify({"anzahl": anzahl, "vorher_gesichert": vorher})


def _betrag(v):
    return f"{v:.2f}".replace(".", ",")


@app.get("/api/export")
def export_year():
    """Export für den Steuerberater: alle Rechnungen eines Jahres als CSV (Excel) + PDFs."""
    jahr = request.args.get("jahr") or str(date.today().year)
    if not jahr.isdigit():
        abort(400)
    rechnungen = sorted((r for r in db.list_invoices() if r["datum"].startswith(jahr)),
                        key=lambda r: (r["datum"], r["nummer"]))
    a = absender()
    csv_buf = io.StringIO()
    w = csv.writer(csv_buf, delimiter=";")
    w.writerow(["Rechnungsnummer", "Rechnungsdatum", "Leistungsdatum", "Kunde", "Ort", "Netto (EUR)", "USt-Satz",
                "USt (EUR)", "Betrag (EUR)", "Status", "Bezahlt am", "Bezug", "Datei"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in rechnungen:
            status = ("Storno" if r["storno_von"] else "storniert" if r["storniert_durch"]
                      else "bezahlt" if r["bezahlt"] else "offen")
            bezug = (f"Storno zu {r['storno_zu']['nummer']}" if r["storno_zu"]
                     else f"storniert durch {r['storniert_durch_nummer']}" if r["storniert_durch"] else "")
            leistung = next((p.get("lieferdatum") for p in r["positionen"] if p.get("lieferdatum")), "")
            name = pdf_filename(r)
            netto = round(sum(float(p.get("preis") or 0) for p in r["positionen"]), 2)
            satz = r.get("ust_satz")
            w.writerow([r["nummer"], r["datum"], leistung, r["kunde"].get("name", ""), r["kunde"].get("ort", ""),
                        _betrag(netto), f"{satz:g} %" if satz else "", _betrag(r["gesamt"] - netto) if satz else "",
                        _betrag(r["gesamt"]), status, r.get("bezahlt_am") or "", bezug, name])
            zf.writestr(f"PDFs/{name}", build_invoice_pdf(r, a))
        summe = sum(r["gesamt"] for r in rechnungen)
        bezahlt = sum(r["gesamt"] for r in rechnungen if r["bezahlt"] and not r["storno_von"])
        w.writerow([])
        w.writerow(["Summe aller Rechnungen (inkl. Storno)", "", "", "", "", "", "", "", _betrag(summe)])
        w.writerow(["davon bezahlt (ohne Stornorechnungen)", "", "", "", "", "", "", "", _betrag(bezahlt)])
        # BOM, damit Excel die Umlaute richtig erkennt
        zf.writestr(f"Rechnungen_{jahr}.csv", "\ufeff" + csv_buf.getvalue())
    return Response(buf.getvalue(), mimetype="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="Export_Rechnungen_{jahr}.zip"'})


# ---------- E-Mail-Versand ----------

def _de(iso):
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return ""


def _versand_beleg(art, beleg_id, mahnung_id=None):
    """Beleg, Anhänge und Platzhalter-Werte für eine E-Mail. art: rechnung | angebot | mahnung."""
    a = absender()
    if art == "angebot":
        beleg = db.get_offer(beleg_id) or abort(404)
    elif art in ("rechnung", "mahnung"):
        beleg = db.get_invoice(beleg_id) or abort(404)
    else:
        abort(400)
    mahnung = None
    if art == "mahnung":
        mahnung = next((m for m in beleg["mahnungen"] if m["id"] == mahnung_id), None) or abort(404)
    anhaenge = [(pdf_filename(beleg), build_invoice_pdf(beleg, a))]
    if mahnung:
        anhaenge.insert(0, (mahnung_filename(beleg, mahnung), build_mahnung_pdf(beleg, mahnung, a, _faellig_am(beleg))))
    offen = art != "angebot" and not beleg["bezahlt"] and not beleg["storno_von"]
    werte = {
        "kunde": beleg["kunde"].get("name", ""),
        "nummer": beleg["nummer"], "datum": _de(beleg["datum"]),
        "betrag": fmt_euro(beleg["gesamt"]),
        "faellig": _de(_faellig_am(beleg)) if offen else "",
        "gueltig_bis": _de(beleg.get("gueltig_bis")) if art == "angebot" else "",
        "leistungsdatum": _de(next((p.get("lieferdatum") for p in beleg["positionen"] if p.get("lieferdatum")), "")),
        "stufe": MAHNSTUFEN[mahnung["stufe"]] if mahnung else "",
        "frist": _de(mahnung["frist"]) if mahnung else "",
        "absender": a.get("name", ""), "telefon": a.get("telefon", ""),
    }
    return beleg, mahnung, anhaenge, werte


@app.get("/api/versand/entwurf")
def mail_draft():
    """Vorausgefüllte E-Mail (Empfänger aus den Kundendaten, Betreff/Text aus den Vorlagen)."""
    art = request.args.get("art", "")
    mahnung_id = request.args.get("mahnung_id", type=int)
    beleg, mahnung, anhaenge, werte = _versand_beleg(art, request.args.get("id", type=int), mahnung_id)
    a = absender()
    kunde = db.get_customer(beleg.get("kunde_id")) if beleg.get("kunde_id") else None
    email = (kunde or {}).get("email") or beleg["kunde"].get("email") or ""
    betreff, text = a[f"mail_betreff_{art}"], a[f"mail_text_{art}"]
    if art == "rechnung" and beleg.get("storno_zu"):   # Stornorechnung: eigener Text statt „Vielen Dank für Ihren Auftrag“
        betreff, text = mail.STORNO_BETREFF, mail.STORNO_TEXT
        werte |= {"storno_nummer": beleg["storno_zu"]["nummer"], "storno_datum": _de(beleg["storno_zu"]["datum"])}
    return jsonify({
        "an": email, "kunde_email": email, "kunde_id": beleg.get("kunde_id"),
        "betreff": mail.fuellen(betreff, werte),
        "text": mail.fuellen(text, werte),
        "anhaenge": [name for name, _ in anhaenge],
        "konfiguriert": mail.konfiguriert(a),
        "kopie": bool(a.get("mail_kopie_an_mich")), "absender_email": a.get("absender_email", ""),
        "versand": [v for v in beleg.get("versand", []) if v.get("mahnung_id") == (mahnung["id"] if mahnung else None)],
    })


@app.post("/api/versand")
def mail_send():
    """E-Mail mit PDF(s) verschicken, im Versand-Protokoll vermerken; Rechnungen werden festgeschrieben."""
    d = _daten()
    art = d.get("art", "")
    beleg, mahnung, anhaenge, _ = _versand_beleg(art, d.get("id"), d.get("mahnung_id"))
    try:
        an = mail.adressen(d.get("an"))
    except ValueError as e:
        return _fehler(str(e))
    betreff = (d.get("betreff") or "").strip()
    text = (d.get("text") or "").strip()
    if not betreff or not text:
        return _fehler("Betreff und Text dürfen nicht leer sein.")
    a = absender()
    try:
        mail.senden(a, an, betreff, text, anhaenge,
                    kopie_an=a.get("absender_email") if d.get("kopie") else None, ssl_kontext=_ssl_kontext())
    except ValueError as e:
        return _fehler(str(e), 502)
    db.add_versand(art, beleg["id"], ", ".join(an), betreff, mahnung["id"] if mahnung else None)
    if art != "angebot":
        db.festschreiben(beleg["id"])   # verschickt = ausgestellt
    if d.get("email_speichern") and len(an) == 1:
        kid = beleg.get("kunde_id") or db.upsert_customer(beleg["kunde"])
        db.set_customer_email(kid, an[0])
    return jsonify({"an": an, "anhaenge": [n for n, _ in anhaenge]})


@app.post("/api/versand/test")
def mail_test():
    """Testmail an die eigene Adresse – mit den Werten aus dem Formular (noch nicht gespeichert)."""
    d = _daten()
    cfg = absender()
    for k in ("absender_email", "smtp_server", "smtp_port", "smtp_sicherheit", "smtp_benutzer", "smtp_passwort",
              "mail_antwort_an", "name"):
        if d.get(k) not in (None, ""):
            cfg[k] = d[k]
    try:
        an = mail.adressen(cfg.get("absender_email"))
        cfg["smtp_port"] = int(cfg.get("smtp_port") or 587)
        mail.senden(cfg, an, "Testmail von DJ Office Studio",
                    "Hallo,\n\ndiese Testmail zeigt: Der E-Mail-Versand aus DJ Office Studio funktioniert.\n\n"
                    f"Server: {cfg['smtp_server']}:{cfg['smtp_port']} ({cfg.get('smtp_sicherheit')})",
                    ssl_kontext=_ssl_kontext())
    except ValueError as e:
        return _fehler(str(e), 502)
    return jsonify({"an": an[0]})


def _pdf_response(inv, download=False):
    disposition = "attachment" if download or request.args.get("download") else "inline"
    return Response(build_invoice_pdf(inv, absender()), mimetype="application/pdf",
                    headers={"Content-Disposition": f'{disposition}; filename="{pdf_filename(inv)}"'})


@app.get("/api/rechnungen/<int:inv_id>/girocode")
def invoices_girocode(inv_id):
    """GiroCode zum Anzeigen in der App (z. B. Kunde bezahlt direkt nach der Feier am Handy)."""
    inv = db.get_invoice(inv_id) or abort(404)
    a = absender() | {"girocode": True}   # Anzeigen geht auch, wenn der Druck im PDF abgeschaltet ist
    if not (a.get("iban") and (a.get("kontoinhaber") or a.get("name"))):
        return _fehler("Für den QR-Code fehlen IBAN oder Name – bitte unter ⚙ Einstellungen eintragen.")
    daten = girocode_fuer_rechnung(inv, a)
    if not daten or inv["bezahlt"] or inv["storniert_durch"]:
        return _fehler("Für diese Rechnung gibt es keinen offenen Betrag zum Überweisen.")
    if request.args.get("info"):
        return jsonify({"empfaenger": (a.get("kontoinhaber") or a.get("name")).strip()[:70],
                        "iban": a["iban"], "bic": a.get("bic", ""), "betrag": inv["gesamt"],
                        "zweck": f"Rechnung {inv['nummer']}"})
    return Response(girocode_svg(daten), mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/api/rechnungen/<int:inv_id>/pdf")
def invoices_pdf(inv_id):
    return _pdf_response(db.get_invoice(inv_id) or abort(404))


def _download(laden, zip_praefix):
    """Mehrere Belege auf einmal: ?ids=1,2,3 → ZIP (bei genau einem Beleg direkt das PDF)."""
    try:
        ids = [int(x) for x in request.args.get("ids", "").split(",") if x.strip()]
    except ValueError:
        abort(400)
    invoices = [inv for inv in (laden(i) for i in dict.fromkeys(ids)) if inv]
    if not invoices:
        abort(404)
    if len(invoices) == 1:
        return _pdf_response(invoices[0], download=True)

    buf = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for inv in invoices:
            name = pdf_filename(inv)
            stem, n = name.removesuffix(".pdf"), 2
            while name in used:          # gleiche Dateinamen nicht überschreiben
                name, n = f"{stem}_{n}.pdf", n + 1
            used.add(name)
            zf.writestr(name, build_invoice_pdf(inv, absender()))
    zip_name = f"{zip_praefix}_{date.today():%Y-%m-%d}.zip"
    return Response(buf.getvalue(), mimetype="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{zip_name}"'})


@app.get("/api/rechnungen/download")
def invoices_download():
    return _download(db.get_invoice, "Rechnungen")


@app.get("/api/angebote/download")
def offers_download():
    return _download(db.get_offer, "Angebote")


# ---------- Paperless-ngx (Eingangsordner) ----------

def _paperless_ordner(a=None):
    a = a if a is not None else absender()
    return (a.get("paperless_eingangsordner") or "").strip()


def _in_eingangsordner(ordner, name, pdf_bytes):
    """PDF in den Eingangsordner legen. Erst als .part schreiben und dann umbenennen,
    damit Paperless keine halb geschriebene Datei einliest. Gleichnamige Dateien werden nicht überschrieben."""
    stem, n = name.removesuffix(".pdf"), 2
    ziel = os.path.join(ordner, name)
    while os.path.exists(ziel):
        ziel, n = os.path.join(ordner, f"{stem}_{n}.pdf"), n + 1
    tmp = ziel + ".part"
    with open(tmp, "wb") as f:
        f.write(pdf_bytes)
    os.replace(tmp, ziel)
    return os.path.basename(ziel)


@app.post("/api/paperless")
def invoices_to_paperless():
    """Ausgewählte Rechnungen oder Angebote als PDF in den Eingangsordner von Paperless legen:
    {"ids": [1, 2, 3], "art": "rechnung" | "angebot"}."""
    a = absender()
    daten = _daten()
    angebot = daten.get("art") == "angebot"
    laden, table = (db.get_offer, "angebote") if angebot else (db.get_invoice, "rechnungen")
    ordner = _paperless_ordner(a)
    if not a.get("paperless_installiert"):
        return jsonify({"error": "Paperless ist nicht aktiviert – unter ⚙ Einstellungen "
                                 "„Paperless-ngx ist installiert“ einschalten."}), 400
    if not ordner:
        return jsonify({"error": "Paperless ist nicht eingerichtet – bitte unter ⚙ Einstellungen "
                                 "den Paperless-Eingangsordner eintragen."}), 400
    if not os.path.isdir(ordner):
        # Bewusst nicht anlegen: Bei falschem Pfad würden die PDFs sonst unbemerkt liegen bleiben
        return jsonify({"error": f"Eingangsordner {ordner} nicht gefunden – Pfad unter ⚙ Einstellungen prüfen"
                                 + ("." if DESKTOP else " (muss unter /share oder /media liegen).")}), 400

    ok, fehler = [], []
    for inv_id in dict.fromkeys(daten.get("ids") or []):
        inv = laden(inv_id)
        if not inv:
            continue
        name = pdf_filename(inv)
        try:
            _in_eingangsordner(ordner, name, build_invoice_pdf(inv, a))
        except OSError as e:
            fehler.append({"id": inv_id, "name": name, "error": f"{name} konnte nicht abgelegt werden: {e}"})
            continue
        db.set_paperless(inv_id, datetime.now().isoformat(timespec="seconds"), table)
        if not angebot:
            db.festschreiben(inv_id)   # an Paperless übergeben = verschickt/abgelegt
        ok.append(inv_id)
    return jsonify({"ok": ok, "fehler": fehler})


@app.post("/api/vorschau")
def invoices_preview():
    data = _daten()
    data["nummer"] = (data.get("nummer") or "").strip() or "VORSCHAU"
    return _pdf_response(_validate_invoice(data, check_number=False, art=data.get("art") or "rechnung", pflicht=False))


# ---------- Angebote ----------

@app.get("/api/angebote")
def offers_list():
    return jsonify([a | {"name": pdf_filename(a).removesuffix(".pdf")} for a in db.list_offers()])


@app.get("/api/angebote/naechste-nummer")
def offers_next():
    return jsonify({"nummer": db.next_number(absender().get("angebot_startnummer") or 1, "angebote")})


@app.get("/api/angebote/<int:offer_id>")
def offers_get(offer_id):
    return jsonify(db.get_offer(offer_id) or abort(404))


def _save_offer(offer_id=None):
    a = _validate_invoice(_daten(), offer_id, art="angebot")
    a["kunde_id"] = db.upsert_customer({**a["kunde"], "id": a["kunde_id"]})
    offer_id = db.save_offer(a, offer_id)
    return {"id": offer_id, "datei": _write_pdf_file(a)}


@app.post("/api/angebote")
def offers_create():
    return jsonify(_save_offer()), 201


@app.put("/api/angebote/<int:offer_id>")
def offers_update(offer_id):
    db.get_offer(offer_id) or abort(404)
    return jsonify(_save_offer(offer_id))


@app.patch("/api/angebote/<int:offer_id>/status")
def offers_status(offer_id):
    status = _daten().get("status")
    if status not in db.STATUS:
        abort(400)
    db.set_offer_status(offer_id, status)
    return "", 204


@app.delete("/api/angebote/<int:offer_id>")
def offers_delete(offer_id):
    db.delete_offer(offer_id)
    return "", 204


@app.get("/api/angebote/<int:offer_id>/pdf")
def offers_pdf(offer_id):
    return _pdf_response(db.get_offer(offer_id) or abort(404))


# ---------- Import alter Rechnungen ----------

def _norm_key(s):
    return " ".join((s or "").lower().split())


@app.post("/api/import/analyse")
def import_analyse():
    """PDFs (Rechnungen und Angebote gemischt) auslesen und Vorschläge liefern – speichert noch nichts."""
    rechnungen, angebote, fehler = [], [], []
    for f in request.files.getlist("dateien"):
        try:
            doc = importer.parse_document(importer.pdf_text(f.read()))
            if not doc["kunde"].get("name") or not doc["positionen"]:
                raise ValueError("Empfänger oder Positionen nicht erkannt")
            doc["datei"] = f.filename
            if doc["art"] == "angebot":
                doc["nummer_vorhanden"] = bool(doc["nummer"]) and db.number_taken(doc["nummer"], table="angebote")
                angebote.append(doc)
            else:
                doc["nummer_vorhanden"] = db.number_taken(doc["nummer"])
                rechnungen.append(doc)
        except ValueError as e:
            fehler.append({"datei": f.filename, "fehler": str(e)})
        except Exception:  # defekte/fremde PDFs sollen den Rest nicht aufhalten
            app.logger.exception("Import von %s fehlgeschlagen", f.filename)
            fehler.append({"datei": f.filename, "fehler": "PDF konnte nicht gelesen werden (defekt oder geschützt)"})

    # Empfänger (einmalig je Name+Ort)
    bekannte = {(_norm_key(k["name"]), _norm_key(k["ort"])) for k in db.list_items("kunden")}
    kunden, seen = [], set()
    for inv in sorted(rechnungen + angebote, key=lambda r: r["datum"], reverse=True):  # neueste Adresse gewinnt
        k = inv["kunde"]
        key = (_norm_key(k["name"]), _norm_key(k["ort"]))
        if key not in seen:
            seen.add(key)
            kunden.append({**k, "vorhanden": key in bekannte})

    # Textbaustein-Vorschläge (gleiche Texte zusammengefasst, vorhandene ausgelassen)
    vorhandene = db.list_items("textbausteine")
    vorhandene_tb = {_norm_key(t["text"]) for t in vorhandene} | {_norm_key(t["titel"]) for t in vorhandene}
    vorschlaege = {}
    for inv in rechnungen + angebote:
        for p in inv["positionen"]:
            v = importer.textbaustein_vorschlag(p["beschreibung"])
            key = _norm_key(v["text"])
            if key in vorhandene_tb or _norm_key(v["titel"]) in vorhandene_tb:
                continue
            vorschlaege.setdefault(key, {**v, "anzahl": 0})["anzahl"] += 1
    textbausteine = sorted(vorschlaege.values(), key=lambda v: -v["anzahl"])

    rechnungen.sort(key=lambda r: r["nummer"])
    angebote.sort(key=lambda r: (r["datum"], r["nummer"]))
    return jsonify({"rechnungen": rechnungen, "angebote": angebote, "kunden": kunden,
                    "textbausteine": textbausteine, "fehler": fehler})


@app.post("/api/import/uebernehmen")
def import_uebernehmen():
    data = _daten()
    n_kunden = n_tb = n_rech = n_ang = 0
    for k in data.get("kunden") or []:
        if (k.get("name") or "").strip():
            db.upsert_customer(k)
            n_kunden += 1
    for t in data.get("textbausteine") or []:
        if (t.get("text") or "").strip():
            db.save_item("textbausteine", {"titel": (t.get("titel") or t["text"][:40]).strip(),
                                           "text": t["text"].strip()})
            n_tb += 1
    for inv in data.get("rechnungen") or []:
        nummer = (inv.get("nummer") or "").strip()
        if not nummer or db.number_taken(nummer) or not inv.get("positionen"):
            continue
        kunde = {k: (inv["kunde"].get(k) or "").strip() for k in db.TABLES["kunden"]}
        db.save_invoice({
            "nummer": nummer, "datum": inv.get("datum") or date.today().isoformat(),
            "kunde": kunde, "kunde_id": db.upsert_customer(kunde),
            "positionen": inv["positionen"], "zahlungsbedingung": inv.get("zahlungsbedingung") or "",
            "gesamt": round(sum(float(p.get("preis") or 0) for p in inv["positionen"]), 2),
            "bezahlt": bool(data.get("bezahlt")),
            "festgeschrieben": True,   # alte, bereits verschickte Rechnungen
        })
        n_rech += 1
    status = data.get("angebot_status") if data.get("angebot_status") in db.STATUS else "offen"
    for a in data.get("angebote") or []:
        nummer = (a.get("nummer") or "").strip() or db.next_number(absender().get("angebot_startnummer") or 1, "angebote")  # ohne Nummer → nächste freie
        if db.number_taken(nummer, table="angebote") or not a.get("positionen"):
            continue
        kunde = {k: (a["kunde"].get(k) or "").strip() for k in db.TABLES["kunden"]}
        offer_id = db.save_offer({
            "nummer": nummer, "datum": a.get("datum") or date.today().isoformat(),
            "gueltig_bis": a.get("gueltig_bis") or "",
            "kunde": kunde, "kunde_id": db.upsert_customer(kunde),
            "positionen": a["positionen"], "zahlungsbedingung": "", "hinweise": a.get("hinweise") or "",
            "gesamt": round(sum(float(p.get("preis") or 0) for p in a["positionen"]), 2),
        })
        if status != "offen":
            db.set_offer_status(offer_id, status)
        n_ang += 1
    return jsonify({"kunden": n_kunden, "textbausteine": n_tb, "rechnungen": n_rech, "angebote": n_ang})


if __name__ == "__main__":
    from waitress import serve

    db.init()
    port = int(os.environ.get("PORT", "8099"))
    print(f"DJ Office Studio läuft auf Port {port}")
    serve(app, host="0.0.0.0", port=port)

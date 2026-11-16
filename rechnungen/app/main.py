"""DJ Office Studio – Weboberfläche + REST-API.

Läuft als Home-Assistant-App (Ingress) oder als Desktop-App (desktop/start.py setzt DJOS_DESKTOP=1).
"""
import hashlib
import io
import json
import os
import zipfile
from datetime import date, datetime

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import db
import importer
from pdf import build_invoice_pdf, pdf_filename

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")
DESKTOP = os.environ.get("DJOS_DESKTOP") == "1"   # Desktop-Version (Windows/Mac) statt Home Assistant
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # Upload alter Rechnungen


# Einstellungen der App: Name → (Typ, Standardwert). Gespeichert in der Datenbank, bearbeitbar unter ⚙ Einstellungen.
FELDER = {
    "name": (str, ""), "strasse": (str, ""), "plz_ort": (str, ""), "telefon": (str, ""),
    "ort_fuer_datum": (str, ""),
    "bank_name": (str, ""), "kontoinhaber": (str, ""), "iban": (str, ""), "bic": (str, ""),
    "steuernummer": (str, ""), "kleinunternehmer": (bool, True),
    "startnummer": (int, 1), "angebot_startnummer": (int, 1), "angebot_gueltigkeit_tage": (int, 30),
    "pdf_ordner": (str, os.environ.get("STANDARD_PDF_ORDNER", "/share/rechnungen")),
    "paperless_installiert": (bool, False),
    "paperless_eingangsordner": (str, "" if DESKTOP else "/share/paperless/consume"),
}


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
    return jsonify(absender())


@app.put("/api/einstellungen")
def settings_put():
    daten = request.get_json() or {}
    werte, fehler = {}, []
    for k, (typ, standard) in FELDER.items():
        if k not in daten:
            continue
        v = daten[k]
        if typ is bool:
            werte[k] = bool(v)
        elif typ is int:
            try:
                werte[k] = int(v)
            except (TypeError, ValueError):
                fehler.append(f"„{k}“ muss eine Zahl sein")
                continue
            if werte[k] < 1:
                fehler.append(f"„{k}“ muss mindestens 1 sein")
        else:
            werte[k] = (v or "").strip()
    if fehler:
        return jsonify({"error": "; ".join(fehler)}), 400
    db.save_settings(werte)
    a = absender()
    # Hinweise zu Ordnern (kein Fehler – der Ordner kann z. B. erst später angelegt werden)
    hinweise = []
    if a["paperless_installiert"] and not os.path.isdir(a["paperless_eingangsordner"] or "-"):
        hinweise.append(f"Paperless-Eingangsordner {a['paperless_eingangsordner'] or '(leer)'} wurde nicht gefunden.")
    return jsonify({"einstellungen": a, "hinweise": hinweise})


@app.get("/api/absender")
def get_absender():
    a = absender()
    return jsonify({k: a.get(k) for k in ("name", "strasse", "plz_ort", "ort_fuer_datum")}
                   | {"vollstaendig": bool(a.get("name") and a.get("iban")),
                      "paperless": bool(a.get("paperless_installiert")),
                      "angebot_gueltigkeit_tage": a.get("angebot_gueltigkeit_tage") or 30,
                      "version": APP_VERSION,
                      "desktop": DESKTOP})


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
        return jsonify({"id": db.save_item(table, _clean(table, request.get_json()))}), 201

    def update(item_id):
        db.save_item(table, _clean(table, request.get_json()), item_id)
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

def _validate_invoice(data, inv_id=None, check_number=True, art="rechnung"):
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
        "gesamt": round(sum(p["preis"] for p in positionen), 2),
    }
    if angebot:
        doc |= {"art": "angebot", "gueltig_bis": data.get("gueltig_bis") or "",
                "hinweise": (data.get("hinweise") or "").strip()}
    else:
        doc["bezahlt"] = bool(data.get("bezahlt"))
    return doc


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
    inv = _validate_invoice(request.get_json())
    inv["kunde_id"] = db.upsert_customer({**inv["kunde"], "id": inv["kunde_id"]})
    inv_id = db.save_invoice(inv)
    angebot_id = (request.get_json() or {}).get("angebot_id")
    if angebot_id and db.get_offer(angebot_id):
        db.set_offer_status(angebot_id, "angenommen", inv_id)
    return jsonify({"id": inv_id, "datei": _write_pdf_file(inv)}), 201


@app.put("/api/rechnungen/<int:inv_id>")
def invoices_update(inv_id):
    db.get_invoice(inv_id) or abort(404)
    inv = _validate_invoice(request.get_json(), inv_id)
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
    db.set_paid(inv_id, request.get_json().get("bezahlt"))
    return "", 204


@app.delete("/api/rechnungen/<int:inv_id>")
def invoices_delete(inv_id):
    db.delete_invoice(inv_id)
    return "", 204


def _pdf_response(inv, download=False):
    disposition = "attachment" if download or request.args.get("download") else "inline"
    return Response(build_invoice_pdf(inv, absender()), mimetype="application/pdf",
                    headers={"Content-Disposition": f'{disposition}; filename="{pdf_filename(inv)}"'})


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
    daten = request.get_json() or {}
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
        ok.append(inv_id)
    return jsonify({"ok": ok, "fehler": fehler})


@app.post("/api/vorschau")
def invoices_preview():
    data = request.get_json()
    data["nummer"] = (data.get("nummer") or "").strip() or "VORSCHAU"
    return _pdf_response(_validate_invoice(data, check_number=False, art=data.get("art") or "rechnung"))


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
    a = _validate_invoice(request.get_json(), offer_id, art="angebot")
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
    status = (request.get_json() or {}).get("status")
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
    data = request.get_json() or {}
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
    print(f"Rechnungen läuft auf Port {port}")
    serve(app, host="0.0.0.0", port=port)

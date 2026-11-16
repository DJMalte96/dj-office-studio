"""Rechnungen – Home Assistant App (Ingress-Weboberfläche + REST-API)."""
import hashlib
import io
import json
import os
import zipfile
from datetime import date, datetime

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import db
import importer
import paperless
from pdf import build_invoice_pdf, pdf_filename

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # Upload alter Rechnungen


def absender():
    """Absender-/Fußzeilendaten aus der App-Konfiguration in Home Assistant."""
    try:
        with open(OPTIONS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


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

@app.get("/api/absender")
def get_absender():
    a = absender()
    return jsonify({k: a.get(k) for k in ("name", "strasse", "plz_ort", "ort_fuer_datum")}
                   | {"vollstaendig": bool(a.get("name") and a.get("iban")),
                      "paperless": bool(_paperless_config(a))})


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

def _validate_invoice(data, inv_id=None, check_number=True):
    errors = []
    kunde = data.get("kunde") or {}
    if not (kunde.get("name") or "").strip():
        errors.append("Kundenname fehlt")
    nummer = (data.get("nummer") or "").strip()
    if not nummer:
        errors.append("Rechnungsnummer fehlt")
    elif check_number and db.number_taken(nummer, inv_id):
        errors.append(f"Rechnungsnummer {nummer} ist bereits vergeben")
    positionen = [p for p in data.get("positionen") or [] if (p.get("beschreibung") or "").strip()]
    if not positionen:
        errors.append("Mindestens eine Position mit Beschreibung angeben")
    for p in positionen:
        try:
            p["preis"] = round(float(p.get("preis") or 0), 2)
        except (TypeError, ValueError):
            errors.append(f"Ungültiger Preis bei '{p['beschreibung'][:30]}'")
    if not (data.get("zahlungsbedingung") or "").strip():
        errors.append("Zahlungsbedingung fehlt")
    if errors:
        abort(Response(json.dumps({"error": "; ".join(errors)}), 400, mimetype="application/json"))
    return {
        "nummer": nummer,
        "datum": data.get("datum") or date.today().isoformat(),
        "kunde": {k: (kunde.get(k) or "").strip() for k in db.TABLES["kunden"]},
        "kunde_id": kunde.get("id"),
        "positionen": [{"beschreibung": p["beschreibung"].strip(),
                        "lieferdatum": p.get("lieferdatum") or "",
                        "preis": p["preis"]} for p in positionen],
        "zahlungsbedingung": data["zahlungsbedingung"].strip(),
        "gesamt": round(sum(p["preis"] for p in positionen), 2),
        "bezahlt": bool(data.get("bezahlt")),
    }


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
    return jsonify({"id": inv_id, "datei": _write_pdf_file(inv)}), 201


@app.put("/api/rechnungen/<int:inv_id>")
def invoices_update(inv_id):
    db.get_invoice(inv_id) or abort(404)
    inv = _validate_invoice(request.get_json(), inv_id)
    inv["kunde_id"] = db.upsert_customer({**inv["kunde"], "id": inv["kunde_id"]})
    db.save_invoice(inv, inv_id)
    return jsonify({"id": inv_id, "datei": _write_pdf_file(inv)})


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


@app.get("/api/rechnungen/download")
def invoices_download():
    """Mehrere Rechnungen auf einmal: ?ids=1,2,3 → ZIP (bei genau einer Rechnung direkt das PDF)."""
    try:
        ids = [int(x) for x in request.args.get("ids", "").split(",") if x.strip()]
    except ValueError:
        abort(400)
    invoices = [inv for inv in (db.get_invoice(i) for i in dict.fromkeys(ids)) if inv]
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
    zip_name = f"Rechnungen_{date.today():%Y-%m-%d}.zip"
    return Response(buf.getvalue(), mimetype="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{zip_name}"'})


# ---------- Paperless-ngx ----------

def _paperless_config(a=None):
    a = a if a is not None else absender()
    url, token = (a.get("paperless_url") or "").strip(), (a.get("paperless_token") or "").strip()
    return (url, token) if url and token else None


@app.post("/api/paperless")
def invoices_to_paperless():
    """Ausgewählte Rechnungen als PDF an Paperless-ngx schicken: {"ids": [1, 2, 3]}."""
    a = absender()
    cfg = _paperless_config(a)
    if not cfg:
        return jsonify({"error": "Paperless ist nicht eingerichtet – bitte paperless_url und "
                                 "paperless_token in der App-Konfiguration eintragen."}), 400
    client = paperless.Paperless(*cfg)
    tags = [t.strip() for t in (a.get("paperless_tags") or "").split(",") if t.strip()]
    doc_type = a.get("paperless_dokumenttyp") or ""
    mit_kunde = a.get("paperless_kunde_als_korrespondent", True)

    ok, fehler = [], []
    for inv_id in dict.fromkeys(request.get_json().get("ids") or []):
        inv = db.get_invoice(inv_id)
        if not inv:
            continue
        name = pdf_filename(inv)
        try:
            client.upload(build_invoice_pdf(inv, a), name, title=name.removesuffix(".pdf"),
                          created=inv["datum"],
                          correspondent=inv["kunde"].get("name") if mit_kunde else None,
                          document_type=doc_type, tags=tags)
        except paperless.PaperlessError as e:
            fehler.append({"id": inv_id, "name": name, "error": str(e)})
            if e.fatal:
                break   # Verbindungs-/Anmeldeproblem betrifft alle weiteren genauso
            continue
        db.set_paperless(inv_id, datetime.now().isoformat(timespec="seconds"))
        ok.append(inv_id)
    return jsonify({"ok": ok, "fehler": fehler})


@app.post("/api/vorschau")
def invoices_preview():
    data = request.get_json()
    data["nummer"] = (data.get("nummer") or "").strip() or "VORSCHAU"
    return _pdf_response(_validate_invoice(data, check_number=False))


# ---------- Import alter Rechnungen ----------

def _norm_key(s):
    return " ".join((s or "").lower().split())


@app.post("/api/import/analyse")
def import_analyse():
    """PDFs auslesen und Vorschläge liefern – speichert noch nichts."""
    rechnungen, fehler = [], []
    for f in request.files.getlist("dateien"):
        try:
            inv = importer.parse_invoice(importer.pdf_text(f.read()))
            if not inv["kunde"].get("name") or not inv["positionen"]:
                raise ValueError("Empfänger oder Positionen nicht erkannt")
            inv["datei"] = f.filename
            inv["nummer_vorhanden"] = db.number_taken(inv["nummer"])
            rechnungen.append(inv)
        except ValueError as e:
            fehler.append({"datei": f.filename, "fehler": str(e)})
        except Exception:  # defekte/fremde PDFs sollen den Rest nicht aufhalten
            app.logger.exception("Import von %s fehlgeschlagen", f.filename)
            fehler.append({"datei": f.filename, "fehler": "PDF konnte nicht gelesen werden (defekt oder geschützt)"})

    # Empfänger (einmalig je Name+Ort)
    bekannte = {(_norm_key(k["name"]), _norm_key(k["ort"])) for k in db.list_items("kunden")}
    kunden, seen = [], set()
    for inv in sorted(rechnungen, key=lambda r: r["datum"], reverse=True):  # neueste Adresse gewinnt
        k = inv["kunde"]
        key = (_norm_key(k["name"]), _norm_key(k["ort"]))
        if key not in seen:
            seen.add(key)
            kunden.append({**k, "vorhanden": key in bekannte})

    # Textbaustein-Vorschläge (gleiche Texte zusammengefasst, vorhandene ausgelassen)
    vorhandene = db.list_items("textbausteine")
    vorhandene_tb = {_norm_key(t["text"]) for t in vorhandene} | {_norm_key(t["titel"]) for t in vorhandene}
    vorschlaege = {}
    for inv in rechnungen:
        for p in inv["positionen"]:
            v = importer.textbaustein_vorschlag(p["beschreibung"])
            key = _norm_key(v["text"])
            if key in vorhandene_tb or _norm_key(v["titel"]) in vorhandene_tb:
                continue
            vorschlaege.setdefault(key, {**v, "anzahl": 0})["anzahl"] += 1
    textbausteine = sorted(vorschlaege.values(), key=lambda v: -v["anzahl"])

    rechnungen.sort(key=lambda r: r["nummer"])
    return jsonify({"rechnungen": rechnungen, "kunden": kunden,
                    "textbausteine": textbausteine, "fehler": fehler})


@app.post("/api/import/uebernehmen")
def import_uebernehmen():
    data = request.get_json() or {}
    n_kunden = n_tb = n_rech = 0
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
    return jsonify({"kunden": n_kunden, "textbausteine": n_tb, "rechnungen": n_rech})


if __name__ == "__main__":
    from waitress import serve

    db.init()
    port = int(os.environ.get("PORT", "8099"))
    print(f"Rechnungen läuft auf Port {port}")
    serve(app, host="0.0.0.0", port=port)

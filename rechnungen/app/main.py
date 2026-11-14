"""Rechnungen – Home Assistant App (Ingress-Weboberfläche + REST-API)."""
import hashlib
import json
import os
from datetime import date

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import db
from pdf import build_invoice_pdf, pdf_filename

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(__name__, static_folder=None)


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
                   | {"vollstaendig": bool(a.get("name") and a.get("iban"))})


# ---------- Stammdaten (Kunden, Textbausteine, Zahlungsbedingungen) ----------

def _clean(table, data):
    out = {}
    for col in db.TABLES[table]:
        v = data.get(col)
        if col in ("preis", "grundpreis", "grundstunden", "stundensatz"):
            v = float(v) if v not in (None, "") else None
        elif col == "sortierung":
            v = int(v or 0)
        else:
            v = (v or "").strip()
        out[col] = v
    required = {"kunden": "name", "textbausteine": "text", "zahlungsbedingungen": "text"}[table]
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
    return jsonify(db.list_invoices())


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


def _pdf_response(inv):
    disposition = "attachment" if request.args.get("download") else "inline"
    return Response(build_invoice_pdf(inv, absender()), mimetype="application/pdf",
                    headers={"Content-Disposition": f'{disposition}; filename="{pdf_filename(inv)}"'})


@app.get("/api/rechnungen/<int:inv_id>/pdf")
def invoices_pdf(inv_id):
    return _pdf_response(db.get_invoice(inv_id) or abort(404))


@app.post("/api/vorschau")
def invoices_preview():
    data = request.get_json()
    data["nummer"] = (data.get("nummer") or "").strip() or "VORSCHAU"
    return _pdf_response(_validate_invoice(data, check_number=False))


if __name__ == "__main__":
    from waitress import serve

    db.init()
    port = int(os.environ.get("PORT", "8099"))
    print(f"Rechnungen läuft auf Port {port}")
    serve(app, host="0.0.0.0", port=port)

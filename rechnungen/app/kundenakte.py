"""Kundenakte (seit 1.14): „Bar bezahlt“ vermerken und die Jahres-Erinnerung für Stammkunden ausblenden.

Bar bezahlt: Die Quittung schreibt man von Hand auf den Quittungsblock – die App erzeugt keine Quittung, sie vermerkt nur
die Zahlung (Betrag, Tag, optional Nummer vom Block und ein Foto vom Durchschlag). Der Vermerk erscheint in der
Kundenakte und erledigt die Erinnerung „Rechnung schreiben“; in EÜR, Export und Kleinunternehmer-Grenze zählt er nicht.

Kennzahlen und Erinnerungen rechnet die Oberfläche aus Rechnungen, Angeboten, Verträgen und Barzahlungen; hier liegt
nur, was gespeichert werden muss.
"""
import json
import os
import re
import uuid
from datetime import date

from flask import Blueprint, abort, jsonify, request, send_file

import db

bp = Blueprint("kundenakte", __name__)
ORDNER = "barzahlungen"              # unter DATA_DIR: Fotos vom Durchschlag (kommt in die Datensicherung)
MAX_DATEI = 20 * 1024 * 1024
ENDUNGEN = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".heic": "image/heic", ".heif": "image/heif"}


def _fehler(text, code=400):
    return jsonify({"error": text}), code


def _ist_datum(text):
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text or "")) and bool(date.fromisoformat(text))
    except ValueError:
        return False


def _ordner():
    pfad = os.path.join(db.DATA_DIR, ORDNER)
    os.makedirs(pfad, exist_ok=True)
    return pfad


def _sicherer_pfad(rel):
    """Datei nur innerhalb von barzahlungen/ – auch nach einer manipulierten Sicherung."""
    if not rel or "/" in rel or "\\" in rel or rel in (".", ".."):
        return None
    basis = os.path.realpath(_ordner())
    pfad = os.path.realpath(os.path.join(basis, rel))
    return pfad if os.path.dirname(pfad) == basis and os.path.isfile(pfad) else None


def _aus_zeile(r):
    d = dict(r)
    d["kunde"] = json.loads(d.pop("kunde_json") or "{}")
    d["hat_beleg"] = bool(d.pop("beleg_datei"))
    return d


def liste():
    with db.connect() as con:
        return [_aus_zeile(r) for r in con.execute("SELECT * FROM barzahlungen ORDER BY datum DESC, id DESC")]


def _betrag(v):
    """„450“, „450,50“, „1.200,00“ oder Zahl → float; None, wenn kein Betrag."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(float(v), 2)
    t = str(v or "").strip().replace("€", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def _herkunft(vertrag_id, angebot_id):
    """Kunde, Anlass und Feiertag aus Vertrag bzw. Angebot."""
    import vertraege
    v = vertraege.lesen(vertrag_id) if vertrag_id else None
    if vertrag_id and not v:
        return None
    if v and v.get("angebot_id"):
        angebot_id = angebot_id or v["angebot_id"]
    a = db.get_offer(angebot_id) if angebot_id else None
    if angebot_id and not a:
        return None
    if v:
        return {"kunde": v["kunde"], "kunde_id": v.get("kunde_id"), "anlass": v.get("anlass") or "",
                "feier_datum": v.get("datum") or "", "vertrag_id": v["id"], "angebot_id": a["id"] if a else None}
    if a:
        aus = vertraege._aus_angebot(a)
        return {"kunde": a["kunde"], "kunde_id": a.get("kunde_id"), "anlass": aus["anlass"],
                "feier_datum": aus["datum"], "vertrag_id": None, "angebot_id": a["id"]}
    return {"vertrag_id": None, "angebot_id": None}


@bp.get("/api/barzahlungen")
def barzahlungen_liste():
    return jsonify(liste())


@bp.post("/api/barzahlungen")
def barzahlung_anlegen():
    """Bar bezahlt vermerken. Formular (wegen des optionalen Fotos): betrag, datum, quittung_nr, vertrag_id | angebot_id
    oder kunde (JSON) für eine Barzahlung ohne Vertrag und Angebot, beleg (Datei)."""
    f = request.form
    betrag = _betrag(f.get("betrag"))
    if betrag is None or betrag <= 0:
        return _fehler("Bitte den erhaltenen Betrag eintragen")
    if betrag > 1_000_000:
        return _fehler("Der Betrag ist ungewöhnlich hoch – bitte prüfen")
    datum = (f.get("datum") or "").strip()
    if not _ist_datum(datum):
        return _fehler("Bitte das Datum angeben, an dem bezahlt wurde")
    vid = int(f["vertrag_id"]) if (f.get("vertrag_id") or "").isdigit() else None
    aid = int(f["angebot_id"]) if (f.get("angebot_id") or "").isdigit() else None
    h = _herkunft(vid, aid)
    if h is None:
        return _fehler("Vertrag bzw. Angebot nicht gefunden", 404)
    if "kunde" not in h:
        try:
            kunde = json.loads(f.get("kunde") or "{}")
        except ValueError:
            kunde = {}
        kunde = {k: str(kunde.get(k) or "").strip()[:300] for k in ("name", "zusatz", "strasse", "plz", "ort", "email")} \
            if isinstance(kunde, dict) else {}
        if not kunde.get("name"):
            return _fehler("Bitte den Kunden angeben")
        h.update(kunde=kunde, kunde_id=None, anlass=str(f.get("anlass") or "").strip()[:200], feier_datum="")
    datei = request.files.get("beleg")
    gespeichert = name = None
    if datei and datei.filename:
        endung = os.path.splitext(datei.filename)[1].lower()
        if endung not in ENDUNGEN:
            return _fehler("Bitte ein Foto (JPG, PNG, HEIC) oder ein PDF hochladen")
        inhalt = datei.read(MAX_DATEI + 1)
        if len(inhalt) > MAX_DATEI:
            return _fehler("Die Datei ist größer als 20 MB", 413)
        import vertraege
        if not vertraege._inhalt_passt(endung, inhalt):
            return _fehler("Die Datei passt nicht zu ihrer Endung – bitte ein echtes Foto oder PDF hochladen")
        gespeichert = f"{uuid.uuid4().hex}{endung}"
        with open(os.path.join(_ordner(), gespeichert), "wb") as out:
            out.write(inhalt)
        name = os.path.basename(datei.filename)[:200]

    try:
        with db.connect() as con:
            bid = con.execute(
                "INSERT INTO barzahlungen (datum, betrag, kunde_id, kunde_json, angebot_id, vertrag_id, anlass,"
                " feier_datum, quittung_nr, beleg_datei, beleg_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (datum, betrag, h.get("kunde_id"), json.dumps(h["kunde"]), h["angebot_id"], h["vertrag_id"],
                 h["anlass"], h["feier_datum"], str(f.get("quittung_nr") or "").strip()[:40], gespeichert, name)).lastrowid
    except Exception:
        if gespeichert:
            os.remove(os.path.join(_ordner(), gespeichert))
        raise
    if h["angebot_id"]:                       # bar bezahlt heißt: das Angebot wurde angenommen
        a_ = db.get_offer(h["angebot_id"])
        if a_ and a_["status"] != "angenommen":
            db.set_offer_status(a_["id"], "angenommen")
    with db.connect() as con:
        return jsonify(_aus_zeile(con.execute("SELECT * FROM barzahlungen WHERE id = ?", (bid,)).fetchone())), 201


@bp.delete("/api/barzahlungen/<int:bid>")
def barzahlung_loeschen(bid):
    with db.connect() as con:
        r = con.execute("SELECT beleg_datei FROM barzahlungen WHERE id = ?", (bid,)).fetchone() or abort(404)
        con.execute("DELETE FROM barzahlungen WHERE id = ?", (bid,))
    pfad = _sicherer_pfad(r["beleg_datei"])
    if pfad:
        try:
            os.remove(pfad)
        except OSError:   # z. B. unter Windows gerade geöffnet – der Vermerk ist trotzdem gelöscht
            pass
    return "", 204


@bp.get("/api/barzahlungen/<int:bid>/beleg")
def barzahlung_beleg(bid):
    with db.connect() as con:
        r = con.execute("SELECT beleg_datei, beleg_name, datum FROM barzahlungen WHERE id = ?", (bid,)).fetchone() or abort(404)
    pfad = _sicherer_pfad(r["beleg_datei"]) or abort(404)
    endung = os.path.splitext(pfad)[1].lower()
    # immer als Download – eine hochgeladene Datei wird nie als Seite der App angezeigt
    return send_file(pfad, mimetype=ENDUNGEN.get(endung, "application/octet-stream"), as_attachment=True,
                     download_name=r["beleg_name"] or f"Quittung_{r['datum']}{endung}")


# ---------- Notizen zum Kunden (seit 1.15) ----------

NOTIZ_MAX = 5000


@bp.put("/api/kunden/<int:kid>/notiz")
def notiz_speichern(kid):
    """Eigene Notiz zum Kunden – nur in der App (Kundenakte, Editor), nie auf Rechnung, Angebot oder E-Rechnung."""
    d = request.get_json(silent=True)
    text = str((d or {}).get("notiz") or "").strip() if isinstance(d, dict) else ""
    if len(text) > NOTIZ_MAX:
        return _fehler(f"Die Notiz ist zu lang (höchstens {NOTIZ_MAX} Zeichen).")
    with db.connect() as con:
        if not con.execute("UPDATE kunden SET notiz = ? WHERE id = ?", (text, kid)).rowcount:
            abort(404)
    return jsonify({"id": kid, "notiz": text})


# ---------- Doppelte Kunden zusammenführen (seit 1.16) ----------

def _norm(text):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).replace("ß", "ss")
    t = re.sub(r"strasse\b|str\.|\bstr\b", "str", t)
    return re.sub(r"[^a-z0-9]", "", t)


def _abstand(a, b):
    """Tippfehler-Abstand (Levenshtein)."""
    vorher = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        jetzt = [i]
        for j, y in enumerate(b, 1):
            jetzt.append(min(vorher[j] + 1, jetzt[j - 1] + 1, vorher[j - 1] + (x != y)))
        vorher = jetzt
    return vorher[-1]


def _kunden():
    with db.connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM kunden ORDER BY id")]


def duplikate():
    """Vermutlich doppelte Kunden: gleiche Anschrift und (fast) gleicher Name, oder gleicher Name mit gleicher PLZ."""
    kunden = _kunden()
    with db.connect() as con:
        nein = {(r["a"], r["b"]) for r in con.execute("SELECT a, b FROM kunden_kein_duplikat")}
        belege = {}
        for tab in ("rechnungen", "angebote", "vertraege"):
            for r in con.execute(f"SELECT kunde_id, COUNT(*) n FROM {tab} WHERE kunde_id IS NOT NULL GROUP BY kunde_id"):
                belege.setdefault(r["kunde_id"], {})[tab] = r["n"]
    paare = []
    for i, a in enumerate(kunden):
        for b in kunden[i + 1:]:
            if (a["id"], b["id"]) in nein:
                continue
            na, nb = _norm(a["name"]), _norm(b["name"])
            if not na or not nb:
                continue
            adresse = _norm(a["strasse"]) and _norm(a["strasse"]) == _norm(b["strasse"]) and (a["plz"] or "") == (b["plz"] or "")
            nah = na != nb and _abstand(na, nb) <= (1 if min(len(na), len(nb)) < 8 else 2)
            if adresse and na == nb:
                grund = "gleicher Name und gleiche Anschrift"
            elif adresse and nah:
                grund = "gleiche Anschrift, fast gleicher Name (Tippfehler?)"
            elif na == nb and (a["plz"] or "") == (b["plz"] or "") and (a["plz"] or a["ort"]):
                grund = "gleicher Name, gleiche Postleitzahl"
            else:
                continue
            paare.append({"a": a | {"belege": belege.get(a["id"], {})}, "b": b | {"belege": belege.get(b["id"], {})}, "grund": grund})
    return paare


@bp.get("/api/kunden/duplikate")
def duplikate_api():
    return jsonify(duplikate())


@bp.post("/api/kunden/kein-duplikat")
def kein_duplikat():
    d = request.get_json(silent=True) or {}
    try:
        a, b = sorted((int(d.get("a")), int(d.get("b"))))
    except (TypeError, ValueError):
        return _fehler("Ungültige Angabe")
    with db.connect() as con:
        con.execute("INSERT OR IGNORE INTO kunden_kein_duplikat (a, b) VALUES (?, ?)", (a, b))
    return "", 204


@bp.post("/api/kunden/zusammenfuehren")
def zusammenfuehren():
    """{behalten, weg}: Alles vom Eintrag „weg“ gehört danach zu „behalten“ – Rechnungen, Angebote, Verträge,
    Barzahlungen. Belege selbst ändern sich nicht (Name und Anschrift bleiben, wie sie verschickt wurden);
    entfernt wird nur der doppelte Stammdaten-Eintrag. Sein Name wird gemerkt, damit die Kundenakte alles findet."""
    d = request.get_json(silent=True) or {}
    try:
        behalten, weg = int(d.get("behalten")), int(d.get("weg"))
    except (TypeError, ValueError):
        return _fehler("Ungültige Angabe")
    if behalten == weg:
        return _fehler("Bitte zwei verschiedene Kunden wählen")
    with db.connect() as con:
        k = con.execute("SELECT * FROM kunden WHERE id = ?", (behalten,)).fetchone()
        w = con.execute("SELECT * FROM kunden WHERE id = ?", (weg,)).fetchone()
        if not k or not w:
            abort(404)
        zahlen = {}
        for tab in ("rechnungen", "angebote", "vertraege", "barzahlungen"):
            zahlen[tab] = con.execute(f"UPDATE {tab} SET kunde_id = ? WHERE kunde_id = ?", (behalten, weg)).rowcount
        namen = [n for n in dict.fromkeys(json.loads(k["weitere_namen"] or "[]") + [w["name"]] + json.loads(w["weitere_namen"] or "[]"))
                 if _norm(n) != _norm(k["name"])]
        felder = {f: k[f] or w[f] or "" for f in ("zusatz", "strasse", "plz", "ort", "email")}
        notiz = "\n".join(n for n in dict.fromkeys(x.strip() for x in (k["notiz"] or "", w["notiz"] or "")) if n)
        con.execute("UPDATE kunden SET zusatz = ?, strasse = ?, plz = ?, ort = ?, email = ?, notiz = ?, weitere_namen = ? WHERE id = ?",
                    (*felder.values(), notiz[:NOTIZ_MAX], json.dumps(namen, ensure_ascii=False), behalten))
        con.execute("DELETE FROM kunden WHERE id = ?", (weg,))
        con.execute("DELETE FROM kunden_kein_duplikat WHERE a = ? OR b = ?", (weg, weg))
    return jsonify({"behalten": behalten, "verschoben": zahlen, "weitere_namen": namen})


# ---------- Jahres-Erinnerung ----------

def _schluessel(name):
    return re.sub(r"\s+", " ", str(name or "")).strip().lower()[:300]


@bp.get("/api/kunden/erinnerung")
def erinnerung_lesen():
    with db.connect() as con:
        return jsonify({r["kunde"]: r["ruhe"] for r in con.execute("SELECT kunde, ruhe FROM kunden_erinnerung")})


@bp.put("/api/kunden/erinnerung")
def erinnerung_setzen():
    """{name, ruhe}: ruhe = 'nie' (nicht mehr erinnern), ein Datum (diesmal nicht – bis zu diesem Jahrestag) oder
    null (wieder einschalten)."""
    d = request.get_json(silent=True)
    d = d if isinstance(d, dict) else {}
    kunde, ruhe = _schluessel(d.get("name")), d.get("ruhe")
    if not kunde:
        return _fehler("Kunde fehlt")
    if ruhe is not None and ruhe != "nie" and not _ist_datum(ruhe):
        return _fehler("Ungültige Angabe")
    with db.connect() as con:
        if ruhe is None:
            con.execute("DELETE FROM kunden_erinnerung WHERE kunde = ?", (kunde,))
        else:
            con.execute("INSERT INTO kunden_erinnerung (kunde, ruhe) VALUES (?, ?)"
                        " ON CONFLICT(kunde) DO UPDATE SET ruhe = excluded.ruhe", (kunde, ruhe))
    return "", 204

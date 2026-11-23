"""Abos – wiederkehrende Ausgaben (seit 1.9): Musikpool, Software & Co. einmal anlegen; fällige Abbuchungen erscheinen
unter „Neu – bitte prüfen“ und werden mit einem Klick bestätigt. Erst dann gibt es eine Ausgabe (zählt in der EÜR).

Kommt die Rechnung als Mail/PDF herein oder ist die Zahlung schon als Ausgabe erfasst, erkennt die App sie
(Lieferant, Betrag, Datum bis 10 Tage daneben) und verknüpft statt doppelt zu buchen.
"""
import calendar
import re
from datetime import date, timedelta

from flask import Blueprint, abort, jsonify, request

import db
import finanzen

bp = Blueprint("abos", __name__)

# Rhythmus → („w“ Wochen | „m“ Monate, Anzahl, Anzeige)
RHYTHMEN = {
    "woechentlich": ("w", 1, "wöchentlich"), "vierwochen": ("w", 4, "alle 4 Wochen"),
    "monatlich": ("m", 1, "monatlich"), "zweimonatlich": ("m", 2, "alle 2 Monate"),
    "vierteljaehrlich": ("m", 3, "vierteljährlich"), "halbjaehrlich": ("m", 6, "halbjährlich"),
    "jaehrlich": ("m", 12, "jährlich"), "zweijaehrlich": ("m", 24, "alle 2 Jahre"),
    "eigen": (None, None, "eigener Rhythmus"),
}
EINHEITEN = {"wochen": ("Woche", "Wochen"), "monate": ("Monat", "Monate"), "jahre": ("Jahr", "Jahre")}
VORSCHLAEGE = [{"lieferant": "Musikpool", "beschreibung": "DJ-Musikpool (Monatsabo)", "kategorie": "musik", "rhythmus": "monatlich"},
               {"lieferant": "DJ-Software", "beschreibung": "Software-Abo", "kategorie": "musik", "rhythmus": "monatlich"}]
TOLERANZ_TAGE = 10       # Beleg passt zur Abbuchung, wenn sein Datum höchstens so weit daneben liegt
NOTIZ = "aus Abo – Beleg fehlt (z. B. Kontoauszug)"
MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember")
DATUM = re.compile(r"\d{4}-\d{2}-\d{2}")


# ---------- Termine ----------

def schritt(abo):
    """→ („w“, Wochen) oder („m“, Monate)."""
    art, n, _ = RHYTHMEN.get(abo["rhythmus"], RHYTHMEN["monatlich"])
    if art:
        return art, n
    n = max(1, int(abo.get("anzahl") or 1))
    return ("w", n) if abo.get("einheit") == "wochen" else ("m", n * 12 if abo.get("einheit") == "jahre" else n)


def rhythmus_name(abo):
    if abo["rhythmus"] != "eigen":
        return RHYTHMEN.get(abo["rhythmus"], RHYTHMEN["monatlich"])[2]
    n = max(1, int(abo.get("anzahl") or 1))
    eins, viele = EINHEITEN.get(abo.get("einheit"), EINHEITEN["monate"])
    return f"jede{'' if abo.get('einheit') == 'wochen' else 'n'} {eins}" if n == 1 else f"alle {n} {viele}"


def _alle(abo):
    """Alle Abbuchungstermine ab dem Beginn (ISO-Datum), bis zum Ende des Abos – als Generator."""
    beginn = date.fromisoformat(abo["beginn"])
    art, n = schritt(abo)
    i = 0
    while True:
        if art == "w":
            d = (beginn + timedelta(weeks=n * i)).isoformat()
        else:
            monat = beginn.month - 1 + i * n
            j, m = beginn.year + monat // 12, monat % 12 + 1
            if j > 9999:
                return
            tag = int(abo.get("tag") or beginn.day)
            d = date(j, m, min(tag, calendar.monthrange(j, m)[1])).isoformat()   # 31. im Februar → 28./29.
        i += 1
        if abo.get("ende") and d > abo["ende"]:
            return
        if d >= abo["beginn"]:
            yield d


def termine(abo, bis):
    """Abbuchungstermine vom Beginn bis einschließlich „bis“ (ISO-Datum)."""
    out = []
    for d in _alle(abo):
        if d > bis:
            break
        out.append(d)
    return out


def naechster(abo, heute):
    return next((d for d in _alle(abo) if d > heute), None)


def betrag_am(abo, preise, datum):
    """Betrag zu einem Termin: letzte Preisänderung bis zu diesem Tag, sonst der ursprüngliche Betrag."""
    gueltig = [p for p in preise if p["ab"] <= datum]
    return max(gueltig, key=lambda p: p["ab"])["betrag"] if gueltig else abo["betrag"]


def zehn_tage_jahr(abo, datum):
    """10-Tage-Regel: Abbuchung ab dem 22.12. für den nächsten Zeitraum gehört ins neue Jahr (nur Monats-/Jahres-Rhythmen;
    ein Wochen-Abo vom 23.12. betrifft diese Woche)."""
    if schritt(abo)[0] == "m" and datum[5:] >= "12-22":
        return int(datum[:4]) + 1
    return None


# ---------- Laden ----------

def _abos(con):
    abos = [dict(r) for r in con.execute("SELECT * FROM abos ORDER BY lieferant COLLATE NOCASE, id")]
    preise = {}
    for p in con.execute("SELECT * FROM abo_preise ORDER BY ab"):
        preise.setdefault(p["abo_id"], []).append(dict(p))
    for a in abos:
        a["preise"] = preise.get(a["id"], [])
    return abos


def _normal(s):
    return re.sub(r"[^a-z0-9äöüß]", "", (s or "").lower())


def _passt(abo, betrag, x):
    """Ausgabe x (Beleg oder Buchung) passt zu einer Abbuchung über „betrag“?"""
    if x.get("betrag") is None or abs(x["betrag"] - betrag) > 0.005:
        return False
    a, b = _normal(abo["lieferant"]), _normal(x.get("lieferant"))
    if len(a) < 4 or len(b) < 4 or not (a[:8] in b or b[:8] in a):
        return False
    return True


def _nah(datum, x):
    try:
        tag = date.fromisoformat((x.get("bezahlt_am") or x.get("belegdatum") or "")[:10])
    except ValueError:
        return False
    return abs((tag - date.fromisoformat(datum)).days) <= TOLERANZ_TAGE


def faellig(heute=None, jahr=None):
    """Fällige, noch nicht bestätigte Abbuchungen (optional nur eines Jahres) – mit passendem Beleg bzw. schon
    erfasster Ausgabe, falls vorhanden."""
    heute = (heute or date.today()).isoformat()
    zu = db.abgeschlossene_jahre()
    with db.connect() as con:
        abos = _abos(con)
        erledigt = {(r["abo_id"], r["datum"]) for r in con.execute("SELECT abo_id, datum FROM abo_termine")}
        kandidaten = [finanzen._zeile(r) for r in con.execute(
            "SELECT * FROM ausgaben WHERE (status = 'neu' OR (status = 'ok' AND abo_id IS NULL)) AND betrag IS NOT NULL")]
    vergeben, out = set(), []
    for abo in abos:
        for d in termine(abo, heute):
            if (abo["id"], d) in erledigt or (abo.get("erfasst_bis") and d <= abo["erfasst_bis"]):
                continue
            if jahr and not d.startswith(str(jahr)):
                continue
            betrag = betrag_am(abo, abo["preise"], d)
            treffer = next((x for x in sorted(kandidaten, key=lambda x: x["status"] != "neu")
                            if x["id"] not in vergeben and _passt(abo, betrag, x) and _nah(d, x)), None)
            if treffer:
                vergeben.add(treffer["id"])
            out.append({"abo_id": abo["id"], "datum": d, "betrag": betrag, "lieferant": abo["lieferant"],
                        "beschreibung": abo["beschreibung"], "rhythmus": abo["rhythmus"], "rhythmus_name": rhythmus_name(abo),
                        "gesperrt": int(d[:4]) in zu, "zehn_tage": zehn_tage_jahr(abo, d),
                        "beleg": _kurz(treffer) if treffer and treffer["status"] == "neu" else None,
                        "vorhanden": _kurz(treffer) if treffer and treffer["status"] == "ok" else None})
    return sorted(out, key=lambda f: (f["datum"], f["lieferant"].lower()))


def _kurz(x):
    return {"id": x["id"], "lieferant": x["lieferant"], "betrag": x["betrag"], "datum": x.get("bezahlt_am") or x.get("belegdatum"),
            "name": x.get("beleg_name") or ""}


def offene_im_jahr(jahr):
    return faellig(jahr=jahr)


# ---------- Bestätigen ----------

def _monat(datum):
    return f"{MONATE[int(datum[5:7]) - 1]} {datum[:4]}"


def bestaetigen(abo_id, datum, aktion, betrag=None, ab_jetzt=False, beleg_id=None, ausgabe_id=None, heute=None):
    heute = (heute or date.today()).isoformat()
    with db.connect() as con:
        abo = next((a for a in _abos(con) if a["id"] == abo_id), None) or abort(404)
        if not DATUM.fullmatch(datum or "") or datum > heute or datum not in termine(abo, heute):
            raise ValueError("An diesem Tag ist keine Abbuchung dieses Abos fällig.")
        if con.execute("SELECT 1 FROM abo_termine WHERE abo_id = ? AND datum = ?", (abo_id, datum)).fetchone():
            raise ValueError("Diese Abbuchung ist schon erledigt.")
        if aktion == "aus":
            con.execute("INSERT INTO abo_termine (abo_id, datum, status) VALUES (?, ?, 'aus')", (abo_id, datum))
            return None
        if aktion != "ok":
            raise ValueError("Unbekannte Aktion")
        if betrag is not None and ab_jetzt:
            con.execute("INSERT INTO abo_preise (abo_id, ab, betrag) VALUES (?, ?, ?) ON CONFLICT(abo_id, ab) DO UPDATE SET betrag = excluded.betrag",
                        (abo_id, datum, betrag))
        wert = betrag if betrag is not None else betrag_am(abo, abo["preise"], datum)
        euer_jahr = zehn_tage_jahr(abo, datum)
        beschreibung = f"{abo['beschreibung'] or abo['lieferant']} – {_monat(datum)}"
        if beleg_id or ausgabe_id:
            x = con.execute("SELECT * FROM ausgaben WHERE id = ?", (beleg_id or ausgabe_id,)).fetchone()
            if not x or (beleg_id and x["status"] != "neu") or (ausgabe_id and (x["status"] != "ok" or x["abo_id"])):
                raise ValueError("Dieser Beleg passt nicht (mehr) – bitte die Liste neu laden.")
            aid = x["id"]
            if beleg_id:   # Beleg wird zur Ausgabe – Betrag laut Beleg, sofern nicht ausdrücklich geändert
                con.execute("UPDATE ausgaben SET status = 'ok', kategorie = ?, beschreibung = ?, betrag = ?, privatanteil = ?,"
                            " bezahlt_am = ?, belegdatum = COALESCE(belegdatum, ?), lieferant = COALESCE(NULLIF(lieferant, ''), ?),"
                            " abo_id = ?, euer_jahr = ? WHERE id = ?",
                            (abo["kategorie"], beschreibung, betrag if betrag is not None else x["betrag"], abo["privatanteil"] or 0,
                             datum, datum, abo["lieferant"], abo_id, str(euer_jahr) if euer_jahr else None, aid))
            else:          # schon von Hand erfasst: nur verknüpfen, nichts doppelt buchen
                con.execute("UPDATE ausgaben SET abo_id = ? WHERE id = ?", (abo_id, aid))
        else:
            aid = con.execute(
                "INSERT INTO ausgaben (status, belegdatum, bezahlt_am, lieferant, beschreibung, kategorie, betrag, privatanteil, notiz,"
                " abo_id, euer_jahr) VALUES ('ok', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (datum, datum, abo["lieferant"], beschreibung, abo["kategorie"], wert, abo["privatanteil"] or 0, NOTIZ, abo_id,
                 str(euer_jahr) if euer_jahr else None)).lastrowid
        con.execute("INSERT INTO abo_termine (abo_id, datum, status, ausgabe_id) VALUES (?, ?, 'ok', ?)", (abo_id, datum, aid))
    return finanzen.holen(aid)


# ---------- Abos verwalten ----------

def _zahl(v):
    s = str(v if v is not None else "").strip().replace(" ", "").replace("€", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def _werte(d, alt=None):
    """Eingaben prüfen → (werte, fehler)."""
    w, fehler = {}, []
    alt = alt or {}
    for k in ("lieferant", "beschreibung"):
        if k in d or not alt:
            w[k] = " ".join(str(d.get(k) or "").split())[:200]
    if not (w.get("lieferant", alt.get("lieferant")) or "").strip():
        fehler.append("Bitte einen Lieferanten angeben")
    if "kategorie" in d or not alt:
        w["kategorie"] = d.get("kategorie") or "musik"
        if w["kategorie"] not in finanzen.KATEGORIEN or w["kategorie"] == "anschaffung":
            fehler.append("Bitte eine Kategorie wählen (Anschaffungen über 800 € sind kein Abo)")
    if "betrag" in d or not alt:
        try:
            w["betrag"] = round(_zahl(d.get("betrag")), 2)
            if not 0 < w["betrag"] <= 100000:
                raise ValueError
        except (TypeError, ValueError):
            fehler.append("Bitte einen Betrag über 0 € angeben")
    if "rhythmus" in d or not alt:
        w["rhythmus"] = d.get("rhythmus") or "monatlich"
        if w["rhythmus"] not in RHYTHMEN:
            fehler.append("Unbekannter Rhythmus")
    for k, (lo, hi), standard in (("anzahl", (1, 99), 1), ("tag", (1, 31), None)):
        if k in d or not alt:
            try:
                v = d.get(k)
                w[k] = int(v) if v not in (None, "") else (standard or date.today().day)
                if not lo <= w[k] <= hi:
                    raise ValueError
            except (TypeError, ValueError):
                fehler.append("Bitte eine Zahl von 1 bis 99 angeben" if k == "anzahl" else "Bitte einen Tag von 1 bis 31 angeben")
    if "einheit" in d or not alt:
        w["einheit"] = d.get("einheit") or "monate"
        if w["einheit"] not in EINHEITEN:
            fehler.append("Unbekannte Einheit")
    for k in ("beginn", "ende"):
        if k in d or (k == "beginn" and not alt):
            v = (d.get(k) or "").strip() or None
            if (k == "beginn" and not v) or (v and not DATUM.fullmatch(v)):
                fehler.append("Bitte ein Datum für den Beginn angeben" if k == "beginn" else "Ungültiges Enddatum")
            else:
                try:
                    if v:
                        date.fromisoformat(v)
                    w[k] = v
                except ValueError:
                    fehler.append(f"Ungültiges Datum: {v}")
    beginn, ende = w.get("beginn", alt.get("beginn")), w.get("ende", alt.get("ende"))
    if beginn and ende and ende < beginn:
        fehler.append("Das Ende kann nicht vor dem Beginn liegen")
    if "privatanteil" in d or not alt:
        try:
            w["privatanteil"] = round(_zahl(d.get("privatanteil") or 0), 1)
            if not 0 <= w["privatanteil"] <= 100:
                raise ValueError
        except (TypeError, ValueError):
            fehler.append("Privatanteil zwischen 0 und 100 %")
    return w, fehler


def _ausgabe(abo, heute):
    """Für die Liste: aktueller Betrag, Rhythmus, nächste Abbuchung, Kosten im Monat."""
    art, n = schritt(abo)
    betrag = betrag_am(abo, abo["preise"], heute)
    beendet = bool(abo.get("ende")) and abo["ende"] < heute
    pro_monat = 0.0 if beendet else (betrag * 52 / 12 / n if art == "w" else betrag / n)
    return abo | {"rhythmus_name": rhythmus_name(abo), "betrag_aktuell": betrag, "beendet": beendet,
                  "naechste": None if beendet else naechster(abo, heute), "pro_monat": round(pro_monat, 2),
                  "wochenweise": art == "w"}


@bp.get("/api/abos")
def liste_api():
    heute = date.today().isoformat()
    with db.connect() as con:
        abos = [_ausgabe(a, heute) for a in _abos(con)]
    offen = {}
    for f in faellig():
        offen[f["abo_id"]] = offen.get(f["abo_id"], 0) + 1
    for a in abos:
        a["offen"] = offen.get(a["id"], 0)
    return jsonify({"abos": abos, "rhythmen": [{"id": k, "name": v[2]} for k, v in RHYTHMEN.items()],
                    "einheiten": [{"id": k, "name": v[1]} for k, v in EINHEITEN.items()], "vorschlaege": VORSCHLAEGE,
                    "pro_monat": round(sum(a["pro_monat"] for a in abos), 2)})


@bp.get("/api/abos/faellig")
def faellig_api():
    return jsonify(faellig())


@bp.post("/api/abos")
def anlegen():
    d = request.get_json(silent=True) or {}
    w, fehler = _werte(d)
    if fehler:
        return jsonify({"error": "; ".join(fehler)}), 400
    heute = date.today()
    # Frühere Abbuchungen sind meist schon erfasst – nur auf Wunsch nachtragen
    w["erfasst_bis"] = None if d.get("nachtragen") else (heute - timedelta(days=1)).isoformat()
    with db.connect() as con:
        aid = con.execute(f"INSERT INTO abos ({', '.join(w)}) VALUES ({', '.join('?' * len(w))})", list(w.values())).lastrowid
        abo = next(a for a in _abos(con) if a["id"] == aid)
    return jsonify(_ausgabe(abo, heute.isoformat())), 201


@bp.put("/api/abos/<int:aid>")
def aendern(aid):
    d = request.get_json(silent=True) or {}
    heute = date.today().isoformat()
    with db.connect() as con:
        alt = next((a for a in _abos(con) if a["id"] == aid), None) or abort(404)
    w, fehler = _werte(d, alt)
    if fehler:
        return jsonify({"error": "; ".join(fehler)}), 400
    neuer_betrag = w.pop("betrag", None)
    ab = str(d.get("betrag_ab") or heute).strip()
    try:
        if not DATUM.fullmatch(ab):
            raise ValueError
        date.fromisoformat(ab)
    except ValueError:
        return jsonify({"error": "Ungültiges Datum für den neuen Betrag"}), 400
    with db.connect() as con:
        if w:
            con.execute(f"UPDATE abos SET {', '.join(k + ' = ?' for k in w)} WHERE id = ?", [*w.values(), aid])
        if neuer_betrag is not None and abs(neuer_betrag - betrag_am(alt, alt["preise"], ab)) > 0.004:
            # Preisänderung gilt ab dem Datum – frühere Buchungen bleiben, wie sie waren
            con.execute("INSERT INTO abo_preise (abo_id, ab, betrag) VALUES (?, ?, ?) ON CONFLICT(abo_id, ab) DO UPDATE SET betrag = excluded.betrag",
                        (aid, ab, neuer_betrag))
        abo = next(a for a in _abos(con) if a["id"] == aid)
    return jsonify(_ausgabe(abo, heute))


@bp.delete("/api/abos/<int:aid>")
def loeschen(aid):
    """Abo entfernen – schon gebuchte Ausgaben bleiben (ohne Verweis aufs Abo)."""
    with db.connect() as con:
        if not con.execute("DELETE FROM abos WHERE id = ?", (aid,)).rowcount:
            abort(404)
        con.execute("DELETE FROM abo_termine WHERE abo_id = ?", (aid,))
        con.execute("DELETE FROM abo_preise WHERE abo_id = ?", (aid,))
        con.execute("UPDATE ausgaben SET abo_id = NULL WHERE abo_id = ?", (aid,))
    return "", 204


@bp.post("/api/abos/<int:aid>/termine/<datum>")
def termin_api(aid, datum):
    d = request.get_json(silent=True) or {}
    betrag = None
    if d.get("betrag") not in (None, ""):
        try:
            betrag = round(_zahl(d["betrag"]), 2)
            if not 0 < betrag <= 100000:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "Bitte einen Betrag über 0 € angeben"}), 400
    ids = {k: d.get(k) for k in ("beleg_id", "ausgabe_id")}
    if any(v is not None and type(v) is not int for v in ids.values()):
        return jsonify({"error": "Ungültiger Beleg"}), 400
    try:
        a = bestaetigen(aid, datum, d.get("aktion"), betrag, bool(d.get("ab_jetzt")), ids["beleg_id"], ids["ausgabe_id"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    finanzen.anlage_zur_ausgabe(a["id"]) if a else None
    return (jsonify(a), 201) if a else ("", 204)


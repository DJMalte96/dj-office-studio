"""Booking-Verträge (seit 1.13): aus einem Angebot oder ohne Angebot, Vorlage mit Abschnitten (eingebaute Bausteine,
eigene Abschnitte, aus einem hochgeladenen Vertrag übernommen), Anlagen, PDF, Versand und Unterschrift.

Der Vertragstext entsteht nur hier (inhalt) – Vorschau im Browser und PDF zeigen dasselbe. Ab „verschickt“ wird der
Text festgehalten, damit sich ein verschickter oder unterschriebener Vertrag nicht mehr ändert.
"""
import io
import json
import os
import re
import uuid
import zipfile
from datetime import date, datetime

from flask import Blueprint, abort, jsonify, request, send_file

import db

bp = Blueprint("vertraege", __name__)
ORDNER = "vertraege"                 # unter DATA_DIR: anlagen/, unterschrieben/ (kommt in die Datensicherung)
STATUS = ("entwurf", "verschickt", "unterschrieben")
WEGE = {"datei": "unterschrieben zurück", "mail": "per Mail bestätigt", "vorort": "vor Ort unterschrieben"}
ZAHLUNG = ("rechnung", "bar", "ganz")
MAX_DATEI = 20 * 1024 * 1024
UNTERSCHRIFT_ENDUNGEN = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                         ".heic": "image/heic", ".heif": "image/heif"}
HINWEIS = ("Die Texte sind ein Vorschlag und keine Rechtsberatung – bitte einmal prüfen lassen "
           "(z. B. Anwalt oder DJ-Verband) und an deine Bedingungen anpassen.")
PLATZHALTER = ("veranstalter", "dj", "datum", "anlass", "ort", "spielzeit", "gage")

# Eingebaute Bausteine: (id, Titel, standardmäßig an, Text). Nur ein Vorschlag – in der Vorlage frei änderbar.
STANDARD = [
    ("verpflegung", "Verpflegung", True,
     "Der Veranstalter stellt dem DJ während der Veranstaltung kostenfrei alkoholfreie Getränke sowie eine warme Mahlzeit "
     "zur Verfügung{verpflegung_zusatz}."),
    ("ersatz", "Ausfall des DJs, Ersatz-DJ", True,
     "Kann der DJ den Termin wegen Krankheit oder eines anderen unvorhersehbaren, von ihm nicht zu vertretenden Grundes nicht "
     "wahrnehmen, informiert er den Veranstalter unverzüglich und bemüht sich um einen gleichwertigen Ersatz-DJ. Ein Ersatz-DJ "
     "wird nur mit Zustimmung des Veranstalters eingesetzt; es gelten dann die Bedingungen dieses Vertrags. Kommt kein Ersatz "
     "zustande, erstattet der DJ bereits geleistete Zahlungen vollständig. Weitergehende Ansprüche bestehen nur bei Vorsatz "
     "oder grober Fahrlässigkeit des DJs."),
    ("gema", "GEMA", True, "{gema_text}"),
    ("haftung", "Schäden durch Gäste", True,
     "Der DJ haftet nicht für Schäden, die Gäste der Veranstaltung verursachen. Beschädigen Gäste die Technik oder Ausrüstung "
     "des DJs, haftet der Veranstalter gegenüber dem DJ für den entstandenen Schaden, soweit ihn nicht der DJ selbst zu "
     "vertreten hat; der Veranstalter kann sich beim Verursacher schadlos halten. Der Veranstalter sorgt dafür, dass der "
     "Aufbaubereich des DJs nicht von Gästen betreten wird."),
    ("storno", "Stornierung durch den Veranstalter", False,
     "Sagt der Veranstalter die Veranstaltung ab, berechnet der DJ: bis 90 Tage vor dem Termin keine Kosten, bis 30 Tage "
     "vorher 50 % der Gage, danach 100 % der Gage. Bereits geleistete Anzahlungen werden verrechnet."),
    ("verlaengerung", "Verlängerung", False,
     "Wünscht der Veranstalter eine Verlängerung über die vereinbarte Zeit hinaus, wird jede angefangene Stunde mit 80,00 € "
     "berechnet, sofern der DJ zustimmt."),
    ("technik", "Strom, Aufbau, Zufahrt", False,
     "Der Veranstalter stellt einen ebenen, überdachten Platz für den Aufbau, einen Stromanschluss (230 V, separat "
     "abgesichert) in unmittelbarer Nähe sowie eine Zufahrt bzw. einen Parkplatz zum Be- und Entladen bereit."),
    ("musik", "Musikwünsche und Ablauf", False,
     "Musikwünsche, Ablauf (z. B. Eröffnungstanz, Reden, Programmpunkte) und „Bitte nicht spielen“-Titel teilt der "
     "Veranstalter dem DJ bis spätestens zwei Wochen vor der Veranstaltung mit. Im Rahmen dieser Wünsche gestaltet der DJ "
     "das Programm nach eigenem Ermessen und passt es der Stimmung an."),
    ("spielzeit", "Spielzeit, Pausen und Ende", False,
     "Die vereinbarte Spielzeit beginnt mit dem ersten und endet mit dem letzten Musikstück; Auf- und Abbau liegen außerhalb "
     "dieser Zeit. Kurze Pausen des DJs erfolgen ohne Unterbrechung der Musik. Endet die Veranstaltung früher als vereinbart, "
     "bleibt die vereinbarte Gage bestehen."),
    ("laerm", "Lautstärke, Sperrstunde und Auflagen", False,
     "Der Veranstalter informiert den DJ vorab über Lautstärkebegrenzungen, Sperrstunden und sonstige Auflagen des "
     "Veranstaltungsorts und sorgt für deren Einhaltung bzw. erforderliche Genehmigungen. Muss die Musik wegen solcher "
     "Auflagen leiser gestellt oder früher beendet werden, mindert das die Gage nicht."),
    ("nebel", "Nebel und Rauchmelder", False,
     "Setzt der DJ Nebel- oder Hazer-Geräte ein, klärt der Veranstalter vorab mit dem Veranstaltungsort, ob das zulässig ist "
     "und ob Rauchmelder abgeschaltet werden müssen. Kosten eines durch Nebel ausgelösten Feuerwehr- oder "
     "Brandmeldeeinsatzes trägt der Veranstalter, wenn er die Klärung unterlassen hat."),
    ("outdoor", "Veranstaltungen im Freien, Wetter", False,
     "Bei Veranstaltungen im Freien stellt der Veranstalter einen gegen Regen und direkte Sonne geschützten Platz für die "
     "Technik bereit. Bei Gewitter, Starkregen oder Sturm darf der DJ die Musik unterbrechen bzw. beenden und die Technik "
     "schützen, ohne dass sich die Gage mindert."),
    ("sicherheit", "Sicherheit und Abbruch", False,
     "Der DJ darf seine Leistung unterbrechen oder beenden, wenn Personen oder seine Technik ernsthaft gefährdet sind (z. B. "
     "Bedrohung, Gewalt, erhebliche Beschädigung) und der Veranstalter trotz Aufforderung keine Abhilfe schafft. Der Anspruch "
     "auf die Gage bleibt in diesem Fall bestehen."),
    ("gewalt", "Höhere Gewalt", False,
     "Kann die Veranstaltung wegen höherer Gewalt (z. B. Unwetter, behördliche Untersagung, Epidemie) nicht stattfinden, wird "
     "keine Partei schadensersatzpflichtig. Bereits geleistete Anzahlungen werden erstattet oder – nach Absprache – auf "
     "einen Ersatztermin angerechnet."),
    ("haftung_dj", "Haftung des DJs", False,
     "Der DJ haftet für Schäden, die er oder seine Helfer vorsätzlich oder grob fahrlässig verursachen, sowie für Schäden aus "
     "der Verletzung von Leben, Körper oder Gesundheit. Im Übrigen ist die Haftung ausgeschlossen, soweit gesetzlich zulässig."),
    ("mitwirkung", "Mitwirkung des Veranstalters", False,
     "Der Veranstalter sorgt dafür, dass der DJ zur vereinbarten Aufbauzeit Zugang zum Veranstaltungsort hat, und benennt "
     "einen Ansprechpartner vor Ort. Änderungen bei Zeit, Ort oder Ablauf teilt er dem DJ rechtzeitig mit."),
    ("moderation", "Moderation und Mikrofon", False,
     "Kurze Ansagen gehören zur Leistung. Eine Moderation darüber hinaus (z. B. Spiele, Programmpunkte) erfolgt nur nach "
     "Absprache. Ein Funkmikrofon für Reden der Gäste stellt der DJ auf Wunsch bereit."),
    ("uebernachtung", "Anreise und Übernachtung", False,
     "Die Anreise bis 50 km ist in der Gage enthalten. Bei einem Spielende nach 2:00 Uhr und einer Rückfahrt von mehr als "
     "100 km stellt der Veranstalter eine Übernachtungsmöglichkeit oder übernimmt die Kosten nach Absprache."),
    ("fotos", "Fotos für Werbung", False,
     "Der DJ darf Fotos seines Aufbaus und der Veranstaltung ohne erkennbare Gäste für die eigene Werbung (Website, soziale "
     "Medien) verwenden. Den Namen des Veranstalters nennt er nur mit dessen Zustimmung."),
    ("datenschutz", "Datenschutz", False,
     "Der DJ verwendet die Daten des Veranstalters nur zur Durchführung und Abrechnung dieses Vertrags und bewahrt sie im "
     "Rahmen der gesetzlichen Aufbewahrungsfristen auf. Eine Weitergabe an Dritte erfolgt nicht, außer an einen Ersatz-DJ "
     "im Ausfall."),
]
STANDARD_IDS = {s[0] for s in STANDARD}
# Teile, die die App selbst ausfüllt – beim Hochladen eines eigenen Vertrags nicht vorausgewählt
FEST = re.compile(r"vertragspartner|vertragsparteien|\bparteien\b|leistung|gage|vergütung|honorar|zahlung|schlussbestimmung|"
                  r"unterschrift|salvatorisch", re.I)


def _main():
    import main   # zur Laufzeit (main bindet dieses Modul ein)
    return main


def _fehler(text, code=400):
    return jsonify({"error": text}), code


def _daten():
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


def _ordner(*teile):
    pfad = os.path.join(db.DATA_DIR, ORDNER, *teile)
    os.makedirs(pfad, exist_ok=True)
    return pfad


def _sicherer_pfad(unterordner, rel):
    """Datei nur innerhalb von vertraege/<unterordner> – auch nach einer manipulierten Sicherung."""
    if not rel or "/" in rel or "\\" in rel or rel in (".", ".."):
        return None
    basis = os.path.realpath(_ordner(unterordner))
    pfad = os.path.realpath(os.path.join(basis, rel))
    return pfad if os.path.dirname(pfad) == basis and os.path.isfile(pfad) else None


def _ist_datum(text):
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text)) and bool(date.fromisoformat(text))
    except (TypeError, ValueError):
        return False


def _ist_zeit(text):
    return bool(re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", text or ""))


def _text(v, laenge):
    return str(v or "").strip()[:laenge]


# ---------- Vorlage ----------

def vorlage():
    """Abschnitte der Vorlage in ihrer Reihenfolge; fehlende eingebaute Bausteine werden ergänzt (Änderungen bleiben)."""
    with db.connect() as con:
        vorhanden = {r["id"] for r in con.execute("SELECT id FROM vertrag_abschnitte")}
        start = con.execute("SELECT COALESCE(MAX(sortierung), 0) FROM vertrag_abschnitte").fetchone()[0]
        for i, (sid, titel, an, text) in enumerate(STANDARD):
            if sid not in vorhanden:
                con.execute("INSERT INTO vertrag_abschnitte (id, titel, text, an, sortierung, herkunft) VALUES (?, ?, ?, ?, ?, 'standard')",
                            (sid, titel, text, int(an), (start if vorhanden else 0) + i + 1))
        return [dict(r) | {"an": bool(r["an"])} for r in con.execute("SELECT * FROM vertrag_abschnitte ORDER BY sortierung, rowid")]


def anlagen():
    with db.connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM vertrag_anlagen ORDER BY id")]


@bp.get("/api/vertragsvorlage")
def vorlage_lesen():
    return jsonify({"abschnitte": vorlage(), "anlagen": [{"id": a["id"], "name": a["name"]} for a in anlagen()],
                    "platzhalter": PLATZHALTER, "hinweis": HINWEIS})


@bp.put("/api/vertragsvorlage/abschnitte")
def vorlage_speichern():
    """Ganze Liste in der gewünschten Reihenfolge. Neue Abschnitte ohne id werden angelegt; eigene und übernommene
    Abschnitte, die fehlen, werden gelöscht. Eingebaute Bausteine lassen sich nur ausschalten, nicht löschen."""
    liste = _daten().get("abschnitte")
    if not isinstance(liste, list) or len(liste) > 200:
        return _fehler("Ungültige Liste")
    alt = {a["id"]: a for a in vorlage()}
    neu = []
    for i, a in enumerate(liste):
        if not isinstance(a, dict):
            return _fehler("Ungültiger Abschnitt")
        titel, text = _text(a.get("titel"), 120), _text(a.get("text"), 6000)
        if not titel or not text:
            return _fehler("Jeder Abschnitt braucht eine Überschrift und einen Text.")
        sid = a.get("id")
        if sid not in alt:
            sid = None
        herkunft = alt[sid]["herkunft"] if sid else ("eigen" if not a.get("herkunft") else _text(a.get("herkunft"), 120))
        neu.append((sid or f"e{uuid.uuid4().hex[:10]}", titel, text, int(bool(a.get("an"))), i + 1, herkunft))
    behalten = {n[0] for n in neu}
    with db.connect() as con:
        for sid, a in alt.items():
            if sid not in behalten and a["herkunft"] != "standard":
                con.execute("DELETE FROM vertrag_abschnitte WHERE id = ?", (sid,))
        for sid in STANDARD_IDS - behalten:   # eingebauten Baustein „gelöscht“ → ans Ende, aus
            con.execute("UPDATE vertrag_abschnitte SET an = 0, sortierung = ? WHERE id = ?", (len(neu) + 1, sid))
        for z in neu:
            con.execute("INSERT INTO vertrag_abschnitte (id, titel, text, an, sortierung, herkunft) VALUES (?, ?, ?, ?, ?, ?)"
                        " ON CONFLICT(id) DO UPDATE SET titel = excluded.titel, text = excluded.text, an = excluded.an,"
                        " sortierung = excluded.sortierung", z)
    return jsonify({"abschnitte": vorlage()})


def zerlegen(text):
    """Text eines eigenen Vertrags → Abschnitte nach Überschriften wie „§ 3 Anfahrt“ oder „3. Anfahrt“."""
    zeilen = [z.strip() for z in text.replace("\r", "").split("\n")]
    kopf = re.compile(r"^(?:§\s*\d+[a-z]?\.?|\d{1,2}\.)\s+(.{2,80})$")
    teile, akt = [], None
    for z in zeilen:
        m = kopf.match(z)
        if m and not re.search(r"[.;,]$", m.group(1)):
            akt = {"titel": m.group(1).strip(), "zeilen": []}
            teile.append(akt)
        elif akt is not None:
            akt["zeilen"].append(z)

    def absatz(liste):
        return "\n\n".join(re.sub(r"\s+", " ", x).strip() for x in "\n".join(liste).split("\n\n") if x.strip())
    liste = [{"titel": t["titel"][:120], "text": absatz(t["zeilen"])[:6000]} for t in teile]
    liste = [t | {"fest": bool(FEST.search(t["titel"]))} for t in liste if t["text"]][:60]
    if not liste:
        ganz = absatz(zeilen)[:6000]
        liste = [{"titel": "Eigener Vertragstext", "text": ganz, "fest": False}] if ganz else []
    return liste


def _docx_text(daten):
    with zipfile.ZipFile(io.BytesIO(daten)) as zf:
        info = zf.getinfo("word/document.xml")
        if info.file_size > 20 * 1024 * 1024:
            raise ValueError("Das Word-Dokument ist zu groß.")
        xml = zf.read(info).decode("utf-8", "replace")
    absaetze = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    text = "\n".join("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in absaetze)
    for alt, neu in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")):
        text = text.replace(alt, neu)
    return text


@bp.post("/api/vertragsvorlage/lesen")
def eigenen_vertrag_lesen():
    """Hochgeladenen Vertrag (PDF, Word .docx, Text) in Abschnitte zerlegen – gespeichert wird erst beim Übernehmen."""
    f = request.files.get("datei")
    if not f:
        return _fehler("Keine Datei")
    daten = f.read(MAX_DATEI + 1)
    if len(daten) > MAX_DATEI:
        return _fehler("Die Datei ist zu groß (höchstens 20 MB).", 413)
    name = os.path.basename(f.filename or "Vertrag")[:120]
    endung = os.path.splitext(name)[1].lower()
    try:
        if endung == ".pdf" or daten[:5] == b"%PDF-":
            import pdflesen   # fremde PDFs nur im begrenzten Kindprozess lesen
            text = pdflesen.text(daten)[0]
        elif endung == ".docx":
            text = _docx_text(daten)
        elif endung == ".txt":
            text = daten.decode("utf-8") if not daten.startswith(b"\xff\xfe") else daten.decode("utf-16")
        else:
            return _fehler("Bitte einen Vertrag als PDF, Word (.docx) oder Text (.txt) hochladen. Ältere .doc-Dateien vorher in Word als .docx speichern.")
    except UnicodeDecodeError:
        text = daten.decode("latin-1")
    except (KeyError, zipfile.BadZipFile):
        return _fehler("Das Word-Dokument lässt sich nicht lesen.")
    except ValueError as e:
        return _fehler(str(e))
    except Exception as e:     # pdflesen: Abgebrochen / Kaputt
        return _fehler(f"Die Datei lässt sich nicht lesen ({e}).")
    abschnitte = zerlegen(text)
    if not abschnitte:
        return _fehler("In der Datei steht kein lesbarer Text (eingescannte Verträge werden nicht unterstützt).")
    return jsonify({"name": name, "abschnitte": abschnitte})


@bp.post("/api/vertragsvorlage/anlagen")
def anlage_hochladen():
    """PDF, das unverändert an jeden Vertrag angehängt wird (z. B. AGB)."""
    f = request.files.get("datei")
    if not f:
        return _fehler("Keine Datei")
    daten = f.read(MAX_DATEI + 1)
    if len(daten) > MAX_DATEI:
        return _fehler("Die Datei ist zu groß (höchstens 20 MB).", 413)
    if daten[:5] != b"%PDF-":
        return _fehler("Anlagen bitte als PDF – z. B. in Word über „Speichern unter → PDF“.")
    name = re.sub(r"[^\w.\- ()äöüÄÖÜß]", "_", os.path.basename(f.filename or "Anlage.pdf"))[:120] or "Anlage.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    datei = f"{uuid.uuid4().hex}.pdf"
    with open(os.path.join(_ordner("anlagen"), datei), "wb") as out:
        out.write(daten)
    with db.connect() as con:
        con.execute("INSERT INTO vertrag_anlagen (name, datei) VALUES (?, ?)", (name, datei))
    return jsonify({"anlagen": [{"id": a["id"], "name": a["name"]} for a in anlagen()]}), 201


@bp.delete("/api/vertragsvorlage/anlagen/<int:aid>")
def anlage_loeschen(aid):
    with db.connect() as con:
        r = con.execute("SELECT datei FROM vertrag_anlagen WHERE id = ?", (aid,)).fetchone() or abort(404)
        con.execute("DELETE FROM vertrag_anlagen WHERE id = ?", (aid,))
    pfad = _sicherer_pfad("anlagen", r["datei"])
    if pfad:
        os.remove(pfad)
    return "", 204


@bp.get("/api/vertragsvorlage/anlagen/<int:aid>")
def anlage_ansehen(aid):
    a = next((x for x in anlagen() if x["id"] == aid), None) or abort(404)
    pfad = _sicherer_pfad("anlagen", a["datei"]) or abort(404)
    return send_file(pfad, mimetype="application/pdf", download_name=a["name"])


def anlagen_dateien():
    """[(Name, Bytes)] für den Versand."""
    aus = []
    for a in anlagen():
        pfad = _sicherer_pfad("anlagen", a["datei"])
        if pfad:
            with open(pfad, "rb") as f:
                aus.append((a["name"], f.read()))
    return aus


# ---------- Verträge ----------

def _aus_zeile(r):
    d = dict(r)
    d["kunde"] = json.loads(d.pop("kunde_json") or "{}")
    d["ort"] = json.loads(d.pop("ort_json") or "null")
    d["felder"] = json.loads(d.pop("felder_json") or "{}")
    d["abschnitte"] = json.loads(d.pop("abschnitte_json") or "[]")
    d["unterschrieben"] = json.loads(d.pop("unterschrieben_json") or "null")
    d.pop("inhalt_json", None)
    d["kleinunternehmer"] = None if d["kleinunternehmer"] is None else bool(d["kleinunternehmer"])
    d["name"] = f"Vertrag zu Angebot {d['angebot_nummer']}" if d["angebot_nummer"] else f"Vertrag {d['nummer']}"
    d["hat_unterschrift_datei"] = bool(d.pop("unterschrift_datei"))
    return d


def lesen(vid):
    with db.connect() as con:
        r = con.execute("SELECT * FROM vertraege WHERE id = ?", (vid,)).fetchone()
    return _aus_zeile(r) if r else None


def liste():
    with db.connect() as con:
        return [_aus_zeile(r) for r in con.execute("SELECT * FROM vertraege ORDER BY CASE WHEN datum = '' THEN 1 ELSE 0 END, datum, id")]


def _naechste_nummer(con):
    hoechste = max((int(m.group(1)) for (n,) in con.execute("SELECT nummer FROM vertraege")
                    if (m := re.fullmatch(r"V(\d+)", n))), default=0)
    return f"V{hoechste + 1:03d}"


def _kurz(t):
    return re.sub(r"^0(\d)", r"\1", t or "")


def _aus_angebot(a):
    """Kunde, Termin, Ort und Gage aus einem Angebot."""
    text = (a["positionen"][0]["beschreibung"] if a["positionen"] else "") or ""
    zeit = re.search(r"(\d{1,2}:\d{2}) Uhr bis (\d{1,2}:\d{2}) Uhr", text)
    anlass = re.sub(r"\s*–\s*\d{1,2}:\d{2} Uhr bis.*$", "", re.sub(r"^DJ – (Tätigkeit )?", "", text)).strip() or "Veranstaltung"
    datum = max((p.get("lieferdatum") or "" for p in a["positionen"]), default="")
    umfasst = [re.sub(r"\s*–\s*\d{1,2}:\d{2} Uhr bis.*$", "", re.sub(r"^DJ – (Tätigkeit )?", "", p["beschreibung"])).strip()
               for p in a["positionen"] if (p.get("beschreibung") or "").strip()]
    return {"kunde": a["kunde"], "kunde_id": a.get("kunde_id"), "ort": a.get("veranstaltungsort"), "anlass": anlass,
            "datum": datum if _ist_datum(datum) else "",
            "von": zeit.group(1).zfill(5) if zeit else "", "bis": zeit.group(2).zfill(5) if zeit else "",
            "gage": a["gesamt"], "kleinunternehmer": a.get("kleinunternehmer"),
            "umfasst": umfasst if len(umfasst) > 1 else []}


@bp.get("/api/vertraege")
def vertraege_liste():
    return jsonify(liste())


@bp.post("/api/vertraege")
def vertrag_anlegen():
    """{"angebot_id": …} – aus einem Angebot; ohne → Vertrag ohne Angebot (Angaben im Vertrag eintragen)."""
    d = _daten()
    a = _main().absender()
    werte = {"kunde": {"name": "", "strasse": "", "plz": "", "ort": ""}, "kunde_id": None, "ort": None, "anlass": "", "datum": "",
             "von": "", "bis": "", "gage": 0, "kleinunternehmer": bool(a.get("kleinunternehmer")), "umfasst": []}
    angebot = None
    if d.get("angebot_id") is not None:
        angebot = db.get_offer(d["angebot_id"]) if isinstance(d["angebot_id"], int) else None
        if not angebot:
            return _fehler("Das Angebot gibt es nicht (mehr).", 404)
        werte |= _aus_angebot(angebot)
        if werte["kleinunternehmer"] is None:
            werte["kleinunternehmer"] = bool(a.get("kleinunternehmer"))
    felder = {"aufbau": "", "kontakt": "", "zahlung": "rechnung", "anzahlung": 30, "gema": "veranstalter", "verpflegung": "",
              "umfasst": werte.pop("umfasst")}
    an = [x["id"] for x in vorlage() if x["an"]]
    with db.connect() as con:
        nummer = _naechste_nummer(con)
        vid = con.execute(
            "INSERT INTO vertraege (nummer, angebot_id, angebot_nummer, kunde_id, kunde_json, ort_json, anlass, datum, von, bis, gage,"
            " kleinunternehmer, felder_json, abschnitte_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (nummer, angebot["id"] if angebot else None, angebot["nummer"] if angebot else None, werte["kunde_id"],
             json.dumps(werte["kunde"]), json.dumps(werte["ort"]) if werte["ort"] else None, werte["anlass"], werte["datum"],
             werte["von"], werte["bis"], werte["gage"], int(bool(werte["kleinunternehmer"])), json.dumps(felder),
             json.dumps(an))).lastrowid
    v = lesen(vid)
    return jsonify({"vertrag": v, "inhalt": inhalt(v)}), 201


@bp.get("/api/vertraege/<int:vid>")
def vertrag_holen(vid):
    v = lesen(vid) or abort(404)
    return jsonify({"vertrag": v, "inhalt": inhalt(v)})


@bp.put("/api/vertraege/<int:vid>")
def vertrag_aendern(vid):
    """Nur im Entwurf. Felder, die fehlen, bleiben."""
    v = lesen(vid) or abort(404)
    if v["status"] != "entwurf":
        return _fehler("Der Vertrag ist schon verschickt – zum Ändern erst „Wieder bearbeiten“ wählen.", 409)
    d = _daten()
    fehler = []
    if "kunde" in d:
        k = d["kunde"] if isinstance(d["kunde"], dict) else {}
        v["kunde"] = {x: _text(k.get(x), 200) for x in ("name", "zusatz", "strasse", "plz", "ort")}
        v["kunde_id"] = None if v["kunde"]["name"] != (lesen(vid)["kunde"].get("name") or "") else v["kunde_id"]
    for x in ("anlass",):
        if x in d:
            v[x] = _text(d[x], 120)
    if "datum" in d:
        if d["datum"] and not _ist_datum(d["datum"]):
            fehler.append("Ungültiges Datum")
        else:
            v["datum"] = d["datum"] or ""
    for x in ("von", "bis"):
        if x in d:
            if d[x] and not _ist_zeit(d[x]):
                fehler.append(f"Ungültige Uhrzeit bei „{x}“")
            else:
                v[x] = d[x] or ""
    if "gage" in d:
        try:
            v["gage"] = round(float(d["gage"] or 0), 2)
            if not 0 <= v["gage"] <= 1_000_000:
                raise ValueError
        except (TypeError, ValueError):
            fehler.append("Ungültige Gage")
    if isinstance(d.get("felder"), dict):
        f = d["felder"]
        if "aufbau" in f:
            if f["aufbau"] and not _ist_zeit(f["aufbau"]):
                fehler.append("Ungültige Aufbauzeit")
            else:
                v["felder"]["aufbau"] = f["aufbau"] or ""
        for x, n in (("kontakt", 200), ("verpflegung", 200)):
            if x in f:
                v["felder"][x] = _text(f[x], n)
        if "zahlung" in f:
            if f["zahlung"] not in ZAHLUNG:
                fehler.append("Ungültige Zahlungsart")
            else:
                v["felder"]["zahlung"] = f["zahlung"]
        if "gema" in f:
            v["felder"]["gema"] = "dj" if f["gema"] == "dj" else "veranstalter"
        if "anzahlung" in f:
            try:
                v["felder"]["anzahlung"] = max(0, min(100, round(float(f["anzahlung"] or 0), 1)))
            except (TypeError, ValueError):
                fehler.append("Ungültige Anzahlung")
    if "abschnitte" in d:
        ids = {x["id"] for x in vorlage()}
        if not isinstance(d["abschnitte"], list):
            fehler.append("Ungültige Abschnitte")
        else:
            v["abschnitte"] = [x for x in d["abschnitte"] if x in ids]
    if fehler:
        return _fehler("; ".join(fehler))
    with db.connect() as con:
        con.execute("UPDATE vertraege SET kunde_id = ?, kunde_json = ?, anlass = ?, datum = ?, von = ?, bis = ?, gage = ?,"
                    " felder_json = ?, abschnitte_json = ? WHERE id = ? AND status = 'entwurf'",
                    (v["kunde_id"], json.dumps(v["kunde"]), v["anlass"], v["datum"], v["von"], v["bis"], v["gage"],
                     json.dumps(v["felder"]), json.dumps(v["abschnitte"]), vid))
    v = lesen(vid)
    return jsonify({"vertrag": v, "inhalt": inhalt(v)})


def fehlende_angaben(v):
    return [t for t, ok in (("Veranstalter", v["kunde"].get("name")), ("Anschrift", v["kunde"].get("strasse") and v["kunde"].get("ort")),
                            ("Datum", v["datum"]), ("Gage", v["gage"] > 0)) if not ok]


def festhalten(vid, status, extra_sql="", extra=()):
    """Status setzen; beim Verlassen des Entwurfs wird der Vertragstext festgehalten."""
    v = lesen(vid)
    text = json.dumps(inhalt(v)) if v["status"] == "entwurf" and status != "entwurf" else None
    with db.connect() as con:
        con.execute(f"UPDATE vertraege SET status = ?, inhalt_json = CASE WHEN ? = 'entwurf' THEN NULL ELSE COALESCE(?, inhalt_json) END"
                    f"{extra_sql} WHERE id = ?", (status, status, text, *extra, vid))


@bp.post("/api/vertraege/<int:vid>/status")
def vertrag_status(vid):
    """„Als verschickt vermerken“ (z. B. per WhatsApp verschickt) bzw. „Wieder bearbeiten“."""
    v = lesen(vid) or abort(404)
    neu = _daten().get("status")
    if neu == "verschickt" and v["status"] == "entwurf":
        if fehlende_angaben(v):
            return _fehler(f"Bitte noch eintragen: {', '.join(fehlende_angaben(v))}")
        festhalten(vid, "verschickt", ", verschickt_am = ?", (date.today().isoformat(),))
    elif neu == "entwurf" and v["status"] == "verschickt":
        festhalten(vid, "entwurf", ", verschickt_am = NULL")
    else:
        return _fehler("Dieser Wechsel ist nicht möglich.", 409)
    v = lesen(vid)
    return jsonify({"vertrag": v, "inhalt": inhalt(v)})


@bp.post("/api/vertraege/<int:vid>/unterschrieben")
def vertrag_unterschrieben(vid):
    """Formular: weg (datei | mail | vorort), am, notiz, datei (bei „datei“), angebot_annehmen."""
    v = lesen(vid) or abort(404)
    if v["status"] == "unterschrieben":
        return _fehler("Der Vertrag ist schon als unterschrieben vermerkt.", 409)
    if fehlende_angaben(v):
        return _fehler(f"Bitte noch eintragen: {', '.join(fehlende_angaben(v))}")
    weg, am, notiz = request.form.get("weg"), request.form.get("am") or date.today().isoformat(), _text(request.form.get("notiz"), 500)
    if weg not in WEGE:
        return _fehler("Bitte angeben, wie unterschrieben wurde.")
    if not _ist_datum(am):
        return _fehler("Ungültiges Datum")
    datei, dateiname = None, ""
    if weg == "datei":
        f = request.files.get("datei")
        if not f:
            return _fehler("Bitte die unterschriebene Datei auswählen.")
        daten = f.read(MAX_DATEI + 1)
        if len(daten) > MAX_DATEI:
            return _fehler("Die Datei ist zu groß (höchstens 20 MB).", 413)
        endung = os.path.splitext(f.filename or "")[1].lower()
        if endung not in UNTERSCHRIFT_ENDUNGEN:
            return _fehler("Bitte als PDF oder Foto (JPG, PNG, HEIC).")
        dateiname = os.path.basename(f.filename)[:120]
        datei = f"{vid}_{uuid.uuid4().hex[:12]}{endung}"
        with open(os.path.join(_ordner("unterschrieben"), datei), "wb") as out:
            out.write(daten)
    info = {"weg": weg, "am": am, "notiz": notiz, "dateiname": dateiname}
    festhalten(vid, "unterschrieben", ", unterschrieben_json = ?, unterschrift_datei = ?", (json.dumps(info), datei))
    if v["angebot_id"] and request.form.get("angebot_annehmen") == "1":
        a = db.get_offer(v["angebot_id"])
        if a and a["status"] != "angenommen":
            db.set_offer_status(a["id"], "angenommen")
    v = lesen(vid)
    return jsonify({"vertrag": v, "inhalt": inhalt(v)})


@bp.get("/api/vertraege/<int:vid>/unterschrift")
def unterschrift_ansehen(vid):
    with db.connect() as con:
        r = con.execute("SELECT unterschrift_datei, unterschrieben_json FROM vertraege WHERE id = ?", (vid,)).fetchone() or abort(404)
    pfad = _sicherer_pfad("unterschrieben", r["unterschrift_datei"]) or abort(404)
    endung = os.path.splitext(pfad)[1].lower()
    name = (json.loads(r["unterschrieben_json"] or "{}").get("dateiname") or f"Vertrag_unterschrieben{endung}")
    # immer als Download – eine hochgeladene Datei wird nie als Seite der App angezeigt
    return send_file(pfad, mimetype=UNTERSCHRIFT_ENDUNGEN.get(endung, "application/octet-stream"), as_attachment=True, download_name=name)


@bp.delete("/api/vertraege/<int:vid>")
def vertrag_loeschen(vid):
    with db.connect() as con:
        r = con.execute("SELECT status, unterschrift_datei FROM vertraege WHERE id = ?", (vid,)).fetchone() or abort(404)
        if r["status"] == "unterschrieben":
            return _fehler("Ein unterschriebener Vertrag wird aufbewahrt und lässt sich nicht löschen.", 409)
        con.execute("DELETE FROM vertraege WHERE id = ?", (vid,))
    return "", 204


@bp.get("/api/vertraege/<int:vid>/pdf")
def vertrag_pdf(vid):
    v = lesen(vid) or abort(404)
    from pdf import build_vertrag_pdf
    m = _main()
    return send_file(io.BytesIO(build_vertrag_pdf(inhalt(v), m.absender())), mimetype="application/pdf",
                     download_name=dateiname(v))


def dateiname(v):
    teil = f"Angebot_{v['angebot_nummer']}" if v["angebot_nummer"] else v["nummer"]
    datum = date.fromisoformat(v["datum"]).strftime("%d%m%y") if v["datum"] else ""
    return re.sub(r"[^\w.-]", "_", f"Vertrag_{teil}{'_' + datum if datum else ''}") + ".pdf"


def pdf_bytes(v):
    from pdf import build_vertrag_pdf
    return build_vertrag_pdf(inhalt(v), _main().absender())


# ---------- Vertragstext ----------

def _euro(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _de(iso):
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return ""


def _de_lang(iso):
    tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    monate = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
    try:
        d = date.fromisoformat(iso)
        return f"{tage[d.weekday()]}, {d.day}. {monate[d.month - 1]} {d.year}"
    except (TypeError, ValueError):
        return "–"


def inhalt(v):
    """Vertragstext als Struktur (für Vorschau und PDF). Ab „verschickt“ der festgehaltene Stand."""
    if v["status"] != "entwurf":
        with db.connect() as con:
            r = con.execute("SELECT inhalt_json FROM vertraege WHERE id = ?", (v["id"],)).fetchone()
        if r and r["inhalt_json"]:
            return json.loads(r["inhalt_json"])
    a = _main().absender()
    k, f = v["kunde"], v["felder"]
    ort = v["ort"] or k
    ort_text = ", ".join(x for x in ((ort.get("name") if ort.get("name") != k.get("name") else ""), ort.get("strasse"),
                                     " ".join(y for y in (ort.get("plz"), ort.get("ort")) if y)) if x)
    spielzeit = f"{_kurz(v['von'])} bis {_kurz(v['bis'])} Uhr" if v["von"] and v["bis"] else "nach Absprache"
    gage = v["gage"] or 0
    anz = 0 if f.get("zahlung") == "ganz" else round(gage * (f.get("anzahlung") or 0) / 100, 2)
    ku = v["kleinunternehmer"] if v["kleinunternehmer"] is not None else bool(a.get("kleinunternehmer"))
    zahlung = (f"Die Gage beträgt **{_euro(gage)}**{' (gemäß § 19 UStG ohne Umsatzsteuer)' if ku else ' inkl. Umsatzsteuer'}"
               + (f"; sie umfasst {', '.join(f.get('umfasst'))}" if f.get("umfasst") else "") + ". ")
    if anz:
        zahlung += (f"Eine Anzahlung von **{_euro(anz)}** ist innerhalb von 14 Tagen nach Unterschrift fällig; der Termin ist mit "
                    "Eingang der Anzahlung fest reserviert. ")
    if f.get("zahlung") == "bar":
        zahlung += f"Der Restbetrag von **{_euro(gage - anz)}** wird am Veranstaltungstag bar bezahlt."
    else:
        zahlung += (f"Der {'Restbetrag von **' + _euro(gage - anz) + '**' if anz else 'Betrag'} wird nach der Veranstaltung in "
                    "Rechnung gestellt und ist innerhalb von 8 Tagen zu zahlen.")
    werte = {"veranstalter": k.get("name") or "der Veranstalter", "dj": a.get("name") or "der DJ", "datum": _de(v["datum"]) or "–",
             "anlass": v["anlass"] or "Veranstaltung", "ort": ort_text or "–", "spielzeit": spielzeit, "gage": _euro(gage),
             "verpflegung_zusatz": f" ({f['verpflegung']})" if f.get("verpflegung") else "",
             "gema_text": ("Die Anmeldung der Veranstaltung bei der GEMA und die Gebühren übernimmt der DJ; sie sind in der Gage enthalten."
                           if f.get("gema") == "dj" else
                           "Die Anmeldung der Veranstaltung bei der GEMA und die Zahlung der Gebühren übernimmt der Veranstalter.")}

    def fuellen(text):
        return re.sub(r"\{(\w+)\}", lambda m: werte.get(m.group(1), m.group(0)), text)

    leistung = [["Anlass:", v["anlass"] or "–"], ["Datum:", _de_lang(v["datum"])], ["Spielzeit:", spielzeit]]
    if f.get("aufbau"):
        leistung.append(["Aufbau ab:", f"{_kurz(f['aufbau'])} Uhr"])
    leistung.append(["Ort:", ort_text or "–"])
    if f.get("kontakt"):
        leistung.append(["Ansprechpartner:", f["kontakt"]])
    abschnitte = [
        {"titel": "Vertragspartner", "tabelle": [
            ["Veranstalter:", "\n".join(x for x in (k.get("name"), k.get("zusatz"), k.get("strasse"),
                                                     " ".join(y for y in (k.get("plz"), k.get("ort")) if y)) if x) or "–"],
            ["DJ:", "\n".join(x for x in (a.get("name"), a.get("strasse"), a.get("plz_ort")) if x)]]},
        {"titel": "Leistung", "text": "Der DJ übernimmt die musikalische Gestaltung der folgenden Veranstaltung mit eigener Musik-, "
                                      "Licht- und Tontechnik:", "tabelle": leistung},
        {"titel": "Gage und Zahlung", "text": zahlung, "fett": True},
    ]
    eingeschaltet = set(v["abschnitte"])
    for x in vorlage():
        if x["id"] in eingeschaltet:
            abschnitte.append({"titel": x["titel"], "text": fuellen(x["text"])})
    abschnitte.append({"titel": "Schlussbestimmungen", "text": "Änderungen und Ergänzungen dieses Vertrags bedürfen der Textform "
                       "(z. B. E-Mail). Sollte eine Bestimmung unwirksam sein, bleibt der Vertrag im Übrigen wirksam."})
    for i, x in enumerate(abschnitte, 1):
        x["titel"] = f"§ {i} {x['titel']}"
    namen = [x["name"] for x in anlagen()]
    return {
        "titel": "DJ-Vertrag",
        "kopf_links": " · ".join(x for x in (a.get("name"), a.get("strasse"), a.get("plz_ort")) if x),
        "kopf_rechts": v["name"],
        "abschnitte": abschnitte,
        "anlagen": namen,
        "unterschrift_links": "Ort, Datum, Unterschrift Veranstalter",
        "unterschrift_rechts": f"{a.get('ort_fuer_datum') or ''}, {date.today():%d.%m.%Y} · Unterschrift DJ".lstrip(", "),
        "fuss": "Bitte unterschrieben zurücksenden – als Scan, Foto oder per Mail-Bestätigung.",
        "stand": datetime.now().isoformat(timespec="seconds"),
    }

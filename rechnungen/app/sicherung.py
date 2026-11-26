"""Sicherungs-Passwort und verschlüsselte Sicherungen (seit 1.15), Tageskopie in einen Cloud-Ordner (Desktop).

- Passwort festlegen/ändern: Schlüsselpaar in den Einstellungen (_sicherung_pub offen, _sicherung_priv verschlossen).
- Herunterladen mit Passwort: POST /api/sicherung/vorbereiten prüft das Passwort und legt die verschlüsselte Datei
  bereit; GET /api/sicherung/datei/<id> holt sie einmal ab (so steht das Passwort nie in einer Adresse – die
  Desktop-Version lädt Dateien für „Speichern unter“ selbst über ihre Adresse).
- Tageskopie: einmal am Tag die komplette Sicherung verschlüsselt in einen Ordner (z. B. Nextcloud, iCloud Drive, NAS).
"""
import glob
import os
import re
import secrets
import tempfile
import threading
import time
from datetime import date, datetime

from flask import Blueprint, Response, abort, jsonify, request

import db
import verschluesselung as vs

bp = Blueprint("sicherung", __name__)
BEREIT_MINUTEN = 10
KOPIEN_BEHALTEN = 7
KOPIE_MUSTER = re.compile(r"DJ-Office-Studio-Sicherung_\d{4}-\d{2}-\d{2}\.djos")
_bereit = {}                       # id → (pfad, name, zeitpunkt)
_sperre = threading.Lock()


def _main():
    import main
    return main


def _fehler(text, code=400, **extra):
    return jsonify({"error": text, **extra}), code


def _daten():
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


def schluessel():
    """(öffentlich, verschlossen) oder (None, None), wenn kein Sicherungs-Passwort festgelegt ist."""
    s = db.get_settings()
    return s.get("_sicherung_pub"), s.get("_sicherung_priv")


def status():
    s = db.get_settings()
    return {"gesetzt": bool(s.get("_sicherung_pub")), "seit": s.get("_sicherung_seit"), "desktop": _main().DESKTOP,
            "kopie_ordner": s.get("sicherung_kopie_ordner") or "", "kopie_am": s.get("_kopie_am"),
            "kopie_fehler": s.get("_kopie_fehler"), "min_laenge": vs.MIN_LAENGE}


@bp.get("/api/sicherung")
def status_lesen():
    return jsonify(status())


@bp.post("/api/sicherung/passwort")
def passwort_setzen():
    d = _daten()
    neu, alt = str(d.get("neu") or ""), str(d.get("alt") or "")
    if len(neu) < vs.MIN_LAENGE:
        return _fehler(f"Das Passwort braucht mindestens {vs.MIN_LAENGE} Zeichen.")
    if len(neu) > 200:
        return _fehler("Das Passwort ist zu lang.")
    pub, priv = schluessel()
    if pub:
        try:
            priv = vs.passwort_aendern(priv, alt, neu)
        except vs.FalschesPasswort:
            return _fehler("Das bisherige Passwort stimmt nicht.", passwort=True)
        db.save_settings({"_sicherung_priv": priv, "_sicherung_seit": date.today().isoformat()})
    else:
        pub, priv = vs.schluessel_erzeugen(neu)
        db.save_settings({"_sicherung_pub": pub, "_sicherung_priv": priv, "_sicherung_seit": date.today().isoformat()})
    return jsonify(status())


def _aufraeumen():
    grenze = time.time() - BEREIT_MINUTEN * 60
    with _sperre:
        for k, (pfad, _, zeit) in list(_bereit.items()):
            if zeit < grenze:
                _bereit.pop(k, None)
                _entfernen(pfad)


def _entfernen(pfad):
    try:
        os.remove(pfad)
    except OSError:
        pass


def verschluesselt_schreiben(ziel_pfad):
    """Komplette Sicherung (ZIP) verschlüsselt nach ziel_pfad. Rückgabe: Anzahl der Belege."""
    pub, priv = schluessel()
    if not pub:
        raise RuntimeError("Kein Sicherungs-Passwort festgelegt")
    with tempfile.TemporaryFile() as zip_tmp:
        anzahl = _main().sicherung_schreiben(zip_tmp)
        zip_tmp.seek(0)
        with open(ziel_pfad, "wb") as ziel:
            vs.verschluesseln(zip_tmp, ziel, pub, priv)
    return anzahl


@bp.post("/api/sicherung/vorbereiten")
def vorbereiten():
    """Passwort prüfen und die verschlüsselte Sicherung zum Abholen bereitlegen."""
    pub, priv = schluessel()
    if not pub:
        return _fehler("Es ist noch kein Sicherungs-Passwort festgelegt.")
    try:
        vs.privat_oeffnen(priv, str(_daten().get("passwort") or ""))
    except vs.FalschesPasswort:
        return _fehler("Das Passwort stimmt nicht.", passwort=True)
    _aufraeumen()
    ordner = os.path.join(db.DATA_DIR, "sicherungen", "bereit")
    os.makedirs(ordner, exist_ok=True)
    kennung = secrets.token_urlsafe(24)
    pfad = os.path.join(ordner, kennung)
    try:
        verschluesselt_schreiben(pfad)
    except BaseException:
        _entfernen(pfad)
        raise
    name = f"DJ-Office-Studio-Sicherung_{date.today():%Y-%m-%d}{vs.ENDUNG}"
    with _sperre:
        _bereit[kennung] = (pfad, name, time.time())
    return jsonify({"url": f"api/sicherung/datei/{kennung}", "name": name})


@bp.get("/api/sicherung/datei/<kennung>")
def abholen(kennung):
    _aufraeumen()
    with _sperre:
        eintrag = _bereit.pop(kennung, None)
    if not eintrag:
        abort(404)
    pfad, name, _ = eintrag
    db.save_settings({"_letzte_sicherung": datetime.now().isoformat(timespec="seconds")})   # für die Erinnerung
    groesse = os.path.getsize(pfad)

    def stuecke():   # stückweise ausliefern und danach löschen – auch bei abgebrochenem Download
        try:
            with open(pfad, "rb") as f:
                while teil := f.read(1024 * 1024):
                    yield teil
        finally:
            _entfernen(pfad)
    return Response(stuecke(), mimetype="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Content-Length": str(groesse)})


def entschluesseln_falls_noetig(inhalt, passwort):
    """Hochgeladene Sicherung: verschlüsselt → entschlüsselte Bytes; sonst unverändert. Wirft FalschesPasswort/KeineSicherung."""
    if not vs.ist_verschluesselt(inhalt):
        return inhalt
    import io
    out = io.BytesIO()
    vs.entschluesseln(io.BytesIO(inhalt), out, passwort)
    return out.getvalue()


# ---------- Tageskopie in einen Ordner (Cloud, NAS) ----------

def tageskopie(heute=None, erzwingen=False):
    """Einmal am Tag die komplette Sicherung verschlüsselt in den eingestellten Ordner. Rückgabe: Dateiname oder None."""
    s = db.get_settings()
    ordner = (s.get("sicherung_kopie_ordner") or "").strip()
    heute = heute or date.today()
    if not ordner:
        return None
    if not s.get("_sicherung_pub"):
        db.save_settings({"_kopie_fehler": "Für die Kopie in den Ordner bitte zuerst ein Sicherungs-Passwort festlegen."})
        return None
    name = f"DJ-Office-Studio-Sicherung_{heute:%Y-%m-%d}{vs.ENDUNG}"
    ziel = os.path.join(ordner, name)
    if os.path.exists(ziel) and not erzwingen:
        return name
    try:
        if not os.path.isdir(ordner):
            raise OSError(f"Der Ordner „{ordner}“ ist nicht erreichbar.")
        tmp = ziel + ".teil"
        verschluesselt_schreiben(tmp)
        os.replace(tmp, ziel)
        alte = sorted(n for n in os.listdir(ordner) if KOPIE_MUSTER.fullmatch(n))[:-KOPIEN_BEHALTEN]
        for n in alte:
            _entfernen(os.path.join(ordner, n))
        db.save_settings({"_kopie_am": datetime.now().isoformat(timespec="seconds"), "_kopie_fehler": None})
        return name
    except OSError as e:
        for rest in glob.glob(glob.escape(ziel) + ".teil"):
            _entfernen(rest)
        db.save_settings({"_kopie_fehler": e.strerror or str(e)})
        return None


@bp.post("/api/sicherung/kopie")
def kopie_jetzt():
    if not (db.get_settings().get("sicherung_kopie_ordner") or "").strip():
        return _fehler("Bitte zuerst einen Ordner eintragen und speichern.")
    name = tageskopie(erzwingen=True)
    st = status()
    if not name:
        return _fehler(st["kopie_fehler"] or "Die Kopie hat nicht geklappt.")
    return jsonify(st | {"datei": name})


def tageskopie_im_hintergrund():
    """Desktop-Start: Tageskopie, ohne den Start aufzuhalten."""
    threading.Thread(target=lambda: _sicher(tageskopie), daemon=True).start()


def _sicher(f):
    try:
        f()
    except Exception as e:   # noqa: BLE001 – die Kopie darf die App nie stören
        print(f"Tageskopie fehlgeschlagen: {e}")


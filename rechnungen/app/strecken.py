"""Entfernungen über OpenStreetMap: Adresse → Koordinaten (Nominatim), Koordinaten → Straßen-km (OSRM).

Wird nur benutzt, wenn unter ⚙ Einstellungen „Strecke automatisch berechnen“ eingeschaltet ist. Übertragen werden
ausschließlich Adressen (keine Namen, keine Beträge). Ergebnisse werden in der Datenbank zwischengespeichert, damit
dieselbe Adresse nicht erneut abgefragt wird; die Nutzungsregeln von Nominatim (höchstens 1 Anfrage pro Sekunde,
Programm gibt sich zu erkennen) werden eingehalten.
"""
import json
import threading
import time
import urllib.parse
import urllib.request

import db

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OSRM = "https://router.project-osrm.org/route/v1/driving"
KENNUNG = "DJ-Office-Studio (+https://github.com/DJMalte96/dj-office-studio)"   # Programmname, keine persönlichen Daten
_sperre = threading.Lock()
_letzte_anfrage = [0.0]


class StreckenFehler(Exception):
    pass


def adresse_text(d):
    """{strasse, plz, ort} bzw. {strasse, plz_ort} → „Straße, PLZ Ort“."""
    if not d:
        return ""
    plz_ort = d.get("plz_ort") or " ".join(x for x in ((d.get("plz") or "").strip(), (d.get("ort") or "").strip()) if x)
    return ", ".join(x for x in ((d.get("strasse") or "").strip(), plz_ort.strip()) if x)


def _laden(url, ssl_kontext=None):
    with _sperre:   # Nominatim: höchstens eine Anfrage pro Sekunde
        warten = 1.1 - (time.time() - _letzte_anfrage[0])
        if warten > 0:
            time.sleep(warten)
        _letzte_anfrage[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": KENNUNG, "Accept-Language": "de"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl_kontext) as r:
            return json.loads(r.read())
    except Exception as e:
        raise StreckenFehler(f"Kartendienst nicht erreichbar ({type(e).__name__})") from e


def _cache(schluessel):
    with db.connect() as con:
        r = con.execute("SELECT wert FROM strecken_cache WHERE schluessel = ?", (schluessel,)).fetchone()
        return json.loads(r["wert"]) if r else None


def _merken(schluessel, wert):
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO strecken_cache (schluessel, wert) VALUES (?, ?)", (schluessel, json.dumps(wert)))


def koordinaten(adresse, ssl_kontext=None):
    schluessel = "geo:" + " ".join(adresse.lower().split())
    treffer = _cache(schluessel)
    if treffer:
        return treffer
    q = urllib.parse.urlencode({"q": adresse, "format": "json", "limit": 1, "countrycodes": "de,at,ch,nl,be,lu,dk,pl,cz,fr"})
    daten = _laden(f"{NOMINATIM}?{q}", ssl_kontext)
    if not daten:
        raise StreckenFehler(f"Adresse nicht gefunden: {adresse}")
    punkt = [float(daten[0]["lat"]), float(daten[0]["lon"])]
    _merken(schluessel, punkt)
    return punkt


def strecke_km(start, ziel, ssl_kontext=None):
    """Straßen-Entfernung (einfache Strecke) in km, auf 1 Nachkommastelle."""
    if not start or not ziel:
        raise StreckenFehler("Start- oder Zieladresse fehlt")
    schluessel = "km:" + " ".join(start.lower().split()) + "→" + " ".join(ziel.lower().split())
    treffer = _cache(schluessel)
    if treffer is not None:
        return treffer
    (lat1, lon1), (lat2, lon2) = koordinaten(start, ssl_kontext), koordinaten(ziel, ssl_kontext)
    daten = _laden(f"{OSRM}/{lon1},{lat1};{lon2},{lat2}?overview=false", ssl_kontext)
    if daten.get("code") != "Ok" or not daten.get("routes"):
        raise StreckenFehler("Keine Route gefunden")
    km = round(daten["routes"][0]["distance"] / 1000, 1)
    _merken(schluessel, km)
    return km

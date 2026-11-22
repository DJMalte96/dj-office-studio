"""Zugriff auf Paperless-ngx über dessen REST-Schnittstelle (nur lesend): Tags, Dokumente, Korrespondenten, Download.

Anmeldung mit dem API-Token aus Paperless (Profil → API-Token). Die App holt Dokumente mit einem bestimmten Tag
als Ausgaben-Belege ab; an Paperless selbst wird nichts geändert.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

# Übliche Adressen des Paperless-ngx-Add-ons in Home Assistant (interner Hostname = Repository-Kennung + Slug)
# sowie im Heimnetz. Werden bei „Adresse suchen“ der Reihe nach ausprobiert.
KANDIDATEN = (
    "http://ca5234a0-paperless-ngx:8000",     # Add-on aus dem Repository von BenoitAnastay
    "http://db21ed7f-paperless-ngx:8000",     # Add-on aus dem Repository von alexbelgium
    "http://homeassistant.local:8000",
    "http://homeassistant:8000",
    "http://localhost:8000",
)


BEKANNTE_ADDONS = ("ca5234a0_paperless-ngx", "db21ed7f_paperless_ngx")


class PaperlessFehler(Exception):
    pass


def adresse(url):
    """Eingabe vereinheitlichen: ohne Schrägstrich und ohne „/api“ am Ende, http:// ergänzen."""
    url = (url or "").strip().rstrip("/")
    url = re.sub(r"/api$", "", url)
    if url and not re.match(r"(?i)https?://", url):
        url = "http://" + url
    return url


def _anfrage(url, token, pfad, roh=False, timeout=30, ssl_kontext=None):
    ziel = pfad if pfad.startswith("http") else adresse(url) + pfad
    kopf = {"Accept": "application/json; version=5"}
    if token:
        kopf["Authorization"] = f"Token {token}"
    req = urllib.request.Request(ziel, headers=kopf)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_kontext) as r:
            daten = r.read()
            if roh:
                name = r.headers.get_filename() or ""
                return daten, name, r.headers.get_content_type()
            return json.loads(daten)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) and "json" in (e.headers.get_content_type() or ""):
            raise PaperlessFehler("Paperless lehnt den Zugriff ab – bitte neu anmelden bzw. den API-Token prüfen") from e
        if e.code == 403:
            raise PaperlessFehler(f"Unter {adresse(url)} wird der Zugriff verweigert (403) – das ist vermutlich nicht "
                                  "die Paperless-Schnittstelle selbst") from e
        if e.code == 404:
            raise PaperlessFehler("Unter dieser Adresse antwortet kein Paperless (404)") from e
        raise PaperlessFehler(f"Paperless meldet Fehler {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        grund = getattr(e, "reason", e)
        raise PaperlessFehler(f"Paperless ist nicht erreichbar ({grund})") from e
    except ValueError as e:
        raise PaperlessFehler("Unter dieser Adresse antwortet kein Paperless") from e


def _alle(url, token, pfad, ssl_kontext=None):
    """Alle Seiten einer Liste abrufen (Paperless liefert „results“ und „next“)."""
    ergebnis, naechste = [], pfad
    while naechste:
        d = _anfrage(url, token, naechste, ssl_kontext=ssl_kontext)
        if not isinstance(d, dict) or "results" not in d:
            raise PaperlessFehler("Unter dieser Adresse antwortet kein Paperless")
        ergebnis += d["results"]
        naechste = d.get("next")
        if naechste:   # „next“ kann einen anderen Hostnamen tragen (Proxy) → nur Pfad und Abfrage übernehmen
            teile = urllib.parse.urlsplit(naechste)
            naechste = teile.path + ("?" + teile.query if teile.query else "")
    return ergebnis


def erreichbar(url, timeout=3):
    """Antwortet unter der Adresse wirklich die Paperless-Schnittstelle? Ohne Anmeldung antwortet sie mit 401/403,
    aber immer als JSON. Eine HTML-Seite (z. B. 403 vom Ingress-Eingang eines Add-ons, der nur Home Assistant
    durchlässt) zählt nicht."""
    req = urllib.request.Request(adresse(url) + "/api/", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return "json" in (r.headers.get_content_type() or "")
    except urllib.error.HTTPError as e:
        return e.code in (401, 403) and "json" in (e.headers.get_content_type() or "")
    except Exception:
        return False


def _supervisor(pfad):
    """Supervisor-Schnittstelle von Home Assistant (nur im Add-on; braucht „hassio_api: true“)."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    req = urllib.request.Request("http://supervisor" + pfad, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read()).get("data")
    except Exception:
        return None


def addon_kandidaten():
    """Installierte Paperless-Add-ons → [(name, läuft, [Adressen])]. Hostname und Ports liefert der Supervisor."""
    # Die Liste der installierten Add-ons steht in /info (für jedes Add-on lesbar; /addons bräuchte mehr Rechte).
    # Zur Sicherheit auch die bekannten Paperless-Add-ons direkt abfragen.
    liste = list((_supervisor("/info") or {}).get("addons") or [])
    for slug in BEKANNTE_ADDONS:
        if not any(a.get("slug") == slug for a in liste) and _supervisor(f"/addons/{slug}/info"):
            liste.append({"slug": slug, "name": "Paperless-ngx"})
    ergebnis = []
    for a in liste:
        if "paperless" not in (a.get("slug", "") + " " + a.get("name", "")).lower():
            continue
        info = _supervisor(f"/addons/{a['slug']}/info") or {}
        if not info and a.get("name") == "Paperless-ngx" and a["slug"] in BEKANNTE_ADDONS:
            continue
        hosts = [h for h in (info.get("hostname"), info.get("ip_address"), a["slug"].replace("_", "-")) if h]
        ports = [int(str(k).split("/")[0]) for k in (info.get("network") or {})]   # Ports im Container, z. B. „8000/tcp“
        # übliche Ports von Paperless; der Ingress-Port zuletzt (dort lassen viele Add-ons nur Home Assistant durch)
        ports += [p for p in (8000, 8010, 8080, 80, info.get("ingress_port")) if p and p not in ports]
        ergebnis.append((a.get("name") or a["slug"], (info.get("state") or a.get("state")) == "started",
                         [f"http://{h}:{p}" for h in dict.fromkeys(hosts) for p in ports]))
    return ergebnis


def suchen(ausser=()):
    """Paperless finden → (adresse | None, hinweis). Zuerst über Home Assistant, dann übliche Adressen im Heimnetz.
    ausser: Adressen, die schon nicht funktioniert haben."""
    ausser = {adresse(u) for u in ausser if u}
    addons = addon_kandidaten()
    for name, laeuft, adressen in addons:
        for u in adressen:
            if u not in ausser and erreichbar(u):
                return u, f"Add-on „{name}“ gefunden"
    if addons and not any(laeuft for _, laeuft, _ in addons):
        return None, f"Das Add-on „{addons[0][0]}“ ist installiert, läuft aber nicht – bitte in Home Assistant starten."
    for u in KANDIDATEN:
        if u not in ausser and erreichbar(u):
            return u, "Paperless gefunden"
    if addons:
        return None, f"Das Add-on „{addons[0][0]}“ antwortet nicht – bitte die Adresse von Hand eintragen."
    return None, "Paperless wurde nicht gefunden – bitte die Adresse eintragen (z. B. http://homeassistant.local:8000)."


def token_holen(url, benutzer, passwort, ssl_kontext=None):
    """API-Token mit Benutzername und Passwort von Paperless abrufen (das Passwort wird nicht gespeichert)."""
    req = urllib.request.Request(adresse(url) + "/api/token/", method="POST",
                                 data=urllib.parse.urlencode({"username": benutzer, "password": passwort}).encode(),
                                 headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl_kontext) as r:
            token = json.loads(r.read()).get("token")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            raise PaperlessFehler("Benutzername oder Passwort stimmt nicht") from e
        raise PaperlessFehler(f"Paperless unter {adresse(url)} meldet Fehler {e.code}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise PaperlessFehler("Paperless ist nicht erreichbar") from e
    if not token:
        raise PaperlessFehler("Paperless hat keinen Token geliefert")
    return token


def tags(url, token, ssl_kontext=None):
    return sorted(({"id": t["id"], "name": t["name"], "anzahl": t.get("document_count")}
                   for t in _alle(url, token, "/api/tags/?page_size=500", ssl_kontext)), key=lambda t: t["name"].lower())


def korrespondenten(url, token, ssl_kontext=None):
    return {k["id"]: k["name"] for k in _alle(url, token, "/api/correspondents/?page_size=500", ssl_kontext)}


def dokumente(url, token, tag_id, ssl_kontext=None):
    felder = "id,title,content,created,created_date,correspondent,original_file_name,mime_type"
    return _alle(url, token, f"/api/documents/?tags__id__all={int(tag_id)}&page_size=100&ordering=created&fields={felder}",
                 ssl_kontext)


def original_noetig(dokument):
    """PDF, XML und Mails zuerst als Original: In der Archivfassung fehlt die E-Rechnung. Bei Fotos und Office-Dateien
    ist die Archivfassung (PDF) besser – die kann die App anzeigen. (Scans: siehe finanzen._nur_scan.)"""
    typ = dokument.get("mime_type")
    if typ:
        return typ in ("application/pdf", "application/xml", "text/xml", "message/rfc822")
    return (dokument.get("original_file_name") or "").lower().endswith((".pdf", ".xml", ".eml"))


def herunterladen(url, token, doc_id, ssl_kontext=None, original=False):
    """Original bzw. Archivfassung (gibt es keine, liefert Paperless das Original) → (bytes, dateiname, typ)."""
    pfad = f"/api/documents/{int(doc_id)}/download/" + ("?original=true" if original else "")
    return _anfrage(url, token, pfad, roh=True, timeout=120, ssl_kontext=ssl_kontext)

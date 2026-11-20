"""Zugriff auf Paperless-ngx über dessen REST-Schnittstelle (nur lesend): Tags, Dokumente, Korrespondenten, Download.

Anmeldung mit dem API-Token aus Paperless (Profil → API-Token). Die App holt Dokumente mit einem bestimmten Tag
als Ausgaben-Belege ab; an Paperless selbst wird nichts geändert.
"""
import json
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
        if e.code in (401, 403):
            raise PaperlessFehler("Paperless lehnt den Zugriff ab – bitte den API-Token prüfen") from e
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
    """Antwortet unter der Adresse ein Paperless? (auch ohne Token: die API antwortet dann mit 401)"""
    try:
        with urllib.request.urlopen(urllib.request.Request(adresse(url) + "/api/", headers={"Accept": "application/json"}),
                                    timeout=timeout):
            return True
    except urllib.error.HTTPError as e:
        return e.code in (401, 403)
    except Exception:
        return False


def suchen():
    return next((u for u in KANDIDATEN if erreichbar(u)), None)


def tags(url, token, ssl_kontext=None):
    return sorted(({"id": t["id"], "name": t["name"], "anzahl": t.get("document_count")}
                   for t in _alle(url, token, "/api/tags/?page_size=500", ssl_kontext)), key=lambda t: t["name"].lower())


def korrespondenten(url, token, ssl_kontext=None):
    return {k["id"]: k["name"] for k in _alle(url, token, "/api/correspondents/?page_size=500", ssl_kontext)}


def dokumente(url, token, tag_id, ssl_kontext=None):
    felder = "id,title,content,created,created_date,correspondent,original_file_name,mime_type"
    return _alle(url, token, f"/api/documents/?tags__id__all={int(tag_id)}&page_size=100&ordering=created&fields={felder}",
                 ssl_kontext)


def herunterladen(url, token, doc_id, ssl_kontext=None):
    """Archivfassung (PDF mit Texterkennung) bzw. Original, falls es keine gibt → (bytes, dateiname, typ)."""
    return _anfrage(url, token, f"/api/documents/{int(doc_id)}/download/", roh=True, timeout=120, ssl_kontext=ssl_kontext)

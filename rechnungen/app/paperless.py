"""Übertragung von Rechnungs-PDFs an Paperless-ngx (REST-API, Token-Authentifizierung)."""
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

TIMEOUT = 30


class PaperlessError(Exception):
    def __init__(self, msg, fatal=False):
        super().__init__(msg)
        self.fatal = fatal   # True = betrifft alle Dokumente (keine Verbindung, Token falsch)


class Paperless:
    def __init__(self, url, token):
        self.base = url.strip().rstrip("/")
        if self.base.endswith("/api"):
            self.base = self.base[:-4]
        self.token = token.strip()
        self._cache = {}

    # ---------- HTTP ----------

    def _request(self, method, path, body=None, content_type=None):
        req = urllib.request.Request(self.base + path, data=body, method=method)
        req.add_header("Authorization", f"Token {self.token}")
        req.add_header("Accept", "application/json")
        if content_type:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                raw = res.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise PaperlessError("Paperless lehnt den Zugriff ab – API-Token prüfen.", fatal=True) from e
            detail = e.read().decode("utf-8", "replace")[:300]
            raise PaperlessError(f"Paperless meldet Fehler {e.code}: {detail}") from e
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise PaperlessError(f"Paperless unter {self.base} nicht erreichbar ({reason}).", fatal=True) from e
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return raw.decode("utf-8", "replace")

    def _json(self, method, path, data):
        return self._request(method, path, json.dumps(data).encode(), "application/json")

    # ---------- Stammdaten (per Name suchen, sonst anlegen) ----------

    def _id_for(self, endpoint, name):
        """ID eines Tags/Dokumenttyps/Korrespondenten nach Namen; fehlt er, wird er angelegt."""
        name = (name or "").strip()
        if not name:
            return None
        key = (endpoint, name.lower())
        if key not in self._cache:
            q = urllib.parse.urlencode({"name__iexact": name})
            found = self._request("GET", f"/api/{endpoint}/?{q}") or {}
            results = found.get("results") or []
            if results:
                self._cache[key] = results[0]["id"]
            else:
                # matching_algorithm 0 = „Keine“: Paperless soll nichts automatisch zuordnen
                created = self._json("POST", f"/api/{endpoint}/", {"name": name, "matching_algorithm": 0})
                self._cache[key] = created["id"]
        return self._cache[key]

    # ---------- Upload ----------

    def upload(self, pdf_bytes, filename, title, created=None, correspondent=None,
               document_type=None, tags=()):
        fields = [("title", title)]
        if created:
            fields.append(("created", created))
        if (cid := self._id_for("correspondents", correspondent)):
            fields.append(("correspondent", str(cid)))
        if (did := self._id_for("document_types", document_type)):
            fields.append(("document_type", str(did)))
        for tag in tags:
            if (tid := self._id_for("tags", tag)):
                fields.append(("tags", str(tid)))

        boundary = uuid.uuid4().hex
        parts = []
        for k, v in fields:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\n'
                     f"Content-Type: application/pdf\r\n\r\n".encode() + pdf_bytes + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        # Antwort: UUID der Verarbeitungsaufgabe – Paperless verarbeitet das Dokument im Hintergrund
        return self._request("POST", "/api/documents/post_document/", b"".join(parts),
                             f"multipart/form-data; boundary={boundary}")

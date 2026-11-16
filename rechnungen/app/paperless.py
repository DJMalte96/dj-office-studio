"""Übertragung von Rechnungs-PDFs an Paperless-ngx (REST-API, Token-Authentifizierung).

Es wird nur die PDF-Datei hochgeladen – Titel, Korrespondent, Tags usw. vergibt Paperless selbst.
"""
import urllib.error
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

    def upload(self, pdf_bytes, filename):
        """PDF an Paperless übergeben. Paperless verarbeitet das Dokument danach im Hintergrund."""
        boundary = uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\n'
                f"Content-Type: application/pdf\r\n\r\n").encode() + pdf_bytes + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.base + "/api/documents/post_document/", data=body, method="POST")
        req.add_header("Authorization", f"Token {self.token}")
        req.add_header("Accept", "application/json")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                res.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise PaperlessError("Paperless lehnt den Zugriff ab – API-Token prüfen.", fatal=True) from e
            detail = e.read().decode("utf-8", "replace")[:300]
            raise PaperlessError(f"Paperless meldet Fehler {e.code}: {detail}") from e
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise PaperlessError(f"Paperless unter {self.base} nicht erreichbar ({reason}).", fatal=True) from e

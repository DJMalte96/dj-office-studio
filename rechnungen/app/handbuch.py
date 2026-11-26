"""Handbuch in der App (seit 1.16): die README als Seite, mit Bildern, ohne Internet.

Die Kopie liegt in app/handbuch (erzeugt von docs/handbuch.py). Weggelassen werden das Logo, das Inhaltsverzeichnis
der README (die App zeigt die Abschnitte links) und der Teil für Entwickler ab „Lokale Entwicklung“.
"""
import os
import re
import threading

from flask import Blueprint, abort, jsonify, send_file

bp = Blueprint("handbuch", __name__)
ORDNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handbuch")
_cache = {}
_sperre = threading.Lock()


def _slug(text, trenner="-"):
    """Wie GitHub: klein, ohne Satzzeichen, Leerzeichen → „-“ (so passen die Links aus der README)."""
    t = re.sub(r"<[^>]+>", "", text).strip().lower()
    t = "".join(ch for ch in t if ch.isalnum() or ch in " -_")
    return t.replace(" ", trenner)


def html():
    pfad = os.path.join(ORDNER, "README.md")
    if not os.path.isfile(pfad):
        return None
    stand = os.path.getmtime(pfad)
    with _sperre:
        if _cache.get("stand") == stand:
            return _cache["html"]
        import markdown
        with open(pfad, encoding="utf-8") as f:
            text = f.read()
        text = text.split("\n## Lokale Entwicklung")[0]
        a, b = text.find("\n## Inhalt"), text.find("\n## Funktionen")
        if 0 <= a < b:
            text = text[:a] + text[b:]
        h = markdown.markdown(text, extensions=["tables", "fenced_code", "attr_list", "toc"],
                              extension_configs={"toc": {"slugify": _slug}})
        h = re.sub(r'<img[^>]*src="rechnungen/logo\.png"[^>]*>', "", h)
        h = re.sub(r'src="docs/bilder/([\w.-]+)\.png"', r'src="api/handbuch/bilder/\1.webp" loading="lazy"', h)
        _cache.update(stand=stand, html=h)
        return h


@bp.get("/api/handbuch")
def handbuch():
    h = html()
    if h is None:
        return jsonify({"error": "Das Handbuch ist in dieser Version nicht enthalten."}), 404
    return jsonify({"html": h})


@bp.get("/api/handbuch/bilder/<name>")
def bild(name):
    if not re.fullmatch(r"[\w.-]+\.webp", name) or ".." in name:
        abort(404)
    pfad = os.path.join(ORDNER, "bilder", name)
    if not os.path.isfile(pfad):
        abort(404)
    return send_file(pfad, mimetype="image/webp", max_age=86400)

"""Handbuch für die App (seit 1.16): README.md und verkleinerte Bilder nach rechnungen/app/handbuch kopieren.

Die App (Home Assistant und Desktop) zeigt das Handbuch unter ⚙ Einstellungen → Über die App – auch ohne Internet.
Nach jeder Änderung an der README ausführen (docs/screenshots.py ruft es am Ende selbst auf):
    python docs/handbuch.py
Ein Test (tests/test_handbuch.py) meldet, wenn die Kopie nicht mehr zur README passt.
"""
import re
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "rechnungen" / "app" / "handbuch"
BREITE = 1240          # Bilder in der App: halbe Auflösung der README-Bilder reicht
QUALITAET = 80


def bilder_in(text):
    return sorted(set(re.findall(r"docs/bilder/([\w.-]+\.png)", text)))


def erzeugen():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    if ZIEL.exists():
        shutil.rmtree(ZIEL / "bilder", ignore_errors=True)
    (ZIEL / "bilder").mkdir(parents=True, exist_ok=True)
    (ZIEL / "README.md").write_text(text, encoding="utf-8")
    groesse = 0
    for name in bilder_in(text):
        with Image.open(ROOT / "docs" / "bilder" / name) as b:
            b = b.convert("RGB")
            if b.width > BREITE:
                b = b.resize((BREITE, round(b.height * BREITE / b.width)), Image.LANCZOS)
            ziel = ZIEL / "bilder" / (Path(name).stem + ".webp")
            b.save(ziel, "WEBP", quality=QUALITAET, method=6)
            groesse += ziel.stat().st_size
    print(f"Handbuch: {len(bilder_in(text))} Bilder, {groesse / 1024 / 1024:.1f} MB → {ZIEL.relative_to(ROOT)}")


if __name__ == "__main__":
    erzeugen()

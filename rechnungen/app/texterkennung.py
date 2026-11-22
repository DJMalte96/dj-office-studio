"""Texterkennung (OCR) für Fotos und Scans – vollständig lokal, mit RapidOCR (PP-OCRv6, Modelle im Paket).

Läuft je Beleg in einem eigenen Prozess: Der Arbeitsspeicher (bis etwa 600 MB) wird danach wieder frei, und ein
Absturz der nativen Bibliotheken reißt die App nicht mit. Die App ruft nur lesen() auf; erkennen() und kind()
laufen im Kindprozess. Dieses Modul importiert deshalb nichts aus der App.
"""
import json
import math
import os
import subprocess
import sys
import tempfile

SCHALTER = "--texterkennung"     # damit startet die gepackte Desktop-App als Kindprozess (siehe desktop/start.py)
MAX_SEITE = 1600                 # längere Bildseite in Pixeln
MAX_PDF_SEITEN = 3
ZEITLIMIT = 240                  # Sekunden je Beleg (langsame Geräte wie Raspberry Pi)
PDF_SPEICHER_MB = 550            # nur fürs Öffnen fremder Dateien, nicht für die Erkennung
BILD_SPEICHER_MB = 1100          # 48-MP-HEIC vom iPhone braucht beim Dekodieren knapp 800 MB
BILD_ZEITLIMIT = 45
MIN_KANTE = 64                   # RapidOCR vergrößert dünnere Streifen auf Zehntausende Pixel Breite


class NichtVerfuegbar(Exception):
    """Die Bibliotheken laufen auf diesem Gerät nicht (z. B. macOS älter als 13)."""


class Fehlgeschlagen(Exception):
    """Dieser Beleg ließ sich nicht lesen."""


# ---------- Aufruf aus der App ----------

def _befehl():
    if getattr(sys, "frozen", False):
        return [sys.executable, SCHALTER]
    return [sys.executable, "-I", os.path.abspath(__file__), SCHALTER]


def lesen(pfad, zeitlimit=ZEITLIMIT):
    """Beleg im Kindprozess lesen → Text (Zeilen von oben nach unten)."""
    with tempfile.TemporaryDirectory(prefix="djos-text-") as tmp:
        ausgabe = os.path.join(tmp, "ergebnis.json")    # Datei statt stdout: Windows-Fensterprogramme haben keins
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        try:
            umgebung = {k: v for k, v in os.environ.items() if k not in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN")}
            p = subprocess.run(_befehl() + [os.path.abspath(pfad), ausgabe], timeout=zeitlimit, stdin=subprocess.DEVNULL, env=umgebung,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)
        except subprocess.TimeoutExpired as e:
            raise Fehlgeschlagen("hat zu lange gedauert") from e
        except OSError as e:
            raise NichtVerfuegbar(type(e).__name__) from e
        try:
            with open(ausgabe, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError) as e:
            # 86/87: die Grenzen aus grenzen.py (dieses Modul importiert hier nichts aus der App)
            grund = {86: "braucht zu viel Arbeitsspeicher", 87: "dauert zu lange"}.get(
                p.returncode, f"abgebrochen (Code {p.returncode}), evtl. zu wenig Arbeitsspeicher")
            raise Fehlgeschlagen(grund) from e
    if d.get("nicht_verfuegbar"):
        raise NichtVerfuegbar(d["nicht_verfuegbar"])
    if d.get("fehler"):
        raise Fehlgeschlagen(d["fehler"])
    return d.get("text", "")


# ---------- Textkästen → Zeilen ----------

def zeilen_bilden(kaesten, texte, kopfueber=False):
    """Textkästen zu Zeilen zusammensetzen: „SUMME EUR“ und das rechts daneben stehende „42,46“ gehören zusammen.
    kaesten: je 4 Punkte (oben links, oben rechts, unten rechts, unten links) in waagerechter Grundausrichtung."""
    teile = []
    for k, t in zip(kaesten, texte):
        (ax, ay), (bx, by), (cx, cy), (dx, dy) = ((float(x), float(y)) for x, y in k)
        teile.append({"x": (ax + bx + cx + dx) / 4, "y": (ay + by + cy + dy) / 4, "text": t.strip(),
                      "breite": math.hypot(bx - ax, by - ay), "hoehe": math.hypot(dx - ax, dy - ay),
                      "winkel": math.atan2((by - ay) + (cy - dy), (bx - ax) + (cx - dx))})
    if not teile:
        return []
    # Schräglage des Belegs: nach Breite gewichteter Median (lange Kästen messen den Winkel genauer)
    nach_winkel = sorted(teile, key=lambda e: e["winkel"])
    halb, summe = sum(e["breite"] for e in teile) / 2, 0
    winkel = 0
    for e in nach_winkel:
        summe += e["breite"]
        if summe >= halb:
            winkel = e["winkel"]
            break
    cos, sin, richtung = math.cos(winkel), math.sin(winkel), -1 if kopfueber else 1
    for e in teile:
        e["u"] = richtung * (e["x"] * cos + e["y"] * sin)
        e["v"] = richtung * (e["y"] * cos - e["x"] * sin)
    zeilen = []
    for e in sorted(teile, key=lambda e: e["v"]):
        passend = []
        for z in zeilen:
            abstand = abs(sum(x["v"] for x in z) / len(z) - e["v"])
            hoehe = min(e["hoehe"], min(x["hoehe"] for x in z))
            ueberlappt = any(abs(x["u"] - e["u"]) < (x["breite"] + e["breite"]) * .4 for x in z)
            if abstand <= .65 * hoehe and not ueberlappt:
                passend.append((abstand, z))
        if passend:
            min(passend, key=lambda p: p[0])[1].append(e)
        else:
            zeilen.append([e])
    zeilen.sort(key=lambda z: sum(x["v"] for x in z) / len(z))
    return [" ".join(x["text"] for x in sorted(z, key=lambda x: x["u"])) for z in zeilen]


# ---------- Kindprozess ----------

def _engine():
    from rapidocr import RapidOCR
    engine = RapidOCR(params={
        "Global.log_level": "error",
        "EngineConfig.onnxruntime.intra_op_num_threads": min(2, os.cpu_count() or 1),
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "Det.limit_type": "max", "Det.limit_side_len": 736,     # zusammen mit den Einzel-Batches: 540 statt 1540 MB
        "Cls.cls_batch_num": 1, "Rec.rec_batch_num": 1,
    })
    # Die Richtungserkennung meldet je Textkasten, ob er auf dem Kopf steht. RapidOCR gibt das nicht weiter,
    # deshalb hier mitschreiben (Version in requirements.txt fest).
    original = engine.cls_and_rotate

    def merken(bilder):
        gedreht, ergebnis = original(bilder)
        engine.richtungen = [r for r, _ in (ergebnis.cls_res or [])]
        return gedreht, ergebnis
    engine.cls_and_rotate = merken
    return engine


def _ist_pdf(pfad):
    with open(pfad, "rb") as f:
        return b"%PDF-" in f.read(1024)


def _bilder(pfad):
    """Foto bzw. die ersten PDF-Seiten als verkleinerte RGB-Bilder."""
    from PIL import Image, ImageOps
    if _ist_pdf(pfad):
        import pypdfium2
        pdf = pypdfium2.PdfDocument(pfad)
        try:
            for i in range(min(len(pdf), MAX_PDF_SEITEN)):
                seite = pdf[i]
                bild = seite.render(scale=MAX_SEITE / max(seite.get_size())).to_pil().convert("RGB")
                seite.close()
                yield bild
        finally:
            pdf.close()
        return
    import grenzen
    with grenzen.bild_oeffnen(pfad) as roh:
        roh.draft("RGB", (MAX_SEITE, MAX_SEITE))        # große JPEGs gleich verkleinert dekodieren
        bild = ImageOps.exif_transpose(roh)
        bild.thumbnail((MAX_SEITE, MAX_SEITE))
        if bild.mode in ("RGBA", "LA", "P"):            # durchsichtiger Hintergrund → weiß statt schwarz
            rgba = bild.convert("RGBA")
            bild = Image.new("RGB", rgba.size, "white")
            bild.paste(rgba, mask=rgba.getchannel("A"))
        yield bild.convert("RGB")


def _mit_rand(bild):
    if min(bild.size) >= MIN_KANTE:
        return bild
    from PIL import Image
    feld = Image.new("RGB", (max(bild.width, MIN_KANTE), max(bild.height, MIN_KANTE)), "white")
    feld.paste(bild, (0, 0))
    return feld


def erkennen(bild, engine):
    """Ein Bild lesen → Zeilen; auch um 90°, 180° oder 270° gedreht."""
    import numpy as np

    def lauf(b):
        engine.richtungen = []
        r = engine(np.asarray(b)[:, :, ::-1].copy())
        return ([], []) if r.boxes is None or not r.txts else (r.boxes, r.txts)

    kaesten, texte = lauf(bild)
    if len(texte):
        quer = gesamt = 0
        for k, t in zip(kaesten, texte):
            if len(t.strip()) < 3:
                continue
            xs, ys = [p[0] for p in k], [p[1] for p in k]
            gesamt += 1
            quer += (max(ys) - min(ys)) > (max(xs) - min(xs))
        if quer * 2 > gesamt:                           # Beleg liegt quer → drehen und noch einmal lesen
            kaesten, texte = lauf(bild.rotate(90, expand=True))
    r = engine.richtungen
    return zeilen_bilden(kaesten, texte, kopfueber=sum("180" in x for x in r) * 2 > len(r))


def kind(pfad, ausgabe):
    """Einstieg des Kindprozesses."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))

    if not getattr(sys, "frozen", False):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # -I: der eigene Ordner fehlt im Suchpfad
    import grenzen
    # Belege verlassen das Gerät nicht: In diesem Prozess gibt es kein Netz, auch kein Nachladen von Modellen.
    grenzen.ohne_netz()
    if hasattr(os, "nice"):
        try:
            os.nice(10)                                 # Home Assistant hat Vorrang
        except OSError:
            pass
    d = bilder = None
    # Zuerst die fremde Datei öffnen, unter engen Grenzen. Die Erkennung danach sieht nur noch kleine Bilder.
    try:
        grenzen.prozess_begrenzen(PDF_SPEICHER_MB if _ist_pdf(pfad) else BILD_SPEICHER_MB, BILD_ZEITLIMIT)
        bilder = [_mit_rand(b) for b in _bilder(pfad)]
    except MemoryError:
        os._exit(grenzen.ZU_VIEL_SPEICHER)
    except ImportError as e:
        d = {"nicht_verfuegbar": f"{type(e).__name__}: {e}"[:300]}
    except Exception as e:
        d = {"fehler": f"nicht lesbar ({type(e).__name__})"}
    if d is None:
        grenzen.prozess_begrenzen(None, ZEITLIMIT)
        try:
            engine = _engine()
        except Exception as e:
            d = {"nicht_verfuegbar": f"{type(e).__name__}: {e}"[:300]}
        else:
            try:
                d = {"text": "\n".join(z for bild in bilder for z in erkennen(bild, engine))}
            except Exception as e:
                d = {"fehler": f"nicht lesbar ({type(e).__name__})"}
    with open(ausgabe, "w", encoding="utf-8") as f:
        json.dump(d, f)


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == SCHALTER:
    kind(sys.argv[2], sys.argv[3])

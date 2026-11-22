"""Präparierte Dateien: Die App bleibt stehen, der Beleg bekommt einen Hinweis."""
import io
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

import belege
import erechnung_muster
import grenzen
import pdf_muster
import pdflesen
import texterkennung

WURZEL = Path(__file__).resolve().parents[1]
APP = WURZEL / "rechnungen" / "app"


@pytest.fixture(autouse=True)
def frisch():
    pdflesen._merker.clear()
    yield
    pdflesen._merker.clear()


def python(code, timeout=90):
    return subprocess.run([sys.executable, "-B", "-c", f"import sys; sys.path.insert(0, {str(APP)!r})\n{code}"],
                          capture_output=True, text=True, timeout=timeout)


# ---------- PDFs

@pytest.mark.parametrize("bau", ["flate_bombe", "doppelt_gepackt", "seitenbaum"])
def test_bombe_wird_abgebrochen(bau):
    daten = getattr(pdf_muster, bau)()
    anfang = time.time()
    v = belege.auswerten("r.pdf", daten)
    assert time.time() - anfang < pdflesen.ZEITLIMIT + pdflesen.START_RESERVE + 5
    assert v["betrag"] is None and "Sicherheitsgründen" in v["hinweise"][0]
    assert not belege.braucht_texterkennung("pdf", None, daten)         # nicht auch noch rendern


def test_endlose_querverweise_enden():
    anfang = time.time()
    belege.auswerten("r.pdf", pdf_muster.xref_schleife())
    assert time.time() - anfang < pdflesen.ZEITLIMIT + pdflesen.START_RESERVE + 5


def test_app_importiert_pypdf_nie():
    p = python(f"""sys.path.insert(0, {str(WURZEL / 'tests')!r})
import belege, importer, erechnung_muster
d = erechnung_muster.mail(("r.pdf", erechnung_muster.pdf(["Gesamt 5,00 EUR"])))
for m in list(sys.modules):
    if m.startswith("pypdf"): del sys.modules[m]
belege.auswerten("k.eml", d)
import pdf_muster
belege.auswerten("r.pdf", pdf_muster.mit_text(b"Gesamt 5,00 EUR"))
importer.pdf_text(pdf_muster.mit_text(b"Rechnung Nr. 1"))
print([m for m in sys.modules if m.startswith("pypdf")])""")
    assert p.stdout.strip() == "[]", p.stdout + p.stderr


def test_gewoehnliches_pdf_wie_bisher():
    v = belege.auswerten("r.pdf", erechnung_muster.pdf(["Musikhaus Probe", "Gesamt 119,00 EUR"]))
    assert (v["betrag"], v["lieferant"], v["hinweise"]) == (119, "Musikhaus Probe", [])


def test_kaputtes_pdf_geht_weiter_an_die_texterkennung():
    daten = b"%PDF-1.4\nkaputt"
    assert "Scan" in belege.auswerten("r.pdf", daten)["hinweise"][0]
    assert belege.braucht_texterkennung("pdf", None, daten)
    with pytest.raises(pdflesen.Kaputt):
        pdflesen.text(daten)


def test_erechnung_ueberlebt_bombe_und_warnt():
    v = belege.auswerten("r.pdf", pdf_muster.bombe_mit_erechnung(erechnung_muster.cii()))
    assert v["betrag"] == 53.5 and any("ließ sich nicht prüfen" in h for h in v["hinweise"])


def test_langes_pdf_behaelt_die_letzte_seite():
    from fpdf import FPDF
    f = FPDF()
    f.set_font("Helvetica", size=12)
    for i in range(130):
        f.add_page()
        f.cell(0, 8, f"Seite {i}")
    f.cell(0, 8, " Gesamtbetrag 4.711,00 EUR")
    v = belege.auswerten("r.pdf", bytes(f.output()))
    assert v["betrag"] == 4711 and any("Langes PDF" in h for h in v["hinweise"])


def test_zu_viel_text(tmp_path, monkeypatch):
    monkeypatch.setattr(pdflesen, "MAX_ZEICHEN", 10)
    (tmp_path / "beleg.pdf").write_bytes(pdf_muster.mit_text(b"mehr als zehn Zeichen"))
    assert "viel Text" in pdflesen._auslesen(str(tmp_path), False)["problem"]


@pytest.mark.parametrize("fehler, voll", [(MemoryError(), True), (ValueError(), False)])
def test_speicher_voll(fehler, voll):
    assert pdflesen._speicher_voll(fehler) == voll
    aussen = RuntimeError()
    aussen.__cause__ = fehler
    assert pdflesen._speicher_voll(aussen) == voll


def test_bibliotheksgrenze_zaehlt_als_speicher():
    from pypdf.errors import LimitReachedError
    assert pdflesen._speicher_voll(LimitReachedError("zu viel"))


def test_je_beleg_ein_prozess(monkeypatch):
    starts, echt = [], subprocess.run
    monkeypatch.setattr(pdflesen.subprocess, "run", lambda *a, **k: starts.append(1) or echt(*a, **k))
    daten = pdf_muster.mit_text(b"nur kurz")
    v = belege.auswerten("r.pdf", daten)
    belege.braucht_texterkennung(v["typ"], v["betrag"], daten)
    assert len(starts) == 1


def test_kind_ohne_token_des_supervisors(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    monkeypatch.setenv("HASSIO_TOKEN", "geheim")
    gesehen = []
    echt = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: gesehen.append(k.get("env")) or echt(*a, **k))
    pdflesen.lesen(pdf_muster.mit_text(b"x"))
    assert gesehen[0] is not None and "geheim" not in gesehen[0].values()


def test_texterkennung_ohne_token(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    gesehen = []

    class Fertig:
        returncode = 86

    monkeypatch.setattr(texterkennung.subprocess, "run", lambda *a, **k: gesehen.append(k.get("env")) or Fertig())
    with pytest.raises(texterkennung.Fehlgeschlagen, match="braucht zu viel"):
        texterkennung.lesen(str(tmp_path / "x.pdf"))
    assert gesehen[0] is not None and "geheim" not in gesehen[0].values()


def test_haengender_prozess_wird_beendet(monkeypatch):
    monkeypatch.setattr(pdflesen, "ZEITLIMIT", 1)
    monkeypatch.setattr(pdflesen, "START_RESERVE", 0)
    monkeypatch.setattr(pdflesen, "_befehl", lambda: [sys.executable, "-c", "import time; time.sleep(30)"])
    anfang = time.time()
    assert pdflesen.lesen(b"%PDF-haengt").problem == grenzen.GRUENDE[grenzen.ZU_LANGE]
    assert time.time() - anfang < 10


def test_absturz_wird_nicht_gemerkt(monkeypatch):
    monkeypatch.setattr(pdflesen, "_befehl", lambda: [sys.executable, "-c", "import os; os._exit(9)"])
    assert pdflesen.lesen(b"%PDF-absturz").problem
    assert not pdflesen._merker


def test_start_scheitert(monkeypatch):
    monkeypatch.setattr(pdflesen, "_befehl", lambda: ["/gibt/es/nicht"])
    assert "starten" in pdflesen.lesen(b"%PDF-start").problem and not pdflesen._merker


def test_desktop_startet_sich_als_pdf_leser(tmp_path):
    (tmp_path / "beleg.pdf").write_bytes(pdf_muster.mit_text(b"Hallo aus dem Kind"))
    subprocess.run([sys.executable, "-B", str(WURZEL / "desktop" / "start.py"), "--pdf-lesen", str(tmp_path), "beleg"], timeout=60, check=True)
    assert "Hallo aus dem Kind" in (tmp_path / "text.json").read_text(encoding="utf-8")


def test_import_meldet_und_macht_weiter(client):
    r = client.post("/api/import/analyse", data={"dateien": [
        (io.BytesIO(pdf_muster.seitenbaum()), "boese.pdf"),
        (io.BytesIO(pdf_muster.mit_text(b"nichts")), "fremd.pdf")]}, content_type="multipart/form-data")
    f = {x["datei"]: x["fehler"] for x in r.get_json()["fehler"]}
    assert "PDF nicht gelesen" in f["boese.pdf"] and "fremd.pdf" in f


# ---------- Grenzen des Kindprozesses

def test_speichergrenze_greift_auf_diesem_system():
    p = python("""import grenzen, os, time
grenzen.prozess_begrenzen(200, 30)
try:
    b = []
    for i in range(90):
        b.append(b"x" * 10_000_000)
        time.sleep(.03)
except MemoryError:
    os._exit(grenzen.ZU_VIEL_SPEICHER)
print("durch")""")
    assert "durch" not in p.stdout and p.returncode != 0, p.stderr


def test_zeitgrenze_greift_auch_bei_rechenarbeit():
    anfang = time.time()
    p = python("import grenzen; grenzen.prozess_begrenzen(None, 1)\nwhile True: pass", timeout=30)
    assert p.returncode == grenzen.ZU_LANGE and time.time() - anfang < 15


def test_speicher_laesst_sich_wieder_freigeben():
    p = python("""import grenzen
grenzen.prozess_begrenzen(150, 30)
grenzen.prozess_begrenzen(None, 30)
b = b"x" * 300_000_000
import time; time.sleep(.2)
print("frei")""")
    assert "frei" in p.stdout, p.stderr


def test_pdf_kind_begrenzt_sich_selbst(tmp_path):
    p = python(f"""import pdflesen
pdflesen.ZEITLIMIT = 1
def endlos(*a):
    while True: pass
pdflesen._auslesen = endlos
pdflesen.kind({str(tmp_path)!r}, "beleg")""", timeout=30)
    assert p.returncode == grenzen.ZU_LANGE


def test_ohne_netz():
    p = python("""import grenzen, socket
grenzen.ohne_netz()
try: socket.create_connection(("127.0.0.1", 9))
except OSError as e: print(e)""")
    assert "ohne Netzwerk" in p.stdout


def test_texterkennung_bricht_bombe_ab(tmp_path):
    (tmp_path / "b.pdf").write_bytes(pdf_muster.seite(pdf_muster.strom(pdf_muster.gepackt(b" ", 1_200_000_000), pdf_muster.FLATE)))
    with pytest.raises(texterkennung.Fehlgeschlagen):
        texterkennung.lesen(str(tmp_path / "b.pdf"))


def test_duenner_streifen_bekommt_rand():
    from PIL import Image
    assert texterkennung._mit_rand(Image.new("RGB", (1600, 1))).size == (1600, texterkennung.MIN_KANTE)
    assert texterkennung._mit_rand(Image.new("RGB", (800, 600))).size == (800, 600)


# ---------- Text

@pytest.mark.parametrize("text", [
    "IBAN DE02 1203 0000 0000 2020 51", "DE02120300000000202051", "Kundennummer 12345678901234567890",
    "Gesamt" + "." * 120 + "119,00 EUR", "Pos 1" + "." * 80 + "19,90", "1.234.567,89 EUR", "01.02.2026 03.02.2026 05.02.2026",
    "100 1,00 2,00 3,00 4,00 5,00 6,00 7,00 8,00 9,00 10,00 45,00 EUR", "Zeile eins\nZeile zwei\n"])
def test_gewoehnlicher_text_bleibt_unveraendert(text):
    assert grenzen.text_begrenzen(text) == text


def test_lange_zeile_wird_geteilt_ohne_betrag_zu_zerschneiden():
    text = "Wort " * 400 + "119,00 EUR"
    aus = grenzen.text_begrenzen(text).split("\n")
    assert all(len(z) <= grenzen.MAX_ZEILE for z in aus) and aus[-1].endswith("119,00 EUR")
    assert " ".join(" ".join(aus).split()) == text


def test_wort_bleibt_ganz():
    teile = " ".join(grenzen.text_begrenzen("Betragszeile " * 400).split("\n")).split()
    assert set(teile) == {"Betragszeile"}


def test_zifferngruppen_weg():
    assert "111.111.111" not in grenzen.text_begrenzen("111." * 1000)


def test_jede_auswertung_bekommt_begrenzte_zeilen():
    assert all(len(z) <= grenzen.MAX_ZEILE and "1" * 30 not in z for z in belege.zeilen_aus("1" * 5000 + "a " * 5000))


def test_riesentext_behaelt_das_ende():
    assert grenzen.text_begrenzen("x\n" * 400_000 + "Gesamt 5,00 EUR").endswith("Gesamt 5,00 EUR")


def test_viele_zeilen_begrenzt():
    assert grenzen.text_begrenzen("x\n" * 20_000).count("\n") <= grenzen.MAX_ZEILEN


@pytest.mark.parametrize("muster", ["1", "111.", "gesamt ", "brutto ", "1,", " ", "Summe\n", "1 111"])
@pytest.mark.parametrize("weg", ["mail", "ocr"])
def test_textauswertung_haengt_nicht(muster, weg):
    text = muster * (300_000 // len(muster))
    anfang = time.time()
    if weg == "mail":
        belege.auswerten("k.eml", ("From: L <a@example.org>\nSubject: Kauf\n\n" + text).encode())
    else:
        belege.ocr_vorschlaege(text)
    assert time.time() - anfang < 8          # langsame CI-Rechner – vorher: Minuten


def test_import_text_begrenzt(monkeypatch):
    import importer
    monkeypatch.setattr(pdflesen, "text", lambda *a, **k: ("Rechnung " + "1" * 100_000, False))
    assert "1" * 30 not in importer.pdf_text(b"x")


@pytest.mark.parametrize("kopf", ["From", "Subject"])
def test_riesige_kopfzeile(kopf):
    anfang = time.time()
    v = belege.auswerten("k.eml", f"{kopf}: {'a. ' * 100_000}\nX-Ende: x\n\nGesamt 5,00 EUR".encode())
    assert time.time() - anfang < 5 and len(v.get("beschreibung") or "") <= 120


def test_riesige_kopfzeile_in_mbox():
    anfang = time.time()
    belege.mbox_aufteilen(b"From x\nSubject: " + b"a. " * 100_000 + b"\n\nText\n")
    assert time.time() - anfang < 5


def test_jeder_mail_parser_begrenzt_kopfzeilen(monkeypatch):
    regeln, echt = [], belege.email.message_from_bytes
    monkeypatch.setattr(belege.email, "message_from_bytes", lambda d, policy=None: regeln.append(policy) or echt(d, policy=policy))
    m = erechnung_muster.mail()
    belege.auswerten("k.eml", m)
    belege.mbox_aufteilen(b"From x\n" + m)
    assert len(regeln) >= 3 and all(r is belege.MAIL_REGELN for r in regeln)


def test_riesige_html_zahl():
    assert "Gesamt" in belege.html_zu_text("&#" + "1" * 6000 + "; Gesamt 5 EUR")


@pytest.mark.parametrize("muster", ["<", "<script>", "<head", "<br "])
def test_html_haengt_nicht(muster):
    import finanzen
    text = muster * (300_000 // len(muster))
    anfang = time.time()
    belege.html_zu_text(text)
    finanzen._html_bereinigen(text)
    assert time.time() - anfang < 5


ALT_TEXT = re.compile(r"(?is)<(style|script|head)[^>]*>.*?</\1>")


@pytest.mark.parametrize("roh", [
    "<html><head><title>x</title></head><body>Hallo</body></html>", "<style>a{}</style>A<style>b{}</style>B",
    "<SCRIPT type='a'>x</SCRIPT>rest", "<script>offen", "ohne Tags", "<style>a<script>b</script>c</style>d", "a < b und c"])
def test_bloecke_wie_das_alte_muster(roh):
    assert belege.ohne_bloecke(roh, ("style", "script", "head"), " ") == ALT_TEXT.sub(" ", roh)


def test_header_element_ist_kein_head():
    assert "Laden" in belege.html_zu_text("<header>Laden</header><p>x</p><head></head>")


def test_vorschau_bleibt_bereinigt():
    import finanzen
    aus = finanzen._html_bereinigen("<p>ok</p><script>x()</script><iframe src=x><link href=y><script a='<'>offen")
    assert "<p>ok</p>" in aus and "x()" not in aus and not re.search(r"<(script|iframe|link)", aus)


def test_mail_mit_vielen_pdfs(monkeypatch):
    gelesen = []
    monkeypatch.setattr(pdflesen, "lesen", lambda d, layout=False: gelesen.append(d) or pdflesen.Ergebnis("", [], None, None, False))
    m = erechnung_muster.mail(*[(f"{i}.pdf", b"%%PDF-%d" % i) for i in range(15)])
    v = belege.auswerten("k.eml", m)
    assert len(set(gelesen)) <= belege.MAX_MAIL_PDFS + 1
    assert "5 weitere PDF-Anhänge nicht geprüft – bitte selbst ansehen" in v["hinweise"]


def test_mail_mit_bombe_nennt_den_grund():
    v = belege.auswerten("k.eml", erechnung_muster.mail(("r.pdf", pdf_muster.seitenbaum())))
    assert any("Angehängtes PDF" in h for h in v["hinweise"])


# ---------- Betragssuche

@pytest.mark.parametrize("zeilen, soll", [
    (["Positionssumme 198,00", "Gesamtbetrag der Abschläge -0,00", "Steuerbetrag in EUR 37,62", "Bruttosumme 235,62", "Zahlbetrag 235,62"], 235.62),
    (["Währung: EUR", "Gesamtbetrag der Zuschläge", "Steuerbetrag in EUR 3,50", "Bruttosumme 1.053,50", "Zahlbetrag 53,50"], 1053.5),
    (["Währung: EUR", "Zahlbetrag: 53,50"], 53.5),
    (["Summe der Rabatte 5,00 EUR", "Summe 45,00 EUR"], 45),
    (["Gesamtbetrag 119,00 EUR"], 119),
    (["Gesamtbetrag der Zuschläge inkl. USt 5,00 EUR", "Gesamt 45,00 EUR"], 45),
])
def test_teilsumme_ist_nicht_der_gesamtbetrag(zeilen, soll):
    assert belege.gesamt_vorschlag(zeilen)[0] == soll


def test_schlusszeile_nur_bei_euro():
    assert belege.gesamt_vorschlag(["Currency USD", "Bruttosumme 235,62"])[0] is None

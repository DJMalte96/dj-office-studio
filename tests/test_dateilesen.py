"""Outlook-Mails und HEIC-Vorschau im begrenzten Prozess."""
import io
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

import belege
import dateilesen
import grenzen
import pdflesen
from erechnung_muster import pdf, ubl
from msg_muster import msg

WURZEL = Path(__file__).resolve().parents[1]
APP = WURZEL / "rechnungen" / "app"
DATEIEN = WURZEL / "tests" / "beispiele" / "dateien"


@pytest.fixture(autouse=True)
def frisch():
    pdflesen._merker.clear()
    yield
    pdflesen._merker.clear()


def python(code):
    return subprocess.run([sys.executable, "-B", "-c", f"import sys; sys.path.insert(0, {str(APP)!r})\n{code}"],
                          capture_output=True, text=True, timeout=90)


def hochladen(client, name, daten):
    return client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(daten), name)]},
                       content_type="multipart/form-data").get_json()["neu"][0]


def test_msg_wie_bisher():
    v = belege.auswerten("k.msg", msg())
    assert (v["betrag"], v["lieferant"], v["beschreibung"], v["belegdatum"], v["message_id"]) == \
        (23.8, "Musterladen", "Kauf Kabel", "2026-03-10", "<probe@example.org>")


def test_msg_mit_erechnung():
    v = belege.auswerten("k.msg", msg(anhaenge=[("r.xml", ubl("O-1"))]))
    assert (v["betrag"], v["erechnung"]["nummer"]) == (119, "O-1")


def test_msg_mit_pdf():
    v = belege.auswerten("k.msg", msg(text="siehe Anhang", anhaenge=[("r.pdf", pdf(["Gesamt 47,11 EUR"]))]))
    assert v["betrag"] == 47.11


def test_andere_anhaenge_nur_mit_namen():
    _, a = belege.msg_lesen(msg(anhaenge=[("bild.png", b"geheim"), ("r.xml", ubl())]))
    assert [(n, d) for n, _, d in a] == [("bild.png", b""), ("r.xml", ubl())]


def test_anhaenge_begrenzt(monkeypatch, tmp_path):
    monkeypatch.setattr(dateilesen, "MAX_ANHAENGE", 3)
    monkeypatch.setattr(dateilesen, "MAX_ANHANG_BYTES", 1500)
    (tmp_path / "eingabe").write_bytes(msg(anhaenge=[(f"{i}.xml", b"<a>" + b"x" * 1000 + b"</a>") for i in range(5)]))
    d = dateilesen.msg_auslesen(str(tmp_path))
    assert [x[2] for x in d["anhaenge"]] == [True, False, False]


def test_text_gekuerzt_behaelt_ende(monkeypatch):
    monkeypatch.setattr(dateilesen, "MAX_TEXT", 1000)
    t = dateilesen._kuerzen("x" * 5000 + "Gesamt 5,00 EUR")
    assert len(t) <= 1001 and t.endswith("Gesamt 5,00 EUR")


def test_lange_kopfzeilen():
    m, _ = belege.msg_lesen(msg(betreff="b" * 5000, von="v" * 5000))
    assert len(m["betreff"]) == belege.MAX_KOPFZEILE == len(m["absender"])


def test_kaputte_msg_wie_bisher():
    v = belege.auswerten("k.msg", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 kein Outlook")
    assert "nicht gelesen" in v["hinweise"][0]


def abbruch(monkeypatch, code):
    monkeypatch.setattr(pdflesen, "_befehl", lambda: [sys.executable, "-c", f"import os; os._exit({code})"])


def test_abgebrochene_msg_nennt_den_grund(monkeypatch):
    abbruch(monkeypatch, grenzen.ZU_VIEL_SPEICHER)
    v = belege.auswerten("k.msg", msg())
    assert "Sicherheitsgründen" in v["hinweise"][0] and "Arbeitsspeicher" in v["hinweise"][0] and v["betrag"] is None
    assert not pdflesen._merker


@pytest.mark.parametrize("art", ["msg", "foto"])
def test_start_scheitert(monkeypatch, art):
    monkeypatch.setattr(pdflesen, "_befehl", lambda: ["/gibt/es/nicht"])
    if art == "foto":
        assert dateilesen.als_jpeg(b"x") is None
    else:
        with pytest.raises(pdflesen.Abgebrochen, match="Outlook"):
            dateilesen.msg(b"x")
    assert not pdflesen._merker


@pytest.mark.parametrize("name, code", [("k.msg", None), ("k.msg", grenzen.ZU_LANGE)])
def test_vorschau_kaputter_msg_ist_kein_serverfehler(client, monkeypatch, name, code):
    a = hochladen(client, name, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 kaputt")
    if code:
        pdflesen._merker.clear()
        abbruch(monkeypatch, code)
    r = client.get(f"/api/ausgaben/{a['id']}/ansicht")
    assert r.status_code == 200 and "keine Vorschau" in r.get_data(as_text=True)
    assert ("dauert zu lange" in r.get_data(as_text=True)) == bool(code)


def test_heic_vorschau_verkleinert():
    bild = Image.open(io.BytesIO(dateilesen.als_jpeg((DATEIEN / "foto.heic").read_bytes())))
    assert bild.format == "JPEG" and max(bild.size) == dateilesen.VORSCHAU


def test_kein_foto():
    assert dateilesen.als_jpeg(b"kein Bild") is None


def test_eps_wird_nie_geoeffnet(tmp_path):
    p = tmp_path / "beleg.jpg"
    p.write_bytes(b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\nshowpage\n")
    with pytest.raises(OSError):
        grenzen.bild_oeffnen(p)


def test_texterkennung_oeffnet_kein_eps(tmp_path):
    import texterkennung
    p = tmp_path / "beleg.jpg"
    p.write_bytes(b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\nshowpage\n")
    with pytest.raises(OSError, match="identify"):
        list(texterkennung._bilder(str(p)))


@pytest.mark.parametrize("endung", ["JPEG", "PNG", "WEBP", "TIFF", "GIF", "BMP"])
def test_uebliche_fotoformate_bleiben(tmp_path, endung):
    p = tmp_path / "beleg"
    Image.new("RGB", (40, 40), "white").save(p, endung)
    assert grenzen.bild_oeffnen(p).format == endung


def test_app_prozess_laedt_die_bibliotheken_nie():
    p = python(f"""import belege, dateilesen
belege.auswerten("k.msg", open({str(DATEIEN / 'kauf.msg')!r}, "rb").read())
assert dateilesen.als_jpeg(open({str(DATEIEN / 'foto.heic')!r}, "rb").read())
print([m for m in ("extract_msg", "pillow_heif", "PIL.Image", "olefile") if m in sys.modules])""")
    assert p.stdout.strip() == "[]", p.stdout + p.stderr


def test_nur_ein_prozess_je_beleg(monkeypatch):
    starts, echt = [], subprocess.run
    monkeypatch.setattr(pdflesen.subprocess, "run", lambda *a, **k: starts.append(1) or echt(*a, **k))
    daten = msg(anhaenge=[("r.xml", ubl())])
    belege.auswerten("k.msg", daten)
    belege.msg_lesen(daten)
    assert len(starts) == 1


def test_aufrufer_kann_gemerktes_nicht_veraendern():
    daten = msg()
    dateilesen.msg(daten)[0]["betreff"] = "anders"
    assert dateilesen.msg(daten)[0]["betreff"] == "Kauf Kabel"


def test_ohne_token(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "geheim")
    gesehen, echt = [], subprocess.run
    monkeypatch.setattr(pdflesen.subprocess, "run", lambda *a, **k: gesehen.append(k["env"]) or echt(*a, **k))
    dateilesen.msg(msg())
    assert "geheim" not in gesehen[0].values()


@pytest.mark.parametrize("art, ziel, konstante", [("msg", "msg_auslesen", "ZEITLIMIT"), ("foto", "foto_umwandeln", "FOTO_ZEITLIMIT")])
def test_kind_begrenzt_sich(tmp_path, art, ziel, konstante):
    p = python(f"""import pdflesen, dateilesen
pdflesen.{konstante} = 1
def endlos(*a):
    while True: pass
dateilesen.{ziel} = endlos
pdflesen.kind({str(tmp_path)!r}, {art!r})""")
    assert p.returncode == grenzen.ZU_LANGE


def test_foto_bekommt_mehr_speicher(tmp_path):
    p = python(f"""import pdflesen, grenzen, dateilesen
gesehen = []
grenzen.prozess_begrenzen = lambda mb, s: gesehen.append(mb)
def zeig(*a):
    print(gesehen[0], flush=True)
    return {{}}
dateilesen.foto_umwandeln = zeig
pdflesen.kind({str(tmp_path)!r}, "foto")""")
    assert p.stdout.strip() == str(pdflesen.FOTO_SPEICHER_MB), p.stderr


def test_desktop_startet_sich_als_msg_leser(tmp_path):
    (tmp_path / "eingabe").write_bytes(msg())
    subprocess.run([sys.executable, "-B", str(WURZEL / "desktop" / "start.py"), "--pdf-lesen", str(tmp_path), "msg"], timeout=60, check=True)
    assert "Kauf Kabel" in (tmp_path / "ergebnis.json").read_text(encoding="utf-8")

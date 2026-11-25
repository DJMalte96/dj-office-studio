"""Erzeugt die Screenshots für die README (docs/bilder/*.png) – nur mit erfundenen Beispieldaten.

    pip install -r rechnungen/requirements.txt playwright
    python -m playwright install chromium
    python docs/screenshots.py

Nach jeder sichtbaren Änderung an der Oberfläche ausführen und die Bilder mit committen.
"""
import json
import os
import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "docs" / "bilder"
tmp = tempfile.mkdtemp()
os.environ.update(DATA_DIR=tmp, OPTIONS_PATH=os.path.join(tmp, "options.json"))
sys.path.insert(0, str(ROOT / "rechnungen" / "app"))

import abschluss  # noqa: E402
import db  # noqa: E402
import finanzen  # noqa: E402
import main  # noqa: E402

abschluss.abschliessbar_ab = lambda j: date(int(j) + 1, 1, 1)   # Vorjahr auch in den ersten Januartagen abschließbar (nur für die Bilder)

finanzen.HINTERGRUND = False   # keine Streckenberechnung im Hintergrund (kein Internet nötig)
# Belege-Ordner /share/belege (Standard in Home Assistant) nachstellen – leer, damit die Bilder den Normalfall zeigen
_ordner_liste = finanzen._ordner_liste
finanzen._ordner_liste = lambda muster: ["/share/belege"] if muster == "/share/belege" else _ordner_liste(muster)
_ordner_dateien = finanzen._ordner_dateien
finanzen._ordner_dateien = lambda o, *a, **k: iter(()) if o == "/share/belege" else _ordner_dateien(o, *a, **k)

db.init()
db.save_settings({
    "_uebernommen": True, "_hinweis_bestaetigt": 1, "name": "Max Beispiel", "strasse": "Musterweg 1", "plz_ort": "12345 Musterstadt",
    "telefon": "0170/1234567", "ort_fuer_datum": "Musterstadt", "bank_name": "Sparkasse Musterstadt",
    "iban": "DE00 0000 0000 0000 0000 00", "bic": "ABCDEFGHXXX", "steuernummer": "12/345/67890",
    "kleinunternehmer": True, "startnummer": 37, "angebot_startnummer": 10, "angebot_gueltigkeit_tage": 30,
    "pdf_ordner": os.path.join(tmp, "pdf"),   # in den Einstellungen wird unten der übliche Pfad gezeigt
    "paperless_installiert": True, "paperless_eingangsordner": "/share/paperless/consume",
    "absender_email": "max@example.de", "smtp_server": "smtp.example.de", "smtp_port": 587,
    "smtp_sicherheit": "starttls", "smtp_passwort": "nur-ein-beispiel",
})
c = main.app.test_client()
c.environ_base["HTTP_X_DJOS"] = "1"
heute = date.today()
db.save_settings({"_letzte_sicherung": f"{heute - timedelta(days=12)}T19:42:00"})   # Startseite: Sicherung vor 12 Tagen
db.save_settings({"_rundgang_anbieten": False})   # Frage nach dem Rundgang nicht auf jedem Bild (eigenes Bild unten)
d = lambda n: (heute + timedelta(days=n)).isoformat()   # noqa: E731
ZB8 = "Bitte den Betrag innerhalb der nächsten 8 Tage auf das unten genannte Konto überweisen."
K = {
    "anna": {"name": "Anna und Jonas Muster", "strasse": "Lindenweg 12", "plz": "12345", "ort": "Musterstadt"},
    "bernd": {"name": "Bernd Probe", "strasse": "Am Markt 3", "plz": "12346", "ort": "Beispielhausen",
              "email": "bernd.probe@example.de"},
    "carla": {"name": "Carla Test", "strasse": "Rosenstr. 8", "plz": "12347", "ort": "Testdorf"},
    "dora": {"name": "Dora Alt", "strasse": "Feldweg 2", "plz": "12348", "ort": "Altstadt"},
    "verein": {"name": "Sportverein Musterstadt e. V.", "strasse": "Sportplatz 1", "plz": "12345", "ort": "Musterstadt"},
    "firma": {"name": "Beispiel GmbH", "strasse": "Industriestr. 5", "plz": "12349", "ort": "Neustadt"},
    "eva": {"name": "Eva und Tom Probe", "strasse": "Birkenallee 7", "plz": "12346", "ort": "Beispielhausen"},
}
H = "Jede weitere angefangene Stunde wird mit 80,- Euro berechnet.\nDie GEMA-Anmeldung erfolgt durch den Veranstalter."


def pos(text, datum, preis):
    return {"beschreibung": text, "lieferdatum": datum, "preis": preis}


def angebot(nr, kunde, datum, gueltig, positionen):
    r = c.post("/api/angebote", json={"art": "angebot", "nummer": nr, "datum": datum, "gueltig_bis": gueltig,
                                      "kunde": K[kunde], "positionen": positionen, "hinweise": H})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def rechnung(nr, kunde, datum, positionen, bezahlt=False, angebot_id=None):
    r = c.post("/api/rechnungen", json={"nummer": nr, "datum": datum, "kunde": K[kunde], "positionen": positionen,
                                        "zahlungsbedingung": ZB8, "angebot_id": angebot_id})
    assert r.status_code == 201, r.get_json()
    inv_id = r.get_json()["id"]
    if bezahlt:
        c.patch(f"/api/rechnungen/{inv_id}/bezahlt", json={"bezahlt": True})
    return inv_id


# Angebote
a010 = angebot("010", "anna", d(-60), d(-30), [pos("DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr", d(-18), 900)])
angebot("011", "carla", d(-40), d(-10), [pos("DJ – Tätigkeit Geburtstagsfeier – 20:00 Uhr bis 2:00 Uhr", d(10), 600)])
angebot("012", "verein", d(-28), d(2), [pos("DJ – Tätigkeit Vereinsfeier – 19:00 Uhr bis 1:00 Uhr", d(40), 700)])
a013 = angebot("013", "eva", d(-6), d(24), [pos("DJ – Tätigkeit Hochzeit – 16:00 Uhr bis 2:00 Uhr", d(200), 1100),
                                     pos("Fahrtkosten", d(200), 60)])
angebot("014", "firma", d(-2), d(28), [pos("DJ – Tätigkeit Weihnachtsfeier – 18:00 Uhr bis 0:00 Uhr", d(30), 650)])

db.add_versand("angebot", a013, "eva.probe@example.de", "Ihr Angebot 013")

# Rechnungen: bezahlt, überfällig mit Zahlungserinnerung, offen, storniert
rechnung("030", "dora", f"{heute.year - 1}-11-15",
         [pos("DJ – Tätigkeit Geburtstagsfeier – 20:00 Uhr bis 2:00 Uhr", f"{heute.year - 1}-11-15", 800)], bezahlt=True)
rechnung("038", "firma", d(-30), [pos("DJ – Tätigkeit Firmenfeier – 19:00 Uhr bis 0:00 Uhr", d(-31), 500)])
rechnung("039", "carla", d(-21), [pos("DJ – Tätigkeit Geburtstagsfeier – 19:00 Uhr bis 1:00 Uhr", d(-21), 650)],
         bezahlt=True)
r040 = rechnung("040", "anna", d(-16), [pos("DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr", d(-18), 900),
                                        pos("Fahrtkosten", d(-18), 60)], angebot_id=a010)
r041 = rechnung("041", "bernd", d(-4), [pos("DJ – Tätigkeit Firmenfeier – 19:00 Uhr bis 0:00 Uhr", d(-4), 450)])
c.post(f"/api/rechnungen/{r040}/mahnung")                                        # Zahlungserinnerung
db.add_versand("rechnung", r040, "anna.muster@example.de", "Rechnung 040")     # per E-Mail verschickt
db.festschreiben(r040, main.absender_jetzt())
for k in db.list_items("kunden"):                                               # E-Mail-Adresse bei Bernd
    if k["name"] == "Bernd Probe":
        db.set_customer_email(k["id"], "bernd.probe@example.de")
r038 = next(r["id"] for r in db.list_invoices() if r["nummer"] == "038")
c.post(f"/api/rechnungen/{r038}/stornieren")                                    # 038 → Stornorechnung 042

# Finanzen: bezahlte Auftritte übers Jahr, Ausgaben (auch Kauf-Mails), Fahrten, ein Gerät mit Abschreibung
FRUEHER = [(2, 14, "carla", "Geburtstagsfeier", 650), (4, 26, "verein", "Vereinsfeier", 700), (5, 23, "eva", "Hochzeit", 1100),
           (6, 13, "firma", "Sommerfest", 850), (7, 18, "dora", "Geburtstagsfeier", 600), (8, 22, "anna", "Hochzeit", 1200),
           (9, 12, "bernd", "Firmenfeier", 750)]
nr = 31
for monat, tag, kunde, anlass, preis in FRUEHER:
    datum = date(heute.year, monat, tag)
    if datum >= heute - timedelta(days=40):
        continue
    inv = rechnung(f"0{nr}", kunde, datum.isoformat(), [pos(f"DJ – Tätigkeit {anlass} – 19:00 Uhr bis 1:00 Uhr", datum.isoformat(), preis)],
                   bezahlt=True)
    c.put(f"/api/rechnungen/{inv}/bezahlt_am", json={"bezahlt_am": (datum + timedelta(days=6)).isoformat()})
    nr += 1
# Vorjahr: ein paar Auftritte und Ausgaben (für den Jahresabschluss)
v = heute.year - 1
for i, (monat, tag, kunde, anlass, preis) in enumerate([(3, 8, "verein", "Vereinsfeier", 650), (6, 21, "anna", "Hochzeit", 1150),
                                                        (9, 6, "carla", "Geburtstagsfeier", 600), (12, 12, "firma", "Weihnachtsfeier", 700)]):
    datum = date(v, monat, tag)
    inv = rechnung(f"02{i}", kunde, datum.isoformat(), [pos(f"DJ – Tätigkeit {anlass} – 19:00 Uhr bis 1:00 Uhr", datum.isoformat(), preis)],
                   bezahlt=True)
    c.put(f"/api/rechnungen/{inv}/bezahlt_am", json={"bezahlt_am": (datum + timedelta(days=5)).isoformat()})
for datum, lieferant, betrag, kategorie, text in [(f"{v}-04-10", "Kabelshop Probe", 54.90, "technik", "Kabeltrommel"),
                                                  (f"{v}-08-02", "Versicherung Muster", 186.40, "versicherung", "Betriebshaftpflicht"),
                                                  (f"{v}-12-30", "Mobilfunk Beispiel", 29.99, "telefon", "Handyvertrag Januar")]:
    c.post("/api/ausgaben", json={"belegdatum": datum, "lieferant": lieferant, "betrag": betrag, "kategorie": kategorie,
                                  "beschreibung": text, "notiz": "Beleg in Papierform"})
with db.connect() as con:                                                       # km wie vom Kartendienst berechnet
    for i, (fid,) in enumerate(con.execute("SELECT id FROM fahrten ORDER BY datum DESC").fetchall()):
        con.execute("UPDATE fahrten SET km_einfach = ? WHERE id = ?", ([24.6, 12.3, 38.1, 7.9, 52.4, 18.0, 31.2, 9.6][i % 8], fid))
db.save_settings({"kartendienst": True})   # erst jetzt einschalten – beim Anlegen oben keine Abfrage ins Internet


def ausgabe(datum, lieferant, betrag, kategorie, beschreibung=""):
    r = c.post("/api/ausgaben", json={"belegdatum": datum, "lieferant": lieferant, "betrag": betrag, "kategorie": kategorie,
                                      "beschreibung": beschreibung, "notiz": "Beleg in Papierform"})
    assert r.status_code == 201, r.get_json()


j = heute.year
for datum, lieferant, betrag, kategorie, text in [
        (f"{j}-01-15", "Mobilfunk Beispiel", 29.99, "telefon", "Handyvertrag"), (f"{j}-02-03", "Versicherung Muster", 186.40, "versicherung", "Betriebshaftpflicht"),
        (f"{j}-03-12", "Musterhaus Technik", 2380, "anschaffung", "Aktivboxen (Paar)"), (f"{j}-04-08", "Kabelshop Probe", 64.80, "technik", "XLR-Kabel, Adapter"),
        (f"{j}-05-20", "Druckerei Beispiel", 89.00, "werbung", "Flyer und Visitenkarten"), (f"{j}-07-02", "Musterhaus Technik", 149.00, "technik", "Funkmikrofon"),
        (f"{j}-09-15", "Webhosting Muster", 59.88, "werbung", "Website (Jahr)")]:
    if datum < heute.isoformat():
        ausgabe(datum, lieferant, betrag, kategorie, text)
BEISPIELMAILS = ROOT / "tests" / "beispiele" / "mails"
mails = [("dateien", (open(BEISPIELMAILS / n, "rb"), n)) for n in ("beatport.eml", "apple.eml", "qobuz.eml")]
neu = c.post("/api/ausgaben/belege", data={"dateien": [m[1] for m in mails]}, content_type="multipart/form-data").get_json()["neu"]
for a in neu[:2]:                                                                   # zwei geprüft, eine wartet noch
    c.put(f"/api/ausgaben/{a['id']}", json={"uebernehmen": True})
# zwei Einträge im Papierkorb
for lieferant, betrag, datum, text in (("Druckerei Beispiel", 24.90, f"{j}-01-20", "Plakat (doppelt erfasst)"),
                                       ("Parkhaus am Markt", 12.50, f"{j}-01-27", "privat geparkt")):
    r = c.post("/api/ausgaben", json={"belegdatum": datum, "lieferant": lieferant, "betrag": betrag, "kategorie": "sonstiges",
                                      "beschreibung": text, "notiz": "Beispiel"}).get_json()
    c.delete(f"/api/ausgaben/{r['id']}")

from playwright.sync_api import sync_playwright  # noqa: E402
from waitress import create_server  # noqa: E402

srv = create_server(main.app, host="127.0.0.1", port=0)
threading.Thread(target=srv.run, daemon=True).start()
URL = f"http://127.0.0.1:{srv.effective_port}/"
ZIEL.mkdir(parents=True, exist_ok=True)
fehler = []


def oeffne(page, menue, tab):
    page.click(f"nav .menu-kopf >> text={menue}")
    page.click(f"nav [data-tab='{tab}']")
    page.wait_for_timeout(900)
    page.mouse.move(5, 890)


with sync_playwright() as p:
    browser = p.chromium.launch(args=["--lang=de-DE"])
    ctx = browser.new_context(viewport={"width": 1240, "height": 900}, device_scale_factor=2, locale="de-DE")
    ctx.add_init_script("try { localStorage.setItem('theme','light') } catch (e) {}")
    page = ctx.new_page()
    page.on("pageerror", lambda e: fehler.append(str(e)))

    page.goto(URL)
    page.wait_for_timeout(1500)
    page.screenshot(path=str(ZIEL / "startseite.png"), full_page=True)

    oeffne(page, "Rechnungen", "liste")
    page.screenshot(path=str(ZIEL / "rechnungen.png"), full_page=True)

    oeffne(page, "Angebote", "angebote")
    page.screenshot(path=str(ZIEL / "angebote.png"), full_page=True)

    page.click("#einstellungen-btn")
    page.wait_for_timeout(800)
    page.fill("[name=pdf_ordner]", "/share/rechnungen")   # üblicher Pfad statt Temp-Ordner (nicht gespeichert)
    page.mouse.move(5, 890)
    page.screenshot(path=str(ZIEL / "einstellungen.png"), full_page=True)

    # Versand-Dialog für Rechnung 041
    oeffne(page, "Rechnungen", "liste")
    page.locator("#offen tr[data-id]", has_text="_041_").locator("button[data-act=senden]").click()
    page.wait_for_timeout(800)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.screenshot(path=str(ZIEL / "versand.png"))
    page.click("#versand-abbrechen")

    # QR-Code zum Bezahlen für Rechnung 041
    page.locator("#offen tr[data-id]", has_text="_041_").locator("button[data-act=qr]").click()
    page.wait_for_timeout(800)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.screenshot(path=str(ZIEL / "girocode.png"))
    page.click("#qr-zu")

    # Finanzen
    oeffne(page, "Finanzen", "finanzen")
    page.screenshot(path=str(ZIEL / "finanzen.png"), full_page=True)
    oeffne(page, "Finanzen", "ausgaben")
    page.screenshot(path=str(ZIEL / "ausgaben.png"), full_page=True)
    page.click("#papierkorb-oeffnen")
    page.wait_for_timeout(700)
    page.screenshot(path=str(ZIEL / "papierkorb.png"))
    page.click("#papierkorb-zurueck")
    page.wait_for_timeout(700)
    page.click("#alle-pruefen")
    page.wait_for_timeout(1500)
    page.mouse.move(5, 890)
    page.screenshot(path=str(ZIEL / "beleg-pruefen.png"))
    sys.path.insert(0, str(ROOT / "tests"))
    from erechnung_muster import ubl
    xml = ubl("2026-0815", str(date.today() - timedelta(days=3)), "178.50", "150.00", "28.50", posten="Funkmikrofon-Set")
    page.locator("#beleg-schliessen").click()
    page.set_input_files("#beleg-dateien", files=[{"name": "rechnung-2026-0815.xml", "mimeType": "application/xml", "buffer": xml}])
    page.wait_for_timeout(1500)
    page.locator("#ausgaben-neu .neu-beleg", has_text="Musikhaus Probe").locator("[data-act=pruefen]").click()
    page.wait_for_timeout(1500)
    page.screenshot(path=str(ZIEL / "e-rechnung.png"))
    page.once("dialog", lambda d: d.accept())     # danach wieder wegräumen, die übrigen Bilder bleiben ohne sie
    page.locator("#beleg-verwerfen").click()
    page.wait_for_timeout(6000)     # bis die Meldung unten verschwunden ist
    oeffne(page, "Finanzen", "fahrten")
    page.screenshot(path=str(ZIEL / "fahrten.png"), full_page=True)
    oeffne(page, "Finanzen", "euer")
    page.screenshot(path=str(ZIEL / "euer.png"), full_page=True)

    # Absender ändern: Rückfrage zu den noch nicht festgeschriebenen Rechnungen (wird abgebrochen)
    page.click("#einstellungen-btn")
    page.wait_for_timeout(800)
    page.fill("#einstellungen [name=strasse]", "Neuer Weg 9")
    page.click("#einstellungen button[type=submit]")
    page.wait_for_selector("#absender-dialog[open]")
    page.wait_for_timeout(400)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.locator("#absender-dialog").screenshot(path=str(ZIEL / "absender.png"))
    page.click("#absender-abbrechen")

    # Abos: zwei fällige Abbuchungen unter „Neu – bitte prüfen“ und die Abo-Liste
    for w in ({"lieferant": "Musikpool Beispiel", "beschreibung": "DJ-Musikpool (Monatsabo)", "betrag": "19,99", "rhythmus": "monatlich",
               "tag": 1, "beginn": date(heute.year, heute.month, 1).isoformat(), "nachtragen": True},
              {"lieferant": "DJ-Software Pro", "beschreibung": "Software-Abo (Jahreslizenz)", "betrag": "119", "rhythmus": "jaehrlich",
               "tag": (heute - timedelta(days=12)).day, "beginn": (heute - timedelta(days=12)).isoformat(), "nachtragen": True},
              {"lieferant": "Promo-Pool Muster", "beschreibung": "Promo-Downloads", "betrag": "4,99", "rhythmus": "vierwochen",
               "beginn": (heute - timedelta(days=3)).isoformat()}):
        assert c.post("/api/abos", json=w | {"kategorie": "musik"}).status_code == 201
    oeffne(page, "Finanzen", "ausgaben")
    page.wait_for_timeout(600)
    page.evaluate("document.querySelector('#toast').classList.add('hidden'); document.querySelector('header').style.visibility = 'hidden'")
    page.locator("#ausgaben-neu-karte").screenshot(path=str(ZIEL / "abos-faellig.png"))
    page.evaluate("document.querySelector('header').style.visibility = ''")
    page.click("#abos-oeffnen")
    page.wait_for_selector("#abos-dialog[open]")
    page.wait_for_timeout(400)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.locator("#abos-dialog").screenshot(path=str(ZIEL / "abos.png"))
    page.click("[data-abos=schliessen]")
    for f in c.get("/api/abos/faellig").get_json():      # für die übrigen Bilder wieder erledigt
        c.post(f"/api/abos/{f['abo_id']}/termine/{f['datum']}", json={"aktion": "ok"})

    # Jahresabschluss des Vorjahres: Assistent (Schritt 1), danach abgeschlossen und „wieder öffnen“
    oeffne(page, "Finanzen", "euer")
    page.select_option("#euer-jahr", str(v))
    page.wait_for_timeout(900)
    page.click("#abschluss-band [data-abschluss=start]")
    page.wait_for_selector("#abschluss-dialog[open]")
    page.wait_for_timeout(600)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.locator("#abschluss-dialog").screenshot(path=str(ZIEL / "jahresabschluss.png"))
    page.click("[data-abschluss=schliessen]")
    for a in c.get("/api/ausgaben").get_json():           # wartenden Beleg übernehmen, dann abschließen
        if a["status"] == "neu":
            c.put(f"/api/ausgaben/{a['id']}", json={"uebernehmen": True})
    r = c.post(f"/api/abschluss/{v}", json={"bestaetigt": True})
    assert r.status_code == 201, r.get_json()
    page.reload()
    page.wait_for_timeout(1000)
    oeffne(page, "Finanzen", "euer")
    page.select_option("#euer-jahr", str(v))
    page.wait_for_timeout(1000)
    page.screenshot(path=str(ZIEL / "jahr-abgeschlossen.png"), clip={"x": 0, "y": 0, "width": 1240, "height": 560})
    page.click("#abschluss-band [data-abschluss-oeffnen]")
    page.wait_for_selector("#oeffnen-dialog[open]")
    page.locator("#oeffnen-vorschlaege button", has_text="Beleg nachgereicht").click()
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(300)
    page.locator("#oeffnen-dialog").screenshot(path=str(ZIEL / "jahr-oeffnen.png"))
    page.click("#oeffnen-abbrechen")

    # Rundgang und Schnellsuche (seit 1.12)
    page.evaluate("showTab('start')")
    page.wait_for_timeout(800)
    page.evaluate("document.querySelector('#tour-frage').showModal()")
    page.wait_for_timeout(300)
    page.locator("#tour-frage").screenshot(path=str(ZIEL / "rundgang-frage.png"))
    page.click("#tour-frage [data-frage=los]")
    page.wait_for_timeout(500)
    for _ in range(3):
        page.click(".tour-karte [data-tour=weiter]")
        page.wait_for_timeout(600)
    page.screenshot(path=str(ZIEL / "rundgang.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    page.keyboard.press("Control+k")
    page.wait_for_timeout(800)
    page.keyboard.type("hochzeit")
    page.wait_for_timeout(400)
    page.screenshot(path=str(ZIEL / "suche.png"))
    page.keyboard.press("Escape")

    # Nachfrage zu einem Angebot ohne Antwort (seit 1.11)
    page.evaluate("showTab('start')")
    page.wait_for_timeout(1000)
    page.locator("#start [data-start=nachfragen]").first.click()
    page.wait_for_timeout(700)
    page.locator("#nachfrage").screenshot(path=str(ZIEL / "nachfrage.png"))
    page.keyboard.press("Escape")

    # Rechnungseditor mit Bestandskunde und zwei Positionen
    ctx2 = browser.new_context(viewport={"width": 1240, "height": 1180}, device_scale_factor=2, locale="de-DE")
    ctx2.add_init_script("try { localStorage.setItem('theme','light') } catch (e) {}")
    page = ctx2.new_page()
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.goto(URL)
    page.wait_for_timeout(1000)
    oeffne(page, "Rechnungen", "neu")
    page.fill("#k-name", "Anna")
    page.wait_for_timeout(600)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    erste = page.locator("#positionen .pos").nth(0)
    erste.locator(".tb").select_option(label="Hochzeit")
    erste.locator(".von").fill("17:00")
    erste.locator(".bis").fill("02:00")
    erste.locator(".lieferdatum").fill(d(-2))
    erste.locator(".preis").fill("960")
    page.click("#pos-add")
    zweite = page.locator("#positionen .pos").nth(1)
    zweite.locator(".tb").select_option(value="frei")
    zweite.locator(".beschreibung").fill("Fahrtkosten")
    zweite.locator(".preis").fill("60")
    page.evaluate("document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0)")
    page.mouse.move(5, 1100)
    page.wait_for_timeout(400)
    page.screenshot(path=str(ZIEL / "rechnungseditor.png"))
    # Preis-Spickzettel und Anzahlungsrechnung (seit 1.11)
    erste.locator(".spick").evaluate("e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(200)
    erste.locator(".spick").screenshot(path=str(ZIEL / "spickzettel.png"))
    page.locator("#rechnungsart-box label", has_text="Anzahlungsrechnung").click()
    page.wait_for_timeout(400)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.locator("#positionen").locator("xpath=ancestor::div[contains(@class,'card')]").screenshot(path=str(ZIEL / "anzahlung.png"))
    browser.close()

print("Bilder in", ZIEL, "– JavaScript-Fehler:", fehler or "keine")
sys.exit(1 if fehler else 0)

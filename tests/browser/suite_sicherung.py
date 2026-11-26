"""Seit 1.15: Sicherungs-Passwort, E-Rechnung, Notizen, Menüleiste auf dem Handy.

Aus den Klick-Tests der jeweiligen Version übernommen; läuft über tests/browser/test_browser.py."""
import io
import zipfile

import erechnung
import facturx
import verschluesselung

SZENARIO = "114"


def lauf(pg, URL, ok, ENGINE, B, DATEIEN):
    shot = lambda pg, sel, name: ENGINE == "chromium" and pg.locator(sel).first.screenshot(path=f"{B}/{name}.png")
    api = lambda pg, pfad: pg.evaluate(f"async () => (await fetch('api/{pfad}')).json()")
    PW = "Plattenkiste-1987!"
    pg.goto(URL); pg.wait_for_timeout(2500)

    # ---------- Sicherung ohne Passwort: Warnung, dann festlegen ----------
    pg.evaluate("showTab('einstellungen')"); pg.wait_for_timeout(1500)
    pg.click(".eins-nav [data-thema=sicherung]"); pg.wait_for_timeout(300)   # seit 1.16: Einstellungen nach Themen
    ok("noch kein Passwort", "Noch nicht festgelegt" in pg.inner_text("#sp-box"))
    pg.click("#sicherung-btn"); pg.wait_for_timeout(500)
    ok("Warnung ohne Passwort", "unverschlüsselt" in pg.inner_text("#sp-laden"))
    with pg.expect_download() as dl:
        pg.click("#sp-laden [data-l=ohne]")
    zip_ = dl.value.path().read_bytes()
    ok("ohne Passwort: ZIP wie bisher", zip_[:2] == b"PK" and dl.value.suggested_filename.endswith(".zip"))
    pg.click("#sp-box [data-sp-box]"); pg.wait_for_timeout(400)
    pg.fill("#sp-neu", "kurz"); pg.fill("#sp-neu2", "kurz"); pg.click("#sp-notiert"); pg.click("#sp-dialog [data-sp=speichern]"); pg.wait_for_timeout(400)
    ok("zu kurz abgelehnt", pg.locator("#sp-dialog").is_visible())
    pg.fill("#sp-neu", PW); pg.fill("#sp-neu2", PW)
    ok("Stärke sehr gut", "sehr gut" in pg.inner_text("#sp-staerke"))
    shot(pg, "#sp-dialog", "p1_festlegen")
    pg.click("#sp-dialog [data-sp=speichern]"); pg.wait_for_timeout(1500)
    ok("festgelegt", "verschlüsselt" in pg.inner_text("#sp-box") and api(pg, "sicherung")["gesetzt"])
    shot(pg, "#sicherung-btn >> xpath=ancestor::div[contains(@class,'card')]", "p2_karte")

    # ---------- verschlüsselt herunterladen ----------
    pg.click("#sicherung-btn"); pg.wait_for_timeout(500)
    pg.fill("#sp-eingabe", "falsch-falsch"); pg.click("#sp-laden [data-l=laden]"); pg.wait_for_timeout(800)
    ok("falsches Passwort", pg.locator("#sp-laden").is_visible() and "stimmt nicht" in pg.inner_text("#toast"))
    pg.fill("#sp-eingabe", PW)
    shot(pg, "#sp-laden", "p3_laden")
    with pg.expect_download() as dl:
        pg.click("#sp-laden [data-l=laden]")
    djos = dl.value.path().read_bytes()
    ok(f"verschlüsselt geladen: {dl.value.suggested_filename}", djos.startswith(b"DJOS-SICHERUNG") and dl.value.suggested_filename.endswith(".djos"))
    out = io.BytesIO(); verschluesselung.entschluesseln(io.BytesIO(djos), out, PW)
    ok("Inhalt: komplette Sicherung", "rechnungen.db" in zipfile.ZipFile(io.BytesIO(out.getvalue())).namelist())

    # ---------- verschlüsselt einspielen ----------
    vorher = len(api(pg, "rechnungen"))
    pg.evaluate("fetch('api/rechnungen', {method: 'POST', headers: {...SCHUTZ, 'Content-Type': 'application/json'}, body: JSON.stringify({nummer: '099', datum: '2026-11-20', kunde: {name: 'Test Weg', strasse: 'A 1', plz: '12345', ort: 'B'}, zahlungsbedingung: '8 Tage', positionen: [{beschreibung: 'DJ', lieferdatum: '2026-11-20', preis: 100}]})})")
    pg.wait_for_timeout(800)
    pg.set_input_files("#sicherung-datei", files=[{"name": dl.value.suggested_filename, "mimeType": "application/octet-stream", "buffer": djos}])
    pg.wait_for_timeout(1500)
    ok("Einspielen fragt nach Passwort", pg.locator("#sp-laden").is_visible() and "Entschlüsseln" in pg.inner_text("#sp-laden"))
    shot(pg, "#sp-laden", "p4_einspielen")
    pg.fill("#sp-eingabe", "falsch-falsch"); pg.click("#sp-laden [data-l=einspielen]"); pg.wait_for_timeout(1500)
    ok("falsches Passwort beim Einspielen", pg.locator("#sp-laden").is_visible())
    pg.fill("#sp-eingabe", PW)
    with pg.expect_navigation():
        pg.click("#sp-laden [data-l=einspielen]")
    pg.wait_for_timeout(2500)
    ok("eingespielt: 099 wieder weg", len(api(pg, "rechnungen")) == vorher)

    # ---------- Notiz zum Kunden ----------
    pg.evaluate("oeffneAkte('Lea Probe')"); pg.wait_for_timeout(1200)
    pg.fill("#ka-notiz", "mag keinen Schlager\nParken hinterm Haus")
    pg.click("#kundenakte [data-ka=notiz]"); pg.wait_for_timeout(800)
    ok("Notiz gespeichert", "gespeichert" in pg.inner_text("#ka-notiz-stand"))
    shot(pg, "#kundenakte", "p5_akte_notiz")
    pg.click("#kundenakte [data-ka=zu]")
    pg.evaluate("neueRechnung()"); pg.wait_for_timeout(1200)
    pg.fill("#k-name", "Lea"); pg.wait_for_timeout(700); pg.keyboard.press("ArrowDown"); pg.keyboard.press("Enter"); pg.wait_for_timeout(800)
    ok("Notiz im Editor", "Schlager" in pg.inner_text("#k-notiz") and pg.locator("#k-notiz").is_visible())
    ok("Privatkunde: E-Rechnung aus", not pg.is_checked("#r-erechnung"))

    # ---------- E-Rechnung ----------
    pg.fill("#k-name", ""); pg.evaluate("fillKunde({name: 'Sportverein Musterstadt e. V.', strasse: 'Sportplatz 1', plz: '12345', ort: 'Musterstadt'})")
    pg.wait_for_timeout(500)
    ok("Verein: E-Rechnung automatisch an", pg.is_checked("#r-erechnung") and not pg.locator("#k-notiz").is_visible())
    pos = pg.locator("#positionen .pos").first
    pos.locator(".tb").select_option(value="frei"); pos.locator(".beschreibung").fill("DJ – Tätigkeit Vereinsfeier – 19:00 Uhr bis 1:00 Uhr")
    pos.locator(".lieferdatum").fill("2026-11-21"); pos.locator(".preis").fill("700")
    shot(pg, "#tab-neu .grid2 .card >> nth=1", "p6_erechnung")
    pg.locator("#rechnung button[type=submit]").first.click(); pg.wait_for_timeout(1500)
    ok("ohne Steuernummer: klare Meldung", "Steuernummer" in pg.inner_text("#toast"))
    pg.evaluate("fetch('api/einstellungen', {method: 'PUT', headers: {...SCHUTZ, 'Content-Type': 'application/json'}, body: JSON.stringify({steuernummer: '12/345/67890', schon_verschickt: []})}).then(r => r.status)")
    pg.wait_for_timeout(600)
    ok("Steuernummer nachgetragen", api(pg, "einstellungen")["steuernummer"] == "12/345/67890")
    pg.locator("#rechnung button[type=submit]").first.click(); pg.wait_for_timeout(2500)
    pg.keyboard.press("Escape")
    r = [x for x in api(pg, "rechnungen") if x["kunde"]["name"].startswith("Sportverein")][-1]
    ok("E-Rechnung gespeichert", r["erechnung"])
    pdf = pg.evaluate(f"async () => Array.from(new Uint8Array(await (await fetch('api/rechnungen/{r['id']}/pdf')).arrayBuffer()))")
    xml = dict(erechnung.pdf_anhaenge(bytes(pdf))).get("factur-x.xml")
    ok("PDF enthält gültiges ZUGFeRD", bool(xml) and facturx.xml_check_xsd(xml, flavor="factur-x", level="en16931"))
    pg.evaluate("showTab('liste')"); pg.wait_for_timeout(1500)
    ok("Liste: E-Kennzeichen", pg.locator("#offen-body .e-chip, #liste-body .e-chip, .e-chip").count() >= 1)

    # ---------- Handy-Leiste ----------
    pg.set_viewport_size({"width": 390, "height": 844}); pg.evaluate("showTab('start')"); pg.wait_for_timeout(1500)
    ok("Handy: Leiste da, Menü oben weg", pg.locator(".unten-leiste").is_visible() and not pg.locator("header nav").is_visible())
    if ENGINE == "chromium": pg.screenshot(path=f"{B}/p7_handy_start.png")
    pg.click("[data-unten=finanzen]"); pg.wait_for_timeout(400)
    pg.locator(".unten-blatt [data-ziel=euer]").click(); pg.wait_for_timeout(1500)
    ok("EÜR über Leiste, Finanzen markiert", pg.locator("#tab-euer").is_visible() and "aktiv" in (pg.get_attribute("[data-unten=finanzen]", "class") or ""))
    pg.click("[data-unten=mehr]"); pg.wait_for_timeout(400)
    if ENGINE == "chromium": pg.screenshot(path=f"{B}/p8_handy_mehr.png")
    pg.locator(".unten-blatt [data-ziel=vertraege]").click(); pg.wait_for_timeout(1500)
    ok("Verträge über Mehr", pg.locator("#tab-vertraege").is_visible() and "aktiv" in (pg.get_attribute("[data-unten=mehr]", "class") or ""))
    pg.click("[data-unten=rechnungen]"); pg.wait_for_timeout(300)
    pg.locator(".unten-blatt [data-ziel=neu]").click(); pg.wait_for_timeout(1500)
    ok("Editor: Leiste über der Menüleiste", pg.evaluate("document.querySelector('#tab-neu .actions').getBoundingClientRect().bottom <= document.querySelector('.unten-leiste').getBoundingClientRect().top + 1"))
    if ENGINE == "chromium": pg.screenshot(path=f"{B}/p9_handy_editor.png")
    pg.click("#einstellungen-btn"); pg.wait_for_timeout(1200)
    ok("Einstellungen: keine Leisten-Markierung", not any("aktiv" in (x or "") for x in pg.locator(".unten-leiste button").evaluate_all("l => l.map(b => b.className)")))
    ok(f"keine Querscroll {pg.evaluate('document.documentElement.scrollWidth')}", pg.evaluate("document.documentElement.scrollWidth") <= 392)
    pg.set_viewport_size({"width": 1280, "height": 900}); pg.wait_for_timeout(400)
    ok("Computer: Menü oben, keine Leiste", not pg.locator(".unten-leiste").is_visible() and pg.locator("header nav").is_visible())

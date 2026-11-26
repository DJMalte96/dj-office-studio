"""Seit 1.16: Nachlass, Vertrag vor Ort unterschreiben, Kunden zusammenführen, Belege aus dem Postfach,
Einstellungen nach Themen, Handbuch in der App."""
SZENARIO = "116"


def lauf(pg, URL, ok, ENGINE, B, DATEIEN):
    api = lambda pfad: pg.evaluate(f"async () => (await fetch('api/{pfad}')).json()")   # noqa: E731

    def male(sel):
        box = pg.locator(sel).bounding_box()
        x, y = box["x"] + 30, box["y"] + 110
        pg.mouse.move(x, y); pg.mouse.down()
        for i in range(1, 40):
            pg.mouse.move(x + i * 6, y - 30 * ((i % 8) / 8) + (i % 3) * 4)
        pg.mouse.up()

    pg.goto(URL); pg.wait_for_timeout(2500)

    # ---------- Nachlass ----------
    pg.evaluate("neuesAngebot()"); pg.wait_for_timeout(1000)
    pg.evaluate("fillKunde({name: 'Lea Probe', strasse: 'Gartenstr. 8', plz: '12360', ort: 'Birkenfeld'})")
    pos = pg.locator("#positionen .pos").first
    pos.locator(".tb").select_option(value="frei"); pos.locator(".beschreibung").fill("DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr")
    pos.locator(".lieferdatum").evaluate("e => e.value = '2027-06-12'"); pos.locator(".preis").fill("1200")
    pg.click("#nl-add"); pg.wait_for_timeout(300)
    ok(f"Nachlass 10 %: {pg.inner_text('#gesamt')}", "1.080," in pg.inner_text("#gesamt") and not pg.locator("#positionen .pos.nachlass").is_visible())
    pg.fill("#nl-text", "Stammkundenrabatt"); pg.select_option("#nl-art", "betrag"); pg.fill("#nl-wert", "100"); pg.wait_for_timeout(300)
    ok(f"Nachlass 100 €: {pg.inner_text('#gesamt')}", "1.100," in pg.inner_text("#gesamt"))
    pg.locator("#rechnung button[type=submit]").first.click(); pg.wait_for_timeout(2500); pg.keyboard.press("Escape")
    a = max((x for x in api("angebote") if x["kunde"]["name"] == "Lea Probe"), key=lambda x: x["id"])
    nl = [p for p in a["positionen"] if p.get("nachlass")]
    ok("Angebot gespeichert: Nachlass vom Server berechnet", a["gesamt"] == 1100 and nl and nl[0]["preis"] == -100
       and nl[0]["beschreibung"] == "Stammkundenrabatt")
    pg.evaluate(f"api('angebote/{a['id']}').then(loadAngebotIntoForm)"); pg.wait_for_timeout(900)
    ok("wieder geöffnet: Nachlass-Zeile da", pg.input_value("#nl-wert") == "100" and pg.input_value("#nl-art") == "betrag")
    pg.click("#btn-neu"); pg.wait_for_timeout(600)
    ok("Formular leeren: Nachlass weg", pg.locator("#nl-add").is_visible())

    # ---------- Vertrag vor Ort unterschreiben ----------
    pg.evaluate("showTab('vertraege')"); pg.wait_for_timeout(1500)
    pg.locator("#vt-body tr", has_text="Carla").locator("[data-vt-act=unterschrieben]").click(); pg.wait_for_timeout(500)
    pg.check("#vt-unterschrift [value=hier]"); pg.click("#vtu-form button[type=submit]"); pg.wait_for_timeout(600)
    ok("Unterschrift-Fenster offen, Knopf noch gesperrt", pg.locator("#sign").is_visible() and pg.is_disabled("#sign-ok"))
    male("#sign canvas[data-pad='0']")
    ok("nach einer Unterschrift noch gesperrt", pg.is_disabled("#sign-ok"))
    male("#sign canvas[data-pad='1']"); pg.wait_for_timeout(200)
    pg.click("#sign-ok"); pg.wait_for_timeout(2500)
    v = [x for x in api("vertraege") if x["kunde"]["name"] == "Carla Test"][0]
    ok("Vertrag unterschrieben (auf dem Gerät)", v["status"] == "unterschrieben" and v["unterschrieben"]["weg"] == "hier")
    ok("Vorschau zeigt beide Unterschriften", pg.locator("#vt-papier .vt-unterschrift img").count() == 2
       and pg.evaluate("[...document.querySelectorAll('#vt-papier .vt-unterschrift img')].every(i => i.complete && i.naturalWidth > 0)"))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)

    # ---------- Kunden zusammenführen ----------
    pg.evaluate("document.querySelectorAll('dialog[open]').forEach(d => d.close()); showTab('kunden')"); pg.wait_for_timeout(2000)
    ok("Hinweis: 2 doppelt", "2 Kunden sind vermutlich doppelt" in pg.inner_text("#tab-kunden"))
    rechnungen_vorher = {r["id"]: r["kunde"]["name"] for r in api("rechnungen")}
    pg.click("#dup-oeffnen"); pg.wait_for_timeout(800)
    erst = pg.locator("#dup .dup-paar").first
    ok("Dialog: keine Rechnung geht verloren, Anna vorausgewählt", "Es geht keine Rechnung verloren" in pg.inner_text("#dup")
       and "Anna Muster" in erst.locator("input:checked").evaluate("i => i.closest('label').textContent"))
    erst.locator("[data-dup=ja]").click(); pg.wait_for_timeout(800)
    pg.locator("#dup .dup-paar").first.locator("[data-dup=nein]").click(); pg.wait_for_timeout(1200)
    namen = [k["name"] for k in api("kunden")]
    ok("Ana Muster zusammengeführt, Jonas bleibt doppelt (kein Duplikat)", "Ana Muster" not in namen and namen.count("Jonas Beispiel") == 2)
    ok("alle Rechnungen unverändert da", {r["id"]: r["kunde"]["name"] for r in api("rechnungen")} == rechnungen_vorher)
    pg.evaluate("oeffneAkte('Anna Muster')"); pg.wait_for_timeout(1200)
    ok("Kundenakte Anna enthält die Rechnung von „Ana Muster“", "032" in pg.inner_text("#kundenakte"))
    pg.click("#kundenakte [data-ka=zu]")

    # ---------- Einstellungen nach Themen, Postfach ----------
    pg.click("#einstellungen-btn"); pg.wait_for_timeout(1200)
    ok("7 Themen links", pg.locator(".eins-nav button").count() == 7)
    leer = pg.locator(".eins-gruppe").evaluate_all("l => l.filter(g => g.children.length < 2).map(g => g.dataset.gruppe)")
    ok(f"jedes Thema hat Inhalt {leer}", not leer)
    pg.click(".eins-nav [data-thema=mail]"); pg.wait_for_timeout(500)
    ok("E-Mail: Versand und Postfach", pg.locator("#mail-karte").is_visible() and pg.locator("#pf-karte").is_visible()
       and "imap.web.de" in pg.inner_text("#pf-karte"))
    pg.click("#pf-laden"); pg.wait_for_timeout(800)
    ok("Ordner geladen", pg.locator("#pf-ordnerliste option").count() == 3)
    pg.click("#pf-neu"); pg.locator("#pf-regeln [data-f=ordner]").last.fill("Geschäftlich/Belege/Technik")
    pg.click("#pf-neu"); pg.locator("#pf-regeln [data-f=ordner]").last.fill("Geschäftlich/Belege/Falsch")
    pg.click("#pf-pruefen"); pg.wait_for_timeout(1200)
    t = pg.inner_text("#pf-regeln")
    ok("Regeln prüfen: gefunden + nicht gefunden", "Ordner gefunden · 2 passende Mails" in t and "gibt es im Postfach nicht" in t)
    pg.locator("#pf-regeln [data-weg]").last.click()
    pg.locator("#einstellungen button[type=submit]").first.click(); pg.wait_for_timeout(1200)
    import json
    ok("Regeln gespeichert", len(json.loads(api("einstellungen")["postfach_regeln"])) == 2)
    pg.evaluate("showTab('ausgaben')"); pg.wait_for_timeout(1500)
    vorher = len(api("ausgaben"))
    pg.click("#pf-holen"); pg.wait_for_timeout(4000)
    ok(f"aus dem Postfach: {len(api('ausgaben')) - vorher} neu", len(api("ausgaben")) - vorher == 3)
    pg.click("#pf-holen"); pg.wait_for_timeout(2500)
    ok("zweites Mal: nichts doppelt", len(api("ausgaben")) - vorher == 3)

    # ---------- Handbuch ----------
    pg.click("#einstellungen-btn"); pg.wait_for_timeout(800)
    pg.click(".eins-nav [data-thema=app]"); pg.wait_for_timeout(300)
    pg.click("#handbuch-oeffnen"); pg.wait_for_timeout(1500)
    n = pg.locator("#hb-nav a").count()
    ok(f"Handbuch: {n} Abschnitte", n > 30)
    pg.evaluate("document.querySelectorAll('#hb-text img').forEach(i => i.loading = 'eager')"); pg.wait_for_timeout(1500)
    ok("Bilder geladen", pg.evaluate("[...document.querySelectorAll('#hb-text img')].every(i => i.complete && i.naturalWidth > 0)"))
    pg.locator("#hb-nav a[href='#daten--backup']").click(); pg.wait_for_timeout(500)
    ok("Abschnitt angesprungen", pg.evaluate("document.querySelector('#hb-text').scrollTop") > 1000)
    pg.fill("#hb-suche", "Sicherungs-Passwort"); pg.wait_for_timeout(900)
    ok("Suche markiert Treffer", pg.locator("#hb-text mark").count() > 0 and pg.locator("#hb-nav a:not(.weg)").count() < n)
    pg.click("#handbuch [data-hb=zu]")

    # ---------- Handy ----------
    pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(600)
    ok("Handy: Themen als Leiste oben", pg.locator(".eins-nav").evaluate("n => getComputedStyle(n).display") == "flex")
    ok(f"keine Querscroll {pg.evaluate('document.documentElement.scrollWidth')}", pg.evaluate("document.documentElement.scrollWidth") <= 392)

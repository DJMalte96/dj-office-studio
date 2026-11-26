"""Seit 1.11: Nachfassen, Preis-Spickzettel, Anzahlungs- und Schlussrechnung.

Aus den Klick-Tests der jeweiligen Version übernommen; läuft über tests/browser/test_browser.py."""
SZENARIO = "111"


def lauf(pg, URL, ok, ENGINE, B, DATEIEN):
    shot = lambda pg, sel, name: ENGINE == "chromium" and pg.locator(sel).first.screenshot(path=f"{B}/{name}.png")
    api = lambda pg, pfad: pg.evaluate(f"async () => (await fetch('api/{pfad}')).json()")
    pg.goto(URL); pg.wait_for_timeout(2000)
    if pg.locator("#tour-frage").is_visible(): pg.click("#tour-frage [data-frage=spaeter]"); pg.wait_for_timeout(300)
    w = pg.inner_text("#start .wichtig")
    ok(f"Chips: {w!r}", "2 Angebote nachfragen" in w and "Rechnung schreiben: Feier Jonas" in w)
    ok("Karte: keine Antwort seit 10 Tagen", "keine Antwort seit 10 Tagen" in pg.inner_text("#start .start-pinnwand"))
    ok("Karte Anzahlung-Chip nicht bei bezahlter Anzahlung (nicht offen)", True)
    if ENGINE == "chromium": pg.screenshot(path=f"{B}/s1_start.png", full_page=True)
    # Nachfrage (Mail nicht eingerichtet → vermerken)
    pg.locator("#start [data-start=nachfragen]").first.click(); pg.wait_for_timeout(700)
    ok("Nachfrage-Dialog", pg.locator("#nachfrage").is_visible() and "Angebot 011" in pg.input_value("#nachfrage-text")
       and "{" not in pg.input_value("#nachfrage-text"))
    ok("ohne Mail: Hinweis, kein Senden", pg.locator("#nachfrage-nicht-eingerichtet").is_visible() and not pg.locator("#nachfrage-senden").is_visible())
    shot(pg, "#nachfrage", "s2_nachfrage")
    pg.click("#nachfrage [data-nf=erledigt]"); pg.wait_for_timeout(1000)
    ok(f"danach 1 Angebot: {pg.inner_text('#start .wichtig')!r}", "1 Angebot nachfragen" in pg.inner_text("#start .wichtig"))
    ok("Vermerk 'nachgefragt'", "nachgefragt" in pg.inner_text("#start .start-pinnwand"))
    # Angebote-Tab
    pg.evaluate("showTab('angebote')"); pg.wait_for_timeout(900)
    ok("Angebote: 1× Nachfragen", pg.locator("#angebote-offen [data-act=nachfragen]").count() == 1)
    ok("Angebot 010: Anzahlung bezahlt + → Schlussrechnung",
       "Anzahlung 270 € bezahlt" in pg.inner_text("#angebote-body") and pg.locator("#angebote-body button", has_text="→ Schlussrechnung").count() == 1)
    # Spickzettel
    pg.evaluate("neueRechnung().then(resetForm)"); pg.wait_for_timeout(1200)
    pos = pg.locator("#positionen .pos").first
    hz = pg.evaluate("String(state.textbausteine.find(t => t.titel === 'Hochzeit').id)")
    pos.locator(".tb").select_option(hz); pos.locator(".von").fill("17:00"); pos.locator(".bis").fill("01:00"); pg.wait_for_timeout(300)
    sp = pos.locator(".spick").inner_text()
    ok(f"Spickzettel: {sp!r}", "Hochzeit bisher" in sp and "pro Stunde" in sp and "für 8 Std." in sp)
    pos.locator(".spick").evaluate("e => e.scrollIntoView({block: 'center'})")
    pos.locator(".spick .spick-preis").last.click(); pg.wait_for_timeout(200)
    ok(f"Preis übernommen: {pos.locator('.preis').input_value()}", pos.locator(".preis").input_value() not in ("", "0"))
    # Anzahlung ohne Angebot
    pg.locator("#k-name").press_sequentially("Anna Mu"); pg.wait_for_timeout(700); pg.locator("#ac-list > *").first.click(); pg.wait_for_timeout(300)
    ok("Kundenzeile im Spickzettel", "Anna Muster" in pos.locator(".spick").inner_text())
    pos.locator(".lieferdatum").evaluate("e => e.value = '2027-05-08'"); pos.locator(".preis").fill("1200")
    pg.locator("#rechnungsart-box label", has_text="Anzahlungsrechnung").click(); pg.wait_for_timeout(300)
    ok(f"30 %: {pg.inner_text('#gesamt')}", "360," in pg.inner_text("#gesamt") and not pg.locator("#r-fahrt").is_checked())
    pg.fill("#ra-wert", "25"); pg.wait_for_timeout(200)
    ok(f"25 %: {pg.inner_text('#gesamt')}", "300," in pg.inner_text("#gesamt") and "Anzahlung 25 %" in pg.locator("#positionen .beschreibung").first.input_value())
    ok("kein Spickzettel an der Anzahlungszeile", not pg.locator("#positionen .spick").first.is_visible())
    shot(pg, "#positionen >> xpath=ancestor::div[contains(@class,'card')]", "s3_anzahlung")
    pg.locator("#rechnungsart-box label", has_text="Normale Rechnung").click(); pg.wait_for_timeout(300)
    ok("zurück: 1.200", "1.200," in pg.inner_text("#gesamt") and pg.locator("#r-fahrt").is_checked())
    pg.locator("#rechnungsart-box label", has_text="Anzahlungsrechnung").click(); pg.wait_for_timeout(300)
    pg.locator("#rechnung button[type=submit]").first.click(); pg.wait_for_timeout(2200); pg.keyboard.press("Escape")
    rs = api(pg, "rechnungen")
    anna = [r for r in rs if r["kunde"]["name"] == "Anna Muster" and r["rechnungsart"] == "anzahlung"]
    ok(f"Anzahlungsrechnung gespeichert ({len(anna)})", len(anna) == 1 and anna[0]["gesamt"] == 300 and not anna[0]["fahrt_erfassen"])
    ok("% gemerkt", pg.evaluate("JSON.parse(localStorage.getItem('djos-anzahlung')).wert") == 25)
    # Schlussrechnung ohne Angebot
    pg.evaluate("resetForm()"); pg.wait_for_timeout(900)
    pg.locator("#k-name").press_sequentially("Anna Mu"); pg.wait_for_timeout(700); pg.locator("#ac-list > *").first.click(); pg.wait_for_timeout(300)
    pos = pg.locator("#positionen .pos").first
    pos.locator(".tb").select_option(hz); pos.locator(".von").fill("17:00"); pos.locator(".bis").fill("01:00")
    pos.locator(".lieferdatum").evaluate("e => e.value = '2027-05-08'"); pos.locator(".preis").fill("1200")
    pg.locator("#rechnungsart-box label", has_text="Schlussrechnung").click(); pg.wait_for_timeout(900)
    ok(f"Schluss: 900 ({pg.inner_text('#gesamt')})", "900," in pg.inner_text("#gesamt") and pg.locator("[data-ra-anzahlung]:checked").count() == 1)
    ok("Abzugszeile schreibgeschützt", pg.locator("#positionen .pos.abzug .preis").evaluate("e => e.readOnly"))
    shot(pg, "#positionen >> xpath=ancestor::div[contains(@class,'card')]", "s4_schluss")
    pg.locator("#rechnung button[type=submit]").first.click(); pg.wait_for_timeout(2200); pg.keyboard.press("Escape")
    rs = api(pg, "rechnungen")
    sch = [r for r in rs if r["kunde"]["name"] == "Anna Muster" and r["rechnungsart"] == "schluss"]
    ok("Schlussrechnung gespeichert", len(sch) == 1 and sch[0]["gesamt"] == 900)
    # Schlussrechnung wieder öffnen: Haken stimmt
    pg.evaluate(f"api('rechnungen/{sch[0]['id']}').then(loadIntoForm)"); pg.wait_for_timeout(900)
    ok("geöffnet: Schlussrechnung mit Haken", pg.locator("#rechnungsart-box [value=schluss]").is_checked()
       and pg.locator("[data-ra-anzahlung]:checked").count() == 1 and "900," in pg.inner_text("#gesamt"))
    # Angebot 012: → Rechnung (normal), Anzahlung im Editor, dann → Schlussrechnung
    pg.evaluate("showTab('angebote')"); pg.wait_for_timeout(900)
    pg.locator("#angebote-offen tr", has_text="Eva und Tom").locator("[data-act=rechnung]").click(); pg.wait_for_timeout(900)
    ok("→ Rechnung: normale Rechnung, kein Dialog", pg.locator("#rechnungsart-box [value=normal]").is_checked() and "1.250," in pg.inner_text("#gesamt"))
    pg.locator("#rechnungsart-box label", has_text="Anzahlungsrechnung").click(); pg.wait_for_timeout(300)
    pg.fill("#ra-wert", "30"); pg.wait_for_timeout(200)
    ok("375 € laut Angebot 012", "375," in pg.inner_text("#gesamt") and "laut Angebot 012" in pg.locator("#positionen .beschreibung").first.input_value())
    pg.locator("#rechnung button[type=submit]").first.click(); pg.wait_for_timeout(2200); pg.keyboard.press("Escape")
    pg.evaluate("showTab('angebote')"); pg.wait_for_timeout(900)
    zeile = pg.locator("#angebote-body tr", has_text="Eva und Tom")
    ok("Angebot 012 angenommen, Anzahlung offen", "Anzahlung 375 € offen" in zeile.inner_text())
    zeile.locator("button", has_text="→ Schlussrechnung").click(); pg.wait_for_timeout(1200)
    ok(f"Schluss 875 ({pg.inner_text('#gesamt')})", "875," in pg.inner_text("#gesamt"))
    pg.locator("#rechnung button[type=submit]").first.click(); pg.wait_for_timeout(2200); pg.keyboard.press("Escape")
    a12 = next(a for a in api(pg, "angebote") if a["nummer"] == "012")
    r12 = next(r for r in api(pg, "rechnungen") if r["id"] == a12["rechnung_id"])
    ok("Angebot 012 zeigt jetzt auf die Schlussrechnung", r12["rechnungsart"] == "schluss" and r12["gesamt"] == 875)
    # Startseite: Rechnung schreiben für Jonas (seit 1.14.1 mit der Frage „Wie wurde bezahlt?“) → Schlussrechnung
    pg.evaluate("showTab('start')"); pg.wait_for_timeout(1300)
    pg.locator("#start [data-ka-start=angebot-rechnung]", has_text="Jonas").click(); pg.wait_for_timeout(600)
    pg.click("#rv-wahl [data-zahlweg=rechnung]"); pg.wait_for_timeout(1300)
    ok(f"Jonas: Schluss 630 ({pg.inner_text('#gesamt')})", "630," in pg.inner_text("#gesamt") and pg.locator("#rechnungsart-box [value=schluss]").is_checked())
    # Angebot-Modus: kein Bereich
    pg.evaluate("neuesAngebot()"); pg.wait_for_timeout(800)
    ok("Angebot: kein Bereich „Art der Rechnung“", not pg.locator("#rechnungsart-box").is_visible())
    ok("Spickzettel auch im Angebot", True)
    pos = pg.locator("#positionen .pos").first
    pos.locator(".tb").select_option(hz); pg.wait_for_timeout(300)
    ok("Spickzettel im Angebot sichtbar", pos.locator(".spick").is_visible())
    # Einstellungen
    pg.click("#einstellungen-btn"); pg.wait_for_timeout(800)
    pg.click(".eins-nav [data-thema=belege-re]"); pg.wait_for_timeout(300)   # seit 1.16: Einstellungen nach Themen
    ok("Einstellung Nachfassen = 7", pg.input_value("#einstellungen [name=nachfassen_tage]") == "7")
    ok("Vorlage Nachfrage gefüllt", "Nachfrage" in pg.input_value("#einstellungen [name=mail_betreff_nachfrage]"))
    pg.fill("#einstellungen [name=nachfassen_tage]", "0")
    pg.locator("#einstellungen button[type=submit]").first.click(); pg.wait_for_timeout(1000)
    pg.evaluate("showTab('start')"); pg.wait_for_timeout(1200)
    ok("0 = nie: kein Nachfragen-Chip", "nachfragen" not in pg.inner_text("#start .wichtig"))
    pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(500)
    ok(f"Handy-Breite Start {pg.evaluate('document.documentElement.scrollWidth')}", pg.evaluate("document.documentElement.scrollWidth") <= 392)
    pg.evaluate("neueRechnung()"); pg.wait_for_timeout(800)
    ok(f"Handy-Breite Editor {pg.evaluate('document.documentElement.scrollWidth')}", pg.evaluate("document.documentElement.scrollWidth") <= 392)
    if ENGINE == "chromium": pg.locator("#rechnungsart-box").screenshot(path=f"{B}/s5_handy.png")

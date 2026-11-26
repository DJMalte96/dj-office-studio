"""Sicherheit: Alle Seiten und Dialoge öffnen, während jedes Textfeld Schadcode enthält (Szenario „xss“).
Fehler, wenn irgendein Code ausgeführt wird (__x), ein Dialog aufgeht oder die CSP etwas blockieren musste."""
SZENARIO = "xss"
INIT_SCRIPT = "window.__treffer = []; window.__x = f => window.__treffer.push(f);"
DIALOG = "fehler"     # ein alert/confirm aus Schadcode wäre ein Treffer


def lauf(pg, URL, ok, ENGINE, B, DATEIEN):
    probleme = []

    def schritt(name, js=None, klick=None, warte=900):
        try:
            pg.evaluate("document.querySelectorAll('dialog[open]').forEach(d => d.close())")
            if js:
                pg.evaluate(js)
            if klick:
                pg.locator(klick).first.click()
            pg.wait_for_timeout(warte)
        except Exception as e:   # noqa: BLE001
            probleme.append(f"{name}: {str(e)[:100]}")

    pg.goto(URL); pg.wait_for_timeout(2000)
    for tab in ("liste", "angebote", "finanzen", "ausgaben", "fahrten", "anschaffungen", "euer", "kunden", "textbausteine",
                "zahlungsbedingungen", "einstellungen", "vertraege", "vertragsvorlage", "start"):
        schritt(f"Seite {tab}", f"showTab('{tab}')")
    schritt("Rechnungseditor", "api('rechnungen/1').then(r => loadIntoForm({...r, festgeschrieben: false}))", warte=1300)
    pg.fill("#k-name", "kunde"); pg.wait_for_timeout(700)
    pg.keyboard.press("ArrowDown"); pg.keyboard.press("Enter"); pg.wait_for_timeout(700)     # Kunde mit Notiz übernehmen
    schritt("Angebot im Editor", "api('angebote/1').then(loadAngebotIntoForm)", warte=1200)
    schritt("Versand-Dialog Rechnung", "api('rechnungen/1').then(r => oeffneVersand('rechnung', r))", warte=1200)
    pg.keyboard.press("Escape")
    schritt("Nachfrage-Dialog", "oeffneNachfrage(state.angebote.find(a => a.id === 2) || state.angebote[0])", warte=1200)
    pg.keyboard.press("Escape")
    schritt("QR-Dialog", "api('rechnungen/1').then(oeffneQr)", warte=1000); pg.keyboard.press("Escape")
    schritt("Beleg-Dialog", "showTab('ausgaben'); api('ausgaben').then(l => oeffneBeleg(l.find(a => a.status === 'neu')?.id ?? l[0].id))", warte=1800)
    pg.keyboard.press("Escape")
    schritt("Abos-Dialog", "showTab('start'); showTab('ausgaben')", warte=900)
    pg.click("#abos-oeffnen"); pg.wait_for_timeout(900); pg.locator("[data-abos=bearbeiten]").first.click(); pg.wait_for_timeout(600)
    pg.keyboard.press("Escape")
    schritt("Papierkorb", "showTab('start'); showTab('ausgaben')", warte=900)
    pg.click("#papierkorb-oeffnen"); pg.wait_for_timeout(800); pg.keyboard.press("Escape")
    schritt("Vertrag 1", "oeffneVertrag(1)", warte=1500)
    schritt("Vertrag 2 (unterschrieben)", "oeffneVertrag(2)", warte=1500)
    schritt("Vertrag senden", "oeffneVersand('vertrag', vtState.aktuell)", warte=1200); pg.keyboard.press("Escape")
    schritt("Vertragsliste", "document.querySelector('#vertrag').close(); showTab('vertraege')", warte=1200)
    schritt("Neuer Vertrag – Auswahl", "neuerVertrag()", warte=1200); pg.keyboard.press("Escape")
    schritt("Vertragsvorlage", "showTab('vertragsvorlage')", warte=900)
    schritt("Vorlage aufklappen", "document.querySelectorAll('#vt-vorlage details').forEach(d => d.open = true)", warte=500)
    schritt("Unterschrift-Dialog", "oeffneUnterschrift(vtState.liste?.[0] || {id: 1, name: 'x'})", warte=600); pg.keyboard.press("Escape")
    # seit 1.14/1.15
    schritt("Kundenliste mit Akte-Links", "showTab('kunden')", warte=1200)
    schritt("Kundenakte (Notiz, Barzahlung)", "api('kunden').then(l => oeffneAkte(l[0].name))", warte=1500)
    schritt("Bar bezahlt (Angebot)", "api('angebote').then(l => oeffneBar({angebot: l[l.length - 1]}))", warte=900)
    schritt("Wie wurde bezahlt?", "api('angebote').then(l => zahlwegFragen({angebot: l[l.length - 1]}))", warte=700)
    schritt("Sicherungs-Dialoge", "showTab('einstellungen'); sicherungLaden()", warte=1200); pg.keyboard.press("Escape")
    schritt("Schnellsuche", "document.querySelector('#suche-knopf').click()", warte=1000)
    for q in ("kunde", "aus", "vt", "abo", "bar", "x"):
        pg.fill("#suche-eingabe", q); pg.wait_for_timeout(400)
    pg.keyboard.press("Escape")
    schritt("Rundgang", "document.querySelector('#rundgang-starten').click()", warte=600)
    for _ in range(13):
        try:
            pg.click(".tour-karte [data-tour=weiter]"); pg.wait_for_timeout(400)
        except Exception:   # noqa: BLE001
            break
    for tab in ("start", "angebote", "liste"):
        schritt(f"zuletzt {tab}", f"showTab('{tab}')", warte=1000)
    pg.set_viewport_size({"width": 390, "height": 844})
    schritt("Handy-Leiste: Mehr", None, "[data-unten=mehr]", warte=600)
    treffer = pg.evaluate("window.__treffer")
    ok(f"kein Schadcode ausgeführt ({len(treffer)} Treffer: {sorted(set(treffer))[:5]})", not treffer)
    ok(f"alle Schritte durchlaufen ({probleme[:3]})", not probleme)

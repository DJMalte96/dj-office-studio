"""Browser-Tests (seit 1.15): Klick-Abläufe in Chrome (Chromium) und Safari (WebKit) mit Prüfung der CSP.

Laufen nur, wenn eingeschaltet – sie brauchen Playwright samt Browsern und dauern ein paar Minuten:
    pip install playwright pytest && python -m playwright install chromium webkit
    DJOS_BROWSERTESTS=1 pytest tests/browser
In GitHub Actions laufen sie bei jedem Push (.github/workflows/tests.yml, Job „browser“).
Jede Suite startet ihren eigenen Server mit erfundenen Daten (tests/browser/server.py).
"""
import importlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parents[1] / "rechnungen" / "app"))

if not os.environ.get("DJOS_BROWSERTESTS"):
    pytest.skip("Browser-Tests nur mit DJOS_BROWSERTESTS=1", allow_module_level=True)
sync_api = pytest.importorskip("playwright.sync_api")

SUITEN = ["suite_anzahlungen", "suite_rundgang", "suite_vertraege", "suite_kundenakte", "suite_sicherung", "suite_xss"]
BROWSER = [b for b in os.environ.get("DJOS_BROWSER", "chromium,webkit").split(",") if b]


@pytest.fixture(scope="module")
def playwright():
    with sync_api.sync_playwright() as pw:
        yield pw


def _server(szenario):
    p = subprocess.Popen([sys.executable, "-u", str(HIER / "server.py"), szenario], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    ende = time.time() + 120
    for zeile in p.stdout:
        if zeile.startswith("BEREIT"):
            return p, zeile.split()[1]
        if time.time() > ende:
            break
    p.kill()
    raise RuntimeError(f"Testserver {szenario} startet nicht")


@pytest.mark.parametrize("engine", BROWSER)
@pytest.mark.parametrize("name", SUITEN)
def test_browser(playwright, engine, name):
    suite = importlib.import_module(name)
    server, url = _server(suite.SZENARIO)
    fehler, schritte = [], []

    def ok(text, bedingung):
        schritte.append(("✓" if bedingung else "✗", text))
        if not bedingung:
            fehler.append(text)

    browser = getattr(playwright, engine).launch()
    try:
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="de-DE", accept_downloads=True)
        pg = ctx.new_page()
        if getattr(suite, "INIT_SCRIPT", None):
            pg.add_init_script(suite.INIT_SCRIPT)
        pg.on("pageerror", lambda e: fehler.append(f"JS-Fehler: {e}"))
        # Konsolenfehler zählen (CSP-Verstöße!), außer gewollten Antworten 400 (Eingabe abgelehnt)
        pg.on("console", lambda m: m.type == "error" and "400" not in m.text and fehler.append(f"Konsole: {m.text[:200]}"))
        if getattr(suite, "DIALOG", "accept") == "fehler":
            pg.on("dialog", lambda d: (fehler.append(f"Dialog: {d.message[:80]}"), d.dismiss()))
        else:
            pg.on("dialog", lambda d: d.accept())
        with tempfile.TemporaryDirectory() as bilder:
            suite.lauf(pg, url, ok, engine, bilder, str(HIER / "dateien"))
    finally:
        browser.close()
        server.kill()
    bericht = "\n".join(f"  {z} {t}" for z, t in schritte)
    assert not fehler, f"{name} in {engine}:\n" + "\n".join(dict.fromkeys(fehler)) + f"\n\nAblauf:\n{bericht}"

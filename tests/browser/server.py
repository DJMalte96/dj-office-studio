"""Testserver mit erfundenen Daten für die Browser-Tests (tests/browser). Nur Beispieldaten – keine echten Personen.

Aufruf: python tests/browser/server.py <szenario>   (leer | basis | 111 | 114 | xss)
Druckt „BEREIT <url>“, sobald der Server läuft; beendet sich, wenn der Test-Prozess ihn beendet.
"""
import io
import json
import os
import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
tmp = tempfile.mkdtemp()
os.environ.update(DATA_DIR=tmp, OPTIONS_PATH=os.path.join(tmp, "o.json"))
sys.path.insert(0, str(ROOT / "rechnungen" / "app"))
import db  # noqa: E402
import finanzen  # noqa: E402
import main  # noqa: E402

finanzen.HINTERGRUND = False
db.init()
c = main.app.test_client()
c.environ_base["HTTP_X_DJOS"] = "1"
h = date.today()
d = lambda n: (h + timedelta(days=n)).isoformat()  # noqa: E731


def basis():
    """Absender, Rechnungen 2024–2026, Ausgaben, eine Kauf-Mail, Fahrten."""
    global KUNDEN
    db.save_settings({"_uebernommen": True, "_hinweis_bestaetigt": 99, "name": "Max Beispiel", "strasse": "Musterweg 1",
                      "plz_ort": "12345 Musterstadt", "ort_fuer_datum": "Musterstadt", "iban": "DE02120300000000202051", "bic": "BYLADEM1001",
                      "kleinunternehmer": True, "_letzte_sicherung": "2026-11-20T10:00:00",
                      "pdf_ordner": os.path.join(tmp, "pdf"), "belege_ordner": os.path.join(tmp, "eingang")})
    c = main.app.test_client(); c.environ_base["HTTP_X_DJOS"] = "1"
    KUNDEN = [("Anna Muster", "Lindenweg 12", "12345", "Musterstadt"), ("Jonas Beispiel", "Am Hang 3", "12350", "Lindenau"),
              ("Lea Probe", "Gartenstr. 8", "12360", "Birkenfeld"), ("Tim Erfunden", "Hauptstr. 21", "12370", "Eichdorf")]
    def rechnung(nr, datum, preis, bezahlt_am=None, k=0, was="DJ – Hochzeit"):
        kn = dict(zip(("name", "strasse", "plz", "ort"), KUNDEN[k % 4]))
        r = c.post("/api/rechnungen", json={"nummer": nr, "datum": datum, "kunde": kn, "zahlungsbedingung": "Bitte innerhalb von 8 Tagen überweisen.",
                   "fahrt_erfassen": False, "positionen": [{"beschreibung": was, "lieferdatum": datum, "preis": preis}]}).get_json()
        if bezahlt_am:
            c.patch(f"/api/rechnungen/{r['id']}/bezahlt", json={"bezahlt": True})
            c.put(f"/api/rechnungen/{r['id']}/bezahlt_am", json={"bezahlt_am": bezahlt_am})
        return r["id"]
    n = 1
    for jahr, liste in ((2024, [("03-09", 750), ("05-18", 1100), ("07-06", 950), ("09-14", 1200), ("12-31", 600)]),
                        (2025, [("02-15", 650), ("04-26", 1150), ("05-31", 980), ("06-21", 1300), ("08-09", 1250), ("09-13", 900), ("10-04", 1050), ("12-31", 800)]),
                        (2026, [("03-14", 700), ("05-09", 1200), ("06-13", 1350), ("08-22", 1100), ("11-14", 950)])):
        for i, (md, p) in enumerate(liste):
            d = f"{jahr}-{md}"
            bez = None if (jahr == 2025 and md in ("10-04",)) or (jahr == 2026 and md == "11-14") else (f"{jahr + 1}-01-04" if md == "12-31" else d)
            rechnung(f"{n:03d}", d, p, bez, k=i, was=["DJ – Hochzeit", "DJ – Geburtstag", "DJ – Firmenfeier"][i % 3]); n += 1
    for d, l, b, k, besch in (("2025-01-20", "Musikhaus Klangwerk", 1190, "anschaffung", "Controller"), ("2025-03-02", "Kabelwelt", 89.9, "technik", "Kabel und Adapter"),
                              ("2025-06-11", "Plattenladen Groove", 64.5, "musik", "Platten"), ("2025-11-28", "Versicherung Beispiel AG", 180, "versicherung", "Haftpflicht 2025"),
                              ("2025-12-30", "Mobilfunk Muster", 29.99, "telefon", "Handyvertrag Dezember"), ("2024-05-02", "Lichtladen", 449, "technik", "LED-Bar"),
                              ("2026-02-03", "Kabelwelt", 39.9, "technik", "Ersatzkabel")):
        c.post("/api/ausgaben", json={"belegdatum": d, "lieferant": l, "betrag": b, "kategorie": k, "beschreibung": besch, "notiz": "Beleg per Post"})
    mails = ROOT / "tests" / "beispiele" / "mails"
    c.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO((mails / "beatport.eml").read_bytes()), "beatport.eml")]}, content_type="multipart/form-data")
    for d, z, km in (("2025-04-26", "Am Hang 3, 12350 Lindenau", 31), ("2025-06-21", "Gartenstr. 8, 12360 Birkenfeld", 44), ("2025-09-13", "Hauptstr. 21, 12370 Eichdorf", 18)):
        c.post("/api/fahrten", json={"datum": d, "ziel": z, "km_einfach": km})
    c.post("/api/fahrten", json={"datum": "2025-08-09", "ziel": "Lindenweg 12, 12345 Musterstadt"})


def szenario_111():
    """Seit 1.11: Nachfassen, Spickzettel, Anzahlungen (auf Basis)."""
    import abschluss
    abschluss.jahre_festhalten()
    h = date.today()
    d = lambda n: (h + timedelta(days=n)).isoformat()
    T = lambda anlass, von, bis: f"DJ – Tätigkeit {anlass} – {von} Uhr bis {bis} Uhr"
    KD = {k[0]: dict(zip(("name", "strasse", "plz", "ort"), k)) for k in KUNDEN}
    K = {"Sportverein Musterstadt e. V.": {"name": "Sportverein Musterstadt e. V.", "strasse": "Sportplatz 1", "plz": "12345", "ort": "Musterstadt"},
         "Eva und Tom Probe": {"name": "Eva und Tom Probe", "strasse": "Birkenallee 7", "plz": "12346", "ort": "Beispielhausen"},
         "Carla Test": {"name": "Carla Test", "strasse": "Rosenstr. 8", "plz": "12347", "ort": "Testdorf"}} | KD

    # Rechnungen mit Uhrzeiten – Futter für den Preis-Spickzettel
    def rechnung(nr, datum, kunde, text, preis, bezahlt=True, angebot_id=None, art="normal"):
        r = c.post("/api/rechnungen", json={"nummer": nr, "datum": datum, "kunde": K[kunde], "zahlungsbedingung": "Bitte innerhalb von 8 Tagen überweisen.",
                   "fahrt_erfassen": False, "angebot_id": angebot_id, "rechnungsart": art,
                   "positionen": [{"beschreibung": text, "lieferdatum": datum, "preis": preis}]}).get_json()
        if bezahlt:
            c.patch(f"/api/rechnungen/{r['id']}/bezahlt", json={"bezahlt": True})
            c.put(f"/api/rechnungen/{r['id']}/bezahlt_am", json={"bezahlt_am": bezahlt if isinstance(bezahlt, str) else datum})
        return r["id"]
    for nr, (datum, kunde, text, preis) in enumerate((
            ("2025-07-12", "Lea Probe", T("Hochzeit", "16:00", "1:00"), 1250),
            ("2026-04-18", "Tim Erfunden", T("Hochzeit", "17:00", "2:00"), 1300),
            ("2026-09-19", "Lea Probe", T("Hochzeit", "18:00", "2:00"), 1200),
            ("2026-03-21", "Anna Muster", T("Geburtstagsfeier", "20:00", "1:00"), 550),
            ("2026-10-10", "Jonas Beispiel", T("Geburtstagsfeier", "19:00", "1:00"), 600),
            ("2026-10-24", "Tim Erfunden", T("Firmenfeier", "19:00", "0:00"), 800)), 19):
        rechnung(f"{nr:03d}", datum, kunde, text, preis)

    # Angebote
    def angebot(nr, datum, gueltig, kunde, text, fest, preis, gesendet=None):
        a = c.post("/api/angebote", json={"nummer": nr, "datum": datum, "gueltig_bis": gueltig, "kunde": K[kunde],
                                          "positionen": [{"beschreibung": text, "lieferdatum": fest, "preis": preis}]}).get_json()
        if gesendet:
            vid = db.add_versand("angebot", a["id"], gesendet[1], f"Ihr Angebot {nr}")
            with db.connect() as con:
                con.execute("UPDATE versand SET zeitpunkt = ? WHERE id = ?", (f"{gesendet[0]} 18:12:00", vid))
        return a["id"]
    a10 = angebot("010", d(-45), d(-15), "Jonas Beispiel", T("Firmenfeier", "19:00", "1:00"), d(-2), 900, (d(-45), "jonas.beispiel@example.com"))
    angebot("011", d(-10), d(20), "Sportverein Musterstadt e. V.", T("Firmenfeier", "19:00", "1:00"), d(75), 700, (d(-10), "vorstand@sportverein-muster.example"))
    angebot("012", d(-3), d(27), "Eva und Tom Probe", T("Hochzeit", "17:00", "2:00"), d(200), 1250, (d(-3), "eva.probe@example.com"))
    angebot("013", d(-8), d(22), "Anna Muster", T("Geburtstagsfeier", "20:00", "1:00"), d(45), 600)
    angebot("014", d(-40), d(-10), "Carla Test", T("Geburtstagsfeier", "19:00", "0:00"), d(30), 550, (d(-40), "carla.test@example.com"))
    # angenommenes Angebot 010 mit bezahlter Anzahlung, Feier war vorgestern → Schlussrechnung fehlt
    rechnung("025", d(-30), "Jonas Beispiel", f"Anzahlung 30 % für DJ – Tätigkeit Firmenfeier am {date.fromisoformat(d(-2)).strftime('%d.%m.%Y')} laut Angebot 010",
             270, bezahlt=d(-26), angebot_id=a10, art="anzahlung")
    with db.connect() as con:
        for name, mail in (("Eva und Tom Probe", "eva.probe@example.com"), ("Sportverein Musterstadt e. V.", "vorstand@sportverein-muster.example"),
                           ("Anna Muster", "anna.muster@example.com"), ("Jonas Beispiel", "jonas.beispiel@example.com")):
            con.execute("UPDATE kunden SET email = ? WHERE name = ?", (mail, name))
    for f in c.get("/api/fahrten?jahr=2025").get_json()["fahrten"]:
        if f["km_einfach"] is None: c.put(f"/api/fahrten/{f['id']}", json={"km_einfach": 6})
    db.save_settings({"_letzte_sicherung": f"{d(-5)}T19:42:00", "telefon": "0170/1234567", "bank_name": "Sparkasse Musterstadt"})

    return locals()


def szenario_114():
    """Seit 1.14: Verträge, Bar bezahlt, Stammkunde, angenommene Angebote (auf 1.11)."""
    g = szenario_111()
    K, T, angebot, rechnung, d = g["K"], g["T"], g["angebot"], g["rechnung"], g["d"]
    # --- seit 1.14: Verträge, Stammkunde ---
    db.save_settings({"_rundgang_anbieten": False})
    ang = {a["nummer"]: a["id"] for a in c.get("/api/angebote").get_json()}
    def vertrag(angebot, weg="mail", zahlung=None):
        v = c.post("/api/vertraege", json={"angebot_id": ang[angebot]}).get_json()["vertrag"]["id"]
        if zahlung:
            c.put(f"/api/vertraege/{v}", json={"felder": zahlung})
        c.post(f"/api/vertraege/{v}/unterschrieben", data={"weg": weg, "am": d(-20)}, content_type="multipart/form-data")
        return v
    vertrag("010")                                         # Jonas: Feier vorgestern, Anzahlung 025 bezahlt → Schlussrechnung
    vertrag("012", zahlung={"zahlung": "rechnung", "anzahlung": 30})   # Eva und Tom: Anzahlung noch anfordern
    # Sportverein: Weihnachtsfeier vor knapp einem Jahr → Jahres-Erinnerung
    K["Musikverein Beispiel"] = {"name": "Musikverein Beispiel", "strasse": "Am Markt 4", "plz": "12349", "ort": "Neustadt"}
    rechnung("030", d(-345), "Musikverein Beispiel", T("Firmenfeier", "19:00", "1:00"), 700)
    rechnung("031", d(-710), "Musikverein Beispiel", T("Firmenfeier", "19:00", "0:00"), 650)
    # 1.14.1: angenommene Angebote ohne Vertrag – Feier vor 5 Tagen (Erinnerung) und vor 200 Tagen (still)
    for nr, kunde, tage in (("015", "Anna Muster", -5), ("016", "Lea Probe", -200)):
        aid = angebot(nr, d(tage - 30), d(tage), kunde, T("Geburtstagsfeier", "20:00", "1:00"), d(tage), 600)
        c.patch(f"/api/angebote/{aid}/status", json={"status": "angenommen"})


def szenario_xss():
    """Jedes Textfeld enthält Schadcode; löst er im Browser aus, ruft er __x('<feld>') auf."""
    def X(feld):
        """Payload für Text-, Attribut- und Skript-Kontext."""
        return f"{feld}\"'><img src=x onerror=__x('{feld}')><svg onload=__x('{feld}')>`${{__x('{feld}')}}`</script><script>__x('{feld}')</script>"


    c = main.app.test_client(); c.environ_base["HTTP_X_DJOS"] = "1"
    h = date.today()
    d = lambda n: (h + timedelta(days=n)).isoformat()
    ok = lambda r, n="": (r.status_code < 300) or print("SEED-FEHLER", n, r.status_code, r.get_data(as_text=True)[:200])
    db.save_settings({"_uebernommen": True, "_hinweis_bestaetigt": 99, "_rundgang_anbieten": False,
                      "name": X("einst_name"), "strasse": X("einst_strasse"), "plz_ort": "12345 " + X("einst_ort"), "telefon": X("einst_telefon"),
                      "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": X("einst_bank"), "kontoinhaber": X("einst_inhaber"),
                      "ort_fuer_datum": X("einst_ortdatum"), "steuernummer": X("einst_stnr"), "kleinunternehmer": True,
                      "mail_betreff_rechnung": X("vorlage_betreff"), "mail_text_rechnung": X("vorlage_text"), "_letzte_sicherung": f"{d(-40)}T10:00:00",
                      "pdf_ordner": os.path.join(tmp, "pdf"), "sicherung_kopie_ordner": X("kopie_ordner")})
    K = {"name": X("kunde_name"), "zusatz": X("kunde_zusatz"), "strasse": X("kunde_strasse"), "plz": "12345", "ort": X("kunde_ort")}
    ok(c.post("/api/textbausteine", json={"titel": X("tb_titel"), "text": X("tb_text") + " {von} Uhr bis {bis} Uhr"}), "tb")
    ok(c.post("/api/zahlungsbedingungen", json={"titel": X("zb_titel"), "text": X("zb_text") + " innerhalb von 8 Tagen"}), "zb")
    pos = lambda f, n=0: [{"beschreibung": X(f), "lieferdatum": d(n), "preis": 500}]
    r = c.post("/api/rechnungen", json={"nummer": "001", "datum": d(-30), "kunde": K, "zahlungsbedingung": X("re_zahlung") + " 8 Tage",
                                       "veranstaltungsort": {"name": X("re_ortname"), "strasse": X("re_ortstr"), "plz": "1", "ort": X("re_ortort")},
                                       "positionen": pos("re_pos", -30)}); ok(r, "re1")
    r1 = r.get_json()["id"]
    c.post(f"/api/rechnungen/{r1}/mahnung")
    r = c.post("/api/rechnungen", json={"nummer": "002", "datum": d(-20), "kunde": K, "zahlungsbedingung": "8 Tage", "positionen": pos("re2_pos", -20)}); ok(r)
    r2 = r.get_json()["id"]
    c.patch(f"/api/rechnungen/{r2}/bezahlt", json={"bezahlt": True})
    c.post(f"/api/rechnungen/{r2}/stornieren")
    a = c.post("/api/angebote", json={"nummer": "010", "datum": d(-12), "gueltig_bis": d(20), "kunde": K, "hinweise": X("ang_hinweise"),
                                      "positionen": pos("ang_pos", 40)}); ok(a, "ang")
    aid = a.get_json()["id"]
    c.post(f"/api/angebote/{aid}/nachgefragt", json={"wie": X("ang_nachgefragt_wie")})
    c.post("/api/angebote", json={"nummer": "011", "datum": d(-12), "gueltig_bis": d(20), "kunde": K, "positionen": pos("ang2_pos", 50)}).get_json()["id"]
    for i, f in enumerate(("aus_lieferant", "aus_beschreibung")):
        ok(c.post("/api/ausgaben", json={"belegdatum": d(-5 - i), "lieferant": X("aus_lieferant"), "betrag": 12.5, "kategorie": "technik",
                                         "beschreibung": X("aus_beschreibung"), "notiz": X("aus_notiz")}), "aus")
    # Beleg mit Schad-Dateiname (wird „neu – bitte prüfen“)
    ok(c.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(b"Rechnung\nSumme 12,00 EUR\n"), X("beleg_dateiname") + ".txt")]},
              content_type="multipart/form-data"), "beleg")
    ok(c.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(b"From: " + X("mail_von").encode() + b"\nSubject: " + X("mail_betreff").encode()
                                                        + b"\n\nGesamt 9,99 EUR"), "kauf.eml")]}, content_type="multipart/form-data"), "eml")
    ok(c.post("/api/fahrten", json={"datum": d(-3), "ziel": X("fahrt_ziel"), "km_einfach": 10}), "fahrt")
    ok(c.post("/api/anlagen", json={"bezeichnung": X("anlage_bez"), "anschaffung_am": d(-60), "kosten": 1500, "nutzungsdauer": 3}), "anlage")
    ok(c.post("/api/einnahmen", json={"datum": d(-2), "beschreibung": X("einnahme_beschr"), "betrag": "50"}), "einnahme")
    ok(c.post("/api/abos", json={"lieferant": X("abo_lieferant"), "beschreibung": X("abo_beschr"), "betrag": "9,99", "rhythmus": "monatlich", "tag": 1,
                                 "beginn": d(-40), "kategorie": "musik", "nachtragen": True}), "abo")
    v = c.post("/api/vertraege", json={"angebot_id": aid}).get_json()["vertrag"]["id"]
    ok(c.put(f"/api/vertraege/{v}", json={"anlass": X("vt_anlass"), "felder": {"kontakt": X("vt_kontakt"), "verpflegung": X("vt_verpflegung")}}), "vt")
    vl = c.get("/api/vertragsvorlage").get_json()["abschnitte"]
    vl.append({"titel": X("vorlage_titel"), "text": X("vorlage_abschnitt") + " {veranstalter}", "an": True})
    vl.append({"titel": X("vorlage_import"), "text": "Text", "an": True, "herkunft": X("vorlage_herkunft")})
    ok(c.put("/api/vertragsvorlage/abschnitte", json={"abschnitte": vl}), "vorlage")
    ok(c.post("/api/vertragsvorlage/anlagen", data={"datei": (io.BytesIO(b"%PDF-1.4 x"), X("anlage_name") + ".pdf")}, content_type="multipart/form-data"), "anlage_vt")
    v2 = c.post("/api/vertraege", json={}).get_json()["vertrag"]["id"]
    c.put(f"/api/vertraege/{v2}", json={"kunde": K, "anlass": "Feier", "datum": d(30), "gage": 500})
    ok(c.post(f"/api/vertraege/{v2}/unterschrieben", data={"weg": "datei", "am": d(0), "notiz": X("vtu_notiz"),
                                                          "datei": (io.BytesIO(b"%PDF-1.4"), "vtu_datei<img src=x onerror=__x(1)>.pdf")}, content_type="multipart/form-data"), "vtu")
    # seit 1.14/1.15: Barzahlung, Notiz zum Kunden
    ok(c.post("/api/barzahlungen", data={"betrag": "300", "datum": d(-1), "quittung_nr": X("bar_nr")[:40], "anlass": X("bar_anlass"),
                                         "kunde": json.dumps(K)}, content_type="multipart/form-data"), "bar")
    kid = next(k["id"] for k in c.get("/api/kunden").get_json() if k["name"] == K["name"])
    ok(c.put(f"/api/kunden/{kid}/notiz", json={"notiz": X("kunde_notiz")}), "notiz")


if __name__ == "__main__":
    szenario = sys.argv[1] if len(sys.argv) > 1 else "basis"
    if szenario == "basis":
        basis()
    elif szenario == "111":
        basis(); szenario_111()
    elif szenario == "114":
        basis(); szenario_114()
    elif szenario == "xss":
        szenario_xss()
    from waitress import create_server
    srv = create_server(main.app, host="127.0.0.1", port=0, threads=4)
    threading.Thread(target=srv.run, daemon=True).start()
    print("BEREIT", f"http://127.0.0.1:{srv.effective_port}/", flush=True)
    threading.Event().wait()

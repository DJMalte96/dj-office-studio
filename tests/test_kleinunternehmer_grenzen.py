"""Finanzen – Kleinunternehmer-Grenzen (§ 19 UStG seit 2025): 25.000 € im Vorjahr, 100.000 € im laufenden Jahr."""
from datetime import date

from test_euer import rechnung


def grenzen(client, jahr=2026, heute=date(2026, 11, 21)):
    import finanzen
    return finanzen.kleinunternehmer_grenzen(jahr, heute=heute)


def texte(g, stufe):
    return " | ".join(h["text"] for h in g["hinweise"] if h["stufe"] == stufe)


def test_unter_den_grenzen(client):
    rechnung(client, "001", "2025-06-01", 8000, bezahlt_am="2025-06-10")
    rechnung(client, "002", "2026-05-01", 960, bezahlt_am="2026-05-10")
    g = grenzen(client)
    assert (g["umsatz"], g["vorjahr"], g["stufe"]) == (960.0, 8000.0, "ok") and not g["gruendungsjahr"]
    e = client.get("/api/finanzen/euer?jahr=2026").get_json()
    assert e["grenzen"]["umsatz"] == 960.0 and not any(p["aktion"] == "grenzen" for p in e["pruefliste"])


def test_vorjahr_ueber_25000(client):
    rechnung(client, "001", "2025-03-01", 26000, bezahlt_am="2025-03-20")
    g = grenzen(client)
    assert g["stufe"] == "rot" and "für 2026 nicht" in texte(g, "rot")
    e = client.get("/api/finanzen/euer?jahr=2026").get_json()                 # auch in der Prüfliste der EÜR
    assert any(p["aktion"] == "grenzen" and "25.000" in p["text"] for p in e["pruefliste"])


def test_laufendes_jahr_ueber_25000_gilt_fuers_naechste_jahr(client):
    rechnung(client, "001", "2025-03-01", 1000, bezahlt_am="2025-03-20")
    rechnung(client, "002", "2026-03-01", 20000, bezahlt_am="2026-03-20")
    rechnung(client, "003", "2026-09-01", 6000, bezahlt_am="2026-09-05")
    g = grenzen(client)
    assert g["umsatz"] == 26000.0 and g["stufe"] == "gelb" and "Für 2027 gilt" in texte(g, "gelb")


def test_offene_rechnungen_und_storno(client):
    rechnung(client, "001", "2025-03-01", 1000, bezahlt_am="2025-03-20")
    rechnung(client, "002", "2026-03-01", 22000, bezahlt_am="2026-03-20")
    rechnung(client, "003", "2026-10-01", 4000)                               # offen
    g = grenzen(client)
    assert g["offen"] == 4000.0 and "offenen Rechnungen" in texte(g, "gelb")
    storno = rechnung(client, "004", "2026-04-01", 3000, bezahlt_am="2026-04-10")
    client.post(f"/api/rechnungen/{storno}/stornieren")                       # bezahlt und erstattet → zählt nicht
    assert grenzen(client)["umsatz"] == 22000.0


def test_ueber_100000_mit_datum(client):
    rechnung(client, "001", "2025-03-01", 1000, bezahlt_am="2025-03-20")
    rechnung(client, "002", "2026-02-01", 90000, bezahlt_am="2026-02-15")
    rechnung(client, "003", "2026-07-01", 15000, bezahlt_am="2026-07-04")
    g = grenzen(client)
    assert g["ueber_100_am"] == "2026-07-04" and "Seit 04.07.2026" in texte(g, "rot")


def test_gruendungsjahr_und_hochrechnung(client):
    rechnung(client, "001", "2026-02-01", 26000, bezahlt_am="2026-02-15")     # keine Rechnungen vor 2026
    g = grenzen(client)
    assert g["gruendungsjahr"] and "Gründungsjahr" in texte(g, "gelb")
    # Hochrechnung: 11.000 € bis Ende Mai → rund 26.600 € im Jahr → Hinweis (nur Info, weil geschätzt)
    rechnung(client, "002", "2025-12-01", 100, bezahlt_am="2025-12-05")
    import db
    with db.connect() as con:
        con.execute("DELETE FROM rechnungen WHERE nummer = '001'")
    rechnung(client, "003", "2026-04-01", 11000, bezahlt_am="2026-04-10")
    g = grenzen(client, heute=date(2026, 5, 31))
    assert g["hochrechnung"] and g["hochrechnung"] > 25000 and "Hochrechnung" in texte(g, "info")
    assert grenzen(client, heute=date(2026, 2, 1))["hochrechnung"] is None   # zu früh im Jahr für eine Hochrechnung


def test_nicht_fuer_umsatzsteuerpflichtige(client):
    client.put("/api/einstellungen", json={"kleinunternehmer": False, "steuernummer": "1"})
    rechnung(client, "001", "2026-03-01", 30000, bezahlt_am="2026-03-20")
    assert grenzen(client) is None
    assert client.get("/api/finanzen/euer?jahr=2026").get_json()["grenzen"] is None

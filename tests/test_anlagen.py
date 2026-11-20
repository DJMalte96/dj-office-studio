"""Finanzen – Anschaffungen: Abschreibung (linear, anteilig), Übernahme aus Vorjahren, Abgang, Verknüpfung mit Ausgaben."""
import pytest

import finanzen


@pytest.mark.parametrize("anlage, jahr, afa, ende", [
    ({"anschaffung_am": "2026-03-12", "kosten": 2380, "nutzungsdauer": 7}, 2026, 283.33, 2096.67),   # 10 von 12 Monaten
    ({"anschaffung_am": "2026-03-12", "kosten": 2380, "nutzungsdauer": 7}, 2027, 340.00, 1756.67),
    ({"anschaffung_am": "2026-03-12", "kosten": 2380, "nutzungsdauer": 7}, 2033, 56.67, 0.0),        # Rest im letzten Jahr
    ({"anschaffung_am": "2024-06-05", "kosten": 1290, "nutzungsdauer": 7}, 2026, 184.29, 813.92),
    ({"anschaffung_am": "2025-01-20", "kosten": 1499, "nutzungsdauer": 1}, 2025, 1499.0, 0.0),       # Computer: voll im Kaufjahr
    ({"restwert_start": 1000, "start_jahr": 2026, "rest_nutzungsdauer": 4}, 2027, 250.0, 500.0),     # aus Vorjahren übernommen
])
def test_abschreibung(anlage, jahr, afa, ende):
    w = finanzen.anlage_im_jahr(anlage, jahr)
    assert (w["afa"], w["restwert_ende"]) == (afa, ende)
    assert round(sum(b for _, b, _ in finanzen.afa_plan(anlage)), 2) == anlage.get("kosten", anlage.get("restwert_start"))


def test_abgang_mitten_im_jahr():
    a = {"anschaffung_am": "2026-03-12", "kosten": 2380, "nutzungsdauer": 7, "abgang_am": "2028-06-15", "abgang_erloes": 900}
    w = finanzen.anlage_im_jahr(a, 2028)
    assert (w["afa"], w["abgang_restwert"], w["abgang_erloes"], w["restwert_ende"]) == (170.0, 1586.67, 900.0, 0.0)
    assert finanzen.anlage_im_jahr(a, 2029)["afa"] == 0


def test_nutzungsdauer_vorschlag():
    assert finanzen.nutzungsdauer_vorschlag("MacBook Pro 14") == 1
    assert finanzen.nutzungsdauer_vorschlag("Aktivboxen (Paar)") == 7


def test_anlagen_api_und_jahr(client):
    r = client.post("/api/anlagen", json={"bezeichnung": "DJ-Controller", "anschaffung_am": "2024-06-05", "kosten": "1.290,00", "nutzungsdauer": 7})
    assert r.status_code == 201 and r.get_json()["kosten"] == 1290.0
    assert client.post("/api/anlagen", json={"bezeichnung": "x"}).status_code == 400
    assert client.post("/api/anlagen", json={"bezeichnung": "Alt", "restwert_start": 500}).status_code == 400   # Jahr fehlt
    liste = client.get("/api/anlagen?jahr=2026").get_json()
    assert [(a["bezeichnung"], a["afa"], a["restwert_anfang"], a["restwert_ende"]) for a in liste] == [("DJ-Controller", 184.29, 998.21, 813.92)]
    assert client.get("/api/anlagen?jahr=2023").get_json() == []          # vor dem Kauf nicht im Verzeichnis
    aid = liste[0]["id"]
    r = client.put(f"/api/anlagen/{aid}", json={"abgang_am": "2024-01-01"})
    assert r.status_code == 400 and "vor dem Kauf" in r.get_json()["error"]
    assert client.delete(f"/api/anlagen/{aid}").status_code == 204


def test_ausgabe_anschaffung_landet_im_verzeichnis(client):
    basis = {"belegdatum": "2026-03-12", "lieferant": "Musterhaus", "beschreibung": "Aktivboxen (Paar)", "betrag": 2380,
             "kategorie": "anschaffung", "notiz": "Beleg folgt"}
    aus = client.post("/api/ausgaben", json=basis).get_json()
    anl = client.get("/api/anlagen?jahr=2026").get_json()
    assert len(anl) == 1 and anl[0]["ausgabe_id"] == aus["id"] and anl[0]["nutzungsdauer"] == 7 and anl[0]["afa"] == 283.33
    assert client.delete(f"/api/anlagen/{anl[0]['id']}").status_code == 409            # nur über die Ausgabe änderbar
    # Kategorie geändert → Gerät verschwindet wieder
    client.put(f"/api/ausgaben/{aus['id']}", json={"kategorie": "technik"})
    assert client.get("/api/anlagen?jahr=2026").get_json() == []


def test_umsatzsteuerpflichtige_schreiben_netto_ab(client):
    client.put("/api/einstellungen", json={"kleinunternehmer": False, "steuernummer": "1"})
    client.post("/api/ausgaben", json={"belegdatum": "2026-01-10", "lieferant": "Shop", "beschreibung": "Laptop",
                                       "betrag": 1190, "ust_satz": 19, "kategorie": "anschaffung", "notiz": "x"})
    a = client.get("/api/anlagen?jahr=2026").get_json()[0]
    assert a["kosten"] == 1000.0 and a["nutzungsdauer"] == 1 and a["afa"] == 1000.0

"""Finanzen – Fahrten: automatisch je Rechnung, Veranstaltungsort, abwählen, korrigieren, von Hand, nachberechnen."""
import pytest

from conftest import KUNDE

ZB = "Bitte innerhalb der nächsten 8 Tage überweisen."
ORT = {"name": "Hof Lindenhof", "strasse": "Feldweg 3", "plz": "12350", "ort": "Lindenau"}


@pytest.fixture
def karte(app_modul, client, monkeypatch):
    """Kartendienst eingeschaltet, aber nachgebaut: km nach Ziel-PLZ, Aufrufe werden mitgezählt."""
    import finanzen
    import strecken
    aufrufe = []

    def km(start, ziel, ssl_kontext=None):
        aufrufe.append((start, ziel))
        if "99999" in ziel:
            raise strecken.StreckenFehler("Adresse nicht gefunden: " + ziel)
        return {"12350": 31.0, "12345": 4.2}.get(ziel.split(", ")[-1].split()[0], 18.0)

    monkeypatch.setattr(strecken, "strecke_km", km)
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    client.put("/api/einstellungen", json={"kartendienst": True})
    return aufrufe


def rechnung(client, nummer="037", ort=None, **extra):
    r = client.post("/api/rechnungen", json={"nummer": nummer, "datum": "2026-11-01", "kunde": KUNDE, "zahlungsbedingung": ZB,
                                             "veranstaltungsort": ort, "positionen": [
                                                 {"beschreibung": "DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr",
                                                  "lieferdatum": "2026-10-31", "preis": 960}], **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def fahrten(client, jahr=2026):
    return client.get(f"/api/fahrten?jahr={jahr}").get_json()


def test_fahrt_zur_rechnung_mit_veranstaltungsort(client, karte):
    inv = rechnung(client, ort=ORT)
    f = fahrten(client)["fahrten"]
    assert len(f) == 1 and f[0]["rechnung_id"] == inv and f[0]["datum"] == "2026-10-31" and f[0]["quelle"] == "auto"
    assert f[0]["ziel"] == "Feldweg 3, 12350 Lindenau" and f[0]["start"] == "Musterweg 1, 12345 Musterstadt"
    assert (f[0]["km_einfach"], f[0]["km_gesamt"], f[0]["betrag"]) == (31.0, 62.0, 18.6)
    assert client.get(f"/api/rechnungen/{inv}").get_json()["veranstaltungsort"] == ORT


def test_ohne_ort_wird_kundenadresse_genommen(client, karte):
    rechnung(client)
    assert fahrten(client)["fahrten"][0]["ziel"] == "Lindenweg 12, 12345 Musterstadt"


def test_fahrt_abwaehlen_und_loeschen(client, karte):
    inv = rechnung(client, fahrt_erfassen=False)
    d = fahrten(client)
    assert d["fahrten"] == [] and [x["nummer"] for x in d["ohne_fahrt"]] == ["037"]
    # wieder einschalten → Fahrt entsteht
    daten = client.get(f"/api/rechnungen/{inv}").get_json()
    client.put(f"/api/rechnungen/{inv}", json=daten | {"fahrt_erfassen": True})
    fid = fahrten(client)["fahrten"][0]["id"]
    # Fahrt in der Liste löschen → schaltet „Fahrt erfassen“ der Rechnung aus, auch erneutes Speichern legt keine an
    assert client.delete(f"/api/fahrten/{fid}").status_code == 204
    daten = client.get(f"/api/rechnungen/{inv}").get_json()
    assert daten["fahrt_erfassen"] is False
    client.put(f"/api/rechnungen/{inv}", json=daten)
    assert fahrten(client)["fahrten"] == []


def test_korrektur_bleibt_beim_speichern(client, karte):
    inv = rechnung(client, ort=ORT)
    fid = fahrten(client)["fahrten"][0]["id"]
    r = client.put(f"/api/fahrten/{fid}", json={"km_einfach": "33,5"}).get_json()
    assert r["quelle"] == "korrigiert" and r["km_einfach"] == 33.5
    daten = client.get(f"/api/rechnungen/{inv}").get_json()
    client.put(f"/api/rechnungen/{inv}", json=daten)
    assert fahrten(client)["fahrten"][0]["km_einfach"] == 33.5


def test_ziel_geaendert_wird_neu_berechnet(client, karte):
    inv = rechnung(client)
    assert fahrten(client)["fahrten"][0]["km_einfach"] == 4.2
    daten = client.get(f"/api/rechnungen/{inv}").get_json()
    client.put(f"/api/rechnungen/{inv}", json=daten | {"veranstaltungsort": ORT})
    assert fahrten(client)["fahrten"][0]["km_einfach"] == 31.0


def test_von_hand_und_fehler_und_rechnung_loeschen(client, karte):
    inv = rechnung(client, ort=ORT)
    r = client.post("/api/fahrten", json={"datum": "2026-10-30", "anlass": "Aufbau am Vortag", "ziel": "Feldweg 3, 12350 Lindenau",
                                          "rechnung_id": inv})
    assert r.status_code == 201 and r.get_json()["km_einfach"] == 31.0 and r.get_json()["quelle"] == "hand"
    r = client.post("/api/fahrten", json={"datum": "2026-10-29", "ziel": "Nirgendwo 1, 99999 Unbekannt"}).get_json()
    assert r["km_einfach"] is None and "nicht gefunden" in r["fehler"]
    assert client.post("/api/fahrten", json={"datum": "", "ziel": "x"}).status_code == 400
    # Rechnung löschen: automatische Fahrt weg, von Hand ergänzte bleibt (ohne Bezug)
    client.delete(f"/api/rechnungen/{inv}")
    rest = fahrten(client)["fahrten"]
    assert sorted(f["quelle"] for f in rest) == ["hand", "hand"] and all(f["rechnung_id"] is None for f in rest)


def test_storno_hat_keine_eigene_fahrt(client, karte):
    inv = rechnung(client)
    client.post(f"/api/rechnungen/{inv}/festschreiben")
    client.post(f"/api/rechnungen/{inv}/stornieren")
    f = fahrten(client)["fahrten"]
    assert len(f) == 1 and f[0]["rechnung_storniert"] is True


def test_nachberechnen_fuer_alte_rechnungen(client, app_modul, monkeypatch):
    import finanzen
    import strecken
    rechnung(client, "037")          # Kartendienst aus → Fahrt ohne km
    assert fahrten(client)["fahrten"][0]["km_einfach"] is None
    import db
    with db.connect() as con:          # z. B. importierte alte Rechnung ohne Fahrt
        con.execute("DELETE FROM fahrten")
    monkeypatch.setattr(strecken, "strecke_km", lambda s, z, ssl_kontext=None: 18.0)
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    client.put("/api/einstellungen", json={"kartendienst": True})
    r = client.post("/api/fahrten/nachberechnen", json={"jahr": 2026}).get_json()
    assert r["angelegt"] == 1 and fahrten(client)["fahrten"][0]["km_einfach"] == 18.0


def test_ohne_kartendienst_keine_anfrage(client, app_modul, monkeypatch):
    import strecken
    monkeypatch.setattr(strecken, "strecke_km", lambda *a, **k: pytest.fail("Kartendienst darf nicht gefragt werden"))
    rechnung(client, ort=ORT)
    assert fahrten(client)["fahrten"][0]["km_einfach"] is None
    assert "km_einfach" not in client.get("/api/fahrten/vorschau?strasse=Feldweg 3&plz=12350&ort=Lindenau").get_json()


def test_vorschau_und_einstellungen(client, karte):
    v = client.get("/api/fahrten/vorschau?strasse=Feldweg 3&plz=12350&ort=Lindenau").get_json()
    assert (v["km_einfach"], v["km_gesamt"], v["betrag"]) == (31.0, 62.0, 18.6)
    assert client.put("/api/einstellungen", json={"km_satz": "0,35"}).status_code == 200
    assert client.get("/api/einstellungen").get_json()["km_satz"] == 0.35
    assert client.put("/api/einstellungen", json={"km_satz": "abc"}).status_code == 400
    assert client.put("/api/einstellungen", json={"fahrzeug": "fahrrad"}).status_code == 400


def test_veranstaltungsort_auf_pdf(client):
    from conftest import pdf_text
    inv = rechnung(client, ort=ORT)
    ohne = rechnung(client, "038")
    text = " ".join(pdf_text(client.get(f"/api/rechnungen/{inv}/pdf").data).split())
    assert "Veranstaltungsort: Hof Lindenhof, Feldweg 3, 12350 Lindenau" in text
    assert "Veranstaltungsort" not in pdf_text(client.get(f"/api/rechnungen/{ohne}/pdf").data)
    a = client.post("/api/angebote", json={"nummer": "010", "datum": "2026-11-01", "kunde": KUNDE, "veranstaltungsort": ORT,
                                           "positionen": [{"beschreibung": "DJ", "preis": 500}]}).get_json()["id"]
    assert client.get(f"/api/angebote/{a}").get_json()["veranstaltungsort"] == ORT
    assert "Veranstaltungsort: Hof Lindenhof" in " ".join(pdf_text(client.get(f"/api/angebote/{a}/pdf").data).split())


def test_offene_fahrten_werden_beim_oeffnen_berechnet(client, monkeypatch):
    """Kartendienst nachträglich eingeschaltet bzw. App neu gestartet: Die Liste stößt die Berechnung selbst an."""
    import finanzen
    import strecken
    rechnung(client, "037")                               # Kartendienst aus → Fahrt ohne km
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    monkeypatch.setattr(strecken, "strecke_km", lambda s, z, ssl_kontext=None: 21.5)
    client.put("/api/einstellungen", json={"kartendienst": True})
    assert fahrten(client)["fahrten"][0]["km_einfach"] == 21.5


def test_unerwarteter_fehler_beendet_berechnung_nicht_lautlos(client, monkeypatch):
    import finanzen
    import strecken
    rechnung(client, "037")
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    monkeypatch.setattr(strecken, "strecke_km", lambda *a, **k: {}["kaputt"])
    client.put("/api/einstellungen", json={"kartendienst": True})
    f = fahrten(client)["fahrten"][0]
    assert f["km_einfach"] is None and "KeyError" in f["fehler"]   # → „km fehlen“ statt ewig „wird berechnet …“

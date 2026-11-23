"""1.9.0 Abos: Termine je Rhythmus, fällige Abbuchungen, bestätigen/aussetzen, Beleg erkennen, Preisänderung, 10-Tage-Regel,
Zusammenspiel mit dem Jahresabschluss."""
import io
from datetime import date, timedelta

import pytest

HEUTE = date.today()
H = HEUTE.isoformat()
Y = HEUTE.year - 1


def abo(client, **w):
    d = {"lieferant": "Musikpool Beispiel", "beschreibung": "DJ-Musikpool (Monatsabo)", "kategorie": "musik", "betrag": "19,99",
         "rhythmus": "monatlich", "tag": 1, "beginn": f"{Y}-01-01"} | w
    r = client.post("/api/abos", json=d)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def faellig(client, abo_id=None):
    return [f for f in client.get("/api/abos/faellig").get_json() if abo_id is None or f["abo_id"] == abo_id]


def euer(client, jahr):
    return client.get(f"/api/finanzen/euer?jahr={jahr}").get_json()


# ---------- Termine ----------

@pytest.mark.parametrize("w, erwartet", [
    ({"rhythmus": "monatlich", "tag": 31, "beginn": "2025-01-31"}, ["2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30"]),
    ({"rhythmus": "monatlich", "tag": 31, "beginn": "2024-01-31"}, ["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30"]),
    ({"rhythmus": "monatlich", "tag": 1, "beginn": "2025-03-20"}, ["2025-04-01", "2025-05-01", "2025-06-01", "2025-07-01"]),
    ({"rhythmus": "zweimonatlich", "tag": 5, "beginn": "2025-01-05"}, ["2025-01-05", "2025-03-05", "2025-05-05", "2025-07-05"]),
    ({"rhythmus": "vierteljaehrlich", "tag": 15, "beginn": "2025-11-15"}, ["2025-11-15", "2026-02-15", "2026-05-15", "2026-08-15"]),
    ({"rhythmus": "halbjaehrlich", "tag": 1, "beginn": "2025-01-01"}, ["2025-01-01", "2025-07-01", "2026-01-01", "2026-07-01"]),
    ({"rhythmus": "jaehrlich", "tag": 29, "beginn": "2024-02-29"}, ["2024-02-29", "2025-02-28", "2026-02-28", "2027-02-28"]),
    ({"rhythmus": "zweijaehrlich", "tag": 15, "beginn": "2024-12-15"}, ["2024-12-15", "2026-12-15", "2028-12-15", "2030-12-15"]),
    ({"rhythmus": "woechentlich", "beginn": "2025-12-25"}, ["2025-12-25", "2026-01-01", "2026-01-08", "2026-01-15"]),
    ({"rhythmus": "vierwochen", "beginn": "2026-10-01"}, ["2026-10-01", "2026-10-29", "2026-11-26", "2026-12-24"]),
    ({"rhythmus": "eigen", "anzahl": 18, "einheit": "monate", "tag": 5, "beginn": "2025-11-05"}, ["2025-11-05", "2027-05-05", "2028-11-05", "2030-05-05"]),
    ({"rhythmus": "eigen", "anzahl": 6, "einheit": "wochen", "beginn": "2026-01-02"}, ["2026-01-02", "2026-02-13", "2026-03-27", "2026-05-08"]),
    ({"rhythmus": "eigen", "anzahl": 3, "einheit": "jahre", "tag": 1, "beginn": "2025-06-01"}, ["2025-06-01", "2028-06-01", "2031-06-01", "2034-06-01"]),
    ({"rhythmus": "monatlich", "tag": 1, "beginn": "2025-01-01", "ende": "2025-03-15"}, ["2025-01-01", "2025-02-01", "2025-03-01"]),
])
def test_termine(app_modul, w, erwartet):
    import abos
    a = {"anzahl": 1, "einheit": "monate", "tag": None, "ende": None} | w
    assert abos.termine(a, "2099-12-31")[:4] == erwartet


def test_rhythmus_namen_und_kosten_im_monat(client):
    for rhythmus, extra, name, monat in [("monatlich", {}, "monatlich", 12.0), ("jaehrlich", {}, "jährlich", 1.0),
                                         ("vierwochen", {}, "alle 4 Wochen", 13.0), ("woechentlich", {}, "wöchentlich", 52.0),
                                         ("eigen", {"anzahl": 18, "einheit": "monate"}, "alle 18 Monate", 0.67),
                                         ("eigen", {"anzahl": 1, "einheit": "wochen"}, "jede Woche", 52.0)]:
        a = abo(client, lieferant=f"Test {rhythmus}{extra.get('anzahl', '')}", betrag="12", rhythmus=rhythmus, **extra)
        assert a["rhythmus_name"] == name and a["pro_monat"] == monat, (rhythmus, a)


@pytest.mark.parametrize("w, fehler", [
    ({"lieferant": " "}, "Lieferanten"), ({"betrag": "0"}, "Betrag"), ({"betrag": "abc"}, "Betrag"), ({"rhythmus": "taeglich"}, "Rhythmus"),
    ({"tag": 32}, "Tag"), ({"beginn": "31.12.2025"}, "Beginn"), ({"beginn": "2025-02-30"}, "Datum"), ({"ende": "2024-01-01"}, "Ende"),
    ({"kategorie": "anschaffung"}, "Kategorie"), ({"privatanteil": 120}, "Privatanteil"),
    ({"rhythmus": "eigen", "anzahl": 0}, "Zahl"), ({"rhythmus": "eigen", "einheit": "tage"}, "Einheit"),
])
def test_eingaben_werden_geprueft(client, w, fehler):
    d = {"lieferant": "X Pool", "betrag": "9,99", "beginn": f"{Y}-01-01"} | w
    r = client.post("/api/abos", json=d)
    assert r.status_code == 400 and fehler in r.get_json()["error"], r.get_json()


# ---------- Fällig, bestätigen, aussetzen ----------

def test_fruehere_abbuchungen_nur_auf_wunsch(client):
    ohne = abo(client, beginn=f"{Y}-01-01")
    assert all(f["datum"] >= H for f in faellig(client, ohne["id"]))
    mit = abo(client, lieferant="Software Beispiel", beginn=f"{Y}-01-15", tag=15, nachtragen=True)
    termine = [f["datum"] for f in faellig(client, mit["id"])]
    assert termine[0] == f"{Y}-01-15" and termine[-1] <= H and len(termine) >= 12


def test_bestaetigen_bucht_eine_ausgabe(client):
    a = abo(client, beginn=f"{Y}-03-01", nachtragen=True, privatanteil=10)
    f = faellig(client, a["id"])[0]
    vorher = euer(client, Y)["ausgaben"]
    r = client.post(f"/api/abos/{a['id']}/termine/{f['datum']}", json={"aktion": "ok"})
    assert r.status_code == 201
    x = r.get_json()
    assert (x["status"], x["betrag"], x["kategorie"], x["abo_id"], x["privatanteil"]) == ("ok", 19.99, "musik", a["id"], 10)
    assert x["beschreibung"] == f"DJ-Musikpool (Monatsabo) – März {Y}" and "Beleg fehlt" in x["notiz"]
    assert round(euer(client, Y)["ausgaben"] - vorher, 2) == round(19.99 * 0.9, 2)
    assert f["datum"] not in [g["datum"] for g in faellig(client, a["id"])]
    # doppelt geht nicht, ein Tag ohne Abbuchung auch nicht
    assert client.post(f"/api/abos/{a['id']}/termine/{f['datum']}", json={"aktion": "ok"}).status_code == 409
    assert client.post(f"/api/abos/{a['id']}/termine/{Y}-03-02", json={"aktion": "ok"}).status_code == 409
    assert client.post(f"/api/abos/{a['id']}/termine/{HEUTE.year + 1}-01-01", json={"aktion": "ok"}).status_code == 409


def test_aussetzen_bucht_nichts(client):
    a = abo(client, beginn=f"{Y}-03-01", nachtragen=True)
    f = faellig(client, a["id"])[0]
    vorher = euer(client, Y)["ausgaben"]
    assert client.post(f"/api/abos/{a['id']}/termine/{f['datum']}", json={"aktion": "aus"}).status_code == 204
    assert euer(client, Y)["ausgaben"] == vorher and f["datum"] not in [g["datum"] for g in faellig(client, a["id"])]


def test_betrag_nur_diesmal_oder_ab_jetzt(client):
    a = abo(client, beginn=f"{Y}-01-01", nachtragen=True)
    t = [f["datum"] for f in faellig(client, a["id"])]
    assert client.post(f"/api/abos/{a['id']}/termine/{t[0]}", json={"aktion": "ok", "betrag": "22,50"}).get_json()["betrag"] == 22.5
    assert faellig(client, a["id"])[0]["betrag"] == 19.99               # nur diesmal
    assert client.post(f"/api/abos/{a['id']}/termine/{t[1]}", json={"aktion": "ok", "betrag": "24,99", "ab_jetzt": True}).status_code == 201
    assert faellig(client, a["id"])[0]["betrag"] == 24.99               # ab jetzt immer
    liste = client.get("/api/abos").get_json()["abos"][0]
    assert liste["betrag_aktuell"] == 24.99 and liste["preise"][0]["ab"] == t[1]


def test_preisaenderung_im_abo_wirkt_nicht_zurueck(client):
    a = abo(client, beginn=f"{Y}-01-01", nachtragen=True)
    t = faellig(client, a["id"])[0]["datum"]
    client.put(f"/api/abos/{a['id']}", json={"betrag": "29,99"})
    assert faellig(client, a["id"])[0]["betrag"] == 19.99 and client.get("/api/abos").get_json()["abos"][0]["betrag_aktuell"] == 29.99
    client.post(f"/api/abos/{a['id']}/termine/{t}", json={"aktion": "ok"})
    assert client.get(f"/api/ausgaben?jahr={Y}").get_json()[0]["betrag"] == 19.99


def test_kuendigen_und_loeschen(client):
    a = abo(client, beginn=f"{Y}-01-01", nachtragen=True)
    t = faellig(client, a["id"])
    client.post(f"/api/abos/{a['id']}/termine/{t[0]['datum']}", json={"aktion": "ok"})
    r = client.put(f"/api/abos/{a['id']}", json={"ende": f"{Y}-03-31"}).get_json()
    assert r["beendet"] and r["pro_monat"] == 0 and r["naechste"] is None
    assert [f["datum"] for f in faellig(client, a["id"])] == [f"{Y}-02-01", f"{Y}-03-01"]
    assert client.delete(f"/api/abos/{a['id']}").status_code == 204
    aus = client.get(f"/api/ausgaben?jahr={Y}").get_json()
    assert len(aus) == 1 and aus[0]["abo_id"] is None                    # gebuchte Ausgabe bleibt
    assert faellig(client) == [] and client.delete(f"/api/abos/{a['id']}").status_code == 404


# ---------- Beleg erkennen, nichts doppelt ----------

def _mail(lieferant, betrag, datum):
    return (f"From: {lieferant} <rechnung@pool.example>\nTo: max@example.com\nSubject: Deine Rechnung\n"
            f"Date: {date.fromisoformat(datum).strftime('%a, %d %b %Y')} 08:00:00 +0100\nMIME-Version: 1.0\n"
            f"Content-Type: text/plain; charset=utf-8\n\nRechnung\nRechnungsdatum: {date.fromisoformat(datum):%d.%m.%Y}\n"
            f"Gesamtbetrag: {betrag} EUR\n").encode()


def test_beleg_wird_erkannt_und_zur_ausgabe(client):
    a = abo(client, beginn=f"{Y}-11-01", nachtragen=True)
    neu = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(_mail("Musikpool Beispiel", "19,99", f"{Y}-11-03")), "r.eml")]},
                      content_type="multipart/form-data").get_json()["neu"][0]
    f = next(x for x in faellig(client, a["id"]) if x["datum"] == f"{Y}-11-01")
    assert f["beleg"]["id"] == neu["id"] and f["vorhanden"] is None
    # anderer Monat/Betrag passt nicht
    assert all(x["beleg"] is None for x in faellig(client, a["id"]) if x["datum"] != f"{Y}-11-01")
    x = client.post(f"/api/abos/{a['id']}/termine/{f['datum']}", json={"aktion": "ok", "beleg_id": neu["id"]}).get_json()
    assert x["id"] == neu["id"] and x["status"] == "ok" and x["beleg_datei"] and x["bezahlt_am"] == f"{Y}-11-01"
    assert x["kategorie"] == "musik" and x["abo_id"] == a["id"]
    aus = client.get(f"/api/ausgaben?jahr={Y}").get_json()
    assert [y["id"] for y in aus if y["lieferant"] == "Musikpool Beispiel"] == [neu["id"]]     # genau eine Ausgabe
    # derselbe Beleg kann nicht noch einmal verwendet werden
    t2 = next(x for x in faellig(client, a["id"]))["datum"]
    assert client.post(f"/api/abos/{a['id']}/termine/{t2}", json={"aktion": "ok", "beleg_id": neu["id"]}).status_code == 409


def test_schon_erfasste_ausgabe_wird_verknuepft(client):
    a = abo(client, beginn=f"{Y}-05-01", nachtragen=True)
    von_hand = client.post("/api/ausgaben", json={"belegdatum": f"{Y}-05-02", "lieferant": "Musikpool Beispiel GmbH", "betrag": 19.99,
                                                  "kategorie": "musik", "beschreibung": "Mai", "notiz": "x"}).get_json()
    f = next(x for x in faellig(client, a["id"]) if x["datum"] == f"{Y}-05-01")
    assert f["vorhanden"]["id"] == von_hand["id"]
    vorher = euer(client, Y)["ausgaben"]
    client.post(f"/api/abos/{a['id']}/termine/{f['datum']}", json={"aktion": "ok", "ausgabe_id": von_hand["id"]})
    assert euer(client, Y)["ausgaben"] == vorher                              # nicht doppelt
    assert client.get(f"/api/ausgaben/{von_hand['id']}").get_json()["abo_id"] == a["id"]


# ---------- 10-Tage-Regel ----------

def test_zehn_tage_regel_automatisch(client):
    a = abo(client, lieferant="Software Beispiel", beginn=f"{Y}-12-30", tag=30, nachtragen=True, betrag="9,99")
    f = faellig(client, a["id"])[0]
    assert f["datum"] == f"{Y}-12-30" and f["zehn_tage"] == Y + 1
    vorher, folge = euer(client, Y)["ausgaben"], euer(client, Y + 1)["ausgaben"]
    x = client.post(f"/api/abos/{a['id']}/termine/{f['datum']}", json={"aktion": "ok"}).get_json()
    assert x["jahr"] == str(Y + 1) and euer(client, Y)["ausgaben"] == vorher
    assert round(euer(client, Y + 1)["ausgaben"] - folge, 2) == 9.99
    # im Jahresabschluss keine gelbe 10-Tage-Frage für Abos
    p = client.get(f"/api/abschluss/{Y}/pruefung").get_json()
    assert not any(x.get("art") == "zehn_tage" for x in p["punkte"])
    w = abo(client, lieferant="Wochen Pool", rhythmus="woechentlich", beginn=f"{Y}-12-23", nachtragen=True)
    assert faellig(client, w["id"])[0]["zehn_tage"] is None                  # Wochen-Abo: bleibt im Jahr


# ---------- Jahresabschluss ----------

def test_jahresabschluss_wartet_auf_abos(client, monkeypatch):
    import abschluss
    monkeypatch.setattr(abschluss, "abschliessbar_ab", lambda j: date(int(j) + 1, 1, 1))
    a = abo(client, lieferant="Software Beispiel", rhythmus="jaehrlich", tag=15, beginn=f"{Y}-06-15", nachtragen=True, betrag="119")
    p = client.get(f"/api/abschluss/{Y}/pruefung").get_json()
    rot = [x for x in p["punkte"] if x["stufe"] == "rot"]
    assert len(rot) == 1 and "1 Abo-Abbuchung" in rot[0]["text"] and rot[0]["aktion"] == "ausgaben"
    assert client.post(f"/api/abschluss/{Y}", json={"bestaetigt": True}).status_code == 409
    client.post(f"/api/abos/{a['id']}/termine/{Y}-06-15", json={"aktion": "ok"})
    assert client.post(f"/api/abschluss/{Y}", json={"bestaetigt": True}).status_code == 201
    # danach: neues Abo mit Abbuchung im abgeschlossenen Jahr → gesperrt; bestätigen geht nicht, aussetzen schon
    b = abo(client, lieferant="Spät Pool", beginn=f"{Y}-11-01", nachtragen=True)
    f = faellig(client, b["id"])[0]
    assert f["gesperrt"] is True
    r = client.post(f"/api/abos/{b['id']}/termine/{f['datum']}", json={"aktion": "ok"})
    assert r.status_code == 409 and str(Y) in r.get_json()["error"]
    assert client.post(f"/api/abos/{b['id']}/termine/{f['datum']}", json={"aktion": "aus"}).status_code == 204


def test_sicherung_enthaelt_abos(client):
    a = abo(client, beginn=f"{Y}-01-01", nachtragen=True)
    client.post(f"/api/abos/{a['id']}/termine/{Y}-01-01", json={"aktion": "ok"})
    sicherung = client.get("/api/backup").data
    client.delete(f"/api/abos/{a['id']}")
    assert client.post("/api/backup", data={"datei": (io.BytesIO(sicherung), "s.zip")}, content_type="multipart/form-data").status_code == 200
    assert client.get("/api/abos").get_json()["abos"][0]["lieferant"] == "Musikpool Beispiel"
    assert f"{Y}-01-01" not in [f["datum"] for f in faellig(client)]


def test_fremde_seite_kann_kein_abo_anlegen(app_modul):
    r = app_modul.app.test_client().post("/api/abos", json={"lieferant": "x", "betrag": 1, "beginn": H})
    assert r.status_code == 403


def test_preis_ab_unmoeglichem_datum_abgelehnt(client):
    a = abo(client)
    for ab in ("2026-13-45", "2026-02-30", "morgen", 20260101):
        r = client.put(f"/api/abos/{a['id']}", json={"betrag": "29,99", "betrag_ab": ab})
        assert r.status_code == 400, ab
    assert client.get("/api/abos").get_json()["abos"][0]["preise"] == []

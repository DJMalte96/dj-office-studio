"""Papierkorb: Gelöschtes zählt nirgends mit, geht aber nicht verloren und kommt nicht von selbst zurück."""
import io
import os
import random
import threading
import time
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

MAILS = Path(__file__).parent / "beispiele" / "mails"
JAHRE = (2024, 2025, 2026)


def hochladen(client, *namen):
    return client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO((MAILS / n).read_bytes()), n) for n in namen]},
                       content_type="multipart/form-data").get_json()


def ausgabe(client, **werte):
    r = client.post("/api/ausgaben", json={"belegdatum": "2026-03-12", "lieferant": "Shop", "betrag": 100,
                                           "kategorie": "technik", "notiz": "Test"} | werte)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def weg(client, aid):
    assert client.delete(f"/api/ausgaben/{aid}").status_code == 204


def holen(client, aid):
    r = client.post(f"/api/papierkorb/{aid}/wiederherstellen")
    assert r.status_code == 200
    return r.get_json()


def korb(client):
    return client.get("/api/papierkorb").get_json()


# ---------- das Wichtigste: im Papierkorb = gab es nie, wiederhergestellt = nie gelöscht ----------

def abbild(client):
    """Alles, was die App aus Ausgaben macht: Listen, Vorschläge, EÜR, Anlagen und jede Datei im Export."""
    d = {p: client.get(p).get_json() for p in
         ["/api/ausgaben", "/api/ausgaben/lieferanten", "/api/anlagen"]
         + [f"/api/{was}?jahr={j}" for j in JAHRE for was in ("ausgaben", "finanzen/euer", "anlagen")]}
    for j in JAHRE:
        r = client.get(f"/api/export?jahr={j}")
        assert r.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(r.data))
        d[f"export {j}"] = {n: zf.read(n) for n in sorted(zf.namelist())}
    return d


@pytest.mark.parametrize("saat", range(12))
@pytest.mark.parametrize("kleinunternehmer", [True, False])
def test_papierkorb_ist_wie_nie_dagewesen(client, saat, kleinunternehmer):
    import finanzen
    z = random.Random(saat)
    if not kleinunternehmer:
        client.put("/api/einstellungen", json={"kleinunternehmer": False, "steuernummer": "1"})

    def zufall(i):
        kat = "anschaffung" if i % 3 == 0 else z.choice(list(finanzen.KATEGORIEN))
        return ausgabe(client, belegdatum=f"{z.choice(JAHRE)}-{z.randint(1, 12):02}-{z.randint(1, 28):02}",
                       lieferant=f"Laden {z.randint(1, 5)}", betrag=z.randint(100, 300000) / 100, kategorie=kat,
                       privatanteil=z.choice((0, 0, 50)), ust_satz=z.choice(("", 7, 19)), beschreibung=f"Posten {i}")

    for i in range(6):
        zufall(i)
    hochladen(client, "qobuz.eml")                                          # bleibt, ungeprüft
    vorher = abbild(client)

    opfer = [zufall(i) for i in range(6)]
    neu = hochladen(client, "beatport.eml", "apple.eml")["neu"]
    client.put(f"/api/ausgaben/{neu[0]['id']}", json={"uebernehmen": True})  # eine mit Beleg übernommen, eine ungeprüft
    opfer += [a["id"] for a in neu]
    mit = abbild(client)
    assert mit != vorher

    z.shuffle(opfer)
    for aid in opfer:
        weg(client, aid)
    assert abbild(client) == vorher                                         # zählt nirgends mehr mit

    for aid in opfer:
        holen(client, aid)
    assert abbild(client) == mit                                            # exakt wie nie gelöscht

    for aid in opfer:
        weg(client, aid)
    assert client.post("/api/papierkorb/leeren", json={"ids": opfer}).get_json() == {"anzahl": len(opfer)}
    assert abbild(client) == vorher and korb(client) == []


def test_geraet_kommt_mit_eigener_nutzungsdauer_zurueck(client):
    aid = ausgabe(client, betrag=2380, kategorie="anschaffung", beschreibung="Aktivboxen")
    g = client.get("/api/anlagen").get_json()[0]
    assert client.put(f"/api/anlagen/{g['id']}", json={"nutzungsdauer": 11, "bezeichnung": "Meine Boxen"}).status_code == 200
    weg(client, aid)
    assert client.get("/api/anlagen").get_json() == []
    assert client.put(f"/api/anlagen/{g['id']}", json={"nutzungsdauer": 3}).status_code == 409
    holen(client, aid)
    g = client.get("/api/anlagen").get_json()[0]
    assert (g["nutzungsdauer"], g["bezeichnung"]) == (11, "Meine Boxen")


# ---------- Schutz vor Versehen ----------

def test_zweites_fenster_kann_nicht_still_zurueckholen(client):
    a = hochladen(client, "beatport.eml")["neu"][0]
    weg(client, a["id"])
    r = client.put(f"/api/ausgaben/{a['id']}", json={"uebernehmen": True})
    assert r.status_code == 409 and "Papierkorb" in r.get_json()["error"]
    assert korb(client)[0]["status_vorher"] == "neu"


def test_geloescht_zwischen_lesen_und_schreiben(client, monkeypatch):
    import finanzen
    aid = ausgabe(client)
    echt = finanzen._pruefen

    def dazwischen(*a, **k):
        weg(client, aid)                                                   # anderes Fenster, genau jetzt
        return echt(*a, **k)
    monkeypatch.setattr(finanzen, "_pruefen", dazwischen)
    assert client.put(f"/api/ausgaben/{aid}", json={"betrag": "1", "uebernehmen": True}).status_code == 409
    assert korb(client)[0]["betrag"] == 100


def test_zweimal_loeschen_behaelt_vorherigen_status(client):
    aid = ausgabe(client)
    weg(client, aid)
    weg(client, aid)
    assert holen(client, aid)["status"] == "ok"
    assert client.delete("/api/ausgaben/999").status_code == 404


def test_endgueltig_nur_aus_dem_papierkorb(client):
    lebend, tot, spaeter = ausgabe(client), ausgabe(client), ausgabe(client)
    weg(client, tot)
    weg(client, spaeter)
    assert client.delete(f"/api/papierkorb/{lebend}").status_code == 404
    assert client.post(f"/api/papierkorb/{lebend}/wiederherstellen").status_code == 404
    for kaputt in ({}, {"ids": "alle"}, {"ids": [str(tot)]}, {"ids": [True]}):
        assert client.post("/api/papierkorb/leeren", json=kaputt).status_code == 400
    assert client.post("/api/papierkorb/leeren", json={"ids": [tot, lebend]}).get_json() == {"anzahl": 1}
    assert [a["id"] for a in korb(client)] == [spaeter]                    # nur das Angezeigte
    assert [a["id"] for a in client.get("/api/ausgaben").get_json()] == [lebend]


def test_endgueltig_laesst_datei_einer_anderen_ausgabe(client, tmp_path):
    import db
    a, b = hochladen(client, "beatport.eml", "apple.eml")["neu"]
    with db.connect() as con:                                              # z. B. manipulierte Sicherung
        con.execute("UPDATE ausgaben SET beleg_datei = ? WHERE id = ?", (b["beleg_datei"], a["id"]))
    weg(client, a["id"])
    client.delete(f"/api/papierkorb/{a['id']}")
    assert (tmp_path / b["beleg_datei"]).exists()


def test_warnung_vor_doppeltem_zaehlen(client):
    a, b = ausgabe(client, lieferant="Scan"), ausgabe(client, lieferant="Original")
    weg(client, a)
    assert korb(client)[0]["aehnlich"] == "Original"
    weg(client, b)
    assert [x["aehnlich"] for x in korb(client)] == [None, None]


def test_anzahl_und_vorschau(client):
    a = hochladen(client, "beatport.eml")["neu"][0]
    weg(client, a["id"])
    assert client.get("/api/papierkorb/anzahl").get_json() == {"anzahl": 1}
    assert client.get(f"/api/ausgaben/{a['id']}/ansicht").status_code == 200


def test_sicherung_nimmt_den_papierkorb_mit(client):
    a = hochladen(client, "beatport.eml")["neu"][0]
    ausgabe(client)
    weg(client, a["id"])
    sicherung = client.get("/api/backup").data
    client.delete(f"/api/papierkorb/{a['id']}")
    r = client.post("/api/backup", data={"datei": (io.BytesIO(sicherung), "s.zip")}, content_type="multipart/form-data")
    assert r.get_json()["anzahl"]["ausgaben"] == 1                         # zählt Gelöschtes nicht
    assert [x["id"] for x in korb(client)] == [a["id"]]
    assert client.get(f"/api/ausgaben/{a['id']}/beleg").data == (MAILS / "beatport.eml").read_bytes()


# ---------- erneut hochladen ----------

def test_erneut_hochladen_bietet_wiederherstellen_an(client):
    a = hochladen(client, "beatport.eml")["neu"][0]
    weg(client, a["id"])
    r = hochladen(client, "beatport.eml")
    assert r["neu"] == r["doppelt"] == [] and r["papierkorb"] == [{"datei": "beatport.eml", "id": a["id"]}]


def test_lebende_ausgabe_geht_vor_geloeschter(client):
    import db
    import finanzen
    a, b = hochladen(client, "beatport.eml", "apple.eml")["neu"]
    weg(client, a["id"])
    with db.connect() as con:
        con.execute("UPDATE ausgaben SET mail_message_id = (SELECT mail_message_id FROM ausgaben WHERE id = ?) WHERE id = ?",
                    (a["id"], b["id"]))
        mid = con.execute("SELECT mail_message_id FROM ausgaben WHERE id = ?", (a["id"],)).fetchone()[0]
    assert finanzen._doppelt("x", mid) == b["id"]


def test_endgueltig_geloeschtes_von_hand_wieder_hochladen(client):
    a = hochladen(client, "beatport.eml")["neu"][0]
    weg(client, a["id"])
    client.delete(f"/api/papierkorb/{a['id']}")
    assert len(hochladen(client, "beatport.eml")["neu"]) == 1


# ---------- Belege-Ordner ----------

@pytest.fixture()
def ordner(client, tmp_path, monkeypatch):
    import finanzen
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    monkeypatch.setattr(finanzen, "_standard_ordner", lambda: "")
    finanzen._ordner_stand.update(neu=0, doppelt=0, papierkorb=[], fehler=[], problem=None)
    o = tmp_path / "eingang"
    o.mkdir()

    def einrichten(verschieben=True, pfad=None):
        client.put("/api/einstellungen", json={"belege_ordner": str(pfad or o), "belege_ordner_verschieben": verschieben})
    einrichten()
    return o, einrichten, lambda: client.post("/api/belege-ordner/einlesen").get_json()


def ablegen(ziel, mail="beatport.eml"):
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes((MAILS / mail).read_bytes())
    alt = time.time() - 60
    os.utime(ziel, (alt, alt))
    return ziel


def test_nochmal_in_den_ordner_gelegt(client, ordner):
    o, _, einlesen = ordner
    ablegen(o / "a.eml")
    einlesen()
    aid = client.get("/api/ausgaben").get_json()[0]["id"]
    weg(client, aid)
    ablegen(o / "b.eml")
    assert einlesen()["papierkorb"] == [aid]
    assert (o / "übernommen" / "b.eml").exists()                           # nicht nach „nicht lesbar“
    holen(client, aid)
    assert client.get("/api/belege-ordner").get_json()["papierkorb"] == []


def test_nur_lesen_ordner_holt_endgueltig_geloeschtes_nicht_zurueck(client, ordner):
    o, einrichten, einlesen = ordner
    einrichten(verschieben=False)
    datei = ablegen(o / "a.eml")
    einlesen()
    aid = client.get("/api/ausgaben").get_json()[0]["id"]
    weg(client, aid)
    assert einlesen()["papierkorb"] == []                                  # fremde Ablage: nichts anbieten
    client.delete(f"/api/papierkorb/{aid}")
    datei.rename(o / "umbenannt.eml")                                      # Paperless benennt um
    einlesen()
    assert client.get("/api/ausgaben").get_json() == [] and korb(client) == []


# ---------- einmaliger Abgleich: vor 1.6 Verworfenes ----------

def wie_vor_16(client):
    import db
    with db.connect() as con:
        con.execute("DELETE FROM einstellungen WHERE schluessel = '_papierkorb_abgleich'")


def frueher_verworfen(aid):
    import db
    with db.connect() as con:
        con.execute("DELETE FROM ausgaben WHERE id = ?", (aid,))


@pytest.mark.parametrize("verschieben", [True, False])
def test_abgleich_findet_frueher_verworfenes(client, ordner, verschieben):
    o, einrichten, einlesen = ordner
    einrichten(verschieben)
    ablegen(o / "a.eml")
    ablegen(o / "unter" / "b.eml", "apple.eml")
    einlesen()
    a = next(x for x in client.get("/api/ausgaben").get_json() if x["lieferant"] == "Beatport")
    frueher_verworfen(a["id"])
    wie_vor_16(client)
    ablegen(o / "ganz neu.eml", "qobuz.eml")                               # nie gesehen → normal „neu“
    einlesen()
    k = korb(client)
    assert [(x["lieferant"], x["geloescht_am"]) for x in k] == [("Beatport", None)]
    assert {x["lieferant"] for x in client.get("/api/ausgaben").get_json()} == {"Apple", "Qobuz"}
    assert holen(client, k[0]["id"])["status"] == "neu"


def test_abgleich_nur_einmal(client, ordner):
    o, _, einlesen = ordner
    einlesen()
    ablegen(o / "übernommen" / "spaeter.eml")
    einlesen()
    assert korb(client) == []


def test_abgleich_wartet_bis_der_ordner_da_ist(client, ordner, tmp_path):
    o, einrichten, einlesen = ordner
    fehlt = tmp_path / "noch nicht eingebunden" / "eingang"
    einrichten(pfad=fehlt)
    einlesen()
    import db
    assert not db.get_settings().get("_papierkorb_abgleich")
    ablegen(fehlt / "übernommen" / "a.eml")
    einlesen()
    assert len(korb(client)) == 1


def test_abgleich_postfach_je_mail(client, ordner):
    from test_belege import _mbox
    o, _, einlesen = ordner
    export = o / "Musik.mbox"
    export.mkdir()
    (export / "mbox").write_bytes(_mbox((MAILS / "qobuz.eml").read_bytes(), (MAILS / "beatport.eml").read_bytes()))
    einlesen()
    alle = client.get("/api/ausgaben").get_json()
    assert len(alle) == 2
    frueher_verworfen(alle[0]["id"])
    wie_vor_16(client)
    einlesen()
    assert [x["lieferant"] for x in korb(client)] == [alle[0]["lieferant"]]


def test_abgleich_standardordner_nach_umstellung(client, ordner, tmp_path, monkeypatch):
    import finanzen
    o, einrichten, einlesen = ordner
    alt = tmp_path / "share-belege"
    ablegen(alt / "übernommen" / "a.eml")
    monkeypatch.setattr(finanzen, "_standard_ordner", lambda: str(alt))
    einrichten(verschieben=False)                                          # inzwischen auf Paperless umgestellt
    einlesen()
    assert len(korb(client)) == 1


def test_abgleich_liest_keine_pfade_aus_der_datenbank(client, ordner, tmp_path):
    import db
    o, einrichten, einlesen = ordner
    einrichten(verschieben=False)
    geheim = ablegen(tmp_path / "privat" / "geheim.eml")
    with db.connect() as con:                                              # manipulierte Sicherung
        for p in (str(geheim), str(o / ".." / "privat" / "geheim.eml")):
            con.execute("INSERT INTO belege_ordner_dateien (pfad) VALUES (?)", (p,))
    einlesen()
    assert korb(client) == [] and client.get("/api/ausgaben").get_json() == []


def test_abgleich_fehler_blockiert_einlesen_nicht(client, ordner, monkeypatch):
    import finanzen
    o, _, einlesen = ordner
    monkeypatch.setattr(finanzen, "_abgleich_vor_16", lambda a: 1 / 0)
    ablegen(o / "a.eml")
    assert einlesen()["neu"] == 1


# ---------- Paperless-Schnittstelle ----------

@pytest.fixture()
def abholen(client, monkeypatch):
    import finanzen
    from test_paperless_belege import FakePaperless, TOKEN
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakePaperless)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(finanzen, "HINTERGRUND", False)
    client.put("/api/einstellungen", json={"paperless_installiert": True, "paperless_token": TOKEN, "paperless_tag": "7",
                                           "paperless_url": f"http://127.0.0.1:{srv.server_address[1]}"})
    yield lambda: client.post("/api/paperless/abholen").get_json()
    srv.shutdown()


def test_paperless_bringt_verworfenes_nicht_zurueck(client, abholen):
    assert abholen()["neu"] == 2
    a, b = client.get("/api/ausgaben").get_json()
    weg(client, a["id"])
    st = abholen()
    assert (st["gesamt"], st["neu"], st["verworfen"], st["vorhanden"]) == (0, 0, 1, 1)
    client.delete(f"/api/papierkorb/{a['id']}")
    st = abholen()
    assert (st["gesamt"], st["neu"], st["verworfen"], st["vorhanden"]) == (0, 0, 1, 1)
    assert [x["id"] for x in client.get("/api/ausgaben").get_json()] == [b["id"]]


def test_paperless_erkennt_geloeschten_upload_an_der_pruefsumme(client, abholen):
    from test_paperless_belege import DOKUMENTE
    a = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(DOKUMENTE[11]["daten"]), "kabel.pdf")]},
                    content_type="multipart/form-data").get_json()["neu"][0]
    weg(client, a["id"])
    client.delete(f"/api/papierkorb/{a['id']}")
    st = abholen()
    assert (st["neu"], st["verworfen"]) == (1, 1)
    assert abholen()["gesamt"] == 0                                        # wird nicht jedes Mal neu heruntergeladen


# ---------- Randfälle ----------

def test_auch_leeres_speichern_wird_abgelehnt(client):
    aid = ausgabe(client)
    weg(client, aid)
    assert client.put(f"/api/ausgaben/{aid}", json={}).status_code == 409


def test_paperless_zaehlt_upload_im_papierkorb_als_verworfen(client, abholen):
    from test_paperless_belege import DOKUMENTE
    a = client.post("/api/ausgaben/belege", data={"dateien": [(io.BytesIO(DOKUMENTE[11]["daten"]), "kabel.pdf")]},
                    content_type="multipart/form-data").get_json()["neu"][0]
    weg(client, a["id"])
    st = abholen()
    assert (st["neu"], st["doppelt"], st["verworfen"]) == (1, 0, 1)


def test_nur_lesen_umbenanntes_aus_dem_papierkorb_wird_nicht_angeboten(client, ordner):
    o, einrichten, einlesen = ordner
    einrichten(verschieben=False)
    datei = ablegen(o / "a.eml")
    einlesen()
    weg(client, client.get("/api/ausgaben").get_json()[0]["id"])
    datei.rename(o / "umbenannt.eml")
    assert einlesen()["papierkorb"] == []
    assert len(korb(client)) == 1


def test_postfach_mit_fehler_und_papierkorb_gilt_als_uebernommen(client, ordner, monkeypatch):
    import finanzen
    o, _, einlesen = ordner
    ablegen(o / "a.eml")
    monkeypatch.setattr(finanzen, "dateien_aufnehmen", lambda *a, **k: {
        "neu": [], "doppelt": [], "papierkorb": [{"datei": "a", "id": 1}], "fehler": [{"datei": "b", "fehler": "x"}]})
    einlesen()
    assert (o / "übernommen" / "a.eml").exists()

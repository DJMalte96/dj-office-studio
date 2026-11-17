"""Zahlungserinnerung und Mahnungen."""
import os
from datetime import date, timedelta

from conftest import neue_rechnung, pdf_text


def test_drei_stufen(client, tmp_path):
    inv_id = neue_rechnung(client, datum="2026-10-01")
    erwartet = ["Zahlungserinnerung", "1. Mahnung", "2. Mahnung"]
    for stufe, titel in enumerate(erwartet, start=1):
        r = client.post(f"/api/rechnungen/{inv_id}/mahnung")
        assert r.status_code == 201
        assert r.get_json()["stufe"] == stufe and r.get_json()["bezeichnung"] == titel
        text = pdf_text(client.get(f"/api/mahnungen/{r.get_json()['id']}/pdf").data)
        assert titel in text and "Rechnung Nr. 037" in text and "960,- Euro" in text
        frist = (date.today() + timedelta(days=7)).strftime("%d.%m.%Y")
        assert f"bis spätestens {frist}" in text
        assert "fällig seit 09.10.26" in text   # Rechnungsdatum + 8 Tage aus der Zahlungsbedingung
    assert "letzte Mahnung" in text
    assert client.post(f"/api/rechnungen/{inv_id}/mahnung").status_code == 400   # mehr als 3 Stufen

    inv = client.get(f"/api/rechnungen/{inv_id}").get_json()
    assert [m["stufe"] for m in inv["mahnungen"]] == [1, 2, 3]
    assert inv["festgeschrieben"]
    assert sorted(os.listdir(tmp_path / "pdf"))[:1] == ["1-Mahnung_037_" + date.today().strftime("%d%m%y") + ".pdf"]


def test_mahnfrist_aus_einstellungen(client):
    client.put("/api/einstellungen", json={"mahnfrist_tage": 14})
    inv_id = neue_rechnung(client)
    m = client.post(f"/api/rechnungen/{inv_id}/mahnung").get_json()
    inv = client.get(f"/api/rechnungen/{inv_id}").get_json()
    assert inv["mahnungen"][0]["frist"] == (date.today() + timedelta(days=14)).isoformat()
    assert m["stufe"] == 1


def test_keine_mahnung_fuer_bezahlte_oder_stornierte(client):
    bezahlt = neue_rechnung(client, nummer="037", bezahlt=True)
    assert client.post(f"/api/rechnungen/{bezahlt}/mahnung").status_code == 400
    offen = neue_rechnung(client, nummer="038")
    client.post(f"/api/rechnungen/{offen}/stornieren")
    assert client.post(f"/api/rechnungen/{offen}/mahnung").status_code == 400

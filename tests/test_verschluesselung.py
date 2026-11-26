"""Seit 1.15: Verschlüsselte Sicherungen (.djos) – Schlüsselpaar, Passwort, Blöcke, Manipulation."""
import io
import os
import struct

import pytest

import conftest  # noqa: F401  (Pfad zur App)
import verschluesselung as v

PW = "Plattenkiste-1987!"


@pytest.fixture(scope="module")
def schluessel():
    return v.schluessel_erzeugen(PW)


def zu(daten, pub, priv):
    out = io.BytesIO()
    v.verschluesseln(io.BytesIO(daten), out, pub, priv)
    return out.getvalue()


def auf(djos, pw=PW):
    out = io.BytesIO()
    v.entschluesseln(io.BytesIO(djos), out, pw)
    return out.getvalue()


@pytest.mark.parametrize("groesse", [0, 1, 1000, v.BLOCK, v.BLOCK + 1, int(2.5 * v.BLOCK)])
def test_hin_und_zurueck(schluessel, groesse):
    daten = os.urandom(groesse)
    djos = zu(daten, *schluessel)
    assert v.ist_verschluesselt(djos)
    if groesse >= 16:                                  # Klartext kommt in der Datei nicht vor
        assert daten[:200] not in djos
    assert auf(djos) == daten


def test_passwort_nicht_gespeichert(schluessel):
    pub, priv = schluessel
    assert PW not in priv and PW not in pub
    djos = zu(b"geheim", pub, priv)
    assert PW.encode() not in djos


def test_falsches_passwort(schluessel):
    djos = zu(b"Kunden und Belege", *schluessel)
    with pytest.raises(v.FalschesPasswort):
        auf(djos, "falsch-falsch")
    with pytest.raises(v.FalschesPasswort):
        v.privat_oeffnen(schluessel[1], "")


def test_zu_kurzes_passwort():
    with pytest.raises(ValueError):
        v.schluessel_erzeugen("kurz")


def test_manipulation_faellt_auf(schluessel):
    daten = os.urandom(int(2.5 * v.BLOCK))
    djos = bytearray(zu(daten, *schluessel))
    kaputt = bytes(djos[:-10]) + bytes([djos[-10] ^ 1]) + bytes(djos[-9:])
    with pytest.raises(v.KeineSicherung):
        auf(kaputt)
    with pytest.raises(v.KeineSicherung):           # abgeschnitten: letzter Block fehlt
        auf(bytes(djos[:-(v.BLOCK // 2)]))
    with pytest.raises(v.KeineSicherung):           # etwas angehängt
        auf(bytes(djos) + b"x")
    # zwei Blöcke vertauschen
    (n,) = struct.unpack(">I", djos[len(v.MAGIC):len(v.MAGIC) + 4])
    start = len(v.MAGIC) + 4 + n
    bloecke, pos = [], start
    while pos < len(djos):
        (l,) = struct.unpack(">I", djos[pos:pos + 4])
        bloecke.append(bytes(djos[pos:pos + 4 + l]))
        pos += 4 + l
    assert len(bloecke) == 3
    with pytest.raises(v.KeineSicherung):
        auf(bytes(djos[:start]) + bloecke[1] + bloecke[0] + bloecke[2])
    with pytest.raises(v.KeineSicherung):
        auf(b"PK\x03\x04 keine Sicherung")


def test_neuer_rechner_braucht_nur_das_passwort(schluessel):
    """Der verschlossene Schlüssel steckt im Kopf – auf einem neuen Rechner genügt das Passwort."""
    djos = zu(b"alles", *schluessel)
    assert auf(djos) == b"alles"


def test_passwort_aendern(schluessel):
    pub, priv = schluessel
    alt = zu(b"vorher", pub, priv)
    priv_neu = v.passwort_aendern(priv, PW, "Neues-Passwort-2027")
    neu = zu(b"nachher", pub, priv_neu)
    assert auf(neu, "Neues-Passwort-2027") == b"nachher"
    assert auf(alt, PW) == b"vorher"                 # ältere Sicherung: bisheriges Passwort
    with pytest.raises(v.FalschesPasswort):
        auf(neu, PW)
    with pytest.raises(v.FalschesPasswort):
        v.passwort_aendern(priv, "falsch-falsch", "Neues-Passwort-2027")

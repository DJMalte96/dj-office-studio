"""Verschlüsselte Sicherungen (seit 1.15).

Ein Sicherungs-Passwort erzeugt einmal ein Schlüsselpaar (X25519):
- Der öffentliche Schlüssel liegt offen in den Einstellungen und kann nur verschlüsseln – damit verschlüsselt die
  automatische Sicherung, ohne dass jemand ein Passwort eingibt.
- Der private Schlüssel wird mit dem Passwort (scrypt → AES-256-GCM) verschlossen gespeichert. Das Passwort selbst wird
  nirgends gespeichert. Ohne Passwort lässt sich keine Sicherung öffnen.

Dateiformat (.djos): MAGIC, 4 Byte Länge + Kopf (JSON: Version, flüchtiger öffentlicher Schlüssel, Blockgröße und der
mit dem Passwort verschlossene private Schlüssel – so öffnet sich die Sicherung auch auf einem neuen Rechner),
danach Blöcke aus 4 Byte Länge + AES-256-GCM. Jeder Block hängt an Kopf, Blocknummer und „letzter Block“ –
vertauschte, fehlende oder angehängte Blöcke fallen beim Entschlüsseln auf. So bleiben auch Sicherungen mit
Hunderten MB Belegen ohne viel Arbeitsspeicher verschlüsselbar.
"""
import base64
import json
import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"DJOS-SICHERUNG\n"
ENDUNG = ".djos"
BLOCK = 1024 * 1024
MIN_LAENGE = 10
SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}      # ~32 MB, ein paar Zehntelsekunden – auch auf dem Raspberry Pi


class FalschesPasswort(Exception):
    pass


class KeineSicherung(Exception):
    pass


def _b64(b):
    return base64.b64encode(b).decode()


def _unb64(t):
    return base64.b64decode(t.encode())


def _passwort_schluessel(passwort, salt, n, r, p):
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(passwort.encode("utf-8"))


def schluessel_erzeugen(passwort):
    """Neues Schlüsselpaar → (öffentlicher Schlüssel als Text, verschlossener privater Schlüssel als JSON-Text)."""
    if len(passwort or "") < MIN_LAENGE:
        raise ValueError(f"Das Passwort braucht mindestens {MIN_LAENGE} Zeichen")
    privat = X25519PrivateKey.generate()
    return _b64(privat.public_key().public_bytes_raw()), _verschliessen(privat.private_bytes_raw(), passwort)


def _verschliessen(roh, passwort):
    salt, nonce = os.urandom(16), os.urandom(12)
    k = _passwort_schluessel(passwort, salt, **SCRYPT)
    return json.dumps({"v": 1, "kdf": "scrypt", **SCRYPT, "salt": _b64(salt), "nonce": _b64(nonce),
                       "ct": _b64(AESGCM(k).encrypt(nonce, roh, b"djos-privat"))})


def privat_oeffnen(verschlossen, passwort):
    """Privaten Schlüssel mit dem Passwort öffnen – FalschesPasswort, wenn es nicht passt."""
    d = json.loads(verschlossen)
    k = _passwort_schluessel(passwort or "", _unb64(d["salt"]), d["n"], d["r"], d["p"])
    try:
        return X25519PrivateKey.from_private_bytes(AESGCM(k).decrypt(_unb64(d["nonce"]), _unb64(d["ct"]), b"djos-privat"))
    except InvalidTag:
        raise FalschesPasswort from None


def passwort_aendern(verschlossen, alt, neu):
    """Gleiches Schlüsselpaar, neu verschlossen – alle bisherigen Sicherungen öffnen sich dann mit dem neuen Passwort."""
    if len(neu or "") < MIN_LAENGE:
        raise ValueError(f"Das Passwort braucht mindestens {MIN_LAENGE} Zeichen")
    privat = privat_oeffnen(verschlossen, alt)
    return _verschliessen(privat.private_bytes_raw(), neu)


def _blockschluessel(geteilt, eph_pub):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=eph_pub, info=b"djos-sicherung-v1").derive(geteilt)


def _nonce(basis, nr):
    return basis[:4] + struct.pack(">Q", nr)


def verschluesseln(quelle, ziel, oeffentlich, verschlossen):
    """Datei-Objekt quelle → ziel (.djos) für den öffentlichen Schlüssel (Text); verschlossen = privater Schlüssel
    (mit dem Passwort verschlossen) für den Kopf."""
    eph = X25519PrivateKey.generate()
    eph_pub = eph.public_key().public_bytes_raw()
    geteilt = eph.exchange(X25519PublicKey.from_public_bytes(_unb64(oeffentlich)))
    aes = AESGCM(_blockschluessel(geteilt, eph_pub))
    basis = os.urandom(12)
    kopf = json.dumps({"v": 1, "alg": "X25519-HKDF-SHA256-AES256GCM", "eph": _b64(eph_pub), "nonce": _b64(basis),
                       "block": BLOCK, "schluessel": json.loads(verschlossen)}).encode()
    ziel.write(MAGIC + struct.pack(">I", len(kopf)) + kopf)
    nr, teil = 0, quelle.read(BLOCK)
    while True:
        naechster = quelle.read(BLOCK)
        letzter = not naechster
        ct = aes.encrypt(_nonce(basis, nr), teil, kopf + struct.pack(">Q?", nr, letzter))
        ziel.write(struct.pack(">I", len(ct)) + ct)
        if letzter:
            return
        nr, teil = nr + 1, naechster


def ist_verschluesselt(anfang):
    return anfang[:len(MAGIC)] == MAGIC


def entschluesseln(quelle, ziel, passwort):
    """quelle (.djos) → ziel mit dem Passwort. FalschesPasswort / KeineSicherung bei Problemen."""
    if not ist_verschluesselt(quelle.read(len(MAGIC))):
        raise KeineSicherung("Keine verschlüsselte Sicherung")
    try:
        (n,) = struct.unpack(">I", quelle.read(4))
        if n > 16384:
            raise KeineSicherung("Kopf ungültig")
        kopf = quelle.read(n)
        d = json.loads(kopf)
        eph_pub, basis = _unb64(d["eph"]), _unb64(d["nonce"])
        privat = privat_oeffnen(json.dumps(d["schluessel"]), passwort)
        aes = AESGCM(_blockschluessel(privat.exchange(X25519PublicKey.from_public_bytes(eph_pub)), eph_pub))
    except (ValueError, KeyError, TypeError, struct.error) as e:
        raise KeineSicherung("Kopf ungültig") from e
    nr = 0
    while True:
        laenge = quelle.read(4)
        if len(laenge) < 4:
            raise KeineSicherung("Die Sicherung ist unvollständig")
        (n,) = struct.unpack(">I", laenge)
        if n > BLOCK + 64:
            raise KeineSicherung("Block ungültig")
        ct = quelle.read(n)
        for letzter in (False, True):
            try:
                ziel.write(aes.decrypt(_nonce(basis, nr), ct, kopf + struct.pack(">Q?", nr, letzter)))
                break
            except InvalidTag:
                if letzter:
                    raise KeineSicherung("Die Sicherung ist beschädigt") from None
        if letzter:
            if quelle.read(1):
                raise KeineSicherung("Die Sicherung ist beschädigt")
            return
        nr += 1


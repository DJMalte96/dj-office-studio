"""SQLite-Datenhaltung für Kunden, Textbausteine, Zahlungsbedingungen und Rechnungen."""
import json
import os
import sqlite3
from pathlib import Path

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "rechnungen.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS kunden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    zusatz TEXT DEFAULT '',
    strasse TEXT DEFAULT '',
    plz TEXT DEFAULT '',
    ort TEXT DEFAULT '',
    email TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS textbausteine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titel TEXT NOT NULL,
    text TEXT NOT NULL,
    preis REAL,
    grundpreis REAL,
    grundstunden REAL,
    stundensatz REAL
);
CREATE TABLE IF NOT EXISTS zahlungsbedingungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titel TEXT NOT NULL,
    text TEXT NOT NULL,
    sortierung INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS aufgaben (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titel TEXT NOT NULL,
    faellig TEXT DEFAULT '',
    erledigt INTEGER DEFAULT 0,
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rechnungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nummer TEXT NOT NULL UNIQUE,
    datum TEXT NOT NULL,
    kunde_id INTEGER REFERENCES kunden(id) ON DELETE SET NULL,
    kunde_json TEXT NOT NULL,
    positionen_json TEXT NOT NULL,
    zahlungsbedingung TEXT NOT NULL,
    gesamt REAL NOT NULL,
    bezahlt INTEGER DEFAULT 0,
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mahnungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rechnung_id INTEGER NOT NULL REFERENCES rechnungen(id) ON DELETE CASCADE,
    stufe INTEGER NOT NULL,                -- 1 Zahlungserinnerung, 2 = 1. Mahnung, 3 = 2. Mahnung
    datum TEXT NOT NULL,
    frist TEXT NOT NULL,
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS einstellungen (
    schluessel TEXT PRIMARY KEY,
    wert TEXT                              -- JSON-Wert
);
CREATE TABLE IF NOT EXISTS angebote (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nummer TEXT NOT NULL UNIQUE,
    datum TEXT NOT NULL,
    gueltig_bis TEXT DEFAULT '',
    kunde_id INTEGER REFERENCES kunden(id) ON DELETE SET NULL,
    kunde_json TEXT NOT NULL,
    positionen_json TEXT NOT NULL,
    zahlungsbedingung TEXT DEFAULT '',
    hinweise TEXT DEFAULT '',
    gesamt REAL NOT NULL,
    status TEXT DEFAULT 'offen',          -- offen | angenommen | abgelehnt
    rechnung_id INTEGER REFERENCES rechnungen(id) ON DELETE SET NULL,
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

DEFAULT_ZAHLUNGSBEDINGUNGEN = [
    ("Überweisung 8 Tage", "Bitte den Betrag innerhalb der nächsten 8 Tage auf das unten genannte Konto überweisen."),
    ("Überweisung 14 Tage", "Bitte den Betrag innerhalb der nächsten 14 Tage auf das unten genannte Konto überweisen."),
    ("Bar erhalten", "Den Rechnungsbetrag habe ich dankend in bar erhalten."),
    ("Bereits bezahlt", "Der Rechnungsbetrag wurde bereits vollständig beglichen."),
]

def anlass_text(anlass):
    """Standard-Textvorlage für einen Anlass (Tabelle textbausteine: titel = Anlass, text = Vorlage)."""
    return f"DJ – Tätigkeit {anlass} – {{von}} Uhr bis {{bis}} Uhr"


# Anlass → Textvorlage
DEFAULT_ANLAESSE = {
    "Hochzeit": anlass_text("Hochzeit"),
    "Geburtstag": anlass_text("Geburtstagsfeier"),
    "Firmenfeier": anlass_text("Firmenfeier"),
}

# Frühere Standard-Textbausteine (bis 0.2.1) → werden, falls unverändert, zu Anlässen umbenannt
LEGACY_TEXTBAUSTEINE = {
    ("DJ Hochzeit",
     "DJ – Tätigkeit Hochzeit (750€ für 6 Stunden, jede weitere Stunde 70€) – {von} Uhr bis {bis} Uhr"): "Hochzeit",
    ("DJ Geburtstag", "DJ – Tätigkeit Geburtstagsfeier – {von} Uhr bis {bis} Uhr"): "Geburtstag",
}


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init():
    with connect() as con:
        con.executescript(SCHEMA)
        if con.execute("SELECT COUNT(*) FROM zahlungsbedingungen").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO zahlungsbedingungen (titel, text, sortierung) VALUES (?, ?, ?)",
                [(t, x, i) for i, (t, x) in enumerate(DEFAULT_ZAHLUNGSBEDINGUNGEN)],
            )
        if con.execute("SELECT COUNT(*) FROM textbausteine").fetchone()[0] == 0:
            con.executemany("INSERT INTO textbausteine (titel, text) VALUES (?, ?)",
                            list(DEFAULT_ANLAESSE.items()))
        spalten = {r["name"] for r in con.execute("PRAGMA table_info(rechnungen)")}
        if "paperless_am" not in spalten:   # seit 0.6.0: Zeitpunkt der Übertragung an Paperless
            con.execute("ALTER TABLE rechnungen ADD COLUMN paperless_am TEXT")
        # seit 0.12.0: Festschreiben, Storno, Bezahlt-Datum
        if "festgeschrieben" not in spalten:
            con.execute("ALTER TABLE rechnungen ADD COLUMN festgeschrieben INTEGER DEFAULT 0")
            # Bestehende bezahlte bzw. an Paperless übertragene Rechnungen gelten als festgeschrieben
            con.execute("UPDATE rechnungen SET festgeschrieben = 1 WHERE bezahlt = 1 OR paperless_am IS NOT NULL")
        for spalte, typ in (("storno_von", "INTEGER"), ("storniert_durch", "INTEGER"), ("bezahlt_am", "TEXT")):
            if spalte not in spalten:
                con.execute(f"ALTER TABLE rechnungen ADD COLUMN {spalte} {typ}")
        if "paperless_am" not in {r["name"] for r in con.execute("PRAGMA table_info(angebote)")}:
            con.execute("ALTER TABLE angebote ADD COLUMN paperless_am TEXT")   # seit 0.8.4
        for (titel, text), anlass in LEGACY_TEXTBAUSTEINE.items():
            con.execute("UPDATE textbausteine SET titel = ?, text = ?, preis = NULL, grundpreis = NULL,"
                        " grundstunden = NULL, stundensatz = NULL WHERE titel = ? AND text = ?",
                        (anlass, DEFAULT_ANLAESSE[anlass], titel, text))


def rows(cur):
    return [dict(r) for r in cur.fetchall()]


# ---------- Generisches CRUD für einfache Tabellen ----------

TABLES = {
    "kunden": ["name", "zusatz", "strasse", "plz", "ort", "email"],
    "textbausteine": ["titel", "text", "preis", "grundpreis", "grundstunden", "stundensatz"],
    "zahlungsbedingungen": ["titel", "text", "sortierung"],
    "aufgaben": ["titel", "faellig", "erledigt"],
}
ORDER = {
    "kunden": "name COLLATE NOCASE",
    "textbausteine": "titel COLLATE NOCASE",
    "zahlungsbedingungen": "sortierung, id",
    "aufgaben": "erledigt, faellig = '', faellig, id",
}


def list_items(table, q=None):
    with connect() as con:
        if table == "kunden" and q:
            like = f"%{q}%"
            return rows(con.execute(
                "SELECT * FROM kunden WHERE name LIKE ? OR ort LIKE ? OR strasse LIKE ?"
                f" ORDER BY {ORDER[table]} LIMIT 10", (like, like, like)))
        return rows(con.execute(f"SELECT * FROM {table} ORDER BY {ORDER[table]}"))


def save_item(table, data, item_id=None):
    cols = TABLES[table]
    values = [data.get(c) for c in cols]
    with connect() as con:
        if item_id:
            con.execute(
                f"UPDATE {table} SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?",
                values + [item_id])
            return item_id
        cur = con.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            values)
        return cur.lastrowid


def delete_item(table, item_id):
    with connect() as con:
        con.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))


# ---------- Rechnungen ----------

def _invoice_from_row(r):
    d = dict(r)
    d["kunde"] = json.loads(d.pop("kunde_json"))
    d["positionen"] = json.loads(d.pop("positionen_json"))
    d["bezahlt"] = bool(d["bezahlt"])
    d["festgeschrieben"] = bool(d.get("festgeschrieben"))
    return d


def _ergaenzen(con, rechnungen):
    """Mahnungen und Storno-Bezug (Nummer/Datum der stornierten Rechnung) anhängen."""
    if not rechnungen:
        return rechnungen
    mahnungen = {}
    for m in con.execute("SELECT * FROM mahnungen ORDER BY stufe"):
        mahnungen.setdefault(m["rechnung_id"], []).append(dict(m))
    kopf = {r["id"]: {"nummer": r["nummer"], "datum": r["datum"]}
            for r in con.execute("SELECT id, nummer, datum FROM rechnungen")}
    for inv in rechnungen:
        inv["mahnungen"] = mahnungen.get(inv["id"], [])
        inv["storno_zu"] = kopf.get(inv["storno_von"]) if inv.get("storno_von") else None
        inv["storniert_durch_nummer"] = kopf.get(inv["storniert_durch"], {}).get("nummer") \
            if inv.get("storniert_durch") else None
    return rechnungen


def list_invoices():
    with connect() as con:
        return _ergaenzen(con, [_invoice_from_row(r) for r in con.execute(
            "SELECT * FROM rechnungen ORDER BY datum DESC, nummer DESC")])


def get_invoice(inv_id):
    with connect() as con:
        r = con.execute("SELECT * FROM rechnungen WHERE id = ?", (inv_id,)).fetchone()
        return _ergaenzen(con, [_invoice_from_row(r)])[0] if r else None


def next_number(start=1, table="rechnungen"):
    """Höchste numerische Nummer + 1 (mindestens `start`), dreistellig mit führenden Nullen."""
    with connect() as con:
        nums = [r[0] for r in con.execute(f"SELECT nummer FROM {table}")]
    highest = max((int(n) for n in nums if n.isdigit()), default=0)
    width = max([3] + [len(n) for n in nums if n.isdigit()])
    return str(max(highest + 1, int(start or 1))).zfill(width)


def number_taken(nummer, exclude_id=None, table="rechnungen"):
    with connect() as con:
        r = con.execute(f"SELECT id FROM {table} WHERE nummer = ? AND id IS NOT ?",
                        (nummer, exclude_id)).fetchone()
        return r is not None


def upsert_customer(kunde):
    """Kunde speichern: vorhandene ID aktualisieren, sonst per Name+Ort suchen oder neu anlegen."""
    data = {c: (kunde.get(c) or "").strip() for c in TABLES["kunden"]}
    kid = kunde.get("id")
    if not kid:
        with connect() as con:
            r = con.execute(
                "SELECT id FROM kunden WHERE name = ? COLLATE NOCASE AND ort = ? COLLATE NOCASE",
                (data["name"], data["ort"])).fetchone()
            kid = r["id"] if r else None
    return save_item("kunden", data, kid)


def save_invoice(inv, inv_id=None):
    vals = (inv["nummer"], inv["datum"], inv.get("kunde_id"), json.dumps(inv["kunde"]),
            json.dumps(inv["positionen"]), inv["zahlungsbedingung"], inv["gesamt"],
            int(bool(inv.get("bezahlt"))))
    with connect() as con:
        if inv_id:
            con.execute(
                "UPDATE rechnungen SET nummer=?, datum=?, kunde_id=?, kunde_json=?,"
                " positionen_json=?, zahlungsbedingung=?, gesamt=?, bezahlt=? WHERE id=?",
                vals + (inv_id,))
            return inv_id
        return con.execute(
            "INSERT INTO rechnungen (nummer, datum, kunde_id, kunde_json, positionen_json,"
            " zahlungsbedingung, gesamt, bezahlt, festgeschrieben, storno_von, bezahlt_am)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            vals + (int(bool(inv.get("festgeschrieben"))), inv.get("storno_von"), inv.get("bezahlt_am"))).lastrowid


def set_paid(inv_id, paid):
    """Bezahlt setzen (mit Datum) – eine bezahlte Rechnung wird damit auch festgeschrieben."""
    with connect() as con:
        if paid:
            con.execute("UPDATE rechnungen SET bezahlt = 1, festgeschrieben = 1,"
                        " bezahlt_am = COALESCE(bezahlt_am, date('now', 'localtime')) WHERE id = ?", (inv_id,))
        else:
            con.execute("UPDATE rechnungen SET bezahlt = 0, bezahlt_am = NULL WHERE id = ?", (inv_id,))


def festschreiben(inv_id):
    with connect() as con:
        con.execute("UPDATE rechnungen SET festgeschrieben = 1 WHERE id = ?", (inv_id,))


def set_storniert(inv_id, storno_id):
    with connect() as con:
        con.execute("UPDATE rechnungen SET storniert_durch = ?, festgeschrieben = 1 WHERE id = ?",
                    (storno_id, inv_id))


# ---------- Mahnungen ----------

def add_mahnung(inv_id, stufe, datum, frist):
    with connect() as con:
        return con.execute("INSERT INTO mahnungen (rechnung_id, stufe, datum, frist) VALUES (?, ?, ?, ?)",
                           (inv_id, stufe, datum, frist)).lastrowid


def get_mahnung(mahnung_id):
    with connect() as con:
        r = con.execute("SELECT * FROM mahnungen WHERE id = ?", (mahnung_id,)).fetchone()
        return dict(r) if r else None


# ---------- Datensicherung ----------

def sichern(ziel_pfad):
    """Konsistente Kopie der Datenbank (auch während die App läuft)."""
    quelle = connect()
    ziel = sqlite3.connect(ziel_pfad)
    try:
        quelle.backup(ziel)
    finally:
        ziel.close()
        quelle.close()


def pruefe_sicherung(pfad):
    """Prüft, ob die Datei eine Datenbank von DJ Office Studio ist; gibt Anzahlen zurück."""
    try:
        # nur lesend öffnen; as_uri() ergibt auch unter Windows eine gültige file:-Adresse
        con = sqlite3.connect(Path(pfad).resolve().as_uri() + "?mode=ro", uri=True)
        tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"rechnungen", "kunden"} <= tabellen:
            raise ValueError("Die Datei enthält keine Daten von DJ Office Studio.")
        anzahl = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("rechnungen", "kunden", "angebote") if t in tabellen}
        con.close()
        return anzahl
    except sqlite3.DatabaseError as e:
        raise ValueError("Die Datei ist keine gültige Sicherung.") from e


def wiederherstellen(pfad):
    """Inhalt der aktuellen Datenbank durch die Sicherung ersetzen und Schema auf Stand bringen."""
    quelle = sqlite3.connect(pfad)
    ziel = connect()
    try:
        quelle.backup(ziel)
    finally:
        quelle.close()
        ziel.close()
    init()


def set_paperless(inv_id, zeitpunkt, table="rechnungen"):
    with connect() as con:
        con.execute(f"UPDATE {table} SET paperless_am = ? WHERE id = ?", (zeitpunkt, inv_id))


def delete_invoice(inv_id):
    with connect() as con:
        con.execute("DELETE FROM rechnungen WHERE id = ?", (inv_id,))


# ---------- Angebote ----------

STATUS = ("offen", "angenommen", "abgelehnt")


def _offer_from_row(r):
    d = dict(r)
    d["kunde"] = json.loads(d.pop("kunde_json"))
    d["positionen"] = json.loads(d.pop("positionen_json"))
    d["art"] = "angebot"
    return d


def list_offers():
    with connect() as con:
        return [_offer_from_row(r) for r in con.execute(
            "SELECT * FROM angebote ORDER BY datum DESC, nummer DESC")]


def get_offer(offer_id):
    with connect() as con:
        r = con.execute("SELECT * FROM angebote WHERE id = ?", (offer_id,)).fetchone()
        return _offer_from_row(r) if r else None


def save_offer(a, offer_id=None):
    vals = (a["nummer"], a["datum"], a["gueltig_bis"], a.get("kunde_id"), json.dumps(a["kunde"]),
            json.dumps(a["positionen"]), a["zahlungsbedingung"], a["hinweise"], a["gesamt"])
    with connect() as con:
        if offer_id:
            con.execute(
                "UPDATE angebote SET nummer=?, datum=?, gueltig_bis=?, kunde_id=?, kunde_json=?,"
                " positionen_json=?, zahlungsbedingung=?, hinweise=?, gesamt=? WHERE id=?",
                vals + (offer_id,))
            return offer_id
        return con.execute(
            "INSERT INTO angebote (nummer, datum, gueltig_bis, kunde_id, kunde_json, positionen_json,"
            " zahlungsbedingung, hinweise, gesamt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", vals).lastrowid


def set_offer_status(offer_id, status, rechnung_id=None):
    with connect() as con:
        if rechnung_id:
            con.execute("UPDATE angebote SET status = ?, rechnung_id = ? WHERE id = ?",
                        (status, rechnung_id, offer_id))
        else:
            con.execute("UPDATE angebote SET status = ? WHERE id = ?", (status, offer_id))


def delete_offer(offer_id):
    with connect() as con:
        con.execute("DELETE FROM angebote WHERE id = ?", (offer_id,))


# ---------- Einstellungen (Absender, Bank, Nummern, Paperless …) ----------

def get_settings():
    with connect() as con:
        return {r["schluessel"]: json.loads(r["wert"]) for r in con.execute("SELECT * FROM einstellungen")}


def save_settings(werte):
    with connect() as con:
        con.executemany("INSERT INTO einstellungen (schluessel, wert) VALUES (?, ?)"
                        " ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
                        [(k, json.dumps(v)) for k, v in werte.items()])

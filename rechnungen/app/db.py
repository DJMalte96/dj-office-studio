"""SQLite-Datenhaltung für Kunden, Textbausteine, Zahlungsbedingungen und Rechnungen."""
import json
import os
import sqlite3

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
"""

DEFAULT_ZAHLUNGSBEDINGUNGEN = [
    ("Überweisung 8 Tage", "Bitte den Betrag innerhalb der nächsten 8 Tage auf das unten genannte Konto überweisen."),
    ("Überweisung 14 Tage", "Bitte den Betrag innerhalb der nächsten 14 Tage auf das unten genannte Konto überweisen."),
    ("Bar erhalten", "Den Rechnungsbetrag habe ich dankend in bar erhalten."),
    ("Bereits bezahlt", "Der Rechnungsbetrag wurde bereits vollständig beglichen."),
]

DEFAULT_TEXTBAUSTEINE = [
    # titel, text, preis, grundpreis, grundstunden, stundensatz
    ("DJ Hochzeit",
     "DJ – Tätigkeit Hochzeit (750€ für 6 Stunden, jede weitere Stunde 70€) – {von} Uhr bis {bis} Uhr",
     None, 750, 6, 70),
    ("DJ Geburtstag",
     "DJ – Tätigkeit Geburtstagsfeier – {von} Uhr bis {bis} Uhr",
     None, None, None, None),
]


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
            con.executemany(
                "INSERT INTO textbausteine (titel, text, preis, grundpreis, grundstunden, stundensatz)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                DEFAULT_TEXTBAUSTEINE,
            )


def rows(cur):
    return [dict(r) for r in cur.fetchall()]


# ---------- Generisches CRUD für einfache Tabellen ----------

TABLES = {
    "kunden": ["name", "zusatz", "strasse", "plz", "ort", "email"],
    "textbausteine": ["titel", "text", "preis", "grundpreis", "grundstunden", "stundensatz"],
    "zahlungsbedingungen": ["titel", "text", "sortierung"],
}
ORDER = {
    "kunden": "name COLLATE NOCASE",
    "textbausteine": "titel COLLATE NOCASE",
    "zahlungsbedingungen": "sortierung, id",
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
    return d


def list_invoices():
    with connect() as con:
        return [_invoice_from_row(r) for r in con.execute(
            "SELECT * FROM rechnungen ORDER BY datum DESC, nummer DESC")]


def get_invoice(inv_id):
    with connect() as con:
        r = con.execute("SELECT * FROM rechnungen WHERE id = ?", (inv_id,)).fetchone()
        return _invoice_from_row(r) if r else None


def next_number(start=1):
    """Höchste numerische Rechnungsnummer + 1 (mindestens `start`), dreistellig mit führenden Nullen."""
    with connect() as con:
        nums = [r[0] for r in con.execute("SELECT nummer FROM rechnungen")]
    highest = max((int(n) for n in nums if n.isdigit()), default=0)
    width = max([3] + [len(n) for n in nums if n.isdigit()])
    return str(max(highest + 1, int(start or 1))).zfill(width)


def number_taken(nummer, exclude_id=None):
    with connect() as con:
        r = con.execute("SELECT id FROM rechnungen WHERE nummer = ? AND id IS NOT ?",
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
            " zahlungsbedingung, gesamt, bezahlt) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", vals).lastrowid


def set_paid(inv_id, paid):
    with connect() as con:
        con.execute("UPDATE rechnungen SET bezahlt = ? WHERE id = ?", (int(bool(paid)), inv_id))


def delete_invoice(inv_id):
    with connect() as con:
        con.execute("DELETE FROM rechnungen WHERE id = ?", (inv_id,))

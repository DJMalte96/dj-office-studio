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
    email TEXT DEFAULT '',
    notiz TEXT DEFAULT '',                       -- seit 1.15: eigene Notizen (nur in der App, nie auf Belegen)
    weitere_namen TEXT DEFAULT '[]'              -- seit 1.16: Namen zusammengeführter Einträge (Rechnungen behalten ihren Namen)
);
-- seit 1.16: Paare, die laut Nutzer keine Duplikate sind
CREATE TABLE IF NOT EXISTS kunden_kein_duplikat (
    a INTEGER NOT NULL,
    b INTEGER NOT NULL,
    PRIMARY KEY (a, b)
);
-- seit 1.16: schon aus dem Postfach abgeholte Mails (Message-ID bzw. Ordner/UIDVALIDITY/UID) – nichts kommt doppelt
CREATE TABLE IF NOT EXISTS postfach_abgeholt (
    schluessel TEXT PRIMARY KEY,
    ordner TEXT,
    abgeholt TEXT DEFAULT CURRENT_TIMESTAMP
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
CREATE TABLE IF NOT EXISTS versand (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    art TEXT NOT NULL,                     -- rechnung | angebot | mahnung
    beleg_id INTEGER NOT NULL,             -- ID der Rechnung bzw. des Angebots
    mahnung_id INTEGER,
    an TEXT NOT NULL,
    betreff TEXT DEFAULT '',
    zeitpunkt TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS einstellungen (
    schluessel TEXT PRIMARY KEY,
    wert TEXT                              -- JSON-Wert
);
-- Finanzen (seit 1.1): Ausgaben mit Belegen
CREATE TABLE IF NOT EXISTS ausgaben (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'neu',          -- neu (hochgeladen, noch nicht geprüft) | ok
    belegdatum TEXT,
    bezahlt_am TEXT,
    lieferant TEXT DEFAULT '',
    beschreibung TEXT DEFAULT '',
    kategorie TEXT DEFAULT 'sonstiges',
    betrag REAL,                                 -- brutto, wie auf dem Beleg
    ust_satz REAL,                               -- Umsatzsteuer auf dem Beleg (für Vorsteuer), NULL = keine/unbekannt
    privatanteil REAL DEFAULT 0,                 -- Prozent
    beleg_datei TEXT,                            -- relativ zum Datenordner
    beleg_name TEXT,
    beleg_typ TEXT,                              -- pdf | xml | mail | msg | bild | unbekannt
    beleg_pruefsumme TEXT,
    mail_message_id TEXT,
    erkannt_json TEXT,                           -- Vorschläge und Fundstellen der Auswertung
    notiz TEXT DEFAULT '',
    rechnung_id INTEGER REFERENCES rechnungen(id) ON DELETE SET NULL,
    anlage_id INTEGER,
    paperless_id INTEGER,                        -- für die spätere Paperless-Anbindung
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ausgaben_pruefsumme ON ausgaben(beleg_pruefsumme);
-- Fahrten zu Veranstaltungen (automatisch je Rechnung oder von Hand)
-- Endgültig aus dem Papierkorb gelöscht: damit Paperless bzw. der Nur-lesen-Ordner sie nicht wieder hereinholen
CREATE TABLE IF NOT EXISTS ausgaben_geloescht (
    pruefsumme TEXT,
    paperless_id INTEGER,
    geloescht_am TEXT
);
-- Belege-Ordner im Nur-lesen-Modus (z. B. Ablage von Paperless): bereits gesehene Dateien
CREATE TABLE IF NOT EXISTS belege_ordner_dateien (
    pfad TEXT PRIMARY KEY,
    groesse INTEGER,
    geaendert REAL
);
CREATE TABLE IF NOT EXISTS fahrten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rechnung_id INTEGER REFERENCES rechnungen(id) ON DELETE SET NULL,
    datum TEXT NOT NULL,
    anlass TEXT DEFAULT '',
    start TEXT DEFAULT '',
    ziel TEXT DEFAULT '',
    km_einfach REAL,                             -- NULL = noch nicht berechnet
    hin_zurueck INTEGER DEFAULT 1,
    km_satz REAL DEFAULT 0.30,
    quelle TEXT DEFAULT 'auto',                  -- auto | korrigiert | hand
    fehler TEXT,                                 -- letzte Meldung der automatischen Berechnung
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
-- Anschaffungen über 800 € (Anlagenverzeichnis mit Abschreibung)
CREATE TABLE IF NOT EXISTS anlagen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bezeichnung TEXT NOT NULL,
    anschaffung_am TEXT,                         -- Kaufdatum
    kosten REAL,                                 -- Abschreibungsbasis (Kleinunternehmer brutto, sonst netto)
    nutzungsdauer INTEGER,                       -- Jahre (1 = Computer/Software, voll im Kaufjahr)
    restwert_start REAL,                         -- übernommen: Restwert zu Beginn von start_jahr …
    start_jahr INTEGER,
    rest_nutzungsdauer INTEGER,                  -- … und verbleibende Nutzungsdauer ab dann (Jahre)
    abgang_am TEXT,                              -- Verkauf / Verschrottung
    abgang_erloes REAL,
    ausgabe_id INTEGER,                          -- aus einer Ausgabe (Kategorie „Anschaffung über 800 €“)
    notiz TEXT DEFAULT '',
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
-- Einnahmen ohne Rechnung (z. B. Verkauf eines alten Geräts)
CREATE TABLE IF NOT EXISTS einnahmen_sonstige (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,
    beschreibung TEXT NOT NULL,
    betrag REAL NOT NULL,
    ust_satz REAL,
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS strecken_cache (
    schluessel TEXT PRIMARY KEY,                 -- geo:<adresse> bzw. km:<start>→<ziel>
    wert TEXT
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
-- seit 1.8: Jahresabschluss. Eine Zeile je Fassung; das Jahr ist zu, solange die neueste Fassung nicht wieder geöffnet ist.
CREATE TABLE IF NOT EXISTS jahresabschluss (
    jahr INTEGER NOT NULL,
    fassung INTEGER NOT NULL,
    abgeschlossen_am TEXT NOT NULL,
    gewinn REAL NOT NULL,
    euer_json TEXT NOT NULL,                     -- EÜR zum Zeitpunkt des Abschlusses
    pruefsumme TEXT NOT NULL,                    -- SHA-256 über die Dateien des Pakets
    datei TEXT NOT NULL,                         -- Paket, relativ zum Datenordner
    version TEXT DEFAULT '',                     -- App-Version beim Abschluss
    geoeffnet_am TEXT,                           -- wieder geöffnet (NULL = gilt noch)
    grund TEXT,
    PRIMARY KEY (jahr, fassung)
);
-- seit 1.9: Abos (wiederkehrende Ausgaben). Fällige Abbuchungen bestätigt man; erst dann gibt es eine Ausgabe.
CREATE TABLE IF NOT EXISTS abos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lieferant TEXT NOT NULL,
    beschreibung TEXT DEFAULT '',
    kategorie TEXT NOT NULL DEFAULT 'musik',
    betrag REAL NOT NULL,                        -- brutto, bis zur ersten Preisänderung
    rhythmus TEXT NOT NULL DEFAULT 'monatlich',  -- woechentlich | vierwochen | monatlich | … | eigen
    anzahl INTEGER DEFAULT 1,                    -- nur „eigen“: alle <anzahl> <einheit>
    einheit TEXT DEFAULT 'monate',               -- wochen | monate | jahre
    tag INTEGER DEFAULT 1,                       -- Tag im Monat (nicht bei Wochen-Rhythmen)
    beginn TEXT NOT NULL,
    ende TEXT,
    privatanteil REAL DEFAULT 0,
    erfasst_bis TEXT,                            -- Abbuchungen bis hierhin gelten als schon erfasst (nicht nachtragen)
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS abo_preise (
    abo_id INTEGER NOT NULL REFERENCES abos(id) ON DELETE CASCADE,
    ab TEXT NOT NULL,
    betrag REAL NOT NULL,
    PRIMARY KEY (abo_id, ab)
);
CREATE TABLE IF NOT EXISTS abo_termine (
    abo_id INTEGER NOT NULL REFERENCES abos(id) ON DELETE CASCADE,
    datum TEXT NOT NULL,
    status TEXT NOT NULL,                        -- ok (gebucht) | aus (nicht abgebucht)
    ausgabe_id INTEGER,
    PRIMARY KEY (abo_id, datum)
);
-- seit 1.13: Booking-Verträge (aus einem Angebot oder frei), Vertragsvorlage und Anlagen
CREATE TABLE IF NOT EXISTS vertraege (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nummer TEXT NOT NULL UNIQUE,                 -- V001, V002 …
    angebot_id INTEGER,                          -- NULL = Vertrag ohne Angebot
    angebot_nummer TEXT,
    kunde_id INTEGER,
    kunde_json TEXT NOT NULL,
    ort_json TEXT,                               -- abweichender Veranstaltungsort
    anlass TEXT NOT NULL DEFAULT '',
    datum TEXT NOT NULL DEFAULT '',
    von TEXT NOT NULL DEFAULT '',
    bis TEXT NOT NULL DEFAULT '',
    gage REAL NOT NULL DEFAULT 0,                -- Gesamtbetrag (brutto)
    kleinunternehmer INTEGER,
    felder_json TEXT NOT NULL DEFAULT '{}',      -- Aufbau, Ansprechpartner, Zahlung, Anzahlung, GEMA, Verpflegung …
    abschnitte_json TEXT NOT NULL DEFAULT '[]',  -- IDs der eingeschalteten Vorlage-Abschnitte
    status TEXT NOT NULL DEFAULT 'entwurf',      -- entwurf | verschickt | unterschrieben
    inhalt_json TEXT,                            -- festgehaltener Text ab „verschickt“
    verschickt_am TEXT,
    unterschrieben_json TEXT,                    -- {weg, am, notiz, dateiname}
    unterschrift_datei TEXT,                     -- relativ zu vertraege/unterschrieben
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS vertrag_abschnitte (
    id TEXT PRIMARY KEY,
    titel TEXT NOT NULL,
    text TEXT NOT NULL,
    an INTEGER NOT NULL DEFAULT 0,               -- standardmäßig in neuen Verträgen
    sortierung INTEGER NOT NULL DEFAULT 0,
    herkunft TEXT NOT NULL DEFAULT 'standard'    -- standard | eigen | Dateiname eines hochgeladenen Vertrags
);
CREATE TABLE IF NOT EXISTS vertrag_anlagen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    datei TEXT NOT NULL                          -- relativ zu vertraege/anlagen
);
-- seit 1.14: bar bezahlt – Quittung von Hand auf dem Quittungsblock; nur ein Vermerk für die Kundenakte, zählt nicht in der EÜR
CREATE TABLE IF NOT EXISTS barzahlungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,                         -- Tag, an dem das Geld kam
    betrag REAL NOT NULL,                        -- erhaltener Betrag (nur für die Kundenakte, nicht in der EÜR)
    kunde_id INTEGER,
    kunde_json TEXT NOT NULL,
    angebot_id INTEGER,
    vertrag_id INTEGER,
    anlass TEXT NOT NULL DEFAULT '',
    feier_datum TEXT NOT NULL DEFAULT '',
    quittung_nr TEXT NOT NULL DEFAULT '',
    beleg_datei TEXT,                            -- Foto vom Durchschlag, relativ zu barzahlungen/
    beleg_name TEXT,
    erstellt TEXT DEFAULT CURRENT_TIMESTAMP
);
-- seit 1.14: Jahres-Erinnerung für Stammkunden ausgeblendet („Diesmal nicht“ bis zum Jahrestag, „Nicht mehr erinnern“)
CREATE TABLE IF NOT EXISTS kunden_erinnerung (
    kunde TEXT PRIMARY KEY,                      -- Kundenname, klein geschrieben
    ruhe TEXT NOT NULL                           -- 'nie' oder Datum (JJJJ-MM-TT), bis zu dem nicht erinnert wird
);
-- seit 1.8: Kleinunternehmer und Fahrzeug je Jahr (fehlt ein Jahr: aktuelle Einstellungen)
CREATE TABLE IF NOT EXISTS jahr_einstellungen (
    jahr INTEGER PRIMARY KEY,
    kleinunternehmer INTEGER NOT NULL,
    fahrzeug TEXT NOT NULL
);
"""

# ---------- Sperre abgeschlossener Jahre (seit 1.8) ----------
# Die Datenbank selbst weist jede Änderung ab, die die EÜR eines abgeschlossenen Jahres verändern würde – egal über
# welchen Weg (Oberfläche, Hintergrundaufgabe, Import). Spalten ohne Einfluss auf Beträge (Notiz, Belegdatei …) bleiben frei.
GESPERRT = "DJOS_GESPERRT"
_ZU = "EXISTS (SELECT 1 FROM jahresabschluss WHERE geoeffnet_am IS NULL AND jahr = {})"
_ZU_AB = "EXISTS (SELECT 1 FROM jahresabschluss WHERE geoeffnet_am IS NULL AND jahr >= {})"
_J = "CAST(substr({}, 1, 4) AS INTEGER)"


def _ausgabe_zu(x):
    jahr = f"CAST(COALESCE({x}.euer_jahr, substr(COALESCE({x}.bezahlt_am, {x}.belegdatum), 1, 4)) AS INTEGER)"
    return f"({x}.status = 'ok' AND {_ZU.format(jahr)})"


def _rechnung_zu(x):
    jahr = (f"CASE WHEN {x}.storno_von IS NOT NULL THEN {_J.format(x + '.datum')}"
            f" WHEN {x}.bezahlt = 1 THEN {_J.format(x + '.bezahlt_am')} END")
    return _ZU.format(jahr)


def _anlage_plan_zu(x):
    return _ZU_AB.format(f"COALESCE({x}.start_jahr, {_J.format(x + '.anschaffung_am')})")


def _geaendert(spalten):
    return "(" + " OR ".join(f"OLD.{s} IS NOT NEW.{s}" for s in spalten) + ")"


def _sperr_trigger():
    """(name, tabelle, ereignis, bedingung) – Bedingung wahr → Änderung abweisen."""
    aus = ("status", "belegdatum", "bezahlt_am", "betrag", "kategorie", "privatanteil", "ust_satz", "euer_jahr")
    rech = ("datum", "positionen_json", "gesamt", "bezahlt", "bezahlt_am", "kleinunternehmer", "ust_satz", "storno_von")
    fahrt = ("datum", "km_einfach", "hin_zurueck", "km_satz")
    plan = ("kosten", "nutzungsdauer", "anschaffung_am", "restwert_start", "start_jahr", "rest_nutzungsdauer")
    abgang = ("abgang_am", "abgang_erloes")
    ein = ("datum", "betrag", "ust_satz")
    abg = lambda x: _ZU_AB.format(_J.format(x + ".abgang_am"))
    return [
        ("ausgaben_neu", "ausgaben", "INSERT", _ausgabe_zu("NEW")),
        ("ausgaben_aendern", "ausgaben", "UPDATE", f"{_geaendert(aus)} AND ({_ausgabe_zu('OLD')} OR {_ausgabe_zu('NEW')})"),
        ("ausgaben_loeschen", "ausgaben", "DELETE", _ausgabe_zu("OLD")),
        ("rechnungen_neu", "rechnungen", "INSERT", _rechnung_zu("NEW")),
        ("rechnungen_aendern", "rechnungen", "UPDATE", f"{_geaendert(rech)} AND ({_rechnung_zu('OLD')} OR {_rechnung_zu('NEW')})"),
        ("rechnungen_loeschen", "rechnungen", "DELETE", _rechnung_zu("OLD")),
        ("fahrten_neu", "fahrten", "INSERT", _ZU.format(_J.format("NEW.datum"))),
        ("fahrten_aendern", "fahrten", "UPDATE",
         f"{_geaendert(fahrt)} AND ({_ZU.format(_J.format('OLD.datum'))} OR {_ZU.format(_J.format('NEW.datum'))})"),
        ("fahrten_loeschen", "fahrten", "DELETE", _ZU.format(_J.format("OLD.datum"))),
        ("anlagen_neu", "anlagen", "INSERT", f"({_anlage_plan_zu('NEW')} OR {abg('NEW')})"),
        ("anlagen_plan", "anlagen", "UPDATE", f"{_geaendert(plan)} AND ({_anlage_plan_zu('OLD')} OR {_anlage_plan_zu('NEW')})"),
        ("anlagen_abgang", "anlagen", "UPDATE", f"{_geaendert(abgang)} AND ({abg('OLD')} OR {abg('NEW')})"),
        ("anlagen_loeschen", "anlagen", "DELETE", f"({_anlage_plan_zu('OLD')} OR {abg('OLD')})"),
        ("einnahmen_neu", "einnahmen_sonstige", "INSERT", _ZU.format(_J.format("NEW.datum"))),
        ("einnahmen_aendern", "einnahmen_sonstige", "UPDATE",
         f"{_geaendert(ein)} AND ({_ZU.format(_J.format('OLD.datum'))} OR {_ZU.format(_J.format('NEW.datum'))})"),
        ("einnahmen_loeschen", "einnahmen_sonstige", "DELETE", _ZU.format(_J.format("OLD.datum"))),
        ("jahre_neu", "jahr_einstellungen", "INSERT", _ZU.format("NEW.jahr")),
        ("jahre_aendern", "jahr_einstellungen", "UPDATE", f"({_ZU.format('OLD.jahr')} OR {_ZU.format('NEW.jahr')})"),
        ("jahre_loeschen", "jahr_einstellungen", "DELETE", _ZU.format("OLD.jahr")),
    ]


def _trigger_anlegen(con):
    """Bei jedem Start neu – so passen die Trigger auch nach dem Einspielen einer älteren Sicherung."""
    for name, tabelle, ereignis, bedingung in _sperr_trigger():
        con.execute(f"DROP TRIGGER IF EXISTS sperre_{name}")
        con.execute(f"CREATE TRIGGER sperre_{name} BEFORE {ereignis} ON {tabelle} WHEN {bedingung}"
                    f" BEGIN SELECT RAISE(ABORT, '{GESPERRT}'); END")


def ist_gesperrt_fehler(e):
    return isinstance(e, sqlite3.IntegrityError) and GESPERRT in str(e)


def abgeschlossene_jahre():
    with connect() as con:
        return {r[0] for r in con.execute("SELECT DISTINCT jahr FROM jahresabschluss WHERE geoeffnet_am IS NULL")}

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
    # 30 s statt 5 s warten, wenn gerade geschrieben wird – auf langsamen Geräten (Raspberry Pi, Texterkennung
    # im Hintergrund) dauert ein Schreibvorgang mal länger; sonst bricht eine Abfrage mit „database is locked“ ab
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init():
    with connect() as con:
        neu = not con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'rechnungen'").fetchone()
        con.executescript(SCHEMA)
        if neu:   # seit 1.12: nur bei einer neuen Installation einmal den Rundgang anbieten
            con.execute("INSERT OR IGNORE INTO einstellungen (schluessel, wert) VALUES ('_rundgang_anbieten', 'true')")
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
        # seit 1.1: Veranstaltungsort (Rechnung/Angebot) und „Fahrt erfassen“ (Rechnung)
        # seit 1.11: Anzahlungs-/Schlussrechnung, Herkunft aus einem Angebot, Nachfrage zum Angebot
        for tabelle, felder in (("rechnungen", (("veranstaltungsort_json", "TEXT"), ("fahrt_erfassen", "INTEGER DEFAULT 1"),
                                                ("rechnungsart", "TEXT DEFAULT 'normal'"), ("angebot_id", "INTEGER"),
                                                ("vertrag_id", "INTEGER"),     # seit 1.14: Rechnung aus einem Vertrag
                                                ("erechnung", "INTEGER DEFAULT 0"))),   # seit 1.15: ZUGFeRD eingebettet
                                ("angebote", (("veranstaltungsort_json", "TEXT"), ("nachgefragt_am", "TEXT"), ("nachgefragt_wie", "TEXT")))):
            vorhanden = {r["name"] for r in con.execute(f"PRAGMA table_info({tabelle})")}
            for spalte, typ in felder:
                if spalte not in vorhanden:
                    con.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")
        # seit 0.18.0: Steuer je Beleg festhalten (NULL = älterer Beleg → wie bisher nach aktueller Einstellung, ohne USt.)
        for tabelle in ("rechnungen", "angebote"):
            vorhanden = {r["name"] for r in con.execute(f"PRAGMA table_info({tabelle})")}
            for spalte, typ in (("kleinunternehmer", "INTEGER"), ("ust_satz", "REAL")):
                if spalte not in vorhanden:
                    con.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")
        # seit 1.5: Texterkennung für Fotos und Scans (ocr: wartet | laeuft | fertig | fehler | nicht_verfuegbar)
        vorhanden = {r["name"] for r in con.execute("PRAGMA table_info(ausgaben)")}
        if "ocr_versuche" not in vorhanden:
            con.execute("ALTER TABLE ausgaben ADD COLUMN ocr_versuche INTEGER DEFAULT 0")
        if "ocr" not in vorhanden:
            con.execute("ALTER TABLE ausgaben ADD COLUMN ocr TEXT")
            # einmalig: vorhandene, noch ungeprüfte Fotos und Scans ohne Betrag nachträglich lesen
            con.execute("UPDATE ausgaben SET ocr = 'wartet' WHERE status = 'neu' AND betrag IS NULL AND beleg_datei IS NOT NULL"
                        " AND (beleg_typ = 'bild' OR (beleg_typ = 'pdf' AND erkannt_json LIKE '%PDF ohne Text%'))")
        # seit 1.6: Papierkorb (status 'papierkorb'; status_vorher = 'neu' | 'ok' fürs Wiederherstellen)
        vorhanden = {r["name"] for r in con.execute("PRAGMA table_info(ausgaben)")}
        for spalte in ("status_vorher", "geloescht_am"):
            if spalte not in vorhanden:
                con.execute(f"ALTER TABLE ausgaben ADD COLUMN {spalte} TEXT")
        # seit 1.7.2: Absender beim Festschreiben festhalten (NULL = nicht festgeschrieben → aktuelle Einstellungen)
        for tabelle in ("rechnungen", "mahnungen"):
            if "absender_json" not in {r["name"] for r in con.execute(f"PRAGMA table_info({tabelle})")}:
                con.execute(f"ALTER TABLE {tabelle} ADD COLUMN absender_json TEXT")
        # seit 1.8: Jahr der EÜR abweichend vom Bezahlt-Datum (10-Tage-Regel für regelmäßige Zahlungen um Silvester)
        if "euer_jahr" not in {r["name"] for r in con.execute("PRAGMA table_info(ausgaben)")}:
            con.execute("ALTER TABLE ausgaben ADD COLUMN euer_jahr TEXT")
        # seit 1.15: Notizen zum Kunden (bewusst nicht in TABLES – Rechnungen speichern den Kunden mit, ohne Notiz)
        if "notiz" not in {r["name"] for r in con.execute("PRAGMA table_info(kunden)")}:
            con.execute("ALTER TABLE kunden ADD COLUMN notiz TEXT DEFAULT ''")
        if "weitere_namen" not in {r["name"] for r in con.execute("PRAGMA table_info(kunden)")}:   # seit 1.16
            con.execute("ALTER TABLE kunden ADD COLUMN weitere_namen TEXT DEFAULT '[]'")
        # seit 1.9: Ausgabe aus einem Abo
        if "abo_id" not in {r["name"] for r in con.execute("PRAGMA table_info(ausgaben)")}:
            con.execute("ALTER TABLE ausgaben ADD COLUMN abo_id INTEGER")
        _trigger_anlegen(con)
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
    fest = _absender_lesen(d.pop("absender_json", None))
    d["absender"] = fest if d["festgeschrieben"] else None      # ein Entwurf folgt immer den Einstellungen
    d["veranstaltungsort"] = json.loads(d.pop("veranstaltungsort_json", None) or "null")
    d["fahrt_erfassen"] = d.get("fahrt_erfassen", 1) != 0
    return d


def _absender_lesen(text):
    try:
        d = json.loads(text or "null")
    except ValueError:              # kann aus einer fremden Sicherung stammen
        return None
    return {k: v for k, v in d.items() if isinstance(v, (str, bool))} if isinstance(d, dict) else None


def _absender_text(absender):
    return json.dumps(absender) if absender else None


def _mahnung_aus_zeile(r):
    d = dict(r)
    d["absender"] = _absender_lesen(d.pop("absender_json", None))
    return d


def _ergaenzen(con, rechnungen):
    """Mahnungen und Storno-Bezug (Nummer/Datum der stornierten Rechnung) anhängen."""
    if not rechnungen:
        return rechnungen
    mahnungen = {}
    for m in con.execute("SELECT * FROM mahnungen ORDER BY stufe"):
        mahnungen.setdefault(m["rechnung_id"], []).append(_mahnung_aus_zeile(m))
    kopf = {r["id"]: {"nummer": r["nummer"], "datum": r["datum"]}
            for r in con.execute("SELECT id, nummer, datum FROM rechnungen")}
    versand = _versand(con, "rechnung", "mahnung")
    for inv in rechnungen:
        inv["mahnungen"] = mahnungen.get(inv["id"], [])
        inv["versand"] = versand.get(inv["id"], [])
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
        steuer = (_ku(inv.get("kleinunternehmer")), inv.get("ust_satz"))
        ort = (json.dumps(inv["veranstaltungsort"]) if inv.get("veranstaltungsort") else None,
               int(inv.get("fahrt_erfassen", True) is not False))
        art = (inv.get("rechnungsart") or "normal", inv.get("angebot_id"), inv.get("vertrag_id"), int(bool(inv.get("erechnung"))))
        if inv_id:
            con.execute(
                "UPDATE rechnungen SET nummer=?, datum=?, kunde_id=?, kunde_json=?,"
                " positionen_json=?, zahlungsbedingung=?, gesamt=?, bezahlt=?, kleinunternehmer=?, ust_satz=?,"
                " veranstaltungsort_json=?, fahrt_erfassen=?, rechnungsart=?, angebot_id=COALESCE(?, angebot_id),"
                " vertrag_id=COALESCE(?, vertrag_id), erechnung=? WHERE id=?",
                vals + steuer + ort + art + (inv_id,))
            return inv_id
        return con.execute(
            "INSERT INTO rechnungen (nummer, datum, kunde_id, kunde_json, positionen_json,"
            " zahlungsbedingung, gesamt, bezahlt, festgeschrieben, storno_von, bezahlt_am, kleinunternehmer, ust_satz,"
            " veranstaltungsort_json, fahrt_erfassen, absender_json, rechnungsart, angebot_id, vertrag_id, erechnung)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            vals + (int(bool(inv.get("festgeschrieben"))), inv.get("storno_von"), inv.get("bezahlt_am")) + steuer + ort
            + (_absender_text(inv.get("absender")) if inv.get("festgeschrieben") else None,) + art).lastrowid


def _ku(wert):
    return None if wert is None else int(bool(wert))


# Festschreiben und Absender festhalten gehören zusammen – deshalb ist „absender“ überall Pflicht.
# Ein einmal festgehaltener Absender wird nie überschrieben.
_FEST = " festgeschrieben = 1, absender_json = CASE WHEN festgeschrieben = 1 AND absender_json IS NOT NULL THEN absender_json ELSE ? END"


def set_paid(inv_id, paid, absender):
    """Bezahlt setzen (mit Datum) – eine bezahlte Rechnung wird damit auch festgeschrieben."""
    with connect() as con:
        if paid:
            con.execute("UPDATE rechnungen SET bezahlt = 1," + _FEST + ","
                        " bezahlt_am = COALESCE(bezahlt_am, date('now', 'localtime')) WHERE id = ?",
                        (_absender_text(absender), inv_id))
        else:
            con.execute("UPDATE rechnungen SET bezahlt = 0, bezahlt_am = NULL WHERE id = ?", (inv_id,))


def festschreiben(inv_id, absender):
    with connect() as con:
        con.execute("UPDATE rechnungen SET" + _FEST + " WHERE id = ?", (_absender_text(absender), inv_id))


def set_storniert(inv_id, storno_id, absender):
    with connect() as con:
        con.execute("UPDATE rechnungen SET storniert_durch = ?," + _FEST + " WHERE id = ?",
                    (storno_id, _absender_text(absender), inv_id))


def absender_nachtragen(absender):
    """Festgeschriebenes ohne festgehaltenen Absender (Bestand von vor 1.7.2, ältere Sicherung) → Anzahl."""
    text = _absender_text(absender)
    if not text:
        return 0
    with connect() as con:
        return (con.execute("UPDATE rechnungen SET absender_json = ? WHERE festgeschrieben = 1 AND absender_json IS NULL", (text,)).rowcount
                + con.execute("UPDATE mahnungen SET absender_json = ? WHERE absender_json IS NULL", (text,)).rowcount)


# ---------- Mahnungen ----------

def add_mahnung(inv_id, stufe, datum, frist, absender):
    with connect() as con:
        return con.execute("INSERT INTO mahnungen (rechnung_id, stufe, datum, frist, absender_json) VALUES (?, ?, ?, ?, ?)",
                           (inv_id, stufe, datum, frist, _absender_text(absender))).lastrowid


def get_mahnung(mahnung_id):
    with connect() as con:
        r = con.execute("SELECT * FROM mahnungen WHERE id = ?", (mahnung_id,)).fetchone()
        return _mahnung_aus_zeile(r) if r else None


# ---------- E-Mail-Versand ----------

def _versand(con, *arten):
    """Versand-Protokoll je Beleg (älteste zuerst)."""
    out = {}
    for v in con.execute(f"SELECT * FROM versand WHERE art IN ({', '.join('?' * len(arten))}) ORDER BY id", arten):
        out.setdefault(v["beleg_id"], []).append(dict(v))
    return out


def add_versand(art, beleg_id, an, betreff, mahnung_id=None):
    with connect() as con:
        return con.execute("INSERT INTO versand (art, beleg_id, mahnung_id, an, betreff) VALUES (?, ?, ?, ?, ?)",
                           (art, beleg_id, mahnung_id, an, betreff)).lastrowid


def get_customer(kunde_id):
    with connect() as con:
        r = con.execute("SELECT * FROM kunden WHERE id = ?", (kunde_id,)).fetchone()
        return dict(r) if r else None


def set_customer_email(kunde_id, email):
    with connect() as con:
        con.execute("UPDATE kunden SET email = ? WHERE id = ?", (email, kunde_id))


# ---------- Datensicherung ----------

GEHEIM = ("smtp_passwort", "paperless_token")   # wird nicht in herunterladbare Sicherungen übernommen

def sichern(ziel_pfad):
    """Konsistente Kopie der Datenbank (auch während die App läuft)."""
    quelle = connect()
    ziel = sqlite3.connect(ziel_pfad)
    try:
        quelle.backup(ziel)
    finally:
        ziel.close()
        quelle.close()


def geheimnisse_entfernen(pfad):
    """Passwörter aus einer Sicherungskopie löschen (die Kopie kann weitergegeben oder in die Cloud gelegt werden)."""
    con = sqlite3.connect(pfad)
    try:
        con.execute(f"DELETE FROM einstellungen WHERE schluessel IN ({', '.join('?' * len(GEHEIM))})", GEHEIM)
        con.commit()
        con.execute("VACUUM")   # gelöschte Werte auch physisch aus der Datei entfernen
    finally:
        con.close()


def pruefe_sicherung(pfad):
    """Prüft, ob die Datei eine Datenbank von DJ Office Studio ist; gibt Anzahlen zurück."""
    # nur lesend öffnen; as_uri() ergibt auch unter Windows eine gültige file:-Adresse.
    # Die Verbindung wird in jedem Fall geschlossen – Windows kann die Datei sonst nicht löschen.
    con = sqlite3.connect(Path(pfad).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"rechnungen", "kunden"} <= tabellen:
            raise ValueError("Die Datei enthält keine Daten von DJ Office Studio.")
        ohne = {"ausgaben": " WHERE status != 'papierkorb'"}    # Gelöschtes nicht mitzählen
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}{ohne.get(t, '')}").fetchone()[0]
                for t in ("rechnungen", "kunden", "angebote", "ausgaben") if t in tabellen}
    except sqlite3.DatabaseError as e:
        raise ValueError("Die Datei ist keine gültige Sicherung.") from e
    finally:
        con.close()


def wiederherstellen(pfad):
    """Inhalt der aktuellen Datenbank durch die Sicherung ersetzen und Schema auf Stand bringen.
    Gespeicherte Passwörter bleiben erhalten, wenn die Sicherung keine enthält."""
    geheim = {k: v for k, v in get_settings().items() if k in GEHEIM and v}
    quelle = sqlite3.connect(pfad)
    ziel = connect()
    try:
        quelle.backup(ziel)
    finally:
        quelle.close()
        ziel.close()
    init()
    vorhanden = get_settings()
    save_settings({k: v for k, v in geheim.items() if not vorhanden.get(k)})


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
    d["veranstaltungsort"] = json.loads(d.pop("veranstaltungsort_json", None) or "null")
    d["art"] = "angebot"
    return d


def _mit_versand(con, angebote):
    versand = _versand(con, "angebot")
    for a in angebote:
        a["versand"] = versand.get(a["id"], [])
    return angebote


def list_offers():
    with connect() as con:
        return _mit_versand(con, [_offer_from_row(r) for r in con.execute(
            "SELECT * FROM angebote ORDER BY datum DESC, nummer DESC")])


def get_offer(offer_id):
    with connect() as con:
        r = con.execute("SELECT * FROM angebote WHERE id = ?", (offer_id,)).fetchone()
        return _mit_versand(con, [_offer_from_row(r)])[0] if r else None


def save_offer(a, offer_id=None):
    vals = (a["nummer"], a["datum"], a["gueltig_bis"], a.get("kunde_id"), json.dumps(a["kunde"]),
            json.dumps(a["positionen"]), a["zahlungsbedingung"], a["hinweise"], a["gesamt"],
            _ku(a.get("kleinunternehmer")), a.get("ust_satz"),
            json.dumps(a["veranstaltungsort"]) if a.get("veranstaltungsort") else None)
    with connect() as con:
        if offer_id:
            con.execute(
                "UPDATE angebote SET nummer=?, datum=?, gueltig_bis=?, kunde_id=?, kunde_json=?,"
                " positionen_json=?, zahlungsbedingung=?, hinweise=?, gesamt=?, kleinunternehmer=?, ust_satz=?,"
                " veranstaltungsort_json=? WHERE id=?",
                vals + (offer_id,))
            return offer_id
        return con.execute(
            "INSERT INTO angebote (nummer, datum, gueltig_bis, kunde_id, kunde_json, positionen_json,"
            " zahlungsbedingung, hinweise, gesamt, kleinunternehmer, ust_satz, veranstaltungsort_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals).lastrowid


def set_offer_status(offer_id, status, rechnung_id=None):
    with connect() as con:
        if rechnung_id:
            con.execute("UPDATE angebote SET status = ?, rechnung_id = ? WHERE id = ?",
                        (status, rechnung_id, offer_id))
        else:
            con.execute("UPDATE angebote SET status = ? WHERE id = ?", (status, offer_id))


def set_offer_nachgefragt(offer_id, am, wie=""):
    """Nachfrage zum Angebot vermerken (am = None: Vermerk zurücknehmen)."""
    with connect() as con:
        con.execute("UPDATE angebote SET nachgefragt_am = ?, nachgefragt_wie = ? WHERE id = ?",
                    (am, (wie or "")[:200] if am else None, offer_id))


def anzahlung_verrechnet(anzahlung_id, ausser=None):
    """Gültige Rechnung (nicht storniert, keine Stornorechnung), die diese Anzahlung abzieht – sonst None."""
    with connect() as con:
        for r in con.execute("SELECT id, nummer, positionen_json FROM rechnungen WHERE storno_von IS NULL"
                             " AND storniert_durch IS NULL AND rechnungsart = 'schluss' AND id IS NOT ?", (ausser,)):
            if any(p.get("anzahlung_id") == anzahlung_id for p in json.loads(r["positionen_json"])):
                return {"id": r["id"], "nummer": r["nummer"]}
    return None


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

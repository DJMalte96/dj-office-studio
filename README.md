<img src="rechnungen/logo.png" alt="DJ Office Studio" width="250">

# DJ Office Studio

Eine Home-Assistant-App zum Schreiben von DJ-Rechnungen und -Angeboten. Kunden auswählen, Rechnungsposten und Uhrzeiten eintragen, Preis festlegen – fertig ist das PDF im Layout der bisherigen Word-Vorlage.

![Screenshot: Rechnung erstellen](docs/bilder/rechnungseditor.png)

## Funktionen

- **Startseite** mit Kacheln für alle Aktionen der App und dem Status der Rechnungen: offene Rechnungen mit Restzeit und Warnung bei Überfälligkeit, Umsatz nach Monat/Jahr und die letzten Rechnungen.
- **Rechnungseditor**
  - Kunde mit Autovervollständigung aus bisherigen Kunden; neue Kunden werden beim Speichern automatisch angelegt
  - Positionen per **Rechnungsposten** (Hochzeit, Geburtstag, Firmenfeier, …) mit **von/bis-Zeiten** – der Rechnungstext wird daraus erzeugt, z. B. „DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr“
  - Freitext-Positionen für alles andere (z. B. Fahrtkosten)
  - Preis wird pro Position individuell eingetragen
  - Auswählbare Zahlungsbedingungen (Überweisung 8/14 Tage, bar erhalten, …)
  - Fortlaufende Rechnungsnummer (dreistellig, Startwert einstellbar)
- **PDF** im A4-Layout mit Absenderzeile, Adressfeld, Positionstabelle und Fußzeile (Bankverbindung, Steuernummer, Kleinunternehmer-Hinweis nach §19 UStG). Vorschau vor dem Speichern; beim Speichern wird eine Kopie im Ordner `/share/rechnungen` abgelegt.
- **Offene Rechnungen** auf einen Blick: eine Summenzeile mit Anzahl, Gesamtbetrag und nächster Frist; darunter je Rechnung Rechnungsname (z. B. `Rechnung_037_311026`), Betrag, verbleibende Zeit („noch 5 Tage“, „3 Tage überfällig“) , ein Haken zum Abhaken, wenn bezahlt wurde, und ein ✕ zum direkten Löschen. Das Zahlungsziel wird aus der Zahlungsbedingung gelesen (z. B. „innerhalb der nächsten 8 Tage“) und ab dem Rechnungsdatum gerechnet.
- **Archiv** für bezahlte Rechnungen: Wird eine offene Rechnung abgehakt, wandert sie ins Archiv – mit Suche und Sortierung nach Nummer, Datum, Betrag oder Kunde. Rechnungen lassen sich jederzeit bearbeiten oder wieder auf „offen“ setzen. Mehrere Rechnungen markieren und **als ZIP herunterladen** oder **an Paperless-ngx senden**.
- **Angebote**: Im selben Editor wie Rechnungen (Kunde, Rechnungsposten mit von/bis-Zeiten, Preise) – mit eigenem Nummernkreis, Angebotsdatum, **Gültig bis** (Bindefrist, Standard 30 Tage), optionaler Zahlungsbedingung und freien **Hinweisen** (z. B. Verlängerungsstunde, Leistungsumfang, GEMA). Das PDF hat dasselbe Layout wie die Rechnung (`Angebot_001_120627.pdf`). Oben in der Angebotsansicht und auf der Startseite: **Offene Angebote** mit Angebotsdatum und Restlaufzeit („noch 12 Tage“, „seit 3 Tagen abgelaufen“), auf der Startseite zusätzlich ein Hinweis, wenn ein Angebot in den nächsten 3 Tagen abläuft. In der Angebotsliste: mehrere markieren und als ZIP herunterladen oder an Paperless senden, Status (offen / angenommen / abgelehnt), Restlaufzeit bzw. „abgelaufen“ und **→ Rechnung**, das Kunde und Positionen in eine neue Rechnung übernimmt und das Angebot als angenommen markiert.
- **Import alter Rechnungen und Angebote**: Bisherige PDFs hochladen (gemischt möglich – die App erkennt Rechnung oder Angebot selbst). Empfänger, Positionen und Vorschläge für Rechnungsposten werden erkannt und können übernommen werden, optional auch die Rechnungen selbst als Archiv und die Angebote (mit „gültig bis“ und Hinweisen) in die Angebotsliste.
- **Stammdaten** für Kunden, Rechnungsposten und Zahlungsbedingungen.
- Helles und dunkles Design (folgt der Geräteeinstellung).

## Installation

1. In Home Assistant **Einstellungen → Apps → App-Store** öffnen.
2. Oben rechts **⋮ → Repositories** wählen und diese URL hinzufügen:
   ```
   https://github.com/DJMalte96/ha-rechnungen
   ```
3. **DJ Office Studio** im App-Store auswählen und **Installieren**. Beim ersten Mal wird das Image gebaut – das dauert ein paar Minuten.
4. **Starten** und „In Seitenleiste anzeigen“ aktivieren.
5. In der App oben rechts auf **⚙** klicken und Absenderdaten, Bankverbindung usw. eintragen (siehe unten).

## Einstellungen

Alle Einstellungen werden **in der App** gemacht: oben rechts auf **⚙** klicken.

![Screenshot: Einstellungen](docs/bilder/einstellungen.png)

| Bereich | Felder |
|---|---|
| Absender | Name (Absender, Gruß, Kontoinhaber), Straße, PLZ und Ort, Telefon, Ort vor dem Datum („Musterstadt, den …“) |
| Bankverbindung | Bank, abweichender Kontoinhaber, IBAN, BIC |
| Steuer | Steuernummer, Kleinunternehmer-Hinweis nach §19 UStG |
| Nummern & Fristen | Rechnungen ab Nr., Angebote ab Nr. (danach wird automatisch hochgezählt), Gültigkeit neuer Angebote in Tagen |
| Ablage & Paperless | Ordner für PDF-Kopien (Standard `/share/rechnungen`), „Paperless-ngx ist installiert“, Paperless-Eingangsordner |

Unten auf der Seite steht außerdem die installierte Version mit Link zum Changelog.

Die Angaben erscheinen in Absenderzeile, Gruß und Fußzeile jeder Rechnung und jedes Angebots. Solange Name oder IBAN fehlen, zeigt die App oben einen Hinweis mit Link zu den Einstellungen.

> **Umstieg von älteren Versionen:** Bis Version 0.8 wurden diese Werte in Home Assistant unter *Einstellungen → Apps → DJ Office Studio → Konfiguration* eingetragen. Version 0.9.0 übernimmt sie beim ersten Öffnen der App automatisch in die eigenen Einstellungen; ab 0.9.1 gibt es die Felder in Home Assistant nicht mehr. Wer direkt von 0.8 oder älter auf 0.9.1 oder neuer aktualisiert, trägt die Werte einmal unter ⚙ neu ein.

### Paperless-ngx

Ist unter ⚙ Einstellungen „Paperless-ngx ist installiert“ eingeschaltet, gibt es im Archiv bei markierten Rechnungen und in der Angebotsliste bei markierten Angeboten den Button **⇪ An Paperless senden** (sonst ist er ausgeblendet). Jede Rechnung wird als komplette PDF-Datei (z. B. `Rechnung_037_311026.pdf`) in den Eingangsordner von Paperless gelegt – Titel, Korrespondent, Dokumenttyp, Tags usw. vergibt Paperless anschließend selbst (z. B. über Zuweisungsregeln oder die automatische Zuordnung). Übertragene Rechnungen sind im Archiv mit „Paperless ✓“ gekennzeichnet; ein Klick darauf setzt die Markierung zurück (z. B. wenn das Dokument in Paperless gelöscht wurde).

- Der Paperless-Eingangsordner muss auf den Eingangsordner (consume) der Paperless-App zeigen – welcher das ist, steht in der Konfiguration der Paperless-App. Der Ordner muss unter `/share` oder `/media` liegen, damit DJ Office Studio darauf zugreifen kann.
- Existiert der Ordner nicht, meldet die App einen Fehler, statt ihn anzulegen – so landen keine PDFs unbemerkt im falschen Ordner.

## Bedienung

Oben in der Kopfzeile gibt es auf jeder Seite das Menü: **Start**, **Rechnungen** (Neue Rechnung, Rechnungen), **Angebote** (Neues Angebot, Angebote) und **Stammdaten** (Kunden, Rechnungsposten, Zahlungsbedingungen).


**Start:** Die Startseite öffnet sich beim Aufruf. Über das Menü oder die Kacheln geht es direkt zu jedem Bereich der App (inkl. Import alter Rechnungen und Angebote). Ein Klick auf das Logo führt zurück zur Startseite. Darunter steht der aktuelle Stand: offene Rechnungen mit Restzeit, offene Angebote mit Restlaufzeit, Umsatz und die letzten Rechnungen – plus Hinweise bei überfälligen Rechnungen und bald ablaufenden Angeboten.

![Screenshot: Startseite](docs/bilder/startseite.png)

**Neue Rechnung:** Kundennamen eintippen und einen Vorschlag übernehmen (oder neue Adresse eingeben). Pro Position einen Rechnungsposten wählen, von/bis eintragen, Lieferdatum und Preis ergänzen. Zahlungsbedingung wählen, dann **PDF-Vorschau** oder **Rechnung speichern & PDF öffnen**.

**Angebote:** Über **Angebote → Neues Angebot** im selben Editor schreiben – zusätzlich mit **Gültig bis** und freien **Hinweisen** (z. B. Verlängerungsstunde, GEMA). In **Angebote → Angebote** stehen oben die offenen Angebote mit Restlaufzeit, darunter alle Angebote mit Status (offen / angenommen / abgelehnt). **→ Rechnung** macht aus einem Angebot eine neue Rechnung und markiert es als angenommen.

![Screenshot: Angebote](docs/bilder/angebote.png)

**Rechnungsposten:** Unter **Stammdaten → Rechnungsposten** neue Rechnungsposten (z. B. Hochzeit) anlegen. Ohne eigene Text-Vorlage wird `DJ – Tätigkeit <Bezeichnung> – {von} Uhr bis {bis} Uhr` verwendet; `{von}` und `{bis}` werden durch die Uhrzeiten ersetzt.

**Alte Rechnungen und Angebote importieren:** Unter **Rechnungen** (Archiv) auf **Alte Rechnungen importieren** bzw. unter **Angebote** auf **Alte Angebote importieren** klicken und PDFs hineinziehen – gemischt möglich. Danach auswählen, welche Empfänger, Rechnungsposten, Rechnungen und Angebote übernommen werden. Erkannt werden PDFs mit echtem Text im Aufbau der Vorlage (Absenderzeile mit „|“, Adresse, „Rechnung Nr.“ bzw. „Angebot“, Tabelle, „Gesamt“). Eingescannte Dokumente werden nicht unterstützt.

## Ohne Home Assistant (Windows / Mac)

DJ Office Studio gibt es auch als eigenständige App für **Windows** und **macOS** – ohne Home Assistant, ohne Python, ohne Docker. Funktionen und Oberfläche sind dieselben.

**Herunterladen:** Auf der GitHub-Seite unter **Releases** die passende ZIP-Datei laden:

| System | Datei |
|---|---|
| Windows 10/11 | `DJ-Office-Studio-…-Windows.zip` |
| Mac mit Apple-Chip (M1 und neuer) | `DJ-Office-Studio-…-macOS-AppleSilicon.zip` |
| Mac mit Intel-Prozessor | `DJ-Office-Studio-…-macOS-Intel.zip` |

**Windows:** ZIP entpacken (Rechtsklick → *Alle extrahieren*), im Ordner `DJ Office Studio` die Datei **DJ Office Studio.exe** starten. Beim ersten Start warnt Windows ggf. („Der Computer wurde durch Windows geschützt“) – auf **Weitere Informationen → Trotzdem ausführen** klicken. Die App ist nicht kostenpflichtig signiert, daher die Warnung.

**Mac:** ZIP per Doppelklick entpacken und **DJ Office Studio** in den Ordner *Programme* ziehen. Beim ersten Öffnen meldet macOS, dass der Entwickler nicht verifiziert werden kann: dann unter *Systemeinstellungen → Datenschutz & Sicherheit* ganz unten auf **Dennoch öffnen** klicken (einmalig).

**Benutzung:** Nach dem Start öffnet sich die Oberfläche im Browser, dazu ein kleines Fenster „DJ Office Studio läuft“. Solange dieses Fenster offen ist, läuft die App; Schließen beendet sie. Alles Weitere – Absender, Bankverbindung usw. – unter **⚙ Einstellungen**.

**Daten:** Alles liegt im Dokumente-Ordner unter `DJ Office Studio` – `Daten` (Datenbank mit Kunden, Rechnungen, Angeboten, Einstellungen) und `PDFs` (Kopien aller Rechnungen und Angebote). Für ein Backup einfach diesen Ordner sichern. Die App ist nur auf dem eigenen Rechner erreichbar.

**Update:** Neue ZIP herunterladen und die alte App ersetzen – die Daten im Dokumente-Ordner bleiben erhalten.

## Daten & Backup

| Was | Wo |
|---|---|
| Kunden, Rechnungsposten, Zahlungsbedingungen, Rechnungen, Angebote, Einstellungen | SQLite-Datenbank `rechnungen.db` im App-Datenordner (`/data`) |
| PDF-Kopien | Ordner aus den Einstellungen, standardmäßig `/share/rechnungen` (z. B. per Samba erreichbar) |

Beides ist in den normalen Home-Assistant-Backups enthalten.

## Changelog

Alle Änderungen je Version stehen in [rechnungen/CHANGELOG.md](rechnungen/CHANGELOG.md) – Home Assistant zeigt sie auch beim Update an.

## Lokale Entwicklung

Voraussetzung: Python 3.9 oder neuer (im Container läuft 3.12).

```bash
cd rechnungen
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

mkdir -p /tmp/djos
DATA_DIR=/tmp/djos OPTIONS_PATH=/tmp/djos/options.json python app/main.py
```

Die Oberfläche läuft dann unter <http://localhost:8099>; Absenderdaten usw. unter ⚙ eintragen.

Desktop-Version lokal starten bzw. bauen (Ergebnis in `dist/`):

```bash
python desktop/start.py                       # aus dem Quellcode starten
pip install pyinstaller pillow && python desktop/build.py   # App bauen (auf dem jeweiligen System)
```

Die fertigen Windows- und Mac-Versionen baut GitHub Actions (`.github/workflows/desktop.yml`); ein Tag `desktop-v…` erzeugt daraus ein Release. Für die PDFs wird eine TTF-Schrift gesucht (im Container Carlito, lokal z. B. Arial); mit `FONT_REGULAR` und `FONT_BOLD` lässt sich ein eigener Pfad setzen.

### Aufbau

```
repository.yaml          Home-Assistant-Repository
rechnungen/
  config.yaml            App-Definition (Name, Version)
  icon.png, logo.png     Symbol und Logo für den App-Store in Home Assistant
  CHANGELOG.md           Änderungen je Version
  Dockerfile             Python 3.12 (Debian) + Carlito-Schrift
  app/
    main.py              Flask-App: REST-API und Auslieferung der Oberfläche
    db.py                SQLite-Datenhaltung
    pdf.py               PDF-Erzeugung (fpdf2)
    importer.py          Auslesen alter Rechnungs- und Angebots-PDFs (pypdf)
    static/              Oberfläche (HTML, CSS, JavaScript)
desktop/
  start.py               Starter der Desktop-Version (Server + Statusfenster, Daten im Dokumente-Ordner)
  build.py               Baut die Desktop-App mit PyInstaller
.github/workflows/
  desktop.yml            Baut Windows- und Mac-Version, bei Tag „desktop-v…“ als Release
```

### Neue Version veröffentlichen

`version` in `rechnungen/config.yaml` erhöhen, einen Eintrag in `rechnungen/CHANGELOG.md` ergänzen, committen und pushen. Home Assistant bietet das Update dann unter **Apps → App-Store → ⋮ → Nach Updates suchen** an. Für die Desktop-Version zusätzlich einen Tag `desktop-v<Version>` pushen – GitHub Actions baut dann die Windows- und Mac-Pakete und veröffentlicht sie als Release.

> Hinweis: Das Basis-Image ist im `Dockerfile` fest vorgegeben. Eine `build.yaml` wird vom Supervisor nicht beachtet – er würde sonst sein Alpine-Image verwenden, in dem `apt-get` fehlt.

# Changelog

Alle Änderungen an DJ Office Studio. Neueste Version oben.

## 0.8.3 – 2026-11-16

### Neu
- Neue Option **`angebot_startnummer`** (Standard: 1): Ab dieser Nummer zählen die Angebote. Wie bei Rechnungen gilt: Gibt es schon höhere Angebotsnummern, wird ab der höchsten weitergezählt.

## 0.8.2 – 2026-11-16

### Geändert
- **Neues Menü** in der Kopfzeile – jetzt auch auf der Startseite: **Rechnungen** (Neue Rechnung, Rechnungen), **Angebote** (Neues Angebot, Angebote) und **Stammdaten** (Kunden, Rechnungsposten, Zahlungsbedingungen) als aufklappbare Untermenüs.
- Hinweis zu fehlenden Absenderdaten nennt jetzt den richtigen App-Namen („Apps → DJ Office Studio → Konfiguration“).

## 0.8.1 – 2026-11-16

### Neu
- **Alte Angebote importieren**: Der Import nimmt jetzt auch Angebots-PDFs an – gemischt mit Rechnungen, die App erkennt selbst, was was ist. Erkannt werden Angebotsnummer, Datum, Empfänger, Positionen, **gültig bis** (als Datum oder z. B. „14 Tage gültig“) und die **Hinweise**. Angebote ohne Nummer bekommen beim Übernehmen die nächste freie Nummer.
- Beim Übernehmen lässt sich der Status der importierten Angebote wählen (offen / angenommen / abgelehnt).
- In der Angebotsliste gibt es dafür den Button **⇪ Alte Angebote importieren**; die Startseiten-Kachel „Importieren“ gilt für beides.

## 0.8.0 – 2026-11-16

### Neu
- **Angebote schreiben**: Neuer Bereich **Angebote** (Menü und Startseite: „Neues Angebot“, „Angebote“). Angebote entstehen im gewohnten Editor – mit Kunden-Autovervollständigung, Rechnungsposten und von/bis-Zeiten.
- Inhalt eines Angebots: Angebotsnummer (eigener Nummernkreis ab 001), Angebotsdatum, **Gültig bis** (Bindefrist), Positionen mit Datum der Veranstaltung und Preis, Gesamtsumme, optionale Zahlungsbedingung und freie **Hinweise** (z. B. Preis je Verlängerungsstunde, Leistungsumfang, GEMA-Anmeldung). Absender, Bankverbindung, Steuernummer und Kleinunternehmer-Hinweis stehen wie bei der Rechnung in der Fußzeile.
- PDF im Layout der Rechnung, Dateiname z. B. `Angebot_001_120627.pdf`; eine Kopie landet wie gewohnt im PDF-Ordner.
- **Angebotsliste** mit Suche, Status (offen / angenommen / abgelehnt) und Restlaufzeit bzw. „abgelaufen“.
- **→ Rechnung**: Übernimmt Kunde, Positionen und ggf. Zahlungsbedingung in eine neue Rechnung; beim Speichern wird das Angebot automatisch als „angenommen“ markiert und mit der Rechnung verknüpft.
- Neue Option `angebot_gueltigkeit_tage` (Standard 30) für die vorgeschlagene Bindefrist.

### Geändert
- Startseite: Kacheln jetzt in zwei Reihen à vier (mit „Neues Angebot“ und „Angebote“).

## 0.7.2 – 2026-11-16

### Neu
- Die Markierung **„Paperless ✓“** im Archiv lässt sich per Klick (mit Rückfrage) **zurücksetzen** – z. B. wenn das Dokument in Paperless gelöscht wurde. Die Rechnung kann danach ohne Dubletten-Nachfrage erneut gesendet werden.

## 0.7.1 – 2026-11-16

### Neu
- Neue Option **`paperless_installiert`** (Standard: aus). Nur wenn sie eingeschaltet ist, erscheint im Archiv der Button **⇪ An Paperless senden** – wer Paperless nicht nutzt, sieht ihn nicht.

## 0.7.0 – 2026-11-16

### Geändert
- **Paperless über den Eingangsordner**: „An Paperless senden“ legt die PDFs jetzt einfach in den Eingangsordner (consume) von Paperless – keine Adresse, kein API-Token und keine Port-Freigabe mehr nötig. Paperless liest sie von dort automatisch ein.
- Neue Option `paperless_eingangsordner` (Standard: `/share/paperless/consume`); `paperless_url` und `paperless_token` entfallen.

## 0.6.2 – 2026-11-16

### Geändert
- Der Button **⇪ An Paperless senden** ist bei markierten Rechnungen jetzt immer sichtbar. Ist Paperless noch nicht eingerichtet, erklärt ein Hinweis, was in der Konfiguration einzutragen ist (vorher war der Button dann einfach ausgeblendet).

## 0.6.1 – 2026-11-16

### Geändert
- **Paperless**: Es wird nur noch die komplette PDF-Datei übertragen – ohne Titel, Datum, Korrespondent, Dokumenttyp oder Tags. Die weitere Verarbeitung übernimmt Paperless selbst.
- Die Optionen `paperless_dokumenttyp`, `paperless_tags` und `paperless_kunde_als_korrespondent` entfallen; es bleiben `paperless_url` und `paperless_token`.

## 0.6.0 – 2026-11-16

### Neu
- **An Paperless-ngx senden**: Markierte Rechnungen im Archiv lassen sich mit **⇪ An Paperless senden** direkt an Paperless übertragen – mit Titel, Rechnungsdatum, Kunde als Korrespondent, Dokumenttyp und Tags (fehlende werden in Paperless automatisch angelegt).
- Bereits übertragene Rechnungen sind im Archiv mit **„Paperless ✓“** markiert; vor einem erneuten Senden fragt die App nach, damit keine Dubletten entstehen.
- Neue Optionen in der Konfiguration: `paperless_url`, `paperless_token`, `paperless_dokumenttyp`, `paperless_tags`, `paperless_kunde_als_korrespondent`. Ohne URL und Token bleibt der Button ausgeblendet.

## 0.5.7 – 2026-11-16

### Neu
- **Mehrere Rechnungen herunterladen**: Im Archiv gibt es vorne in jeder Zeile ein Kästchen zum Markieren, in der Kopfzeile eins für „alle angezeigten auswählen“ (berücksichtigt Suche/Filter). Sobald etwas markiert ist, erscheint eine Leiste mit **⇩ Herunterladen** – mehrere Rechnungen kommen als ZIP-Datei mit allen PDFs, eine einzelne direkt als PDF.

## 0.5.6 – 2026-11-16

### Neu
- **Hell/Dunkel-Umschalter** oben rechts in der Kopfzeile (Mond-/Sonnen-Symbol). Ohne eigene Wahl folgt die App weiterhin der Systemeinstellung; die gewählte Darstellung wird im Browser gespeichert.

## 0.5.5 – 2026-11-16

### Behoben
- PDF: Bei längeren Rechnungen landete „Mit freundlichen Grüßen“ unten auf Seite 1 und der Name allein auf Seite 2. Gruß und Name bleiben jetzt immer zusammen – passt der Block nicht mehr auf die Seite, kommen beide gemeinsam auf die nächste.

## 0.5.4 – 2026-11-15

### Neu
- **Offene Rechnungen direkt löschen**: Jede Zeile in „Offene Rechnungen“ hat jetzt ein ✕ zum Löschen (mit Sicherheitsabfrage). Vorher musste die Rechnung erst als bezahlt markiert und dann im Archiv gelöscht werden.

## 0.5.3 – 2026-11-15

### Geändert
- **„Anlässe“ heißt jetzt „Rechnungsposten“** – im Menü, auf der Startseite, im Editor („Rechnungsposten wählen …“) und beim Import. Bestehende Einträge bleiben unverändert erhalten.

## 0.5.2 – 2026-11-15

### Geändert
- Auf der **Startseite** wird die Navigationsleiste ausgeblendet – die Kacheln übernehmen die Navigation. Auf allen anderen Seiten bleibt sie wie gewohnt sichtbar.
- Ein Klick auf das **Logo** oben links führt jederzeit zurück zur Startseite.

## 0.5.1 – 2026-11-15

### Geändert
- **Startseite** neu aufgebaut: Statt der Aufgabenliste gibt es jetzt **Aktions-Kacheln** für alle Bereiche der App (Neue Rechnung, Rechnungen, Importieren, Kunden, Anlässe, Zahlungsbedingungen).
- Darunter nur noch der **Status der Rechnungen**: offene Rechnungen mit Restzeit (Warnung bei überfälligen oder heute fälligen Rechnungen), Umsatz und die letzten Rechnungen.

### Entfernt
- Aufgabenliste (To-dos) auf der Startseite.

## 0.5.0 – 2026-11-15

### Neu
- **Startseite** als neuer erster Menüpunkt (öffnet sich beim Aufruf der App):
  - Begrüßung mit Datum und Schnellaktionen (Neue Rechnung, Kunde anlegen, Rechnungen importieren)
  - **Aufgaben**: eigene To-do-Liste mit optionalem Fälligkeitsdatum („heute“, „morgen“, „2 Tage überfällig“), abhaken, erledigte ein-/ausklappen und löschen
  - **Hinweise**: überfällige oder heute fällige Rechnungen, überfällige Aufgaben, fehlende Absenderdaten
  - Kurzübersicht offene Rechnungen, Umsatz (aktueller Monat, aktuelles Jahr, Vorjahr) und die letzten Rechnungen
- Die übrigen Seiten bleiben unverändert.

## 0.4.3 – 2026-11-14

### Neu
- App-Symbol (`icon.png`) und Logo (`logo.png`) für die App-Übersicht in Home Assistant.

## 0.4.2 – 2026-11-14

### Geändert
- Offene Rechnungen: Die drei Kacheln (offen gesamt, überfällig, fällig in 7 Tagen) wurden durch **eine Summenzeile** ersetzt – Anzahl offener Rechnungen, Gesamtbetrag und die nächste Frist.

## 0.4.1 – 2026-11-14

### Geändert
- **Offene Rechnungen** kompakter: pro Zeile nur noch Rechnungsname, Betrag, verbleibende Zeit und ein Haken „Bezahlt“. Haken setzen verschiebt die Rechnung ins Archiv. Ein Klick auf den Rechnungsnamen öffnet sie im Editor.
- **Archiv** wieder im bisherigen Aussehen (Spalte „Nr.“ statt Rechnungsname) – enthält weiterhin nur bezahlte Rechnungen.

## 0.4.0 – 2026-11-14

### Neu
- **Archiv**: Bezahlte Rechnungen stehen jetzt im Archiv. Wird eine Rechnung auf „bezahlt“ gesetzt, wandert sie aus den offenen Rechnungen ins Archiv; Haken im Archiv entfernen holt sie zurück.
- Changelog (diese Datei) – wird in Home Assistant beim Update angezeigt.

### Geändert
- Offene Rechnungen zeigen zuerst den **Rechnungsnamen** (z. B. `Rechnung_037_311026`, wie die PDF-Datei) und direkt dahinter Status bzw. Restzeit; darunter Kunde, Rechnungsdatum und Fälligkeit.
- Offene Rechnungen haben eigene Buttons für PDF, Bearbeiten und Löschen.
- Die Liste „Alle Rechnungen“ heißt jetzt „Archiv“ und zeigt den Rechnungsnamen statt nur der Nummer. Filter „offen/bezahlt“ und Sortierung nach Status entfallen.

## 0.3.3 – 2026-11-14

### Neu
- Übersicht **Offene Rechnungen**: Summen für offen, überfällig und in 7 Tagen fällig; je Rechnung Fälligkeitsdatum und Restzeit („noch 5 Tage“, „3 Tage überfällig“). Das Zahlungsziel wird aus der Zahlungsbedingung gelesen und ab Rechnungsdatum gerechnet.

## 0.3.2 – 2026-11-14

### Neu
- Rechnungsliste sortierbar nach Nummer, Datum, Kunde, Betrag und Status – per Klick auf die Spaltenköpfe oder über ein Auswahlfeld. Die Sortierung wird gemerkt.
- Filter alle/offen/bezahlt.

## 0.3.1 – 2026-11-14

### Geändert
- Neuer Name **DJ Office Studio** (Seitenleiste, App-Store, Titel).
- Neues Logo (Schallplatte mit Tonarm) und Favicon.
- Ruhigeres Grün (`#4ade80`) statt Leucht-Neon.

## 0.3.0 – 2026-11-14

### Neu
- Positionen mit **Anlass** (Hochzeit, Geburtstag, Firmenfeier, …) und von/bis-Zeiten; der Rechnungstext wird daraus erzeugt.
- Freitext-Option für Positionen ohne Anlass.

### Geändert
- Tab „Textbausteine“ heißt jetzt „Anlässe“. Ohne eigene Vorlage wird „DJ – Tätigkeit <Anlass> – {von} Uhr bis {bis} Uhr“ verwendet.
- Unveränderte alte Standard-Bausteine werden automatisch zu Anlässen umbenannt (Preisangaben entfernt).
- Import schlägt Anlässe ohne Preisangaben vor.

## 0.2.1 – 2026-11-14

### Behoben
- Import erkannte mit Word erzeugte Rechnungs-PDFs nicht („Empfänger oder Positionen nicht erkannt“).

## 0.2.0 – 2026-11-14

### Neu
- **Import alter Rechnungen** (PDF): Empfänger, Positionen, Nummer, Datum und Zahlungsbedingung werden erkannt; Empfänger, Textbaustein-Vorschläge und Rechnungen können ausgewählt und übernommen werden.

## 0.1.5 – 2026-11-14

### Geändert
- Farbschema Schwarz/Weiß/Grün.

## 0.1.4 – 2026-11-14

### Behoben
- Nach Updates wurde teilweise noch das alte Design angezeigt (Browser-Cache).

## 0.1.3 – 2026-11-14

### Geändert
- Modernes Design: Kartenlayout, nummerierte Positionen, feste Aktionsleiste, Bezahlt-Schalter, Dark Mode.

## 0.1.2 – 2026-11-14

### Geändert
- Preise werden nicht mehr automatisch berechnet, sondern pro Position individuell eingetragen.

## 0.1.1 – 2026-11-14

### Behoben
- Installation schlug in Home Assistant fehl (`apt-get: not found`).

## 0.1.0 – 2026-11-14

### Neu
- Erste Version: Rechnungseditor mit Kundenverwaltung, Textbausteinen, Zahlungsbedingungen, PDF im Layout der Vorlage, Rechnungsliste, fortlaufende Nummer ab 037.

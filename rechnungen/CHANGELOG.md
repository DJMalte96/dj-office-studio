# Changelog

Alle Änderungen an DJ Office Studio. Neueste Version oben.

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

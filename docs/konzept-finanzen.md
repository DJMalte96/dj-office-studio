# Konzept: Finanzen (Ausgaben, Fahrten, EÜR)

Stand: 18.11.2026 · Status: **Planung** – noch nicht umgesetzt · geplant ab Version 1.1

Ziel: DJ Office Studio bekommt einen Menüpunkt **Finanzen**. Dort werden Ausgaben verwaltet (mit Beleg), Fahrten zu den Veranstaltungen automatisch berechnet und am Jahresende eine **Einnahmen-Überschuss-Rechnung (EÜR)** erstellt und für den Steuerberater exportiert. Eine Anbindung an Paperless-ngx folgt später; bis dahin werden Belege direkt in der App hochgeladen.

Die App soll für verschiedene DJs passen: Kleinunternehmer und umsatzsteuerpflichtig, Auto im Privat- oder im Betriebsvermögen.

---

## 1. Menü „Finanzen“

| Unterpunkt | Inhalt |
|---|---|
| **Übersicht** | Jahr wählen · Kacheln Einnahmen / Ausgaben / Gewinn · Monatsverlauf · Ausgaben nach Kategorie · Hinweis Kleinunternehmer-Grenze |
| **Ausgaben** | Liste mit Suche und Filter (Jahr, Kategorie) · **Beleg hochladen** · Ausgabe ohne Beleg erfassen · wiederkehrende Ausgaben |
| **Fahrten** | automatisch aus Rechnungen erzeugt, korrigierbar · eigene Fahrten ergänzen · Summe km und Betrag |
| **Anschaffungen** | Anlagenverzeichnis: Geräte über 800 € mit Abschreibung und Restwert |
| **EÜR & Export** | EÜR des Jahres prüfen · Export für den Steuerberater · Jahr abschließen |

Auf der Startseite kommt eine kleine Kachel „Gewinn dieses Jahr“ hinzu.

---

## 2. Ausgaben

### 2.1 Beleg hochladen und auswerten
- Hochladen per Klick oder Ziehen, mehrere auf einmal. Erlaubt: **PDF, JPG, PNG, HEIC** (iPhone-Fotos) sowie **E-Mails** (`.eml`, `.msg` – siehe 2.1a).
- **PDFs mit Text** (Online-Rechnungen, Musikpools, Shops): Die App liest den Text und schlägt vor:
  - **Lieferant** (Absender des Belegs; bekannte Lieferanten werden wiedererkannt)
  - **Belegdatum**
  - **Gesamtbetrag** (sucht „Gesamt“, „Summe“, „Rechnungsbetrag“, „zu zahlen“ …; im Zweifel höchster Euro-Betrag)
  - **Umsatzsteuer** auf dem Beleg (19 % / 7 % / keine), falls erkennbar
  - **Kategorie** (aus der letzten Ausgabe beim selben Lieferanten)
- **Fotos und Scans**: in Stufe 1 ohne automatische Erkennung – Beleg wird gespeichert, Werte trägt man ein. Texterkennung (OCR) folgt in Stufe 3 (siehe 8.).
- Ansicht beim Übernehmen: **links der Beleg, rechts die Felder** – Vorschlag prüfen, korrigieren, speichern.
- Der Beleg wird **unverändert** in der App abgelegt (Aufbewahrungspflicht 8 Jahre) und ist in der Datensicherung enthalten. Doppelt hochgeladene Belege werden erkannt (Prüfsumme).

### 2.1a Belege aus E-Mails (Musikkäufe) – Drag & Drop
Musikkäufe (Apple/iTunes, Amazon, Beatport, Bandcamp, Traxsource, Juno …) haben meist keine PDF-Rechnung, sondern nur eine Kauf-Mail. In Stufe 1 werden diese Mails **per Drag & Drop** in die App gezogen – in denselben Upload-Bereich wie andere Belege, auch mehrere auf einmal.

- **Unterstützte Formate:** `.eml` (Apple Mail, Thunderbird, Gmail „Original herunterladen“, die meisten Programme) und `.msg` (Outlook unter Windows).
  - Apple Mail und Thunderbird: Mail direkt aus der Liste auf den Upload-Bereich ziehen (falls der Browser das nicht annimmt: erst auf den Schreibtisch ziehen, dann von dort).
  - Outlook (Windows): Mail auf den Upload-Bereich bzw. in einen Ordner ziehen.
  - Gmail/Webmail im Browser: Mail als „Original herunterladen“ bzw. „Als .eml speichern“, dann hochladen.
- **Auswertung:**
  - **Lieferant** aus der Absenderadresse (z. B. `…@email.apple.com` → Apple) – sehr zuverlässig
  - **Datum** aus dem Mail-Datum
  - **Betrag** aus dem Mailtext; für die häufigsten Shops eigene Erkennungsregeln (deren Mails sind immer gleich aufgebaut), sonst allgemeine Suche nach „Gesamt“, „Summe“, „Total“
  - **Eigene Erkennungsregeln zuerst für: Beatport, Apple/iTunes, Amazon, Qobuz** (die Shops, bei denen tatsächlich gekauft wird). Grundlage sind echte, bereinigte Beispiel-Mails unter `tests/beispiele/mails/`; weitere Shops (Bandcamp, Traxsource, Juno …) nach Bedarf.
  - **Kategorie** „Musik & Lizenzen“ für bekannte Musik-Shops
  - Bestätigen wie bei allen Belegen: links die Mail, rechts die Felder
- **Aufbewahrung:** Die **Original-Mail wird unverändert gespeichert** (sie ist der Beleg), zusätzlich eine lesbare PDF-Ansicht für Vorschau und Export. Anhänge der Mail (z. B. eine angehängte PDF-Rechnung) werden mitgespeichert und bevorzugt ausgewertet.
- **Doppelte Mails** werden an der Mail-Kennung (Message-ID) erkannt.
- **Hinweise der App:**
  - Amazon-Bestellbestätigungen sind keine Rechnung – die Rechnung gibt es im Amazon-Konto. Für Kleinunternehmer reicht die Mail meist als Nachweis; wer Vorsteuer ziehen will, braucht die Rechnung.
  - Bei Fremdwährung (z. B. US-Dollar) zählt der tatsächlich abgebuchte Euro-Betrag – Vorschlag aus der Mail ggf. nach dem Kontoauszug korrigieren.
- **Ansicht „zusammengefasst“** in der Ausgabenliste (je Monat und Shop), damit viele kleine Einzelkäufe übersichtlich bleiben.

Spätere Ausbaustufen: automatisches Abholen aus einem Mail-Ordner (z. B. „DJ-Belege“, gefüllt per Filterregel) über IMAP mit den Zugangsdaten des E-Mail-Versands (Stufe 2), bzw. über den Mail-Abruf von Paperless-ngx im Rahmen der Paperless-Anbindung (Stufe 3).

### 2.2 Felder einer Ausgabe
| Feld | Hinweis |
|---|---|
| Belegdatum | Datum auf dem Beleg |
| **Bezahlt am** | maßgeblich für die EÜR (Abflussprinzip); Standard = Belegdatum |
| Lieferant | mit Vorschlägen aus bisherigen Ausgaben |
| Beschreibung | z. B. „2 × XLR-Kabel 10 m“ |
| Kategorie | siehe 2.3 |
| Betrag (brutto) | wie auf dem Beleg |
| Umsatzsteuer auf dem Beleg | 19 % / 7 % / keine – nur für umsatzsteuerpflichtige Nutzer relevant (Vorsteuer) |
| Privatanteil | z. B. 50 % beim Handyvertrag; Standard 0 % |
| Beleg | Datei; „ohne Beleg“ möglich (z. B. Parkautomat) mit Pflicht-Notiz |
| Verknüpfung | optional zu einer Rechnung (z. B. Mietlicht für eine bestimmte Hochzeit) |
| Paperless-Nr. | leer – für die spätere Anbindung vorgesehen |

### 2.3 Kategorien
Vorgegeben, passend zur Anlage EÜR, erweiterbar:

| Kategorie | Beispiele |
|---|---|
| Technik (Kleingeräte, Verbrauch) | Kabel, Leuchtmittel, Ersatzteile, Taschen, Geräte bis 800 € netto |
| Anschaffung über 800 € | Boxen, Mischpult, Laptop → wird abgeschrieben (Abschnitt 4) |
| Miete Technik | geliehene Anlage, Licht |
| Musik & Lizenzen | Musikpools, Streaming, DJ-Software, GEMA |
| Fahrzeug | Tanken, Werkstatt, Versicherung – **nur bei Auto im Betriebsvermögen** (siehe 3.4) |
| Reisekosten | Parken, Maut, Bahn, Übernachtung |
| Telefon & Internet | meist mit Privatanteil |
| Werbung | Website, Visitenkarten, Anzeigen, Social-Media-Werbung |
| Versicherungen & Beiträge | Veranstalter-Haftpflicht, Verbände |
| Fortbildung | Kurse, Fachliteratur |
| Bürobedarf & Gebühren | Druckerpapier, Porto, Kontoführung |
| Sonstiges | alles andere |

Die Zuordnung der Kategorien zu den Zeilen der Anlage EÜR wird in einer Tabelle je Steuerjahr gepflegt; die Zeilennummern werden bei der Umsetzung gegen die aktuelle Anlage EÜR geprüft.

### 2.4 Wiederkehrende Ausgaben
Abos (Musikpool, Streaming, Software, Handy) einmal anlegen: Betrag, Lieferant, Kategorie, Intervall (monatlich / jährlich), Beginn und Ende. Die App legt die Buchungen automatisch an; den Beleg kann man später anhängen.

---

## 3. Fahrten

### 3.1 Veranstaltungsort
Rechnungen und Angebote bekommen ein neues Feld **Veranstaltungsort** (Name, Straße, PLZ, Ort) – Standard „wie Kundenadresse“. Wird ein Angebot zur Rechnung, wird der Ort übernommen. Optional erscheint er auch auf dem PDF („Veranstaltungsort: Hof Musterfeld, …“).

### 3.2 Automatische Berechnung
- **Startpunkt**: Absenderadresse aus den Einstellungen; je Fahrt änderbar. Optional eine abweichende Standard-Startadresse (z. B. Lager).
- **Ziel**: Veranstaltungsort der Rechnung.
- **Datum**: Lieferdatum der ersten Position (Tag der Veranstaltung).
- **Strecke**: über einen Kartendienst berechnet (Vorschlag: OpenStreetMap – Adresse → Koordinaten über Nominatim, Strecke über einen Routing-Dienst), **Hin- und Rückfahrt**. Ergebnisse werden zwischengespeichert, damit dieselbe Adresse nicht erneut abgefragt wird.
- Wird angelegt bzw. aktualisiert, wenn eine Rechnung gespeichert wird; nicht für Stornorechnungen. Wird eine Rechnung storniert, wird die Fahrt nicht gelöscht – gefahren ist gefahren – aber markiert.
- **Pro Rechnung abwählbar**: Im Editor gibt es bei jeder Rechnung den Schalter **„Fahrt erfassen“** (Standard: an). Ist er aus – z. B. Veranstaltung zu Fuß erreichbar, Mitfahrt, Kunde holt Technik ab, Online-Auftrag –, wird keine Fahrt angelegt, und sie entsteht auch beim erneuten Speichern oder bei „Fahrten nachberechnen“ nicht wieder. Wird eine automatisch angelegte Fahrt in der Fahrtenliste gelöscht, setzt das denselben Schalter. Der Standardwert für neue Rechnungen ist in den Einstellungen änderbar.
- **Immer korrigierbar**: Kilometer von Hand ändern (z. B. Umweg), weitere Fahrten ergänzen (Aufbau am Vortag, Technik abholen).
- Für vorhandene Rechnungen: Button „Fahrten nachberechnen“.

### 3.3 Datenschutz
Für die Berechnung werden **Start- und Zieladresse an den Kartendienst** geschickt (keine Namen, keine Beträge). Deshalb ist die automatische Berechnung **standardmäßig aus** und wird in den Einstellungen bewusst eingeschaltet – mit einem Satz, was übertragen wird. Ohne Kartendienst: Kilometer von Hand eintragen.

### 3.4 Steuerliche Behandlung – Einstellung „Fahrzeug“
| Einstellung | Fahrten | Fahrzeugkosten (Tanken, Werkstatt …) |
|---|---|---|
| **Privatfahrzeug** (Standard) | 0,30 € je gefahrenem km als Ausgabe | **nicht** zusätzlich absetzbar – die App warnt, wenn Tankbelege erfasst werden |
| **Betriebsfahrzeug** | Fahrten werden als Nachweis geführt, aber **nicht** mit 0,30 €/km angesetzt | tatsächliche Kosten in Kategorie „Fahrzeug“ |

Der Kilometersatz ist einstellbar (Gesetzesänderungen).

### 3.5 Fahrtenliste
Liste aller Fahrten mit Datum, Ziel, Anlass (Rechnungsnummer, Kunde), km und Betrag – geht in den Export als Nachweis.

---

## 4. Anschaffungen und Abschreibung

- Ausgaben der Kategorie „Anschaffung über 800 €“ landen zusätzlich im **Anlagenverzeichnis**.
- Grenze für die Sofortabschreibung (geringwertiges Wirtschaftsgut): **800 € netto** – auch für Kleinunternehmer wird die Grenze am Nettobetrag geprüft; abgesetzt wird bei Kleinunternehmern der Bruttobetrag (keine Vorsteuer).
- Darüber: lineare Abschreibung über die **Nutzungsdauer**, im Anschaffungsjahr anteilig nach Monaten. Vorschläge (änderbar, mit dem Steuerberater abstimmen): Computer/Laptop/Software 1 Jahr, sonstige Technik nach AfA-Tabelle.
- Verkauf oder Verschrottung eines Geräts kann eingetragen werden (Restwert als Ausgabe, Verkaufserlös als Einnahme).
- Das **Anlagenverzeichnis** (Gerät, Anschaffung, Kosten, Nutzungsdauer, Abschreibung im Jahr, Restwert) geht in den Export.

---

## 5. Einnahmen

- **Bezahlte Rechnungen nach Zahlungsdatum** (Zuflussprinzip): Eine im Dezember geschriebene, im Januar bezahlte Rechnung zählt im neuen Jahr. Grundlage ist das vorhandene „Bezahlt am“. Stornos werden verrechnet.
- Rechnungen ohne Bezahlt-Datum (alte Importe): Hinweis in der EÜR-Prüfung, Datum nachtragen.
- **Sonstige Einnahmen** ohne Rechnung von Hand erfassen (z. B. Verkauf eines alten Geräts).

---

## 6. EÜR, Prüfung und Export

### 6.1 EÜR-Ansicht
- Betriebseinnahmen, Betriebsausgaben je Kategorie, Abschreibungen, Fahrten → **Gewinn**.
- **Prüfliste vor dem Export**, z. B.: Rechnungen ohne Bezahlt-Datum · Ausgaben ohne Beleg · Tankbelege bei Privatfahrzeug · Anschaffungen ohne Nutzungsdauer · offene Rechnungen zum Jahresende.

### 6.2 Export für den Steuerberater
Der vorhandene **Jahresexport unter ⚙ Einstellungen** wird erweitert (ein Export für alles), die gleiche Funktion gibt es unter Finanzen → EÜR & Export:

```
Export_2026.zip
├── EÜR_2026.csv               Summen je Kategorie mit Zuordnung zur Anlage EÜR
├── Einnahmen_2026.csv         Rechnungen nach Zahlungsdatum + sonstige Einnahmen
├── Ausgaben_2026.csv          alle Ausgaben mit Beleg-Dateinamen
├── Fahrten_2026.csv           Fahrtenliste
├── Anlagen_2026.csv           Anlagenverzeichnis mit Abschreibung
├── Rechnungen/                eigene Rechnungen als PDF (wie bisher)
└── Belege/                    alle Ausgaben-Belege, benannt z. B. 2026-03-14_Thomann_129,90.pdf
```
Tabellen als CSV mit Semikolon und deutschen Zahlen (öffnet in Excel). Ein DATEV-Format ist **nicht** vorgesehen, kann bei Bedarf später ergänzt werden.

### 6.3 Jahr abschließen
Nach dem Export kann ein Jahr **abgeschlossen** werden: Ausgaben, Fahrten und Einnahmen dieses Jahres lassen sich dann nicht mehr ändern (wie das Festschreiben bei Rechnungen). Wieder öffnen nur mit ausdrücklicher Bestätigung und Vermerk.

---

## 7. Umsatzsteuerpflichtige Nutzer

Ob weitere Nutzer (z. B. der Kollege) umsatzsteuerpflichtig sind, ist offen – deshalb wird es von Anfang an im Datenmodell berücksichtigt:
- Ausgaben speichern den Steuersatz → **Vorsteuer** wird getrennt ausgewiesen.
- In der EÜR zählen bei Umsatzsteuerpflichtigen vereinnahmte Umsatzsteuer als Einnahme sowie Vorsteuer und ans Finanzamt gezahlte Umsatzsteuer als Ausgabe.
- Eine **Übersicht für die Umsatzsteuer-Voranmeldung** (Umsatzsteuer und Vorsteuer je Monat/Quartal) folgt in Stufe 3.
- Für Kleinunternehmer: **Grenzen-Hinweis** (25.000 € Umsatz im Vorjahr / 100.000 € im laufenden Jahr) auf der Übersicht.

---

## 8. Stufen

| Stufe | Version | Inhalt |
|---|---|---|
| **1** | 1.1 | Menü Finanzen · Ausgaben mit Upload und Auswertung von PDFs und **Kauf-Mails per Drag & Drop** (Fotos ohne Erkennung) · Kategorien · Einnahmen nach Zahlungsdatum · Veranstaltungsort · Fahrten (automatisch, Privat-/Betriebsfahrzeug) · Übersicht · EÜR mit Prüfliste · erweiterter Export |
| **2** | 1.2 | Kauf-Mails automatisch aus einem Mail-Ordner abholen (IMAP) · Anschaffungen mit Abschreibung und Anlagenverzeichnis · Privatanteil · wiederkehrende Ausgaben · Jahr abschließen · Kleinunternehmer-Grenzen · „Was bleibt pro Auftrag“ |
| **3** | 1.3+ | Texterkennung für Fotos und Scans · Paperless-Anbindung (Konzept in der Projektnotiz) · Übersicht Umsatzsteuer-Voranmeldung |

---

## 9. Datenmodell (Entwurf)

| Tabelle | Wichtige Felder |
|---|---|
| `ausgaben` | belegdatum, bezahlt_am, lieferant, beschreibung, kategorie, betrag_brutto, waehrung, ust_satz, privatanteil, beleg_datei, beleg_pdf_ansicht, beleg_pruefsumme, mail_message_id, rechnung_id, anlage_id, wiederkehrend_id, paperless_id |
| `fahrten` | datum, rechnung_id, start (Adresse), ziel (Adresse), km, hin_und_zurueck, km_satz, quelle (automatisch/manuell), anlass |
| `anlagen` | bezeichnung, anschaffung_am, kosten, nutzungsdauer_jahre, methode (sofort/linear), abgang_am, abgang_erloes |
| `einnahmen_sonstige` | datum, beschreibung, betrag, ust_satz |
| `wiederkehrend` | lieferant, beschreibung, kategorie, betrag, intervall, beginn, ende |
| `jahresabschluss` | jahr, abgeschlossen_am, notiz |
| `rechnungen`, `angebote` | **neu:** veranstaltungsort; `rechnungen` zusätzlich fahrt_erfassen (ja/nein) |
| Einstellungen | fahrzeug (privat/betrieb), km_satz (0,30), startadresse, kartendienst_aktiv, fahrt_standard (an/aus) |

Belege liegen als Dateien im Datenordner (`belege/JJJJ/…`), die Datenbank speichert Pfad und Prüfsumme. Sicherung und Wiederherstellung schließen den Belegordner ein.

---

## 10. Offene Punkte und Risiken

- **Kartendienst**: Die freien OpenStreetMap-Dienste haben Nutzungsregeln (wenige Anfragen, Programm muss sich zu erkennen geben). Für ein paar Fahrten im Monat unkritisch; Alternative mit kostenlosem API-Schlüssel: OpenRouteService.
- **Texterkennung (OCR)** für Fotos: in Home Assistant gut machbar, in der Desktop-Version vergrößert sie die App deutlich – Entscheidung in Stufe 3.
- **Größe der Sicherung** wächst mit den Belegen (Fotos komprimieren?).
- **Zeilen der Anlage EÜR** ändern sich gelegentlich – Zuordnung je Steuerjahr pflegen.
- **Steuerliche Details** (Nutzungsdauern, Kilometersatz, Privatanteile) mit dem Steuerberater abstimmen; die App macht Vorschläge, entscheidet aber nicht. Der Hinweis „ohne Gewähr“ gilt auch hier.
- **Umsatzsteuerpflichtige Nutzer**: Status des Kollegen klären, bevor Stufe 3 geplant wird.

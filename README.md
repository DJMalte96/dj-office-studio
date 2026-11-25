<img src="rechnungen/logo.png" alt="DJ Office Studio" width="250">

# DJ Office Studio

DJ Office Studio ist eine App zum Schreiben von DJ-Rechnungen, -Angeboten und Booking-Verträgen – als App für Home Assistant oder eigenständig unter Windows und macOS. Kunden auswählen, Rechnungsposten und Uhrzeiten eintragen, Preis festlegen – fertig ist das PDF. Dazu kommen die **Finanzen**: Ausgaben mit Belegen, gefahrene Kilometer, Abschreibungen und eine Einnahmen-Überschuss-Rechnung (EÜR) mit Export für den Steuerberater.

![Screenshot: Rechnung erstellen](docs/bilder/rechnungseditor.png)

## Inhalt

<table>
<tr>
<td valign="top" width="33%">

<b>Einstieg</b>

- [Was die App kann](#funktionen)
- [Installation: Home Assistant](#in-home-assistant)
- [Installation: Windows / Mac](#ohne-home-assistant-windows--mac)
- [Rundgang](#rundgang)
- [Startseite](#start)
- [Schnellsuche](#schnellsuche)

</td>
<td valign="top" width="33%">

<b>Rechnungen</b>

- [Rechnung schreiben](#neue-rechnung)
- [Preis-Spickzettel](#preis-spickzettel)
- [Anzahlung & Schlussrechnung](#anzahlung)
- [Offene Rechnungen & Archiv](#rechnungen)
- [Per Mail versenden](#versenden)
- [QR-Code zum Bezahlen](#qr-code-zum-bezahlen)
- [Absender ändern](#absender-ändern-umzug-neues-konto)

</td>
<td valign="top" width="33%">

<b>Angebote & Verträge</b>

- [Angebote](#angebote)
- [Bei Angeboten nachfragen](#nachfragen)
- [Booking-Verträge](#verträge)
- [Vertragsvorlage](#vertragsvorlage)
- [Vom Vertrag zur Rechnung, bar bezahlt](#vom-vertrag-zur-rechnung)
- [Kundenakte & Stammkunden](#kundenakte)
- [Alte PDFs importieren](#alte-rechnungen-und-angebote-importieren)

</td>
</tr>
<tr>
<td valign="top" width="33%">

<b>Finanzen</b>

- [Überblick](#finanzen)
- [Ausgaben & Belege](#ausgaben)
- [Abos](#abos-wiederkehrende-ausgaben)
- [Fahrten](#fahrten)
- [Anschaffungen & Abschreibung](#anschaffungen)
- [EÜR & Export](#eür--export)
- [Jahr abschließen](#jahr-abschließen)

</td>
<td valign="top" width="33%">

<b>Einstellungen & Daten</b>

- [Einstellungen](#einstellungen)
- [E-Mail-Versand](#e-mail-versand)
- [Paperless-ngx](#paperless-ngx)
- [Datensicherung](#daten--backup)
- [Sicherheit](#schutz-vor-fremden-webseiten)

</td>
<td valign="top" width="33%">

<b>Über das Projekt</b>

- [Changelog](#changelog)
- [Hinweis & Lizenz](#hinweis-und-lizenz)
- [Lokale Entwicklung](#lokale-entwicklung)
- [Tests](#tests)
- [Neue Version veröffentlichen](#neue-version-veröffentlichen)

</td>
</tr>
</table>

<sub>Alle Abschnitte auch über das Gliederungs-Symbol ☰ oben rechts auf GitHub.</sub>

## Funktionen

- **Startseite** mit allem, was ansteht: „Heute wichtig“ (überfällige Rechnungen, fällige Abos, ungeprüfte Belege, ablaufende Angebote, fällige Sicherung), die nächsten Termine, eine Pinnwand mit „Geld kommt rein / Geld geht raus / Angebote“ und Knöpfen direkt an jedem Eintrag, dazu „Dein Jahr“ mit den wichtigsten Zahlen. In ruhigen Zeiten bleibt sie aufgeräumt statt leer.
- **Rechnungseditor**
  - Kunde mit Autovervollständigung aus bisherigen Kunden; neue Kunden werden beim Speichern automatisch angelegt
  - Positionen per **Rechnungsposten** (Hochzeit, Geburtstag, Firmenfeier, …) mit **von/bis-Zeiten** – der Rechnungstext wird daraus erzeugt, z. B. „DJ – Tätigkeit Hochzeit – 17:00 Uhr bis 2:00 Uhr“
  - Freitext-Positionen für alles andere (z. B. Fahrtkosten)
  - Preis wird pro Position individuell eingetragen
  - Auswählbare Zahlungsbedingungen (Überweisung 8/14 Tage, bar erhalten, …)
  - Fortlaufende Rechnungsnummer (dreistellig, Startwert einstellbar)
  - Prüft die Pflichtangaben einer Rechnung (vollständige Anschrift des Kunden, Lieferdatum je Position)
  - **Preis-Spickzettel**: unter jeder Position, was du für diesen Rechnungsposten bisher genommen hast (zuletzt, Schnitt, pro Stunde) und was der Kunde zuletzt gezahlt hat – ein Klick übernimmt den Betrag
  - **Anzahlungs- und Schlussrechnung**: bei Bedarf erst eine Anzahlung (z. B. 30 %) abrechnen, nach der Feier zieht die Schlussrechnung sie ab
- **PDF** im A4-Layout mit Absenderzeile, Adressfeld, Positionstabelle, QR-Code zum Bezahlen und Fußzeile (Bankverbindung, Steuernummer, Kleinunternehmer-Hinweis nach § 19 UStG bzw. Umsatzsteuer). Vorschau vor dem Speichern; beim Speichern wird eine Kopie im PDF-Ordner abgelegt (Home Assistant: `/share/rechnungen`, Desktop: `Dokumente/DJ Office Studio/PDFs`).
- **Offene Rechnungen** auf einen Blick: eine Summenzeile mit Anzahl, Gesamtbetrag und nächster Frist; darunter je Rechnung Rechnungsname (z. B. `Rechnung_037_311026`), Betrag, verbleibende Zeit („noch 5 Tage“, „3 Tage überfällig“), ein Haken zum Abhaken, wenn bezahlt wurde, und Buttons für **Zahlungserinnerung / Mahnung**, QR-Code zum Bezahlen, Senden per E-Mail, Kopieren, Festschreiben (🔒) und Löschen bzw. Stornieren (✕). Das Zahlungsziel wird aus der Zahlungsbedingung gelesen (z. B. „innerhalb der nächsten 8 Tage“) und ab dem Rechnungsdatum gerechnet.
- **Archiv** für bezahlte und stornierte Rechnungen: Wird eine offene Rechnung abgehakt, wandert sie ins Archiv – mit Suche und Sortierung nach Nummer, Datum, Betrag oder Kunde. Bezahlte Rechnungen lassen sich wieder auf „offen“ setzen. Mehrere Rechnungen markieren und **als ZIP herunterladen** oder **an Paperless-ngx senden**.
- **Festschreiben & Storno**: Eine Rechnung lässt sich nur ändern oder löschen, solange sie nicht festgeschrieben ist. Festgeschrieben wird sie automatisch, sobald sie bezahlt, gemahnt oder an Paperless gesendet wird – oder per 🔒 von Hand (z. B. nach dem Versenden). Danach wird korrigiert, wie es steuerlich sein soll: per **Stornorechnung** mit eigener Nummer und negativen Beträgen. Beim Festschreiben wird auch der **Absender** festgehalten (Anschrift, Bank, Steuerangaben) – die Rechnung bleibt nach einem Umzug, wie sie war.
- **Zahlungserinnerung und Mahnungen**: Zu offenen Rechnungen per Klick eine Zahlungserinnerung, dann 1. und 2. Mahnung als PDF – mit Bezug auf die Rechnung, Fälligkeitsdatum und neuer Zahlungsfrist (Standard 7 Tage).
- **E-Mail-Versand**: Rechnungen, Angebote, Zahlungserinnerungen und Mahnungen direkt aus der App per E-Mail verschicken – über das eigene Postfach, egal bei welchem Anbieter (Vorlagen für WEB.DE, GMX, Gmail, iCloud, T-Online & Co., aber auch jeder andere Anbieter oder eigene Mailserver). Empfänger kommt aus den Kundendaten, Betreff und Text aus anpassbaren Vorlagen, das PDF hängt automatisch an. Verschickte Belege tragen einen Vermerk „✉ Datum“, Rechnungen werden dabei festgeschrieben. Herunterladen (z. B. zum Weiterschicken per WhatsApp) geht wie bisher – direkt im selben Dialog.
- **Umsatzsteuer**: Für Kleinunternehmer ohne Umsatzsteuer mit Hinweis nach § 19 UStG. Ohne Kleinunternehmerregelung sind die Positionspreise Nettopreise; Rechnung und Angebot weisen Nettobetrag, Umsatzsteuer (19 % oder 7 %) und Gesamtbetrag aus, der Export enthält Netto, Steuersatz und Steuer. Die Steuer wird je Beleg gespeichert – ein späterer Wechsel in den Einstellungen ändert bereits geschriebene Rechnungen nicht.
- **Kopieren**: Eine Rechnung oder ein Angebot mit einem Klick als neuen Beleg übernehmen (Kunde, Texte, Preise, Zahlungsbedingung) – praktisch für Stammkunden und jährlich wiederkehrende Feiern. Neue Nummer, heutiges Datum, das Datum der Veranstaltung trägt man neu ein.
- **QR-Code zum Bezahlen (GiroCode)**: Auf Rechnungen, Zahlungserinnerungen und Mahnungen steht neben der Zahlungsbedingung ein QR-Code. Der Kunde scannt ihn mit seiner Banking-App, und Empfänger, IBAN, Betrag und Verwendungszweck („Rechnung 037“) sind schon ausgefüllt. Bei offenen Rechnungen zeigt die App den Code auch groß auf dem Bildschirm an, z. B. wenn direkt nach der Feier bezahlt wird. Nicht auf Angeboten, Stornorechnungen und bei „Bar erhalten“ / „Bereits bezahlt“; abschaltbar unter ⚙ Einstellungen.
- **Datensicherung & Export**: Unter ⚙ Einstellungen alle Daten samt Ausgaben-Belegen als eine Sicherungsdatei herunterladen bzw. wieder einspielen. Die Startseite zeigt, wie lange die letzte Sicherung her ist, und erinnert nach einstellbarer Zeit (Standard 30 Tage) an eine neue. Dazu ein **Export für den Steuerberater**: alle Rechnungen eines Jahres als Excel-Tabelle (CSV, mit Bezahlt-Datum, Stornos und ggf. Umsatzsteuer) plus PDFs, dazu EÜR, Ausgaben, Fahrten, Anlagenverzeichnis und alle Belege – als ein ZIP. Die Desktop-Version sichert zusätzlich automatisch einmal pro Tag.
- **Booking-Verträge** (Menü Dokumente): aus einem Angebot oder ohne Angebot, mit deiner Vorlage (Verpflegung, Ersatz-DJ, GEMA, Schäden durch Gäste und 16 weitere Bausteine, eigene Abschnitte, eigener Vertrag zum Hochladen), PDF, Versand per Mail und Unterschrift (Datei, Mail-Bestätigung oder vor Ort).
- **Vom Vertrag zur Rechnung**: Vor der Feier erinnert die Startseite an die vereinbarte Anzahlung, danach an die Rechnung – ein Klick übernimmt Kunde, Termin, Ort und Gage (mit Anzahlung als Schlussrechnung), Verlängerung oder weitere Posten lassen sich vor dem Speichern ergänzen. **Bar bezahlt** (Quittung von Hand auf dem Quittungsblock) wird nur für die Kundenakte vermerkt – Betrag, Tag, Nummer vom Block, auf Wunsch ein Foto vom Durchschlag; in EÜR, Export und Kleinunternehmer-Grenze zählt es nicht.
- **Kundenakte** (Stammdaten → Kunden): je Kunde Umsatz, Feiern, üblicher Preis, letzte und nächste Feier und alle Angebote, Verträge, Rechnungen und Barzahlungen. Stammkunden bekommen knapp ein Jahr nach ihrer letzten Feier eine Erinnerung auf der Startseite – „Diesmal nicht“ oder „Nicht mehr erinnern“ blenden sie aus.
- **Angebote**: Im selben Editor wie Rechnungen (Kunde, Rechnungsposten mit von/bis-Zeiten, Preise) – mit eigenem Nummernkreis, Angebotsdatum, **Gültig bis** (Bindefrist, Standard 30 Tage), optionaler Zahlungsbedingung und freien **Hinweisen** (z. B. Verlängerungsstunde, Leistungsumfang, GEMA). Das PDF hat dasselbe Layout wie die Rechnung (`Angebot_001_120627.pdf`). Oben in der Angebotsansicht und auf der Startseite: **Offene Angebote** mit Angebotsdatum und Restlaufzeit („noch 12 Tage“, „seit 3 Tagen abgelaufen“), auf der Startseite zusätzlich ein Hinweis, wenn ein Angebot in den nächsten 3 Tagen abläuft. In der Angebotsliste: mehrere markieren und als ZIP herunterladen oder an Paperless senden, Status (offen / angenommen / abgelehnt), Restlaufzeit bzw. „abgelaufen“ und **→ Rechnung**, das Kunde und Positionen in eine neue Rechnung übernimmt und das Angebot als angenommen markiert. Bleibt ein Angebot ein paar Tage ohne Antwort, erinnert die Startseite ans **Nachfragen** – mit fertiger Mail.
- **Import alter Rechnungen und Angebote**: Bisherige PDFs hochladen (gemischt möglich – die App erkennt Rechnung oder Angebot selbst). Empfänger, Positionen und Vorschläge für Rechnungsposten werden erkannt und können übernommen werden, optional auch die Rechnungen selbst als Archiv und die Angebote (mit „gültig bis“ und Hinweisen) in die Angebotsliste.
- **Finanzen**
  - **Ausgaben mit Belegen**: PDF-Rechnungen, Fotos (JPG, PNG, HEIC) und Kauf-Mails (.eml, .msg – z. B. von Beatport, iTunes/Apple, Amazon, Qobuz, Bandcamp) per Drag & Drop hochladen – auch ganze Mail-Ordner (Postfach-Export .mbox) oder Finder-Ordner mit Hunderten Mails auf einmal. Die App liest Lieferant, Datum, Betrag und Umsatzsteuer aus – bei **Fotos und Scans mit Texterkennung, vollständig lokal** – und schlägt eine Kategorie vor; man prüft nur noch und übernimmt. Ein **Belege-Ordner** wird automatisch eingelesen (Home Assistant: `/share/belege`) – praktisch mit Scanner-Apps, Cloud-Ordnern oder Mail-Regeln. Wer **Paperless-ngx** nutzt, lässt die App einfach den Ordner lesen, in dem Paperless die Ausgaben ablegt. Die Originale bleiben unverändert gespeichert, doppelte Belege werden erkannt, Gelöschtes landet im **Papierkorb** und lässt sich wiederherstellen. Ausgaben ohne Beleg (z. B. Parkautomat) gehen mit Notiz. Privatanteil in Prozent (z. B. Handyvertrag).
  - **Fahrten**: Zu jeder Rechnung wird automatisch die Hin- und Rückfahrt zum Veranstaltungsort erfasst – auf Wunsch mit Kilometern von OpenStreetMap, sonst von Hand. Pro Rechnung abwählbar, eigene Fahrten (z. B. zum Musikladen) lassen sich ergänzen. Mit Privatfahrzeug zählt die Kilometerpauschale (Standard 0,30 €/km).
  - **Anschaffungen & Abschreibung**: Geräte über 800 € netto werden über die Nutzungsdauer abgeschrieben (linear, monatsgenau; Computer im Kaufjahr voll). Anlagenverzeichnis mit Restwerten, Übernahme von Geräten aus Vorjahren und Verkauf/Ausscheiden.
  - **Übersicht** mit Einnahmen, Ausgaben und Gewinn des Jahres, Diagramm je Monat (auch als Tabelle) und Ausgaben nach Kategorie.
  - **Kleinunternehmer-Grenzen**: Die Übersicht zeigt, wie viel Umsatz im Jahr schon zusammengekommen ist – gemessen an den 25.000 € (entscheidet, ob man im nächsten Jahr noch Kleinunternehmer ist) und den 100.000 € (darüber sofort umsatzsteuerpflichtig), dazu den Vorjahresumsatz. Wird es knapp – auch mit offenen Rechnungen –, warnen Übersicht, Startseite und Prüfliste.
  - **E-Rechnungen empfangen**: XRechnung und ZUGFeRD/Factur-X aus XML, PDF oder Mail lesen – mit Lesefassung, Original und Warnungen (eigene Rechnung, Gutschrift, Fremdwährung, doppelt).
  - **EÜR & Export**: Einnahmen-Überschuss-Rechnung nach Zahlungseingang und -ausgang mit Vorschlag für die Zeilen der Anlage EÜR, Prüfliste vor dem Export (ungeprüfte Belege, fehlende Bezahlt-Daten, fehlende Kilometer …) und ein ZIP für den Steuerberater mit allen Tabellen, Rechnungen und Belegen. Sonstige Einnahmen ohne Rechnung (z. B. Verkauf eines alten Geräts) lassen sich ergänzen.
  - **Abos**: Musikpool, DJ-Software & Co. einmal anlegen – wöchentlich bis alle paar Jahre oder im eigenen Rhythmus. Fällige Abbuchungen erscheinen zum Bestätigen; kommt die Rechnung als Mail oder PDF, hängt die App sie an, statt doppelt zu buchen. Preisänderungen ab einem Datum, Kündigung mit Enddatum, 10-Tage-Regel automatisch.
  - **Jahr abschließen**: Ein fertiges Jahr in drei Schritten prüfen, kontrollieren und abschließen. Die App legt ein Paket mit Abschlussblatt und Prüfsumme ab und sperrt das Jahr gegen Änderungen – ansehen, herunterladen und erneut verschicken geht weiter. Ein Jahr wird nie von selbst gesperrt; wieder öffnen geht mit Begründung. Kleinunternehmer und Fahrzeug gelten je Jahr.
- **Stammdaten** für Kunden, Rechnungsposten und Zahlungsbedingungen.
- **Schnellsuche** (Lupe oder Strg/⌘ + K) über Rechnungen, Angebote, Kunden, Belege und Seiten – und ein **Rundgang** durch die App für den Einstieg (beim ersten Start, jederzeit wiederholbar).
- Helles und dunkles Design (folgt der Geräteeinstellung, umschaltbar oben rechts), nutzbar am Computer, Tablet und Handy.

## Bedienung

Oben in der Kopfzeile gibt es auf jeder Seite das Menü: **Start**, **Rechnungen** (Neue Rechnung, Rechnungen), **Angebote** (Neues Angebot, Angebote), **Dokumente** (Neuer Vertrag, Verträge, Vertragsvorlage), **Finanzen** (Übersicht, Ausgaben, Fahrten, Anschaffungen, EÜR & Export) und **Stammdaten** (Kunden, Rechnungsposten, Zahlungsbedingungen).


### Rundgang

Beim allerersten Start bietet die App einen kurzen Rundgang an (ca. zwei Minuten, 13 Schritte). Der jeweilige Bereich wird hervorgehoben, die App wechselt selbst auf die passende Seite; Weiter/Zurück per Knopf oder Pfeiltasten, Esc beendet. Wiederholen: ⚙ Einstellungen → ganz unten **Rundgang starten**.

![Screenshot: Rundgang](docs/bilder/rundgang.png)

### Schnellsuche

Die Lupe oben rechts oder **Strg + K** (Mac: **⌘ + K**) öffnet die Suche über Rechnungen, Angebote, Kunden, Belege und Seiten. Gesucht wird in Namen, Orten, Nummern, Texten, Daten und Beträgen; mehrere Wörter grenzen ein („eva hochzeit“). Mit ↑ ↓ auswählen, Enter öffnet den Treffer direkt.

![Screenshot: Schnellsuche](docs/bilder/suche.png)

### Start

Die Startseite öffnet sich beim Aufruf; ein Klick auf das Logo führt zurück.

- **Oben:** Begrüßung, **Heute wichtig** (z. B. „2 Rechnungen überfällig“, „1 Abo fällig“, „1 Beleg zu prüfen“ – ein Klick führt hin) und die Schnellknöpfe **Neue Rechnung**, **Neues Angebot**, **Beleg hochladen**. Ist nichts zu tun: „✓ Alles erledigt“ mit dem nächsten Termin.
- **Demnächst:** die nächsten Termine ab morgen – fällige Rechnungen, Abo-Abbuchungen, ablaufende Angebote, Sicherung. Ist viel los, als Leiste der nächsten 14 Tage (ein Klick auf einen Tag zeigt die Einzelheiten).
- **Pinnwand:** **Geld kommt rein** (offene Rechnungen mit Zahlungserinnerung/Mahnung, QR-Code, ✓ Bezahlt), **Geld geht raus** (fällige Abos, ungeprüfte Belege, nächste Abbuchungen), **Angebote** (→ Rechnung, Ansehen, Abgelehnt). Leere Spalten fallen weg.
- **Dein Jahr:** Rechnungen geschrieben, Schnitt je Rechnung, stärkster Monat, Kunden, Gewinn bisher.
- **Statuszeile:** Datensicherung (mit **Jetzt sichern**), Kleinunternehmer-Grenze, ggf. „Jahr abschließen“. Alle Bereiche der App erreicht man über das Menü.

![Screenshot: Startseite](docs/bilder/startseite.png)

### Nachfragen

Bleibt ein Angebot ohne Antwort (Standard 7 Tage nach dem Versand, einstellbar unter ⚙ Einstellungen → Nummern & Fristen, 0 = nie), steht unter „Heute wichtig“ „✉ Angebote nachfragen“ und an der Karte **Nachfragen**. Der Dialog hat eine fertige Mail (Vorlage unter den Textvorlagen), auf Wunsch mit dem Angebot im Anhang. Wer lieber anruft oder per WhatsApp schreibt, kopiert den Text oder vermerkt die Nachfrage von Hand. Erinnert wird einmal pro Angebot.

![Screenshot: Nachfrage zum Angebot](docs/bilder/nachfrage.png)

### Neue Rechnung

Kundennamen eintippen und einen Vorschlag übernehmen (oder neue Adresse eingeben). Pro Position einen Rechnungsposten wählen, von/bis eintragen, Lieferdatum und Preis ergänzen. Zahlungsbedingung wählen, dann **PDF-Vorschau** oder **Rechnung speichern & PDF öffnen**. Gespeichert wird eine Rechnung nur mit den Pflichtangaben: vollständige Anschrift des Kunden (Straße, PLZ, Ort) und ein Lieferdatum bei jeder Position. Die PDF-Vorschau geht auch ohne, Angebote sind davon ausgenommen. Mit dem Kopieren-Symbol bei einer Rechnung oder einem Angebot startet man einen neuen Beleg mit denselben Angaben.

### Preis-Spickzettel

Sobald eine Position einen Rechnungsposten hat, steht darunter, was du dafür bisher genommen hast – wie oft, zuletzt, im Schnitt, von–bis und pro Stunde (mit Uhrzeiten auch ein Vorschlag für die eingetragene Dauer). Ist der Kunde schon bekannt, steht dabei, was er zuletzt gezahlt hat. Ein Klick auf einen Betrag übernimmt ihn als Preis.

![Screenshot: Preis-Spickzettel](docs/bilder/spickzettel.png)

### Anzahlung

Unter den Positionen steht **Art der Rechnung**. Normalerweise bleibt es bei **Normale Rechnung**. Für eine Anzahlung erst die Leistung mit dem vereinbarten Gesamtpreis eintragen und dann **Anzahlungsrechnung** wählen – daraus wird eine Position „Anzahlung 30 % für …“; Prozent oder festen Betrag daneben anpassen (der letzte Wert wird gemerkt). **Normale Rechnung** holt die Positionen zurück. Nach der Feier **Schlussrechnung** wählen: Die Anzahlungsrechnungen des Kunden stehen zum Anhaken da und werden als Minus-Zeile abgezogen, der Gesamtbetrag ist der Rest. Kam die Anzahlung aus einem Angebot, macht **→ Schlussrechnung** in der Angebotsliste bzw. der Hinweis auf der Startseite das von selbst.

![Screenshot: Anzahlungsrechnung](docs/bilder/anzahlung.png)

### Datum eingeben

Alle Datumsfelder nehmen das Datum einfach getippt an – `7.10.2019`, `07.10.19` oder `07102019`; ohne Jahr (`7.10.`) gilt das aktuelle Jahr. Das Kalender-Symbol im Feld öffnet einen Kalender.

### Rechnungen

Oben die offenen Rechnungen mit Restzeit. Ist eine Rechnung bezahlt, Haken setzen – sie wandert ins Archiv. Bei überfälligen Rechnungen erzeugt der grüne Button die nächste Stufe (Zahlungserinnerung → 1. Mahnung → 2. Mahnung) als PDF. 🔒 schreibt eine Rechnung fest, ✕ löscht sie bzw. storniert sie, wenn sie schon festgeschrieben ist. Im Archiv stehen bezahlte und stornierte Rechnungen; dort lassen sich Rechnungen auch stornieren.

![Screenshot: Rechnungen](docs/bilder/rechnungen.png)

### Versenden

Der Briefumschlag an jeder Rechnung und jedem Angebot (auch im Editor nach dem Speichern: **Senden**) öffnet den Versand-Dialog. Empfänger, Betreff und Text sind vorausgefüllt und lassen sich ändern; bei einer Rechnung mit Mahnung wird standardmäßig die letzte Mahnung samt Rechnung verschickt. Fehlt beim Kunden noch die E-Mail-Adresse, kann sie direkt mitgespeichert werden. Wer lieber per WhatsApp oder Messenger schickt, lädt das PDF unten im Dialog herunter (auf dem Handy bzw. über HTTPS gibt es zusätzlich **Teilen …**).

![Screenshot: Versand per E-Mail](docs/bilder/versand.png)

### QR-Code zum Bezahlen

Das QR-Symbol bei einer offenen Rechnung zeigt den GiroCode groß an – der Kunde scannt ihn mit seiner Banking-App („Fotoüberweisung“ bzw. „QR-Code scannen“). Mit **Als bezahlt markieren** wandert die Rechnung danach direkt ins Archiv. Derselbe Code ist auch auf dem Rechnungs-PDF gedruckt.

![Screenshot: QR-Code zum Bezahlen](docs/bilder/girocode.png)

### Angebote

Über **Angebote → Neues Angebot** im selben Editor schreiben – zusätzlich mit **Gültig bis** und freien **Hinweisen** (z. B. Verlängerungsstunde, GEMA). In **Angebote → Angebote** stehen oben die offenen Angebote mit Restlaufzeit, darunter alle Angebote mit Status (offen / angenommen / abgelehnt). **→ Rechnung** macht aus einem Angebot eine neue Rechnung und markiert es als angenommen.

![Screenshot: Angebote](docs/bilder/angebote.png)

### Verträge

Unter **Dokumente → Neuer Vertrag** ein Angebot wählen – Kunde, Termin, Ort, Spielzeit und Gage übernimmt die App daraus – oder **Ohne Angebot** und die Angaben im Vertrag selbst eintragen (bekannte Kunden werden mit Anschrift vorgeschlagen). Links stellst du ein, was in diesen Vertrag gehört: Aufbauzeit, Ansprechpartner vor Ort, Anzahlung (Prozent, Rest per Rechnung oder bar), Verpflegung, wer die GEMA anmeldet, und welche Abschnitte drinstehen. Rechts steht der Vertrag so, wie er als PDF herauskommt.

**✉ Senden** verschickt den Vertrag wie ein Angebot per Mail (mit PDF und den Anlagen der Vorlage); wer ihn ausdruckt oder per WhatsApp schickt, wählt in der Liste **Als verschickt vermerken**. Ab dann steht der Text fest – **Wieder bearbeiten** öffnet ihn noch einmal. Kommt er zurück, vermerkt **✓ Unterschrieben**, wie: als Datei (PDF oder Foto, wird beim Vertrag abgelegt und gesichert), per Mail bestätigt oder vor Ort unterschrieben – auf Wunsch wird das Angebot dabei angenommen. Die Startseite erinnert an Verträge, die noch nicht unterschrieben zurück sind.

![Screenshot: Vertrag](docs/bilder/vertrag.png)

![Screenshot: Verträge](docs/bilder/vertraege.png)

### Vertragsvorlage

Unter **Dokumente → Vertragsvorlage** stehen die Abschnitte für neue Verträge. Fest eingeschaltet sind Verpflegung, Ausfall des DJs/Ersatz-DJ, GEMA und Schäden durch Gäste; 16 weitere übliche Bausteine (z. B. Stornierung, Verlängerung, Strom und Zufahrt, Musikwünsche, Lautstärke und Sperrstunde, Nebel und Rauchmelder, Wetter, Höhere Gewalt, Datenschutz) lassen sich zuschalten. Jeder Text ist änderbar, die Reihenfolge mit ↑ ↓ einstellbar. **＋ Eigenen Abschnitt** legt neue Punkte an – Platzhalter wie `{veranstalter}`, `{datum}`, `{ort}`, `{spielzeit}` oder `{gage}` füllt die App im Vertrag aus.

**Eigenen Vertrag hochladen:** Einen vorhandenen Vertrag als PDF, Word (.docx) oder Text hineinziehen – die App erkennt die Abschnitte (§ 1, § 2 … oder 1., 2. …) und übernimmt die ausgewählten in die Vorlage; Teile, die sie selbst ausfüllt (Vertragspartner, Gage …), sind nicht vorausgewählt. Ein PDF (z. B. AGB) kann auch unverändert als Anlage an jeden Vertrag gehen.

Die mitgelieferten Texte sind ein Vorschlag und keine Rechtsberatung – bitte einmal prüfen lassen (z. B. Anwalt oder DJ-Verband).

![Screenshot: Vertragsvorlage](docs/bilder/vertragsvorlage.png)

### Vom Vertrag zur Rechnung

Ist bei einem unterschriebenen Vertrag eine Anzahlung vereinbart, zeigt die Startseite **€ Anzahlung anfordern** – ein Klick bereitet die Anzahlungsrechnung vor. Nach dem Tag der Feier erscheint **✎ Rechnung schreiben: Feier … war am …**. Die App fragt dann, wie bezahlt wurde:

- **Rechnung schreiben** – Kunde, Termin, Spielzeit, Ort und Gage kommen aus dem Vertrag; gibt es eine Anzahlung, wird es die Schlussrechnung und zieht sie ab. **＋ Verlängerung** und **＋ weitere Position** ergänzen, was dazugekommen ist. Gespeichert gehört die Rechnung zum Vertrag.
- **Bar bezahlt** – die Quittung schreibst du wie gewohnt von Hand auf den Quittungsblock, die App erzeugt keine. Sie vermerkt nur Betrag (nach einer bezahlten Anzahlung ist der Rest vorausgefüllt), Tag, auf Wunsch die Nummer vom Block und ein Foto vom Durchschlag. Der Vermerk steht in der Kundenakte, erledigt die Erinnerung und markiert das Angebot als angenommen – in EÜR, Export und Kleinunternehmer-Grenze zählt er nicht. Bei Firmen und Vereinen weist die App darauf hin, dass sie meist eine richtige Rechnung brauchen.

Dieselben Knöpfe gibt es in **Dokumente → Verträge** (mit dem Stand: „Anzahlung 025 ✓ bezahlt · Rechnung 026 offen“), im Vertragsfenster (**→ Rechnung**) und bei den Angeboten (**Bar bezahlt** neben **→ Rechnung**).

![Screenshot: Wie wurde bezahlt?](docs/bilder/zahlweg.png)

![Screenshot: Bar bezahlt](docs/bilder/bar-bezahlt.png)

### Kundenakte

Unter **Stammdaten → Kunden** stehen alle Kunden mit Feiern, Umsatz und letzter bzw. nächster Feier, nach Umsatz sortiert. Wer in mindestens zwei Jahren gebucht hat, ist **Stammkunde**. Ein Klick auf den Namen – auch im Archiv, bei den Angeboten und Verträgen oder in der Schnellsuche – öffnet die **Kundenakte**: Anschrift, ＋ Angebot / Vertrag / Rechnung, Umsatz, Feiern, üblicher Preis, Umsatz je Jahr und alle Angebote, Verträge, Rechnungen und Barzahlungen (ein Klick öffnet sie; eine versehentlich vermerkte Barzahlung lässt sich dort löschen).

Steht bei einem Stammkunden der Jahrestag der letzten Feier in den nächsten sechs Wochen an und gibt es noch nichts Neues, erinnert die Startseite: **↻ Stammkunde …: letztes Jahr am … – Angebot schicken?** In der Akte macht **Angebot wie letztes Jahr** daraus ein neues Angebot. **Diesmal nicht** (oder ✕ auf der Startseite) blendet die Erinnerung bis zum nächsten Jahr aus, **Nicht mehr erinnern** für diesen Kunden ganz – **Wieder einschalten** steht dann in der Akte.

![Screenshot: Kunden](docs/bilder/kunden.png)

![Screenshot: Kundenakte](docs/bilder/kundenakte.png)

### Rechnungsposten

Unter **Stammdaten → Rechnungsposten** neue Rechnungsposten (z. B. Hochzeit) anlegen. Ohne eigene Text-Vorlage wird `DJ – Tätigkeit <Bezeichnung> – {von} Uhr bis {bis} Uhr` verwendet; `{von}` und `{bis}` werden durch die Uhrzeiten ersetzt.

### Alte Rechnungen und Angebote importieren

Unter **Rechnungen** (Archiv) auf **Alte Rechnungen importieren** bzw. unter **Angebote** auf **Alte Angebote importieren** klicken und PDFs hineinziehen – gemischt möglich. Danach auswählen, welche Empfänger, Rechnungsposten, Rechnungen und Angebote übernommen werden. Erkannt werden PDFs mit echtem Text, die so aufgebaut sind wie die PDFs der App (Absenderzeile mit „|“, Adresse, „Rechnung Nr.“ bzw. „Angebot“, Tabelle, „Gesamt“). Eingescannte Dokumente werden nicht unterstützt.

### Absender ändern (Umzug, neues Konto)

- **Festgeschriebene Rechnungen und Mahnungen** behalten den Absender, mit dem sie ausgestellt wurden. Das 🔒 zeigt ihn (Maus darüber).
- **Nicht festgeschriebene Rechnungen:** Beim Speichern fragt die App, welche schon verschickt sind. Angehakte werden mit dem bisherigen Absender festgeschrieben, die anderen bekommen den neuen.
- **Angebote** folgen immer den aktuellen Einstellungen.
- **Neues Konto:** Neue Mahnungen und der QR-Code am Bildschirm nehmen das neue Konto, die alte Rechnung zeigt weiter das bisherige.
- **Aus der Zeit vor 1.7.2 und importiert:** Den damaligen Absender kennt die App nicht, festgehalten ist der vom Tag des Updates bzw. Imports. Maßgeblich ist dann das verschickte Original.

![Screenshot: Absender ändern](docs/bilder/absender.png)

### Finanzen

#### Jahr wählen

Die Jahresmenüs reichen vom ältesten Eintrag bis heute.

#### Übersicht

Einnahmen, Ausgaben und Gewinn des gewählten Jahres – so gerechnet wie in der EÜR: Einnahmen zählen am Tag des Zahlungseingangs, Ausgaben am Tag der Bezahlung. Für Kleinunternehmer folgt die Karte **Kleinunternehmer-Grenzen** (Umsatz nach Zahlungseingang gegenüber 25.000 € und 100.000 €, Vorjahresumsatz, offene Rechnungen, grobe Hochrechnung) mit Warnungen, wenn es eng wird. Darunter Hinweise auf offene Punkte, das Diagramm je Monat (Maus darüber zeigt die Werte, **Als Tabelle** zeigt alle Zahlen) und die Ausgaben nach Kategorie. Die Abschreibung steht als Jahresbetrag im Dezember.

![Screenshot: Finanzen – Übersicht](docs/bilder/finanzen.png)

#### Texterkennung für Fotos und Scans

Fotos (auch HEIC, schief, quer oder auf dem Kopf) und PDFs ohne Text liest die App im Hintergrund, einen nach dem anderen – in der Liste steht solange „Text wird gelesen …“. Man kann den Beleg währenddessen schon öffnen und ausfüllen; eigene Eingaben werden nie überschrieben. Danach sind Lieferant, Datum, Betrag und – wenn er rechnerisch passt – der Umsatzsteuersatz vorgeschlagen. Gibt es keine Summenzeile, weist die App darauf hin. **Immer mit dem Beleg vergleichen:** Texterkennung kann sich verlesen, Handschrift und stark verblasste Bons liest sie oft nicht. Bei PDFs werden die ersten drei Seiten gelesen. Mit **Text erkennen** lässt sich ein Beleg ohne Betrag erneut lesen.

Die Erkennung läuft vollständig auf dem eigenen Gerät und ohne Netzwerk. Sie braucht kurzzeitig etwa 300–600 MB freien Arbeitsspeicher und auf einem Mac mindestens macOS 13; wo sie nicht läuft, trägt man die Werte von Hand ein.

#### Ausgaben

Belege in das Feld ziehen – PDFs, Fotos oder Kauf-Mails als .eml/.msg. **Apple Mail** gibt Mails beim Ziehen nicht direkt an den Browser weiter – entweder die Mails erst auf den Schreibtisch bzw. in einen Finder-Ordner ziehen und von dort in die App, oder einen ganzen Mail-Ordner auf einmal: Ordner anklicken → **Postfach → Postfach exportieren …** → den entstandenen Ordner „….mbox“ in die App ziehen. Thunderbird-Ordner (mbox-Dateien) gehen genauso; doppelte Mails werden erkannt. Neue Belege stehen unter **Neu – bitte prüfen**. **Alle nacheinander prüfen** öffnet sie der Reihe nach: links der Beleg, rechts die erkannten Angaben. Wo der Betrag gefunden wurde, steht darunter („erkannt: Gesamt … 3,63 €“). Kurz vergleichen, ggf. korrigieren, **Übernehmen**. Erst übernommene Ausgaben zählen in der EÜR. Viele kleine Musikkäufe lassen sich in der Liste je Monat und Shop **zusammengefasst** anzeigen.

![Screenshot: Ausgaben](docs/bilder/ausgaben.png)

![Screenshot: Beleg prüfen](docs/bilder/beleg-pruefen.png)

#### E-Rechnungen

XRechnung (XML, UBL und CII) und ZUGFeRD/Factur-X (PDF mit eingebetteter XML) kommen wie andere Belege herein – hochladen, als Anhang einer Mail oder über den Belege-Ordner.

- Die Werte stammen aus den Rechnungsdaten. Bei XML und Mails zeigt die App eine Lesefassung, bei PDFs schaltet **Rechnungsdaten anzeigen** um.
- Maßgeblich und aufzubewahren ist die XML bzw. das PDF im Original – die App speichert sie unverändert, der Export legt sie unter `Belege/` ab.
- Gutschriften werden negativ vorgeschlagen. Bei Fremdwährung trägt man den abgebuchten Euro-Betrag ein. Bei mehreren Steuersätzen bleibt der Satz leer.
- Die App prüft nicht amtlich, ob eine E-Rechnung gültig ist, und schreibt selbst keine E-Rechnungen. XML-Dateien über 20 MB liest sie nicht.

![Screenshot: E-Rechnung prüfen](docs/bilder/e-rechnung.png)

#### Abos (wiederkehrende Ausgaben)

Unter **Ausgaben → ↻ Abos** legt man Musikpool, DJ-Software & Co. einmal an: Lieferant, Kategorie, Betrag, Rhythmus (wöchentlich, alle 4 Wochen, monatlich, alle 2 Monate, vierteljährlich, halbjährlich, jährlich, alle 2 Jahre oder eigener Rhythmus wie „alle 18 Monate“), Tag der Abbuchung, Beginn und ggf. Privatanteil. Frühere Abbuchungen trägt die App nur auf Wunsch nach – meist sind sie schon erfasst.

- Am Tag der Abbuchung steht das Abo unter **Neu – bitte prüfen**: **✓ Bestätigen** bucht die Ausgabe (mit Notiz „Beleg fehlt“), **Betrag ändern** nur für diesmal oder „ab jetzt immer“, **Diesen Monat nicht** z. B. bei einer Pause. Erst Bestätigtes zählt in der EÜR.
- **Nichts doppelt:** Kommt die Rechnung als Mail oder PDF herein (auch aus Paperless oder dem Belege-Ordner) oder ist die Zahlung schon als Ausgabe erfasst, erkennt die App sie am Lieferanten, am Betrag und an einem Datum bis 10 Tage daneben – **Mit Beleg bestätigen** bzw. **Damit verknüpfen**.
- **10-Tage-Regel:** Abbuchungen ab dem 22.12. für den nächsten Zeitraum zählen automatisch zum neuen Jahr (nicht bei wöchentlichen Abos).
- **Preis ändern** gilt ab heute, frühere Buchungen bleiben. **Kündigen** = Ende eintragen. Löschen entfernt nur das Abo, gebuchte Ausgaben bleiben.
- Im **Jahresabschluss** sind noch nicht bestätigte Abbuchungen des Jahres ein roter Punkt. In ein abgeschlossenes Jahr wird nichts gebucht.

![Screenshot: Fällige Abos](docs/bilder/abos-faellig.png)

![Screenshot: Abos](docs/bilder/abos.png)

#### Schutz vor fremden Webseiten

Die App hat keine eigene Anmeldung. Änderungen nimmt sie deshalb nur von ihrer eigenen Oberfläche an. Die Desktop-App antwortet nur unter 127.0.0.1 bzw. localhost, das Add-on nur über Home Assistant. Mail-Passwort und Paperless-Token gehen nur an den gespeicherten Server; wer Server oder Adresse ändert, gibt sie neu ein. Seit 1.13.1 schickt die App außerdem Sicherheits-Header mit: Eine Content-Security-Policy erlaubt nur ihre eigenen Skripte (eingeschleuster Code würde vom Browser nicht ausgeführt), fremde Seiten dürfen sie nicht einbetten (Schutz vor „Clickjacking“), und der Browser hält sich streng an den angegebenen Dateityp.

#### Schutz vor präparierten Dateien

Fremde PDFs und Outlook-Mails liest die App (HEIC-Fotos mit eigenen, höheren Grenzen) in einem eigenen Prozess mit Grenzen für Arbeitsspeicher (400 MB) und Zeit (20 Sekunden), ohne Netz. Wird eine Grenze erreicht, steht am Beleg „PDF aus Sicherheitsgründen nicht ausgewertet“ – das Original bleibt gespeichert, die Werte trägt man von Hand ein. Von PDFs über 100 Seiten werden die ersten 90 und die letzten 10 gelesen.

#### Papierkorb

**Verwerfen** (ungeprüfter Beleg) und **Löschen** (übernommene Ausgabe) legen den Eintrag samt Beleg in den Papierkorb (Finanzen → Ausgaben → **Papierkorb**). Was dort liegt, zählt nicht in EÜR, Übersicht, Abschreibung und Export.

- **Wiederherstellen** bringt den Eintrag so zurück, wie er war – eine Anschaffung samt eingestellter Nutzungsdauer. Gibt es schon eine Ausgabe mit gleichem Betrag und Datum, fragt die App vorher nach.
- Wird derselbe Beleg noch einmal hochgeladen oder in den Belege-Ordner gelegt, bietet die App das Wiederherstellen an.
- Aus Paperless kommt Verworfenes nicht von selbst zurück, auch nicht nach dem endgültigen Löschen. Von Hand hochladen geht immer.
- Geleert wird nur von Hand. **Endgültig löschen** entfernt die Belegdatei aus der App – Buchungsbelege muss man in der Regel 8 Jahre aufbewahren. Dateien in Paperless bleiben immer unberührt.
- Beim Update auf 1.6 legt die App einmalig in den Papierkorb, was früher aus dem Belege-Ordner verworfen wurde und dort noch liegt. Früher verworfene Uploads gibt es nur noch in älteren Sicherungen.

![Screenshot: Papierkorb](docs/bilder/papierkorb.png)

#### Fahrten

Im Rechnungseditor gibt es die Karte **Veranstaltung & Fahrt** (Veranstaltungsort, Standard: Adresse des Kunden) und den Schalter **Fahrt erfassen**. Beim Speichern der Rechnung legt die App die Fahrt an; ist unter ⚙ Einstellungen → Fahrten der Kartendienst eingeschaltet, berechnet sie die Strecke über OpenStreetMap. Dafür werden Startadresse und Veranstaltungsort an die öffentlichen Dienste von OpenStreetMap (Nominatim, OSRM) geschickt – sonst nichts; ausgeschaltet trägt man die Kilometer selbst ein. Kilometer lassen sich in der Liste korrigieren („korrigiert“), Fahrten ohne Rechnung über **Fahrt ergänzen** hinzufügen. Mit Betriebsfahrzeug zählen statt der Pauschale die echten Kosten (Tanken, Werkstatt …) als Ausgaben.

![Screenshot: Fahrten](docs/bilder/fahrten.png)

#### Anschaffungen

Wird eine Ausgabe als „Anschaffung über 800 €“ eingeordnet, landet das Gerät automatisch im Anlagenverzeichnis und wird abgeschrieben (Nutzungsdauer vorgeschlagen, änderbar). Geräte aus früheren Jahren übernimmt man mit **Gerät aus Vorjahren übernehmen** und dem Restwert zum 1.1. Wird ein Gerät verkauft oder entsorgt, trägt man das Datum und ggf. den Erlös ein.

#### EÜR & Export

Die EÜR des Jahres mit allen Einnahmen- und Ausgabenposten und dem Gewinn. Die Prüfliste daneben zeigt, was vor dem Export noch fehlt – z. B. ungeprüfte Belege oder bezahlte Rechnungen ohne Bezahlt-Datum (alte Importe; unter **nachtragen** mit einem Klick das Rechnungsdatum übernehmen oder einzeln eintragen). **Export herunterladen** erzeugt das ZIP für den Steuerberater. Die Zuordnung zu den Zeilen der Anlage EÜR ist ein Vorschlag – bitte mit dem Steuerberater abgleichen.

![Screenshot: EÜR & Export](docs/bilder/euer.png)

#### Jahr abschließen

Ist ein Jahr fertig, schließt man es unter **EÜR & Export** ab – ab dem 11. Januar des Folgejahres, nach den 10 Tagen um den Jahreswechsel. **Ein Jahr wird nie von selbst gesperrt**: Bis man es abschließt, lässt sich alles ändern. Die Startseite erinnert dezent daran (ausblendbar). **Jahr abschließen …** führt in drei Schritten durch:

1. **Prüfen** – rot markierte Punkte müssen erledigt sein (ungeprüfte Belege, Fahrten ohne Kilometer, Tankbelege beim Privatauto …); **ansehen** öffnet die Stelle, unten rechts geht es zurück. Gelb markierte bestätigt man mit einem Klick: noch offene Rechnungen (oder mit Datum als bezahlt eintragen) und regelmäßige Zahlungen in den 10 Tagen um Silvester (**10-Tage-Regel**, z. B. Handyvertrag oder Versicherung: zu welchem Jahr gehört sie?).
2. **Kontrollieren** – Einnahmen, Ausgaben und Gewinn im Vergleich zum Vorjahr, dazu die Kleinunternehmer-Grenze.
3. **Abschließen** – die App legt ein Paket an (`Jahresabschluss_2025_Fassung_1.zip`): Abschlussblatt als PDF, EÜR und alle Tabellen, alle Rechnungen und Belege im Original, eine Liste mit Prüfsummen (SHA-256). Ändert sich eine Datei, stimmt die Prüfsumme nicht mehr.

![Screenshot: Jahr abschließen – Prüfen](docs/bilder/jahresabschluss.png)

Danach ist das Jahr **gesperrt**: Einträge tragen ein 🔒 und lassen sich **ansehen**, aber nicht ändern, löschen oder mit Datum im Jahr neu anlegen. Die Sperre gilt auf allen Wegen – auch für Hintergrundaufgaben wie die Kilometerberechnung. Weiter geht: Rechnungen erneut verschicken, herunterladen, exportieren, eine offene Rechnung des Jahres später als bezahlt markieren (zählt dann im Zahlungsjahr), ein Gerät aus dem Jahr später verkaufen. Paket und Abschlussblatt liegen unter EÜR & Export und sind in der Datensicherung enthalten.

![Screenshot: Jahr abgeschlossen](docs/bilder/jahr-abgeschlossen.png)

**Wieder öffnen** geht jederzeit, mit einem kurzen Grund – Vorschläge zum Antippen (z. B. „Beleg nachgereicht“, „Korrektur vom Steuerberater“), eigene Gründe merkt sich die App. Das alte Paket bleibt. Beim nächsten Abschluss entsteht Fassung 2; das Abschlussblatt zeigt alle Fassungen, den Grund und die Änderung beim Gewinn.

![Screenshot: Jahr wieder öffnen](docs/bilder/jahr-oeffnen.png)

#### Kleinunternehmer und Fahrzeug je Jahr

Die Einstellungen unter ⚙ gelten für das laufende Jahr. Frühere Jahre behalten ihre Werte – wer z. B. ab Januar umsatzsteuerpflichtig wird, ändert damit nicht die EÜR des Vorjahres. Unter ⚙ Einstellungen → Steuer → **Frühere Jahre** lassen sich offene Jahre gezielt anpassen.

Die App ersetzt keinen Steuerberater und übermittelt nichts an ELSTER. Das Paket mit Prüfsumme macht Änderungen sichtbar, ist aber keine zertifizierte, revisionssichere Archivierung.

## Einstellungen

Alle Einstellungen werden **in der App** gemacht: oben rechts auf **⚙** klicken.

![Screenshot: Einstellungen](docs/bilder/einstellungen.png)

| Bereich | Felder |
|---|---|
| Absender | Name (Absender, Gruß, Kontoinhaber), Straße, PLZ und Ort, Telefon, Ort vor dem Datum („Musterstadt, den …“) |
| Bankverbindung | Bank, abweichender Kontoinhaber, IBAN, BIC, QR-Code zum Bezahlen (GiroCode) drucken |
| Steuer | Steuernummer, Kleinunternehmer (§ 19 UStG) – Hinweis auf die Steuerbefreiung (ab Belegdatum 18.11.2026: „Steuerbefreiung nach § 19 UStG (Kleinunternehmerregelung)“, ältere Belege behalten ihre ursprüngliche Formulierung); ohne Kleinunternehmerregelung: Umsatzsteuersatz (19 % / 7 %) und optional USt-IdNr. |
| Nummern & Fristen | Rechnungen ab Nr., Angebote ab Nr. (danach wird automatisch hochgezählt), Gültigkeit neuer Angebote in Tagen |
| Ablage & Paperless | Ordner für PDF-Kopien (Standard `/share/rechnungen`), **Belege-Ordner** (Standard `/share/belege`, wird automatisch eingelesen) mit „Eingelesene Dateien verschieben“, „Paperless-ngx ist installiert“, Paperless-Eingangsordner; **Belege aus Paperless** |
| Fahrten | Fahrzeug (Privatfahrzeug mit Kilometerpauschale / Betriebsfahrzeug), Kilometersatz, Startadresse (Standard: eigene Adresse), Kartendienst OpenStreetMap ein/aus, „Fahrt erfassen“ bei neuen Rechnungen |
| E-Mail-Versand | eigene E-Mail-Adresse, Anbieter-Vorlage, Postausgangsserver (SMTP), Port, Verschlüsselung, Benutzername, Passwort, „Antworten an“, Kopie an mich, Textvorlagen für Rechnung / Angebot / Mahnung |

Unten auf der Seite steht außerdem die installierte Version mit Link zum Changelog.

Die Angaben erscheinen in Absenderzeile, Gruß und Fußzeile jeder Rechnung und jedes Angebots. Fehlen Angaben für vollständige Rechnungen – Name, Straße, PLZ und Ort, IBAN und ohne Kleinunternehmerregelung die Steuernummer oder USt-IdNr. –, zeigt die App oben einen Hinweis, was fehlt, mit Link zu den Einstellungen.

> **Umstieg von älteren Versionen:** Bis Version 0.8 wurden diese Werte in Home Assistant unter *Einstellungen → Apps → DJ Office Studio → Konfiguration* eingetragen. Version 0.9.0 übernimmt sie beim ersten Öffnen der App automatisch in die eigenen Einstellungen; ab 0.9.1 gibt es die Felder in Home Assistant nicht mehr. Wer direkt von 0.8 oder älter auf 0.9.1 oder neuer aktualisiert, trägt die Werte einmal unter ⚙ neu ein.

### E-Mail-Versand

Die App verschickt über den **Postausgangsserver (SMTP) deines eigenen Postfachs** – das funktioniert mit jedem Anbieter. Unter ⚙ Einstellungen → E-Mail-Versand die eigene Adresse eintragen: Bei bekannten Anbietern werden Server, Port und Verschlüsselung automatisch vorgeschlagen, alles andere (eigene Domain, Webhoster, eigener Server) wird von Hand eingetragen. Mit **Testmail an mich senden** lässt sich die Einrichtung vor dem Speichern prüfen.

- **Freischalten / App-Passwort:** Bei WEB.DE, GMX und freenet muss der Zugriff über externe Programme (POP3/IMAP/SMTP) erst im Postfach erlaubt werden. Gmail, iCloud und Yahoo brauchen ein eigenes **App-Passwort** statt des normalen Passworts, T-Online das separate E-Mail-Passwort. Die App zeigt den passenden Hinweis beim gewählten Anbieter an.
- **Gesendet-Ordner:** Per SMTP verschickte Mails landen nicht automatisch im „Gesendet“-Ordner des Postfachs. Deshalb gibt es die Option **Kopie an mich** (BCC) – dann liegt jede verschickte Mail auch im Posteingang.
- **Passwort:** Es wird nur lokal in der Datenbank der App gespeichert, nie an die Oberfläche zurückgegeben und ist **nicht** in der herunterladbaren Sicherung enthalten. Nach dem Einspielen einer Sicherung auf einem anderen Gerät einmal neu eintragen.
- **Textvorlagen:** Betreff und Text für Rechnung, Angebot und Mahnung sind frei änderbar, mit Platzhaltern wie `{kunde}`, `{nummer}`, `{betrag}`, `{faellig}`, `{gueltig_bis}`, `{stufe}`, `{frist}`. Eine Zeile, deren Platzhalter leer bleibt (z. B. Rechnung ohne Zahlungsfrist), entfällt automatisch.

### Paperless-ngx

Ist unter ⚙ Einstellungen „Paperless-ngx ist installiert“ eingeschaltet, gibt es im Archiv bei markierten Rechnungen und in der Angebotsliste bei markierten Angeboten den Button **⇪ An Paperless senden** (sonst ist er ausgeblendet). Jede Rechnung wird als komplette PDF-Datei (z. B. `Rechnung_037_311026.pdf`) in den Eingangsordner von Paperless gelegt – Titel, Korrespondent, Dokumenttyp, Tags usw. vergibt Paperless anschließend selbst (z. B. über Zuweisungsregeln oder die automatische Zuordnung). Übertragene Rechnungen sind im Archiv mit „Paperless ✓“ gekennzeichnet; ein Klick darauf setzt die Markierung zurück (z. B. wenn das Dokument in Paperless gelöscht wurde).

- Der Paperless-Eingangsordner muss auf den Eingangsordner (consume) der Paperless-App zeigen – welcher das ist, steht in der Konfiguration der Paperless-App. In Home Assistant muss der Ordner unter `/share` oder `/media` liegen, damit DJ Office Studio darauf zugreifen kann; in der Desktop-Version geht jeder erreichbare Ordner (z. B. ein Netzlaufwerk).
- Existiert der Ordner nicht, meldet die App einen Fehler, statt ihn anzulegen – so landen keine PDFs unbemerkt im falschen Ordner.

**Ausgaben-Belege aus Paperless** (Finanzen → Ausgaben) – erscheint nur, wenn „Paperless-ngx ist installiert“ angehakt ist:

- **Am einfachsten – Ablage lesen:** Legt Paperless die Ausgaben per Speicherpfad in einem eigenen Ordner ab (z. B. `DJ/{{ created_year }}/Ausgaben/…`), klickt man auf **Ausgaben-Ordner von Paperless suchen**. Die App sucht in `/share` und `/media` nach dem Ordner „Ausgaben“ in der Ablage von Paperless (`…/documents/originals/…`), trägt ihn als Belege-Ordner ein – mit `*` für alle Jahre, z. B. `…/originals/DJ/*/Ausgaben` – und liest ihn ab dann automatisch. Die Dateien bleiben unverändert liegen (nur lesen), neue Belege kommen von selbst dazu. Voraussetzung: Die Ablage von Paperless liegt unter `/share` oder `/media` (Einstellung des Paperless-Add-ons).
- **Alternativ – über die Schnittstelle:** Liegen die Belege nicht in einem eigenen Ordner, holt **⇩ Aus Paperless abholen** alle Dokumente mit einem Tag. Einrichten:

1. **Paperless-Benutzername und -Passwort** eintragen (dieselbe Anmeldung wie in Paperless) und **Mit Paperless verbinden** klicken. Die App findet das Paperless-Add-on in Home Assistant selbst, holt sich einen Zugangsschlüssel (API-Token) und speichert das Passwort nicht.
2. Den **Tag der Ausgaben-Belege** wählen – heißt ein Tag z. B. „Ausgaben“ oder „Belege“, ist er schon vorausgewählt. Die Auswahl wird sofort gespeichert.

Unter *Erweitert* lassen sich Adresse und API-Token auch von Hand eintragen – nötig für die **Desktop-Version** (Adresse im Heimnetz, z. B. `http://homeassistant.local:8000`; dafür muss das Add-on seinen Port freigeben) oder wenn Paperless nicht als Add-on läuft. In Home Assistant fragt die App dafür den Supervisor nach den installierten Add-ons (Berechtigung `hassio_api`, nur lesend).

**Belege-Ordner allgemein:** Was im Belege-Ordner landet, liest die App jede Minute und beim Öffnen der Ausgaben ein; erkannte Belege erscheinen unter „Neu – bitte prüfen“. Ist „Eingelesene Dateien verschieben“ an (Standard), wandern sie danach in den Unterordner `übernommen` (unlesbare nach `nicht lesbar`); aus = nur lesen, die App merkt sich, was sie schon kennt. Dateien, die gerade noch geschrieben werden, wartet sie kurz ab. Doppelte Belege werden erkannt.

Beim Abholen über die Schnittstelle kommen alle Dokumente mit dem Tag – auch aus früheren Jahren –, die noch nicht übernommen sind. Die App speichert eine Kopie (PDFs, XML und Mails im Original, damit E-Rechnungen vollständig bleiben; Scans und Fotos als PDF mit Texterkennung aus Paperless), damit Export und Sicherung auch ohne laufendes Paperless funktionieren. Lieferant (Korrespondent) und Datum kommen aus Paperless, der Betrag wird aus dem Text gelesen; die Belege stehen dann unter **Neu – bitte prüfen**. Wurde ein Beleg schon von Hand hochgeladen, wird er nur verknüpft und nicht doppelt angelegt. In Paperless wird nichts verändert. Der API-Token wird wie das E-Mail-Passwort nur lokal gespeichert und ist nicht in der Sicherung enthalten.

## Installation

DJ Office Studio läuft entweder als App in Home Assistant oder eigenständig unter Windows und macOS – Funktionen und Oberfläche sind gleich.

### In Home Assistant

1. In Home Assistant **Einstellungen → Apps → App-Store** öffnen.
2. Oben rechts **⋮ → Repositories** wählen und diese URL hinzufügen:
   ```
   https://github.com/DJMalte96/dj-office-studio
   ```
3. **DJ Office Studio** im App-Store auswählen und **Installieren**. Beim ersten Mal wird das Image gebaut – das dauert ein paar Minuten.
4. **Starten** und „In Seitenleiste anzeigen“ aktivieren.
5. In der App oben rechts auf **⚙** klicken und Absenderdaten, Bankverbindung usw. eintragen (siehe [Einstellungen](#einstellungen)).

> Das Repository hieß früher `ha-rechnungen`. Wer es unter der alten Adresse schon in Home Assistant eingetragen hat, lässt es einfach so – GitHub leitet weiter, Updates kommen weiterhin an. Bitte **nicht** entfernen und neu hinzufügen: Home Assistant würde die App sonst als neue App behandeln.

### Ohne Home Assistant (Windows / Mac)

DJ Office Studio gibt es auch als eigenständige App für **Windows** und **macOS** – ohne Home Assistant, ohne Python, ohne Docker. Funktionen und Oberfläche sind dieselben.

**Herunterladen:** Auf der GitHub-Seite unter **Releases** die passende ZIP-Datei laden:

| System | Datei |
|---|---|
| Windows 10/11 | `DJ-Office-Studio-…-Windows.zip` |
| Mac mit Apple-Chip (M1 und neuer) | `DJ-Office-Studio-…-macOS-AppleSilicon.zip` |
| Mac mit Intel-Prozessor | `DJ-Office-Studio-…-macOS-Intel.zip` |

**Windows:** ZIP entpacken (Rechtsklick → *Alle extrahieren*), im Ordner `DJ Office Studio` die Datei **DJ Office Studio.exe** starten. Beim ersten Start warnt Windows ggf. („Der Computer wurde durch Windows geschützt“) – auf **Weitere Informationen → Trotzdem ausführen** klicken. Die App ist nicht kostenpflichtig signiert, daher die Warnung.

**Mac:** ZIP per Doppelklick entpacken und **DJ Office Studio** in den Ordner *Programme* ziehen. Beim ersten Öffnen meldet macOS „*DJ Office Studio* nicht geöffnet – Apple konnte nicht überprüfen, ob … frei von Schadsoftware ist“. Das liegt nur daran, dass die App nicht bei Apple notarisiert ist (kostenpflichtiger Entwickler-Account). So geht es einmalig trotzdem:

1. **Fertig** klicken – *nicht* „In den Papierkorb legen“.
2. *Systemeinstellungen → Datenschutz & Sicherheit* öffnen und ganz nach unten scrollen.
3. Bei „DJ Office Studio wurde blockiert …“ auf **Dennoch öffnen** klicken und mit Passwort/Touch ID bestätigen.

Alternativ im Terminal: `xattr -dr com.apple.quarantine "/Applications/DJ Office Studio.app"` – danach startet die App normal.

**Benutzung:** DJ Office Studio öffnet sich in einem **eigenen Programmfenster** – ohne Browser. Fenster schließen beendet die App. PDFs (Vorschau, Rechnungen, Mahnungen) öffnen sich im PDF-Programm des Computers, Sicherungen und Exporte werden über „Speichern unter“ abgelegt, und unter ⚙ Einstellungen öffnet **Daten- und PDF-Ordner öffnen** den Speicherort. Alles Weitere – Absender, Bankverbindung usw. – unter **⚙ Einstellungen**. Unter Windows nutzt das Fenster Microsoft Edge WebView2 (bei Windows 10/11 vorhanden); fehlt es, öffnet sich die App wie früher im Browser mit einem kleinen Statusfenster.

**Daten:** Alles liegt im Dokumente-Ordner unter `DJ Office Studio` – `Daten` (Datenbank mit Kunden, Rechnungen, Angeboten, Einstellungen) und `PDFs` (Kopien aller Rechnungen und Angebote). Für ein Backup einfach diesen Ordner sichern. Die App ist nur auf dem eigenen Rechner erreichbar.

**Update:** Die App prüft beim Start, ob es eine neue Version gibt, und zeigt dann oben einen Hinweis mit Download-Link (abschaltbar unter ⚙ Einstellungen). Neue ZIP herunterladen und die alte App ersetzen – die Daten im Dokumente-Ordner bleiben erhalten.

## Daten & Backup

| Was | Wo |
|---|---|
| Kunden, Rechnungsposten, Zahlungsbedingungen, Rechnungen, Angebote, Einstellungen | SQLite-Datenbank `rechnungen.db` im App-Datenordner (`/data`) |
| Ausgaben-Belege (Originale) | Ordner `belege/` im App-Datenordner, sortiert nach Jahr |
| Jahresabschlüsse (Pakete) | Ordner `abschluesse/` im App-Datenordner, auch in der Sicherung enthalten |
| PDF-Kopien | Ordner aus den Einstellungen, standardmäßig `/share/rechnungen` (z. B. per Samba erreichbar) |

Alles ist in den normalen Home-Assistant-Backups enthalten. Die Startseite zeigt in der Karte **Datensicherung**, wann zuletzt eine Sicherung heruntergeladen wurde, und färbt sich rot, sobald die eingestellte Zeit (⚙ Einstellungen → Datensicherung & Export, Standard 30 Tage, 0 = keine Erinnerung) überschritten ist – mit **Jetzt sichern** direkt daneben. Zusätzlich gibt es unter **⚙ Einstellungen → Datensicherung & Export** eine Sicherung zum Herunterladen und Einspielen – mit Datenbank und allen Belegen (vor dem Einspielen sichert die App den bisherigen Stand automatisch unter `sicherungen/`).

In der **Desktop-Version** liegt alles im Dokumente-Ordner unter `DJ Office Studio`; die App legt dort in `Daten/Sicherungen` einmal pro Tag automatisch eine Kopie der Datenbank ab (die letzten 14 bleiben erhalten).

## Changelog

Alle Änderungen je Version stehen in [rechnungen/CHANGELOG.md](rechnungen/CHANGELOG.md) – Home Assistant zeigt sie auch beim Update an.

## Hinweis und Lizenz

DJ Office Studio ist ein kostenloses Hilfsmittel zum Schreiben von Rechnungen und Angeboten. Die App prüft wichtige Pflichtangaben, garantiert aber nicht, dass jede Rechnung allen steuerlichen und rechtlichen Anforderungen entspricht – das hängt auch von der eigenen Situation ab (z. B. Kleinunternehmer oder umsatzsteuerpflichtig). **Für den Inhalt der Rechnungen ist jeder Nutzer selbst verantwortlich**; im Zweifel bitte den Steuerberater fragen. Die Nutzung erfolgt ohne Gewähr.

Die App zeigt diesen Hinweis beim ersten Start einmal an; danach steht er unter **⚙ Einstellungen → Hinweise & Lizenz**.

DJ Office Studio steht unter der [MIT-Lizenz](LICENSE): Nutzen, Weitergeben und Verändern sind ausdrücklich erlaubt.

Die Texterkennung verwendet [RapidOCR](https://github.com/RapidAI/RapidOCR) (© RapidOCR Authors) mit Modellen aus [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) (© Baidu bzw. PaddleOCR Authors), beides unter der Apache-Lizenz 2.0, dazu ONNX Runtime (MIT), OpenCV (Apache 2.0) und PDFium über pypdfium2 (BSD-3-Clause/Apache 2.0).

## Lokale Entwicklung

Voraussetzung: Python 3.10 bis 3.12 (im Container läuft 3.12; die Pakete der Texterkennung gibt es nicht für 3.9).

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
pip install -r desktop/requirements.txt       # eigenes App-Fenster (pywebview)
python desktop/start.py                       # aus dem Quellcode starten
pip install pyinstaller pillow && python desktop/build.py   # App bauen (auf dem jeweiligen System)
```

Die fertigen Windows- und Mac-Versionen baut GitHub Actions (`.github/workflows/desktop.yml`); ein Tag `desktop-v…` erzeugt daraus ein Release. Für die PDFs wird eine TTF-Schrift gesucht (im Container Carlito, lokal z. B. Arial); mit `FONT_REGULAR` und `FONT_BOLD` lässt sich ein eigener Pfad setzen.

### Screenshots für die README

Nach jeder sichtbaren Änderung die Bilder in `docs/bilder/` neu erzeugen (nur mit erfundenen Beispieldaten):

```bash
pip install playwright && python -m playwright install chromium
python docs/screenshots.py
```

### Tests

```bash
pip install -r rechnungen/requirements.txt pytest
pytest tests
```

Die Tests laufen auch automatisch bei jedem Push (GitHub Actions, `.github/workflows/tests.yml`) und vor jedem Bau der Desktop-Version.

### Aufbau

```
repository.yaml          Home-Assistant-Repository
LICENSE                  MIT-Lizenz
rechnungen/
  config.yaml            App-Definition (Name, Version)
  icon.png, logo.png     Symbol und Logo für den App-Store in Home Assistant
  CHANGELOG.md           Änderungen je Version
  Dockerfile             Python 3.12 (Debian) + Carlito-Schrift
  app/
    main.py              Flask-App: REST-API und Auslieferung der Oberfläche
    db.py                SQLite-Datenhaltung
    pdf.py               PDF-Erzeugung (fpdf2) inkl. QR-Code zum Bezahlen (segno)
    importer.py          Auslesen alter Rechnungs- und Angebots-PDFs (pypdf)
    mail.py              E-Mail-Versand per SMTP, Textvorlagen
    finanzen.py          Finanzen: Ausgaben, Fahrten, Anschaffungen/Abschreibung, EÜR, Export
    abschluss.py         Jahresabschluss: prüfen, Paket mit Prüfsumme, wieder öffnen; Kleinunternehmer/Fahrzeug je Jahr
    abos.py              Abos: wiederkehrende Ausgaben, fällige Abbuchungen, Belege erkennen
    vertraege.py         Booking-Verträge: Vorlage mit Bausteinen, eigener Vertrag hochladen, Vertragstext, Unterschrift
    kundenakte.py        Bar bezahlt (Quittung von Hand, Foto vom Durchschlag) und Jahres-Erinnerung für Stammkunden
    belege.py            Auslesen von Belegen (PDF, Fotos, Kauf-Mails .eml/.msg/.mbox)
    texterkennung.py     Texterkennung für Fotos und Scans (lokal, im eigenen Prozess)
    pdflesen.py          Lesen fremder PDFs im eigenen Prozess
    dateilesen.py        Outlook-Mails und HEIC-Vorschau im eigenen Prozess
    grenzen.py           Grenzen für Speicher, Zeit und Textlänge
    erechnung.py         Lesen von E-Rechnungen (XRechnung, ZUGFeRD/Factur-X) samt Lesefassung
    paperless.py         Abholen von Ausgaben-Belegen aus Paperless-ngx (REST-Schnittstelle, nur lesend)
    strecken.py          Entfernungen über OpenStreetMap (Nominatim, OSRM) mit Zwischenspeicher
    static/              Oberfläche (HTML, CSS, JavaScript; vertraege.js = Dokumente, kundenakte.js = Kundenakte und Vertrag → Rechnung,
                         rundgang.js = Rundgang und Schnellsuche)
desktop/
  start.py               Starter der Desktop-Version (Server + eigenes App-Fenster mit pywebview, Daten im Dokumente-Ordner)
  requirements.txt       Zusätzliche Pakete nur für die Desktop-Version (pywebview)
  build.py               Baut die Desktop-App mit PyInstaller
.github/workflows/
  desktop.yml            Baut Windows- und Mac-Version, bei Tag „desktop-v…“ als Release
  tests.yml              Führt bei jedem Push die Tests aus
docs/
  screenshots.py         Erzeugt die README-Screenshots (docs/bilder/) mit Beispieldaten
tests/                   Automatische Tests (pytest): API, PDFs, Pflichtangaben, Umsatzsteuer, QR-Code, Festschreiben/Storno,
                         Mahnungen, E-Mail-Versand, Sicherung, Import, Belege, Fahrten, Abschreibung, EÜR, Jahresabschluss, Abos, Verträge, Kundenakte …
```

### Neue Version veröffentlichen

`version` in `rechnungen/config.yaml` erhöhen, einen Eintrag in `rechnungen/CHANGELOG.md` ergänzen, committen und pushen. Home Assistant bietet das Update dann unter **Apps → App-Store → ⋮ → Nach Updates suchen** an. Für die Desktop-Version zusätzlich einen Tag `desktop-v<Version>` pushen – GitHub Actions baut dann die Windows- und Mac-Pakete und veröffentlicht sie als Release.

> Hinweis: Das Basis-Image ist im `Dockerfile` fest vorgegeben. Eine `build.yaml` wird vom Supervisor nicht beachtet – er würde sonst sein Alpine-Image verwenden, in dem `apt-get` fehlt.

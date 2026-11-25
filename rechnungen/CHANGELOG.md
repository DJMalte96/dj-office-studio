# Changelog

Alle Änderungen an DJ Office Studio. Neueste Version oben.

## 1.13.1 – 2026-11-25

### Sicherheit
- **Content-Security-Policy**: Der Browser führt nur noch die Skripte der App selbst aus – kein eingeschleuster Code, kein Inline-Code. Eine zweite Verteidigungslinie: Bei der Prüfung wurde kein Weg gefunden, Code über Textfelder, Dateinamen oder Mails einzuschleusen.
- **Kein Einbetten in fremde Seiten** (Clickjacking): Eine präparierte Webseite konnte die laufende Desktop-App unsichtbar einbinden und zu Klicks verleiten. Home Assistant bettet die App weiterhin ein.
- **Dateityp streng**: Jede Antwort trägt „nosniff“ – auch Vertragsanlagen und statische Dateien.
- **Unterschriebene Verträge**: Der Inhalt muss zur Endung passen; eine HTML-Datei namens „vertrag.pdf“ wird abgelehnt.
- **Flask 3.0.3 → 3.1.3 und fpdf2 2.8.1 → 2.8.9**: schließen die bekannten Lücken der Bibliotheken (betrafen die App nicht direkt).
- **Stammdaten**: Kunden, Rechnungsposten und Zahlungsbedingungen haben jetzt Längengrenzen.
- Entwicklung: GitHub-Workflows mit festen Action-Versionen und nur Leserechten für die Tests, `.gitignore` gegen versehentlich eingecheckte `.env`- und Datenbankdateien.

## 1.13.0 – 2026-11-25

### Neu
- **Booking-Verträge** im neuen Menü **Dokumente**:
  - **Neuer Vertrag** zu einem Angebot (Kunde, Termin, Ort, Spielzeit und Gage werden übernommen) oder **ohne Angebot** mit eigenen Angaben – bekannte Kunden werden mit Anschrift vorgeschlagen.
  - Im Vertragsfenster links Aufbauzeit, Ansprechpartner vor Ort, Anzahlung (Rest per Rechnung oder bar), Verpflegung, GEMA und die Abschnitte – rechts der Vertrag genau so, wie er als PDF herauskommt.
  - **Senden** per Mail mit PDF und Anlagen, oder **Als verschickt vermerken**. Ab dann steht der Text fest; **Wieder bearbeiten** öffnet ihn noch einmal.
  - **Unterschrieben** vermerken – als Datei (PDF/Foto, wird abgelegt und gesichert), per Mail bestätigt oder vor Ort; auf Wunsch wird das Angebot angenommen. Die Startseite erinnert an Verträge, die noch nicht zurück sind.
- **Vertragsvorlage**: Verpflegung, Ersatz-DJ, GEMA und Schäden durch Gäste sind eingeschaltet, 16 weitere übliche Bausteine zuschaltbar. Texte änderbar, Reihenfolge mit ↑ ↓, **eigene Abschnitte** mit Platzhaltern ({veranstalter}, {datum}, {ort}, {spielzeit}, {gage} …).
- **Eigenen Vertrag hochladen** (PDF, Word .docx, Text): Die App erkennt die Abschnitte und übernimmt die ausgewählten in die Vorlage. Ein PDF (z. B. AGB) kann unverändert an jeden Vertrag angehängt werden.
- Verträge stehen in der **Schnellsuche**, der **Rundgang** zeigt das Menü Dokumente.
- Die mitgelieferten Vertragstexte sind ein Vorschlag und keine Rechtsberatung.

### Geändert
- README: übersichtliches Inhaltsverzeichnis – sechs Themenblöcke mit kurzen Listen.

## 1.12.0 – 2026-11-25

### Neu
- **Rundgang durch die App**: Bei einer neuen Installation fragt die App nach dem ersten Hinweis „Kurzer Rundgang?“. In zwölf Schritten zeigt sie Menü, Einstellungen, Startseite, Rechnung schreiben, Rechnungen, Angebote, Ausgaben, EÜR, Schnellsuche und Datensicherung – der jeweilige Bereich wird hervorgehoben, die App wechselt selbst auf die passende Seite. Weiter/Zurück auch mit den Pfeiltasten, Esc beendet.
  - Jederzeit wiederholbar unter ⚙ Einstellungen → **Rundgang starten**.
  - Bestehende Installationen bekommen den Rundgang nach dem Update nicht angeboten.
- **Schnellsuche**: Lupe oben rechts oder **Strg + K** (Mac: **⌘ + K**). Sucht in Rechnungen, Angeboten, Kunden, Belegen und Seiten – nach Name, Ort, Nummer, Text, Datum oder Betrag, mehrere Wörter grenzen ein (z. B. „eva hochzeit“). Mit ↑ ↓ und Enter direkt öffnen: Rechnung oder Angebot im Editor, Kunde mit seinen Rechnungen, Beleg im Prüfen-Dialog oder die Seite.

### Behoben
- **„database is locked“ auf langsamen Geräten**: Lief im Hintergrund gerade die Texterkennung, konnte z. B. die Ausgabenliste auf einem Raspberry Pi mit einem Fehler abbrechen. Die App wartet jetzt bis zu 30 statt 5 Sekunden, bis der Schreibvorgang fertig ist.

## 1.11.0 – 2026-11-25

### Neu
- **Angebote nachfassen**: Hat ein Kunde nach einigen Tagen nicht geantwortet, steht unter „Heute wichtig“ z. B. „✉ 2 Angebote nachfragen“, und an der Karte bzw. in der Angebotsliste steht „keine Antwort seit 10 Tagen“.
  - **Nachfragen** öffnet eine fertige Mail; das Angebot hängt auf Wunsch noch einmal an. Ohne eingerichteten Mailversand: Text kopieren (z. B. für WhatsApp).
  - „Als nachgefragt vermerken“, „Angenommen → Rechnung“ oder „Abgelehnt“ direkt im Dialog.
  - Erinnert wird einmal pro Angebot, solange es gültig ist. Die Tage (Standard 7, 0 = nie) stehen unter ⚙ Einstellungen → Nummern & Fristen, die Vorlage bei den Textvorlagen.
- **Preis-Spickzettel**: Im Editor zeigt die App unter jeder Position, was du für diesen Rechnungsposten bisher genommen hast – zuletzt, im Schnitt, von–bis und pro Stunde (mit Vorschlag für die eingetragene Dauer), dazu was der Kunde zuletzt gezahlt hat. Ein Klick auf einen Betrag übernimmt ihn. Liegt der Preis deutlich unter oder über dem Schnitt, steht das dabei. Auch bei Angeboten.
- **Anzahlungen**: Unter den Positionen steht „Art der Rechnung“ – **Normale Rechnung** (wie bisher), **Anzahlungsrechnung** oder **Schlussrechnung**. Wer keine Anzahlungen nutzt, muss nichts tun.
  - **Anzahlungsrechnung**: Leistung mit Gesamtpreis eintragen, dann „Anzahlungsrechnung“ – daraus wird eine Anzahlung über z. B. 30 % oder einen festen Betrag. Die App merkt sich den letzten Wert. Die Fahrt wird erst mit der Schlussrechnung erfasst.
  - **Schlussrechnung**: Die Anzahlungsrechnungen des Kunden stehen zum Anhaken da und werden als eigene Minus-Zeile abgezogen; der Betrag kommt immer aus der Anzahlungsrechnung (bei Umsatzsteuer netto). Das PDF heißt „Anzahlungsrechnung“ bzw. „Schlussrechnung“ mit „Restbetrag“.
  - Kommt die Anzahlung aus einem Angebot, macht „→ Rechnung“ daraus später automatisch die Schlussrechnung; die Startseite erinnert nach der Feier („✎ Schlussrechnung …“).
  - In der EÜR zählt jede Zahlung in ihrem Jahr. Eine abgezogene Anzahlung lässt sich nicht mehr ändern, löschen oder stornieren, bis die Schlussrechnung storniert ist. Der Export für den Steuerberater nennt Anzahlungs- und Schlussrechnungen.

## 1.10.0 – 2026-11-23

### Neu
- **Neue Startseite**: oben „Heute wichtig“ mit allem, was ansteht (überfällige Rechnungen, fällige Abos, ungeprüfte Belege, ablaufende Angebote, fällige Sicherung) und die Schnellknöpfe Neue Rechnung, Neues Angebot, Beleg hochladen. Darunter „Demnächst“ mit den nächsten Terminen – bei viel Betrieb als Leiste der nächsten 14 Tage –, eine Pinnwand „Geld kommt rein / Geld geht raus / Angebote“ mit Knöpfen direkt am Eintrag (Zahlungserinnerung, QR-Code, ✓ Bezahlt, → Rechnung …), „Dein Jahr“ und eine Statuszeile (Sicherung, Kleinunternehmer-Grenze, Jahr abschließen).
- In ruhigen Zeiten wirkt die Seite aufgeräumt statt leer: leere Spalten fallen weg, „Dein Jahr“ ist immer gefüllt.
- Die acht Kacheln, „Umsatz“ und „Letzte Rechnungen“ sind weggefallen – alles ist weiter über das Menü erreichbar.

### Behoben
- Abos: Ein unmögliches Datum für eine Preisänderung (z. B. 30. Februar) wurde angenommen.

## 1.9.0 – 2026-11-23

### Neu
- **Abos – wiederkehrende Ausgaben** (Finanzen → Ausgaben → ↻ Abos): Musikpool, DJ-Software & Co. einmal anlegen. Rhythmus wöchentlich, alle 4 Wochen, monatlich, alle 2 Monate, vierteljährlich, halbjährlich, jährlich, alle 2 Jahre oder eigener Rhythmus („alle 18 Monate“). Liste mit Kosten im Monat und im Jahr.
- **Fällige Abbuchungen bestätigen**: Am Tag der Abbuchung steht das Abo unter „Neu – bitte prüfen“ – bestätigen, Betrag ändern (nur diesmal oder ab jetzt) oder aussetzen. Erst Bestätigtes zählt in der EÜR. Die Startseite erinnert daran.
- **Nichts doppelt**: Eine passende Rechnungs-Mail bzw. ein PDF (auch aus Paperless oder dem Belege-Ordner) oder eine schon erfasste Ausgabe erkennt die App und verknüpft sie mit der Abbuchung.
- **10-Tage-Regel für Abos automatisch**: Abbuchungen ab dem 22.12. zählen zum neuen Jahr (nicht bei wöchentlichen Abos).
- **Jahresabschluss**: Nicht bestätigte Abo-Abbuchungen des Jahres sind ein roter Punkt; in ein abgeschlossenes Jahr wird nichts gebucht.

## 1.8.1 – 2026-11-23

### Behoben
- **10-Tage-Regel**: Wurde eine Zahlung dem anderen Jahr zugeordnet und danach ihr Datum geändert, zählte sie weiter zum falschen Jahr. Jetzt zählt sie nach einer Datumsänderung wieder nach dem Datum.
- **Jahr abschließen von zwei Geräten gleichzeitig**: Ein zweiter, abgewiesener Versuch konnte die Paketdatei überschreiben, sodass die Prüfsumme nicht mehr passte. Jetzt läuft immer nur ein Abschluss; die Paketdatei kommt erst nach Erfolg an ihren Platz.
- **Abschluss sperrt zuerst**: Erst wird das Jahr gesperrt, dann gerechnet und gepackt. Eine Änderung in diesen Sekunden auf einem anderen Gerät wird abgewiesen, statt zu fehlen. Geht beim Packen etwas schief, wird die Sperre wieder aufgehoben.

### Verbessert
- **Weniger Arbeitsspeicher**: Jahresabschluss, Export und Datensicherung werden über eine Datei erstellt und gesendet, statt komplett im Arbeitsspeicher. Bei 200 MB Belegen braucht der Abschluss rund 90 statt 700 MB – wichtig z. B. auf einem Raspberry Pi mit Home Assistant.

## 1.8.0 – 2026-11-23

### Neu
- **Jahr abschließen** (Finanzen → EÜR & Export): ein fertiges Jahr in drei Schritten prüfen, kontrollieren und abschließen – ab dem 11. Januar des Folgejahres. Ein Jahr wird nie von selbst gesperrt. Die Startseite erinnert dezent daran (ausblendbar).
  - **Prüfen**: Rot markierte Punkte müssen erledigt sein; „ansehen“ führt hin und unten rechts wieder zurück. Gelb: noch offene Rechnungen (auch gleich mit Datum als bezahlt eintragen) und regelmäßige Zahlungen in den 10 Tagen um Silvester (10-Tage-Regel, einem Jahr zuordnen).
  - **Kontrollieren**: Einnahmen, Ausgaben und Gewinn im Vergleich zum Vorjahr, dazu die Kleinunternehmer-Grenze.
  - **Abschließen**: Paket mit Abschlussblatt (PDF), EÜR, allen Tabellen, Rechnungen und Belegen sowie SHA-256-Prüfsummen. Paket und Blatt liegen unter EÜR & Export und sind in der Datensicherung enthalten.
- **Gesperrtes Jahr**: Einträge tragen ein 🔒 und öffnen sich nur zum Ansehen. Die Sperre sitzt in der Datenbank und gilt auf allen Wegen – Oberfläche, Import, Hintergrundaufgaben. Erneut verschicken, herunterladen, exportieren, eine offene Rechnung später bezahlen und ein Gerät später verkaufen gehen weiter.
- **Wieder öffnen** mit Grund – Vorschläge zum Antippen, eigene Gründe merkt sich die App. Das alte Paket bleibt; das Abschlussblatt der nächsten Fassung zeigt Grund und Änderung beim Gewinn.
- **Kleinunternehmer und Fahrzeug je Jahr**: Die Einstellungen gelten fürs laufende Jahr, frühere Jahre behalten ihre Werte (⚙ Einstellungen → Steuer → Frühere Jahre).

### Behoben
- Eine Änderung von Kleinunternehmer oder Fahrzeug in den Einstellungen änderte rückwirkend die EÜR aller früheren Jahre. Beim Update werden die vergangenen Jahre mit den heutigen Einstellungen festgehalten.

## 1.7.3 – 2026-11-23

### Sicherheit
- **Fremde Webseiten können die App nicht mehr fernsteuern**: Bisher konnte eine präparierte Webseite, die man öffnete, während die Desktop-App lief, eine Sicherung einspielen (und damit z. B. die IBAN ändern) oder Belege unterschieben. Über einen umgeleiteten Domainnamen konnte sie sogar alle Daten auslesen. Jetzt nimmt die App Änderungen nur noch von ihrer eigenen Oberfläche an, und die Desktop-App antwortet nur noch unter 127.0.0.1 bzw. localhost.
- **Home Assistant**: Die App nimmt nur noch Anfragen über den Home-Assistant-Eingang an, nicht mehr von anderen Add-ons im internen Netz.
- **Mail-Passwort und Paperless-Token gehen nur noch an den gespeicherten Server**: Beim Mail-Test oder bei „Verbindung prüfen“ mit einem neuen Server bzw. einer neuen Adresse muss man Passwort bzw. Anmeldung neu eingeben. Wird der Postausgangsserver, der Benutzer oder die Paperless-Adresse geändert und gespeichert, verwirft die App das alte Passwort bzw. den alten Token und sagt das dazu.
- **Sicherungen einspielen**: Eine Sicherung darf entpackt nicht mehr beliebig groß werden (Zip-Bombe), und vorher prüft die App den freien Speicherplatz.
- **Paperless**: Leitet Paperless auf einen anderen Rechner um, geht der Token nicht mit. Antworten und Seitenzahl sind begrenzt.

## 1.7.2 – 2026-11-22

### Behoben
- **Festgeschriebene Rechnungen behalten ihren Absender**: Anschrift, Bankverbindung, Steuerangaben und GiroCode werden beim Festschreiben festgehalten. Bisher trug eine alte Rechnung nach einem Umzug oder Kontowechsel die neuen Angaben, wenn man sie erneut öffnete, verschickte oder exportierte. Mahnungen halten ihren eigenen Absender fest.
- **Rückfrage beim Ändern des Absenders**: Gibt es noch nicht festgeschriebene Rechnungen, fragt die App, welche schon verschickt sind. Die werden mit dem bisherigen Absender festgeschrieben, die übrigen bekommen den neuen.
- **Beim Update**: Schon festgeschriebene Rechnungen und Mahnungen bekommen den **heutigen** Absender festgehalten, den früheren kennt die App nicht. Wer seitdem umgezogen ist oder das Konto gewechselt hat, findet das Original in der abgelegten PDF-Kopie, in Paperless oder in der gesendeten Mail. Das 🔒 zeigt den festgehaltenen Absender.

### Sicherheit
- **Outlook-Mails (.msg) und die Vorschau von HEIC-Fotos** laufen jetzt wie PDFs in einem eigenen Prozess mit Grenzen für Arbeitsspeicher und Zeit.
- **Fotos** werden nur noch in üblichen Bildformaten geöffnet. Eine als Foto benannte EPS-Datei kann kein Fremdprogramm mehr starten.

## 1.7.1 – 2026-11-22

### Sicherheit
- **Präparierte PDFs können die App nicht mehr lahmlegen**: Jedes fremde PDF wird in einem eigenen Prozess mit Grenzen für Arbeitsspeicher und Zeit gelesen, ohne Netz. Wird eine Grenze erreicht, bleibt der Beleg erhalten und bekommt einen Hinweis. Das gilt für Belege, PDF-Anhänge in Mails, den Import alter Rechnungen und die Texterkennung.
- **Präparierte Texte und Mails**: Riesige Ziffernfolgen, Zeilen, Kopfzeilen und kaputtes HTML halten die Auswertung nicht mehr an.
- **pypdf 5.1.0 → 7.1.1**: schließt die bekannten Lücken der PDF-Bibliothek.
- **waitress 3.0.0 → 3.0.2**: schließt die bekannten Lücken des Webservers.

### Behoben
- **Betragserkennung in PDFs**: „Gesamtbetrag der Abschläge“ und andere Teilsummen gelten nicht mehr als Gesamtbetrag, „Bruttosumme“ und „Zahlbetrag“ werden auch ohne €-Zeichen erkannt. Außerdem liest die neue PDF-Bibliothek Text aus PDFs, die bisher leer blieben.

### Geändert
- Von PDFs über 100 Seiten liest die App die ersten 90 und die letzten 10 Seiten und sagt das dazu. Beim Import alter Rechnungen werden solche PDFs abgelehnt.

## 1.7.0 – 2026-11-22

### Neu
- **E-Rechnungen empfangen**: XRechnung (UBL und CII) und ZUGFeRD/Factur-X – als XML, im PDF eingebettet oder als Anhang einer Mail, per Hochladen und über den Belege-Ordner.
  - Verkäufer, Rechnungsnummer, Datum, Bruttobetrag und Umsatzsteuer kommen aus den Rechnungsdaten statt aus dem Text. Bestätigt wird wie bisher.
  - **Lesefassung** mit Positionen und Summen. Das Original bleibt unverändert und kommt in Export und Sicherung.
  - **Warnungen**: eigene Rechnung, Gutschrift (wird negativ vorgeschlagen), Fremdwährung, Anzahlung, Steuerschuld des Empfängers, abweichender Betrag im sichtbaren PDF und dieselbe Rechnung schon in anderer Form vorhanden.
  - Gelesen wird lokal. Die App prüft die Dateien nicht amtlich auf Gültigkeit.
- **Belege-Ordner meldet, was liegen bleibt**: andere Dateitypen, XML ohne Rechnung, beschädigte Dateien.
- **Beim Update**: Bisher übersprungene XML-Rechnungen im Belege-Ordner werden eingelesen, ungeprüfte Belege mit E-Rechnung einmalig nachgelesen. Übernommene und von Hand geänderte Werte bleiben, wie sie sind.

### Geändert
- **Aus Paperless abholen** lädt PDFs, XML und Mails als Original, damit die E-Rechnung erhalten bleibt. Reine Scans kommen weiter als Archivfassung mit Texterkennung. Schon Abgeholtes bleibt unverändert.

### Behoben
- **Belege-Ordner im Nur-lesen-Modus**: Eine Datei, deren Einlesen scheitert, wird noch einmal versucht statt als gesehen gemerkt.
- **Handy**: Ein langer Pfad des Belege-Ordners schiebt die Seite nicht mehr breiter.

### Sicherheit
- CSV-Export: Texte aus Belegen können in Excel nicht mehr als Formel ausgeführt werden.
- Desktop-App: Als PDF erkannte Belege werden nur noch mit der Endung .pdf geöffnet.

## 1.6.1 – 2026-11-22

### Behoben
- **Ältere Jahre fehlten in den Jahresmenüs**: Ausgaben, Fahrten, Anschaffungen, Übersicht, EÜR und der Export in den Einstellungen bieten jetzt alle Jahre seit dem ältesten Eintrag an. Die Daten waren immer da, nur nicht auswählbar. Bei Ausgaben verschwand ein Jahr, sobald dessen letzter Beleg übernommen war.
- **Eigener Name als Lieferant**: Name, Kontoinhaber und Anschrift aus den Einstellungen sowie die eigene Mailadresse (weitergeleitete Mails) werden nicht mehr als Lieferant vorgeschlagen. Das Feld bleibt dann leer und ein Hinweis erinnert daran, dass eigene Rechnungen keine Ausgaben sind. Schon erfasste Ausgaben bleiben unverändert.
- **Beleg prüfen**: Fehlt der Lieferant, steht der Cursor gleich in diesem Feld, statt zum Knopf „Übernehmen“ nach unten zu springen.

## 1.6.0 – 2026-11-22

### Neu
- **Papierkorb für Ausgaben**: „Verwerfen“ und „Löschen“ sind nicht mehr endgültig. Unter Finanzen → Ausgaben → **Papierkorb** lassen sich Belege ansehen, wiederherstellen oder endgültig löschen.
  - Was im Papierkorb liegt, zählt nicht in EÜR, Übersicht, Abschreibung und Export; Anschaffungen kommen samt Nutzungsdauer zurück.
  - Derselbe Beleg noch einmal hochgeladen oder in den Belege-Ordner gelegt: Die App bietet das Wiederherstellen an.
  - Geleert wird nur von Hand.
- **Einmalig beim Update**: Was früher aus dem Belege-Ordner (auch der Ablage von Paperless) verworfen wurde und dort noch liegt, kommt in den Papierkorb. Früher verworfene Uploads lassen sich nur aus älteren Sicherungen holen.

### Behoben
- „Aus Paperless abholen“ holte verworfene Belege bei jedem Abholen erneut herein.

## 1.5.0 – 2026-11-22

### Neu
- **Texterkennung für Fotos und Scans**: Die App liest Lieferant, Datum, Betrag und Umsatzsteuer aus fotografierten Bons und eingescannten PDFs – auch schief, quer oder auf dem Kopf, auch iPhone-Fotos (HEIC).
  - Vollständig lokal und ohne Netzwerk; kein Beleg verlässt das Gerät.
  - Läuft im Hintergrund. Eigene Eingaben und übernommene Belege werden nie überschrieben.
  - Bereits vorhandene, noch ungeprüfte Fotos und Scans ohne Betrag werden nach dem Update automatisch nachgelesen.
  - Kassenbons: Summen ohne €-Zeichen und Datum mit zweistelligem Jahr werden erkannt; gegebenes Bargeld wird nicht als Betrag genommen.

### Sicherheit
- Eine **manipulierte Sicherungsdatei** konnte (seit 1.1.0) nach dem Einspielen dazu führen, dass beim Verwerfen eines Belegs fremde Dateien gelöscht oder in den Steuerberater-Export aufgenommen werden. Belegpfade gelten jetzt nur noch innerhalb der Belegablage. Selbst erstellte Sicherungen waren nicht betroffen.

### Behoben
- **Desktop-App für Intel-Macs**: Das Paket enthielt versehentlich Programmteile, die macOS 15 verlangen (betrifft auch 1.4.3). Sie sind entfernt; jeder Build wird jetzt auf macOS 13 als Mindestversion geprüft.

### Hinweise
- Das Update und die Downloads der Desktop-App sind deutlich größer (Modelle und Bibliotheken der Texterkennung); das erste Update in Home Assistant dauert länger.
- Die Texterkennung braucht kurzzeitig etwa 300–600 MB freien Arbeitsspeicher und am Mac mindestens macOS 13.

## 1.4.3 – 2026-11-21

### Behoben
- Rechnungen und Angebote: Ein ungültiges Datum (z. B. 31.02.) wird jetzt auch vom Server abgelehnt – mit verständlicher Meldung – statt gespeichert zu werden.
- Angebote: Ein Tippfehler im Angebotsdatum führte beim automatischen Nachrechnen von „Gültig bis“ zu einem Fehler im Hintergrund; „Gültig bis“ bleibt jetzt einfach stehen, bis das Datum vollständig ist.
- Belege-Ordner: Der Hintergrund-Wächter startet nur noch beim Programmstart (Home Assistant und Desktop-App) und nicht mehr beim ersten Seitenaufruf.

## 1.4.2 – 2026-11-21

### Geändert
- Kleine Textkorrektur beim Extra in den Einstellungen.

## 1.4.1 – 2026-11-21

### Neu
- Ein kleines Extra ganz unten in den Einstellungen.

## 1.4.0 – 2026-11-21

### Neu
- **Kleinunternehmer-Grenzen im Blick**: Die Finanzen-Übersicht zeigt für Kleinunternehmer eine Karte mit dem Umsatz des Jahres gegenüber den Grenzen nach § 19 UStG (seit 2025):
  - **25.000 €** – wer sie im Jahr überschreitet, ist im **nächsten** Jahr kein Kleinunternehmer mehr; ebenso, wenn der Vorjahresumsatz darüber lag.
  - **100.000 €** – darüber besteht **sofort** Umsatzsteuerpflicht; die App nennt den Tag, an dem die Grenze überschritten wurde.
  - Gezählt wird wie im Gesetz das tatsächlich eingenommene Geld (bezahlte Rechnungen nach Zahlungseingang, Stornos abgezogen). Offene Rechnungen und eine grobe Hochrechnung fürs Jahr zeigen, ob es knapp wird.
  - Warnungen erscheinen auf der Übersicht, der Startseite und in der Prüfliste der EÜR. Hinweis fürs Gründungsjahr (dort gilt schon 25.000 €).

## 1.3.1 – 2026-11-21

### Behoben
- **Datum eintippen in Safari und der Desktop-App am Mac**: Das Jahr ließ sich nicht eingeben („2019“ wurde zu „0019“). Alle Datumsfelder nehmen das Datum jetzt als Text im deutschen Format an – `7.10.2019`, `07.10.19` oder `07102019`, ohne Jahr gilt das aktuelle. Ein Kalender-Symbol im Feld öffnet weiterhin den Kalender. Ungültige Daten (z. B. 31.02.) werden abgelehnt.
- **Beleg-Erkennung bei Händler-Rechnungen**: Beträge ohne €-Zeichen, bei denen „EUR“ nur in der Beschriftung steht (z. B. „Total EUR inkl. MwSt. 788,48“), werden jetzt erkannt. Zeilen mit „inkl. MwSt.“ bzw. „brutto“ haben Vorrang – vorher konnte die App aus der Steuertabelle den Nettobetrag nehmen. Auch die Umsatzsteuer aus Tabellen wie „19 % 662,59 125,89“ wird erkannt.
- Belege aus Paperless: Das Datum im Beleg hat Vorrang vor dem Datum aus Paperless (dort steht oft der Tag des Imports).

## 1.3.0 – 2026-11-20

### Neu
- **Belege-Ordner**: Alles, was in einem Ordner landet (PDFs, Fotos, Mails, Postfach-Exporte), liest die App automatisch ein – jede Minute und beim Öffnen der Ausgaben. In Home Assistant ist das `/share/belege` (wird angelegt), in der Desktop-Version ein frei wählbarer Ordner. Eingelesene Dateien wandern in den Unterordner „übernommen“. Praktisch mit Scanner-Apps, Cloud-Ordnern oder Mail-Regeln – ganz ohne Paperless.
- **Ablage von Paperless direkt lesen**: Legt Paperless die Ausgaben per Speicherpfad in einen eigenen Ordner, findet **Ausgaben-Ordner von Paperless suchen** ihn selbst (z. B. `…/originals/DJ/*/Ausgaben` für alle Jahre). Keine Anmeldung nötig; die Dateien bleiben unverändert liegen (nur lesen), neue kommen automatisch dazu.

### Geändert
- Der Paperless-Teil in den Einstellungen und der Knopf „Aus Paperless abholen“ erscheinen nur noch, wenn „Paperless-ngx ist installiert“ angehakt ist. Die Anmeldung über die Paperless-Schnittstelle gibt es weiterhin als Alternative.

### Behoben
- Paperless-Schnittstelle: „Paperless meldet Fehler 403“ – die App hatte den Ingress-Eingang des Add-ons statt Paperless selbst erwischt. Gezählt wird jetzt nur eine echte Antwort von Paperless; eine falsch gefundene Adresse wird nicht mehr gespeichert und blockiert die weitere Suche nicht.

## 1.2.1 – 2026-11-20

### Verbessert
- **Paperless einfacher verbinden**: Statt Adresse und API-Token reicht jetzt die normale Paperless-Anmeldung (Benutzername und Passwort). Die App holt sich damit einen Zugangsschlüssel – das Passwort wird nicht gespeichert.
- **Paperless-Add-on wird automatisch gefunden**: Die App fragt Home Assistant, welche Add-ons installiert sind, und nimmt Adresse und Port vom Paperless-Add-on. Läuft das Add-on nicht, sagt die Meldung das. Dafür braucht das Add-on die Berechtigung, die Liste der Add-ons zu lesen (`hassio_api`).
- Der Tag der Ausgaben-Belege wird sofort gespeichert; heißt er z. B. „Ausgaben“ oder „Belege“, ist er schon vorausgewählt. Adresse und Token von Hand gibt es weiterhin unter „Erweitert“ (z. B. für die Desktop-Version).

## 1.2.0 – 2026-11-20

### Neu
- **Ausgaben-Belege aus Paperless-ngx abholen**: Unter Finanzen → Ausgaben holt **⇩ Aus Paperless abholen** alle Dokumente mit einem bestimmten Tag (z. B. „Ausgaben“), die noch nicht übernommen sind – auch aus früheren Jahren.
  - Einrichten unter ⚙ Einstellungen → Ablage & Paperless: Adresse (oder automatisch suchen lassen), API-Token aus Paperless, Tag auswählen.
  - Lieferant und Datum kommen aus Paperless (Korrespondent, Ausstellungsdatum), der Betrag wird gelesen – bei Fotos und Scans aus der Texterkennung von Paperless.
  - Die App speichert eine Kopie der PDF, Export und Sicherung funktionieren also auch ohne laufendes Paperless. Schon von Hand hochgeladene Belege werden erkannt und nur verknüpft.
  - In Paperless wird nichts verändert. Der API-Token wird nur lokal gespeichert und ist – wie das E-Mail-Passwort – nicht in der Sicherung enthalten.

## 1.1.4 – 2026-11-20

### Neu
- **Ganze Mail-Ordner importieren**: In Apple Mail einen Ordner per *Postfach → Postfach exportieren …* sichern und den Ordner „….mbox“ in die Ausgaben ziehen – jede Mail wird ein eigener Beleg. Thunderbird-Ordner (mbox) gehen genauso. Doppelte Mails werden erkannt, ein Ordner kann also später einfach noch einmal importiert werden.
- **Ordner aus dem Finder** lassen sich hineinziehen – alle Belege darin (auch in Unterordnern) werden übernommen.

### Behoben
- Mails direkt aus Apple Mail auf das Feld gezogen: Bisher passierte stumm nichts. Jetzt erscheint eine kurze Anleitung, wie es klappt (Apple Mail gibt Mails beim Ziehen nicht an den Browser weiter).

## 1.1.3 – 2026-11-20

### Behoben
- **Fahrten blieben bei „wird berechnet …“ stehen**, wenn die automatische Kilometer-Berechnung erst nachträglich eingeschaltet wurde oder die App während der Berechnung neu gestartet ist (z. B. durch ein Update). Beim Öffnen der Fahrtenliste werden offene Fahrten jetzt automatisch berechnet.
- Geht bei der Berechnung etwas Unerwartetes schief, zeigt die Fahrt „km fehlen“ mit dem Grund, statt dauerhaft „wird berechnet …“.

## 1.1.2 – 2026-11-20

### Verbessert
- **Bezahlt-Datum mit einem Klick**: Bei bezahlten Rechnungen ohne Zahlungsdatum (z. B. alte Importe) übernimmt „Bei allen das Rechnungsdatum übernehmen“ das Rechnungsdatum für alle auf einmal. Einzeln nachtragen ist nur noch nötig, wenn das Geld erst im neuen Jahr kam.
- Beim Import alter Rechnungen als „bezahlt“ wird das Rechnungsdatum jetzt automatisch als Bezahlt-Datum eingetragen.

## 1.1.1 – 2026-11-20

### Verbessert
- **Belege in großen Mengen hochladen**: Beliebig viele Belege und Kauf-Mails auf einmal hineinziehen – bisher war bei 1000 Dateien bzw. 100 MB Schluss. Die App lädt sie jetzt in Paketen hoch und zeigt den Fortschritt („120 von 800 Belegen gelesen …“). Bei vielen doppelten Belegen nennt die Meldung nur noch die Anzahl statt aller Dateinamen.
- Bricht das Hochladen ab (z. B. Verbindung weg), sagt die Meldung, wie viele Dateien schon übernommen wurden. Einfach noch einmal hineinziehen – bereits vorhandene werden erkannt.
- Zu große Uploads (auch beim Einspielen einer Sicherung) bekommen eine verständliche Fehlermeldung statt eines unklaren Fehlers.

## 1.1.0 – 2026-11-20

**Neu: Finanzen.** Ein neuer Menüpunkt mit allem, was für die Steuererklärung gebraucht wird – Ausgaben, Fahrten, Abschreibungen und die Einnahmen-Überschuss-Rechnung (EÜR) samt Export für den Steuerberater.

### Neu
- **Ausgaben mit Belegen**: PDF-Rechnungen, Fotos (JPG, PNG, HEIC) und Kauf-Mails (.eml, .msg) per Drag & Drop hochladen – auch mehrere auf einmal.
  - Die App erkennt Lieferant, Datum, Betrag und Umsatzsteuer und zeigt, wo sie den Betrag gefunden hat.
  - Shops wie Beatport, iTunes/Apple, Amazon, Qobuz und Bandcamp werden am Absender erkannt; die Kategorie wird vorgeschlagen und je Lieferant gelernt.
  - **Prüfen-Ansicht**: links der Beleg (Mails als sichere Vorschau), rechts die erkannten Angaben – „Alle nacheinander prüfen“.
  - Originale bleiben unverändert gespeichert, doppelte Belege werden erkannt.
  - Ausgaben ohne Beleg mit Notiz, Privatanteil in Prozent, Musikkäufe je Monat zusammengefasst.
- **Fahrten**: Zu jeder Rechnung automatisch die Hin- und Rückfahrt zum Veranstaltungsort.
  - Neue Karte „Veranstaltung & Fahrt“ im Editor: abweichender Veranstaltungsort (steht auch auf dem PDF) und „Fahrt erfassen“ pro Rechnung abwählbar.
  - Kilometer optional über OpenStreetMap (ausschaltbar; dann von Hand), korrigierbar, eigene Fahrten ergänzbar.
  - Privatfahrzeug mit Kilometerpauschale (Satz einstellbar) oder Betriebsfahrzeug.
- **Anschaffungen & Abschreibung**: Geräte über 800 € netto werden linear und monatsgenau abgeschrieben (Computer im Kaufjahr voll). Anlagenverzeichnis, Geräte aus Vorjahren mit Restwert übernehmen, Verkauf/Ausscheiden. Hinweis beim Erfassen, wenn ein Betrag über bzw. unter der 800-€-Grenze liegt.
- **Übersicht**: Einnahmen, Ausgaben und Gewinn des Jahres, Diagramm je Monat (auch als Tabelle), Ausgaben nach Kategorie.
- **EÜR & Export**: EÜR nach Zahlungseingang und -ausgang mit Vorschlag für die Zeilen der Anlage EÜR (Kleinunternehmer brutto, sonst netto mit Umsatzsteuer und Vorsteuer). Prüfliste vor dem Export, Bezahlt-Datum für alte Importe nachtragen, sonstige Einnahmen ohne Rechnung.
- **Export für den Steuerberater** enthält jetzt zusätzlich EÜR, Einnahmen, Ausgaben, Fahrten und Anlagenverzeichnis als Excel-Tabellen sowie alle Belege (Dateiname `Export_<Jahr>.zip`).
- **Startseite**: neue Karte „Finanzen“ mit dem Gewinn des laufenden Jahres und einem Hinweis auf ungeprüfte Belege.
- **Einstellungen → Fahrten**: Fahrzeug, Kilometersatz, Startadresse, Kartendienst, „Fahrt erfassen“ als Standard.

### Geändert
- Die **Sicherung** enthält jetzt auch alle Ausgaben-Belege; beim Einspielen werden sie wiederhergestellt.

## 1.0.2 – 2026-11-20

### Behoben
- **Windows: App öffnete sich trotz 1.0.1 im Browser statt im eigenen Fenster.** Ursache: Wird die App als ZIP heruntergeladen und mit Windows entpackt, markiert Windows alle Dateien als „aus dem Internet geladen“; der Baustein für das Edge-Fenster wurde dann nicht geladen (im Protokoll: „Failed to resolve Python.Runtime.Loader.Initialize“). Die App entfernt diese Markierung jetzt beim Start von ihren eigenen Programmdateien – wie „Eigenschaften → Zulassen“, nur automatisch. Ein automatischer Test stellt diesen Fall bei jedem Windows-Build nach.

## 1.0.1 – 2026-11-20

### Geändert
- **Desktop-Version (Windows/macOS) im eigenen Fenster**: DJ Office Studio öffnet sich jetzt in einem eigenen Programmfenster statt im Browser – ohne Adresszeile und Tabs. Fenster schließen beendet die App; das kleine Statusfenster entfällt.
  - PDFs (Vorschau, Rechnungen, Mahnungen, Stornos) öffnen sich im PDF-Programm des Computers.
  - Sicherung, Export und ZIP-Downloads werden über „Speichern unter“ abgelegt.
  - Links (Changelog, Update, Lizenz) öffnen sich im Standardbrowser.
  - Neu unter ⚙ Einstellungen: **Daten- und PDF-Ordner öffnen**.
  - Texte lassen sich markieren und kopieren, Zoomen mit ⌘/Strg + und −.
  - Unter Windows nutzt das Fenster Microsoft Edge WebView2 (bei Windows 10/11 vorhanden). Ist kein eigenes Fenster möglich, öffnet sich die App wie bisher im Browser.
- Für die Home-Assistant-App ändert sich nichts.

## 1.0.0 – 2026-11-17

**Erste stabile Version.** DJ Office Studio deckt jetzt alles ab, was für Rechnungen und Angebote im DJ-Alltag gebraucht wird: Rechnungen und Angebote mit Pflichtangaben-Prüfung, Kleinunternehmerregelung oder Umsatzsteuer, QR-Code zum Bezahlen, E-Mail-Versand, Zahlungserinnerungen und Mahnungen, Festschreiben und Storno, Kopieren, Paperless-Anbindung, Import alter PDFs, Datensicherung mit Erinnerung und Export für den Steuerberater – in Home Assistant und als Desktop-App für Windows und macOS. Ab jetzt gilt: Updates ändern nichts an bestehenden Daten, ohne dass die App sie automatisch anpasst; 1.0.x enthält nur Fehlerbehebungen, neue Funktionen kommen mit 1.1, 1.2 …

### Behoben
- **E-Mail zu Stornorechnungen**: Der vorausgefüllte Text lautete bisher „Vielen Dank für Ihren Auftrag! Im Anhang finden Sie die Rechnung … über -500,- Euro“. Jetzt: „Stornorechnung 042 zur Rechnung 038“ mit passendem Text.
- **Startseite am Handy**: Die Seite war breiter als der Bildschirm (lange Angebotszeilen); Betrag und Frist stehen jetzt unter dem Namen.
- Unvollständige oder ungültige Anfragen an die App führen zu einer verständlichen Fehlermeldung statt zu einem Serverfehler.
- README an den aktuellen Funktionsumfang angepasst.

## 0.18.0 – 2026-11-17

### Neu
- **Umsatzsteuer für Nutzer ohne Kleinunternehmerregelung**: Ist unter ⚙ Einstellungen → Steuer „Kleinunternehmer“ ausgeschaltet, sind die Positionspreise Nettopreise. Rechnungen, Angebote und Stornorechnungen weisen dann Nettobetrag, Umsatzsteuer (19 % oder 7 %) und Gesamtbetrag aus; Gesamtbetrag, Mahnungen, GiroCode und E-Mail-Vorlagen verwenden den Bruttobetrag. Der Editor zeigt die Aufstellung schon beim Schreiben. Optional lässt sich eine USt-IdNr. eintragen (erscheint in der Fußzeile). Der Export für den Steuerberater enthält neue Spalten für Netto, Steuersatz und Steuer.
- Steuersatz und Kleinunternehmer-Status werden **je Beleg gespeichert** – ein späterer Wechsel in den Einstellungen ändert bereits geschriebene Rechnungen nicht. Bestehende Belege verhalten sich wie bisher.
- **Rechnung oder Angebot kopieren**: Das neue Kopieren-Symbol bei offenen Rechnungen, im Archiv und in der Angebotsliste übernimmt Kunde, Texte, Preise und Zahlungsbedingung in einen neuen Beleg mit neuer Nummer und heutigem Datum – das Datum der Veranstaltung trägt man neu ein.
- **Hinweis auf fehlende Angaben** nennt jetzt genau, was für vollständige Rechnungen fehlt: Name, Straße, PLZ und Ort, IBAN und – ohne Kleinunternehmerregelung – Steuernummer oder USt-IdNr.

### Behoben
- Bei mittleren Fensterbreiten (z. B. in Home Assistant mit eingeblendeter Seitenleiste) und am Handy ragten die Tabellen „Offene Rechnungen“ und „Alle Angebote“ über den Kartenrand hinaus. Die Buttons brechen jetzt bei Bedarf in eine zweite Zeile um; unter 900 Pixel Breite werden die Tabellen untereinander dargestellt.

## 0.17.0 – 2026-11-17

### Neu
- **Hinweis beim ersten Start**: DJ Office Studio ist ein Hilfsmittel – für den Inhalt der Rechnungen ist jeder Nutzer selbst verantwortlich, die Nutzung erfolgt ohne Gewähr. Der Hinweis erscheint einmal pro Installation und lässt sich danach unter ⚙ Einstellungen → „Hinweise & Lizenz“ jederzeit nachlesen. In der Desktop-Version erinnert er zusätzlich daran, regelmäßig eine Sicherung anzulegen.
- **MIT-Lizenz**: DJ Office Studio steht jetzt unter der MIT-Lizenz – Nutzen, Weitergeben und Verändern sind ausdrücklich erlaubt.

## 0.16.0 – 2026-11-17

### Neu
- **Pflichtangaben auf Rechnungen**: Eine Rechnung lässt sich nur noch mit vollständiger Anschrift des Kunden (Straße, PLZ, Ort) und mit einem Lieferdatum bei jeder Position speichern – beides gehört auf eine ordnungsgemäße Rechnung. Das Formular markiert fehlende Felder schon vor dem Speichern. Die PDF-Vorschau funktioniert weiterhin auch unvollständig; für Angebote bleiben die Felder freiwillig. Bereits gespeicherte und importierte Rechnungen bleiben unverändert.

### Geändert
- **Kleinunternehmer-Hinweis** in der Fußzeile: Seit der Reform 2025 ist die Kleinunternehmerregelung eine Steuerbefreiung. Rechnungen, Angebote und Mahnungen mit Datum ab dem 18.11.2026 tragen deshalb „Steuerbefreiung nach § 19 UStG (Kleinunternehmerregelung)“. Ältere Belege behalten beim erneuten Öffnen ihren ursprünglichen Text („Gem. §19 UStG als Kleinunternehmer nicht umsatzsteuerpflichtig“), damit sich bereits ausgestellte Rechnungen nicht nachträglich ändern.

## 0.15.1 – 2026-11-17

### Behoben
- Der QR-Code auf Rechnungen und Mahnungen wurde in manchen PDF-Programmen als unlesbares Streifenmuster angezeigt. Er wird jetzt direkt als Vektorgrafik gezeichnet statt als eingebettetes Bild – das sieht in jedem Programm gleich aus und ist beim Drucken gestochen scharf. Ein automatischer Test liest den Code jetzt bei jeder Änderung mit einem echten QR-Decoder aus dem fertigen PDF.

## 0.15.0 – 2026-11-17

### Neu
- **QR-Code zum Bezahlen (GiroCode)** auf Rechnungen, Zahlungserinnerungen und Mahnungen, rechts neben der Zahlungsbedingung. Der Kunde scannt ihn mit seiner Banking-App, und Empfänger, IBAN, BIC, Betrag und Verwendungszweck („Rechnung 037“) sind schon ausgefüllt. Kein QR-Code auf Angeboten, Stornorechnungen und bei Zahlungsbedingungen wie „Bar erhalten“ oder „Bereits bezahlt“. Abschaltbar unter ⚙ Einstellungen → Bankverbindung.
- **QR-Code anzeigen**: Das neue QR-Symbol bei offenen Rechnungen zeigt den Code groß auf dem Bildschirm, zusammen mit Empfänger, IBAN, Betrag und Verwendungszweck – praktisch, wenn der Kunde direkt nach der Feier bezahlt. Mit „Als bezahlt markieren“ geht die Rechnung danach direkt ins Archiv.

## 0.14.1 – 2026-11-17

### Behoben
- Angebotsliste: Seit dem neuen Senden-Button ragte die Zeile über den Rand der Karte hinaus („Löschen“ stand außerhalb). „Bearbeiten“ und „Löschen“ sind jetzt kompakte Symbol-Buttons (✎ und ✕, mit Tooltip), Kundennamen haben wieder mehr Platz.

## 0.14.0 – 2026-11-17

### Neu
- **Erinnerung an Datensicherungen** auf der Startseite: Die Karte „Datensicherung“ zeigt, wie lange die letzte heruntergeladene Sicherung her ist („vor 24 Tagen“), mit Fortschrittsbalken bis zur nächsten Erinnerung und Button **Jetzt sichern**. Ist die eingestellte Zeit überschritten (oder wurde noch nie gesichert), wird die Karte rot. Das Intervall lässt sich unter ⚙ Einstellungen → Datensicherung & Export ändern (Standard 30 Tage, 0 = keine Erinnerung).
- Die Desktop-Version zeigt dort zusätzlich, wann die letzte automatische Tageskopie angelegt wurde.

## 0.13.0 – 2026-11-17

### Neu
- **E-Mail-Versand**: Rechnungen, Angebote, Zahlungserinnerungen und Mahnungen direkt aus der App verschicken – über das eigene Postfach (SMTP), mit jedem Anbieter oder eigenem Mailserver. Unter ⚙ Einstellungen → E-Mail-Versand gibt es Vorlagen für gängige Anbieter (WEB.DE, GMX, Gmail, Outlook.com, iCloud, T-Online, Yahoo, freenet, IONOS, STRATO, Posteo, mailbox.org) samt Hinweisen zu Freischaltung bzw. App-Passwort; Server, Port und Verschlüsselung bleiben frei änderbar. Mit „Testmail an mich senden“ lässt sich die Einrichtung prüfen.
- **Versand-Dialog** (Briefumschlag an jeder Rechnung und jedem Angebot, im Editor „Senden“): Empfänger aus den Kundendaten, Betreff und Text aus anpassbaren Vorlagen mit Platzhaltern, PDF als Anhang (bei Mahnungen Mahnung + Rechnung), optional Kopie an mich (BCC). Eine neue E-Mail-Adresse kann direkt beim Kunden gespeichert werden.
- Verschickte Belege zeigen „✉ Datum“, gesendete Mahnungen ein ✉ am Mahnungs-Chip. Rechnungen werden beim Versenden festgeschrieben.
- Herunterladen bleibt wie bisher möglich – zusätzlich direkt im Versand-Dialog („PDF herunterladen“, auf Geräten mit Teilen-Funktion auch „Teilen …“, z. B. für WhatsApp).

### Sicherheit
- Das E-Mail-Passwort wird nie an die Oberfläche zurückgegeben und ist nicht in der herunterladbaren Sicherung enthalten; beim Einspielen einer Sicherung bleibt das gespeicherte Passwort erhalten.

## 0.12.1 – 2026-11-17

### Behoben
- Die Option „Beim Start nach neuen Versionen suchen“ wurde unter ⚙ Einstellungen auch in der Home-Assistant-App angezeigt – sie gilt nur für die Desktop-Version und ist dort jetzt wieder ausgeblendet.
- Kleinere Darstellungsfehler: Hinweistexte bei „Datensicherung & Export“ brachen mitten im Satz um, „nächste Frist“ in der Summenzeile der offenen Rechnungen ebenfalls.

## 0.12.0 – 2026-11-17

### Neu
- **Festschreiben & Storno**: Rechnungen lassen sich nur noch ändern oder löschen, solange sie nicht festgeschrieben sind. Festgeschrieben wird automatisch beim Bezahlt-Markieren, bei einer Mahnung oder beim Senden an Paperless – oder per 🔒 von Hand (z. B. nach dem Versenden). Korrigiert wird dann per **Stornorechnung** mit eigener Nummer und negativen Beträgen; beide Rechnungen landen im Archiv („Storno zu 038“ / „storniert → 040“). Beim Löschen einer nicht festgeschriebenen Rechnung warnt die App, wenn dadurch eine Lücke im Nummernkreis entsteht.
- **Zahlungserinnerung und Mahnungen**: In „Offene Rechnungen“ erzeugt ein Klick die nächste Stufe – Zahlungserinnerung, 1. Mahnung, 2. Mahnung – als PDF mit Bezug auf die Rechnung, Fälligkeitsdatum und neuer Frist (einstellbar, Standard 7 Tage). Erstellte Mahnungen stehen als Link an der Rechnung; eine Kopie landet im PDF-Ordner. Auf der Startseite steht bei überfälligen Rechnungen die letzte Mahnung dabei.
- **Datensicherung**: Unter ⚙ Einstellungen alle Daten als eine Datei herunterladen und wieder einspielen (der bisherige Stand wird vorher automatisch gesichert). Die Desktop-Version sichert außerdem einmal pro Tag automatisch (die letzten 14 Tage).
- **Export für den Steuerberater**: alle Rechnungen eines Jahres als Excel-Tabelle (CSV) – mit Status, Bezahlt-Datum und Stornos – plus alle PDFs in einer ZIP-Datei.
- Beim Bezahlt-Markieren merkt sich die App jetzt das **Datum der Zahlung** (für den Export).
- **Automatische Tests** im Repository, die bei jedem Push und vor jedem Bau der Desktop-Version laufen.

### Geändert
- Bestehende bezahlte oder an Paperless gesendete Rechnungen werden beim Update automatisch festgeschrieben, ebenso importierte alte Rechnungen. Ein Klick auf eine festgeschriebene Rechnung öffnet das PDF statt den Editor.
- Das Archiv zeigt jetzt bezahlte **und** stornierte Rechnungen.

## 0.11.1 – 2026-11-16

### Behoben
- Desktop-Version (Mac): Die Update-Prüfung meldete „nicht möglich“, weil die gebündelte App die Zertifikate für die sichere Verbindung zu GitHub nicht fand. Die Zertifikate werden jetzt mitgeliefert.

## 0.11.0 – 2026-11-16

### Neu
- **Desktop-Version: Update-Hinweis** – beim Start fragt die App bei GitHub nach der neuesten Version. Ist eine neuere verfügbar, erscheint oben ein Hinweis mit Link zum Download (lässt sich je Version ausblenden). Unter **⚙ Einstellungen** steht neben der Version „aktuell“ bzw. „Update verfügbar“; dort lässt sich die Prüfung auch abschalten. Es werden keine persönlichen Daten übertragen.
- In der Home-Assistant-App ändert sich nichts – dort kommen Updates wie gewohnt über Home Assistant.

## 0.10.1 – 2026-11-16

### Geändert
- Das GitHub-Repository heißt jetzt **dj-office-studio** (vorher ha-rechnungen). Links in der App (Changelog unter ⚙ Einstellungen) und in der README zeigen auf die neue Adresse. In Home Assistant muss nichts geändert werden – die alte Adresse wird weitergeleitet.

## 0.10.0 – 2026-11-16

### Neu
- **Desktop-Version für Windows und macOS** (ohne Home Assistant): eigenständige App zum Herunterladen, gleiche Funktionen und Oberfläche. Daten und PDFs liegen im Dokumente-Ordner unter „DJ Office Studio“. Details in der README, Abschnitt „Ohne Home Assistant (Windows / Mac)“.
- PDFs nutzen am Desktop – falls vorhanden – Calibri (Schrift der Word-Vorlage), sonst Arial.

### Geändert
- In der Home-Assistant-App ändert sich nichts; Hinweise wie „unter /share oder /media“ erscheinen nur noch dort.

## 0.9.2 – 2026-11-16

### Neu
- Unter **⚙ Einstellungen** steht jetzt die installierte **Version** der App, mit Link zum Changelog („Was ist neu?“).

## 0.9.1 – 2026-11-16

### Entfernt
- Die alten Felder in der Home-Assistant-Konfiguration (*Einstellungen → Apps → DJ Office Studio → Konfiguration*) sind weg – alle Einstellungen werden nur noch in der App unter **⚙** gemacht. Die Werte wurden mit 0.9.0 bereits in die App übernommen.

## 0.9.0 – 2026-11-16

### Neu
- **Einstellungen direkt in der App**: Oben rechts gibt es jetzt **⚙ Einstellungen** – Absender (Name, Adresse, Telefon, Ort vor dem Datum), Bankverbindung, Steuernummer und Kleinunternehmer-Hinweis, Startnummern für Rechnungen und Angebote, Gültigkeit neuer Angebote, PDF-Ordner sowie Paperless werden dort eingetragen und sofort wirksam (kein Neustart der App nötig).
- Der Hinweis „Absenderdaten fehlen“ verlinkt direkt auf die Einstellungen.

### Geändert
- **Umstieg**: Beim ersten Start übernimmt die App die bisherigen Werte aus der Home-Assistant-Konfiguration automatisch einmalig. Danach gelten nur noch die Einstellungen in der App – Änderungen in der Home-Assistant-Konfiguration haben keine Wirkung mehr. Die alten Felder dort werden in einer späteren Version entfernt.

## 0.8.6 – 2026-11-16

### Geändert
- Angebotsliste: Bei angenommenen Angeboten steht der Link zur Rechnung jetzt kurz als „→ Rechnung 040“ (voller Name im Tooltip) – vorher konnte der lange Name die Tabelle über den Rand hinausschieben.
- README: neue Screenshots (Rechnungseditor, Startseite mit offenen Angeboten, Angebotsansicht) und aktualisierte Bedienungshinweise.

## 0.8.5 – 2026-11-16

### Neu
- **Offene Angebote** oben in der Angebotsansicht: alle Angebote mit Status „offen“ mit Angebotsdatum, Betrag und Restlaufzeit („noch 12 Tage“, „endet heute“, „seit 3 Tagen abgelaufen“) – bald ablaufende zuerst, abgelaufene am Ende. Summenzeile mit Anzahl, Gesamtbetrag der noch gültigen Angebote und nächstem Ablauf; direkt **→ Rechnung** möglich.
- **Startseite**: neue Karte „Offene Angebote“ mit Summe und den nächsten vier Angeboten, außerdem ein Hinweis, wenn ein Angebot in den nächsten 3 Tagen abläuft.

### Geändert
- Die bisherige Angebotsliste heißt jetzt „Alle Angebote“.

## 0.8.4 – 2026-11-16

### Neu
- **Angebote an Paperless senden**: In der Angebotsliste lassen sich Angebote jetzt markieren (einzeln oder „alle“) und mit **⇪ An Paperless senden** in den Paperless-Eingang legen – genau wie Rechnungen im Archiv (sichtbar bei eingeschaltetem `paperless_installiert`).
- Übertragene Angebote sind mit **„Paperless ✓“** markiert; ein Klick setzt die Markierung zurück.
- Markierte Angebote lassen sich außerdem **herunterladen** (mehrere als ZIP, eines direkt als PDF).

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

"""E-Mail-Versand über das eigene Postfach (SMTP) – funktioniert mit jedem Anbieter oder eigenem Server."""
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

SICHERHEIT = ("starttls", "ssl", "keine")

# Standard-Textvorlagen. Platzhalter in {geschweiften Klammern}; eine Zeile, deren Platzhalter leer bleiben,
# entfällt automatisch (z. B. „bis zum {faellig}“ bei Rechnungen ohne Zahlungsfrist).
VORLAGEN = {
    "mail_betreff_rechnung": "Rechnung {nummer} vom {datum}",
    "mail_text_rechnung": (
        "Hallo {kunde},\n\n"
        "vielen Dank für Ihren Auftrag! Im Anhang finden Sie die Rechnung {nummer} über {betrag}.\n"
        "Bitte überweisen Sie den Betrag bis zum {faellig}.\n\n"
        "Viele Grüße\n{absender}\n{telefon}"),
    "mail_betreff_angebot": "Ihr Angebot {nummer}",
    "mail_text_angebot": (
        "Hallo {kunde},\n\n"
        "vielen Dank für Ihre Anfrage! Im Anhang finden Sie mein Angebot {nummer} über {betrag}.\n"
        "Das Angebot gilt bis zum {gueltig_bis}.\n\n"
        "Bei Fragen melden Sie sich gerne jederzeit.\n\n"
        "Viele Grüße\n{absender}\n{telefon}"),
    "mail_betreff_mahnung": "{stufe} zur Rechnung {nummer}",
    "mail_text_mahnung": (
        "Hallo {kunde},\n\n"
        "sicher ist es nur untergegangen: Die Rechnung {nummer} vom {datum} über {betrag} ist noch offen. "
        "Im Anhang finden Sie die {stufe} und die Rechnung.\n"
        "Bitte überweisen Sie den Betrag bis zum {frist}.\n\n"
        "Sollte sich Ihre Zahlung mit dieser E-Mail überschnitten haben, betrachten Sie sie bitte als gegenstandslos.\n\n"
        "Viele Grüße\n{absender}\n{telefon}"),
    "mail_betreff_nachfrage": "Kurze Nachfrage zu meinem Angebot {nummer}",
    "mail_text_nachfrage": (
        "Hallo {kunde},\n\n"
        "vor ein paar Tagen habe ich Ihnen mein Angebot {nummer} über {betrag} für den {leistungsdatum} geschickt. "
        "Haben Sie schon entschieden, oder sind noch Fragen offen?\n\n"
        "Gern halte ich Ihnen den Termin bis zum {gueltig_bis} frei.\n\n"
        "Viele Grüße\n{absender}\n{telefon}"),
}

# Stornorechnung (nicht einstellbar – kommt selten vor)
STORNO_BETREFF = "Stornorechnung {nummer} zur Rechnung {storno_nummer}"
STORNO_TEXT = ("Hallo {kunde},\n\n"
               "im Anhang finden Sie die Stornorechnung {nummer} zur Rechnung {storno_nummer} vom {storno_datum}. "
               "Die Rechnung {storno_nummer} ist damit aufgehoben; ein bereits gezahlter Betrag wird erstattet.\n\n"
               "Viele Grüße\n{absender}\n{telefon}")

_PLATZHALTER = re.compile(r"\{(\w+)\}")
_ADRESSE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def fuellen(vorlage, werte):
    """Platzhalter ersetzen. Zeilen, in denen ein Platzhalter leer bleibt, werden weggelassen;
    unbekannte Platzhalter bleiben stehen, damit Tippfehler auffallen."""
    zeilen = []
    for zeile in (vorlage or "").split("\n"):
        namen = _PLATZHALTER.findall(zeile)
        if any(n in werte and not werte[n] for n in namen):
            continue
        zeilen.append(_PLATZHALTER.sub(lambda m: str(werte.get(m.group(1), m.group(0))), zeile))
    text = "\n".join(zeilen)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def adressen(text):
    """„a@x.de, b@y.de“ → Liste; ValueError bei ungültigen Adressen."""
    liste = [a.strip() for a in re.split(r"[,;\s]+", text or "") if a.strip()]
    falsch = [a for a in liste if not _ADRESSE.match(a)]
    if falsch:
        raise ValueError(f"Ungültige E-Mail-Adresse: {', '.join(falsch)}")
    if not liste:
        raise ValueError("Bitte eine Empfänger-Adresse angeben.")
    return liste


def konfiguriert(cfg):
    return bool(cfg.get("smtp_server") and cfg.get("absender_email"))


def senden(cfg, an, betreff, text, anhaenge=(), kopie_an=None, ssl_kontext=None):
    """E-Mail mit PDF-Anhängen über SMTP versenden. cfg = Einstellungen der App.
    anhaenge: [(dateiname, bytes)]. Wirft ValueError mit verständlicher Meldung."""
    if not konfiguriert(cfg):
        raise ValueError("Der E-Mail-Versand ist noch nicht eingerichtet (⚙ Einstellungen → E-Mail-Versand).")
    absender = cfg["absender_email"].strip()
    msg = EmailMessage()
    msg["From"] = formataddr((cfg.get("name") or "", absender))
    msg["To"] = ", ".join(an)
    if cfg.get("mail_antwort_an"):
        msg["Reply-To"] = cfg["mail_antwort_an"].strip()
    msg["Subject"] = betreff
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=absender.rsplit("@", 1)[-1])
    msg.set_content(text)
    for name, daten in anhaenge:
        msg.add_attachment(daten, maintype="application", subtype="pdf", filename=name)
    empfaenger = list(an) + ([kopie_an] if kopie_an and kopie_an not in an else [])

    server, port = cfg["smtp_server"].strip(), int(cfg.get("smtp_port") or 587)
    sicherheit = cfg.get("smtp_sicherheit") or "starttls"
    kontext = ssl_kontext or ssl.create_default_context()
    try:
        if sicherheit == "ssl":
            verbindung = smtplib.SMTP_SSL(server, port, context=kontext, timeout=30)
        else:
            verbindung = smtplib.SMTP(server, port, timeout=30)
        with verbindung as s:
            s.ehlo()
            if sicherheit == "starttls":
                s.starttls(context=kontext)
                s.ehlo()
            if cfg.get("smtp_passwort"):
                s.login(cfg.get("smtp_benutzer") or absender, cfg["smtp_passwort"])
            s.send_message(msg, from_addr=absender, to_addrs=empfaenger)
    except smtplib.SMTPAuthenticationError as e:
        raise ValueError("Anmeldung beim Mailserver fehlgeschlagen – Benutzername und Passwort prüfen. "
                         "Viele Anbieter verlangen dafür ein eigenes App-Passwort oder müssen den Versand über "
                         f"externe Programme (SMTP) erst im Postfach freischalten. ({_kurz(e)})") from e
    except smtplib.SMTPRecipientsRefused as e:
        raise ValueError(f"Der Mailserver hat den Empfänger abgelehnt: {', '.join(e.recipients)}") from e
    except smtplib.SMTPSenderRefused as e:
        raise ValueError(f"Der Mailserver akzeptiert die Absenderadresse {absender} nicht – sie muss zum "
                         f"Postfach gehören. ({_kurz(e)})") from e
    except smtplib.SMTPNotSupportedError as e:
        raise ValueError("Der Server unterstützt die gewählte Verschlüsselung oder Anmeldung nicht – "
                         "Port und Verschlüsselung prüfen (587 = STARTTLS, 465 = SSL/TLS).") from e
    except ssl.SSLError as e:
        raise ValueError("Verschlüsselte Verbindung fehlgeschlagen – passt die Verschlüsselung zum Port? "
                         f"(üblich: 587 = STARTTLS, 465 = SSL/TLS) ({_kurz(e)})") from e
    except socket.gaierror as e:
        raise ValueError(f"Mailserver „{server}“ wurde nicht gefunden – Adresse prüfen (oder keine Internetverbindung).") from e
    except smtplib.SMTPException as e:
        raise ValueError(f"Der Mailserver hat den Versand abgelehnt: {_kurz(e)}") from e
    except (socket.timeout, TimeoutError, ConnectionError, OSError) as e:
        raise ValueError(f"Keine Verbindung zu {server}:{port} – Server, Port und Verschlüsselung prüfen. ({_kurz(e)})") from e


def _kurz(e):
    if isinstance(e, smtplib.SMTPResponseException):
        t = e.smtp_error.decode(errors="replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        return f"{e.smtp_code} {t}"[:200]
    return str(e)[:200] or type(e).__name__

"""PDF-Erzeugung im Layout der Vorlage-Rechnung (A4, Calibri-ähnliche Schrift)."""
import os
from datetime import date

from fpdf import FPDF
from fpdf.fonts import FontFace

FONT_CANDIDATES = [
    (os.environ.get("FONT_REGULAR", ""), os.environ.get("FONT_BOLD", "")),
    ("/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
     "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf"),
    # Desktop-Version: Calibri (Schrift der Word-Vorlage), sonst Arial
    (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "calibri.ttf"),
     os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "calibrib.ttf")),
    ("/Library/Fonts/Microsoft/Calibri.ttf", "/Library/Fonts/Microsoft/Calibri Bold.ttf"),
    ("/Applications/Microsoft Word.app/Contents/Resources/DFonts/Calibri.ttf",
     "/Applications/Microsoft Word.app/Contents/Resources/DFonts/Calibrib.ttf"),
    (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
     os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf")),
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]

LEFT = 25.0
RIGHT = 24.0
COLS = (73.0, 34.0, 54.0)  # Beschreibung, Lieferdatum, Preis
BODY_PT = 11
FOOTER_TOP = 245.0


def _find_fonts():
    for reg, bold in FONT_CANDIDATES:
        if reg and bold and os.path.exists(reg) and os.path.exists(bold):
            return reg, bold
    raise RuntimeError("Keine passende TTF-Schrift gefunden (FONT_REGULAR/FONT_BOLD setzen).")


def fmt_date(iso):
    """'2026-10-31' -> '31.10.26'"""
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%y")
    except ValueError:
        return iso


def fmt_euro(value):
    """960 -> '960,- Euro', 1234.5 -> '1.234,50 Euro'"""
    value = round(float(value or 0), 2)
    if value == int(value):
        s = f"{int(value):,}".replace(",", ".") + ",-"
    else:
        s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} Euro"


class InvoicePDF(FPDF):
    def __init__(self, absender):
        super().__init__(format="A4", unit="mm")
        self.absender = absender
        reg, bold = _find_fonts()
        self.add_font("Body", "", reg)
        self.add_font("Body", "B", bold)
        self.set_margins(LEFT, 20, RIGHT)
        self.set_auto_page_break(True, margin=297 - FOOTER_TOP + 8)

    def footer(self):
        a = self.absender
        self.set_draw_color(0)
        self.set_line_width(0.2)
        self.line(LEFT, FOOTER_TOP, 210 - RIGHT - 4, FOOTER_TOP)
        self.set_font("Body", "", 10)
        lh = 5
        cols = [
            (LEFT, [a.get("name"), a.get("strasse"), a.get("plz_ort"), a.get("telefon")]),
            (LEFT + 38, ["Bankverbindung:", a.get("kontoinhaber") or a.get("name"),
                         f"IBAN: {a.get('iban', '')}", f"BIC : {a.get('bic', '')}", a.get("bank_name")]),
            (LEFT + 103, ["Steuernummer:", a.get("steuernummer"), "",
                          *(["Gem. §19 UStG als Kleinunternehmer", "nicht umsatzsteuerpflichtig"]
                            if a.get("kleinunternehmer") else [])]),
        ]
        for x, lines in cols:
            for i, text in enumerate(lines):
                self.set_xy(x, FOOTER_TOP + 1 + i * lh)
                self.cell(0, lh, text or "")


def fmt_date_lang(iso):
    """'2026-10-31' -> '31.10.2026'"""
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return iso or ""


def _briefkopf(pdf, absender, kunde, titel, datum_iso):
    """Absenderzeile, Empfänger, Titel (z. B. „Rechnung Nr.: 037“) und „Ort, den Datum“."""
    epw = pdf.epw
    pdf.set_font("Body", "", 7)
    pdf.set_xy(LEFT, 42)
    sender_line = " | ".join(x for x in (absender.get("name"), absender.get("strasse"),
                                         absender.get("plz_ort")) if x)
    pdf.cell(0, 4, sender_line)

    k = kunde
    pdf.set_font("Body", "", BODY_PT)
    pdf.set_xy(LEFT, 49)
    plz_ort = " ".join(x for x in (k.get("plz"), k.get("ort")) if x)
    for line in (k.get("name"), k.get("zusatz"), k.get("strasse"), plz_ort):
        if line:
            pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")

    pdf.set_xy(LEFT, 93)
    pdf.set_font("Body", "BU", 13)
    pdf.cell(epw * 0.6, 7, titel)
    pdf.set_font("Body", "", BODY_PT)
    ort = absender.get("ort_fuer_datum") or ""
    datum = fmt_date(datum_iso)
    right_edge = LEFT + sum(COLS) - 8  # rechtsbündig, etwas vor dem Tabellenrand
    pdf.set_x(LEFT + epw * 0.6)
    pdf.cell(right_edge - pdf.get_x(), 7, f"{ort}, den {datum}" if ort else datum, align="R")


def _gruss(pdf, absender, abstand=22):
    """„Mit freundlichen Grüßen“ + Name immer zusammen: passt der Block (inkl. Abstand)
    nicht mehr auf die Seite, kommt er komplett auf die nächste."""
    gruss_block = 5 + 4 + 5
    if pdf.will_page_break(abstand + gruss_block):
        pdf.add_page()
    else:
        pdf.ln(abstand)
    pdf.cell(0, 5, "Mit freundlichen Grüßen", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 5, absender.get("name") or "", new_x="LMARGIN", new_y="NEXT")


def build_invoice_pdf(inv, absender):
    """inv: dict mit nummer, datum, kunde{...}, positionen[{beschreibung, lieferdatum, preis}],
    zahlungsbedingung. Mit art="angebot" (+ gueltig_bis, hinweise) entsteht ein Angebot,
    mit storno_zu={nummer, datum} eine Stornorechnung. Gibt PDF als bytes zurück."""
    angebot = inv.get("art") == "angebot"
    storno = inv.get("storno_zu")
    pdf = InvoicePDF(absender)
    pdf.add_page()

    titel = "Angebot" if angebot else "Stornorechnung" if storno else "Rechnung"
    _briefkopf(pdf, absender, inv["kunde"], f"{titel} Nr.: {inv['nummer']}", inv["datum"])

    # Einleitung
    pdf.set_xy(LEFT, 110)
    if angebot:
        einleitung = "Vielen Dank für Ihre Anfrage. Gerne biete ich Ihnen folgende Leistungen an:"
    elif storno:
        einleitung = (f"Hiermit storniere ich die Rechnung Nr. {storno['nummer']} vom "
                      f"{fmt_date_lang(storno['datum'])} vollständig:")
    else:
        einleitung = "Gemäß Ihrem Auftrag stelle ich wie folgt in Rechnung:"
    pdf.cell(0, 5, einleitung)
    pdf.set_xy(LEFT, 118)

    # Positionstabelle
    bold = FontFace(emphasis="BOLD")
    gesamt = 0.0
    with pdf.table(col_widths=COLS, width=sum(COLS), align="LEFT", text_align="LEFT",
                   line_height=5, padding=(1, 2, 1, 2), first_row_as_headings=True,
                   headings_style=bold, borders_layout="ALL", v_align="TOP") as table:
        head = table.row()
        for h in ("Beschreibung", "Datum" if angebot else "Lieferdatum", "Preis"):
            head.cell(h)
        for p in inv["positionen"]:
            preis = float(p.get("preis") or 0)
            gesamt += preis
            row = table.row()
            row.cell(p.get("beschreibung") or "")
            row.cell(fmt_date(p.get("lieferdatum")))
            row.cell(fmt_euro(preis))
        total = table.row()
        total.cell("Gesamt", style=bold)
        total.cell("")
        total.cell(fmt_euro(gesamt))

    if angebot:
        # Gültigkeit, Hinweise (z. B. Verlängerung, Anfahrt, GEMA), optional Zahlungsbedingung
        pdf.ln(6)
        if inv.get("gueltig_bis"):
            pdf.set_font("Body", "B", BODY_PT)
            pdf.multi_cell(0, 5, f"Dieses Angebot ist gültig bis zum {fmt_date_lang(inv['gueltig_bis'])}.",
                           align="L", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
        pdf.set_font("Body", "", BODY_PT)
        for text in (inv.get("hinweise"), inv.get("zahlungsbedingung")):
            if text:
                pdf.multi_cell(0, 5, text, align="L", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(3)
        pdf.ln(7)
        pdf.set_font("Body", "B", BODY_PT)   # Schluss + Gruß fett wie bei der Rechnung
        pdf.multi_cell(0, 5, "Ich freue mich auf Ihre Rückmeldung und stehe für Rückfragen gerne zur Verfügung.",
                       align="L", new_x="LMARGIN", new_y="NEXT")
    elif storno:
        pdf.set_font("Body", "B", BODY_PT)
        pdf.ln(6)
        pdf.multi_cell(0, 5, f"Die Rechnung Nr. {storno['nummer']} ist damit aufgehoben. Ein bereits gezahlter "
                             "Betrag wird erstattet.", align="L", new_x="LMARGIN", new_y="NEXT")
    else:
        # Zahlungsbedingung
        pdf.set_font("Body", "B", BODY_PT)
        pdf.ln(6)
        pdf.multi_cell(0, 5, inv.get("zahlungsbedingung") or "", align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)
        pdf.cell(0, 5, "Vielen Dank für Ihren Auftrag!", new_x="LMARGIN", new_y="NEXT")
    _gruss(pdf, absender)
    return bytes(pdf.output())


MAHNSTUFEN = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung"}


def build_mahnung_pdf(inv, mahnung, absender, faellig_iso=None):
    """Zahlungserinnerung (Stufe 1) bzw. 1./2. Mahnung (Stufe 2/3) zu einer Rechnung."""
    stufe = mahnung["stufe"]
    pdf = InvoicePDF(absender)
    pdf.add_page()
    _briefkopf(pdf, absender, inv["kunde"], MAHNSTUFEN[stufe], mahnung["datum"])

    pdf.set_xy(LEFT, 110)
    pdf.set_font("Body", "", BODY_PT)
    einleitung = {
        1: "sicher ist es Ihrer Aufmerksamkeit entgangen: Für die folgende Rechnung konnte ich bisher "
           "keinen Zahlungseingang feststellen.",
        2: "leider konnte ich für die folgende Rechnung trotz Zahlungserinnerung noch keinen "
           "Zahlungseingang feststellen.",
        3: "trotz Zahlungserinnerung und Mahnung ist die folgende Rechnung weiterhin nicht beglichen.",
    }[stufe]
    pdf.multi_cell(0, 5, "Guten Tag,\n\n" + einleitung, align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    bold = FontFace(emphasis="BOLD")
    with pdf.table(col_widths=COLS, width=sum(COLS), align="LEFT", text_align="LEFT",
                   line_height=5, padding=(1, 2, 1, 2), first_row_as_headings=True,
                   headings_style=bold, borders_layout="ALL", v_align="TOP") as table:
        head = table.row()
        for h in ("Rechnung", "Datum", "Offener Betrag"):
            head.cell(h)
        row = table.row()
        row.cell(f"Rechnung Nr. {inv['nummer']}" + (f"\nfällig seit {fmt_date(faellig_iso)}" if faellig_iso else ""))
        row.cell(fmt_date(inv["datum"]))
        row.cell(fmt_euro(inv["gesamt"]))

    pdf.ln(6)
    pdf.set_font("Body", "B", BODY_PT)
    pdf.multi_cell(0, 5, f"Bitte überweisen Sie den offenen Betrag von {fmt_euro(inv['gesamt'])} bis spätestens "
                         f"{fmt_date_lang(mahnung['frist'])} auf das unten genannte Konto.",
                   align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Body", "", BODY_PT)
    schluss = ("Sollten Sie die Zahlung bereits veranlasst haben, betrachten Sie dieses Schreiben bitte als "
               "gegenstandslos.")
    if stufe == 3:
        schluss = ("Dies ist die letzte Mahnung. Geht der Betrag nicht fristgerecht ein, behalte ich mir weitere "
                   "Schritte vor. " + schluss)
    pdf.multi_cell(0, 5, schluss, align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Body", "B", BODY_PT)
    _gruss(pdf, absender, abstand=16)
    return bytes(pdf.output())


def mahnung_filename(inv, mahnung):
    """Zahlungserinnerung_037_171126.pdf / 1-Mahnung_037_… / 2-Mahnung_037_…"""
    art = MAHNSTUFEN[mahnung["stufe"]].replace(". ", "-")
    try:
        suffix = "_" + date.fromisoformat(mahnung["datum"]).strftime("%d%m%y")
    except (TypeError, ValueError):
        suffix = ""
    return f"{art}_{inv['nummer']}{suffix}.pdf"


def pdf_filename(inv):
    """Rechnung_036_311026.pdf / Angebot_012_311026.pdf (Datum der ersten Position, sonst Belegdatum)."""
    first = next((p.get("lieferdatum") for p in inv["positionen"] if p.get("lieferdatum")), None)
    d = first or inv["datum"]
    try:
        suffix = date.fromisoformat(d).strftime("%d%m%y")
    except (TypeError, ValueError):
        suffix = ""
    art = "Angebot" if inv.get("art") == "angebot" else "Stornorechnung" if inv.get("storno_von") else "Rechnung"
    return f"{art}_{inv['nummer']}" + (f"_{suffix}" if suffix else "") + ".pdf"

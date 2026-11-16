"""PDF-Erzeugung im Layout der Vorlage-Rechnung (A4, Calibri-ähnliche Schrift)."""
import os
from datetime import date

from fpdf import FPDF
from fpdf.fonts import FontFace

FONT_CANDIDATES = [
    (os.environ.get("FONT_REGULAR", ""), os.environ.get("FONT_BOLD", "")),
    ("/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
     "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf"),
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


def build_invoice_pdf(inv, absender):
    """inv: dict mit nummer, datum, kunde{...}, positionen[{beschreibung, lieferdatum, preis}],
    zahlungsbedingung. Gibt PDF als bytes zurück."""
    pdf = InvoicePDF(absender)
    pdf.add_page()
    epw = pdf.epw

    # Absenderzeile über dem Adressfeld
    pdf.set_font("Body", "", 7)
    pdf.set_xy(LEFT, 42)
    sender_line = " | ".join(x for x in (absender.get("name"), absender.get("strasse"),
                                         absender.get("plz_ort")) if x)
    pdf.cell(0, 4, sender_line)

    # Empfänger
    k = inv["kunde"]
    pdf.set_font("Body", "", BODY_PT)
    pdf.set_xy(LEFT, 49)
    plz_ort = " ".join(x for x in (k.get("plz"), k.get("ort")) if x)
    for line in (k.get("name"), k.get("zusatz"), k.get("strasse"), plz_ort):
        if line:
            pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")

    # Rechnungsnummer + Ort/Datum
    pdf.set_xy(LEFT, 93)
    pdf.set_font("Body", "BU", 13)
    pdf.cell(epw / 2, 7, f"Rechnung Nr.: {inv['nummer']}")
    pdf.set_font("Body", "", BODY_PT)
    ort = absender.get("ort_fuer_datum") or ""
    datum = fmt_date(inv["datum"])
    right_edge = LEFT + sum(COLS) - 8  # wie in der Vorlage: rechtsbündig, etwas vor dem Tabellenrand
    pdf.set_x(LEFT + epw / 2)
    pdf.cell(right_edge - pdf.get_x(), 7, f"{ort}, den {datum}" if ort else datum, align="R")

    # Einleitung
    pdf.set_xy(LEFT, 110)
    pdf.cell(0, 5, "Gemäß Ihrem Auftrag stelle ich wie folgt in Rechnung:")
    pdf.set_xy(LEFT, 118)

    # Positionstabelle
    bold = FontFace(emphasis="BOLD")
    gesamt = 0.0
    with pdf.table(col_widths=COLS, width=sum(COLS), align="LEFT", text_align="LEFT",
                   line_height=5, padding=(1, 2, 1, 2), first_row_as_headings=True,
                   headings_style=bold, borders_layout="ALL", v_align="TOP") as table:
        head = table.row()
        for h in ("Beschreibung", "Lieferdatum", "Preis"):
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

    # Zahlungsbedingung + Gruß
    pdf.set_font("Body", "B", BODY_PT)
    pdf.ln(6)
    pdf.multi_cell(0, 5, inv.get("zahlungsbedingung") or "", align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.cell(0, 5, "Vielen Dank für Ihren Auftrag!", new_x="LMARGIN", new_y="NEXT")
    # „Mit freundlichen Grüßen“ + Name immer zusammen: passt der Block (inkl. Abstand)
    # nicht mehr auf die Seite, kommt er komplett auf die nächste.
    gruss_block = 5 + 4 + 5
    if pdf.will_page_break(22 + gruss_block):
        pdf.add_page()
    else:
        pdf.ln(22)
    pdf.cell(0, 5, "Mit freundlichen Grüßen", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 5, absender.get("name") or "", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def pdf_filename(inv):
    """Rechnung_036_311026.pdf (Lieferdatum der ersten Position, sonst Rechnungsdatum)."""
    first = next((p.get("lieferdatum") for p in inv["positionen"] if p.get("lieferdatum")), None)
    d = first or inv["datum"]
    try:
        suffix = date.fromisoformat(d).strftime("%d%m%y")
    except (TypeError, ValueError):
        suffix = ""
    return f"Rechnung_{inv['nummer']}" + (f"_{suffix}" if suffix else "") + ".pdf"

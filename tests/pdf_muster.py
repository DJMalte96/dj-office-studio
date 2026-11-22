"""Handgeschriebene PDFs für die Tests der Grenzen – nur Standardbibliothek (läuft auch im Rauchtest)."""
import functools
import zlib

FLATE = b"/Filter /FlateDecode"


def gepackt(stueck, mal):
    """Komprimieren, ohne alles im Speicher zu halten."""
    c, aus = zlib.compressobj(6), []
    block, rest = stueck * max(1, 1_000_000 // len(stueck)), len(stueck) * mal
    while rest > 0:
        t = block[:rest]
        aus.append(c.compress(t))
        rest -= len(t)
    return b"".join(aus) + c.flush()


def strom(daten, extra=b""):
    return b"<< /Length %d %s >>\nstream\n" % (len(daten), extra) + daten + b"\nendstream"


def dokument(objekte):
    aus, stellen = b"%PDF-1.5\n", []
    for i, o in enumerate(objekte, 1):
        stellen.append(len(aus))
        aus += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(aus)
    aus += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1) + b"".join(b"%010d 00000 n \n" % s for s in stellen)
    return aus + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objekte) + 1, x)


def seite(inhalt, schrift=b"", weitere=(), katalog=b""):
    return dokument([b"<< /Type /Catalog /Pages 2 0 R %s >>" % katalog,
                     b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                     b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
                     inhalt, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica %s >>" % schrift, *weitere])


def mit_text(text):
    return seite(strom(zlib.compress(b"BT /F1 10 Tf 20 800 Td (" + text + b") Tj ET"), FLATE))


@functools.lru_cache
def flate_bombe():
    return seite(strom(gepackt(b" ", 120_000_000), FLATE))


@functools.lru_cache
def doppelt_gepackt():
    return seite(strom(zlib.compress(gepackt(b" ", 120_000_000)), b"/Filter [/FlateDecode /FlateDecode]"))


def seitenbaum():
    """Zehn Millionen Seiten in einem KB."""
    knoten = [b"<< /Type /Pages /Count 10 /Kids [%s] >>" % b" ".join([b"%d 0 R" % (3 + i)] * 10) for i in range(7)]
    return dokument([b"<< /Type /Catalog /Pages 2 0 R >>", *knoten, b"<< /Type /Page /MediaBox [0 0 99 99] >>"])


def xref_schleife():
    d = mit_text(b"x")
    return d.replace(b"/Root 1 0 R >>", b"/Root 1 0 R /Prev %d >>" % d.index(b"xref\n"))


def bombe_mit_erechnung(xml):
    return seite(strom(gepackt(b" ", 120_000_000), FLATE), katalog=b"/AF [6 0 R]",
                 weitere=[b"<< /Type /Filespec /F (factur-x.xml) /EF << /F 7 0 R >> >>", strom(xml)])

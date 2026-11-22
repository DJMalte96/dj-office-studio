"""Erfundene Outlook-Mails (.msg) bauen."""
import io
import struct


def msg(text="Gesamt 23,80 EUR", betreff="Kauf Kabel", von="Musterladen <laden@example.org>", anhaenge=(), rtf=None):
    from extract_msg.ole_writer import OleWriter
    w = OleWriter()

    def wort(pfad, t):
        w.addEntry(pfad, t.encode("utf-16-le"))

    w.addEntry("__properties_version1.0",
               b"\0" * 8 + struct.pack("<IIII", len(anhaenge), 0, 0, len(anhaenge)) + b"\0" * 8
               + struct.pack("<IIQ", 0x00390040, 6, 134176000000000000)      # gesendet am 10.03.2026
               + struct.pack("<IIII", 0x340D0003, 6, 0x40000, 0) + struct.pack("<IIII", 0x0E070003, 6, 1, 0))
    wort("__substg1.0_001A001F", "IPM.Note")
    wort("__substg1.0_0037001F", betreff)
    wort("__substg1.0_0C1A001F", von)
    wort("__substg1.0_1000001F", text)
    wort("__substg1.0_1035001F", "<probe@example.org>")
    w.addEntry("__nameid_version1.0", storage=True)
    for x in ("00020102", "00030102", "00040102"):
        w.addEntry("__nameid_version1.0/__substg1.0_" + x, b"")
    if rtf is not None:
        w.addEntry("__substg1.0_10090102", struct.pack("<IIII", len(rtf) + 12, len(rtf), 0x414C454D, 0) + rtf)
    for i, (name, daten) in enumerate(anhaenge):
        o = f"__attach_version1.0_#{i:08X}"
        w.addEntry(o, storage=True)
        w.addEntry(o + "/__properties_version1.0", b"\0" * 8 + struct.pack("<IIII", 0x37050003, 6, 1, 0))
        wort(o + "/__substg1.0_3707001F", name)
        w.addEntry(o + "/__substg1.0_37010102", daten)
    aus = io.BytesIO()
    w.write(aus)
    return aus.getvalue()

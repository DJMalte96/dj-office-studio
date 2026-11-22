"""Grenzen für das Lesen fremder Dateien – ohne Importe aus der App, auch die Kindprozesse benutzen es.

- prozess_begrenzen(): im Kindprozess – Arbeitsspeicher, Zeit, kein Netz. Nie im Prozess der App aufrufen.
- text_begrenzen(): vor allen Mustern der Auswertung. Die brauchen bei langen Ziffernfolgen und Riesenzeilen
  quadratisch lange und halten dabei die ganze App an (ein Muster gibt den GIL nicht her).
"""
import os
import re
import sys
import threading
import time

ZU_VIEL_SPEICHER, ZU_LANGE = 86, 87     # Exit-Codes der Kindprozesse
GRUENDE = {ZU_VIEL_SPEICHER: "braucht zu viel Arbeitsspeicher", ZU_LANGE: "dauert zu lange"}
MB = 1024 * 1024

# ---------- Text ----------

MAX_TEXT = 300_000
MAX_ZEILE = 1000
MAX_ZEILEN = 5000
_ZIFFERN = re.compile(r"\d{30,}")                   # länger als jede IBAN, Beleg- oder Kundennummer
_GRUPPEN = re.compile(r"(?:\d{1,29}[.,]){20,}\d*")  # „111.111.111. …“; Punktreihen vor Beträgen bleiben


def text_begrenzen(text):
    """Gewöhnliche Belege bleiben unverändert. Gekürzt wird in der Mitte: Die Summe steht oft am Ende."""
    text = text or ""
    if len(text) > MAX_TEXT:
        text = f"{text[:MAX_TEXT * 4 // 5]}\n{text[-MAX_TEXT // 5:]}"
    text = _GRUPPEN.sub(" ", _ZIFFERN.sub(" ", text))
    zeilen = text.split("\n")
    if len(zeilen) <= MAX_ZEILEN and all(len(z) <= MAX_ZEILE for z in zeilen):
        return text
    kurz = []
    for z in zeilen:
        anfang = 0
        while len(z) - anfang > MAX_ZEILE:
            ende = z.rfind(" ", anfang + MAX_ZEILE // 2, anfang + MAX_ZEILE)     # möglichst nicht mitten im Betrag
            ende = ende if ende > 0 else anfang + MAX_ZEILE
            kurz.append(z[anfang:ende])
            anfang = ende
        kurz.append(z[anfang:])
    if len(kurz) > MAX_ZEILEN:
        kurz = kurz[:MAX_ZEILEN * 4 // 5] + kurz[-MAX_ZEILEN // 5:]
    return "\n".join(kurz)


# ---------- Kindprozess ----------

_grenze = {"mb": None, "bis": None}
_waechter = []
_job = []


def prozess_begrenzen(mb, sekunden):
    """Für diesen Prozess, noch einmal aufrufbar mit anderen Werten. mb=None: Speicher frei."""
    _grenze.update(mb=mb, bis=time.monotonic() + sekunden)
    if sys.platform.startswith("linux"):
        _linux(mb)
    elif sys.platform == "win32":
        _windows(mb)
    if not _waechter:
        # Zeit überall; Speicher zusätzlich für macOS, wo der Kernel keine Grenze durchsetzt
        threading.stack_size(512 * 1024)
        t = threading.Thread(target=_wachen, daemon=True, name="grenzen")
        _waechter.append(t)
        t.start()
        threading.stack_size(0)


def ohne_netz():
    import socket

    def gesperrt(*_a, **_k):
        raise OSError("Belege werden ohne Netzwerk gelesen")
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = socket.getaddrinfo = gesperrt


def _wachen():
    mac = sys.platform == "darwin"
    if mac:
        import resource
    while True:
        mb, bis = _grenze["mb"], _grenze["bis"]
        if bis and time.monotonic() > bis:
            os._exit(ZU_LANGE)
        if mac and mb and resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > mb * MB:
            os._exit(ZU_VIEL_SPEICHER)
        time.sleep(0.02)


def _linux(mb):
    import resource
    try:
        with open("/proc/self/oom_score_adj", "w") as f:    # wird der Speicher knapp, trifft es den Kindprozess, nicht die App
            f.write("1000")
    except OSError:
        pass
    # DATA statt AS: zählt belegten, nicht nur reservierten Adressraum (native Bibliotheken reservieren viel)
    _, hart = resource.getrlimit(resource.RLIMIT_DATA)
    weich = hart if not mb else mb * MB
    if hart != resource.RLIM_INFINITY:
        weich = min(weich, hart) if weich != resource.RLIM_INFINITY else hart
    resource.setrlimit(resource.RLIMIT_DATA, (weich, hart))


def _windows(mb):
    import ctypes
    from ctypes import wintypes as w

    class Basis(ctypes.Structure):
        _fields_ = [("ProzessZeit", ctypes.c_int64), ("JobZeit", ctypes.c_int64), ("LimitFlags", w.DWORD),
                    ("MinWS", ctypes.c_size_t), ("MaxWS", ctypes.c_size_t), ("Prozesse", w.DWORD),
                    ("Affinitaet", ctypes.c_size_t), ("Prioritaet", w.DWORD), ("Planung", w.DWORD)]

    class Erweitert(ctypes.Structure):
        _fields_ = [("Basis", Basis), ("Io", ctypes.c_uint64 * 6), ("ProzessSpeicher", ctypes.c_size_t),
                    ("JobSpeicher", ctypes.c_size_t), ("SpitzeProzess", ctypes.c_size_t), ("SpitzeJob", ctypes.c_size_t)]

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = k.GetCurrentProcess.restype = w.HANDLE
    k.CreateJobObjectW.argtypes = [w.LPVOID, w.LPCWSTR]
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
    if not _job:
        job = k.CreateJobObjectW(None, None)
        if not job or not k.AssignProcessToJobObject(job, k.GetCurrentProcess()):
            return                      # dann bleibt die Zeitgrenze
        _job.append(job)
    info = Erweitert()
    if mb:
        info.Basis.LimitFlags = 0x100   # JOB_OBJECT_LIMIT_PROCESS_MEMORY
        info.ProzessSpeicher = mb * MB
    k.SetInformationJobObject(_job[0], 9, ctypes.byref(info), ctypes.sizeof(info))

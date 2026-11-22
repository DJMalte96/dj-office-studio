"""Prüft die fertige macOS-App: Kein nativer Programmteil darf ein neueres macOS verlangen als zugesagt.

    python desktop/mindest_macos.py "dist/DJ Office Studio.app" 13
"""
import re
import subprocess
import sys
from pathlib import Path


def zu_neu(app, grenze):
    for pfad in sorted(Path(app).rglob("*")):
        if pfad.is_symlink() or not pfad.is_file() or not (pfad.suffix in (".so", ".dylib") or pfad.parent.name == "MacOS"):
            continue
        info = subprocess.run(["otool", "-l", str(pfad)], capture_output=True, text=True).stdout
        # je nach Alter steht die Angabe als „minos“ oder als LC_VERSION_MIN_MACOSX → „version“
        for m in re.finditer(r"\bminos (\d+)\.|LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version (\d+)\.", info):
            if int(m.group(1) or m.group(2)) > grenze:
                yield f"{pfad.name}: macOS {m.group(1) or m.group(2)}"
                break


if __name__ == "__main__":
    treffer = list(zu_neu(sys.argv[1], int(sys.argv[2])))
    for t in treffer:
        print(f"::error::{t}")
    print(f"macOS {sys.argv[2]}: " + (f"{len(treffer)} Teile verlangen mehr" if treffer else "alle Programmteile passen"))
    sys.exit(1 if treffer else 0)

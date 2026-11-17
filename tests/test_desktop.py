"""Desktop-Version: automatische tägliche Sicherung."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))


def test_automatische_sicherung(app_modul, tmp_path, monkeypatch):
    import db
    import start
    monkeypatch.setattr(start, "DATEN", tmp_path / "Daten")
    (tmp_path / "Daten").mkdir()
    ordner = tmp_path / "Daten" / "Sicherungen"
    ordner.mkdir()
    for tag in range(1, 17):   # 16 alte Sicherungen
        (ordner / f"rechnungen_2020-01-{tag:02d}.db").write_bytes(b"alt")

    start.automatische_sicherung(db)
    start.automatische_sicherung(db)   # zweiter Start am selben Tag: keine weitere Kopie

    dateien = sorted(p.name for p in ordner.iterdir())
    assert len(dateien) == 14
    assert dateien[-1] == f"rechnungen_{date.today().isoformat()}.db"
    assert db.pruefe_sicherung(str(ordner / dateien[-1]))["rechnungen"] == 0

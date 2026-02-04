from pathlib import Path

DEFAULT_BACKUP_ROOT = Path("C:/nutrinexus_backup")

def resolve_backup_root() -> Path:
    # C: yazılamazsa kullanıcı dizinine düş
    try:
        DEFAULT_BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        test = DEFAULT_BACKUP_ROOT / ".write_test"
        test.write_text("ok", encoding="utf-8")
        test.unlink(missing_ok=True)
        return DEFAULT_BACKUP_ROOT
    except Exception:
        home = Path.home() / "nutrinexus_backup"
        home.mkdir(parents=True, exist_ok=True)
        return home

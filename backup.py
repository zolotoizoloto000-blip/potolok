from pathlib import Path
import shutil, datetime, os
src=Path(__file__).with_name("catalog.db")
dst=Path(__file__).with_name("backups");dst.mkdir(exist_ok=True)
if src.exists():
    name=dst/f"catalog-{datetime.datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(src,name);print(name)
else: print("SQLite file not present; use managed PostgreSQL provider backups.")

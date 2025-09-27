
# FYP/LI Management — COMPLETE PACKAGE

This package includes:
- `main.py` (entrypoint) — Streamlit multipage launcher
- `pages/` — role pages (Pelajar, Penyelia Akademik, Penyelia Industri, Penyelaras)
- `lib/common.py` — DB/auth utilities + DOCX auto-generate helpers
- `templates/` — surat templates (SLI01_Surat_Permohonan.docx, SLI03_Surat_Penempatan.docx)
- `init_mytimes_fyp.sql` — complete DB schema + seed
- `users_demo.xlsx` — demo accounts with temp_password
- `requirements.txt` — dependencies

## Run
```bash
pip install -r requirements.txt
# Initialize DB (once)
python - <<'PY'
import sqlite3, pathlib
db="mytimes.db"
with open("init_mytimes_fyp.sql","r",encoding="utf-8") as f: sql=f.read()
conn=sqlite3.connect(db); conn.executescript(sql); conn.commit(); conn.close()
print("DB:", pathlib.Path(db).absolute())
PY

# Launch
streamlit run main.py
```

## Notes
- Login Pelajar: boleh guna **emel** atau **No. Pelajar** (contoh `2025001`).
- **Auto-generate surat** menggunakan placeholder dalam template `.docx`:
  - SLI01: `{NAMA}`, `{NOPELAJAR}`, `{PROGRAM}`, `{TARIKH}`
  - SLI-03: tambah `{ORG}`
- Markah tidak dipaparkan kepada pelajar; hanya status serahan.
- Penyelia Akademik & Industri boleh **semak logbook & beri komen**.
- Penyelaras ada dashboard overview (boleh tambah agihan/eksport).

## Config
- DB path boleh diubah melalui env: `DB_PATH=/path/to/mytimes.db`

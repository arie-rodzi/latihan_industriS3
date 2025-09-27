
# FYP Praktikal UiTM N9 — Demo

**Apa ada dalam pakej ini**
- `users_demo.xlsx` : Senarai akaun demo (10 pelajar, 3 penyelaras, 3 penyelia akademik, 3 penyelia industri) beserta kata laluan.
- `init_mytimes_fyp.sql` : Skrip SQLite (jadual lengkap + seed peranan, pengguna, dan 1 term contoh).
- `rubrics/bli05.json` dan `rubrics/bli08.json` : Skema rubrik penilaian.
- `app.py` : Aplikasi Streamlit demo dengan login & menu mengikut peranan.
- `.env.example` : Contoh seting rahsia untuk laluan DB.
- `requirements.txt` : Kebergantungan Python.

## Mula Cepat (Local)
1. Pasang kebergantungan:
   ```bash
   pip install -r requirements.txt
   ```
2. Inisialisasi DB SQLite:
   ```bash
   python - <<'PY'
import sqlite3, pathlib
db="mytimes.db"
sql_path="init_mytimes_fyp.sql"
with open(sql_path,"r",encoding="utf-8") as f: sql=f.read()
conn=sqlite3.connect(db); conn.executescript(sql); conn.commit(); conn.close()
print("DB created:", pathlib.Path(db).absolute())
PY
   ```
3. Jalankan Streamlit:
   ```bash
   streamlit run app.py
   ```
4. Log masuk menggunakan emel & kata laluan dalam `users_demo.xlsx` (kolum `temp_password`).

> Nota: Kata laluan disimpan sebagai SHA256 dalam DB; fail Excel memaparkan `temp_password` untuk log masuk demo.

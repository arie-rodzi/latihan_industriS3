# pages/4_Penyelaras_Dashboard.py
import os
import io
import csv
import pandas as pd
import streamlit as st
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

# ==== GUARD (wajib): hanya penyelaras boleh buka page ini ====
try:
    from lib.common import require_role
except Exception:
    def require_role(roles):
        aut = st.session_state.get("auth")
        if not aut or aut.get("role_name") not in roles:
            st.error("Akses tidak dibenarkan. Sila log masuk sebagai Penyelaras.")
            st.stop()

st.set_page_config(page_title="Penyelaras", page_icon="⚙️", layout="wide")
st.title("Dashboard Penyelaras")

# Pastikan DB sedia
try:
    ensure_db(os.path.join(os.path.dirname(__file__), "..", "init_mytimes_fyp.sql"))
except Exception as e:
    st.error(f"Ralat DB: {e}"); st.stop()

# ---------------------- LOGIN ----------------------
if "auth" not in st.session_state: st.session_state.auth = None
if not st.session_state.auth:
    st.subheader("Log Masuk Penyelaras")
    with st.form("login_coord"):
        email = st.text_input("Emel")
        password = st.text_input("Kata Laluan", type="password")
        submitted = st.form_submit_button("Log Masuk")
    if submitted:
        user = auth_email_or_sid(email, password)
        if not user or user["role_name"]!="coordinator":
            st.error("Akaun bukan Penyelaras / salah maklumat.")
        else:
            st.session_state.auth = user; st.rerun()
    st.stop()

# Guard selepas login
require_role(["coordinator"])
user = st.session_state.auth
st.success(f"Log masuk sebagai {user['full_name']}")

# ---------------------- METRICS ----------------------
with get_conn() as conn:
    tlabel = term_label(conn)
    total_students = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=1") or 0
    total_acad = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=3") or 0
    total_ind = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=4") or 0
    bli01 = one(conn, "SELECT COUNT(1) FROM bli01") or 0
    bli02 = one(conn, "SELECT COUNT(1) FROM bli02_responses") or 0
    placements_cnt = one(conn, "SELECT COUNT(1) FROM placements") or 0
    bli05 = one(conn, "SELECT COUNT(1) FROM bli05_industry") or 0
    bli08 = one(conn, "SELECT COUNT(1) FROM bli08_academic") or 0
    reports = one(conn, "SELECT COUNT(1) FROM final_reports") or 0

st.info(f"**Sesi semasa:** {tlabel}")
c1,c2,c3 = st.columns(3)
c1.metric("Pelajar", f"{total_students}")
c2.metric("Penyelia Akademik", f"{total_acad}")
c3.metric("Penyelia Industri", f"{total_ind}")
c4,c5,c6 = st.columns(3)
c4.metric("BLI-01", f"{bli01}")
c5.metric("BLI-02", f"{bli02}")
c6.metric("Penempatan", f"{placements_cnt}")
c7,c8,c9 = st.columns(3)
c7.metric("BLI-05", f"{bli05}")
c8.metric("BLI-08", f"{bli08}")
c9.metric("Laporan Akhir", f"{reports}")

st.divider()

# ====================== Jadual DB asas (kalau perlu) ======================
with get_conn() as conn:
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_assignments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_user_id INTEGER NOT NULL,
            acad_sv_user_id INTEGER,
            ind_sv_user_id INTEGER,
            program_code TEXT,
            term_id INTEGER,
            assigned_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_user_id INTEGER NOT NULL,
            term_id INTEGER,
            acad_score REAL DEFAULT 0,
            ind_score REAL DEFAULT 0,
            total REAL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

# Helper: term_id aktif
with get_conn() as conn:
    df_term = pd.read_sql_query("SELECT term_id, session_label FROM terms ORDER BY term_id DESC LIMIT 1", conn)
term_id = int(df_term.iloc[0]["term_id"]) if not df_term.empty else None

# ---------------------- Util CSV Tanpa Lib Tambahan ----------------------
def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

def read_any_table(uploaded_file) -> pd.DataFrame:
    """
    Baca CSV atau XLSX (jika openpyxl tersedia). Keutamaan: CSV.
    """
    if uploaded_file is None:
        return pd.DataFrame()
    name = (uploaded_file.name or "").lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        # cuba excel jika ada openpyxl
        try:
            import openpyxl  # noqa: F401
            return pd.read_excel(uploaded_file)
        except Exception:
            # fallback: cuba interpret sebagai CSV juga
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Gagal baca fail: {e}")
        return pd.DataFrame()

def require_cols(df: pd.DataFrame, cols: list[str]) -> tuple[bool, str]:
    missing = [c for c in cols if c not in df.columns]
    return (len(missing)==0, ", ".join(missing))

# ---------------------- 1) Papar & Muat Turun Senarai Pelajar ----------------------
st.header("👥 Senarai Pelajar Mengikut Program")

prog = st.selectbox("Pilih program", ["Semua","CS241","CS248","CS249","CS290"], index=0)
query_prog = "" if prog=="Semua" else " AND u.program_code=? "
params = () if prog=="Semua" else (prog,)

with get_conn() as conn:
    sql = f"""
        SELECT 
            u.user_id,
            u.student_id AS no_pelajar,
            u.full_name AS nama_pelajar,
            u.program_code AS program,
            COALESCE(p.org_name,'-') AS organisasi,
            COALESCE(u2.full_name,'(tiada)') AS penyelia_akademik,
            COALESCE(u3.full_name,'(tiada)') AS penyelia_industri
        FROM users u
        LEFT JOIN placements p ON p.student_id=u.user_id AND p.term_id = ?
        LEFT JOIN supervisor_assignments sa ON sa.student_user_id=u.user_id AND sa.term_id = ?
        LEFT JOIN users u2 ON u2.user_id = sa.acad_sv_user_id
        LEFT JOIN users u3 ON u3.user_id = sa.ind_sv_user_id
        WHERE u.role_id=1 {query_prog}
        ORDER BY u.program_code, u.student_id
    """
    p = (term_id, term_id) + params
    df_roster = pd.read_sql_query(sql, conn, params=p)

if df_roster.empty:
    st.info("Tiada pelajar ditemui untuk pilihan ini.")
else:
    st.dataframe(df_roster[["no_pelajar","nama_pelajar","program","organisasi","penyelia_akademik","penyelia_industri"]],
                 use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Muat turun senarai pelajar (CSV)",
        data=df_to_csv_bytes(df_roster[["no_pelajar","nama_pelajar","program","organisasi","penyelia_akademik","penyelia_industri"]]),
        file_name=f"senarai_pelajar_{prog if prog!='Semua' else 'SEMUA'}.csv",
        mime="text/csv"
    )

st.divider()

# ---------------------- 2) Muat Naik Pensyarah & Padanan ----------------------
st.header("🧑‍🏫 Muat Naik Senarai Pensyarah & Jana Padanan (Round-Robin)")

st.caption("**Templat CSV pensyarah**: lajur **sv_email, full_name, program_code, max_students** (max_students opsyenal).")
# Sediakan template CSV untuk pensyarah
tmpl_sv = pd.DataFrame(columns=["sv_email","full_name","program_code","max_students"])
st.download_button("📥 Muat turun templat Pensyarah (CSV)",
                   data=df_to_csv_bytes(tmpl_sv),
                   file_name="template_pensyarah.csv",
                   mime="text/csv")

up_acad = st.file_uploader("Muat naik senarai pensyarah (CSV/XLSX)", key="acad_csv")
df_acad = read_any_table(up_acad)

if not df_acad.empty:
    ok, miss = require_cols(df_acad, ["sv_email","full_name","program_code"])
    if not ok:
        st.error(f"Lajur wajib tiada dalam fail pensyarah: {miss}")
        df_acad = pd.DataFrame()
    else:
        if "max_students" not in df_acad.columns:
            df_acad["max_students"] = None
        st.success(f"Pensyarah dimuat: {len(df_acad)} baris")
        st.dataframe(df_acad, use_container_width=True)

# Pilih program untuk dipadan atau 'Semua'
prog_match = st.selectbox("Program untuk padanan", ["Semua","CS241","CS248","CS249","CS290"], index=0)
btn_match = st.button("⚖️ Jana & Simpan Padanan (Akademik)")

def get_or_create_user(email, full_name, role_id, program_code=None):
    import hashlib
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE email=?", (email,))
        r = cur.fetchone()
        if r:
            return int(r[0])
        ph = hashlib.sha256("DEFAULT123".encode()).hexdigest()
        cur.execute("""
            INSERT INTO users(full_name, email, role_id, program_code, password_hash, is_active)
            VALUES (?,?,?,?,?,1)
        """, (full_name, email, role_id, program_code, ph))
        conn.commit()
        return cur.lastrowid

if btn_match:
    # Ambil senarai pelajar ikut program pilihan
    params_match = () if prog_match=="Semua" else (prog_match,)
    with get_conn() as conn:
        sql = f"""
          SELECT user_id, student_id, full_name, program_code
          FROM users
          WHERE role_id=1 {("" if prog_match=="Semua" else " AND program_code=? ")}
          ORDER BY program_code, student_id
        """
        df_students = pd.read_sql_query(sql, conn, params=params_match)

    if df_students.empty:
        st.warning("Tiada pelajar untuk dipadankan.")
    elif df_acad.empty:
        st.warning("Muat naik senarai pensyarah dahulu.")
    else:
        # Filter pensyarah ikut program
        if prog_match != "Semua":
            df_sv_prog = df_acad[df_acad["program_code"]==prog_match].copy()
        else:
            df_sv_prog = df_acad.copy()
        if df_sv_prog.empty:
            st.warning("Tiada pensyarah untuk program terpilih.")
        else:
            df_sv_prog["max_students"] = pd.to_numeric(df_sv_prog["max_students"], errors="coerce").fillna(999).astype(int)
            df_sv_prog["assigned"] = 0

            assigned_rows = []
            idx = 0
            sv_len = len(df_sv_prog)
            for _, srow in df_students.reset_index(drop=True).iterrows():
                tries = 0
                while tries < sv_len and df_sv_prog.iloc[idx]["assigned"] >= df_sv_prog.iloc[idx]["max_students"]:
                    idx = (idx + 1) % sv_len; tries += 1
                sv = df_sv_prog.iloc[idx]
                assigned_rows.append({
                    "student_id": srow["student_id"],
                    "student_name": srow["full_name"],
                    "program_code": srow["program_code"],
                    "acad_sv_email": sv["sv_email"],
                    "acad_sv_name": sv["full_name"],
                })
                df_sv_prog.at[df_sv_prog.index[idx], "assigned"] += 1
                idx = (idx + 1) % sv_len

            df_assigned = pd.DataFrame(assigned_rows)
            st.subheader("Hasil Padanan (Pratonton)")
            st.dataframe(df_assigned, use_container_width=True)

            # Simpan ke DB
            with get_conn() as conn:
                cur = conn.cursor()
                for _, r in df_assigned.iterrows():
                    # cari student_user_id
                    cur.execute("SELECT user_id FROM users WHERE student_id=?", (str(r["student_id"]),))
                    stu = cur.fetchone()
                    if not stu:
                        # fallback cipta user pelajar jika tiada
                        stu_email = f"{r['student_id']}@student.uitm.edu.my"
                        stu_id = get_or_create_user(stu_email, r["student_name"], 1, r["program_code"])
                    else:
                        stu_id = int(stu[0])

                    acad_id = get_or_create_user(r["acad_sv_email"], r["acad_sv_name"], 3, r["program_code"])

                    cur.execute("""
                        INSERT INTO supervisor_assignments(student_user_id, acad_sv_user_id, ind_sv_user_id, program_code, term_id, assigned_at)
                        VALUES (?,?,?,?,?, datetime('now'))
                    """, (stu_id, acad_id, None, r["program_code"], term_id))
                conn.commit()
            st.success("Padanan & simpanan ke DB berjaya.")

            # Muat turun CSV hasil padanan
            st.download_button(
                "⬇️ Muat turun padanan (CSV)",
                data=df_to_csv_bytes(df_assigned),
                file_name=f"padanan_akademik_{prog_match if prog_match!='Semua' else 'SEMUA'}.csv",
                mime="text/csv"
            )

st.divider()

# ---------------------- 3) Muat Turun Markah Gabungan ----------------------
st.header("📊 Muat Turun Markah (Akademik + Industri)")

st.caption("Sistem akan ambil **rekod terkini** setiap pelajar bagi markah akademik (BLI-08) & industri (BLI-05).")

# Ambil markah terkini: BLI-08 (akademik)
with get_conn() as conn:
    sql_acad = """
      SELECT b.student_user_id AS user_id, MAX(b.id) AS last_id
      FROM bli08_academic b
      WHERE b.term_id=?
      GROUP BY b.student_user_id
    """
    df_last_acad = pd.read_sql_query(sql_acad, conn, params=(term_id,))
    df_acad_score = pd.DataFrame(columns=["user_id","acad_score"])
    if not df_last_acad.empty:
        ids = tuple(df_last_acad["last_id"].tolist())
        # SQLite IN () perlukan sekurang-kurangnya satu elemen
        sql2 = f"SELECT id, student_user_id AS user_id, total AS acad_score FROM bli08_academic WHERE id IN ({','.join(['?']*len(ids))})"
        df_acad_score = pd.read_sql_query(sql2, conn, params=ids)

# Ambil markah terkini: BLI-05 (industri)
with get_conn() as conn:
    sql_ind = """
      SELECT b.student_user_id AS user_id, MAX(b.id) AS last_id
      FROM bli05_industry b
      WHERE b.term_id=?
      GROUP BY b.student_user_id
    """
    df_last_ind = pd.read_sql_query(sql_ind, conn, params=(term_id,))
    df_ind_score = pd.DataFrame(columns=["user_id","ind_score"])
    if not df_last_ind.empty:
        ids = tuple(df_last_ind["last_id"].tolist())
        sql2 = f"SELECT id, student_user_id AS user_id, total AS ind_score FROM bli05_industry WHERE id IN ({','.join(['?']*len(ids))})"
        df_ind_score = pd.read_sql_query(sql2, conn, params=ids)

# Gabung dengan senarai pelajar + supervisor + program (ikut pilihan paparan)
with get_conn() as conn:
    sql_students = f"""
      SELECT 
        u.user_id, u.student_id AS no_pelajar, u.full_name AS nama_pelajar, u.program_code AS program,
        COALESCE(u2.full_name,'(tiada)') AS penyelia_akademik
      FROM users u
      LEFT JOIN supervisor_assignments sa ON sa.student_user_id=u.user_id AND sa.term_id=?
      LEFT JOIN users u2 ON u2.user_id = sa.acad_sv_user_id
      WHERE u.role_id=1 {("" if prog=="Semua" else " AND u.program_code=? ")}
      ORDER BY u.program_code, u.student_id
    """
    params_students = (term_id,) if prog=="Semua" else (term_id, prog)
    df_students_for_marks = pd.read_sql_query(sql_students, conn, params=params_students)

df_merge = df_students_for_marks.merge(df_acad_score, on="user_id", how="left") \
                                .merge(df_ind_score, on="user_id", how="left")
df_merge["acad_score"] = pd.to_numeric(df_merge["acad_score"], errors="coerce").fillna(0.0)
df_merge["ind_score"]  = pd.to_numeric(df_merge["ind_score"], errors="coerce").fillna(0.0)
# Anda boleh ubah weight di sini (contoh 50/50)
df_merge["total"] = df_merge["acad_score"]*0.5 + df_merge["ind_score"]*0.5

st.dataframe(df_merge[["no_pelajar","nama_pelajar","program","penyelia_akademik","acad_score","ind_score","total"]],
             use_container_width=True, hide_index=True)

st.download_button(
    "⬇️ Muat turun markah gabungan (CSV)",
    data=df_to_csv_bytes(df_merge[["no_pelajar","nama_pelajar","program","penyelia_akademik","acad_score","ind_score","total"]]),
    file_name=f"markah_gabungan_{prog if prog!='Semua' else 'SEMUA'}.csv",
    mime="text/csv"
)

st.divider()
if st.button("Log Keluar"):
    st.session_state.auth=None; st.rerun()

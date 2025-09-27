# pages/4_Penyelaras_Dashboard.py
import os, datetime
from io import BytesIO
import pandas as pd
import streamlit as st
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

# ==== GUARD (wajib): hanya penyelaras boleh buka page ini ====
try:
    from lib.common import require_role
except Exception:
    # fallback ringan kalau require_role belum ada
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

# ====================== DB BOOTSTRAP (jadual khas penyelaras) ======================
with get_conn() as conn:
    cur = conn.cursor()
    # Pemetaan penyelia ↔ pelajar (akademik & industri)
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
    # Markah ringkas terkumpul
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

# Helper: dapatkan term_id aktif
with get_conn() as conn:
    df_term = pd.read_sql_query("SELECT term_id, session_label FROM terms ORDER BY term_id DESC LIMIT 1", conn)
term_id = int(df_term.iloc[0]["term_id"]) if not df_term.empty else None

# ---------------------- TEMPLATE EXCEL HELPERS ----------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "templates")

def _gen_template_df(kind: str) -> pd.DataFrame:
    if kind == "students":
        # WAJIB: student_id, full_name, program_code
        return pd.DataFrame(columns=["student_id", "full_name", "program_code"])
    if kind == "acad_supervisors":
        # WAJIB: sv_email, full_name, program_code, max_students (optional)
        return pd.DataFrame(columns=["sv_email", "full_name", "program_code", "max_students"])
    if kind == "marks_academic":
        return pd.DataFrame(columns=["student_id", "acad_score"])
    if kind == "marks_industry":
        return pd.DataFrame(columns=["student_id", "ind_score"])
    return pd.DataFrame()

def _df_to_xlsx_bytes(df: pd.DataFrame, sheet_name="template") -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return bio.getvalue()

def get_template_bytes(filename: str, kind: str) -> bytes:
    """
    Cuba baca fail template dari templates/; jika tak wujud, jana dari DataFrame.
    """
    try_path = os.path.join(TEMPLATES_DIR, filename)
    if os.path.exists(try_path):
        with open(try_path, "rb") as f:
            return f.read()
    df = _gen_template_df(kind)
    return _df_to_xlsx_bytes(df)

def _require_cols(df: pd.DataFrame, required: list[str]) -> tuple[bool, str]:
    missing = [c for c in required if c not in df.columns]
    return (len(missing) == 0, ", ".join(missing))

# ---------------------- HELPER CIPTA USER ----------------------
def _get_or_create_user(email, full_name, role_id, program_code=None):
    import hashlib
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE email=?", (email,))
        r = cur.fetchone()
        if r: 
            return int(r[0])
        # buat default password 'DEFAULT123'
        ph = hashlib.sha256("DEFAULT123".encode()).hexdigest()
        cur.execute("""
            INSERT INTO users(full_name, email, role_id, program_code, password_hash, is_active)
            VALUES (?,?,?,?,?,1)
        """, (full_name, email, role_id, program_code, ph))
        conn.commit()
        return cur.lastrowid

# ====================== 1) MATCH PENYELIA AKADEMIK ↔ PELAJAR ======================
st.header("📎 Padanan Penyelia Akademik ↔ Pelajar")

colt1, colt2 = st.columns(2)
with colt1:
    st.write("**Muat naik senarai pelajar (Excel)** — gunakan templat:")
    st.download_button(
        "📥 Muat turun template pelajar (XLSX)",
        data=get_template_bytes("template_students.xlsx", kind="students"),
        file_name="template_students.xlsx"
    )
    up_students = st.file_uploader("Upload fail pelajar (.xlsx)", type=["xlsx"], key="stud_xlsx")

with colt2:
    st.write("**Muat naik senarai penyelia akademik (Excel)** — gunakan templat:")
    st.download_button(
        "📥 Muat turun template penyelia akademik (XLSX)",
        data=get_template_bytes("template_acad_supervisors.xlsx", kind="acad_supervisors"),
        file_name="template_acad_supervisors.xlsx"
    )
    up_acad = st.file_uploader("Upload fail penyelia akademik (.xlsx)", type=["xlsx"], key="acad_xlsx")

df_students = pd.DataFrame(); df_acad = pd.DataFrame()
if up_students:
    try:
        df_students = pd.read_excel(up_students)
        ok, miss = _require_cols(df_students, ["student_id","full_name","program_code"])
        if not ok:
            st.error(f"Lajur wajib tiada dalam fail pelajar: {miss}")
            df_students = pd.DataFrame()
        else:
            st.success(f"Pelajar dimuat: {len(df_students)} baris")
            st.dataframe(df_students.head(), use_container_width=True)
    except Exception as e:
        st.error(f"Gagal baca fail pelajar: {e}")

if up_acad:
    try:
        df_acad = pd.read_excel(up_acad)
        ok, miss = _require_cols(df_acad, ["sv_email","full_name","program_code"])
        if not ok:
            st.error(f"Lajur wajib tiada dalam fail penyelia akademik: {miss}")
            df_acad = pd.DataFrame()
        else:
            if "max_students" not in df_acad.columns:
                df_acad["max_students"] = None
            st.success(f"Penyelia akademik dimuat: {len(df_acad)} baris")
            st.dataframe(df_acad.head(), use_container_width=True)
    except Exception as e:
        st.error(f"Gagal baca fail penyelia akademik: {e}")

# Butang 'Jana Padanan'
if not df_students.empty and not df_acad.empty:
    st.caption("Padanan dibuat **ikut program** dan secara **round-robin** mengikut kapasiti `max_students` (jika ada).")
    if st.button("⚖️ Jana & Simpan Padanan"):
        try:
            assigned_rows = []
            for prog, df_s_prog in df_students.groupby("program_code"):
                # filter supervisors ikut program
                df_sv_prog = df_acad[df_acad["program_code"]==prog].copy()
                if df_sv_prog.empty:
                    st.warning(f"Tiada penyelia untuk program {prog}; langkau.")
                    continue
                df_sv_prog["max_students"] = df_sv_prog["max_students"].fillna(999).astype(int)
                df_sv_prog["assigned"] = 0

                # pusingan round-robin
                idx = 0
                df_s_prog = df_s_prog.reset_index(drop=True)
                for _, srow in df_s_prog.iterrows():
                    tries = 0
                    while tries < len(df_sv_prog) and df_sv_prog.iloc[idx]["assigned"] >= df_sv_prog.iloc[idx]["max_students"]:
                        idx = (idx + 1) % len(df_sv_prog); tries += 1
                    sv = df_sv_prog.iloc[idx]
                    assigned_rows.append({
                        "student_id": srow["student_id"],
                        "student_name": srow.get("full_name",""),
                        "program_code": prog,
                        "acad_sv_email": sv["sv_email"],
                        "acad_sv_name": sv["full_name"],
                    })
                    df_sv_prog.at[df_sv_prog.index[idx], "assigned"] += 1
                    idx = (idx + 1) % len(df_sv_prog)

            df_assigned = pd.DataFrame(assigned_rows)
            st.subheader("Hasil Padanan (Pratonton)")
            st.dataframe(df_assigned, use_container_width=True)

            # Simpan ke DB
            with get_conn() as conn:
                cur = conn.cursor()
                for _, r in df_assigned.iterrows():
                    # cari student_user_id melalui student_id
                    cur.execute("SELECT user_id, program_code FROM users WHERE student_id=?", (str(r["student_id"]),))
                    stu = cur.fetchone()
                    if not stu:
                        # fallback create pelajar guna email templated
                        stu_email = f"{r['student_id']}@student.uitm.edu.my"
                        stu_id = _get_or_create_user(stu_email, r.get("student_name","Pelajar"), 1, r.get("program_code"))
                    else:
                        stu_id = int(stu[0])

                    acad_id = _get_or_create_user(r["acad_sv_email"], r["acad_sv_name"], 3, r["program_code"])

                    cur.execute("""
                        INSERT INTO supervisor_assignments(student_user_id, acad_sv_user_id, ind_sv_user_id, program_code, term_id, assigned_at)
                        VALUES (?,?,?,?,?, datetime('now'))
                    """, (stu_id, acad_id, None, r["program_code"], term_id))
                conn.commit()
            st.success("Padanan & simpanan ke DB berjaya.")
        except Exception as e:
            st.error(f"Gagal menjana/simpan padanan: {e}")

st.divider()

# ====================== 2) MARKAH: muat naik & gabung ======================
st.header("📝 Markah (Penyelia Akademik & Industri)")

colm1, colm2 = st.columns(2)
with colm1:
    st.write("**Template markah akademik**")
    st.download_button(
        "📥 Muat turun template markah akademik", 
        data=get_template_bytes("template_marks_academic.xlsx", kind="marks_academic"),
        file_name="template_marks_academic.xlsx"
    )
    up_mk_acad = st.file_uploader("Upload markah akademik (.xlsx)", type=["xlsx"], key="marks_acad")

with colm2:
    st.write("**Template markah industri**")
    st.download_button(
        "📥 Muat turun template markah industri", 
        data=get_template_bytes("template_marks_industry.xlsx", kind="marks_industry"),
        file_name="template_marks_industry.xlsx"
    )
    up_mk_ind = st.file_uploader("Upload markah industri (.xlsx)", type=["xlsx"], key="marks_ind")

df_mka = pd.read_excel(up_mk_acad) if up_mk_acad else pd.DataFrame(columns=["student_id","acad_score"])
df_mki = pd.read_excel(up_mk_ind) if up_mk_ind else pd.DataFrame(columns=["student_id","ind_score"])

if not df_mka.empty:
    ok, miss = _require_cols(df_mka, ["student_id","acad_score"])
    if not ok:
        st.error(f"Lajur wajib tiada dalam markah akademik: {miss}")
        df_mka = pd.DataFrame(columns=["student_id","acad_score"])
if not df_mki.empty:
    ok, miss = _require_cols(df_mki, ["student_id","ind_score"])
    if not ok:
        st.error(f"Lajur wajib tiada dalam markah industri: {miss}")
        df_mki = pd.DataFrame(columns=["student_id","ind_score"])

if not df_mka.empty or not df_mki.empty:
    df_marks = pd.merge(df_mka, df_mki, on="student_id", how="outer")
    df_marks["acad_score"] = pd.to_numeric(df_marks["acad_score"], errors="coerce").fillna(0.0)
    df_marks["ind_score"]  = pd.to_numeric(df_marks["ind_score"], errors="coerce").fillna(0.0)
    # contoh weighting 50/50
    df_marks["total"] = df_marks["acad_score"]*0.5 + df_marks["ind_score"]*0.5  

    st.subheader("Pratonton Markah Gabungan")
    st.dataframe(df_marks, use_container_width=True)

    if st.button("💾 Simpan Markah ke DB"):
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                for _, r in df_marks.iterrows():
                    # map student_id -> user_id
                    cur.execute("SELECT user_id FROM users WHERE student_id=?", (str(r["student_id"]),))
                    stu = cur.fetchone()
                    if not stu:
                        continue
                    stu_id = int(stu[0])
                    cur.execute("""
                        INSERT INTO grades(student_user_id, term_id, acad_score, ind_score, total, updated_at)
                        VALUES (?,?,?,?,?, datetime('now'))
                    """, (stu_id, term_id, float(r["acad_score"]), float(r["ind_score"]), float(r["total"])))
                conn.commit()
            st.success("Markah disimpan.")
        except Exception as e:
            st.error(f"Gagal simpan markah: {e}")

    if not df_marks.empty:
        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="xlsxwriter") as w:
            df_marks.to_excel(w, index=False, sheet_name="marks")
        st.download_button("⬇️ Muat turun markah (gabungan)", data=bio.getvalue(), file_name="markah_gabungan.xlsx")

st.divider()

# ====================== 3) Paparan mengikut program ======================
st.header("👁️‍🗨️ Papar Ikut Program")

prog = st.selectbox("Pilih program", ["Semua","CS241","CS248","CS249","CS290"])
query_prog = "" if prog=="Semua" else " AND u.program_code=? "

with get_conn() as conn:
    sql = f"""
        SELECT u.student_id, u.full_name AS student_name, u.program_code,
               COALESCE(u2.full_name,'(tiada)') AS acad_sv,
               COALESCE(u3.full_name,'(tiada)') AS ind_sv,
               COALESCE(g.acad_score,0) AS acad_score,
               COALESCE(g.ind_score,0) AS ind_score,
               COALESCE(g.total,0) AS total
        FROM users u
        LEFT JOIN supervisor_assignments sa ON sa.student_user_id = u.user_id
        LEFT JOIN users u2 ON u2.user_id = sa.acad_sv_user_id
        LEFT JOIN users u3 ON u3.user_id = sa.ind_sv_user_id
        LEFT JOIN grades g ON g.student_user_id = u.user_id AND g.term_id = sa.term_id
        WHERE u.role_id=1 {query_prog}
        ORDER BY u.program_code, u.student_id
    """
    params = () if prog=="Semua" else (prog,)
    df_view = pd.read_sql_query(sql, conn, params=params)

st.dataframe(df_view, use_container_width=True)

st.divider()
if st.button("Log Keluar"): 
    st.session_state.auth=None; st.rerun()

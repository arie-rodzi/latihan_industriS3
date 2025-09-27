# pages/4_Penyelaras_Dashboard.py
import os, io, json
import pandas as pd
import streamlit as st
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

# ============== Setup asas ==============
st.set_page_config(page_title="Penyelaras", page_icon="⚙️", layout="wide")
st.title("Dashboard Penyelaras")

# Pastikan DB sedia
try:
    ensure_db(os.path.join(os.path.dirname(__file__), "..", "init_mytimes_fyp.sql"))
except Exception as e:
    st.error(f"Ralat DB: {e}"); st.stop()

# Login/Guard
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

user = st.session_state.auth
program_managed = user.get("program_code") or "-"
st.success(f"Log masuk sebagai {user['full_name']} — Program: **{program_managed}**")

# Term aktif
with get_conn() as conn:
    df_term = pd.read_sql_query("SELECT term_id, session_label FROM terms ORDER BY term_id DESC LIMIT 1", conn)
if df_term.empty:
    st.warning("Tiada term aktif."); st.stop()
term_id = int(df_term.iloc[0]["term_id"])
st.info(f"Sesi semasa: **{df_term.iloc[0]['session_label']}**")

# Pastikan kolum class_section wujud (migrasi ringan)
def ensure_users_has_class_section():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = {r[1] for r in cur.fetchall()}
        if "class_section" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN class_section TEXT")
            conn.commit()
ensure_users_has_class_section()

# Util CSV (tanpa xlsxwriter)
def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO(); df.to_csv(buf, index=False); return buf.getvalue().encode("utf-8")

def read_any_table(uploaded_file) -> pd.DataFrame:
    """Baca CSV atau XLSX (jika openpyxl ada)."""
    if uploaded_file is None: return pd.DataFrame()
    name = (uploaded_file.name or "").lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        try:
            import openpyxl  # noqa: F401
            return pd.read_excel(uploaded_file)
        except Exception:
            uploaded_file.seek(0); return pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Gagal baca fail: {e}"); return pd.DataFrame()

def require_cols(df: pd.DataFrame, cols: list[str]) -> tuple[bool, str]:
    missing = [c for c in cols if c not in df.columns]
    return (len(missing)==0, ", ".join(missing))

# ================= METRICS ringkas =================
with get_conn() as conn:
    tlabel = term_label(conn)
    total_students = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=1 AND program_code=?", (program_managed,)) or 0
    total_acad = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=3 AND program_code=?", (program_managed,)) or 0
    total_ind = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=4") or 0
    bli01 = one(conn, "SELECT COUNT(1) FROM bli01") or 0
    bli02 = one(conn, "SELECT COUNT(1) FROM bli02_responses") or 0
    placements_cnt = one(conn, "SELECT COUNT(1) FROM placements WHERE term_id=?", (term_id,)) or 0
    bli05 = one(conn, "SELECT COUNT(1) FROM bli05_industry WHERE term_id=?", (term_id,)) or 0
    bli08 = one(conn, "SELECT COUNT(1) FROM bli08_academic WHERE term_id=?", (term_id,)) or 0
    reports = one(conn, "SELECT COUNT(1) FROM final_reports WHERE term_id=?", (term_id,)) or 0

c1,c2,c3 = st.columns(3)
c1.metric("Pelajar (program ini)", f"{total_students}")
c2.metric("Penyelia Akademik (program ini)", f"{total_acad}")
c3.metric("Penyelia Industri (semua)", f"{total_ind}")
c4,c5,c6 = st.columns(3)
c4.metric("BLI-01", f"{bli01}")
c5.metric("BLI-02", f"{bli02}")
c6.metric("Penempatan (term ini)", f"{placements_cnt}")
c7,c8,c9 = st.columns(3)
c7.metric("BLI-05 (term ini)", f"{bli05}")
c8.metric("BLI-08 (term ini)", f"{bli08}")
c9.metric("Laporan Akhir (term ini)", f"{reports}")

st.divider()

# ================= Pilih KELAS (dlm program penyelaras) =================
with get_conn() as conn:
    df_sections = pd.read_sql_query("""
        SELECT class_section, COUNT(1) AS bil
        FROM users
        WHERE role_id=1 AND program_code=? AND COALESCE(class_section,'')!=''
        GROUP BY class_section
        ORDER BY class_section
    """, conn, params=(program_managed,))

if df_sections.empty:
    st.error("Tiada kelas ditemui untuk program ini. Pastikan pelajar program ini mempunyai `class_section` semasa pendaftaran.")
    st.stop()

kelas_list = df_sections["class_section"].tolist()
kelas = st.selectbox("Pilih KELAS", kelas_list, index=0)
st.caption(f"Kelas dipilih: **{kelas}**")

cls_filter = " AND u.class_section=? "
cls_params = (kelas,)

# ================= Senarai Pelajar (kelas dipilih) =================
st.header("👥 Senarai Pelajar Kelas Ini")

with get_conn() as conn:
    sql_roster = f"""
        SELECT 
            u.user_id,
            u.student_id            AS no_pelajar,
            u.full_name             AS nama_pelajar,
            u.program_code          AS program,
            COALESCE(u.class_section,'-') AS kelas,
            COALESCE(p.org_name,'-')     AS organisasi,
            COALESCE(ind.full_name,'(tiada)')  AS penyelia_industri,
            COALESCE(acad.full_name,'(tiada)') AS penyelia_akademik
        FROM users u
        LEFT JOIN supervisor_assignments sa 
          ON sa.student_user_id=u.user_id AND sa.term_id=?
        LEFT JOIN users acad ON acad.user_id = sa.acad_sv_user_id
        LEFT JOIN users ind  ON ind.user_id  = sa.ind_sv_user_id
        LEFT JOIN placements p 
          ON p.student_id=u.user_id AND p.term_id=?
        WHERE u.role_id=1 AND u.program_code=? {cls_filter}
        ORDER BY u.student_id
    """
    params = (term_id, term_id, program_managed) + cls_params
    df_roster = pd.read_sql_query(sql_roster, conn, params=params)

if df_roster.empty:
    st.info("Tiada pelajar ditemui untuk kelas ini.")
else:
    st.caption(f"Bilangan pelajar: **{len(df_roster)}**")
    st.dataframe(df_roster[["no_pelajar","nama_pelajar","program","kelas","organisasi","penyelia_industri","penyelia_akademik"]],
                 use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Muat turun senarai pelajar (CSV)",
        data=df_to_csv_bytes(df_roster[["no_pelajar","nama_pelajar","program","kelas","organisasi","penyelia_industri","penyelia_akademik"]]),
        file_name=f"senarai_pelajar_{kelas.replace(' ','_')}.csv",
        mime="text/csv"
    )

st.divider()

# ================= Muat naik pensyarah akademik & PADANAN (kelas dipilih) =================
st.header("🧑‍🏫 Muat Naik Pensyarah Akademik & Jana Padanan (Kelas ini)")

st.caption("**Templat CSV/XLSX**: lajur **sv_email, full_name, max_students** (max_students opsyenal).")
tmpl_sv = pd.DataFrame({"sv_email":[],"full_name":[],"max_students":[]})
st.download_button("📥 Muat turun templat Pensyarah (CSV)",
                   data=df_to_csv_bytes(tmpl_sv),
                   file_name=f"template_pensyarah_{program_managed}.csv",
                   mime="text/csv")

up_acad = st.file_uploader("Muat naik senarai pensyarah (CSV/XLSX) — untuk program ini", key="acad_csv")
df_acad = read_any_table(up_acad)
if not df_acad.empty:
    ok, miss = require_cols(df_acad, ["sv_email","full_name"])
    if not ok:
        st.error(f"Lajur wajib tiada: {miss}")
        df_acad = pd.DataFrame()
    else:
        if "max_students" not in df_acad.columns: df_acad["max_students"] = None
        st.success(f"Pensyarah dimuat: {len(df_acad)} baris")
        st.dataframe(df_acad, use_container_width=True, hide_index=True)

def get_or_create_user(email, full_name, role_id, program_code=None):
    import hashlib
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE email=?", (email,))
        r = cur.fetchone()
        if r: return int(r[0])
        ph = hashlib.sha256("DEFAULT123".encode()).hexdigest()
        cur.execute("""
            INSERT INTO users(full_name, email, role_id, program_code, password_hash, is_active)
            VALUES (?,?,?,?,?,1)
        """, (full_name, email, role_id, program_code, ph))
        conn.commit()
        return cur.lastrowid

if st.button("⚖️ Jana & Simpan Padanan Akademik (kelas ini)"):
    with get_conn() as conn:
        df_students = pd.read_sql_query("""
          SELECT user_id, student_id, full_name
          FROM users
          WHERE role_id=1 AND program_code=? AND class_section=?
          ORDER BY student_id
        """, conn, params=(program_managed, kelas))

    if df_students.empty:
        st.warning("Tiada pelajar untuk dipadankan dalam kelas ini.")
    elif df_acad.empty:
        st.warning("Muat naik senarai pensyarah dahulu.")
    else:
        df_sv = df_acad.copy()
        df_sv["max_students"] = pd.to_numeric(df_sv["max_students"], errors="coerce").fillna(999).astype(int)
        df_sv["assigned"] = 0

        # Buang assignment AKAD lama untuk kelas ini pada term ini (Industri dikekalkan)
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM supervisor_assignments
                WHERE term_id=? AND program_code=? AND student_user_id IN (
                    SELECT user_id FROM users WHERE role_id=1 AND program_code=? AND class_section=?
                )
            """, (term_id, program_managed, program_managed, kelas))
            conn.commit()

        # Round-robin
        assigned = []
        idx = 0; n = len(df_sv)
        for _, s in df_students.reset_index(drop=True).iterrows():
            tries = 0
            while tries < n and df_sv.iloc[idx]["assigned"] >= df_sv.iloc[idx]["max_students"]:
                idx = (idx + 1) % n; tries += 1
            sv = df_sv.iloc[idx]
            assigned.append({
                "student_id": s["student_id"],
                "student_user_id": int(s["user_id"]),
                "acad_sv_email": sv["sv_email"],
                "acad_sv_name": sv["full_name"]
            })
            df_sv.at[df_sv.index[idx], "assigned"] += 1
            idx = (idx + 1) % n

        df_assigned = pd.DataFrame(assigned)

        # Simpan → `supervisor_assignments`
        with get_conn() as conn:
            cur = conn.cursor()
            for _, r in df_assigned.iterrows():
                acad_id = get_or_create_user(r["acad_sv_email"], r["acad_sv_name"], 3, program_code=program_managed)
                cur.execute("""
                    INSERT INTO supervisor_assignments(student_user_id, acad_sv_user_id, ind_sv_user_id, program_code, term_id, assigned_at)
                    VALUES (?,?,?,?,?, datetime('now'))
                """, (int(r["student_user_id"]), acad_id, None, program_managed, term_id))
            conn.commit()

        st.success(f"Padanan disimpan untuk kelas {kelas}.")
        st.download_button(
            "⬇️ Muat turun CSV padanan",
            data=df_to_csv_bytes(df_assigned[["student_id","acad_sv_email","acad_sv_name"]]),
            file_name=f"padanan_akademik_{kelas.replace(' ','_')}.csv",
            mime="text/csv"
        )
        st.rerun()

st.divider()

# ================= Senarai Penyelia Industri (kelas) =================
st.header("🏭 Senarai Penyelia Industri — Kelas Ini")

with get_conn() as conn:
    sql_indlist = f"""
        SELECT 
          COALESCE(ind.full_name,'(tiada)') AS nama_penyelia_industri,
          COALESCE(ind.email,'-')          AS emel_penyelia_industri,
          COUNT(1) AS bil_pelajar
        FROM users u
        LEFT JOIN supervisor_assignments sa 
          ON sa.student_user_id=u.user_id AND sa.term_id=?
        LEFT JOIN users ind ON ind.user_id=sa.ind_sv_user_id
        WHERE u.role_id=1 AND u.program_code=? {cls_filter}
        GROUP BY ind.user_id, ind.full_name, ind.email
        ORDER BY bil_pelajar DESC, nama_penyelia_industri
    """
    params = (term_id, program_managed) + cls_params
    df_indlist = pd.read_sql_query(sql_indlist, conn, params=params)

st.dataframe(df_indlist, use_container_width=True, hide_index=True)
st.download_button(
    "⬇️ Muat turun senarai penyelia industri (CSV)",
    data=df_to_csv_bytes(df_indlist),
    file_name=f"senarai_penyelia_industri_{kelas.replace(' ','_')}.csv",
    mime="text/csv"
)

st.divider()

# ================= Markah Gabungan (kelas) =================
st.header("📊 Markah (Akademik + Industri) — Kelas Ini")

def fetch_latest_ids(conn, table, key_student="student_user_id"):
    sql = f"""
        SELECT {key_student} AS user_id, MAX(id) AS last_id
        FROM {table}
        WHERE term_id=?
        GROUP BY {key_student}
    """
    return pd.read_sql_query(sql, conn, params=(term_id,))

with get_conn() as conn:
    # Pelajar kelas
    df_students = pd.read_sql_query("""
        SELECT user_id, student_id AS no_pelajar, full_name AS nama_pelajar
        FROM users
        WHERE role_id=1 AND program_code=? AND class_section=?
        ORDER BY student_id
    """, conn, params=(program_managed, kelas))

    # Latest academic
    df_last_acad = fetch_latest_ids(conn, "bli08_academic")
    df_acad = pd.DataFrame(columns=["user_id","acad_score"])
    if not df_last_acad.empty:
        ids = tuple(df_last_acad["last_id"].tolist())
        sql = f"SELECT id, student_user_id AS user_id, total AS acad_score FROM bli08_academic WHERE id IN ({','.join(['?']*len(ids))})"
        df_acad = pd.read_sql_query(sql, conn, params=ids)

    # Latest industry
    df_last_ind = fetch_latest_ids(conn, "bli05_industry")
    df_ind = pd.DataFrame(columns=["user_id","ind_score"])
    if not df_last_ind.empty:
        ids = tuple(df_last_ind["last_id"].tolist())
        sql = f"SELECT id, student_user_id AS user_id, total AS ind_score FROM bli05_industry WHERE id IN ({','.join(['?']*len(ids))})"
        df_ind = pd.read_sql_query(sql, conn, params=ids)

# Merge & papar
dfm = df_students.merge(df_acad, on="user_id", how="left").merge(df_ind, on="user_id", how="left")
dfm["acad_score"] = pd.to_numeric(dfm["acad_score"], errors="coerce").fillna(0.0)
dfm["ind_score"]  = pd.to_numeric(dfm["ind_score"],  errors="coerce").fillna(0.0)
dfm["total"] = dfm["acad_score"]*0.5 + dfm["ind_score"]*0.5  # ubah weight jika perlu

st.dataframe(dfm[["no_pelajar","nama_pelajar","acad_score","ind_score","total"]],
             use_container_width=True, hide_index=True)

st.download_button(
    "⬇️ Muat turun markah gabungan (CSV)",
    data=df_to_csv_bytes(dfm[["no_pelajar","nama_pelajar","acad_score","ind_score","total"]]),
    file_name=f"markah_gabungan_{kelas.replace(' ','_')}.csv",
    mime="text/csv"
)

st.divider()
if st.button("Log Keluar"):
    st.session_state.auth=None; st.rerun()

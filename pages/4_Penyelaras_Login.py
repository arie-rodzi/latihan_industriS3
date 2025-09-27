# pages/4_Penyelaras_Dashboard.py
import os, io, math, hashlib
import pandas as pd
import streamlit as st
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

# ================= Setup asas =================
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

# ---------------------- Selepas login: program & term ----------------------
user = st.session_state.auth

# Tetapkan program penyelaras (fallback demo jika None) dan simpan balik
program_managed = (user.get("program_code") or "").strip()
if not program_managed:
    program_managed = "CS241"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET program_code=? WHERE user_id=?", (program_managed, user["user_id"]))
        conn.commit()

st.success(f"Log masuk sebagai {user['full_name']} — Program: **{program_managed}**")

with get_conn() as conn:
    df_term = pd.read_sql_query("SELECT term_id, session_label FROM terms ORDER BY term_id DESC LIMIT 1", conn)
if df_term.empty:
    st.warning("Tiada term aktif."); st.stop()
term_id = int(df_term.iloc[0]["term_id"])
st.info(f"Sesi semasa: **{df_term.iloc[0]['session_label']}**")

# ---------------------- Util umum ----------------------
def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def ensure_users_has_class_section():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = {r[1] for r in cur.fetchall()}
        if "class_section" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN class_section TEXT")
            conn.commit()

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
            import openpyxl  # noqa
            return pd.read_excel(uploaded_file)
        except Exception:
            uploaded_file.seek(0); return pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Gagal baca fail: {e}"); return pd.DataFrame()

def require_cols(df: pd.DataFrame, cols: list[str]) -> tuple[bool, str]:
    missing = [c for c in cols if c not in df.columns]
    return (len(missing)==0, ", ".join(missing))

# ---------------------- Seeder 25/kelas (50 total) ----------------------
ensure_users_has_class_section()

def seed_or_fix_classes_for_program(program_code: str, term_id: int) -> str:
    """
    Sasaran demo: 25 pelajar utk {PROGRAM}7A dan 25 pelajar utk {PROGRAM}7B (total 50).
    - Jika tiada pelajar → cipta 50 (25/kelas).
    - Jika ada tapi tiada class_section → bahagikan ke 7A/7B kemudian top-up hingga 25/kelas.
    - Tambah placements & padanan industri (Kumar/Lim) jika belum ada utk term ini.
    """
    target_per_class = 25
    secA, secB = f"{program_code}7A", f"{program_code}7B"

    with get_conn() as conn:
        cur = conn.cursor()
        # Dapatkan senarai pelajar semasa
        df = pd.read_sql_query("""
            SELECT user_id, student_id, COALESCE(class_section,'') AS cs
            FROM users WHERE role_id=1 AND program_code=?
            ORDER BY CAST(student_id AS TEXT)
        """, conn, params=(program_code,))
        total = len(df)

        def _create_students(n, section, start_sid):
            for i in range(n):
                sid = str(start_sid + i)
                name = f"Pelajar {program_code} #{sid[-2:]}"
                email = f"{sid}@student.uitm.edu.my"
                cur.execute("""
                    INSERT INTO users(full_name, email, role_id, program_code, student_id, class_section, password_hash, is_active)
                    VALUES (?,?,?,?,?,?,?,1)
                """, (name, email, 1, program_code, sid, section, _sha("DEFAULT123")))
            conn.commit()

        if total == 0:
            base = 20252000
            _create_students(target_per_class, secA, base+1)
            _create_students(target_per_class, secB, base+1+target_per_class)
        else:
            # Jika tiada class_section langsung → bahagikan separuh ke A/B
            if not any(df["cs"].str.strip()):
                half = (total + 1)//2
                idsA = df.iloc[:half]["user_id"].tolist()
                idsB = df.iloc[half:]["user_id"].tolist()
                if idsA:
                    cur.execute(f"UPDATE users SET class_section=? WHERE user_id IN ({','.join(['?']*len(idsA))})",
                                (secA, *idsA))
                if idsB:
                    cur.execute(f"UPDATE users SET class_section=? WHERE user_id IN ({','.join(['?']*len(idsB))})",
                                (secB, *idsB))
                conn.commit()

            # Top-up setiap kelas hinggalah 25
            countA = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=1 AND program_code=? AND class_section=?",
                         (program_code, secA)) or 0
            countB = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=1 AND program_code=? AND class_section=?",
                         (program_code, secB)) or 0
            base = int(one(conn, "SELECT COALESCE(MAX(CAST(student_id AS INTEGER)), 20252000) FROM users", ())) or 20252000
            if countA < target_per_class:
                _create_students(target_per_class - countA, secA, base+1); base += (target_per_class - countA)
            if countB < target_per_class:
                _create_students(target_per_class - countB, secB, base+1); base += (target_per_class - countB)

        # Pastikan penyelia industri demo wujud
        def _get_or_create_user(email, full_name, role_id):
            cur.execute("SELECT user_id FROM users WHERE email=?", (email,))
            r = cur.fetchone()
            if r: return int(r[0])
            cur.execute("""INSERT INTO users(full_name, email, role_id, password_hash, is_active)
                           VALUES (?,?,?,?,1)""", (full_name, email, role_id, _sha("DEFAULT123")))
            conn.commit(); return cur.lastrowid

        kumar_id = _get_or_create_user("kumar@industry.com", "Encik Kumar", 4)
        lim_id   = _get_or_create_user("lim@industry.com",   "Encik Lim",   4)

        # Tambah placements & padanan industri (skip jika sudah ada)
        df_stu = pd.read_sql_query("""
            SELECT u.user_id FROM users u
            WHERE u.role_id=1 AND u.program_code=? AND u.class_section IN (?,?)
            ORDER BY CAST(u.student_id AS TEXT)
        """, conn, params=(program_code, secA, secB))
        for idx, r in df_stu.iterrows():
            uid = int(r["user_id"])
            # placements
            cur.execute("SELECT 1 FROM placements WHERE student_id=? AND term_id=? LIMIT 1", (uid, term_id))
            if not cur.fetchone():
                cur.execute("""INSERT INTO placements(student_id, org_name, address, contact_person, contact_email, contact_phone, term_id, created_at)
                               VALUES (?,?,?,?,?,?,?, datetime('now'))""",
                            (uid, f"Syarikat Demo #{idx+1:02d}", "Alamat Demo",
                             "Penyelia Syarikat", "pic@demo.com", "03-12345678", term_id))
            # padan industri
            cur.execute("""SELECT 1 FROM supervisor_assignments 
                           WHERE student_user_id=? AND term_id=? LIMIT 1""", (uid, term_id))
            if not cur.fetchone():
                ind_id = kumar_id if (idx % 2 == 0) else lim_id
                cur.execute("""INSERT INTO supervisor_assignments(student_user_id, acad_sv_user_id, ind_sv_user_id, program_code, term_id, assigned_at)
                               VALUES (?,?,?,?,?, datetime('now'))""",
                            (uid, None, ind_id, program_code, term_id))
        conn.commit()
    return f"OK: {secA} & {secB} dipastikan ≥25 pelajar setiap satu."

msg_init = seed_or_fix_classes_for_program(program_managed, term_id)
st.caption(f"Init kelas: {msg_init}")

st.divider()

# ---------------------- METRICS ringkas ----------------------
with get_conn() as conn:
    tlabel = term_label(conn)
    total_students = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=1 AND program_code=?", (program_managed,)) or 0
    total_ind = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=4") or 0
    placements_cnt = one(conn, "SELECT COUNT(1) FROM placements WHERE term_id=?", (term_id,)) or 0
    bli05 = one(conn, "SELECT COUNT(1) FROM bli05_industry WHERE term_id=?", (term_id,)) or 0
    bli08 = one(conn, "SELECT COUNT(1) FROM bli08_academic WHERE term_id=?", (term_id,)) or 0
    reports = one(conn, "SELECT COUNT(1) FROM final_reports WHERE term_id=?", (term_id,)) or 0

c1,c2,c3 = st.columns(3)
c1.metric("Pelajar (program ini)", f"{total_students}")
c2.metric("Penyelia Industri (semua)", f"{total_ind}")
c3.metric("Penempatan (term ini)", f"{placements_cnt}")
c4,c5,c6 = st.columns(3)
c4.metric("BLI-05 (term ini)", f"{bli05}")
c5.metric("BLI-08 (term ini)", f"{bli08}")
c6.metric("Laporan Akhir (term ini)", f"{reports}")

st.divider()

# ---------------------- Pilih KELAS ----------------------
with get_conn() as conn:
    df_sections = pd.read_sql_query("""
        SELECT class_section, COUNT(1) AS bil
        FROM users
        WHERE role_id=1 AND program_code=? AND COALESCE(class_section,'')!=''
        GROUP BY class_section
        ORDER BY class_section
    """, conn, params=(program_managed,))
if df_sections.empty:
    st.error("Tiada kelas ditemui untuk program ini."); st.stop()

kelas_list = df_sections["class_section"].tolist()
kelas = st.selectbox("Pilih KELAS", kelas_list, index=0)
st.caption(f"Kelas dipilih: **{kelas}**")

# ---------------------- Senarai Pelajar (kelas dipilih) ----------------------
st.header("👥 Senarai Pelajar Kelas Ini")

with get_conn() as conn:
    sql_roster = """
        SELECT 
            u.user_id,
            u.student_id            AS no_pelajar,
            u.full_name             AS nama_pelajar,
            u.program_code          AS program,
            COALESCE(u.class_section,'-') AS kelas,
            COALESCE(p.org_name,'-')     AS organisasi,
            COALESCE(ind.full_name,'(tiada)')  AS penyelia_industri
        FROM users u
        LEFT JOIN supervisor_assignments sa 
          ON sa.student_user_id=u.user_id AND sa.term_id=?
        LEFT JOIN users ind  ON ind.user_id  = sa.ind_sv_user_id
        LEFT JOIN placements p 
          ON p.student_id=u.user_id AND p.term_id=?
        WHERE u.role_id=1 AND u.program_code=? AND u.class_section=?
        ORDER BY u.student_id
    """
    df_roster = pd.read_sql_query(sql_roster, conn, params=(term_id, term_id, program_managed, kelas))

st.caption(f"Bilangan pelajar: **{len(df_roster)}**")
st.dataframe(
    df_roster[["no_pelajar","nama_pelajar","program","kelas","organisasi","penyelia_industri"]],
    use_container_width=True, hide_index=True
)
st.download_button(
    "⬇️ Muat turun senarai pelajar (CSV)",
    data=df_to_csv_bytes(df_roster[["no_pelajar","nama_pelajar","program","kelas","organisasi","penyelia_industri"]]),
    file_name=f"senarai_pelajar_{kelas.replace(' ','_')}.csv",
    mime="text/csv"
)

st.divider()

# ---------------------- Muat naik Pensyarah & PADANAN (kelas) ----------------------
st.header("🧑‍🏫 Muat Naik Pensyarah Akademik & Jana Padanan (Kelas ini)")
st.caption("**Templat (boleh buka dengan Excel)**: lajur **sv_email, full_name, max_students**.")

tmpl_sv = pd.DataFrame({
    "sv_email": ["ahmad@uitm.edu.my", "zuraida@uitm.edu.my", "lee@uitm.edu.my"],
    "full_name": ["En. Ahmad", "Pn. Zuraida", "En. Lee"],
    "max_students": [12, 12, 12]
})
st.download_button(
    "📥 Muat turun templat Pensyarah (CSV)",
    data=df_to_csv_bytes(tmpl_sv),
    file_name=f"template_pensyarah_{program_managed}_{kelas}.csv",
    mime="text/csv"
)

up_acad = st.file_uploader("Muat naik senarai pensyarah (CSV/XLSX) — padanan untuk kelas ini", key="acad_csv")
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
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE email=?", (email,))
        r = cur.fetchone()
        if r: return int(r[0])
        cur.execute("""
            INSERT INTO users(full_name, email, role_id, program_code, password_hash, is_active)
            VALUES (?,?,?,?,?,1)
        """, (full_name, email, role_id, program_code, _sha("DEFAULT123")))
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

        # Buang assignment akademik lama untuk kelas ini pada term ini (industri kekal)
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

        # Simpan assignment akademik
        with get_conn() as conn:
            cur = conn.cursor()
            for _, r in df_assigned.iterrows():
                acad_id = get_or_create_user(r["acad_sv_email"], r["acad_sv_name"], 3, program_code=program_managed)
                cur.execute("""
                    INSERT INTO supervisor_assignments(student_user_id, acad_sv_user_id, ind_sv_user_id, program_code, term_id, assigned_at)
                    VALUES (?,?,?,?,?, datetime('now'))
                """, (int(r["student_user_id"]), acad_id, None, program_managed, term_id))
            conn.commit()

        st.success(f"Padanan akademik disimpan untuk kelas {kelas}.")
        st.download_button(
            "⬇️ Muat turun CSV padanan",
            data=df_to_csv_bytes(df_assigned[["student_id","acad_sv_email","acad_sv_name"]]),
            file_name=f"padanan_akademik_{kelas.replace(' ','_')}.csv",
            mime="text/csv"
        )
        st.rerun()

st.divider()

# ---------------------- Senarai Penyelia Industri (kelas) ----------------------
st.header("🏭 Senarai Penyelia Industri — Kelas Ini")
with get_conn() as conn:
    df_indlist = pd.read_sql_query("""
        SELECT 
          COALESCE(ind.full_name,'(tiada)') AS nama_penyelia_industri,
          COALESCE(ind.email,'-')          AS emel_penyelia_industri,
          COUNT(1) AS bil_pelajar
        FROM users u
        LEFT JOIN supervisor_assignments sa 
          ON sa.student_user_id=u.user_id AND sa.term_id=?
        LEFT JOIN users ind ON ind.user_id=sa.ind_sv_user_id
        WHERE u.role_id=1 AND u.program_code=? AND u.class_section=?
        GROUP BY ind.user_id, ind.full_name, ind.email
        ORDER BY bil_pelajar DESC, nama_penyelia_industri
    """, conn, params=(term_id, program_managed, kelas))

st.dataframe(df_indlist, use_container_width=True, hide_index=True)
st.download_button(
    "⬇️ Muat turun senarai penyelia industri (CSV)",
    data=df_to_csv_bytes(df_indlist),
    file_name=f"senarai_penyelia_industri_{kelas.replace(' ','_')}.csv",
    mime="text/csv"
)

st.divider()

# ---------------------- Markah Gabungan (kelas) ----------------------
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

    # Rekod terkini akademik
    df_last_acad = fetch_latest_ids(conn, "bli08_academic")
    df_acad = pd.DataFrame(columns=["user_id","acad_score"])
    if not df_last_acad.empty:
        ids = tuple(df_last_acad["last_id"].tolist())
        sql = f"SELECT id, student_user_id AS user_id, total AS acad_score FROM bli08_academic WHERE id IN ({','.join(['?']*len(ids))})"
        df_acad = pd.read_sql_query(sql, conn, params=ids)

    # Rekod terkini industri
    df_last_ind = fetch_latest_ids(conn, "bli05_industry")
    df_ind = pd.DataFrame(columns=["user_id","ind_score"])
    if not df_last_ind.empty:
        ids = tuple(df_last_ind["last_id"].tolist())
        sql = f"SELECT id, student_user_id AS user_id, total AS ind_score FROM bli05_industry WHERE id IN ({','.join(['?']*len(ids))})"
        df_ind = pd.read_sql_query(sql, conn, params=ids)

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

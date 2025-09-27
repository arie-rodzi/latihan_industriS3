# pages/4_Penyelaras_Dashboard.py
import os, io, json, re, math
import pandas as pd
import streamlit as st
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

# ========== Setup ==========
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

# ====== SEED DEMO: jika program ini tiada langsung kelas, auto pecahkan kepada 2 kelas (…7A, …7B) ======
def seed_demo_sections_for_program(program_code: str):
    """Auto-assign class_section untuk pelajar program ini jika kosong.
       Logik: sort ikut student_id → bahagikan hampir sama rata ke {program}7A dan {program}7B."""
    with get_conn() as conn:
        # Ada data kelas?
        df_chk = pd.read_sql_query("""
            SELECT COUNT(1) AS c
            FROM users
            WHERE role_id=1 AND program_code=? AND COALESCE(class_section,'')!=''
        """, conn, params=(program_code,))
        has_any = int(df_chk.iloc[0]["c"]) > 0

        if has_any:
            return 0, (f"{program_code} — kelas sedia ada, tiada seeding")

        # ambil semua pelajar program ini
        df_students = pd.read_sql_query("""
            SELECT user_id, student_id
            FROM users
            WHERE role_id=1 AND program_code=?
            ORDER BY CAST(student_id AS TEXT)
        """, conn, params=(program_code,))

        if df_students.empty:
            return 0, (f"{program_code} — tiada pelajar untuk diseed")

        # tentukan label kelas
        # contoh ringkas: kalau program CS241 → kelas CS2417A & CS2417B
        suffix = "7"
        secA = f"{program_code}{suffix}A"
        secB = f"{program_code}{suffix}B"

        # bahagikan hampir separuh
        n = len(df_students)
        half = math.ceil(n/2)
        idsA = df_students.iloc[:half]["user_id"].tolist()
        idsB = df_students.iloc[half:]["user_id"].tolist()

        cur = conn.cursor()
        if idsA:
            cur.execute(f"UPDATE users SET class_section=? WHERE user_id IN ({','.join(['?']*len(idsA))})",
                        (secA, *idsA))
        if idsB:
            cur.execute(f"UPDATE users SET class_section=? WHERE user_id IN ({','.join(['?']*len(idsB))})",
                        (secB, *idsB))
        conn.commit()
        return n, (f"Seed kelas demo siap: {secA} ~{len(idsA)} pelajar, {secB} ~{len(idsB)} pelajar")

# jalankan seeding DEMO bila perlu
seed_n, seed_msg = seed_demo_sections_for_program(program_managed)
if seed_n > 0:
    st.warning(seed_msg)
# kalau tak perlu seeding, diam2 je; data real kekal

# Util CSV (tanpa xlsxwriter)
def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO(); df.to_csv(buf, index=False); return buf.getvalue().encode("utf-8")

def read_any_table(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None: return pd.DataFrame()
    name = (uploaded_file.name or "").lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        try:
            import openpyxl  # jika ada, benarkan .xlsx
            return pd.read_excel(uploaded_file)
        except Exception:
            uploaded_file.seek(0); return pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Gagal baca fail: {e}"); return pd.DataFrame()

def require_cols(df: pd.DataFrame, cols: list[str]) -> tuple[bool, str]:
    missing = [c for c in cols if c not in df.columns]
    return (len(missing)==0, ", ".join(missing))

st.divider()

# ====================== Senarai kelas sedia ada (selepas seeding jika perlu) ======================
with get_conn() as conn:
    df_sections = pd.read_sql_query("""
        SELECT class_section, COUNT(1) AS bil
        FROM users
        WHERE role_id=1 AND program_code=? AND COALESCE(class_section,'')!=''
        GROUP BY class_section
        ORDER BY class_section
    """, conn, params=(program_managed,))
if df_sections.empty:
    st.error("Masih tiada kelas ditemui untuk program ini (walau selepas seeding). Sahkan data pelajar wujud.")
    st.stop()

kelas_list = df_sections["class_section"].tolist()
kelas = st.selectbox("Pilih kelas (section)", kelas_list, index=0)

cls_filter = " AND u.class_section=? "
cls_params = (kelas,)

# ====================== Upload pensyarah akademik & matching kelas ======================
st.header("🧑‍🏫 Muat Naik Pensyarah Akademik & Padan (Kelas terpilih)")
st.caption("**Templat CSV/XLSX**: lajur **sv_email,full_name,max_students** (max_students opsyenal). Program diambil sebagai **"
           + program_managed + "** mengikut akaun penyelaras.")

tmpl_sv = pd.DataFrame({"sv_email":[],"full_name":[],"max_students":[]})
st.download_button("📥 Muat turun templat Pensyarah (CSV)",
                   data=df_to_csv_bytes(tmpl_sv),
                   file_name=f"template_pensyarah_{program_managed}.csv",
                   mime="text/csv")

up_acad = st.file_uploader("Muat naik senarai pensyarah (CSV/XLSX)", key="acad_csv")
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

if st.button("⚖️ Jana & Simpan Padanan Akademik (untuk kelas ini)"):
    # Ambil pelajar kelas terpilih
    with get_conn() as conn:
        sql_stu = """
          SELECT user_id, student_id, full_name
          FROM users u
          WHERE u.role_id=1 AND u.program_code=? AND u.class_section=?
          ORDER BY u.student_id
        """
        df_students = pd.read_sql_query(sql_stu, conn, params=(program_managed, kelas))

    if df_students.empty:
        st.warning("Tiada pelajar untuk dipadankan dalam kelas ini.")
    elif df_acad.empty:
        st.warning("Muat naik senarai pensyarah dahulu.")
    else:
        df_sv = df_acad.copy()
        df_sv["max_students"] = pd.to_numeric(df_sv["max_students"], errors="coerce").fillna(999).astype(int)
        df_sv["assigned"] = 0
        if df_sv.empty:
            st.warning("Senarai pensyarah kosong.")
        else:
            # Buang assignment akademik lama untuk pelajar kelas ini pada term ini
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

            # Simpan ke DB
            with get_conn() as conn:
                cur = conn.cursor()
                for _, r in df_assigned.iterrows():
                    acad_id = get_or_create_user(r["acad_sv_email"], r["acad_sv_name"], 3, program_managed)
                    cur.execute("""
                        INSERT INTO supervisor_assignments(student_user_id, acad_sv_user_id, ind_sv_user_id, program_code, term_id, assigned_at)
                        VALUES (?,?,?,?,?, datetime('now'))
                    """, (int(r["student_user_id"]), acad_id, None, program_managed, term_id))
                conn.commit()

            st.success(f"Padanan disimpan untuk kelas {kelas}.")
            st.download_button(
                "⬇️ Muat turun CSV padanan",
                data=df_to_csv_bytes(df_assigned[["student_id","acad_sv_email","acad_sv_name"]]),
                file_name=f"padanan_akademik_{program_managed}_{kelas.replace(' ','_')}.csv",
                mime="text/csv"
            )
            st.rerun()

st.divider()

# ====================== Roster kelas (data sedia ada / selepas seeding) ======================
st.header("👥 Senarai Pelajar (mengikut kelas)")

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
    st.error("Tiada pelajar ditemui untuk kelas ini. (Pelik, patutnya selepas seeding mesti ada.)")
else:
    st.caption(f"Bilangan pelajar: **{len(df_roster)}**")
    st.dataframe(df_roster[["no_pelajar","nama_pelajar","program","kelas","organisasi","penyelia_industri","penyelia_akademik"]],
                 use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Muat turun senarai pelajar (CSV)",
        data=df_to_csv_bytes(df_roster[["no_pelajar","nama_pelajar","program","kelas","organisasi","penyelia_industri","penyelia_akademik"]]),
        file_name=f"senarai_pelajar_{program_managed}_{kelas.replace(' ','_')}.csv",
        mime="text/csv"
    )

st.divider()

# ====================== Senarai Penyelia Industri (kelas terpilih) ======================
st.header("🏭 Senarai Penyelia Industri (kelas terpilih)")

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
    file_name=f"senarai_penyelia_industri_{program_managed}_{kelas.replace(' ','_')}.csv",
    mime="text/csv"
)

st.divider()

# ====================== Markah (CLO) — semua pelajar dalam kelas ======================
st.header("📊 Markah (CLO) — semua pelajar dalam kelas")

def fetch_latest_ids(conn, table, key_student="student_user_id"):
    sql = f"""
        SELECT {key_student} AS user_id, MAX(id) AS last_id
        FROM {table}
        WHERE term_id=?
        GROUP BY {key_student}
    """
    return pd.read_sql_query(sql, conn, params=(term_id,))

with get_conn() as conn:
    df_last_acad = fetch_latest_ids(conn, "bli08_academic")
    df_acad = pd.DataFrame(columns=[
        "user_id","score_komunikasi","score_disiplin","score_kualiti","score_kehadiran","score_inisiatif","total"
    ])
    if not df_last_acad.empty:
        ids = tuple(df_last_acad["last_id"].tolist())
        sql = f"""
            SELECT id, student_user_id AS user_id,
                   score_komunikasi, score_disiplin, score_kualiti, score_kehadiran, score_inisiatif,
                   total
            FROM bli08_academic
            WHERE id IN ({','.join(['?']*len(ids))})
        """
        df_acad = pd.read_sql_query(sql, conn, params=ids)

    df_last_ind = fetch_latest_ids(conn, "bli05_industry")
    df_ind = pd.DataFrame(columns=["user_id","ind_total","details_json"])
    if not df_last_ind.empty:
        ids = tuple(df_last_ind["last_id"].tolist())
        sql = f"""
            SELECT id, student_user_id AS user_id,
                   total AS ind_total,
                   COALESCE(details_json,'') AS details_json
            FROM bli05_industry
            WHERE id IN ({','.join(['?']*len(ids))})
        """
        df_ind = pd.read_sql_query(sql, conn, params=ids)

# Senarai pelajar untuk merge
df_students = df_roster[["user_id","no_pelajar","nama_pelajar","kelas"]].copy()

# Gabung markah
dfm = df_students.merge(df_acad, on="user_id", how="left").merge(df_ind, on="user_id", how="left")

# Normalisasi numerik
for col in ["score_komunikasi","score_disiplin","score_kualiti","score_kehadiran","score_inisiatif","total","ind_total"]:
    if col in dfm.columns: dfm[col] = pd.to_numeric(dfm[col], errors="coerce")

# Pemetaan CLO Akademik
dfm["CLO1_Akad"] = dfm["score_komunikasi"]
dfm["CLO2_Akad"] = dfm["score_disiplin"] + dfm["score_kehadiran"]
dfm["CLO3_Akad"] = dfm["score_kualiti"]
dfm["CLO4_Akad"] = dfm["score_inisiatif"]

# Extract CLO Industri dari details_json jika ada
def extract_clo_from_json(s):
    try:
        if not s: return {}
        d = json.loads(s)
        out = {}
        for k, v in d.items():
            kk = str(k).strip().upper().replace(" ","").replace("_","")
            if kk in ["CLO1","CLO2","CLO3","CLO4"]:
                try: out[kk] = float(v)
                except: pass
        if not out and isinstance(d.get("clo", None), dict):
            for kk, vv in d["clo"].items():
                key = f"CLO{kk}".upper()
                try: out[key] = float(vv)
                except: pass
        return out
    except Exception:
        return {}

for i in range(1,5):
    dfm[f"CLO{i}_Ind"] = None
if "details_json" in dfm.columns:
    for idx, row in dfm.iterrows():
        clo = extract_clo_from_json(row.get("details_json"))
        for i in range(1,5):
            key = f"CLO{i}"
            if key in clo: dfm.at[idx, f"CLO{i}_Ind"] = clo[key]

# Papar & download
view_cols = [
    "no_pelajar","nama_pelajar","kelas",
    "CLO1_Akad","CLO2_Akad","CLO3_Akad","CLO4_Akad",
    "ind_total","CLO1_Ind","CLO2_Ind","CLO3_Ind","CLO4_Ind",
    "total"
]
view_cols = [c for c in view_cols if c in dfm.columns]
st.dataframe(dfm[view_cols], use_container_width=True, hide_index=True)
st.download_button(
    "⬇️ Muat turun markah (CLO) kelas ini — CSV",
    data=df_to_csv_bytes(dfm[view_cols]),
    file_name=f"markah_CLO_{program_managed}_{kelas.replace(' ','_')}.csv",
    mime="text/csv"
)

st.divider()
if st.button("Log Keluar"):
    st.session_state.auth=None; st.rerun()

# pages/4_Penyelaras_Dashboard.py
import os, io, json, re
import pandas as pd
import streamlit as st
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

# ========== Setup asas ==========
st.set_page_config(page_title="Penyelaras", page_icon="⚙️", layout="wide")
st.title("Dashboard Penyelaras")

# Pastikan DB sedia
try:
    ensure_db(os.path.join(os.path.dirname(__file__), "..", "init_mytimes_fyp.sql"))
except Exception as e:
    st.error(f"Ralat DB: {e}"); st.stop()

# Guard peranan
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
if user.get("role_name")!="coordinator":
    st.error("Akses tidak dibenarkan. Hanya Penyelaras."); st.stop()

# Program yang diselia oleh penyelaras ini
program_managed = user.get("program_code") or "-"
st.success(f"Log masuk sebagai {user['full_name']} — Program: **{program_managed}**")

# Term aktif
with get_conn() as conn:
    df_term = pd.read_sql_query(
        "SELECT term_id, session_label FROM terms ORDER BY term_id DESC LIMIT 1", conn
    )
if df_term.empty:
    st.warning("Tiada term aktif."); st.stop()
term_id = int(df_term.iloc[0]["term_id"])
st.info(f"Sesi semasa: **{df_term.iloc[0]['session_label']}**")

# ========== Migrasi ringan: tambah lajur class_section pada users kalau tiada ==========
def ensure_users_has_class_section():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = {r[1] for r in cur.fetchall()}
        if "class_section" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN class_section TEXT")
            conn.commit()
ensure_users_has_class_section()

# Util CSV
def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

st.divider()

# ========== Senarai Kelas (section) bagi program penyelaras ==========
with get_conn() as conn:
    df_sections = pd.read_sql_query("""
        SELECT class_section, COUNT(1) AS bil
        FROM users
        WHERE role_id=1 AND program_code=? AND COALESCE(class_section,'')!=''
        GROUP BY class_section
        ORDER BY class_section
    """, conn, params=(program_managed,))
if df_sections.empty:
    st.warning("Belum ada `class_section` diisi untuk pelajar program ini. Sila kemas kini medan kelas (contoh: CS2417A, CS2417B).")
    # Masih benarkan lihat semua pelajar program — tanpa tapis kelas
    sections = ["(SEMUA)"]
else:
    sections = ["(SEMUA)"] + df_sections["class_section"].tolist()

kelas = st.selectbox("Pilih kelas (section)", sections, index=0)

# Penapis SQL kelas
cls_filter = "" if kelas=="(SEMUA)" else " AND u.class_section=? "
cls_params = () if kelas=="(SEMUA)" else (kelas,)

# ========== 1) Senarai Pelajar 30 orang per kelas (roster) ==========
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
    st.info("Tiada pelajar ditemui untuk pilihan ini.")
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

# ========== 2) Senarai Penyelia Industri untuk kelas terpilih ==========
st.header("🏭 Senarai Penyelia Industri (kelas terpilih)")

if df_roster.empty:
    st.info("Tiada data untuk dipapar.")
else:
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

# ========== 3) Markah Semua Orang (ikut CLO) untuk kelas terpilih ==========
st.header("📊 Markah (CLO) — semua pelajar dalam kelas")

# Helper: baca rekod terkini mengikut student_user_id
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

# Ambil senarai pelajar (kelas pilih) untuk merge
df_students = df_roster[["user_id","no_pelajar","nama_pelajar","kelas"]].copy()

# Gabung markah
dfm = df_students.merge(df_acad, on="user_id", how="left").merge(df_ind, on="user_id", how="left")

# Kira CLO Akademik (pemetaan default)
# CLO1 = Komunikasi
# CLO2 = Disiplin + Kehadiran
# CLO3 = Kualiti Kerja
# CLO4 = Inisiatif
for col in ["score_komunikasi","score_disiplin","score_kualiti","score_kehadiran","score_inisiatif","total","ind_total"]:
    if col in dfm.columns:
        dfm[col] = pd.to_numeric(dfm[col], errors="coerce")

dfm["CLO1_Akad"] = dfm["score_komunikasi"]
dfm["CLO2_Akad"] = dfm["score_disiplin"] + dfm["score_kehadiran"]
dfm["CLO3_Akad"] = dfm["score_kualiti"]
dfm["CLO4_Akad"] = dfm["score_inisiatif"]

# Cuba baca CLO Industri dari details_json jika wujud
def extract_clo_from_json(s):
    try:
        if not s: return {}
        d = json.loads(s)
        out = {}
        # Jika JSON guna kunci CLO1..CLO4
        for k, v in d.items():
            if re.fullmatch(r"(?i)clo\s*([1-4])", str(k).replace("_"," ").strip()):
                out[k.upper().replace(" ","")] = float(v) if isinstance(v, (int,float,str)) else None
        # Atau kalau ada nested dict "clo": {"1":..}
        if not out and isinstance(d.get("clo", None), dict):
            for kk, vv in d["clo"].items():
                key = f"CLO{kk}".upper()
                try:
                    out[key] = float(vv)
                except Exception:
                    pass
        return out
    except Exception:
        return {}

clo_cols = ["CLO1_Ind","CLO2_Ind","CLO3_Ind","CLO4_Ind"]
for c in clo_cols: dfm[c] = None
if "details_json" in dfm.columns:
    for idx, row in dfm.iterrows():
        clo = extract_clo_from_json(row.get("details_json"))
        for i in range(1,5):
            key = f"CLO{i}"
            if key in clo:
                dfm.at[idx, f"CLO{i}_Ind"] = clo[key]

# Papar jadual markah
view_cols = [
    "no_pelajar","nama_pelajar","kelas",
    "CLO1_Akad","CLO2_Akad","CLO3_Akad","CLO4_Akad",
    "ind_total","CLO1_Ind","CLO2_Ind","CLO3_Ind","CLO4_Ind",
    "total"  # total akademik (daripada BLI-08)
]
# Jamin kolum wujud
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

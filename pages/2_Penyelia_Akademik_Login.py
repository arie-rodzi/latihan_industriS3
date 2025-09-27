# pages/2_Penyelia_Akademik_Dashboard.py
import os
import pandas as pd
import streamlit as st
from io import BytesIO
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

# ============ Setup & DB init ============
st.set_page_config(page_title="Penyelia Akademik", page_icon="📘", layout="wide")
st.title("Dashboard Penyelia Akademik")

try:
    ensure_db(os.path.join(os.path.dirname(__file__), "..", "init_mytimes_fyp.sql"))
except Exception as e:
    st.error(f"Ralat DB: {e}")
    st.stop()

# Jadual yang mungkin belum ada → buat ringkas
with get_conn() as conn:
    cur = conn.cursor()
    # Padanan penyelia (dibina oleh Penyelaras)
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
    # BLI-08 (Penilaian Penyelia Akademik)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bli08_academic(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_user_id INTEGER NOT NULL,
            acad_supervisor_id INTEGER NOT NULL,
            term_id INTEGER,
            score_komunikasi REAL DEFAULT 0,
            score_disiplin REAL DEFAULT 0,
            score_kualiti REAL DEFAULT 0,
            score_kehadiran REAL DEFAULT 0,
            score_inisiatif REAL DEFAULT 0,
            komen_umum TEXT,
            total REAL DEFAULT 0,
            submitted_at TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # Laporan Akhir (kalau belum wujud). Skema sebenar Dr mungkin dah ada.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS final_reports(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            term_id INTEGER,
            file_name TEXT,
            file_blob BLOB,              -- opsyen: kalau repo Dr simpan binari
            uploaded_at TEXT DEFAULT (datetime('now')),
            acad_status TEXT             -- e.g. PENDING/APPROVED/REJECTED
        )
    """)
    conn.commit()

# ============ Login ============
if "auth" not in st.session_state:
    st.session_state.auth = None

if not st.session_state.auth:
    st.subheader("Log Masuk Penyelia Akademik")
    with st.form("login_acad"):
        email = st.text_input("Emel")
        password = st.text_input("Kata Laluan", type="password")
        submitted = st.form_submit_button("Log Masuk")
    if submitted:
        user = auth_email_or_sid(email, password)
        if not user or user["role_name"] != "acad_sv":
            st.error("Akaun bukan Penyelia Akademik / salah maklumat.")
        else:
            st.session_state.auth = user
            st.rerun()
    st.stop()

# ============ Guard role ============
def require_role(roles):
    aut = st.session_state.get("auth")
    if not aut or aut.get("role_name") not in roles:
        st.error("Akses tidak dibenarkan untuk peranan anda.")
        st.stop()
require_role(["acad_sv"])

user = st.session_state.auth
st.success(f"Log masuk sebagai {user['full_name']}")

# ============ Info ringkas ============
with get_conn() as conn:
    tlabel = term_label(conn)
    # dapatkan term aktif
    term_df = pd.read_sql_query("SELECT term_id, session_label FROM terms ORDER BY term_id DESC LIMIT 1", conn)
    term_id = int(term_df.iloc[0]["term_id"]) if not term_df.empty else None

st.caption(f"**Sesi:** {tlabel if tlabel else '-'}")
if not term_id:
    st.warning("Tiada term aktif."); st.stop()

# Berapa pelajar di bawah jagaan + statistik
with get_conn() as conn:
    assigned = one(conn,
        "SELECT COUNT(1) FROM supervisor_assignments WHERE term_id=? AND acad_sv_user_id=?",
        (term_id, user['user_id'])
    )
    # BLI-08 belum lengkap: tiada rekod atau total=0
    pending_bli08 = one(conn,
        """SELECT COUNT(1) FROM supervisor_assignments sa
           LEFT JOIN bli08_academic b ON (b.student_user_id=sa.student_user_id AND b.term_id=sa.term_id AND b.acad_supervisor_id=?)
           WHERE sa.term_id=? AND sa.acad_sv_user_id=? AND (b.id IS NULL OR COALESCE(b.total,0)=0)""",
        (user['user_id'], term_id, user['user_id'])
    )
    # Laporan akhir status pending (kalau kolum acad_status wujud)
    reports_to_review = one(conn,
        "SELECT COUNT(1) FROM final_reports WHERE term_id=? AND COALESCE(acad_status,'PENDING')='PENDING'",
        (term_id,)
    )
    log_comments = one(conn,
        "SELECT COUNT(1) FROM logbook WHERE term_id=? AND acad_commented_by=?",
        (term_id, user['user_id'])
    )

c1, c2, c3 = st.columns(3)
c1.metric("Pelajar diselia", f"{assigned}")
c2.metric("BLI-08 belum lengkap", f"{pending_bli08}")
c3.metric("Laporan Akhir (Pending)", f"{reports_to_review}")

st.divider()

# ============ Senarai pelajar diselia ============
with get_conn() as conn:
    df_stu = pd.read_sql_query(
        """SELECT u.user_id, u.full_name, u.student_id, u.program_code
           FROM supervisor_assignments sa
           JOIN users u ON u.user_id = sa.student_user_id
           WHERE sa.term_id=? AND sa.acad_sv_user_id=?
           ORDER BY u.full_name""",
        conn, params=(term_id, user['user_id'])
    )

if df_stu.empty:
    st.info("Tiada pelajar di bawah jagaan anda.")
    if st.button("Log Keluar"):
        st.session_state.auth = None; st.rerun()
    st.stop()

label_to_id = {
    f"{r.student_id} — {r.full_name} ({r.program_code or '-'})": int(r.user_id)
    for r in df_stu.itertuples(index=False)
}
choice = st.selectbox("Pilih pelajar", list(label_to_id.keys()))
student_user_id = label_to_id[choice]

st.divider()

# ============ 1) Logbook & Komen ============
st.markdown("## 📒 Semak Logbook & Komen")

with get_conn() as conn:
    df_logs = pd.read_sql_query(
        """SELECT log_id, entry_date, title, activities, outcomes, hours,
                  COALESCE(acad_comment,'') AS acad_comment
           FROM logbook
           WHERE student_id=? AND term_id=?
           ORDER BY entry_date DESC""",
        conn, params=(student_user_id, term_id)
    )

st.caption(f"Jumlah entri: {len(df_logs)}")
if df_logs.empty:
    st.info("Pelajar ini belum isi logbook.")
else:
    st.dataframe(df_logs[["entry_date","title","hours","acad_comment"]], use_container_width=True)
    st.markdown("#### ✍️ Komen Pada Entri")
    for _, row in df_logs.iterrows():
        with st.expander(f"Entri {row['entry_date']} — {row['title'] or '-'}"):
            st.markdown("**Aktiviti**"); st.write(row["activities"] or "-")
            st.markdown("**Hasil/Outcomes**"); st.write(row["outcomes"] or "-")
            new_c = st.text_area("Komen (Akademik)", value=row["acad_comment"] or "", key=f"acad_c_{row['log_id']}")
            if st.button("Simpan Komen (Akademik)", key=f"btn_acad_{row['log_id']}"):
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("""UPDATE logbook
                                   SET acad_comment=?, acad_commented_by=?, acad_commented_at=datetime('now')
                                   WHERE log_id=?""",
                                (new_c, user['user_id'], int(row["log_id"])))
                    conn.commit()
                st.success("Komen akademik disimpan."); st.rerun()

st.divider()

# ============ 2) Laporan Akhir (download jika ada) ============
st.markdown("## 📄 Laporan Akhir Pelajar")
with get_conn() as conn:
    # cuba cari mengikut student & term
    df_rep = pd.read_sql_query(
        "SELECT id, file_name, uploaded_at, LENGTH(file_blob) AS blob_len FROM final_reports WHERE student_id=? AND term_id=? ORDER BY uploaded_at DESC",
        conn, params=(student_user_id, term_id)
    )

if df_rep.empty:
    st.info("Tiada muat naik Laporan Akhir untuk pelajar ini.")
else:
    st.dataframe(df_rep[["file_name","uploaded_at","blob_len"]], use_container_width=True)
    # kalau ada BLOB, tawarkan download
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT file_name, file_blob FROM final_reports WHERE student_id=? AND term_id=? ORDER BY uploaded_at DESC LIMIT 1",
                    (student_user_id, term_id))
        row = cur.fetchone()
    if row and row[1]:
        st.download_button("⬇️ Muat Turun Laporan Akhir (terkini)", data=row[1],
                           file_name=row[0] or "Laporan_Akhir.docx")
    else:
        st.info("Repositori laporan tidak simpan binari (file_blob). Pastikan modul pelajar simpan fail sebagai BLOB atau letakkan pautan simpanan.")

st.divider()

# ============ 3) BLI-08 — Penilaian Penyelia Akademik ============
st.markdown("## 📝 BLI-08 — Penilaian Penyelia Akademik")

# prefill jika pernah isi
with get_conn() as conn:
    df_bli08 = pd.read_sql_query(
        """SELECT id, score_komunikasi, score_disiplin, score_kualiti, score_kehadiran, score_inisiatif,
                  komen_umum, total, submitted_at
           FROM bli08_academic
           WHERE student_user_id=? AND term_id=? AND acad_supervisor_id=?
           ORDER BY id DESC LIMIT 1""",
        conn, params=(student_user_id, term_id, user['user_id'])
    )
pref = df_bli08.iloc[0] if not df_bli08.empty else None

colA, colB, colC = st.columns(3)
s1 = colA.number_input("Komunikasi (0–20)", min_value=0.0, max_value=20.0, step=1.0, value=float(pref["score_komunikasi"]) if pref is not None else 0.0)
s2 = colA.number_input("Disiplin (0–20)",   min_value=0.0, max_value=20.0, step=1.0, value=float(pref["score_disiplin"]) if pref is not None else 0.0)
s3 = colB.number_input("Kualiti kerja (0–30)", min_value=0.0, max_value=30.0, step=1.0, value=float(pref["score_kualiti"]) if pref is not None else 0.0)
s4 = colB.number_input("Kehadiran (0–15)",  min_value=0.0, max_value=15.0, step=1.0, value=float(pref["score_kehadiran"]) if pref is not None else 0.0)
s5 = colC.number_input("Inisiatif (0–15)",  min_value=0.0, max_value=15.0, step=1.0, value=float(pref["score_inisiatif"]) if pref is not None else 0.0)
komen = st.text_area("Komen umum", value=pref["komen_umum"] if pref is not None else "")

total = s1 + s2 + s3 + s4 + s5
st.metric("Jumlah Markah", f"{total:.1f} / 100")

colX, colY = st.columns(2)
if colX.button("💾 Simpan Draf (boleh ubah)"):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bli08_academic(student_user_id, acad_supervisor_id, term_id,
                score_komunikasi, score_disiplin, score_kualiti, score_kehadiran, score_inisiatif,
                komen_umum, total, submitted_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?, NULL, datetime('now'))
        """, (student_user_id, user['user_id'], term_id, s1, s2, s3, s4, s5, komen, total))
        conn.commit()
    st.success("Draf penilaian disimpan.")
    st.rerun()

if colY.button("✅ Hantar (muktamad)"):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bli08_academic(student_user_id, acad_supervisor_id, term_id,
                score_komunikasi, score_disiplin, score_kualiti, score_kehadiran, score_inisiatif,
                komen_umum, total, submitted_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?, datetime('now'), datetime('now'))
        """, (student_user_id, user['user_id'], term_id, s1, s2, s3, s4, s5, komen, total))
        conn.commit()
    st.success("Penilaian dihantar.")
    st.rerun()

st.divider()
if st.button("Log Keluar"):
    st.session_state.auth = None
    st.rerun()

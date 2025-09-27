# pages/2_Penyelia_Akademik_Dashboard.py
import os
import pandas as pd
import streamlit as st
from io import BytesIO
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

# ---- Setup
st.set_page_config(page_title="Penyelia Akademik", page_icon="📘", layout="wide")
st.title("Dashboard Penyelia Akademik")

try:
    ensure_db(os.path.join(os.path.dirname(__file__), "..", "init_mytimes_fyp.sql"))
except Exception as e:
    st.error(f"Ralat DB: {e}"); st.stop()

# ---- Guard util
def require_role(roles):
    aut = st.session_state.get("auth")
    if not aut or aut.get("role_name") not in roles:
        st.error("Akses tidak dibenarkan. Sila log masuk sebagai Penyelia Akademik.")
        st.stop()

# ---- Login
if "auth" not in st.session_state: st.session_state.auth = None
if not st.session_state.auth:
    st.subheader("Log Masuk Penyelia Akademik")
    with st.form("login_acad"):
        email = st.text_input("Emel")
        password = st.text_input("Kata Laluan", type="password")
        submitted = st.form_submit_button("Log Masuk")
    if submitted:
        user = auth_email_or_sid(email, password)
        if not user or user["role_name"]!="acad_sv":
            st.error("Akaun bukan Penyelia Akademik / salah maklumat.")
        else:
            st.session_state.auth = user; st.rerun()
    st.stop()

# ---- Guard role
require_role(["acad_sv"])
user = st.session_state.auth
st.success(f"Log masuk sebagai {user['full_name']}")

# ---- Pastikan jadual penting wujud (tak crash kalau baru)
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS final_reports(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            term_id INTEGER,
            file_name TEXT,
            file_blob BLOB,
            uploaded_at TEXT DEFAULT (datetime('now')),
            acad_status TEXT
        )
    """)
    # Kolum komen logbook jika belum ada
    cur.execute("PRAGMA table_info(logbook)")
    cols = {r[1] for r in cur.fetchall()}
    if "acad_comment" not in cols:      cur.execute("ALTER TABLE logbook ADD COLUMN acad_comment TEXT")
    if "acad_commented_by" not in cols: cur.execute("ALTER TABLE logbook ADD COLUMN acad_commented_by INTEGER")
    if "acad_commented_at" not in cols: cur.execute("ALTER TABLE logbook ADD COLUMN acad_commented_at TEXT")
    conn.commit()

# ---- Term semasa
with get_conn() as conn:
    tlabel = term_label(conn)
    df_term = pd.read_sql_query("SELECT term_id FROM terms ORDER BY term_id DESC LIMIT 1", conn)
term_id = int(df_term.iloc[0]["term_id"]) if not df_term.empty else None
st.caption(f"**Sesi:** {tlabel or '-'}")
if not term_id:
    st.warning("Tiada term aktif."); st.stop()

# ---- Senarai pelajar di bawah jagaan penyelia ini
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
    if st.button("Log Keluar"): st.session_state.auth=None; st.rerun()
    st.stop()

st.subheader("Pelajar Diselia")
st.dataframe(df_stu, use_container_width=True)

st.divider()

# ---------- LOOP: panel setiap pelajar (Ali, Siti, ... apa-apa yang dipadankan) ----------
for row in df_stu.itertuples(index=False):
    stu_id = int(row.user_id)
    stu_label = f"{row.student_id} — {row.full_name} ({row.program_code or '-'})"
    with st.expander(f"👨‍🎓 {stu_label}", expanded=False):

        # 1) LOGBOOK + KOMEN
        st.markdown("### 📒 Logbook & Komen")
        with get_conn() as conn:
            df_logs = pd.read_sql_query(
                """SELECT log_id, entry_date, title, activities, outcomes, hours,
                          COALESCE(acad_comment,'') AS acad_comment
                   FROM logbook
                   WHERE student_id=? AND term_id=?
                   ORDER BY entry_date DESC""",
                conn, params=(stu_id, term_id)
            )
        st.caption(f"Jumlah entri: {len(df_logs)}")
        if df_logs.empty:
            st.info("Pelajar ini belum isi logbook.")
        else:
            st.dataframe(df_logs[["entry_date","title","hours","acad_comment"]], use_container_width=True)
            for _, rlog in df_logs.iterrows():
                with st.expander(f"Entri {rlog['entry_date']} — {rlog['title'] or '-'}"):
                    st.markdown("**Aktiviti**"); st.write(rlog["activities"] or "-")
                    st.markdown("**Hasil/Outcomes**"); st.write(rlog["outcomes"] or "-")
                    new_c = st.text_area("Komen (Akademik)", value=rlog["acad_comment"] or "", key=f"ac_{stu_id}_{rlog['log_id']}")
                    if st.button("Simpan Komen", key=f"btn_ac_{stu_id}_{rlog['log_id']}"):
                        with get_conn() as conn:
                            cur = conn.cursor()
                            cur.execute("""UPDATE logbook
                                           SET acad_comment=?, acad_commented_by=?, acad_commented_at=datetime('now')
                                           WHERE log_id=?""",
                                        (new_c, user['user_id'], int(rlog["log_id"])))
                            conn.commit()
                        st.success("Komen disimpan."); st.rerun()

        st.divider()

        # 2) FINAL REPORT (download jika wujud blob)
        st.markdown("### 📄 Laporan Akhir")
        with get_conn() as conn:
            df_rep = pd.read_sql_query(
                """SELECT id, file_name, uploaded_at, LENGTH(file_blob) AS blob_len
                   FROM final_reports WHERE student_id=? AND term_id=? ORDER BY uploaded_at DESC""",
                conn, params=(stu_id, term_id)
            )
        if df_rep.empty:
            st.info("Tiada muat naik Laporan Akhir untuk pelajar ini.")
        else:
            st.dataframe(df_rep[["file_name","uploaded_at","blob_len"]], use_container_width=True)
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""SELECT file_name, file_blob
                               FROM final_reports
                               WHERE student_id=? AND term_id=?
                               ORDER BY uploaded_at DESC LIMIT 1""",
                            (stu_id, term_id))
                f = cur.fetchone()
            if f and f[1]:
                st.download_button("⬇️ Muat Turun Laporan Akhir (terkini)", data=f[1],
                                   file_name=f[0] or "Laporan_Akhir.docx")
            else:
                st.info("Blob laporan tiada (repo simpan path sahaja).")

        st.divider()

        # 3) BLI-08 — PENILAIAN PENYELIA AKADEMIK
        st.markdown("### 📝 BLI-08 — Penilaian Akademik (0–100)")

        with get_conn() as conn:
            df_bli08 = pd.read_sql_query(
                """SELECT id, score_komunikasi, score_disiplin, score_kualiti, score_kehadiran, score_inisiatif,
                          komen_umum, total, submitted_at
                   FROM bli08_academic
                   WHERE student_user_id=? AND term_id=? AND acad_supervisor_id=?
                   ORDER BY id DESC LIMIT 1""",
                conn, params=(stu_id, term_id, user['user_id'])
            )
        pref = df_bli08.iloc[0] if not df_bli08.empty else None

        colA, colB, colC = st.columns(3)
        s1 = colA.number_input("Komunikasi (0–20)", 0.0, 20.0, float(pref["score_komunikasi"]) if pref is not None else 0.0, 1.0, key=f"s1_{stu_id}")
        s2 = colA.number_input("Disiplin (0–20)",   0.0, 20.0, float(pref["score_disiplin"]) if pref is not None else 0.0, 1.0, key=f"s2_{stu_id}")
        s3 = colB.number_input("Kualiti Kerja (0–30)", 0.0, 30.0, float(pref["score_kualiti"]) if pref is not None else 0.0, 1.0, key=f"s3_{stu_id}")
        s4 = colB.number_input("Kehadiran (0–15)",  0.0, 15.0, float(pref["score_kehadiran"]) if pref is not None else 0.0, 1.0, key=f"s4_{stu_id}")
        s5 = colC.number_input("Inisiatif (0–15)",  0.0, 15.0, float(pref["score_inisiatif"]) if pref is not None else 0.0, 1.0, key=f"s5_{stu_id}")
        komen = st.text_area("Komen umum", value=(pref["komen_umum"] if pref is not None else ""), key=f"km_{stu_id}")

        total = s1 + s2 + s3 + s4 + s5
        st.metric("Jumlah Markah", f"{total:.1f} / 100", key=f"mt_{stu_id}")

        colX, colY = st.columns(2)
        if colX.button("💾 Simpan Draf", key=f"draf_{stu_id}"):
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO bli08_academic(student_user_id, acad_supervisor_id, term_id,
                        score_komunikasi, score_disiplin, score_kualiti, score_kehadiran, score_inisiatif,
                        komen_umum, total, submitted_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?, NULL, datetime('now'))
                """, (stu_id, user['user_id'], term_id, s1, s2, s3, s4, s5, komen, total))
                conn.commit()
            st.success("Draf disimpan.")
            st.rerun()

        if colY.button("✅ Hantar (Muktamad)", key=f"hantar_{stu_id}"):
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO bli08_academic(student_user_id, acad_supervisor_id, term_id,
                        score_komunikasi, score_disiplin, score_kualiti, score_kehadiran, score_inisiatif,
                        komen_umum, total, submitted_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?, datetime('now'), datetime('now'))
                """, (stu_id, user['user_id'], term_id, s1, s2, s3, s4, s5, komen, total))
                conn.commit()
            st.success("Penilaian dihantar.")
            st.rerun()

st.divider()
if st.button("Log Keluar"): st.session_state.auth=None; st.rerun()

# pages/3_Penyelia_Industri.py
import os, json
import pandas as pd
import streamlit as st
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

# ------------------------------------------------------------
# Setup & Init
# ------------------------------------------------------------
st.set_page_config(page_title="Penyelia Industri", page_icon="🏭", layout="wide")
st.title("Portal Penyelia Industri")

try:
    # gunakan skrip init yang sama seperti app lain
    ensure_db(os.path.join(os.path.dirname(__file__), "..", "init_mytimes_fyp.sql"))
except Exception as e:
    st.error(f"Ralat DB: {e}")
    st.stop()

# ------------------------------------------------------------
# Guard util
# ------------------------------------------------------------
def require_role(roles):
    aut = st.session_state.get("auth")
    if not aut or aut.get("role_name") not in roles:
        st.error("Akses tidak dibenarkan. Sila log masuk sebagai Penyelia Industri.")
        st.stop()

# ------------------------------------------------------------
# Login
# ------------------------------------------------------------
if "auth" not in st.session_state:
    st.session_state.auth = None

if not st.session_state.auth:
    st.subheader("Log Masuk")
    with st.form("login_ind"):
        email = st.text_input("Emel")
        password = st.text_input("Kata Laluan", type="password")
        submitted = st.form_submit_button("Log Masuk")
    if submitted:
        user = auth_email_or_sid(email, password)
        if not user or user.get("role_name") != "ind_sv":
            st.error("Akaun bukan Penyelia Industri / salah maklumat.")
        else:
            st.session_state.auth = user
            st.rerun()
    st.stop()

# ------------------------------------------------------------
# Role guard & user info
# ------------------------------------------------------------
require_role(["ind_sv"])
user = st.session_state.auth
st.success(f"Log masuk sebagai {user['full_name']}")

# ------------------------------------------------------------
# DB bootstrap (pastikan kolum yang diperlukan wujud)
# ------------------------------------------------------------
with get_conn() as conn:
    cur = conn.cursor()

    # Jadual BLI-05 (jika belum wujud)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bli05_industry(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_user_id INTEGER NOT NULL,
            ind_supervisor_id INTEGER NOT NULL,
            term_id INTEGER NOT NULL,
            items_json TEXT,                 -- simpan skor item (dictionary)
            js_total REAL DEFAULT 0,         -- jumlah skor mentah (JS)
            weighted_30 REAL DEFAULT 0,      -- markah ditimbang ke 30%
            overall_decision TEXT,           -- LULUS / GAGAL / TIDAK LENGKAP
            comments TEXT,
            submitted_at TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Pastikan kolum komen industri pada logbook ada
    cur.execute("PRAGMA table_info(logbook)")
    log_cols = {r[1] for r in cur.fetchall()}
    if "ind_comment" not in log_cols:
        cur.execute("ALTER TABLE logbook ADD COLUMN ind_comment TEXT")
    if "ind_commented_by" not in log_cols:
        cur.execute("ALTER TABLE logbook ADD COLUMN ind_commented_by INTEGER")
    if "ind_commented_at" not in log_cols:
        cur.execute("ALTER TABLE logbook ADD COLUMN ind_commented_at TEXT")

    conn.commit()

# ------------------------------------------------------------
# Term semasa
# ------------------------------------------------------------
with get_conn() as conn:
    tlabel = term_label(conn)
    df_term = pd.read_sql_query("SELECT term_id FROM terms ORDER BY term_id DESC LIMIT 1", conn)
term_id = int(df_term.iloc[0]["term_id"]) if not df_term.empty else None

cols_top = st.columns(3)
cols_top[0].metric("Sesi", tlabel or "-")
if not term_id:
    st.warning("Tiada term aktif.")
    st.stop()

# ------------------------------------------------------------
# Dapatkan senarai pelajar di bawah seliaan industri pengguna ini
# (guna jadual supervisor_assignments seperti yang dinyatakan)
# ------------------------------------------------------------
with get_conn() as conn:
    df_stu = pd.read_sql_query(
        """
        SELECT u.user_id, u.full_name, u.student_id, u.program_code
        FROM supervisor_assignments sa
        JOIN users u ON u.user_id = sa.student_user_id
        WHERE sa.term_id=? AND sa.ind_sv_user_id=?
        ORDER BY u.full_name
        """,
        conn, params=(term_id, user['user_id'])
    )

if df_stu.empty:
    st.info("Tiada pelajar di bawah jagaan anda.")
    if st.button("Log Keluar"): st.session_state.auth = None; st.rerun()
    st.stop()

# Statistik ringkas
with get_conn() as conn:
    assigned = len(df_stu)
    reported = one(conn,
        """
        SELECT COUNT(1)
        FROM reporting_in r
        JOIN supervisor_assignments sa ON sa.student_user_id=r.student_id AND sa.term_id=r.term_id
        WHERE sa.ind_sv_user_id=? AND sa.term_id=?
        """,
        (user['user_id'], term_id)
    ) or 0
    bli05_done = one(conn,
        "SELECT COUNT(1) FROM bli05_industry WHERE ind_supervisor_id=? AND term_id=?",
        (user['user_id'], term_id)
    ) or 0

cols_mid = st.columns(3)
cols_mid[0].metric("Pelajar di bawah anda", f"{assigned}")
cols_mid[1].metric("Lapor Diri (BLI-04)", f"{reported}")
cols_mid[2].metric("BLI-05 dihantar", f"{bli05_done}")

st.subheader("Pelajar Diselia (Industri)")
st.dataframe(df_stu, use_container_width=True)
st.divider()

# ------------------------------------------------------------
# Pilih seorang pelajar (default cuba pilih Ali jika ada)
# ------------------------------------------------------------
options = [
    (int(r.user_id), f"{r.student_id} — {r.full_name} ({r.program_code or '-'})")
    for _, r in df_stu.iterrows()
]
default_idx = 0
for i, (_, label) in enumerate(options):
    if "ali" in label.lower():   # auto-pilih Ali Bin Abu jika ada
        default_idx = i
        break

sel_stu = st.selectbox("Pilih pelajar untuk semakan & pemarkahan:", options=options, index=default_idx, format_func=lambda x: x[1], key="sel_ind_student")
stu_id = sel_stu[0]
stu_label = sel_stu[1]

with st.expander(f"👷 {stu_label}", expanded=True):
    tab_log, tab_bli = st.tabs(["📒 Logbook", "📝 BLI-05 (Penyelia Industri)"])

    # =========================================================
    # TAB: LOGBOOK (komen industri)
    # =========================================================
    with tab_log:
        with get_conn() as conn:
            df_logs = pd.read_sql_query(
                """
                SELECT log_id, entry_date, title, activities, outcomes, hours,
                       COALESCE(ind_comment,'') AS ind_comment
                FROM logbook
                WHERE student_id=? AND term_id=?
                ORDER BY entry_date DESC
                """,
                conn, params=(stu_id, term_id)
            )
        st.caption(f"Total entri: {len(df_logs)}")
        if df_logs.empty:
            st.info("Pelajar ini belum isi logbook.")
        else:
            st.dataframe(df_logs[["entry_date","title","hours","ind_comment"]], use_container_width=True)

            # Pilih satu entri untuk butiran & komen (elak expander bertingkat banyak)
            options_logs = [
                (int(r.log_id), f"{r.entry_date} — {r.title or '-'}")
                for r in df_logs.itertuples(index=False)
            ]
            sel_log = st.selectbox("Pilih entri untuk lihat butiran", options=options_logs, format_func=lambda x: x[1], key=f"sel_log_{stu_id}")
            if sel_log:
                sel_log_id = sel_log[0]
                rlog = df_logs[df_logs["log_id"] == sel_log_id].iloc[0]

                box = st.container()
                with box:
                    st.markdown(f"**Entri:** {rlog['entry_date']} — {rlog['title'] or '-'}")
                    st.markdown("**Aktiviti**")
                    st.write(rlog["activities"] or "-")
                    st.markdown("**Hasil/Outcomes**")
                    st.write(rlog["outcomes"] or "-")

                    new_c = st.text_area("Komen (Industri)", value=rlog["ind_comment"] or "", key=f"ind_c_{int(rlog['log_id'])}")
                    if st.button("💾 Simpan Komen (Industri)", key=f"btn_ind_{int(rlog['log_id'])}"):
                        with get_conn() as conn:
                            cur = conn.cursor()
                            cur.execute("""
                                UPDATE logbook
                                SET ind_comment=?, ind_commented_by=?, ind_commented_at=datetime('now')
                                WHERE log_id=?""",
                                (new_c, user['user_id'], int(rlog["log_id"]))
                            )
                            conn.commit()
                        st.success("Komen industri disimpan.")
                        st.rerun()

    # =========================================================
    # TAB: BLI-05 (ikut borang UiTM, skala 1–5, 30%)
    # =========================================================
    with tab_bli:
        st.info("Penilaian mengikut borang **BLI-05** (skala 1–5 untuk setiap kriteria; markah akhir ditimbang ke 30%).")
        # Cuba load rekod terakhir untuk prefill
        with get_conn() as conn:
            df_last = pd.read_sql_query(
                """
                SELECT items_json, js_total, weighted_30, overall_decision, comments, submitted_at
                FROM bli05_industry
                WHERE student_user_id=? AND term_id=? AND ind_supervisor_id=?
                ORDER BY id DESC LIMIT 1
                """,
                conn, params=(stu_id, term_id, user['user_id'])
            )
        last_items = {}
        last_comments = ""
        last_decision = None
        if not df_last.empty:
            try:
                last_items = json.loads(df_last.iloc[0]["items_json"] or "{}")
            except Exception:
                last_items = {}
            last_comments = df_last.iloc[0]["comments"] or ""
            last_decision = df_last.iloc[0]["overall_decision"] or None

        # Senarai kriteria (rujuk borang)
        # Nota: Dokumen menunjukkan 9 kriteria bertanda 1–5 (dengan perincian pada item 8),
        # jadi kita jadikan 9 item utama 1–5. JS maks = 45, markah 30% = (JS/45)*30
        items = [
            (1, "Keupayaan mental (kecerdasan & keupayaan am)"),
            (2, "Keupayaan fizikal (ketahanan kerja lapangan)"),
            (3, "Kebolehpercayaan / Reliabiliti"),
            (4, "Tanggungjawab terhadap tugasan / aset / rekod / peralatan"),
            (5, "Kemahiran bergaul & berkomunikasi"),
            (6, "Kerja berpasukan"),
            (7, "Inisiatif / Berdikari (perlukan sedikit penyeliaan)"),
            (8, "Penyesuaian diri (masa kerja / kesediaan OT / reaksi kecemasan / patuh peraturan)"),
            (9, "Penilaian keseluruhan sebagai pekerja")
        ]

        scores = {}
        for no, label in items:
            key = f"bli05_{stu_id}_{no}"
            default = int(last_items.get(str(no), 3))
            idx = [1,2,3,4,5].index(default) if default in [1,2,3,4,5] else 2
            scores[str(no)] = st.radio(
                f"{no}. {label}", options=[1,2,3,4,5],
                horizontal=True, index=idx, key=key
            )

        js_total = sum(scores.values())         # maks 45
        weighted_30 = (js_total / 45.0) * 30.0  # disukat ke 30%

        colA, colB = st.columns(2)
        with colA:
            st.metric("Jumlah Skor (JS)", f"{js_total} / 45")
        with colB:
            st.metric("Markah Ditimbang (30%)", f"{weighted_30:.2f} / 30")

        decision = st.selectbox(
            "Keputusan", ["LULUS","GAGAL","TIDAK LENGKAP"],
            index=(["LULUS","GAGAL","TIDAK LENGKAP"].index(last_decision) if last_decision in ["LULUS","GAGAL","TIDAK LENGKAP"] else 0),
            key=f"dec_{stu_id}"
        )
        comments = st.text_area("Komen tambahan", value=last_comments, key=f"cm_{stu_id}")

        details_json = json.dumps(scores, ensure_ascii=False)

        colX, colY = st.columns(2)
        if colX.button("💾 Simpan Draf (BLI-05)", key=f"draf05_{stu_id}"):
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO bli05_industry(
                        student_user_id, ind_supervisor_id, term_id,
                        items_json, js_total, weighted_30, overall_decision, comments,
                        submitted_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?, ?, NULL, datetime('now'))
                """, (stu_id, user['user_id'], term_id,
                      details_json, js_total, weighted_30, decision, comments))
                conn.commit()
            st.success("Draf BLI-05 disimpan.")
            st.rerun()

        if colY.button("✅ Hantar (Muktamad BLI-05)", key=f"hantar05_{stu_id}"):
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO bli05_industry(
                        student_user_id, ind_supervisor_id, term_id,
                        items_json, js_total, weighted_30, overall_decision, comments,
                        submitted_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?, ?, datetime('now'), datetime('now'))
                """, (stu_id, user['user_id'], term_id,
                      details_json, js_total, weighted_30, decision, comments))
                conn.commit()
            st.success("Penilaian BLI-05 dihantar.")
            st.rerun()

# ------------------------------------------------------------
# Logout
# ------------------------------------------------------------
st.divider()
if st.button("Log Keluar"):
    st.session_state.auth = None
    st.rerun()

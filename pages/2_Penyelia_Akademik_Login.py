# pages/2_Penyelia_Akademik_Dashboard.py
import os
import json
import pandas as pd
import streamlit as st
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

# ----------------------------- Setup -----------------------------
st.set_page_config(page_title="Penyelia Akademik", page_icon="📘", layout="wide")
st.title("Dashboard Penyelia Akademik")

try:
    ensure_db(os.path.join(os.path.dirname(__file__), "..", "init_mytimes_fyp.sql"))
except Exception as e:
    st.error(f"Ralat DB: {e}")
    st.stop()

# ----------------------- Util & Guard ---------------------------
def require_role(roles):
    aut = st.session_state.get("auth")
    if not aut or aut.get("role_name") not in roles:
        st.error("Akses tidak dibenarkan. Sila log masuk sebagai Penyelia Akademik.")
        st.stop()

def radio_default(key, default):
    """Helper untuk dapatkan nilai default radio yang stabil."""
    return st.session_state.get(key, default)

# --------------------------- Login ------------------------------
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
        if not user or user.get("role_name") != "acad_sv":
            st.error("Akaun bukan Penyelia Akademik / maklumat log masuk tidak sah.")
        else:
            st.session_state.auth = user
            st.rerun()
    st.stop()

# ------------------------ Role Check ----------------------------
require_role(["acad_sv"])
user = st.session_state.auth
st.success(f"Log masuk sebagai {user['full_name']}")

# ------------------------ DB Bootstrap --------------------------
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
            score_komunikasi REAL DEFAULT 0,   -- guna utk CLO1 (30%)
            score_disiplin REAL DEFAULT 0,     -- guna utk CLO5 Logbook (10%)
            score_kualiti REAL DEFAULT 0,      -- guna utk CLO4 (30%)
            score_kehadiran REAL DEFAULT 0,    -- tidak digunakan di versi ini
            score_inisiatif REAL DEFAULT 0,    -- tidak digunakan di versi ini
            komen_umum TEXT,                   -- simpan JSON butiran BLI-08 + komen
            total REAL DEFAULT 0,              -- jumlah 70% utk komponen ini
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
    # Tambah kolum komen logbook jika tiada
    cur.execute("PRAGMA table_info(logbook)")
    cols = {r[1] for r in cur.fetchall()}
    if "acad_comment" not in cols:
        cur.execute("ALTER TABLE logbook ADD COLUMN acad_comment TEXT")
    if "acad_commented_by" not in cols:
        cur.execute("ALTER TABLE logbook ADD COLUMN acad_commented_by INTEGER")
    if "acad_commented_at" not in cols:
        cur.execute("ALTER TABLE logbook ADD COLUMN acad_commented_at TEXT")
    conn.commit()

# --------------------------- Term Now ---------------------------
with get_conn() as conn:
    tlabel = term_label(conn)
    df_term = pd.read_sql_query(
        "SELECT term_id FROM terms ORDER BY term_id DESC LIMIT 1", conn
    )
term_id = int(df_term.iloc[0]["term_id"]) if not df_term.empty else None
st.caption(f"**Sesi:** {tlabel or '-'}")
if not term_id:
    st.warning("Tiada term aktif.")
    st.stop()

# ---------------------- Senarai Pelajar -------------------------
with get_conn() as conn:
    df_stu = pd.read_sql_query(
        """
        SELECT u.user_id, u.full_name, u.student_id, u.program_code
        FROM supervisor_assignments sa
        JOIN users u ON u.user_id = sa.student_user_id
        WHERE sa.term_id=? AND sa.acad_sv_user_id=?
        ORDER BY u.full_name
        """,
        conn, params=(term_id, user['user_id'])
    )

if df_stu.empty:
    st.info("Tiada pelajar di bawah jagaan anda.")
    if st.button("Log Keluar"):
        st.session_state.auth = None
        st.rerun()
    st.stop()

st.subheader("Pelajar Diselia")

# Carian pantas & pemilih pelajar (fokus satu pelajar)
col_find, col_sel = st.columns([1, 2])
with col_find:
    q = st.text_input("Cari nama/ID", value="", help="Taip sebahagian nama atau nombor matrik")
df_view = df_stu[
    df_stu.apply(lambda r: q.lower() in (f"{r['student_id']} {r['full_name']}".lower()), axis=1)
] if q else df_stu

options = [
    (int(r.user_id), f"{r.student_id} — {r.full_name} ({r.program_code or '-'})")
    for _, r in df_view.iterrows()
]
if not options:
    st.warning("Tiada padanan carian.")
    st.stop()

with col_sel:
    default_idx = 0
    for i, (_, label) in enumerate(options):
        if "nurhidayah" in label.lower():
            default_idx = i
            break
    sel_stu = st.selectbox("Pilih pelajar", options=options, index=default_idx, format_func=lambda x: x[1], key="sel_pelajar")

st.dataframe(df_view, use_container_width=True)
st.divider()

# -------------------- Panel Pelajar (Tabs) ----------------------
stu_id = sel_stu[0]
stu_label = sel_stu[1]
with st.expander(f"👨‍🎓 {stu_label}", expanded=True):
    tab_log, tab_rep, tab_bli = st.tabs(["📒 Logbook", "📄 Laporan Akhir", "📝 BLI-08 (Penyelia Akademik)"])

    # ======================= TAB: LOGBOOK =======================
    with tab_log:
        with get_conn() as conn:
            df_logs = pd.read_sql_query(
                """
                SELECT log_id, entry_date, title, activities, outcomes, hours,
                       COALESCE(acad_comment,'') AS acad_comment
                FROM logbook
                WHERE student_id=? AND term_id=?
                ORDER BY entry_date DESC
                """,
                conn, params=(stu_id, term_id)
            )

        st.caption(f"Jumlah entri: {len(df_logs)}")
        if df_logs.empty:
            st.info("Pelajar ini belum isi logbook.")
        else:
            st.dataframe(df_logs[["entry_date","title","hours","acad_comment"]], use_container_width=True)

            # Pilih satu entri untuk lihat butiran dan beri komen
            options_logs = [
                (int(r.log_id), f"{r.entry_date} — {r.title or '-'}")
                for r in df_logs.itertuples(index=False)
            ]
            sel_log = st.selectbox(
                "Pilih entri untuk lihat butiran",
                options=options_logs,
                format_func=lambda x: x[1],
                key=f"sel_log_{stu_id}"
            )
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

                    new_c = st.text_area(
                        "Komen (Akademik)",
                        value=rlog["acad_comment"] or "",
                        key=f"ac_{stu_id}_{int(rlog['log_id'])}"
                    )
                    if st.button("💾 Simpan Komen", key=f"btn_ac_{stu_id}_{int(rlog['log_id'])}"):
                        with get_conn() as conn:
                            cur = conn.cursor()
                            cur.execute(
                                """
                                UPDATE logbook
                                SET acad_comment=?, acad_commented_by=?, acad_commented_at=datetime('now')
                                WHERE log_id=?
                                """,
                                (new_c, user['user_id'], int(rlog["log_id"]))
                            )
                            conn.commit()
                        st.success("Komen disimpan.")
                        st.rerun()

    # ==================== TAB: LAPORAN AKHIR ====================
    with tab_rep:
        with get_conn() as conn:
            df_rep = pd.read_sql_query(
                """
                SELECT id, file_name, uploaded_at, LENGTH(file_blob) AS blob_len
                FROM final_reports
                WHERE student_id=? AND term_id=?
                ORDER BY uploaded_at DESC
                """,
                conn, params=(stu_id, term_id)
            )

        if df_rep.empty:
            st.info("Tiada muat naik Laporan Akhir untuk pelajar ini.")
        else:
            st.dataframe(df_rep[["file_name","uploaded_at","blob_len"]], use_container_width=True)

            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT file_name, file_blob
                    FROM final_reports
                    WHERE student_id=? AND term_id=?
                    ORDER BY uploaded_at DESC LIMIT 1
                    """,
                    (stu_id, term_id)
                )
                f = cur.fetchone()
            if f and f[1]:
                st.download_button("⬇️ Muat Turun Laporan Akhir (terkini)", data=f[1],
                                   file_name=f[0] or "Laporan_Akhir.docx")
            else:
                st.info("Blob laporan tiada (repo simpan path sahaja).")

    # ===================== TAB: BLI-08 (UiTM) ===================
    with tab_bli:
        st.info("Penilaian ini mengikut borang BLI-08 (skala 1–5 & 1–2) dan pemberat CLO sebagaimana borang rasmi.")
        # Cuba muat semula nilai terakhir untuk prefill
        with get_conn() as conn:
            df_bli_last = pd.read_sql_query(
                """
                SELECT id, komen_umum, score_komunikasi, score_disiplin, score_kualiti, total, submitted_at
                FROM bli08_academic
                WHERE student_user_id=? AND term_id=? AND acad_supervisor_id=?
                ORDER BY id DESC LIMIT 1
                """,
                conn, params=(stu_id, term_id, user['user_id'])
            )
        pref_json = {}
        if not df_bli_last.empty and df_bli_last.iloc[0]["komen_umum"]:
            try:
                # komen_umum mungkin ada prefix "[BLI08]\n"
                raw = df_bli_last.iloc[0]["komen_umum"]
                start = raw.find("{")
                if start >= 0:
                    pref_json = json.loads(raw[start:])
            except Exception:
                pref_json = {}

        # -------- CLO1 (30%) : skala 1–5, 6 item --------
        st.subheader("CLO1 — Penilaian Laporan Akhir (30%)")
        clo1_items = [
            "Pengenalan latihan industri",
            "Latar belakang organisasi & tugasan",
            "Laporan aktiviti (organisasi/jabatan yang ditempatkan)",
            "Tugasan/Projek (permasalahan, objektif, skop)",
            "Keberkesanan tugasan/projek kepada organisasi/komuniti",
            "Kaedah kerja (pendekatan/kaedah/penyampaian maklumat)"
        ]
        clo1_scores = {}
        for i, label in enumerate(clo1_items, start=1):
            key_r = f"clo1_{stu_id}_{i}"
            default = int(pref_json.get("CLO1", {}).get(f"CLO1_{i}", 3))
            clo1_scores[f"CLO1_{i}"] = st.radio(
                f"{i}. {label}",
                options=[1,2,3,4,5],
                horizontal=True,
                index=[1,2,3,4,5].index(default),
                key=key_r
            )
        clo1_raw = sum(clo1_scores.values())          # maks 30
        clo1_weighted = clo1_raw / 30 * 30            # = clo1_raw

        st.caption(f"Jumlah CLO1: {clo1_raw}/30 → **{clo1_weighted:.1f} markah (30%)**")
        st.divider()

        # -------- CLO5 / Logbook (10%) : skala 1–2, 5 item --------
        st.subheader("CLO5 — Penilaian Buku Log (10%)")
        clo5_items = [
            "Kekemasan catatan dalam buku log",
            "Keupayaan menterjemah tugasan harian/mingguan ke buku log",
            "Penulisan dan tatabahasa",
            "Kandungan buku log secara keseluruhan",
            "Disemak oleh penyelia industri secara berkala"
        ]
        clo5_scores = {}
        for i, label in enumerate(clo5_items, start=1):
            key_r = f"clo5_{stu_id}_{i}"
            default = int(pref_json.get("CLO5", {}).get(f"CLO5_{i}", 1))
            clo5_scores[f"CLO5_{i}"] = st.radio(
                f"{i}. {label}",
                options=[1,2],
                horizontal=True,
                index=[1,2].index(default),
                key=key_r
            )
        clo5_raw = sum(clo5_scores.values())          # maks 10
        clo5_weighted = clo5_raw / 10 * 10            # = clo5_raw
        st.caption(f"Jumlah CLO5 (Logbook): {clo5_raw}/10 → **{clo5_weighted:.1f} markah (10%)**")
        st.divider()

        # -------- CLO4 (30%) : skala 1–2, 5 item; gandaan 3 --------
        st.subheader("CLO4 — Penilaian Laporan Akhir (30%)")
        clo4_items = [
            "Maklumat bergambar, carta & lukisan berkaitan",
            "Kelebihan daripada tugasan latihan industri",
            "Kesimpulan & cadangan penambahbaikan",
            "Persembahan laporan (format/konsisten/bahasa jelas)",
            "Kekemasan format seperti ditetapkan penyelia"
        ]
        clo4_scores = {}
        for i, label in enumerate(clo4_items, start=1):
            key_r = f"clo4_{stu_id}_{i}"
            default = int(pref_json.get("CLO4", {}).get(f"CLO4_{i}", 1))
            clo4_scores[f"CLO4_{i}"] = st.radio(
                f"{i}. {label}",
                options=[1,2],
                horizontal=True,
                index=[1,2].index(default),
                key=key_r
            )
        clo4_raw = sum(clo4_scores.values())          # maks 10
        clo4_weighted = clo4_raw / 10 * 30            # skala ke 30%
        st.caption(f"Jumlah CLO4: {clo4_raw}/10 → **{clo4_weighted:.1f} markah (30%)**")
        st.divider()

        # -------- Jumlah set komponen (70%) --------
        total_70 = clo1_weighted + clo5_weighted + clo4_weighted
        colA, colB = st.columns(2)
        with colA:
            st.metric("Jumlah BLI-08 (set ini)", f"{total_70:.1f} / 70")
        with colB:
            st.progress(min(max(total_70/70.0, 0.0), 1.0))

        komen_bli = st.text_area(
            "Komen umum (BLI-08)",
            value=(st.session_state.get(f"komen_bli_{stu_id}", "")),
            key=f"komen_bli_{stu_id}"
        )

        details_json = json.dumps({
            "CLO1": clo1_scores,
            "CLO5": clo5_scores,
            "CLO4": clo4_scores,
            "Totals": {
                "CLO1_raw": clo1_raw, "CLO1_weighted": clo1_weighted,
                "CLO5_raw": clo5_raw, "CLO5_weighted": clo5_weighted,
                "CLO4_raw": clo4_raw, "CLO4_weighted": clo4_weighted,
                "Grand_70": total_70
            }
        }, ensure_ascii=False)

        colX, colY = st.columns(2)
        if colX.button("💾 Simpan Draf (BLI-08)", key=f"draf_bli_{stu_id}"):
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO bli08_academic(
                        student_user_id, acad_supervisor_id, term_id,
                        score_komunikasi, score_disiplin, score_kualiti, score_kehadiran, score_inisiatif,
                        komen_umum, total, submitted_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?, NULL, datetime('now'))
                """, (
                    stu_id, user['user_id'], term_id,
                    clo1_weighted,      # simpan di score_komunikasi
                    clo5_weighted,      # simpan di score_disiplin
                    clo4_weighted,      # simpan di score_kualiti
                    0, 0,
                    f"[BLI08]\n{details_json}\n\n{komen_bli}",
                    total_70
                ))
                conn.commit()
            st.success("Draf BLI-08 disimpan.")
            st.rerun()

        if colY.button("✅ Hantar (Muktamad BLI-08)", key=f"hantar_bli_{stu_id}"):
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO bli08_academic(
                        student_user_id, acad_supervisor_id, term_id,
                        score_komunikasi, score_disiplin, score_kualiti, score_kehadiran, score_inisiatif,
                        komen_umum, total, submitted_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?, datetime('now'), datetime('now'))
                """, (
                    stu_id, user['user_id'], term_id,
                    clo1_weighted,
                    clo5_weighted,
                    clo4_weighted,
                    0, 0,
                    f"[BLI08]\n{details_json}\n\n{komen_bli}",
                    total_70
                ))
                conn.commit()
            st.success("Penilaian BLI-08 dihantar.")
            st.rerun()

# --------------------------- Footer -----------------------------
st.divider()
if st.button("Log Keluar"):
    st.session_state.auth = None
    st.rerun()

# pages/1_Pelajar_Login.py
import os
import datetime
from datetime import date, datetime as dt
import pandas as pd
import streamlit as st

from lib.common import (
    ensure_db, auth_email_or_sid, ROLES,
    get_conn, one, term_label, render_docx_from_template
)

# -------------------- Setup & DB init --------------------
st.set_page_config(page_title="Log Masuk Pelajar", page_icon="🎓", layout="wide")
st.title("Log Masuk Pelajar")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_PATH = os.path.join(BASE_DIR, "..", "init_mytimes_fyp.sql")

try:
    ensure_db(SQL_PATH)  # make sure DB exists and schema is loaded
except Exception as e:
    st.error(f"Ralat DB: {e}")
    st.stop()

if "auth" not in st.session_state:
    st.session_state.auth = None

# -------------------- Login --------------------
if not st.session_state.auth:
    with st.form("login"):
        login_text = st.text_input("Emel / No. Pelajar")
        password = st.text_input("Kata Laluan", type="password")
        submitted = st.form_submit_button("Log Masuk")
    if submitted:
        user = auth_email_or_sid(login_text, password)
        if not user:
            st.error("Maklumat log masuk tidak sah.")
        elif user["role_name"] != "student":
            st.error("Akaun ini bukan peranan Pelajar.")
        else:
            st.session_state.auth = user
            st.rerun()
    st.stop()

# -------------------- Selepas login --------------------
user = st.session_state.auth
st.success(f"Log masuk sebagai {user['full_name']} ({user.get('program_code') or '-'})")

# Metrics ringkas
with get_conn() as conn:
    tlabel = term_label(conn)
    bli01 = one(conn, "SELECT COUNT(1) FROM bli01 WHERE student_id=?", (user['user_id'],))
    bli02 = one(conn, "SELECT COUNT(1) FROM bli02_responses WHERE student_id=?", (user['user_id'],))
    plc   = one(conn, "SELECT COUNT(1) FROM placements WHERE student_id=?", (user['user_id'],))
    repin = one(conn, "SELECT COUNT(1) FROM reporting_in WHERE student_id=?", (user['user_id'],))
    logs  = one(conn, "SELECT COUNT(1) FROM logbook WHERE student_id=?", (user['user_id'],))
    rep   = one(conn, "SELECT COUNT(1) FROM final_reports WHERE student_id=?", (user['user_id'],))
    ind   = one(conn, "SELECT COUNT(1) FROM bli05_industry WHERE student_id=?", (user['user_id'],))
    aca   = one(conn, "SELECT COUNT(1) FROM bli08_academic WHERE student_id=?", (user['user_id'],))

col1, col2, col3 = st.columns(3)
col1.metric("Sesi", tlabel)
col2.metric("BLI-01", "✅" if bli01 else "❌")
col3.metric("BLI-02 (upload)", "✅" if bli02 else "❌")
col4, col5, col6 = st.columns(3)
col4.metric("BLI-03", "✅" if plc else "❌")
col5.metric("BLI-04", "✅" if repin else "❌")
col6.metric("Logbook Mingguan", f"{logs} entri")
col7, col8, col9 = st.columns(3)
col7.metric("Laporan Akhir", "✅" if rep else "❌")
col8.metric("BLI-05 (Industri)", "✅" if ind else "❌")
col9.metric("BLI-08 (Akademik)", "✅" if aca else "❌")

st.divider()

# -------------------- Borang Atas Talian --------------------
st.markdown("## 📝 Borang Atas Talian")
tabs = st.tabs([
    "BLI-01 Maklumat Peribadi",
    "BLI-03 Pengesahan Penempatan",
    "BLI-04 Lapor Diri"
])

# Dapatkan term semasa
with get_conn() as conn:
    term_id = pd.read_sql_query(
        "SELECT term_id FROM terms ORDER BY term_id DESC LIMIT 1", conn
    ).iloc[0]["term_id"]

# --- BLI-01 (Maklumat Peribadi, online)
with tabs[0]:
    st.caption("Isi maklumat peribadi. Boleh kemas kini sebelum tarikh tutup.")
    with get_conn() as conn:
        df_bli01 = pd.read_sql_query(
            "SELECT data_json FROM bli01 WHERE student_id=? AND term_id=? ORDER BY id DESC LIMIT 1",
            conn, params=(user['user_id'], term_id)
        )
    data_prefill = {}
    if not df_bli01.empty and df_bli01["data_json"].iloc[0]:
        try:
            import json
            data_prefill = json.loads(df_bli01["data_json"].iloc[0])
        except Exception:
            data_prefill = {}

    with st.form("form_bli01"):
        colA, colB = st.columns(2)
        nama    = colA.text_input("Nama Penuh", value=data_prefill.get("nama", user["full_name"]))
        no_ic   = colA.text_input("No. IC", value=data_prefill.get("no_ic", ""))
        no_tel  = colA.text_input("No. Telefon", value=data_prefill.get("no_tel", ""))
        alamat  = colB.text_area("Alamat Surat-Menyurat", value=data_prefill.get("alamat", ""))
        program = colB.text_input("Kod Program", value=data_prefill.get("program", user.get("program_code") or ""))
        guardian     = st.text_input("Nama Penjaga/Waris", value=data_prefill.get("guardian", ""))
        guardian_tel = st.text_input("Telefon Penjaga/Waris", value=data_prefill.get("guardian_tel", ""))
        hantar_bli01 = st.form_submit_button("Simpan BLI-01")

    if hantar_bli01:
        import json
        payload = {
            "nama": nama, "no_ic": no_ic, "no_tel": no_tel, "alamat": alamat,
            "program": program, "guardian": guardian, "guardian_tel": guardian_tel,
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds")
        }
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO bli01(student_id, term_id, submitted_at, data_json)
                VALUES (?,?,datetime('now'),?)
            """, (user["user_id"], term_id, json.dumps(payload)))
            conn.commit()
        st.success("BLI-01 disimpan.")
        st.rerun()

# --- BLI-03 (Pengesahan Penempatan, online)
with tabs[1]:
    st.caption("Isi butiran penempatan praktikal/industri.")
    with get_conn() as conn:
        df_plc = pd.read_sql_query("""
            SELECT org_name, address, contact_person, contact_email, contact_phone
            FROM placements
            WHERE student_id=? AND term_id=?
            ORDER BY id DESC LIMIT 1
        """, conn, params=(user["user_id"], term_id))
    plc = df_plc.iloc[0].to_dict() if not df_plc.empty else {}

    with st.form("form_bli03"):
        org_name = st.text_input("Nama Organisasi", value=plc.get("org_name", ""))
        org_addr = st.text_area("Alamat Organisasi", value=plc.get("address", ""))
        contact_person = st.text_input("Penyelia Industri (Nama)", value=plc.get("contact_person", ""))
        contact_email  = st.text_input("Emel Penyelia Industri", value=plc.get("contact_email", ""))
        contact_phone  = st.text_input("Telefon Penyelia Industri", value=plc.get("contact_phone", ""))
        hantar_bli03   = st.form_submit_button("Simpan BLI-03")

    if hantar_bli03:
        if not org_name:
            st.error("Nama organisasi wajib diisi.")
        else:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO placements
                    (student_id, org_name, address, contact_person, contact_email, contact_phone, term_id, created_at)
                    VALUES (?,?,?,?,?,?,?, datetime('now'))
                """, (user["user_id"], org_name, org_addr, contact_person, contact_email, contact_phone, term_id))
                conn.commit()
            st.success("BLI-03 disimpan.")
            st.rerun()

# --- BLI-04 (Lapor Diri, online)
with tabs[2]:
    st.caption("Sahkan lapor diri di organisasi (sekali untuk sesi ini).")
    with get_conn() as conn:
        done = pd.read_sql_query(
            "SELECT COUNT(1) AS c FROM reporting_in WHERE student_id=? AND term_id=?",
            conn, params=(user["user_id"], term_id)
        )["c"].iloc[0] > 0
    if done:
        st.success("Sudah lapor diri. Terima kasih!")
    else:
        if st.button("Saya sahkan sudah Lapor Diri (BLI-04)"):
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO reporting_in(student_id, term_id, reported_at)
                    VALUES (?,?, datetime('now'))
                """, (user["user_id"], term_id))
                conn.commit()
            st.success("BLI-04 direkodkan.")
            st.rerun()

st.divider()

# -------------------- Logbook Mingguan --------------------
st.markdown("## 📒 Logbook Mingguan")

with get_conn() as conn:
    df_term = pd.read_sql_query(
        "SELECT term_id, session_label, start_date FROM terms ORDER BY term_id DESC LIMIT 1", conn
    )
term_start = None
try:
    if df_term.iloc[0]["start_date"]:
        term_start = dt.strptime(df_term.iloc[0]["start_date"], "%Y-%m-%d").date()
except Exception:
    term_start = None

with get_conn() as conn:
    df_logs = pd.read_sql_query("""
        SELECT log_id, entry_date, title, activities, outcomes, hours,
               COALESCE(acad_comment,'') AS acad_comment,
               COALESCE(ind_comment,'')  AS ind_comment
        FROM logbook
        WHERE student_id=? AND term_id=?
        ORDER BY entry_date DESC
    """, conn, params=(user["user_id"], term_id))

with st.form("form_logbook"):
    c1, c2 = st.columns([1, 1])
    entry_date = c1.date_input("Tarikh aktiviti", value=date.today())
    hours = c2.number_input("Jumlah jam (hari tersebut)", min_value=0.0, max_value=12.0, step=0.5, value=0.0)
    title = st.text_input("Ringkasan tajuk / Fokus mingguan", value="")
    activities = st.text_area("Aktiviti dilaksana (ringkas tetapi jelas)", value="", height=120)
    outcomes = st.text_area("Hasil/Output/Pembelajaran", value="", height=120)
    submit_log = st.form_submit_button("Simpan Logbook")

if submit_log:
    if not title.strip() or not activities.strip():
        st.error("Sila isi sekurang-kurangnya **Tajuk** dan **Aktiviti**.")
    else:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT log_id, acad_comment, ind_comment
                FROM logbook
                WHERE student_id=? AND term_id=? AND entry_date=?
            """, (user["user_id"], term_id, entry_date.isoformat()))
            row = cur.fetchone()

            def commented(r):
                return bool(r and ((r[1] and r[1].strip()) or (r[2] and r[2].strip())))

            if row and commented(row):
                st.error("Entri pada tarikh ini telah menerima komen penyelia dan tidak boleh diubah.")
            elif row:
                cur.execute("""
                    UPDATE logbook
                    SET title=?, activities=?, outcomes=?, hours=?
                    WHERE log_id=?
                """, (title.strip(), activities.strip(), outcomes.strip(), float(hours), int(row[0])))
                conn.commit()
                st.success("Logbook dikemas kini.")
                st.rerun()
            else:
                cur.execute("""
                    INSERT INTO logbook(student_id, term_id, entry_date, title, activities, outcomes, hours, created_at)
                    VALUES (?,?,?,?,?,?,?, datetime('now'))
                """, (user["user_id"], term_id, entry_date.isoformat(),
                      title.strip(), activities.strip(), outcomes.strip(), float(hours)))
                conn.commit()
                st.success("Logbook disimpan.")
                st.rerun()

st.markdown("### Entri Terkini")
if df_logs.empty:
    st.info("Belum ada entri logbook.")
else:
    def status_komen(r):
        a = bool(r["acad_comment"].strip()); i = bool(r["ind_comment"].strip())
        if a and i: return "✅ Akademik & Industri"
        if a:       return "✅ Akademik"
        if i:       return "✅ Industri"
        return "– Tiada komen"
    show = df_logs.copy()
    show["Status Komen"] = show.apply(status_komen, axis=1)
    show = show[["entry_date", "title", "hours", "Status Komen"]]
    st.dataframe(show, use_container_width=True)

st.divider()

# -------------------- Surat: Auto-Generate dari BLI-01 & BLI-03 --------------------
st.markdown("## 📄 Surat Permohonan & Penempatan (Auto-isi)")

tmpl_perm = os.path.join(BASE_DIR, "..", "templates", "SLI01_Surat_Permohonan.docx")
tmpl_sli3 = os.path.join(BASE_DIR, "..", "templates", "SLI03_Surat_Penempatan.docx")

# Kumpul data: profil, BLI-01 (data_json), BLI-03 (placements terkini)
with get_conn() as conn:
    u = pd.read_sql_query(
        "SELECT full_name, student_id, program_code FROM users WHERE user_id=?",
        conn, params=(user["user_id"],)
    ).iloc[0]
    df_b1 = pd.read_sql_query(
        "SELECT data_json FROM bli01 WHERE student_id=? AND term_id=? ORDER BY id DESC LIMIT 1",
        conn, params=(user["user_id"], term_id)
    )
    b1 = {}
    if not df_b1.empty and df_b1["data_json"].iloc[0]:
        import json
        try:
            b1 = json.loads(df_b1["data_json"].iloc[0]) or {}
        except Exception:
            b1 = {}
    df_p = pd.read_sql_query(
        """SELECT org_name, address, contact_person, contact_email, contact_phone
           FROM placements WHERE student_id=? AND term_id=? ORDER BY id DESC LIMIT 1""",
        conn, params=(user["user_id"], term_id)
    )
    plc = df_p.iloc[0].to_dict() if not df_p.empty else {}

today_str = datetime.date.today().strftime("%d %b %Y")
mapping_base = {
    "NAMA": u["full_name"],
    "NOPELAJAR": u["student_id"] or "",
    "PROGRAM": u["program_code"] or "",
    "TARIKH": today_str,
    # BLI-01
    "ALAMAT": b1.get("alamat", ""),
    "NOIC": b1.get("no_ic", ""),
    "NOTEL": b1.get("no_tel", ""),
    "GUARDIAN": b1.get("guardian", ""),
    "GUARDIAN_TEL": b1.get("guardian_tel", ""),
}
mapping_sli3 = {
    **mapping_base,
    # BLI-03
    "ORG": plc.get("org_name", ""),
    "ORG_ADDR": plc.get("address", ""),
    "ORG_PIC": plc.get("contact_person", ""),
    "ORG_EMAIL": plc.get("contact_email", ""),
    "ORG_PHONE": plc.get("contact_phone", ""),
}

need_bli01 = not mapping_base["ALAMAT"]  # anggap alamat wajib utk SLI01
need_bli03 = not mapping_sli3["ORG"]     # organisasi wajib utk SLI-03

c1, c2 = st.columns(2)
with c1:
    if not os.path.exists(tmpl_perm):
        st.error("Template SLI01 tidak ditemui. Letak di `templates/SLI01_Surat_Permohonan.docx`.")
    elif need_bli01:
        st.warning("Lengkapkan BLI-01 dahulu (alamat/IC/telefon) untuk auto-isi Surat Permohonan.")
    else:
        try:
            b = render_docx_from_template(tmpl_perm, mapping_base)
            st.download_button("✨ Muat Turun Surat Permohonan (Auto-isi)", b,
                               file_name=f"SLI01_{u['student_id']}.docx", type="primary")
        except Exception as e:
            st.error(f"Gagal jana Surat Permohonan: {e}")

with c2:
    if not os.path.exists(tmpl_sli3):
        st.error("Template SLI-03 tidak ditemui. Letak di `templates/SLI03_Surat_Penempatan.docx`.")
    elif need_bli03:
        st.warning("Lengkapkan BLI-03 dahulu (organisasi/penyelia industri) untuk auto-isi Surat Penempatan.")
    else:
        try:
            b = render_docx_from_template(tmpl_sli3, mapping_sli3)
            st.download_button("✨ Muat Turun Surat Penempatan (Auto-isi)", b,
                               file_name=f"SLI03_{u['student_id']}.docx", type="primary")
        except Exception as e:
            st.error(f"Gagal jana Surat Penempatan: {e}")

# -------------------- Logout --------------------
if st.button("Log Keluar"):
    st.session_state.auth = None
    st.rerun()


import streamlit as st, os, datetime, pandas as pd
from lib.common import ensure_db, auth_email_or_sid, ROLES, get_conn, one, term_label, render_docx_from_template

st.set_page_config(page_title="Log Masuk Pelajar", page_icon="🎓", layout="wide")
st.title("Log Masuk Pelajar")

try:
    ensure_db("init_mytimes_fyp.sql")
except Exception as e:
    st.error(f"Ralat DB: {e}"); st.stop()

if "auth" not in st.session_state: st.session_state.auth = None

if not st.session_state.auth:
    with st.form("login"):
        login_text = st.text_input("Emel / No. Pelajar")
        password = st.text_input("Kata Laluan", type="password")
        submitted = st.form_submit_button("Log Masuk")
    if submitted:
        user = auth_email_or_sid(login_text, password)
        if not user: st.error("Maklumat log masuk tidak sah.")
        elif user["role_name"] != "student": st.error("Akaun ini bukan peranan Pelajar.")
        else: st.session_state.auth = user; st.rerun()
else:
    user = st.session_state.auth
    st.success(f"Log masuk sebagai {user['full_name']} ({user['program_code'] or '-'})")
    st.markdown("### Dashboard Pelajar")
    with get_conn() as conn:
        tlabel = term_label(conn)
        bli01 = one(conn, "SELECT COUNT(1) FROM bli01 WHERE student_id=?", (user['user_id'],))
        bli02 = one(conn, "SELECT COUNT(1) FROM bli02_responses WHERE student_id=?", (user['user_id'],))
        plc  = one(conn, "SELECT COUNT(1) FROM placements WHERE student_id=?", (user['user_id'],))
        repin= one(conn, "SELECT COUNT(1) FROM reporting_in WHERE student_id=?", (user['user_id'],))
        logs = one(conn, "SELECT COUNT(1) FROM logbook WHERE student_id=?", (user['user_id'],))
        rep  = one(conn, "SELECT COUNT(1) FROM final_reports WHERE student_id=?", (user['user_id'],))
        ind  = one(conn, "SELECT COUNT(1) FROM bli05_industry WHERE student_id=?", (user['user_id'],))
        aca  = one(conn, "SELECT COUNT(1) FROM bli08_academic WHERE student_id=?", (user['user_id'],))

    col1, col2, col3 = st.columns(3)
    col1.metric("Sesi", tlabel)
    col2.metric("BLI-01", "✅" if bli01 else "❌")
    col3.metric("BLI-02", "✅" if bli02 else "❌")
    col4, col5, col6 = st.columns(3)
    col4.metric("BLI-03", "✅" if plc else "❌")
    col5.metric("BLI-04", "✅" if repin else "❌")
    col6.metric("Logbook Mingguan", f"{logs} entri")
    col7, col8, col9 = st.columns(3)
    col7.metric("Laporan Akhir", "✅" if rep else "❌")
    col8.metric("BLI-05", "✅" if ind else "❌")
    col9.metric("BLI-08", "✅" if aca else "❌")

    st.markdown("### 📄 Muat Turun Surat")
    def _readb(p):
        try:
            with open(p, "rb") as fh: return fh.read()
        except Exception: return None
    tmpl_perm = os.path.join("templates","SLI01_Surat_Permohonan.docx")
    tmpl_sli3 = os.path.join("templates","SLI03_Surat_Penempatan.docx")
    c1, c2 = st.columns(2)
    with c1:
        b1 = _readb(tmpl_perm)
        if b1: st.download_button("⬇️ Download Surat Permohonan (Kosong)", b1, file_name="SLI01_Surat_Permohonan.docx")
        else: st.warning("Template SLI01 tak jumpa. Letak di templates/SLI01_Surat_Permohonan.docx")
    with c2:
        b2 = _readb(tmpl_sli3)
        if b2: st.download_button("⬇️ Download Surat Penempatan (Kosong)", b2, file_name="SLI03_Surat_Penempatan.docx")
        else: st.warning("Template SLI-03 tak jumpa. Letak di templates/SLI03_Surat_Penempatan.docx")

    st.markdown("#### ✨ Auto-Generate (Isi Automatik)")
    with get_conn() as conn:
        df_u = pd.read_sql_query("SELECT full_name, student_id, program_code FROM users WHERE user_id=?", conn, params=(user['user_id'],))
        full_name, s_id, prog = df_u.iloc[0].tolist()
        df_org = pd.read_sql_query("SELECT org_name FROM placements WHERE student_id=? ORDER BY id DESC LIMIT 1", conn, params=(user['user_id'],))
        org_name = df_org['org_name'].iloc[0] if not df_org.empty else ""
    today = datetime.date.today().strftime("%d %b %Y")
    mapping_base = {"NAMA": full_name, "NOPELAJAR": s_id or "", "PROGRAM": prog or "", "TARIKH": today}
    mapping_sli3 = dict(mapping_base, **{"ORG": org_name or ""})
    colA, colB = st.columns(2)
    with colA:
        try:
            b = render_docx_from_template(tmpl_perm, mapping_base)
            st.download_button("✨ Auto-Generate Surat Permohonan (SLI01)", b, file_name=f"SLI01_{s_id}.docx")
        except Exception as e:
            st.info("Sediakan template SLI01 dengan placeholder {{NAMA}}, {{NOPELAJAR}}, {{PROGRAM}}, {{TARIKH}}.")
    with colB:
        if org_name:
            try:
                b = render_docx_from_template(tmpl_sli3, mapping_sli3)
                st.download_button("✨ Auto-Generate Surat Penempatan (SLI-03)", b, file_name=f"SLI03_{s_id}.docx")
            except Exception as e:
                st.info("Sediakan template SLI-03 dengan placeholder termasuk {{ORG}}.")
        else:
            st.info("Surat Penempatan diaktifkan selepas maklumat organisasi wujud (BLI-03).")

    if st.button("Log Keluar"): st.session_state.auth=None; st.rerun()

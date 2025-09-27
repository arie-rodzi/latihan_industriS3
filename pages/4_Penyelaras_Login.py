
import streamlit as st
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label
import pandas as pd

st.set_page_config(page_title="Penyelaras", page_icon="⚙️", layout="wide")
st.title("Log Masuk Penyelaras")
try:
    ensure_db("init_mytimes_fyp.sql")
except Exception as e:
    st.error(f"Ralat DB: {e}"); st.stop()

if "auth" not in st.session_state: st.session_state.auth = None
if not st.session_state.auth:
    with st.form("login_coord"):
        email = st.text_input("Emel")
        password = st.text_input("Kata Laluan", type="password")
        submitted = st.form_submit_button("Log Masuk")
    if submitted:
        user = auth_email_or_sid(email, password)
        if not user or user["role_name"]!="coordinator":
            st.error("Akaun bukan Penyelaras / salah maklumat."); 
        else:
            st.session_state.auth = user; st.rerun()
else:
    user = st.session_state.auth
    st.success(f"Log masuk sebagai {user['full_name']}")
    with get_conn() as conn:
        tlabel = term_label(conn)
        total_students = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=1")
        total_acad = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=3")
        total_ind = one(conn, "SELECT COUNT(1) FROM users WHERE role_id=4")
        bli01 = one(conn, "SELECT COUNT(1) FROM bli01")
        bli02 = one(conn, "SELECT COUNT(1) FROM bli02_responses")
        placements_cnt = one(conn, "SELECT COUNT(1) FROM placements")
        bli05 = one(conn, "SELECT COUNT(1) FROM bli05_industry")
        bli08 = one(conn, "SELECT COUNT(1) FROM bli08_academic")
        reports = one(conn, "SELECT COUNT(1) FROM final_reports")
    st.markdown(f"**Sesi:** {tlabel}")
    c1,c2,c3 = st.columns(3)
    c1.metric("Pelajar", f"{total_students}")
    c2.metric("Penyelia Akademik", f"{total_acad}")
    c3.metric("Penyelia Industri", f"{total_ind}")
    c4,c5,c6 = st.columns(3)
    c4.metric("BLI-01", f"{bli01}")
    c5.metric("BLI-02", f"{bli02}")
    c6.metric("Penempatan", f"{placements_cnt}")
    c7,c8,c9 = st.columns(3)
    c7.metric("BLI-05", f"{bli05}")
    c8.metric("BLI-08", f"{bli08}")
    c9.metric("Laporan Akhir", f"{reports}")
    st.info("Modul agihan penyelia & export keputusan boleh ditambah seterusnya.")

    if st.button("Log Keluar"): st.session_state.auth=None; st.rerun()

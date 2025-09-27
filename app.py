
import streamlit as st
import sqlite3, hashlib

DB_PATH = st.secrets.get("DB_PATH", "mytimes.db")
ROLES = {1:"student",2:"coordinator",3:"acad_sv",4:"ind_sv"}

def sha256(pw: str) -> str:
    import hashlib
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def get_conn():
    return sqlite3.connect(DB_PATH)

def auth(email, password):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, full_name, role_id, program_code, password_hash FROM users WHERE email=? AND is_active=1",(email,))
        row = cur.fetchone()
        if not row: return None
        user_id, full_name, role_id, program_code, ph = row
        if ph == sha256(password):
            return {"user_id":user_id,"full_name":full_name,"role_id":role_id,"program_code":program_code}
    return None

def nav_for(role_name):
    if role_name=="student":
        return ["Dashboard","BLI 01 Isian","Upload BLI 02","Logbook","Upload Laporan Akhir","Semakan Supervisor"]
    if role_name=="coordinator":
        return ["Dashboard","Admin Panel","BLI 05 Industri","BLI 08 Akademik","Export Keputusan"]
    if role_name=="acad_sv":
        return ["Dashboard","BLI 08 Akademik","Semak Logbook","Semak Laporan Akhir"]
    if role_name=="ind_sv":
        return ["Dashboard","BLI 05 Industri","Semak Logbook"]
    return []

st.set_page_config(page_title="FYP Praktikal UiTM N9", page_icon="🎓", layout="wide")
st.title("FYP Praktikal UiTM N9 — Demo")

if "auth" not in st.session_state:
    st.session_state.auth = None

if not st.session_state.auth:
    with st.form("login"):
        email = st.text_input("Emel")
        password = st.text_input("Kata Laluan", type="password")
        submitted = st.form_submit_button("Log Masuk")
    if submitted:
        user = auth(email, password)
        if user:
            st.session_state.auth = user
            st.rerun()
        else:
            st.error("Emel/kata laluan tidak sah.")
else:
    user = st.session_state.auth
    role_name = ROLES.get(user["role_id"], "unknown")
    st.sidebar.markdown(f"**Pengguna:** {user['full_name']}")
    st.sidebar.markdown(f"**Peranan:** {role_name}")
    menu = nav_for(role_name)
    choice = st.sidebar.selectbox("Menu", menu)
    st.info(f"Placeholder halaman: **{choice}**.")

    if st.sidebar.button("Log Keluar"):
        st.session_state.auth = None
        st.rerun()

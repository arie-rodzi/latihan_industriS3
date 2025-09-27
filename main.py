# Home.py  (root app entry)
import os
import streamlit as st
from lib.common import ensure_db

st.set_page_config(page_title="Sistem Latihan Industri", page_icon="🎓", layout="wide")

# --- Make sure DB exists using a robust relative path ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_PATH = os.path.join(BASE_DIR, "init_mytimes_fyp.sql")
try:
    ensure_db(SQL_PATH)
except Exception as e:
    st.error(f"Ralat DB: {e}")
    st.stop()

st.title("Sistem Latihan Industri")

# Ensure session key exists
if "auth" not in st.session_state:
    st.session_state.auth = None

auth = st.session_state.auth

if not auth:
    st.caption("Sila pilih peranan untuk log masuk:")
    st.page_link("pages/1_Pelajar_Login.py",           label="👨‍🎓 Pelajar",              icon="🎓")
    st.page_link("pages/2_Penyelia_Akademik_Login.py", label="📘 Penyelia Akademik",     icon="📘")
    st.page_link("pages/3_Penyelia_Industri_Login.py", label="🏭 Penyelia Industri",     icon="🏭")
    st.page_link("pages/4_Penyelaras_Login.py",        label="⚙️ Penyelaras",            icon="⚙️")
else:
    role = auth.get("role_name")
    st.success(f"Log masuk sebagai {auth['full_name']} ({role})")

    if role == "student":
        st.page_link("pages/1_Pelajar_Login.py", label="👨‍🎓 Dashboard Pelajar", icon="🎓")
    elif role == "acad_sv":
        st.page_link("pages/2_Penyelia_Akademik_Dashboard.py", label="📘 Dashboard Penyelia Akademik", icon="📘")
    elif role == "ind_sv":
        st.page_link("pages/3_Penyelia_Industri_Dashboard.py", label="🏭 Dashboard Penyelia Industri", icon="🏭")
    elif role == "coordinator":
        st.page_link("pages/4_Penyelaras_Dashboard.py", label="⚙️ Dashboard Penyelaras", icon="⚙️")

    st.divider()
    if st.button("Log Keluar"):
        st.session_state.auth = None
        st.rerun()

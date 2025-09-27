# main.py (Home)
import os
import streamlit as st
from lib.common import ensure_db

st.set_page_config(page_title="Sistem Latihan Industri", page_icon="🎓", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_PATH  = os.path.join(BASE_DIR, "init_mytimes_fyp.sql")
ensure_db(SQL_PATH)

st.title("Sistem Latihan Industri")

if "auth" not in st.session_state:
    st.session_state.auth = None
auth = st.session_state.auth

def page_exists(rel_path: str) -> bool:
    return os.path.exists(os.path.join(BASE_DIR, rel_path))

def safe_page_link(path_try: str, path_fallback: str, **kwargs):
    st.page_link(path_try if page_exists(path_try) else path_fallback, **kwargs)

if not auth:
    st.caption("Sila pilih peranan untuk log masuk:")
    st.page_link("pages/1_Pelajar_Login.py",           label="👨‍🎓 Pelajar",            icon="🎓")
    st.page_link("pages/2_Penyelia_Akademik_Login.py", label="📘 Penyelia Akademik",   icon="📘")
    st.page_link("pages/3_Penyelia_Industri_Login.py", label="🏭 Penyelia Industri",   icon="🏭")
    st.page_link("pages/4_Penyelaras_Login.py",        label="⚙️ Penyelaras",          icon="⚙️")
else:
    role = auth.get("role_name")
    st.success(f"Log masuk sebagai {auth['full_name']} ({role})")

    if role == "student":
        # Pelajar guna page yang sama untuk dashboard
        st.page_link("pages/1_Pelajar_Login.py", label="👨‍🎓 Dashboard Pelajar", icon="🎓")

    elif role == "acad_sv":
        # Cuba Dashboard; jika tak wujud, fallback ke Login
        safe_page_link(
            "pages/2_Penyelia_Akademik_Dashboard.py",
            "pages/2_Penyelia_Akademik_Login.py",
            label="📘 Dashboard Penyelia Akademik", icon="📘"
        )

    elif role == "ind_sv":
        safe_page_link(
            "pages/3_Penyelia_Industri_Dashboard.py",
            "pages/3_Penyelia_Industri_Login.py",
            label="🏭 Dashboard Penyelia Industri", icon="🏭"
        )

    elif role == "coordinator":
        safe_page_link(
            "pages/4_Penyelaras_Dashboard.py",
            "pages/4_Penyelaras_Login.py",
            label="⚙️ Dashboard Penyelaras", icon="⚙️"
        )

    st.divider()
    if st.button("Log Keluar"):
        st.session_state.auth = None
        st.rerun()

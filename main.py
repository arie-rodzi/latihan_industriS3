import streamlit as st
from lib.common import ensure_db
st.set_page_config(page_title="Sistem Latihan Industri", page_icon="🎓", layout="wide")

ensure_db("init_mytimes_fyp.sql")

st.title("Sistem Latihan Industri")

auth = st.session_state.get("auth")

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
        st.page_link("pages/1_Pelajar_Login.py", label="👨‍🎓 Dashboard Pelajar", icon="🎓")
    elif role == "acad_sv":
        st.page_link("pages/2_Penyelia_Akademik_Dashboard.py", label="📘 Dashboard Penyelia Akademik", icon="📘")
    elif role == "ind_sv":
        st.page_link("pages/3_Penyelia_Industri_Dashboard.py", label="🏭 Dashboard Penyelia Industri", icon="🏭")
    elif role == "coordinator":
        st.page_link("pages/4_Penyelaras_Dashboard.py", label="⚙️ Dashboard Penyelaras", icon="⚙️")
        # jika ada Admin Panel pun letak di bawah coordinator
        # st.page_link("pages/Admin_Panel.py", label="🛡️ Admin Panel", icon="🛡️")

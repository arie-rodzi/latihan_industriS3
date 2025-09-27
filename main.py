
import streamlit as st
from lib.common import ensure_db
st.set_page_config(page_title="Sistem Latihan Industri", page_icon="🎓", layout="wide")
st.title("Sistem Latihan Industri — Demo (main.py)")
st.page_link("pages/1_Pelajar_Login.py", label="👨‍🎓 Pelajar", icon="🎓")
st.page_link("pages/2_Penyelia_Akademik_Login.py", label="📘 Penyelia Akademik", icon="📘")
st.page_link("pages/3_Penyelia_Industri_Login.py", label="🏭 Penyelia Industri", icon="🏭")
st.page_link("pages/4_Penyelaras_Login.py", label="⚙️ Penyelaras", icon="⚙️")
try:
    ensure_db("init_mytimes_fyp.sql")
except Exception as e:
    st.warning(f"DB belum diinisialisasi: {e}")

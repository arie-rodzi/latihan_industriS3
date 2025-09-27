
import streamlit as st, pandas as pd
from lib.common import ensure_db, auth_email_or_sid, get_conn, one, term_label

st.set_page_config(page_title="Penyelia Akademik", page_icon="📘", layout="wide")
st.title("Log Masuk Penyelia Akademik")
try:
    ensure_db("init_mytimes_fyp.sql")
except Exception as e:
    st.error(f"Ralat DB: {e}"); st.stop()

if "auth" not in st.session_state: st.session_state.auth = None
if not st.session_state.auth:
    with st.form("login_acad"):
        email = st.text_input("Emel")
        password = st.text_input("Kata Laluan", type="password")
        submitted = st.form_submit_button("Log Masuk")
    if submitted:
        user = auth_email_or_sid(email, password)
        if not user or user["role_name"]!="acad_sv":
            st.error("Akaun bukan Penyelia Akademik / salah maklumat."); 
        else:
            st.session_state.auth = user; st.rerun()
else:
    user = st.session_state.auth
    st.success(f"Log masuk sebagai {user['full_name']}")
    with get_conn() as conn:
        tlabel = term_label(conn)
        assigned = one(conn, "SELECT COUNT(1) FROM supervision WHERE acad_supervisor_id=?", (user['user_id'],))
        pending_bli08 = one(conn, "SELECT COUNT(1) FROM bli08_academic WHERE acad_supervisor_id=? AND (submitted_at IS NULL OR submitted_at='')", (user['user_id'],))
        reports_to_review = one(conn, "SELECT COUNT(1) FROM final_reports WHERE acad_status='PENDING'")
        log_comments = one(conn, "SELECT COUNT(1) FROM logbook WHERE acad_comment IS NOT NULL AND acad_commented_by=?", (user['user_id'],))
    c1,c2,c3 = st.columns(3)
    c1.metric("Sesi", tlabel); c2.metric("Pelajar diselia", f"{assigned}"); c3.metric("BLI-08 belum lengkap", f"{pending_bli08}")
    c4,c5 = st.columns(2)
    c4.metric("Laporan Akhir (Pending)", f"{reports_to_review}"); c5.metric("Ulasan Logbook (anda)", f"{log_comments}")

    st.markdown("### 📒 Semak Logbook")
    with get_conn() as conn:
        terms = pd.read_sql_query("SELECT term_id, session_label FROM terms ORDER BY term_id DESC", conn)
        term_id = int(terms.iloc[0]["term_id"]) if not terms.empty else None
        if not term_id:
            st.warning("Tiada term."); st.stop()
        df_stu = pd.read_sql_query(
            "SELECT u.user_id, u.full_name, u.student_id FROM supervision s JOIN users u ON u.user_id=s.student_id WHERE s.term_id=? AND s.acad_supervisor_id=? ORDER BY u.full_name",
            conn, params=(term_id, user['user_id'])
        )

    if df_stu.empty:
        st.info("Tiada pelajar di bawah jagaan anda.")
    else:
        label_to_id = { f"{r.student_id} - {r.full_name}": int(r.user_id) for r in df_stu.itertuples(index=False) }
        choice = st.selectbox("Pilih pelajar", list(label_to_id.keys()))
        chosen_id = label_to_id[choice]
        with get_conn() as conn:
            df_logs = pd.read_sql_query(
                "SELECT log_id, entry_date, title, activities, outcomes, hours, acad_comment FROM logbook WHERE student_id=? AND term_id=? ORDER BY entry_date DESC",
                conn, params=(chosen_id, term_id)
            )
        st.caption(f"Total entri: {len(df_logs)}")
        if df_logs.empty:
            st.warning("Pelajar ini belum isi logbook.")
        else:
            st.dataframe(df_logs[["entry_date","title","hours","acad_comment"]], use_container_width=True)
            st.markdown("#### ✍️ Komen Pada Entri")
            for i, row in df_logs.iterrows():
                with st.expander(f"Entri {row['entry_date']} — {row['title'] or '-'}"):
                    st.markdown("**Aktiviti**"); st.write(row["activities"] or "-")
                    st.markdown("**Hasil/Outcomes**"); st.write(row["outcomes"] or "-")
                    new_c = st.text_area("Komen (Akademik)", value=row["acad_comment"] or "", key=f"acad_c_{row['log_id']}")
                    if st.button("Simpan Komen (Akademik)", key=f"btn_acad_{row['log_id']}"):
                        with get_conn() as conn:
                            cur = conn.cursor()
                            cur.execute("UPDATE logbook SET acad_comment=?, acad_commented_by=?, acad_commented_at=datetime('now') WHERE log_id=?", (new_c, user['user_id'], int(row["log_id"])))
                            conn.commit()
                        st.success("Komen akademik disimpan."); st.rerun()

    if st.button("Log Keluar"): st.session_state.auth=None; st.rerun()

# ==== Tambah SEBELUM dapatkan df_sections (awal mukasurat dashboard) ====

import hashlib, math

def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def ensure_users_has_class_section():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = {r[1] for r in cur.fetchall()}
        if "class_section" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN class_section TEXT")
            conn.commit()

def seed_or_fix_classes_for_program(program_code: str, term_id: int) -> str:
    """
    1) Jika ada pelajar program ini tapi semua/majoriti tiada class_section → pecah ke {PROGRAM}7A/7B.
    2) Jika langsung tiada pelajar program ini → jana 60 pelajar demo {PROGRAM}7A/7B,
       tambah placements dan padan penyelia industri (Kumar/Lim).
    """
    ensure_users_has_class_section()
    with get_conn() as conn:
        cur = conn.cursor()

        # Kira pelajar program ini
        cur.execute("SELECT COUNT(1) FROM users WHERE role_id=1 AND program_code=?", (program_code,))
        total = int(cur.fetchone()[0])

        if total == 0:
            # ——— SEED 60 PELAJAR DEMO ———
            base = 2025000
            for i in range(1, 61):
                sid = str(base + i)
                name = f"Pelajar {program_code} #{i:02d}"
                email = f"{sid}@student.uitm.edu.my"
                section = f"{program_code}7A" if i <= 30 else f"{program_code}7B"
                cur.execute("""
                    INSERT INTO users(full_name, email, role_id, program_code, student_id, class_section, password_hash, is_active)
                    VALUES (?,?,?,?,?,?,?,1)
                """, (name, email, 1, program_code, sid, section, _sha("DEFAULT123")))
            conn.commit()

            # Pastikan industry SV wujud
            def _get_or_create_user(email, full_name, role_id, program=None):
                cur.execute("SELECT user_id FROM users WHERE email=?", (email,))
                r = cur.fetchone()
                if r: return int(r[0])
                cur.execute("""
                    INSERT INTO users(full_name, email, role_id, program_code, password_hash, is_active)
                    VALUES (?,?,?,?,?,1)
                """, (full_name, email, role_id, program, _sha("DEFAULT123")))
                conn.commit()
                return cur.lastrowid

            kumar_id = _get_or_create_user("kumar@industry.com", "Encik Kumar", 4, None)
            lim_id   = _get_or_create_user("lim@industry.com",   "Encik Lim",   4, None)

            # Tambah placements + padan industri selang-seli
            df_stu = pd.read_sql_query("""
                SELECT user_id, student_id FROM users
                WHERE role_id=1 AND program_code=? ORDER BY student_id
            """, conn, params=(program_code,))
            for idx, r in df_stu.iterrows():
                cur.execute("""
                    INSERT INTO placements(student_id, org_name, address, contact_person, contact_email, contact_phone, term_id, created_at)
                    VALUES (?,?,?,?,?,?,?, datetime('now'))
                """, (int(r["user_id"]), f"Syarikat Demo #{idx+1:02d}", "Alamat Demo",
                      "Penyelia Syarikat", "pic@demo.com", "03-12345678", term_id))
                ind_id = kumar_id if (idx % 2 == 0) else lim_id
                cur.execute("""
                    INSERT INTO supervisor_assignments(student_user_id, acad_sv_user_id, ind_sv_user_id, program_code, term_id, assigned_at)
                    VALUES (?,?,?,?,?, datetime('now'))
                """, (int(r["user_id"]), None, ind_id, program_code, term_id))
            conn.commit()
            return f"SEED: Cipta 60 pelajar demo untuk {program_code} (…7A/7B) + placements + padanan industri."

        # Ada pelajar — semak class_section
        df_have = pd.read_sql_query("""
            SELECT user_id, COALESCE(class_section,'') AS cs
            FROM users WHERE role_id=1 AND program_code=?
        """, conn, params=(program_code,))
        have_any_section = any(bool(x.strip()) for x in df_have["cs"].tolist())

        if not have_any_section:
            # ——— PECahkan semua pelajar sedia ada ke {PROGRAM}7A/7B ———
            df_sorted = pd.read_sql_query("""
                SELECT user_id FROM users
                WHERE role_id=1 AND program_code=?
                ORDER BY CAST(student_id AS TEXT)
            """, conn, params=(program_code,))
            n = len(df_sorted); half = math.ceil(n/2)
            idsA = df_sorted.iloc[:half]["user_id"].tolist()
            idsB = df_sorted.iloc[half:]["user_id"].tolist()
            secA, secB = f"{program_code}7A", f"{program_code}7B"
            if idsA:
                cur.execute(f"UPDATE users SET class_section=? WHERE user_id IN ({','.join(['?']*len(idsA))})",
                            (secA, *idsA))
            if idsB:
                cur.execute(f"UPDATE users SET class_section=? WHERE user_id IN ({','.join(['?']*len(idsB))})",
                            (secB, *idsB))
            conn.commit()
            return f"ASSIGN: Tetapkan class_section untuk {n} pelajar → {secA} & {secB}."

        return "OK: class_section sedia ada."

# ——— PANGGIL SEED/FIX ———
msg = seed_or_fix_classes_for_program(program_managed, term_id)
st.caption(f"Init kelas: {msg}")

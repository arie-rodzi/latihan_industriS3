
import sqlite3, os, hashlib, io

DB_PATH = os.environ.get("DB_PATH", "mytimes.db")
ROLES = {1:"student",2:"coordinator",3:"acad_sv",4:"ind_sv"}

def sha256(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def get_conn():
    return sqlite3.connect(DB_PATH)

def ensure_db(sql_path: str = "init_mytimes_fyp.sql"):
    need_init = False
    if not os.path.exists(DB_PATH):
        need_init = True
    else:
        try:
            with sqlite3.connect(DB_PATH) as c:
                c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users';")
                if not c.fetchone():
                    need_init = True
        except Exception:
            need_init = True
    if need_init:
        if not os.path.exists(sql_path):
            raise FileNotFoundError(f"Init SQL not found: {sql_path}")
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()
        with sqlite3.connect(DB_PATH) as c:
            c.executescript(sql); c.commit()

def auth_email_or_sid(login_text: str, password: str):
    candidate = (login_text or "").strip()
    sid = None
    if "@" not in candidate and candidate:
        sid = candidate
        candidate = f"{sid.lower()}@student.uitm.edu.my"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, full_name, role_id, program_code, password_hash FROM users WHERE email=? AND is_active=1", (candidate,))
        row = cur.fetchone()
        if not row and sid:
            cur.execute("SELECT user_id, full_name, role_id, program_code, password_hash FROM users WHERE student_id=? AND is_active=1", (sid,))
            row = cur.fetchone()
        if not row: return None
        user_id, full_name, role_id, program_code, ph = row
        if ph == sha256(password):
            return {"user_id":user_id,"full_name":full_name,"role_id":role_id,"role_name":ROLES.get(role_id,"?"),"program_code":program_code}
    return None

def one(conn, sql, params=()):
    cur = conn.cursor(); cur.execute(sql, params); r = cur.fetchone()
    return r[0] if r and r[0] is not None else 0

def term_label(conn):
    try:
        cur = conn.cursor(); cur.execute("SELECT session_label FROM terms ORDER BY term_id DESC LIMIT 1;")
        r = cur.fetchone(); return r[0] if r else "-"
    except Exception:
        return "-"

# DOCX helpers (optional; used by student auto-generate letters)
def _replace_runs_with_placeholders(doc, mapping):
    def _replace_in_para(para):
        text = "".join(run.text for run in para.runs) or para.text
        if not text: return
        original = text
        for k, v in mapping.items():
            text = text.replace("{{"+k+"}}", str(v))
        if text != original:
            while para.runs:
                para._p.remove(para.runs[0]._r)
            para.add_run(text)
    for p in doc.paragraphs: _replace_in_para(p)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for p in cell.paragraphs: _replace_in_para(p)

def render_docx_from_template(template_path: str, mapping: dict) -> bytes:
    from docx import Document
    if not os.path.exists(template_path): raise FileNotFoundError(template_path)
    doc = Document(template_path); _replace_runs_with_placeholders(doc, mapping)
    import io; bio = io.BytesIO(); doc.save(bio); return bio.getvalue()

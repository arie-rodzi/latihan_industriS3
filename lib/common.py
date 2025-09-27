# lib/common.py
import sqlite3, os, hashlib, io, re

DB_PATH = os.environ.get("DB_PATH", "mytimes.db")
ROLES = {1: "student", 2: "coordinator", 3: "acad_sv", 4: "ind_sv"}

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
        cur.execute(
            "SELECT user_id, full_name, role_id, program_code, password_hash "
            "FROM users WHERE email=? AND is_active=1", (candidate,)
        )
        row = cur.fetchone()
        if not row and sid:
            cur.execute(
                "SELECT user_id, full_name, role_id, program_code, password_hash "
                "FROM users WHERE student_id=? AND is_active=1", (sid,)
            )
            row = cur.fetchone()
        if not row: return None
        user_id, full_name, role_id, program_code, ph = row
        if ph == sha256(password):
            return {
                "user_id": user_id, "full_name": full_name,
                "role_id": role_id, "role_name": ROLES.get(role_id, "?"),
                "program_code": program_code
            }
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

# ---------------- DOCX helpers (robust) ----------------
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def _compile_token_patterns(keys):
    """Build regex patterns for {{KEY}}, «KEY», <<KEY>> with optional spaces."""
    pats = {}
    for k in keys:
        kk = re.escape(k)
        pats[k] = [
            re.compile(r"\{\{\s*"+kk+r"\s*\}\}"),   # {{ KEY }}
            re.compile(r"«\s*"+kk+r"\s*»"),         # « KEY »
            re.compile(r"<<\s*"+kk+r"\s*>>"),       # << KEY >>
        ]
    return pats

def _replace_text(text, patterns, values):
    if text is None:
        return text
    out = text
    for k, regs in patterns.items():
        val = "" if values.get(k) is None else str(values[k])
        for rgx in regs:
            out = rgx.sub(val, out)
    return out

def _rewrite_paragraph(p, patterns, values):
    """
    Join ALL text in p (across runs/w:t), do replacements,
    then rebuild the paragraph with a single run (preserving xml:space).
    """
    # collect all w:t text in this paragraph
    t_nodes = p.xpath(".//w:t", namespaces=p.nsmap)
    original = "".join([t.text or "" for t in t_nodes])
    replaced = _replace_text(original, patterns, values)
    if replaced == original:
        return  # nothing to change

    # remove all runs <w:r>
    r_nodes = p.xpath("./w:r", namespaces=p.nsmap)
    for r in r_nodes:
        p.remove(r)

    # create a new run with the replaced text
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")  # keep spaces
    t.text = replaced
    r.append(t)
    p.append(r)

def _process_part(part, patterns, values):
    """
    Process all paragraphs in a docx part (body, header, footer, drawing parts).
    Works even if tokens were split across multiple runs.
    """
    try:
        # all paragraphs anywhere in this part
        p_nodes = part.element.xpath(".//w:p", namespaces=part.element.nsmap)
        for p in p_nodes:
            _rewrite_paragraph(p, patterns, values)
    except Exception:
        pass

def _replace_placeholders_all_parts(doc, mapping):
    patterns = _compile_token_patterns(mapping.keys())
    # main body
    _process_part(doc.part, patterns, mapping)
    # headers/footers
    for section in doc.sections:
        if section.header and getattr(section.header, "part", None):
            _process_part(section.header.part, patterns, mapping)
        if section.footer and getattr(section.footer, "part", None):
            _process_part(section.footer.part, patterns, mapping)
    # related parts (e.g. text boxes)
    for rel in list(getattr(doc.part, "related_parts", {}).values()):
        if hasattr(rel, "element"):
            _process_part(rel, patterns, mapping)

def render_docx_from_template(template_path: str, mapping: dict) -> bytes:
    """
    Load a .docx template and replace placeholders with mapping values.
    - Supports {{KEY}}, «KEY», <<KEY>> (spaces tolerated)
    - Works in body, tables, headers/footers, and most text boxes
    - Merges paragraph runs so split tokens are still replaced
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(template_path)
    doc = Document(template_path)
    _replace_placeholders_all_parts(doc, mapping)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

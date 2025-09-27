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

# ---------------- DOCX helpers (robust, all parts) ----------------
def _compile_token_patterns(mapping_keys):
    """
    Build regex patterns for each KEY to match:
      {{ KEY }}, « KEY », << KEY >>
    with optional spaces around the KEY.
    """
    patterns = {}
    for k in mapping_keys:
        # escape key for regex
        key = re.escape(k)
        patterns[k] = [
            re.compile(r"\{\{\s*" + key + r"\s*\}\}"),      # {{ KEY }}
            re.compile(r"«\s*" + key + r"\s*»"),            # « KEY »
            re.compile(r"<<\s*" + key + r"\s*>>"),          # << KEY >>
        ]
    return patterns

def _replace_in_text_node(txt, patterns, values_by_key):
    """
    Replace placeholders in a single text node string.
    """
    if txt is None:
        return txt
    out = txt
    for k, regs in patterns.items():
        val = "" if values_by_key.get(k) is None else str(values_by_key[k])
        for rgx in regs:
            out = rgx.sub(val, out)
    return out

def _replace_in_part_xml(part, patterns, values_by_key):
    """
    Replace in all w:t nodes of a given part (body/header/footer/etc).
    This catches paragraphs, tables, headers/footers, and most text boxes.
    """
    try:
        from docx.oxml.ns import qn
        # All text nodes
        t_nodes = part.element.xpath(".//w:t", namespaces=part.element.nsmap)
        for t in t_nodes:
            t.text = _replace_in_text_node(t.text, patterns, values_by_key)
    except Exception:
        pass

def _replace_runs_with_placeholders(doc, mapping: dict):
    """
    Replace placeholders across ALL document parts:
    - main document body
    - headers & footers of all sections
    - and any related parts that expose XML with w:t nodes (e.g., text boxes)
    """
    patterns = _compile_token_patterns(mapping.keys())

    # main body
    _replace_in_part_xml(doc.part, patterns, mapping)

    # headers/footers of each section
    for section in doc.sections:
        if section.header and getattr(section.header, "part", None):
            _replace_in_part_xml(section.header.part, patterns, mapping)
        if section.footer and getattr(section.footer, "part", None):
            _replace_in_part_xml(section.footer.part, patterns, mapping)

    # other related parts (e.g., text boxes can live in separate drawing parts)
    for rel in list(getattr(doc.part, "related_parts", {}).values()):
        if hasattr(rel, "element"):
            _replace_in_part_xml(rel, patterns, mapping)

def render_docx_from_template(template_path: str, mapping: dict) -> bytes:
    """
    Load a .docx template and replace placeholders with mapping values.
    Supports tokens in {{KEY}}, «KEY», <<KEY>> formats (with optional spaces).
    Replaces in body, tables, headers/footers, and most text boxes.
    """
    from docx import Document
    if not os.path.exists(template_path):
        raise FileNotFoundError(template_path)
    doc = Document(template_path)
    _replace_runs_with_placeholders(doc, mapping)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  email TEXT UNIQUE,
  student_id TEXT UNIQUE,
  role_id INTEGER NOT NULL,
  program_code TEXT,
  password_hash TEXT NOT NULL,
  is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS terms (
  term_id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_label TEXT NOT NULL,
  start_date TEXT,
  end_date TEXT
);
INSERT OR IGNORE INTO terms(term_id, session_label, start_date, end_date)
VALUES (1,'Oct 2025','2025-10-01','2026-02-28');

CREATE TABLE IF NOT EXISTS supervision (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  term_id INTEGER NOT NULL,
  acad_supervisor_id INTEGER,
  ind_supervisor_id INTEGER,
  coordinator_id INTEGER,
  assigned_at TEXT,
  UNIQUE(student_id, term_id)
);

CREATE TABLE IF NOT EXISTS placements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  org_name TEXT NOT NULL,
  address TEXT,
  contact_person TEXT,
  contact_email TEXT,
  contact_phone TEXT,
  term_id INTEGER,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reporting_in (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  term_id INTEGER,
  reported_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS logbook (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  term_id INTEGER NOT NULL,
  entry_date TEXT NOT NULL,
  title TEXT,
  activities TEXT,
  outcomes TEXT,
  hours REAL DEFAULT 0,
  acad_comment TEXT,
  acad_commented_by INTEGER,
  acad_commented_at TEXT,
  ind_comment TEXT,
  ind_commented_by INTEGER,
  ind_commented_at TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_logbook_student_term ON logbook(student_id, term_id);
CREATE INDEX IF NOT EXISTS idx_logbook_entry_date ON logbook(entry_date);

CREATE TABLE IF NOT EXISTS final_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  term_id INTEGER,
  file_name TEXT,
  uploaded_at TEXT DEFAULT (datetime('now')),
  acad_status TEXT DEFAULT 'PENDING'
);

CREATE TABLE IF NOT EXISTS bli01 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  term_id INTEGER,
  submitted_at TEXT DEFAULT (datetime('now')),
  data_json TEXT
);

CREATE TABLE IF NOT EXISTS bli02_responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  term_id INTEGER,
  uploaded_at TEXT DEFAULT (datetime('now')),
  file_name TEXT
);

CREATE TABLE IF NOT EXISTS bli05_industry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  ind_supervisor_id INTEGER NOT NULL,
  term_id INTEGER,
  submitted_at TEXT DEFAULT (datetime('now')),
  score_total REAL,
  remarks TEXT
);

CREATE TABLE IF NOT EXISTS bli08_academic (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL,
  acad_supervisor_id INTEGER NOT NULL,
  term_id INTEGER,
  submitted_at TEXT DEFAULT (datetime('now')),
  score_total REAL,
  remarks TEXT
);

CREATE VIEW IF NOT EXISTS v_student_status AS
SELECT
  u.user_id AS student_user_id,
  u.full_name,
  u.student_id,
  u.program_code,
  (SELECT COUNT(1) FROM bli01 b WHERE b.student_id=u.user_id) AS has_bli01,
  (SELECT COUNT(1) FROM bli02_responses r WHERE r.student_id=u.user_id) AS has_bli02,
  (SELECT COUNT(1) FROM placements p WHERE p.student_id=u.user_id) AS has_placement,
  (SELECT COUNT(1) FROM reporting_in ri WHERE ri.student_id=u.user_id) AS has_reporting_in,
  (SELECT COUNT(1) FROM logbook l WHERE l.student_id=u.user_id) AS log_count,
  (SELECT COUNT(1) FROM final_reports fr WHERE fr.student_id=u.user_id) AS has_final_report,
  (SELECT COUNT(1) FROM bli05_industry i WHERE i.student_id=u.user_id) AS has_bli05,
  (SELECT COUNT(1) FROM bli08_academic a WHERE a.student_id=u.user_id) AS has_bli08
FROM users u
WHERE u.role_id=1;

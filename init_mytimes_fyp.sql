
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roles (
  role_id INTEGER PRIMARY KEY,
  role_name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  full_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role_id INTEGER NOT NULL REFERENCES roles(role_id),
  program_code TEXT,
  student_id TEXT,
  staff_id TEXT,
  industry_org TEXT,
  is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS terms (
  term_id INTEGER PRIMARY KEY,
  session_label TEXT NOT NULL,
  start_date TEXT, end_date TEXT,
  bli01_deadline TEXT, bli02_deadline TEXT,
  logbook_freq TEXT DEFAULT 'WEEKLY',
  report_deadline TEXT
);

CREATE TABLE IF NOT EXISTS bli01 (
  bli01_id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(user_id),
  term_id INTEGER NOT NULL REFERENCES terms(term_id),
  ic_no TEXT, cgpa REAL, mobile_no TEXT, email TEXT,
  mailing_address TEXT, guardian_phone TEXT,
  status TEXT DEFAULT 'SUBMITTED',
  submitted_at TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS bli02_responses (
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(user_id),
  term_id INTEGER NOT NULL REFERENCES terms(term_id),
  date TEXT, org_decision TEXT, allowance_terms TEXT,
  org_address TEXT, org_officer_name TEXT, org_officer_title TEXT,
  org_phone TEXT, org_fax TEXT, org_email TEXT,
  letter_file_path TEXT, submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS placements (
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(user_id),
  term_id INTEGER NOT NULL REFERENCES terms(term_id),
  start_date TEXT, end_date TEXT,
  org_name TEXT, org_address TEXT, org_phone TEXT, org_fax TEXT,
  org_officer TEXT, org_officer_mobile TEXT,
  student_confirmed_at TEXT, coordinator_action TEXT, coordinator_action_at TEXT
);

CREATE TABLE IF NOT EXISTS reporting_in (
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(user_id),
  term_id INTEGER NOT NULL REFERENCES terms(term_id),
  reported_on TEXT, reported_status TEXT,
  assigned_ind_supervisor_name TEXT, assigned_ind_email TEXT, assigned_ind_phone TEXT,
  org_name TEXT, org_email TEXT, org_phone TEXT, org_fax TEXT
);

CREATE TABLE IF NOT EXISTS logbook (
  log_id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(user_id),
  term_id INTEGER NOT NULL REFERENCES terms(term_id),
  entry_date TEXT NOT NULL,
  title TEXT, activities TEXT, outcomes TEXT, hours REAL,
  acad_comment TEXT, acad_commented_by INTEGER, acad_commented_at TEXT,
  ind_comment TEXT, ind_commented_by INTEGER, ind_commented_at TEXT
);

CREATE TABLE IF NOT EXISTS final_reports (
  report_id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(user_id),
  term_id INTEGER NOT NULL REFERENCES terms(term_id),
  file_path TEXT NOT NULL,
  submitted_at TEXT,
  acad_status TEXT DEFAULT 'PENDING',
  acad_reviewer INTEGER, acad_comment TEXT, reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS bli05_industry (
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(user_id),
  term_id INTEGER NOT NULL REFERENCES terms(term_id),
  ind_supervisor_id INTEGER NOT NULL REFERENCES users(user_id),
  scores_json TEXT NOT NULL,
  total_raw REAL, weighted_30pct REAL,
  decision TEXT, comments_strengths TEXT, comments_others TEXT, submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS bli08_academic (
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(user_id),
  term_id INTEGER NOT NULL REFERENCES terms(term_id),
  acad_supervisor_id INTEGER NOT NULL REFERENCES users(user_id),
  scores_json TEXT NOT NULL,
  subtotal_clo1 REAL, subtotal_log REAL, subtotal_clo4 REAL,
  weighted_total REAL, submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS supervision (
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(user_id),
  term_id INTEGER NOT NULL REFERENCES terms(term_id),
  acad_supervisor_id INTEGER REFERENCES users(user_id),
  ind_supervisor_id INTEGER REFERENCES users(user_id),
  coordinator_id INTEGER NOT NULL REFERENCES users(user_id),
  assigned_at TEXT
);

CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES users(user_id),
  term_id INTEGER NOT NULL REFERENCES terms(term_id),
  weight_industry REAL DEFAULT 0.3,
  weight_academic REAL DEFAULT 0.7,
  score_industry REAL, score_academic REAL,
  final_score REAL, grade TEXT,
  computed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(user_id),
  action TEXT, entity TEXT, entity_id INTEGER, created_at TEXT
);

INSERT OR IGNORE INTO roles (role_id, role_name) VALUES
  (1, 'student'),
  (2, 'coordinator'),
  (3, 'acad_sv'),
  (4, 'ind_sv');

INSERT OR IGNORE INTO terms (term_id, session_label, start_date, end_date, bli01_deadline, bli02_deadline, logbook_freq, report_deadline)
VALUES (1, 'Oct 2025', '2025-10-01', '2026-02-28', '2025-10-15', '2025-11-01', 'WEEKLY', '2026-02-21');

INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (1,'2025001@student.uitm.edu.my','Pelajar Demo 01','dfc376f71d3530c2059331de730a7d28ba4fa2a39bbe5e1f27bf39519f24a4ac',1,'CS248','2025001','','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (2,'2025002@student.uitm.edu.my','Pelajar Demo 02','607121595d9455324a892749c4fac56dea834283bf840634e91b3ea2502720f6',1,'CS249','2025002','','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (3,'2025003@student.uitm.edu.my','Pelajar Demo 03','1e0b361c5cb7831de7a8552bf606a30ba847dea13a18e72e19ff4c081df2ab2c',1,'CS290','2025003','','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (4,'2025004@student.uitm.edu.my','Pelajar Demo 04','28e2b95ac4e1db5fb3ccc1c630b634f76ca372bfea1f03fb306d5afa0f0513a5',1,'CS241','2025004','','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (5,'2025005@student.uitm.edu.my','Pelajar Demo 05','c35e9e2b6284c374eac2d87b1093a14f76287f22d1b2b00e8d001c87392e9c18',1,'CS248','2025005','','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (6,'2025006@student.uitm.edu.my','Pelajar Demo 06','1404cb9051bca5cceacd47afb056cc32d6d256fb8a4984a881f4d93ccafa6c08',1,'CS249','2025006','','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (7,'2025007@student.uitm.edu.my','Pelajar Demo 07','5af0d49656f8f89349d4e4632446614ed84f5ceba56a9a1cd9fc815ae92c651f',1,'CS290','2025007','','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (8,'2025008@student.uitm.edu.my','Pelajar Demo 08','08da3631133c203477f82a37ffa9feaf075d708e033b80b3e82e1594e8dc7875',1,'CS241','2025008','','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (9,'2025009@student.uitm.edu.my','Pelajar Demo 09','d5275eb722747f6db639a9a595a6a8a0120dc009c9b946b96b768fed05489ea4',1,'CS248','2025009','','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (10,'2025010@student.uitm.edu.my','Pelajar Demo 10','1455861e2cf7058210427a8d8f6f7f127e3dcf77c0cd8f93afe4ca29e89587ce',1,'CS249','2025010','','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (101,'coordinator.cs248@uitm.edu.my','Penyelaras CS248','5805aa947c1127f8a506a255aa76627b8b94e1a76a74b83a58ea160ef70acb74',2,'CS248','','STF101','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (102,'coordinator.cs249@uitm.edu.my','Penyelaras CS249','b8de2334e25cc169541ece459b54bd3158a323e2b4f4dc51e496900cfb5e5fe8',2,'CS249','','STF102','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (103,'coordinator.cs290@uitm.edu.my','Penyelaras CS290','3e5f9a62f8bc968a228c71740f05a38bff7be4e0b1cf818b973e5df63c70bc03',2,'CS290','','STF103','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (201,'acadsv01@uitm.edu.my','Penyelia Akademik 01','e6d41df64dcd93930989289e82722831e2c86ba508a29937799e9d4309e4438a',3,'CS248','','STF201','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (202,'acadsv02@uitm.edu.my','Penyelia Akademik 02','8bd61f2b893d4eaa2f2ad3d5bffebdc2c93d81ad927738e06acfd94a12399aba',3,'CS249','','STF202','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (203,'acadsv03@uitm.edu.my','Penyelia Akademik 03','8b3f4e43e8740e47325a50503ad5baaffabf7dbfd05d3b0ae10f1117378c1cf8',3,'CS290','','STF203','',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (301,'indsv01@industry.example.com','Penyelia Industri 01','d0befba39e9c55b380a4f1a4a4796645686762357911bcd8fce448c448b6f1dc',4,'','','IND301','TechMaju Sdn Bhd',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (302,'indsv02@industry.example.com','Penyelia Industri 02','4b251d5450e263d100472fabdc056fbfddd277031c620b9c47ffc2a85fc5db50',4,'','','IND302','DataNusa Sdn Bhd',1);
INSERT OR REPLACE INTO users (user_id,email,full_name,password_hash,role_id,program_code,student_id,staff_id,industry_org,is_active) VALUES (303,'indsv03@industry.example.com','Penyelia Industri 03','4506a74c9f37d624d7b8f30c5f9ec7a95e8ed2dbe87e80c7d7425d50ea82b462',4,'','','IND303','InovasiHub Sdn Bhd',1);

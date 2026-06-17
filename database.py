import os, sqlite3, csv, re
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'noon_academy.db')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'Data')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn

def validate_phone(phone):
    if not phone: return "", True
    phone = str(phone).strip()
    if "@" in phone or ".com" in phone: return phone, True
    cleaned = re.sub(r'[\s\-()]+', '', phone)
    return (phone, True) if len(cleaned) < 7 or not re.match(r'^\+?[0-9]+$', cleaned) else (cleaned, False)

def init_db():
    conn = get_db_connection()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS students (student_id TEXT PRIMARY KEY, facilitator_email TEXT NOT NULL, ai_notes_adjustment REAL DEFAULT 0.0, ai_summary TEXT, ai_why TEXT);
        CREATE TABLE IF NOT EXISTS daily_metrics (metric_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, date TEXT NOT NULL, session_attended_min REAL, practice_questions INTEGER, last_quiz_score REAL, days_until_next_quiz INTEGER, FOREIGN KEY (student_id) REFERENCES students(student_id), UNIQUE(student_id, date));
        CREATE TABLE IF NOT EXISTS facilitator_notes (note_id TEXT PRIMARY KEY, student_id TEXT NOT NULL, facilitator_email TEXT NOT NULL, date TEXT NOT NULL, note_text TEXT NOT NULL, ai_summary TEXT, FOREIGN KEY (student_id) REFERENCES students(student_id));
        CREATE TABLE IF NOT EXISTS queue_status (student_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending', updated_at TEXT, notes TEXT, FOREIGN KEY (student_id) REFERENCES students(student_id));
        CREATE TABLE IF NOT EXISTS facilitator_actions (action_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, action_type TEXT NOT NULL, notes TEXT, created_at TEXT NOT NULL, FOREIGN KEY (student_id) REFERENCES students(student_id));
        CREATE TABLE IF NOT EXISTS system_cache (cache_key TEXT PRIMARY KEY, cache_value TEXT, updated_at TEXT);
    ''')
    for c in ['ai_notes_adjustment', 'ai_summary', 'ai_why']:
        try: conn.execute(f"ALTER TABLE students ADD COLUMN {c} {'REAL DEFAULT 0.0' if c=='ai_notes_adjustment' else 'TEXT'}")
        except sqlite3.OperationalError: pass
    conn.commit()
    conn.close()

def seed_db():
    conn = get_db_connection()
    c = conn.cursor()
    if c.execute("SELECT COUNT(*) FROM students").fetchone()[0] > 0: return conn.close()
    print("Seeding database from CSV files...")
    
    facils = {}
    n_path = os.path.join(DATA_DIR, 'facilitator_notes.csv')
    if os.path.exists(n_path):
        with open(n_path, 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f): facils[r['student_id']] = r['facilitator_email']

    m_path = os.path.join(DATA_DIR, 'student_daily_metrics.csv')
    if os.path.exists(m_path):
        with open(m_path, 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                sid = r['student_id']
                if sid not in facils: facils[sid] = "Unassigned"
                c.execute('''INSERT OR IGNORE INTO daily_metrics (student_id, date, session_attended_min, practice_questions, last_quiz_score, days_until_next_quiz) 
                             VALUES (?, ?, ?, ?, ?, ?)''', 
                          (sid, r['date'], float(r['session_attended_min'] or 0) or None, int(r['practice_questions'] or 0), float(r['last_quiz_score'] or 0) or None, int(r['days_until_next_quiz'] or 0) or None))

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for sid, email in facils.items():
        c.execute("INSERT INTO students (student_id, facilitator_email) VALUES (?, ?)", (sid, email))
        c.execute("INSERT INTO queue_status (student_id, status, updated_at) VALUES (?, 'pending', ?)", (sid, now))

    if os.path.exists(n_path):
        with open(n_path, 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                c.execute("INSERT INTO facilitator_notes (note_id, student_id, facilitator_email, date, note_text) VALUES (?, ?, ?, ?, ?)", 
                          (r['note_id'], r['student_id'], r['facilitator_email'], r['date'], r['note_text']))
                
    conn.commit()
    conn.close()
    print("Database seeding completed.")

if __name__ == "__main__":
    init_db()
    seed_db()

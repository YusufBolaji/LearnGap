import sqlite3
from pathlib import Path
from datetime import date
import hashlib
import pandas as pd
import streamlit as st
import plotly.express as px

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "learngap.db"

TOPICS = [
    "Number System", "Fractions", "Decimals", "Algebra",
    "Geometry", "Measurement", "Statistics", "Probability"
]

# -----------------------------
# Database helpers
# -----------------------------
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                full_name TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                student_name TEXT NOT NULL,
                class_name TEXT NOT NULL,
                gender TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assessments (
                assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                score REAL NOT NULL,
                max_score REAL NOT NULL,
                percentage REAL NOT NULL,
                gap_status TEXT NOT NULL,
                assessment_date TEXT NOT NULL,
                assessment_type TEXT NOT NULL DEFAULT 'Regular',
                intervention_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(student_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interventions (
                intervention_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                baseline_assessment_id INTEGER NOT NULL,
                intervention_title TEXT NOT NULL,
                intervention_action TEXT NOT NULL,
                start_date TEXT NOT NULL,
                target_reassessment_date TEXT,
                status TEXT NOT NULL DEFAULT 'Planned',
                teacher_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(student_id),
                FOREIGN KEY (baseline_assessment_id) REFERENCES assessments(assessment_id)
            )
        """)
        conn.commit()

def seed_default_users():
    defaults = [
        ("admin", hash_password("admin123"), "Administrator", "LearnGap Admin"),
        ("teacher", hash_password("teacher123"), "Teacher", "Demo Teacher"),
    ]
    with get_connection() as conn:
        for row in defaults:
            conn.execute("""
                INSERT OR IGNORE INTO users (username, password_hash, role, full_name)
                VALUES (?, ?, ?, ?)
            """, row)
        conn.commit()

def authenticate(username, password):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT username, role, full_name
            FROM users
            WHERE username = ? AND password_hash = ?
        """, (username.strip(), hash_password(password))).fetchone()
    return dict(row) if row else None

def classify_gap(pct):
    if pct >= 80:
        return "Mastered"
    if pct >= 60:
        return "Developing"
    if pct >= 40:
        return "Learning Gap"
    return "Critical Gap"

def next_student_id():
    with get_connection() as conn:
        row = conn.execute("""
            SELECT student_id FROM students
            WHERE student_id LIKE 'ST%'
            ORDER BY CAST(SUBSTR(student_id, 3) AS INTEGER) DESC
            LIMIT 1
        """).fetchone()
    return "ST001" if not row else f"ST{int(row['student_id'][2:]) + 1:03d}"

def add_student(name, class_name, gender, student_id=None):
    sid = student_id or next_student_id()
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO students
            (student_id, student_name, class_name, gender)
            VALUES (?, ?, ?, ?)
        """, (sid, name.strip(), class_name.strip(), gender))
        conn.commit()
    return sid

def add_assessment(student_id, subject, topic, score, max_score, assessment_date,
                   assessment_type="Regular", intervention_id=None):
    pct = round((float(score) / float(max_score)) * 100, 2)
    status = classify_gap(pct)
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO assessments
            (student_id, subject, topic, score, max_score, percentage, gap_status,
             assessment_date, assessment_type, intervention_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            student_id, subject, topic, float(score), float(max_score), pct, status,
            pd.to_datetime(assessment_date).date().isoformat(),
            assessment_type, intervention_id
        ))
        conn.commit()
        return cur.lastrowid, pct, status

def add_intervention(student_id, subject, topic, baseline_assessment_id,
                     title, action, start_date, target_date, status, notes):
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO interventions
            (student_id, subject, topic, baseline_assessment_id, intervention_title,
             intervention_action, start_date, target_reassessment_date, status, teacher_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            student_id, subject, topic, baseline_assessment_id, title.strip(),
            action.strip(), pd.to_datetime(start_date).date().isoformat(),
            pd.to_datetime(target_date).date().isoformat() if target_date else None,
            status, notes.strip()
        ))
        conn.commit()
        return cur.lastrowid

def update_intervention_status(intervention_id, status):
    with get_connection() as conn:
        conn.execute(
            "UPDATE interventions SET status = ? WHERE intervention_id = ?",
            (status, int(intervention_id))
        )
        conn.commit()

def load_students():
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT student_id, student_name, class_name, gender FROM students ORDER BY student_name",
            conn
        )

def load_assessments():
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT
                a.assessment_id,
                s.student_id,
                s.student_name,
                s.class_name,
                s.gender,
                a.subject,
                a.topic,
                a.score,
                a.max_score,
                a.percentage,
                a.gap_status,
                a.assessment_date,
                a.assessment_type,
                a.intervention_id
            FROM assessments a
            JOIN students s ON a.student_id = s.student_id
            ORDER BY a.assessment_date DESC, a.assessment_id DESC
        """, conn)

def load_interventions():
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT
                i.intervention_id,
                i.student_id,
                s.student_name,
                s.class_name,
                i.subject,
                i.topic,
                i.baseline_assessment_id,
                a.percentage AS baseline_percentage,
                i.intervention_title,
                i.intervention_action,
                i.start_date,
                i.target_reassessment_date,
                i.status,
                i.teacher_notes
            FROM interventions i
            JOIN students s ON i.student_id = s.student_id
            JOIN assessments a ON i.baseline_assessment_id = a.assessment_id
            ORDER BY i.intervention_id DESC
        """, conn)

def intervention_effectiveness_df():
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT
                i.intervention_id,
                s.student_name,
                s.class_name,
                i.subject,
                i.topic,
                i.intervention_title,
                i.status,
                base.percentage AS before_percentage,
                (
                    SELECT a2.percentage
                    FROM assessments a2
                    WHERE a2.intervention_id = i.intervention_id
                      AND a2.assessment_type = 'Reassessment'
                    ORDER BY a2.assessment_date DESC, a2.assessment_id DESC
                    LIMIT 1
                ) AS after_percentage
            FROM interventions i
            JOIN students s ON i.student_id = s.student_id
            JOIN assessments base ON base.assessment_id = i.baseline_assessment_id
            ORDER BY i.intervention_id DESC
        """, conn)

def seed_demo_data():
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM students").fetchone()["n"]
        if count > 0:
            return False

        students = [
            ("ST001", "Amina Yusuf", "JSS2", "Female"),
            ("ST002", "David Okafor", "JSS2", "Male"),
            ("ST003", "Fatima Bello", "JSS2", "Female"),
            ("ST004", "Samuel Adewale", "JSS2", "Male"),
            ("ST005", "Zainab Musa", "JSS2", "Female"),
        ]
        for row in students:
            conn.execute("""
                INSERT INTO students (student_id, student_name, class_name, gender)
                VALUES (?, ?, ?, ?)
            """, row)

        demo_scores = {
            "ST001": [72, 35, 65, 82, 54, 61, 76, 58],
            "ST002": [64, 42, 59, 74, 49, 57, 68, 53],
            "ST003": [81, 55, 73, 88, 63, 69, 84, 66],
            "ST004": [51, 28, 47, 62, 39, 45, 58, 41],
            "ST005": [69, 38, 66, 79, 57, 60, 72, 54],
        }

        baseline_id = None
        for sid, scores in demo_scores.items():
            for topic, pct in zip(TOPICS, scores):
                score = round(pct / 5, 1)
                cur = conn.execute("""
                    INSERT INTO assessments
                    (student_id, subject, topic, score, max_score, percentage, gap_status,
                     assessment_date, assessment_type)
                    VALUES (?, 'Mathematics', ?, ?, 20, ?, ?, '2026-07-01', 'Regular')
                """, (sid, topic, score, pct, classify_gap(pct)))
                if sid == "ST001" and topic == "Fractions":
                    baseline_id = cur.lastrowid

        cur = conn.execute("""
            INSERT INTO interventions
            (student_id, subject, topic, baseline_assessment_id, intervention_title,
             intervention_action, start_date, target_reassessment_date, status, teacher_notes)
            VALUES (
                'ST001', 'Mathematics', 'Fractions', ?,
                'Two-week Fractions Remediation',
                'Re-teach fraction fundamentals using visual models and guided practice.',
                '2026-07-02', '2026-07-15', 'Completed',
                'Student received three targeted support sessions.'
            )
        """, (baseline_id,))
        intervention_id = cur.lastrowid

        conn.execute("""
            INSERT INTO assessments
            (student_id, subject, topic, score, max_score, percentage, gap_status,
             assessment_date, assessment_type, intervention_id)
            VALUES ('ST001', 'Mathematics', 'Fractions', 13, 20, 65, 'Developing',
                    '2026-07-15', 'Reassessment', ?)
        """, (intervention_id,))
        conn.commit()
    return True

def bulk_import_excel(uploaded_file):
    xls = pd.ExcelFile(uploaded_file)
    imported_students = 0
    imported_assessments = 0

    if "Students" in xls.sheet_names:
        sdf = pd.read_excel(xls, "Students")
        required = {"Student_ID", "Student_Name", "Class"}
        if not required.issubset(sdf.columns):
            raise ValueError("Students sheet must contain Student_ID, Student_Name, and Class.")
        for _, row in sdf.iterrows():
            sid = str(row["Student_ID"]).strip()
            name = str(row["Student_Name"]).strip()
            cls = str(row["Class"]).strip()
            gender = str(row.get("Gender", "Prefer not to say")).strip()
            if sid and name and cls:
                add_student(name, cls, gender, sid)
                imported_students += 1

    if "Assessments" in xls.sheet_names:
        adf = pd.read_excel(xls, "Assessments")
        required = {
            "Student_ID", "Subject", "Topic", "Score",
            "Max_Score", "Assessment_Date"
        }
        if not required.issubset(adf.columns):
            raise ValueError(
                "Assessments sheet must contain Student_ID, Subject, Topic, "
                "Score, Max_Score, and Assessment_Date."
            )
        for _, row in adf.iterrows():
            sid = str(row["Student_ID"]).strip()
            add_assessment(
                sid,
                str(row["Subject"]).strip(),
                str(row["Topic"]).strip(),
                float(row["Score"]),
                float(row["Max_Score"]),
                pd.to_datetime(row["Assessment_Date"]).date()
            )
            imported_assessments += 1

    return imported_students, imported_assessments

# -----------------------------
# App setup and styling
# -----------------------------
st.set_page_config(
    page_title="LearnGap",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
:root {
    --navy: #111238;
    --navy-2: #171844;
    --purple: #6E3DF4;
    --purple-2: #8B5CF6;
    --blue: #2F80ED;
    --cyan: #32C5E8;
    --green: #22C55E;
    --lime: #B8F34A;
    --orange: #F59E0B;
    --red: #F43F5E;
    --ink: #17172F;
    --muted: #6B6B86;
    --surface: #FFFFFF;
    --bg: #F7F8FC;
    --border: #E8EAF2;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}

.stApp {
    background:
        radial-gradient(circle at 86% 4%, rgba(111,61,244,.08), transparent 26rem),
        #F7F8FC;
    color: var(--ink);
}

.block-container {
    max-width: 1500px;
    padding-top: 1.1rem;
    padding-bottom: 3rem;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #111238 0%, #151640 100%);
    border-right: 1px solid rgba(255,255,255,.04);
}
section[data-testid="stSidebar"] * {
    color: #F7F7FF;
}
section[data-testid="stSidebar"] > div {
    padding-top: 1.1rem;
}
.sidebar-brand {
    padding: .2rem .2rem 1rem .2rem;
}
.sidebar-logo {
    font-size: 1.7rem;
    font-weight: 900;
    letter-spacing: -.04em;
    margin-bottom: .45rem;
}
.sidebar-logo span {
    color: #8B5CF6;
}
.sidebar-tagline {
    color: rgba(255,255,255,.72) !important;
    line-height: 1.55;
    font-size: .92rem;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] > label {
    display: none;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {
    border-radius: 12px;
    padding: .45rem .6rem;
    margin: .15rem 0;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: rgba(255,255,255,.07);
}
section[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    border-radius: 12px;
    background: rgba(255,255,255,.04);
    color: white;
    border: 1px solid rgba(255,255,255,.14);
}
section[data-testid="stSidebar"] .stButton > button:hover {
    border-color: #8B5CF6;
    color: #B8F34A;
}

/* Top content */
.topbar {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 1.2rem;
}
.page-title {
    font-size: 2rem;
    font-weight: 900;
    letter-spacing: -.035em;
    margin: 0;
    color: #17172F;
}
.welcome-line {
    font-size: 1.15rem;
    font-weight: 800;
    margin-top: .35rem;
    color: #17172F;
}
.page-subtitle {
    color: #66667F;
    margin-top: .15rem;
}

/* KPI cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 1rem;
    margin: 1rem 0 1.2rem 0;
}
.kpi-card {
    background: rgba(255,255,255,.96);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 1.15rem;
    box-shadow: 0 10px 28px rgba(17,18,56,.06);
    min-height: 165px;
}
.kpi-top {
    display: flex;
    align-items: center;
    gap: .85rem;
}
.kpi-icon {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 13px;
    font-size: 1.3rem;
    color: white;
    font-weight: 900;
}
.kpi-value {
    font-size: 1.9rem;
    font-weight: 900;
    line-height: 1;
}
.kpi-label {
    font-weight: 800;
    margin-top: .35rem;
}
.kpi-note {
    color: var(--muted);
    font-size: .84rem;
    margin-top: .35rem;
}
.purple {background: linear-gradient(135deg,#8B5CF6,#6E3DF4);}
.blue {background: linear-gradient(135deg,#49A5FF,#2F80ED);}
.orange {background: linear-gradient(135deg,#FFBE3D,#F59E0B);}
.red {background: linear-gradient(135deg,#FF6B7D,#F43F5E);}
.green {background: linear-gradient(135deg,#4ED273,#22C55E);}

/* Section cards */
.section-card {
    background: rgba(255,255,255,.97);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 1.15rem 1.2rem;
    box-shadow: 0 10px 28px rgba(17,18,56,.055);
    margin-bottom: 1rem;
}
.section-title {
    font-size: 1.1rem;
    font-weight: 900;
    margin-bottom: .25rem;
}
.section-caption {
    color: var(--muted);
    font-size: .88rem;
}

/* Native Streamlit cards/charts/tables */
[data-testid="stMetric"] {
    background: white;
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 1rem;
    box-shadow: 0 8px 24px rgba(17,18,56,.05);
}
[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {
    background: white;
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: .35rem;
    box-shadow: 0 8px 24px rgba(17,18,56,.045);
}
div[data-baseweb="select"] > div,
.stTextInput input,
.stNumberInput input,
.stDateInput input,
.stTextArea textarea {
    border-radius: 12px !important;
    border-color: #E2E4EF !important;
    background: white !important;
}
.stButton > button,
.stFormSubmitButton > button,
.stDownloadButton > button {
    border: 0;
    border-radius: 12px;
    background: linear-gradient(135deg,#7C4DFF,#6338EA);
    color: white;
    font-weight: 800;
    box-shadow: 0 7px 18px rgba(110,61,244,.2);
}
.stButton > button:hover,
.stFormSubmitButton > button:hover,
.stDownloadButton > button:hover {
    color: white;
    transform: translateY(-1px);
}
div[data-testid="stAlert"] {
    border-radius: 14px;
}

/* Login */
.login-shell {
    max-width: 760px;
    margin: 3vh auto 1rem auto;
}
.login-brand {
    text-align: center;
    margin-bottom: 1.25rem;
}
.login-mark {
    width: 78px;
    height: 78px;
    margin: 0 auto .9rem;
    border-radius: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg,#8B5CF6,#6338EA);
    color: white;
    font-size: 2rem;
    box-shadow: 0 15px 35px rgba(110,61,244,.25);
}
.login-brand h1 {
    font-size: 2.65rem;
    letter-spacing: -.05em;
    margin: 0;
}
.login-brand h1 span {
    color: #7C4DFF;
}
.login-brand p {
    color: var(--muted);
    margin-top: .45rem;
}
@media (max-width: 1100px) {
    .kpi-grid {grid-template-columns: repeat(2, minmax(0,1fr));}
}
@media (max-width: 700px) {
    .kpi-grid {grid-template-columns: 1fr;}
}
</style>
""", unsafe_allow_html=True)

init_db()
seed_default_users()

# -----------------------------
# Login
# -----------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.markdown("""
    <div class="login-shell">
      <div class="login-brand">
        <div class="login-mark">◫</div>
        <h1>Learn<span>Gap</span></h1>
        <p>See the gap. Target the support. Measure the growth.</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("Welcome back")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
        if submitted:
            user = authenticate(username, password)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid username or password.")

    st.stop()

user = st.session_state.user

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
      <div class="sidebar-logo">◫ Learn<span>Gap</span></div>
      <div class="sidebar-tagline">See the gap. Target the support. Measure the growth.</div>
    </div>
    """, unsafe_allow_html=True)

    navigation = {
        "⌂  Overview": "Dashboard",
        "♙  Students": "Add Student",
        "▣  Assessments": "Add Assessment",
        "↗  Learning Analysis": "Student Analysis",
        "◎  Intervention Plans": "Create Intervention",
        "↻  Reassessments": "Record Reassessment",
        "↗  Impact": "Intervention Impact",
        "⇧  Data Import": "Bulk Excel Upload",
        "◉  Data Centre": "Data Explorer",
    }
    selected_page = st.radio("Navigation", list(navigation.keys()))
    page = navigation[selected_page]

    st.divider()
    st.markdown(f"**{user['full_name']}**")
    st.caption(user["role"])

    st.divider()
    if st.button("Load demo data"):
        if seed_demo_data():
            st.success("Demo data loaded.")
        else:
            st.info("Database already contains student data.")

    if st.button("Sign out"):
        st.session_state.user = None
        st.rerun()

st.markdown(f"""
<div class="topbar">
  <div>
    <div class="page-title">Overview</div>
    <div class="welcome-line">Good to see you, {user['full_name']} 👋</div>
    <div class="page-subtitle">Track learning gaps, prioritize support, and measure student growth.</div>
  </div>
</div>
""", unsafe_allow_html=True)

students_df = load_students()
assessments_df = load_assessments()
interventions_df = load_interventions()
impact_df = intervention_effectiveness_df()

# -----------------------------
# Dashboard
# -----------------------------
if page == "Dashboard":
    st.markdown("")

    if assessments_df.empty:
        st.info("No assessment data yet.")
    else:
        filtered = assessments_df.copy()
        filtered["assessment_date"] = pd.to_datetime(filtered["assessment_date"])

        f1, f2, f3 = st.columns(3)
        class_options = ["All"] + sorted(filtered["class_name"].dropna().unique().tolist())
        selected_class = f1.selectbox("Class", class_options)

        topic_options = ["All"] + sorted(filtered["topic"].dropna().unique().tolist())
        selected_topic = f2.selectbox("Topic", topic_options)

        min_date = filtered["assessment_date"].min().date()
        max_date = filtered["assessment_date"].max().date()
        date_range = f3.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

        if selected_class != "All":
            filtered = filtered[filtered["class_name"] == selected_class]
        if selected_topic != "All":
            filtered = filtered[filtered["topic"] == selected_topic]
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
            filtered = filtered[
                (filtered["assessment_date"] >= start) &
                (filtered["assessment_date"] <= end)
            ]

        regular_df = filtered[filtered["assessment_type"] == "Regular"]
        data_for_kpis = regular_df if not regular_df.empty else filtered

        if data_for_kpis.empty:
            st.warning("No records match the selected filters.")
        else:
            total_students = data_for_kpis["student_id"].nunique()
            avg_performance = data_for_kpis["percentage"].mean()
            learning_gap_count = int((data_for_kpis["gap_status"] == "Learning Gap").sum())
            critical_gap_count = int((data_for_kpis["gap_status"] == "Critical Gap").sum())

            completed_for_kpi = impact_df.dropna(subset=["after_percentage"]).copy()
            if not completed_for_kpi.empty:
                completed_for_kpi["improvement"] = (
                    completed_for_kpi["after_percentage"] - completed_for_kpi["before_percentage"]
                )
                avg_improvement = completed_for_kpi["improvement"].mean()
                avg_improvement_text = f"{avg_improvement:+.1f}%"
            else:
                avg_improvement_text = "N/A"

            st.markdown(f"""
            <div class="kpi-grid">
              <div class="kpi-card">
                <div class="kpi-top">
                  <div class="kpi-icon purple">♙</div>
                  <div>
                    <div class="kpi-value" style="color:#6E3DF4">{total_students}</div>
                    <div class="kpi-label">Total Students</div>
                    <div class="kpi-note">Across all classes</div>
                  </div>
                </div>
              </div>
              <div class="kpi-card">
                <div class="kpi-top">
                  <div class="kpi-icon blue">▥</div>
                  <div>
                    <div class="kpi-value" style="color:#2F80ED">{avg_performance:.1f}%</div>
                    <div class="kpi-label">Average Performance</div>
                    <div class="kpi-note">All assessments</div>
                  </div>
                </div>
              </div>
              <div class="kpi-card">
                <div class="kpi-top">
                  <div class="kpi-icon orange">!</div>
                  <div>
                    <div class="kpi-value" style="color:#F59E0B">{learning_gap_count}</div>
                    <div class="kpi-label">Learning Gaps</div>
                    <div class="kpi-note">Need support</div>
                  </div>
                </div>
              </div>
              <div class="kpi-card">
                <div class="kpi-top">
                  <div class="kpi-icon red">!</div>
                  <div>
                    <div class="kpi-value" style="color:#F43F5E">{critical_gap_count}</div>
                    <div class="kpi-label">Critical Gaps</div>
                    <div class="kpi-note">Urgent attention</div>
                  </div>
                </div>
              </div>
              <div class="kpi-card">
                <div class="kpi-top">
                  <div class="kpi-icon green">↗</div>
                  <div>
                    <div class="kpi-value" style="color:#22C55E">{avg_improvement_text}</div>
                    <div class="kpi-label">Avg. Improvement</div>
                    <div class="kpi-note">After interventions</div>
                  </div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            topic_summary = (
                data_for_kpis.groupby("topic", as_index=False)["percentage"]
                .mean()
                .sort_values("percentage")
            )
            st.markdown("### Topic Performance")
            fig = px.bar(
                topic_summary,
                x="percentage",
                y="topic",
                orientation="h",
                text=topic_summary["percentage"].round(1)
            )
            fig.update_layout(
                xaxis_title="Average Percentage",
                yaxis_title="Topic",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#17172F"),
                margin=dict(l=10, r=10, t=20, b=10),
                showlegend=False
            )
            fig.update_xaxes(gridcolor="rgba(17,18,56,.08)", zeroline=False)
            fig.update_yaxes(gridcolor="rgba(0,0,0,0)", zeroline=False)
            st.plotly_chart(fig, use_container_width=True)

            gaps = data_for_kpis[
                data_for_kpis["gap_status"].isin(["Learning Gap", "Critical Gap"])
            ]
            if not gaps.empty:
                priority = (
                    gaps.groupby(["student_id", "student_name"], as_index=False)
                    .agg(
                        gap_count=("topic", "count"),
                        average_score=("percentage", "mean")
                    )
                    .sort_values(["gap_count", "average_score"], ascending=[False, True])
                )
                st.markdown("### Priority Support List")
                st.dataframe(priority, use_container_width=True, hide_index=True)

            completed = impact_df.dropna(subset=["after_percentage"]).copy()
            if not completed.empty:
                completed["improvement"] = (
                    completed["after_percentage"] - completed["before_percentage"]
                )
                st.markdown("### Intervention Impact Snapshot")
                k1, k2, k3 = st.columns(3)
                k1.metric("Reassessed Interventions", len(completed))
                k2.metric("Average Improvement", f"{completed['improvement'].mean():.1f} pts")
                k3.metric("Improved Outcomes", f"{(completed['improvement'] > 0).mean() * 100:.0f}%")

elif page == "Add Student":
    st.subheader("Students")
    with st.form("add_student_form", clear_on_submit=True):
        name = st.text_input("Student name")
        class_name = st.selectbox("Class", ["JSS1", "JSS2", "JSS3", "SS1", "SS2", "SS3"])
        gender = st.selectbox("Gender", ["Female", "Male", "Prefer not to say"])
        submitted = st.form_submit_button("Save Student")
        if submitted:
            if not name.strip():
                st.error("Please enter the student's name.")
            else:
                sid = add_student(name, class_name, gender)
                st.success(f"Student saved with ID **{sid}**.")
                st.rerun()

elif page == "Add Assessment":
    st.subheader("Assessments")
    if students_df.empty:
        st.warning("Add a student first.")
    else:
        labels = {
            f"{r.student_name} ({r.student_id})": r.student_id
            for r in students_df.itertuples()
        }
        with st.form("assessment_form", clear_on_submit=True):
            selected = st.selectbox("Student", list(labels.keys()))
            subject = st.selectbox("Subject", ["Mathematics"])
            topic = st.selectbox("Topic", TOPICS)
            c1, c2 = st.columns(2)
            score = c1.number_input("Score", min_value=0.0, value=10.0, step=1.0)
            max_score = c2.number_input("Maximum score", min_value=1.0, value=20.0, step=1.0)
            assessment_date = st.date_input("Assessment date", value=date.today())
            submitted = st.form_submit_button("Save Assessment")
            if submitted:
                if score > max_score:
                    st.error("Score cannot exceed maximum score.")
                else:
                    _, pct, status = add_assessment(
                        labels[selected], subject, topic, score, max_score, assessment_date
                    )
                    st.success(f"Assessment saved: **{pct:.1f}% — {status}**")
                    st.rerun()

elif page == "Student Analysis":
    st.subheader("Learning Analysis")
    if assessments_df.empty:
        st.info("No assessment data available.")
    else:
        options = assessments_df[["student_id", "student_name"]].drop_duplicates().sort_values("student_name")
        labels = {f"{r.student_name} ({r.student_id})": r.student_id for r in options.itertuples()}
        selected = st.selectbox("Select student", list(labels.keys()))
        sid = labels[selected]
        data = assessments_df[assessments_df["student_id"] == sid].copy()

        latest = (
            data.sort_values(["assessment_date", "assessment_id"])
            .groupby("topic", as_index=False)
            .tail(1)
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Latest Average", f"{latest['percentage'].mean():.1f}%")
        c2.metric("Topics Assessed", latest["topic"].nunique())
        c3.metric(
            "Topics Needing Support",
            latest[latest["gap_status"].isin(["Learning Gap", "Critical Gap"])]["topic"].nunique()
        )

        fig = px.bar(
            latest.sort_values("percentage"),
            x="topic",
            y="percentage",
            text=latest.sort_values("percentage")["percentage"].round(1)
        )
        fig.update_yaxes(range=[0, 100], gridcolor="rgba(17,18,56,.08)", zeroline=False)
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#17172F")
        )
        st.plotly_chart(fig, use_container_width=True)

        gaps = latest[latest["gap_status"].isin(["Learning Gap", "Critical Gap"])]
        st.markdown("### Recommended Actions")
        if gaps.empty:
            st.success("No current learning gaps detected.")
        else:
            for row in gaps.sort_values("percentage").itertuples():
                message = (
                    "Provide foundational remediation and reassess within one week."
                    if row.gap_status == "Critical Gap"
                    else "Re-teach the topic, provide targeted exercises, and reassess within 1–2 weeks."
                )
                st.warning(f"**{row.topic}: {row.percentage:.1f}% — {row.gap_status}.** {message}")

elif page == "Create Intervention":
    st.subheader("Intervention Plans")
    eligible = assessments_df[
        assessments_df["gap_status"].isin(["Learning Gap", "Critical Gap"])
    ].copy()

    if eligible.empty:
        st.info("No learning-gap assessment is available.")
    else:
        eligible["label"] = eligible.apply(
            lambda r: (
                f"{r['student_name']} | {r['topic']} | "
                f"{r['percentage']:.1f}% | {r['assessment_date']} | ID {r['assessment_id']}"
            ),
            axis=1
        )
        with st.form("intervention_form", clear_on_submit=True):
            selected_label = st.selectbox("Baseline learning gap", eligible["label"].tolist())
            row = eligible[eligible["label"] == selected_label].iloc[0]
            title = st.text_input("Intervention title", value=f"{row['topic']} Support Plan")
            action = st.text_area(
                "Intervention action",
                value="Re-teach the topic, provide targeted exercises, and monitor progress."
            )
            c1, c2 = st.columns(2)
            start_date = c1.date_input("Start date", value=date.today())
            target_date = c2.date_input("Target reassessment date", value=date.today())
            status = st.selectbox("Status", ["Planned", "In Progress", "Completed"])
            notes = st.text_area("Teacher notes")
            submitted = st.form_submit_button("Create Intervention")

            if submitted:
                intervention_id = add_intervention(
                    row["student_id"], row["subject"], row["topic"],
                    int(row["assessment_id"]), title, action,
                    start_date, target_date, status, notes
                )
                st.success(f"Intervention created with reference **#{intervention_id}**.")
                st.rerun()

elif page == "Record Reassessment":
    st.subheader("Reassessments")
    if interventions_df.empty:
        st.info("Create an intervention first.")
    else:
        active = interventions_df.copy()
        active["label"] = active.apply(
            lambda r: (
                f"#{r['intervention_id']} | {r['student_name']} | {r['topic']} | "
                f"Baseline {r['baseline_percentage']:.1f}% | {r['status']}"
            ),
            axis=1
        )
        selected_label = st.selectbox("Select intervention", active["label"].tolist())
        row = active[active["label"] == selected_label].iloc[0]

        st.info(f"Baseline: **{row['baseline_percentage']:.1f}%** in **{row['topic']}**")

        with st.form("reassessment_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            score = c1.number_input("Reassessment score", min_value=0.0, value=10.0, step=1.0)
            max_score = c2.number_input("Maximum score", min_value=1.0, value=20.0, step=1.0)
            assessment_date = st.date_input("Reassessment date", value=date.today())
            mark_completed = st.checkbox("Mark intervention as Completed", value=True)
            submitted = st.form_submit_button("Save Reassessment")

            if submitted:
                if score > max_score:
                    st.error("Score cannot exceed maximum score.")
                else:
                    _, pct, status = add_assessment(
                        row["student_id"], row["subject"], row["topic"],
                        score, max_score, assessment_date,
                        "Reassessment", int(row["intervention_id"])
                    )
                    improvement = pct - row["baseline_percentage"]
                    if mark_completed:
                        update_intervention_status(int(row["intervention_id"]), "Completed")
                    st.success(
                        f"Reassessment saved: **{pct:.1f}% ({status})**. "
                        f"Change from baseline: **{improvement:+.1f} percentage points**."
                    )
                    st.rerun()

elif page == "Intervention Impact":
    st.subheader("Impact")
    if impact_df.empty:
        st.info("No interventions recorded yet.")
    else:
        impact = impact_df.copy()
        impact["improvement"] = impact["after_percentage"] - impact["before_percentage"]
        impact["outcome"] = impact["improvement"].apply(
            lambda x: "Awaiting Reassessment" if pd.isna(x)
            else ("Improved" if x > 0 else ("No Change" if x == 0 else "Declined"))
        )

        completed = impact.dropna(subset=["after_percentage"]).copy()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Interventions", len(impact))
        c2.metric("Reassessed", len(completed))
        c3.metric(
            "Average Improvement",
            f"{completed['improvement'].mean():.1f} pts" if not completed.empty else "N/A"
        )
        c4.metric(
            "Improvement Rate",
            f"{(completed['improvement'] > 0).mean() * 100:.0f}%"
            if not completed.empty else "N/A"
        )

        st.dataframe(
            impact[
                [
                    "student_name", "class_name", "topic", "intervention_title",
                    "before_percentage", "after_percentage", "improvement",
                    "outcome", "status"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

        if not completed.empty:
            fig = px.bar(
                completed.sort_values("improvement"),
                x="student_name",
                y="improvement",
                hover_data=["topic", "before_percentage", "after_percentage"],
                text=completed.sort_values("improvement")["improvement"].round(1)
            )
            fig.update_layout(
                xaxis_title="Student",
                yaxis_title="Improvement (percentage points)",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#17172F")
            )
            st.plotly_chart(fig, use_container_width=True)

elif page == "Bulk Excel Upload":
    st.subheader("Data Import")
    st.write(
        "Upload an Excel workbook with a **Students** sheet and/or an **Assessments** sheet."
    )

    template_students = pd.DataFrame({
        "Student_ID": ["ST101", "ST102"],
        "Student_Name": ["Example Student One", "Example Student Two"],
        "Class": ["JSS2", "JSS2"],
        "Gender": ["Female", "Male"]
    })
    template_assessments = pd.DataFrame({
        "Student_ID": ["ST101", "ST102"],
        "Subject": ["Mathematics", "Mathematics"],
        "Topic": ["Fractions", "Algebra"],
        "Score": [8, 15],
        "Max_Score": [20, 20],
        "Assessment_Date": ["2026-07-15", "2026-07-15"]
    })

    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        template_students.to_excel(writer, sheet_name="Students", index=False)
        template_assessments.to_excel(writer, sheet_name="Assessments", index=False)
    st.download_button(
        "Download Excel upload template",
        data=output.getvalue(),
        file_name="LearnGap_Upload_Template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    uploaded = st.file_uploader("Choose Excel file", type=["xlsx"])
    if uploaded is not None and st.button("Import Workbook"):
        try:
            n_students, n_assessments = bulk_import_excel(uploaded)
            st.success(
                f"Import complete: {n_students} students and "
                f"{n_assessments} assessments processed."
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Import failed: {exc}")

elif page == "Data Explorer":
    st.subheader("Data Centre")
    t1, t2, t3 = st.tabs(["Students", "Assessments", "Interventions"])
    with t1:
        st.dataframe(students_df, use_container_width=True, hide_index=True)
    with t2:
        st.dataframe(assessments_df, use_container_width=True, hide_index=True)
        if not assessments_df.empty:
            st.download_button(
                "Download assessments CSV",
                data=assessments_df.to_csv(index=False).encode("utf-8"),
                file_name="learngap_assessments.csv",
                mime="text/csv"
            )
    with t3:
        st.dataframe(interventions_df, use_container_width=True, hide_index=True)

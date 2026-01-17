import os
import uuid
import sqlite3
from datetime import datetime, date
from io import BytesIO

import pandas as pd
import streamlit as st

# ----------------------------
# Config
# ----------------------------
DB_PATH = "faculty_data.db"
UPLOAD_DIR = "uploads"
DEFAULT_DATE = date.today()

os.makedirs(UPLOAD_DIR, exist_ok=True)
st.set_page_config(page_title="Faculty Data Collection", layout="wide")


# ----------------------------
# DB helpers
# ----------------------------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Core
    cur.execute("""
    CREATE TABLE IF NOT EXISTS faculty (
        faculty_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        designation TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS membership (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        body_name TEXT NOT NULL,
        membership_number TEXT NOT NULL,
        level TEXT NOT NULL,
        grade_position TEXT NOT NULL,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    # FDP/STTP/etc (will be migrated via ensure_column if DB already exists)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fdp_sttp (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        program_type TEXT,                -- FDP / STTP / SWAYAM / NPTEL / MOOCs
        program_name TEXT,                -- Name of FDP/STTP/etc
        involvement TEXT NOT NULL,        -- Attended/Organised
        date TEXT NOT NULL,
        location TEXT NOT NULL,
        organised_by TEXT NOT NULL,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        date TEXT NOT NULL,
        course_name TEXT NOT NULL,
        offered_by TEXT NOT NULL,
        grade TEXT NOT NULL,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_projects_support (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        project_name TEXT NOT NULL,
        event_date TEXT NOT NULL,
        place TEXT NOT NULL,
        website_link TEXT,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS industry_collab (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        activity_name TEXT NOT NULL,
        company_place TEXT NOT NULL,
        duration TEXT NOT NULL,
        outcomes TEXT NOT NULL,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    # Academic Research: Journal + Conference together
    cur.execute("""
    CREATE TABLE IF NOT EXISTS publications_jc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        pub_type TEXT NOT NULL,           -- Journal / Conference
        title TEXT NOT NULL,
        doi TEXT NOT NULL,
        pub_date TEXT NOT NULL,           -- ISO date string YYYY-MM-DD
        pdf_path TEXT NOT NULL,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    # Books / Book Chapters
    cur.execute("""
    CREATE TABLE IF NOT EXISTS books_chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        item_type TEXT NOT NULL,          -- Book / Book Chapter
        title TEXT NOT NULL,
        publisher TEXT,
        pub_date TEXT,                    -- ISO date string or blank
        pdf_path TEXT,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    # Patents / Working models / Prototypes (last 3 years)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS patents_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        item_type TEXT NOT NULL,          -- Patent Granted / Working Model / Prototype
        title TEXT NOT NULL,
        item_date TEXT NOT NULL,          -- ISO date string
        details TEXT,
        pdf_path TEXT,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    # Sponsored projects (CAY removed; date used)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sponsored_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        project_date TEXT,                -- ISO date string
        pi_name TEXT NOT NULL,
        co_pi TEXT,
        dept_sanctioned TEXT NOT NULL,
        project_title TEXT NOT NULL,
        funding_agency TEXT NOT NULL,
        duration TEXT NOT NULL,
        amount_lakhs REAL NOT NULL,
        status TEXT NOT NULL,             -- Ongoing/Completed
        sanction_pdf_path TEXT,           -- uploaded file path
        completion_pdf_path TEXT,         -- uploaded file path
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    conn.commit()

    # Migrations for older DBs
    ensure_column(conn, "fdp_sttp", "program_type", "TEXT")
    ensure_column(conn, "fdp_sttp", "program_name", "TEXT")
    ensure_column(conn, "sponsored_projects", "project_date", "TEXT")

    conn.close()


def save_uploaded_file(file_obj, subdir):
    if file_obj is None:
        return None
    os.makedirs(os.path.join(UPLOAD_DIR, subdir), exist_ok=True)
    ext = os.path.splitext(file_obj.name)[-1].lower()
    fname = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, subdir, fname)
    with open(path, "wb") as f:
        f.write(file_obj.getbuffer())
    return path


def fetch_table_df(table_name: str) -> pd.DataFrame:
    conn = get_conn()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    finally:
        conn.close()
    return df


def make_excel_bytes(dfs: dict) -> bytes:
    buffer = BytesIO()
    # openpyxl is optional; call only if installed
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            safe_sheet = sheet[:31]  # Excel sheet name limit
            df.to_excel(writer, sheet_name=safe_sheet, index=False)
    buffer.seek(0)
    return buffer.getvalue()


# ----------------------------
# Session state helpers
# ----------------------------
def ensure_list_state(key, default_item):
    if key not in st.session_state:
        st.session_state[key] = [default_item]


def add_item(key, item):
    st.session_state[key].append(item)


def remove_item(key, idx):
    if len(st.session_state[key]) > 1:
        st.session_state[key].pop(idx)


# ----------------------------
# UI
# ----------------------------
init_db()

tab_entry, tab_admin = st.tabs(["📝 Data Entry", "🔐 Admin"])

# ============================
# TAB 1: DATA ENTRY
# ============================
with tab_entry:
    st.title("Faculty Data Collection Web App")
    st.info("Repeatable sections support ➕ Add buttons. Upload PDFs where required.")

    # Repeatable sections
    ensure_list_state("memberships", {"body_name": "", "membership_number": "", "level": "National", "grade_position": ""})

    # FDP/STTP tweak: type + name added
    ensure_list_state("fdps", {
        "program_type": "FDP",
        "program_name": "",
        "involvement": "Attended",
        "date": "",
        "location": "",
        "organised_by": ""
    })

    ensure_list_state("courses", {"date": "", "course_name": "", "offered_by": "", "grade": ""})
    ensure_list_state("student_support", {"project_name": "", "event_date": "", "place": "", "website_link": ""})
    ensure_list_state("industry", {"activity_name": "", "company_place": "", "duration": "", "outcomes": ""})

    # Academic Research
    ensure_list_state("pubs_jc", {"pub_type": "Journal", "title": "", "doi": "", "pub_date": DEFAULT_DATE, "pdf": None})
    ensure_list_state("books", {"item_type": "Book", "title": "", "publisher": "", "pub_date": DEFAULT_DATE, "pdf": None})

    # NEW: patents/models/prototypes (shown only if user says Yes)
    ensure_list_state("patents_models", {
        "item_type": "Patent Granted",
        "title": "",
        "item_date": DEFAULT_DATE,
        "details": "",
        "pdf": None
    })

    # Sponsored projects
    ensure_list_state("sponsored", {
        "project_date": DEFAULT_DATE,
        "pi_name": "", "co_pi": "",
        "dept_sanctioned": "",
        "project_title": "", "funding_agency": "", "duration": "", "amount_lakhs": 0.0,
        "status": "Ongoing",
        "sanction_pdf": None, "completion_pdf": None
    })

    # 1. Basic Details
    st.subheader("1. Basic Details")
    name = st.text_input("Name of the Faculty *", key="faculty_name")
    designation = st.selectbox("Designation *", ["AP", "Associate Professor", "Professor"], key="designation")
    st.divider()

    # 2. Professional Membership
    st.subheader("2. Professional Membership")
    has_membership = st.radio("Professional Membership (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_membership")

    if has_membership == "Yes":
        st.caption("Use ➕ Add Membership to enter multiple memberships neatly.")
        for i, m in enumerate(st.session_state["memberships"]):
            cols = st.columns([3, 3, 2, 3, 1])
            m["body_name"] = cols[0].text_input("Body Name *", value=m["body_name"], key=f"m_body_{i}")
            m["membership_number"] = cols[1].text_input("Membership Number *", value=m["membership_number"], key=f"m_no_{i}")
            m["level"] = cols[2].selectbox(
                "Level *", ["National", "International"],
                index=0 if m["level"] == "National" else 1,
                key=f"m_lvl_{i}"
            )
            m["grade_position"] = cols[3].text_input("Level/Grade/Position *", value=m["grade_position"], key=f"m_pos_{i}")
            if cols[4].button("➖", key=f"m_rm_{i}"):
                remove_item("memberships", i)
                st.rerun()

        if st.button("➕ Add Membership", key="add_membership"):
            add_item("memberships", {"body_name": "", "membership_number": "", "level": "National", "grade_position": ""})
            st.rerun()

    st.divider()

    # 3. FDP/STTP Resource person (UPDATED)
    st.subheader("3. As resource person in FDP/STTP")
    has_fdp = st.radio("Resource person entries (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_fdp")

    if has_fdp == "Yes":
        st.caption("Select type first, then fill the details. Add multiple entries if required.")
        for i, f in enumerate(st.session_state["fdps"]):
            cols0 = st.columns([2.2, 3.8, 1])
            f["program_type"] = cols0[0].selectbox(
                "Select Type *", ["FDP", "STTP", "SWAYAM", "NPTEL", "MOOCs"],
                key=f"f_type_{i}"
            )
            f["program_name"] = cols0[1].text_input(
                f"Name of {f['program_type']} *",
                value=f["program_name"],
                key=f"f_name_{i}"
            )
            if cols0[2].button("➖", key=f"f_rm_{i}"):
                remove_item("fdps", i)
                st.rerun()

            cols = st.columns([2, 2, 3, 3])
            f["involvement"] = cols[0].selectbox("Attended / Organised *", ["Attended", "Organised"], key=f"f_inv_{i}")
            f["date"] = cols[1].text_input("Date (DD/MM/YYYY) *", value=f["date"], key=f"f_date_{i}")
            f["location"] = cols[2].text_input("Location *", value=f["location"], key=f"f_loc_{i}")
            f["organised_by"] = cols[3].text_input("Organised By *", value=f["organised_by"], key=f"f_org_{i}")

            st.markdown("---")

        if st.button("➕ Add Entry", key="add_fdp"):
            add_item("fdps", {
                "program_type": "FDP",
                "program_name": "",
                "involvement": "Attended",
                "date": "",
                "location": "",
                "organised_by": ""
            })
            st.rerun()

    st.divider()

    # 4. Courses Passed
    st.subheader("4. Courses Passed")
    has_courses = st.radio("Courses Passed (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_courses")

    if has_courses == "Yes":
        st.caption("Add multiple course entries.")
        for i, c in enumerate(st.session_state["courses"]):
            cols = st.columns([2, 3, 3, 2, 1])
            c["date"] = cols[0].text_input("Date (DD/MM/YYYY) *", value=c["date"], key=f"c_date_{i}")
            c["course_name"] = cols[1].text_input("Course Name *", value=c["course_name"], key=f"c_name_{i}")
            c["offered_by"] = cols[2].text_input("Course Offered By *", value=c["offered_by"], key=f"c_by_{i}")
            c["grade"] = cols[3].text_input("Grade Obtained *", value=c["grade"], key=f"c_grade_{i}")
            if cols[4].button("➖", key=f"c_rm_{i}"):
                remove_item("courses", i)
                st.rerun()

        if st.button("➕ Add Course", key="add_course"):
            add_item("courses", {"date": "", "course_name": "", "offered_by": "", "grade": ""})
            st.rerun()

    st.divider()

    # 5. Student Innovative Projects Support
    st.subheader("5. Faculty Support in Student Innovative Projects")
    has_support = st.radio("Support Provided (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_support")

    if has_support == "Yes":
        st.caption("Add multiple projects/initiative/event entries.")
        for i, s in enumerate(st.session_state["student_support"]):
            cols = st.columns([3, 2, 2, 3, 1])
            s["project_name"] = cols[0].text_input("Name of Project/Initiative/Event *", value=s["project_name"], key=f"s_name_{i}")
            s["event_date"] = cols[1].text_input("Date of Event (DD/MM/YYYY) *", value=s["event_date"], key=f"s_date_{i}")
            s["place"] = cols[2].text_input("Place of Event *", value=s["place"], key=f"s_place_{i}")
            s["website_link"] = cols[3].text_input("Website Link (if any)", value=s["website_link"], key=f"s_link_{i}")
            if cols[4].button("➖", key=f"s_rm_{i}"):
                remove_item("student_support", i)
                st.rerun()

        if st.button("➕ Add Project/Initiative/Event", key="add_support"):
            add_item("student_support", {"project_name": "", "event_date": "", "place": "", "website_link": ""})
            st.rerun()

    st.divider()

    # 6. Industry internship/training/collab
    st.subheader("6. Faculty Internship/Training/Collaboration with Industry")
    has_industry = st.radio("Industry entries (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_industry")

    if has_industry == "Yes":
        st.caption("Add multiple industry entries.")
        for i, a in enumerate(st.session_state["industry"]):
            cols = st.columns([3, 3, 2, 4, 1])
            a["activity_name"] = cols[0].text_input("Internship/Training/Collaboration Details *", value=a["activity_name"], key=f"i_act_{i}")
            a["company_place"] = cols[1].text_input("Company & Place *", value=a["company_place"], key=f"i_comp_{i}")
            a["duration"] = cols[2].text_input("Duration *", value=a["duration"], key=f"i_dur_{i}")
            a["outcomes"] = cols[3].text_input("Outcomes *", value=a["outcomes"], key=f"i_out_{i}")
            if cols[4].button("➖", key=f"i_rm_{i}"):
                remove_item("industry", i)
                st.rerun()

        if st.button("➕ Add Industry Entry", key="add_industry"):
            add_item("industry", {"activity_name": "", "company_place": "", "duration": "", "outcomes": ""})
            st.rerun()

    st.divider()

    # 7. Academic Research
    st.subheader("7. Academic Research")

    st.markdown("### 7A. Journal & Conference Publications (multiple entries)")
    st.caption("For each entry, provide DOI, date, and upload PDF (front page or full paper).")

    for i, p in enumerate(st.session_state["pubs_jc"]):
        cols = st.columns([1.6, 3.2, 2.2, 2.4, 2.4, 1])
        p["pub_type"] = cols[0].selectbox("Type *", ["Journal", "Conference"], key=f"jc_type_{i}")
        p["title"] = cols[1].text_input("Title *", value=p["title"], key=f"jc_title_{i}")
        p["doi"] = cols[2].text_input("DOI *", value=p["doi"], key=f"jc_doi_{i}")
        p["pub_date"] = cols[3].date_input("Publication date *", value=p["pub_date"], key=f"jc_date_{i}")
        p["pdf"] = cols[4].file_uploader("Upload PDF *", type=["pdf"], key=f"jc_pdf_{i}")

        if cols[5].button("➖", key=f"jc_rm_{i}"):
            remove_item("pubs_jc", i)
            st.rerun()

    if st.button("➕ Add Journal/Conference Publication", key="add_jc_pub"):
        add_item("pubs_jc", {"pub_type": "Journal", "title": "", "doi": "", "pub_date": DEFAULT_DATE, "pdf": None})
        st.rerun()

    pub_confirm = st.checkbox(
        "I confirm the uploaded PDFs match the Journal/Conference publication entries above.",
        value=False,
        key="pub_confirm"
    )

    st.divider()

    st.markdown("### 7B. Books / Book Chapters (multiple entries)")
    for i, b in enumerate(st.session_state["books"]):
        cols = st.columns([1.6, 3.6, 2.6, 2.4, 2.4, 1])
        b["item_type"] = cols[0].selectbox("Type *", ["Book", "Book Chapter"], key=f"bk_type_{i}")
        b["title"] = cols[1].text_input("Title *", value=b["title"], key=f"bk_title_{i}")
        b["publisher"] = cols[2].text_input("Publisher (if any)", value=b["publisher"], key=f"bk_publisher_{i}")
        b["pub_date"] = cols[3].date_input("Publication date (if known)", value=b["pub_date"], key=f"bk_date_{i}")
        b["pdf"] = cols[4].file_uploader("Upload PDF (optional)", type=["pdf"], key=f"bk_pdf_{i}")

        if cols[5].button("➖", key=f"bk_rm_{i}"):
            remove_item("books", i)
            st.rerun()

    if st.button("➕ Add Book / Book Chapter", key="add_book"):
        add_item("books", {"item_type": "Book", "title": "", "publisher": "", "pub_date": DEFAULT_DATE, "pdf": None})
        st.rerun()

    st.divider()

    # 7C. Patents / Working Models / Prototypes (NEW)
    st.markdown("### 7C. Patents / Working Models / Prototypes (last 3 years)")
    has_patents = st.radio(
        "Do you have patents granted / working models / prototypes developed in the last 3 years? *",
        ["No", "Yes"],
        horizontal=True,
        key="has_patents"
    )

    if has_patents == "Yes":
        st.caption("Add one row per item. PDF upload is optional (proof/document).")
        for i, pm in enumerate(st.session_state["patents_models"]):
            cols = st.columns([2.2, 3.6, 2.2, 3.2, 2.2, 1])
            pm["item_type"] = cols[0].selectbox(
                "Type *",
                ["Patent Granted", "Working Model", "Prototype"],
                key=f"pm_type_{i}"
            )
            pm["title"] = cols[1].text_input("Title / Name *", value=pm["title"], key=f"pm_title_{i}")
            pm["item_date"] = cols[2].date_input("Date *", value=pm["item_date"], key=f"pm_date_{i}")
            pm["details"] = cols[3].text_input("Details (optional)", value=pm["details"], key=f"pm_details_{i}")
            pm["pdf"] = cols[4].file_uploader("Upload PDF (optional)", type=["pdf"], key=f"pm_pdf_{i}")

            if cols[5].button("➖", key=f"pm_rm_{i}"):
                remove_item("patents_models", i)
                st.rerun()

        if st.button("➕ Add Item", key="add_pm"):
            add_item("patents_models", {
                "item_type": "Patent Granted",
                "title": "",
                "item_date": DEFAULT_DATE,
                "details": "",
                "pdf": None
            })
            st.rerun()

    st.divider()

    # 8. Sponsored Projects
    st.subheader("8. Sponsored research projects received from external agencies")
    st.caption("Add one row per sponsored project. Upload sanction letter and (if completed) completion certificate.")

    for i, sp in enumerate(st.session_state["sponsored"]):
        cols1 = st.columns([2.0, 2.2, 2.2, 2.4, 1.2, 1])
        sp["project_date"] = cols1[0].date_input("Project date *", value=sp["project_date"], key=f"sp_date_{i}")
        sp["pi_name"] = cols1[1].text_input("PI Name *", value=sp["pi_name"], key=f"sp_pi_{i}")
        sp["co_pi"] = cols1[2].text_input("Co-PI (if any)", value=sp["co_pi"], key=f"sp_copi_{i}")

        # Renamed label (DB column stays dept_sanctioned)
        sp["dept_sanctioned"] = cols1[3].text_input(
            "Name of Dept., where project is sanctioned *",
            value=sp["dept_sanctioned"],
            key=f"sp_dept_{i}"
        )

        sp["status"] = cols1[4].selectbox("Status *", ["Ongoing", "Completed"], key=f"sp_status_{i}")
        if cols1[5].button("➖", key=f"sp_rm_{i}"):
            remove_item("sponsored", i)
            st.rerun()

        cols2 = st.columns([3, 2, 2, 2])
        sp["project_title"] = cols2[0].text_input("Project title *", value=sp["project_title"], key=f"sp_title_{i}")
        sp["funding_agency"] = cols2[1].text_input("Funding agency *", value=sp["funding_agency"], key=f"sp_ag_{i}")
        sp["duration"] = cols2[2].text_input("Duration *", value=sp["duration"], key=f"sp_dur_{i}")
        sp["amount_lakhs"] = cols2[3].number_input(
            "Amount (Lakhs) *",
            min_value=0.0,
            step=0.5,
            value=float(sp["amount_lakhs"]),
            key=f"sp_amt_{i}"
        )

        cols3 = st.columns([3, 3])
        sp["sanction_pdf"] = cols3[0].file_uploader("Upload Sanction/Approval Letter (PDF) *", type=["pdf"], key=f"sp_san_{i}")
        sp["completion_pdf"] = cols3[1].file_uploader("Upload Completion Certificate (PDF) (if completed)", type=["pdf"], key=f"sp_comp_{i}")

        st.markdown("---")

    if st.button("➕ Add Sponsored Project", key="add_sp"):
        add_item("sponsored", {
            "project_date": DEFAULT_DATE,
            "pi_name": "", "co_pi": "",
            "dept_sanctioned": "",
            "project_title": "", "funding_agency": "", "duration": "", "amount_lakhs": 0.0,
            "status": "Ongoing",
            "sanction_pdf": None, "completion_pdf": None
        })
        st.rerun()

    proj_confirm = st.checkbox(
        "I confirm the uploaded sanction letters and completion certificates correspond to the projects listed above.",
        value=False,
        key="proj_confirm"
    )

    submitted = st.button("✅ Submit", key="submit_btn")

    # ----------------------------
    # Validate + Save
    # ----------------------------
    if submitted:
        errors = []

        if not name.strip():
            errors.append("Name of the Faculty is required.")
        if not pub_confirm:
            errors.append("Please confirm Journal/Conference publication PDFs matching.")
        if not proj_confirm:
            errors.append("Please confirm project documents matching.")

        # Membership required fields
        if has_membership == "Yes":
            for idx, m in enumerate(st.session_state["memberships"], start=1):
                if not all([m["body_name"].strip(), m["membership_number"].strip(), m["level"].strip(), m["grade_position"].strip()]):
                    errors.append(f"Membership #{idx}: all fields are required.")

        # FDP/STTP/etc required fields (UPDATED)
        if has_fdp == "Yes":
            for idx, f in enumerate(st.session_state["fdps"], start=1):
                if not all([
                    (f.get("program_type") or "").strip(),
                    (f.get("program_name") or "").strip(),
                    (f.get("involvement") or "").strip(),
                    (f.get("date") or "").strip(),
                    (f.get("location") or "").strip(),
                    (f.get("organised_by") or "").strip()
                ]):
                    errors.append(f"Resource person entry #{idx}: all fields are required (Type, Name, Attended/Organised, Date, Location, Organised By).")

        # Courses
        if has_courses == "Yes":
            for idx, c in enumerate(st.session_state["courses"], start=1):
                if not all([c["date"].strip(), c["course_name"].strip(), c["offered_by"].strip(), c["grade"].strip()]):
                    errors.append(f"Course #{idx}: all fields are required.")

        # Student support
        if has_support == "Yes":
            for idx, s in enumerate(st.session_state["student_support"], start=1):
                if not all([s["project_name"].strip(), s["event_date"].strip(), s["place"].strip()]):
                    errors.append(f"Student support entry #{idx}: project name, date, place are required.")

        # Industry
        if has_industry == "Yes":
            for idx, a in enumerate(st.session_state["industry"], start=1):
                if not all([a["activity_name"].strip(), a["company_place"].strip(), a["duration"].strip(), a["outcomes"].strip()]):
                    errors.append(f"Industry entry #{idx}: all fields are required.")

        # Publications: Journal/Conference required
        for idx, p in enumerate(st.session_state["pubs_jc"], start=1):
            if not p["pub_type"].strip() or not p["title"].strip() or not p["doi"].strip():
                errors.append(f"Publication #{idx}: Type, Title, and DOI are required.")
            if p.get("pub_date") is None:
                errors.append(f"Publication #{idx}: Publication date is required.")
            if p.get("pdf") is None:
                errors.append(f"Publication #{idx}: PDF upload is required (front page or full paper).")

        # Patents/models/prototypes required only if user selected Yes
        if has_patents == "Yes":
            for idx, pm in enumerate(st.session_state["patents_models"], start=1):
                if not (pm.get("item_type") or "").strip() or not (pm.get("title") or "").strip() or pm.get("item_date") is None:
                    errors.append(f"Patents/Models/Prototypes item #{idx}: Type, Title/Name, and Date are required.")

        # Sponsored projects: sanction letter required
        for idx, sp in enumerate(st.session_state["sponsored"], start=1):
            req_fields = [
                (sp.get("pi_name") or ""),
                (sp.get("dept_sanctioned") or ""),
                (sp.get("project_title") or ""),
                (sp.get("funding_agency") or ""),
                (sp.get("duration") or ""),
                (sp.get("status") or "")
            ]
            if not all([str(x).strip() for x in req_fields]) or sp.get("project_date") is None:
                errors.append(f"Sponsored project #{idx}: Project date + required fields are mandatory.")
            if sp.get("sanction_pdf") is None:
                errors.append(f"Sponsored project #{idx}: sanction/approval PDF is required.")

        if errors:
            st.error("Please fix the following issues:\n\n- " + "\n- ".join(errors))
        else:
            faculty_id = uuid.uuid4().hex[:10].upper()
            created_at = datetime.now().isoformat(timespec="seconds")

            conn = get_conn()
            cur = conn.cursor()

            cur.execute(
                "INSERT INTO faculty (faculty_id, name, designation, created_at) VALUES (?, ?, ?, ?)",
                (faculty_id, name.strip(), designation, created_at)
            )

            # Membership
            if has_membership == "Yes":
                for m in st.session_state["memberships"]:
                    cur.execute("""
                        INSERT INTO membership (faculty_id, body_name, membership_number, level, grade_position)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        faculty_id,
                        m["body_name"].strip(),
                        m["membership_number"].strip(),
                        m["level"],
                        m["grade_position"].strip()
                    ))

            # FDP/STTP/etc (UPDATED)
            if has_fdp == "Yes":
                for f in st.session_state["fdps"]:
                    cur.execute("""
                        INSERT INTO fdp_sttp (faculty_id, program_type, program_name, involvement, date, location, organised_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        faculty_id,
                        (f.get("program_type") or "").strip(),
                        (f.get("program_name") or "").strip(),
                        (f.get("involvement") or "").strip(),
                        (f.get("date") or "").strip(),
                        (f.get("location") or "").strip(),
                        (f.get("organised_by") or "").strip(),
                    ))

            # Courses
            if has_courses == "Yes":
                for c in st.session_state["courses"]:
                    cur.execute("""
                        INSERT INTO courses (faculty_id, date, course_name, offered_by, grade)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        faculty_id,
                        c["date"].strip(),
                        c["course_name"].strip(),
                        c["offered_by"].strip(),
                        c["grade"].strip()
                    ))

            # Student support
            if has_support == "Yes":
                for s in st.session_state["student_support"]:
                    cur.execute("""
                        INSERT INTO student_projects_support (faculty_id, project_name, event_date, place, website_link)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        faculty_id,
                        s["project_name"].strip(),
                        s["event_date"].strip(),
                        s["place"].strip(),
                        (s.get("website_link") or "").strip()
                    ))

            # Industry
            if has_industry == "Yes":
                for a in st.session_state["industry"]:
                    cur.execute("""
                        INSERT INTO industry_collab (faculty_id, activity_name, company_place, duration, outcomes)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        faculty_id,
                        a["activity_name"].strip(),
                        a["company_place"].strip(),
                        a["duration"].strip(),
                        a["outcomes"].strip()
                    ))

            # Publications J/C + PDF (required)
            for p in st.session_state["pubs_jc"]:
                pdf_path = save_uploaded_file(p.get("pdf"), f"publications_jc/{faculty_id}")
                pub_date_str = p["pub_date"].isoformat() if p.get("pub_date") else ""
                cur.execute("""
                    INSERT INTO publications_jc (faculty_id, pub_type, title, doi, pub_date, pdf_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    faculty_id,
                    p["pub_type"],
                    p["title"].strip(),
                    p["doi"].strip(),
                    pub_date_str,
                    pdf_path
                ))

            # Books/Chapters (PDF optional)
            for b in st.session_state["books"]:
                pdf_path = save_uploaded_file(b.get("pdf"), f"books_chapters/{faculty_id}") if b.get("pdf") else None
                pub_date_str = b["pub_date"].isoformat() if b.get("pub_date") else ""
                cur.execute("""
                    INSERT INTO books_chapters (faculty_id, item_type, title, publisher, pub_date, pdf_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    faculty_id,
                    b["item_type"],
                    b["title"].strip(),
                    (b.get("publisher") or "").strip(),
                    pub_date_str,
                    pdf_path
                ))

            # Patents / Models / Prototypes (only if Yes)
            if has_patents == "Yes":
                for pm in st.session_state["patents_models"]:
                    pdf_path = save_uploaded_file(pm.get("pdf"), f"patents_models/{faculty_id}") if pm.get("pdf") else None
                    item_date_str = pm["item_date"].isoformat() if pm.get("item_date") else ""
                    cur.execute("""
                        INSERT INTO patents_models (faculty_id, item_type, title, item_date, details, pdf_path)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        faculty_id,
                        (pm.get("item_type") or "").strip(),
                        (pm.get("title") or "").strip(),
                        item_date_str,
                        (pm.get("details") or "").strip(),
                        pdf_path
                    ))

            # Sponsored projects + PDFs
            for sp in st.session_state["sponsored"]:
                sanction_path = save_uploaded_file(sp.get("sanction_pdf"), f"sponsored/{faculty_id}/sanction")
                completion_path = save_uploaded_file(sp.get("completion_pdf"), f"sponsored/{faculty_id}/completion")
                project_date_str = sp["project_date"].isoformat() if sp.get("project_date") else ""

                cur.execute("""
                    INSERT INTO sponsored_projects (
                        faculty_id, project_date, pi_name, co_pi, dept_sanctioned, project_title,
                        funding_agency, duration, amount_lakhs, status,
                        sanction_pdf_path, completion_pdf_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    faculty_id,
                    project_date_str,
                    (sp.get("pi_name") or "").strip(),
                    (sp.get("co_pi") or "").strip(),
                    (sp.get("dept_sanctioned") or "").strip(),
                    (sp.get("project_title") or "").strip(),
                    (sp.get("funding_agency") or "").strip(),
                    (sp.get("duration") or "").strip(),
                    float(sp.get("amount_lakhs") or 0.0),
                    (sp.get("status") or "").strip(),
                    sanction_path,
                    completion_path
                ))

            conn.commit()
            conn.close()

            st.success(f"Submitted successfully ✅  |  Faculty ID: {faculty_id}")
            st.info("Use the 🔐 Admin tab to download Excel/CSV of all submissions.")


# ============================
# TAB 2: ADMIN (Download)
# ============================
with tab_admin:
    st.title("Admin Downloads")

    # Optional password gate:
    admin_pw = os.environ.get("ADMIN_PASSWORD", "").strip()
    if admin_pw:
        entered = st.text_input("Enter Admin Password", type="password")
        if entered != admin_pw:
            st.warning("Enter the correct admin password to access downloads.")
            st.stop()

    st.caption("Download all submissions as Excel (multi-sheet) or individual CSV files.")

    table_names = [
        "faculty",
        "membership",
        "fdp_sttp",
        "courses",
        "student_projects_support",
        "industry_collab",
        "publications_jc",
        "books_chapters",
        "patents_models",
        "sponsored_projects",
    ]

    dfs = {}
    for t in table_names:
        try:
            dfs[t] = fetch_table_df(t)
        except Exception:
            dfs[t] = pd.DataFrame()

    st.subheader("Quick Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faculty records", len(dfs["faculty"]))
    c2.metric("Publications (J/C)", len(dfs["publications_jc"]))
    c3.metric("Patents/Models/Prototypes", len(dfs["patents_models"]))
    c4.metric("Sponsored projects", len(dfs["sponsored_projects"]))

    st.divider()

    st.subheader("Download All Data")
    # Clean UI: Excel is optional; if openpyxl missing, no crash / no traceback.
    try:
        import openpyxl  # noqa: F401
        excel_bytes = make_excel_bytes(dfs)
        st.download_button(
            label="⬇️ Download ALL DATA (Excel, multi-sheet)",
            data=excel_bytes,
            file_name="faculty_submissions_all.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except ModuleNotFoundError:
        st.info("Excel export needs 'openpyxl'. Install it using:  python -m pip install openpyxl  (CSV downloads are available below.)")

    st.divider()

    st.subheader("Download Individual Tables (CSV)")
    for t in table_names:
        df = dfs[t]
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=f"⬇️ Download {t}.csv",
            data=csv_bytes,
            file_name=f"{t}.csv",
            mime="text/csv",
            key=f"dl_{t}"
        )

    st.divider()

    st.subheader("Preview Data")
    table_to_preview = st.selectbox("Select table to preview", table_names)
    st.dataframe(dfs[table_to_preview], use_container_width=True)

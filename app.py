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

    # FDP/STTP/etc
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fdp_sttp (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        program_type TEXT,
        program_name TEXT,
        involvement TEXT NOT NULL,
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

    # Academic Research: Journal + Conference
    cur.execute("""
    CREATE TABLE IF NOT EXISTS publications_jc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        pub_type TEXT NOT NULL,           -- Journal / Conference
        title TEXT NOT NULL,
        doi TEXT NOT NULL,
        pub_date TEXT NOT NULL,           -- ISO date YYYY-MM-DD
        pdf_path TEXT NOT NULL,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    # Books / Chapters
    cur.execute("""
    CREATE TABLE IF NOT EXISTS books_chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        item_type TEXT NOT NULL,          -- Book / Book Chapter
        title TEXT NOT NULL,
        publisher TEXT,
        pub_date TEXT,
        pdf_path TEXT,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    # Patents / Working models / Prototypes
    cur.execute("""
    CREATE TABLE IF NOT EXISTS patents_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        item_type TEXT NOT NULL,          -- dropdown categories
        title TEXT NOT NULL,
        item_date TEXT NOT NULL,          -- ISO date YYYY-MM-DD
        details TEXT,
        pdf_path TEXT,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    # Sponsored Projects
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sponsored_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        project_date TEXT,
        pi_name TEXT NOT NULL,
        co_pi TEXT,
        dept_sanctioned TEXT NOT NULL,
        project_title TEXT NOT NULL,
        funding_agency TEXT NOT NULL,
        duration TEXT NOT NULL,
        amount_lakhs REAL NOT NULL,
        status TEXT NOT NULL,
        sanction_pdf_path TEXT,
        completion_pdf_path TEXT,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    # Consultancy Work (same structure)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS consultancy_work (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        project_date TEXT,
        pi_name TEXT NOT NULL,
        co_pi TEXT,
        dept_sanctioned TEXT NOT NULL,
        project_title TEXT NOT NULL,
        funding_agency TEXT NOT NULL,
        duration TEXT NOT NULL,
        amount_lakhs REAL NOT NULL,
        status TEXT NOT NULL,
        sanction_pdf_path TEXT,
        completion_pdf_path TEXT,
        FOREIGN KEY(faculty_id) REFERENCES faculty(faculty_id)
    )
    """)

    conn.commit()

    # Migrations for older DBs
    ensure_column(conn, "fdp_sttp", "program_type", "TEXT")
    ensure_column(conn, "fdp_sttp", "program_name", "TEXT")
    ensure_column(conn, "sponsored_projects", "project_date", "TEXT")
    ensure_column(conn, "consultancy_work", "project_date", "TEXT")

    conn.close()


def _safe_ext(filename: str) -> str:
    ext = os.path.splitext(filename)[-1].lower()
    return ext if ext else ".pdf"


def save_uploaded_bytes(file_dict, subdir):
    """
    file_dict: {"name": "...", "bytes": b"..."} or None
    """
    if not file_dict:
        return None
    os.makedirs(os.path.join(UPLOAD_DIR, subdir), exist_ok=True)
    ext = _safe_ext(file_dict.get("name", "file.pdf"))
    fname = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, subdir, fname)
    with open(path, "wb") as f:
        f.write(file_dict["bytes"])
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
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet[:31], index=False)
    buffer.seek(0)
    return buffer.getvalue()


# ----------------------------
# Streamlit state helpers
# ----------------------------
def new_row_id() -> str:
    return uuid.uuid4().hex[:10]


def ensure_list_state(key, factory_fn):
    if key not in st.session_state:
        st.session_state[key] = [factory_fn()]


def add_row(key, factory_fn):
    st.session_state[key].append(factory_fn())


def remove_row_by_id(key, row_id: str):
    rows = st.session_state.get(key, [])
    if len(rows) <= 1:
        return
    st.session_state[key] = [r for r in rows if r.get("_id") != row_id]


def persist_pdf_uploader(label: str, widget_key: str):
    """
    Keeps uploaded PDF across reruns/validation errors by storing bytes in session_state.
    Returns file_dict or None.
    """
    store_key = f"{widget_key}__stored"
    uploaded = st.file_uploader(label, type=["pdf"], key=widget_key)

    if uploaded is not None:
        st.session_state[store_key] = {"name": uploaded.name, "bytes": uploaded.getvalue()}

    stored = st.session_state.get(store_key)

    # Show stored indicator + clear
    if stored is not None and uploaded is None:
        colA, colB = st.columns([5, 1])
        colA.caption(f"✅ Already uploaded: {stored['name']}")
        if colB.button("Clear", key=f"{widget_key}__clear"):
            st.session_state.pop(store_key, None)
            st.rerun()

    return stored


# ----------------------------
# Row factories (stable IDs)
# ----------------------------
def membership_factory():
    return {"_id": new_row_id(), "body_name": "", "membership_number": "", "level": "National", "grade_position": ""}


def fdp_factory():
    return {
        "_id": new_row_id(),
        "program_type": "FDP",
        "program_name": "",
        "involvement": "Attended",
        "date": "",
        "location": "",
        "organised_by": ""
    }


def course_factory():
    return {"_id": new_row_id(), "date": "", "course_name": "", "offered_by": "", "grade": ""}


def support_factory():
    return {"_id": new_row_id(), "project_name": "", "event_date": "", "place": "", "website_link": ""}


def industry_factory():
    return {"_id": new_row_id(), "activity_name": "", "company_place": "", "duration": "", "outcomes": ""}


def jc_pub_factory():
    return {"_id": new_row_id(), "pub_type": "Journal", "title": "", "doi": "", "pub_date": DEFAULT_DATE}


def book_factory():
    return {"_id": new_row_id(), "item_type": "Book", "title": "", "publisher": "", "pub_date": DEFAULT_DATE}


def patent_factory():
    return {"_id": new_row_id(), "item_type": "Indian Patent Granted", "title": "", "item_date": DEFAULT_DATE, "details": ""}


def sponsored_factory():
    return {
        "_id": new_row_id(),
        "project_date": DEFAULT_DATE,
        "pi_name": "",
        "co_pi": "",
        "dept_sanctioned": "",
        "project_title": "",
        "funding_agency": "",
        "duration": "",
        "amount_lakhs": 0.0,
        "status": "Ongoing",
    }


def consultancy_factory():
    return {
        "_id": new_row_id(),
        "project_date": DEFAULT_DATE,
        "pi_name": "",
        "co_pi": "",
        "dept_sanctioned": "",
        "project_title": "",
        "funding_agency": "",
        "duration": "",
        "amount_lakhs": 0.0,
        "status": "Ongoing",
    }


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
    st.info("Repeatable sections support ➕ Add buttons. PDFs will NOT disappear on validation errors now.")

    # Initialize repeatables with stable IDs
    ensure_list_state("memberships", membership_factory)
    ensure_list_state("fdps", fdp_factory)
    ensure_list_state("courses", course_factory)
    ensure_list_state("student_support", support_factory)
    ensure_list_state("industry", industry_factory)
    ensure_list_state("pubs_jc", jc_pub_factory)
    ensure_list_state("books", book_factory)
    ensure_list_state("patents_models", patent_factory)
    ensure_list_state("sponsored", sponsored_factory)
    ensure_list_state("consultancy", consultancy_factory)

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
        for m in st.session_state["memberships"]:
            rid = m["_id"]
            cols = st.columns([3, 3, 2, 3, 1])
            m["body_name"] = cols[0].text_input("Body Name *", value=m["body_name"], key=f"m_body_{rid}")
            m["membership_number"] = cols[1].text_input("Membership Number *", value=m["membership_number"], key=f"m_no_{rid}")
            m["level"] = cols[2].selectbox(
                "Level *", ["National", "International"],
                index=0 if m["level"] == "National" else 1,
                key=f"m_lvl_{rid}"
            )
            m["grade_position"] = cols[3].text_input("Level/Grade/Position *", value=m["grade_position"], key=f"m_pos_{rid}")
            if cols[4].button("➖", key=f"m_rm_{rid}"):
                remove_row_by_id("memberships", rid)
                st.rerun()

        if st.button("➕ Add Membership", key="add_membership"):
            add_row("memberships", membership_factory)
            st.rerun()

    st.divider()

    # 3. FDP/STTP Resource person
    st.subheader("3. As resource person in FDP/STTP")
    has_fdp = st.radio("Resource person entries (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_fdp")

    if has_fdp == "Yes":
        st.caption("Select type first, then fill the details. Add multiple entries if required.")
        for f in st.session_state["fdps"]:
            rid = f["_id"]
            cols0 = st.columns([2.2, 3.8, 1])
            f["program_type"] = cols0[0].selectbox(
                "Select Type *", ["FDP", "STTP", "SWAYAM", "NPTEL", "MOOCs"],
                key=f"f_type_{rid}"
            )
            f["program_name"] = cols0[1].text_input(
                f"Name of {f['program_type']} *",
                value=f["program_name"],
                key=f"f_name_{rid}"
            )
            if cols0[2].button("➖", key=f"f_rm_{rid}"):
                remove_row_by_id("fdps", rid)
                st.rerun()

            cols = st.columns([2, 2, 3, 3])
            f["involvement"] = cols[0].selectbox("Attended / Organised *", ["Attended", "Organised"], key=f"f_inv_{rid}")
            f["date"] = cols[1].text_input("Date (DD/MM/YYYY) *", value=f["date"], key=f"f_date_{rid}")
            f["location"] = cols[2].text_input("Location *", value=f["location"], key=f"f_loc_{rid}")
            f["organised_by"] = cols[3].text_input("Organised By *", value=f["organised_by"], key=f"f_org_{rid}")
            st.markdown("---")

        if st.button("➕ Add Entry", key="add_fdp"):
            add_row("fdps", fdp_factory)
            st.rerun()

    st.divider()

    # 4. Courses Passed
    st.subheader("4. Courses Passed")
    has_courses = st.radio("Courses Passed (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_courses")

    if has_courses == "Yes":
        for c in st.session_state["courses"]:
            rid = c["_id"]
            cols = st.columns([2, 3, 3, 2, 1])
            c["date"] = cols[0].text_input("Date (DD/MM/YYYY) *", value=c["date"], key=f"c_date_{rid}")
            c["course_name"] = cols[1].text_input("Course Name *", value=c["course_name"], key=f"c_name_{rid}")
            c["offered_by"] = cols[2].text_input("Course Offered By *", value=c["offered_by"], key=f"c_by_{rid}")
            c["grade"] = cols[3].text_input("Grade Obtained *", value=c["grade"], key=f"c_grade_{rid}")
            if cols[4].button("➖", key=f"c_rm_{rid}"):
                remove_row_by_id("courses", rid)
                st.rerun()

        if st.button("➕ Add Course", key="add_course"):
            add_row("courses", course_factory)
            st.rerun()

    st.divider()

    # 5. Student Innovative Projects Support
    st.subheader("5. Faculty Support in Student Innovative Projects")
    has_support = st.radio("Support Provided (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_support")

    if has_support == "Yes":
        for s in st.session_state["student_support"]:
            rid = s["_id"]
            cols = st.columns([3, 2, 2, 3, 1])
            s["project_name"] = cols[0].text_input("Name of Project/Initiative/Event *", value=s["project_name"], key=f"s_name_{rid}")
            s["event_date"] = cols[1].text_input("Date of Event (DD/MM/YYYY) *", value=s["event_date"], key=f"s_date_{rid}")
            s["place"] = cols[2].text_input("Place of Event *", value=s["place"], key=f"s_place_{rid}")
            s["website_link"] = cols[3].text_input("Website Link (if any)", value=s["website_link"], key=f"s_link_{rid}")
            if cols[4].button("➖", key=f"s_rm_{rid}"):
                remove_row_by_id("student_support", rid)
                st.rerun()

        if st.button("➕ Add Project/Initiative/Event", key="add_support"):
            add_row("student_support", support_factory)
            st.rerun()

    st.divider()

    # 6. Industry internship/training/collab
    st.subheader("6. Faculty Internship/Training/Collaboration with Industry")
    has_industry = st.radio("Industry entries (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_industry")

    if has_industry == "Yes":
        for a in st.session_state["industry"]:
            rid = a["_id"]
            cols = st.columns([3, 3, 2, 4, 1])
            a["activity_name"] = cols[0].text_input("Internship/Training/Collaboration Details *", value=a["activity_name"], key=f"i_act_{rid}")
            a["company_place"] = cols[1].text_input("Company & Place *", value=a["company_place"], key=f"i_comp_{rid}")
            a["duration"] = cols[2].text_input("Duration *", value=a["duration"], key=f"i_dur_{rid}")
            a["outcomes"] = cols[3].text_input("Outcomes *", value=a["outcomes"], key=f"i_out_{rid}")
            if cols[4].button("➖", key=f"i_rm_{rid}"):
                remove_row_by_id("industry", rid)
                st.rerun()

        if st.button("➕ Add Industry Entry", key="add_industry"):
            add_row("industry", industry_factory)
            st.rerun()

    st.divider()

    # 7. Academic Research (YES/NO)
    st.subheader("7. Academic Research")
    has_academic = st.radio("Academic Research entries (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_academic")

    if has_academic == "Yes":
        st.markdown("### 7A. Journal & Conference Publications (multiple entries)")
        for p in st.session_state["pubs_jc"]:
            rid = p["_id"]
            cols = st.columns([1.6, 3.2, 2.2, 2.4, 2.4, 1])
            p["pub_type"] = cols[0].selectbox("Type *", ["Journal", "Conference"], key=f"jc_type_{rid}")
            p["title"] = cols[1].text_input("Title *", value=p["title"], key=f"jc_title_{rid}")
            p["doi"] = cols[2].text_input("DOI *", value=p["doi"], key=f"jc_doi_{rid}")
            p["pub_date"] = cols[3].date_input("Publication date *", value=p["pub_date"], key=f"jc_date_{rid}")
            with cols[4]:
                persist_pdf_uploader("Upload PDF *", widget_key=f"jc_pdf_{rid}")

            if cols[5].button("➖", key=f"jc_rm_{rid}"):
                st.session_state.pop(f"jc_pdf_{rid}__stored", None)
                remove_row_by_id("pubs_jc", rid)
                st.rerun()

        if st.button("➕ Add Journal/Conference Publication", key="add_jc_pub"):
            add_row("pubs_jc", jc_pub_factory)
            st.rerun()

        pub_confirm = st.checkbox(
            "I confirm the uploaded PDFs match the Journal/Conference publication entries above.",
            value=False,
            key="pub_confirm"
        )
    else:
        pub_confirm = True

    st.divider()

    # 7B Books / Chapters (YES/NO)
    st.markdown("### 7B. Books / Book Chapters")
    has_books = st.radio("Books / Book Chapters entries (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_books")

    if has_books == "Yes":
        for b in st.session_state["books"]:
            rid = b["_id"]
            cols = st.columns([1.6, 3.6, 2.6, 2.4, 2.4, 1])
            b["item_type"] = cols[0].selectbox("Type *", ["Book", "Book Chapter"], key=f"bk_type_{rid}")
            b["title"] = cols[1].text_input("Title *", value=b["title"], key=f"bk_title_{rid}")
            b["publisher"] = cols[2].text_input("Publisher (if any)", value=b["publisher"], key=f"bk_publisher_{rid}")
            b["pub_date"] = cols[3].date_input("Publication date (if known)", value=b["pub_date"], key=f"bk_date_{rid}")
            with cols[4]:
                persist_pdf_uploader("Upload PDF (optional)", widget_key=f"bk_pdf_{rid}")

            if cols[5].button("➖", key=f"bk_rm_{rid}"):
                st.session_state.pop(f"bk_pdf_{rid}__stored", None)
                remove_row_by_id("books", rid)
                st.rerun()

        if st.button("➕ Add Book / Book Chapter", key="add_book"):
            add_row("books", book_factory)
            st.rerun()
    # if No, nothing to fill (no confirm needed)

    st.divider()

    # 7C. Patents / Working Models / Prototypes
    st.markdown("### 7C. Patents / Working Models / Prototypes (last 3 years)")
    has_patents = st.radio(
        "Do you have patents / working models / prototypes in the last 3 years? *",
        ["No", "Yes"],
        horizontal=True,
        key="has_patents"
    )

    patent_type_options = [
        "Indian Patent Granted",
        "Utility granted",
        "Utility Published",
        "UK Design Patent",
        "Working Model",
        "Prototype",
    ]

    if has_patents == "Yes":
        for pm in st.session_state["patents_models"]:
            rid = pm["_id"]
            cols = st.columns([2.3, 3.6, 2.2, 3.2, 2.2, 1])
            pm["item_type"] = cols[0].selectbox("Type *", patent_type_options, key=f"pm_type_{rid}")
            pm["title"] = cols[1].text_input("Title / Name *", value=pm["title"], key=f"pm_title_{rid}")
            pm["item_date"] = cols[2].date_input("Date *", value=pm["item_date"], key=f"pm_date_{rid}")
            pm["details"] = cols[3].text_input("Details (optional)", value=pm["details"], key=f"pm_details_{rid}")
            with cols[4]:
                persist_pdf_uploader("Upload PDF (optional)", widget_key=f"pm_pdf_{rid}")

            if cols[5].button("➖", key=f"pm_rm_{rid}"):
                st.session_state.pop(f"pm_pdf_{rid}__stored", None)
                remove_row_by_id("patents_models", rid)
                st.rerun()

        if st.button("➕ Add Item", key="add_pm"):
            add_row("patents_models", patent_factory)
            st.rerun()

    st.divider()

    # 8. Sponsored Projects (Yes/No)
    st.subheader("8. Sponsored research projects received from external agencies")
    has_sponsored = st.radio("Sponsored projects (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_sponsored")

    if has_sponsored == "Yes":
        for sp in st.session_state["sponsored"]:
            rid = sp["_id"]
            cols1 = st.columns([2.0, 2.2, 2.2, 2.4, 1.2, 1])
            sp["project_date"] = cols1[0].date_input("Project date *", value=sp["project_date"], key=f"sp_date_{rid}")
            sp["pi_name"] = cols1[1].text_input("PI Name *", value=sp["pi_name"], key=f"sp_pi_{rid}")
            sp["co_pi"] = cols1[2].text_input("Co-PI (if any)", value=sp["co_pi"], key=f"sp_copi_{rid}")
            sp["dept_sanctioned"] = cols1[3].text_input("Name of Dept., where project is sanctioned *", value=sp["dept_sanctioned"], key=f"sp_dept_{rid}")
            sp["status"] = cols1[4].selectbox("Status *", ["Ongoing", "Completed"], key=f"sp_status_{rid}")

            if cols1[5].button("➖", key=f"sp_rm_{rid}"):
                st.session_state.pop(f"sp_san_{rid}__stored", None)
                st.session_state.pop(f"sp_comp_{rid}__stored", None)
                remove_row_by_id("sponsored", rid)
                st.rerun()

            cols2 = st.columns([3, 2, 2, 2])
            sp["project_title"] = cols2[0].text_input("Project title *", value=sp["project_title"], key=f"sp_title_{rid}")
            sp["funding_agency"] = cols2[1].text_input("Funding agency *", value=sp["funding_agency"], key=f"sp_ag_{rid}")
            sp["duration"] = cols2[2].text_input("Duration *", value=sp["duration"], key=f"sp_dur_{rid}")
            sp["amount_lakhs"] = cols2[3].number_input("Amount (Lakhs) *", min_value=0.0, step=0.5, value=float(sp["amount_lakhs"]), key=f"sp_amt_{rid}")

            cols3 = st.columns([3, 3])
            with cols3[0]:
                persist_pdf_uploader("Upload Sanction/Approval Letter (PDF) *", widget_key=f"sp_san_{rid}")
            with cols3[1]:
                persist_pdf_uploader("Upload Completion Certificate (PDF) (if completed)", widget_key=f"sp_comp_{rid}")

            st.markdown("---")

        if st.button("➕ Add Sponsored Project", key="add_sp"):
            add_row("sponsored", sponsored_factory)
            st.rerun()

        proj_confirm = st.checkbox(
            "I confirm the uploaded sanction letters and completion certificates correspond to the projects listed above.",
            value=False,
            key="proj_confirm"
        )
    else:
        proj_confirm = True

    st.divider()

    # 9. Consultancy Work (Yes/No)
    st.subheader("9. Consultancy Work")
    has_consultancy = st.radio("Consultancy work (Yes/No) *", ["No", "Yes"], horizontal=True, key="has_consultancy")

    if has_consultancy == "Yes":
        for cw in st.session_state["consultancy"]:
            rid = cw["_id"]
            cols1 = st.columns([2.0, 2.2, 2.2, 2.4, 1.2, 1])
            cw["project_date"] = cols1[0].date_input("Consultancy date *", value=cw["project_date"], key=f"cw_date_{rid}")
            cw["pi_name"] = cols1[1].text_input("PI Name *", value=cw["pi_name"], key=f"cw_pi_{rid}")
            cw["co_pi"] = cols1[2].text_input("Co-PI (if any)", value=cw["co_pi"], key=f"cw_copi_{rid}")
            cw["dept_sanctioned"] = cols1[3].text_input("Name of Dept., where project is sanctioned *", value=cw["dept_sanctioned"], key=f"cw_dept_{rid}")
            cw["status"] = cols1[4].selectbox("Status *", ["Ongoing", "Completed"], key=f"cw_status_{rid}")

            if cols1[5].button("➖", key=f"cw_rm_{rid}"):
                st.session_state.pop(f"cw_san_{rid}__stored", None)
                st.session_state.pop(f"cw_comp_{rid}__stored", None)
                remove_row_by_id("consultancy", rid)
                st.rerun()

            cols2 = st.columns([3, 2, 2, 2])
            cw["project_title"] = cols2[0].text_input("Project title *", value=cw["project_title"], key=f"cw_title_{rid}")
            cw["funding_agency"] = cols2[1].text_input("Funding agency / Client *", value=cw["funding_agency"], key=f"cw_ag_{rid}")
            cw["duration"] = cols2[2].text_input("Duration *", value=cw["duration"], key=f"cw_dur_{rid}")
            cw["amount_lakhs"] = cols2[3].number_input("Amount (Lakhs) *", min_value=0.0, step=0.5, value=float(cw["amount_lakhs"]), key=f"cw_amt_{rid}")

            cols3 = st.columns([3, 3])
            with cols3[0]:
                persist_pdf_uploader("Upload Approval/Work Order (PDF) (optional)", widget_key=f"cw_san_{rid}")
            with cols3[1]:
                persist_pdf_uploader("Upload Completion/Report (PDF) (optional)", widget_key=f"cw_comp_{rid}")

            st.markdown("---")

        if st.button("➕ Add Consultancy Work", key="add_cw"):
            add_row("consultancy", consultancy_factory)
            st.rerun()

        consult_confirm = st.checkbox(
            "I confirm the uploaded documents (if any) correspond to the consultancy items listed above.",
            value=False,
            key="consult_confirm"
        )
    else:
        consult_confirm = True

    submitted = st.button("✅ Submit", key="submit_btn")

    # ----------------------------
    # Validate + Save
    # ----------------------------
    if submitted:
        errors = []

        if not name.strip():
            errors.append("Name of the Faculty is required.")

        if has_academic == "Yes" and not pub_confirm:
            errors.append("Please confirm Journal/Conference publication PDFs matching.")

        if has_sponsored == "Yes" and not proj_confirm:
            errors.append("Please confirm Sponsored project documents matching.")

        if has_consultancy == "Yes" and not consult_confirm:
            errors.append("Please confirm Consultancy documents matching.")

        if has_membership == "Yes":
            for idx, m in enumerate(st.session_state["memberships"], start=1):
                if not all([m["body_name"].strip(), m["membership_number"].strip(), m["level"].strip(), m["grade_position"].strip()]):
                    errors.append(f"Membership #{idx}: all fields are required.")

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
                    errors.append(f"Resource person entry #{idx}: all fields are required.")

        if has_courses == "Yes":
            for idx, c in enumerate(st.session_state["courses"], start=1):
                if not all([c["date"].strip(), c["course_name"].strip(), c["offered_by"].strip(), c["grade"].strip()]):
                    errors.append(f"Course #{idx}: all fields are required.")

        if has_support == "Yes":
            for idx, s in enumerate(st.session_state["student_support"], start=1):
                if not all([s["project_name"].strip(), s["event_date"].strip(), s["place"].strip()]):
                    errors.append(f"Student support entry #{idx}: project name, date, place are required.")

        if has_industry == "Yes":
            for idx, a in enumerate(st.session_state["industry"], start=1):
                if not all([a["activity_name"].strip(), a["company_place"].strip(), a["duration"].strip(), a["outcomes"].strip()]):
                    errors.append(f"Industry entry #{idx}: all fields are required.")

        if has_academic == "Yes":
            for idx, p in enumerate(st.session_state["pubs_jc"], start=1):
                rid = p["_id"]
                pdf_dict = st.session_state.get(f"jc_pdf_{rid}__stored")
                if not p["pub_type"].strip() or not p["title"].strip() or not p["doi"].strip():
                    errors.append(f"Publication #{idx}: Type, Title, and DOI are required.")
                if p.get("pub_date") is None:
                    errors.append(f"Publication #{idx}: Publication date is required.")
                if not pdf_dict:
                    errors.append(f"Publication #{idx}: PDF upload is required.")

        if has_books == "Yes":
            for idx, b in enumerate(st.session_state["books"], start=1):
                if not b["item_type"].strip() or not b["title"].strip():
                    errors.append(f"Book/Chapter #{idx}: Type and Title are required.")

        if has_patents == "Yes":
            for idx, pm in enumerate(st.session_state["patents_models"], start=1):
                if not (pm.get("item_type") or "").strip() or not (pm.get("title") or "").strip() or pm.get("item_date") is None:
                    errors.append(f"Patents/Models/Prototypes item #{idx}: Type, Title/Name, and Date are required.")

        if has_sponsored == "Yes":
            for idx, sp in enumerate(st.session_state["sponsored"], start=1):
                rid = sp["_id"]
                sanction_pdf = st.session_state.get(f"sp_san_{rid}__stored")
                req_fields = [
                    (sp.get("pi_name") or ""),
                    (sp.get("dept_sanctioned") or ""),
                    (sp.get("project_title") or ""),
                    (sp.get("funding_agency") or ""),
                    (sp.get("duration") or ""),
                    (sp.get("status") or "")
                ]
                if not all([str(x).strip() for x in req_fields]) or sp.get("project_date") is None:
                    errors.append(f"Sponsored project #{idx}: Date + required fields are mandatory.")
                if not sanction_pdf:
                    errors.append(f"Sponsored project #{idx}: Sanction/Approval PDF is required.")

        if has_consultancy == "Yes":
            for idx, cw in enumerate(st.session_state["consultancy"], start=1):
                req_fields = [
                    (cw.get("pi_name") or ""),
                    (cw.get("dept_sanctioned") or ""),
                    (cw.get("project_title") or ""),
                    (cw.get("funding_agency") or ""),
                    (cw.get("duration") or ""),
                    (cw.get("status") or "")
                ]
                if not all([str(x).strip() for x in req_fields]) or cw.get("project_date") is None:
                    errors.append(f"Consultancy work #{idx}: Date + required fields are mandatory.")

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

            if has_membership == "Yes":
                for m in st.session_state["memberships"]:
                    cur.execute("""
                        INSERT INTO membership (faculty_id, body_name, membership_number, level, grade_position)
                        VALUES (?, ?, ?, ?, ?)
                    """, (faculty_id, m["body_name"].strip(), m["membership_number"].strip(), m["level"], m["grade_position"].strip()))

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
                        (f.get("organised_by") or "").strip()
                    ))

            if has_courses == "Yes":
                for c in st.session_state["courses"]:
                    cur.execute("""
                        INSERT INTO courses (faculty_id, date, course_name, offered_by, grade)
                        VALUES (?, ?, ?, ?, ?)
                    """, (faculty_id, c["date"].strip(), c["course_name"].strip(), c["offered_by"].strip(), c["grade"].strip()))

            if has_support == "Yes":
                for s in st.session_state["student_support"]:
                    cur.execute("""
                        INSERT INTO student_projects_support (faculty_id, project_name, event_date, place, website_link)
                        VALUES (?, ?, ?, ?, ?)
                    """, (faculty_id, s["project_name"].strip(), s["event_date"].strip(), s["place"].strip(), (s.get("website_link") or "").strip()))

            if has_industry == "Yes":
                for a in st.session_state["industry"]:
                    cur.execute("""
                        INSERT INTO industry_collab (faculty_id, activity_name, company_place, duration, outcomes)
                        VALUES (?, ?, ?, ?, ?)
                    """, (faculty_id, a["activity_name"].strip(), a["company_place"].strip(), a["duration"].strip(), a["outcomes"].strip()))

            if has_academic == "Yes":
                for p in st.session_state["pubs_jc"]:
                    rid = p["_id"]
                    pdf_dict = st.session_state.get(f"jc_pdf_{rid}__stored")
                    pdf_path = save_uploaded_bytes(pdf_dict, f"publications_jc/{faculty_id}")
                    cur.execute("""
                        INSERT INTO publications_jc (faculty_id, pub_type, title, doi, pub_date, pdf_path)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (faculty_id, p["pub_type"], p["title"].strip(), p["doi"].strip(), p["pub_date"].isoformat(), pdf_path))

            if has_books == "Yes":
                for b in st.session_state["books"]:
                    rid = b["_id"]
                    pdf_dict = st.session_state.get(f"bk_pdf_{rid}__stored")
                    pdf_path = save_uploaded_bytes(pdf_dict, f"books_chapters/{faculty_id}") if pdf_dict else None
                    cur.execute("""
                        INSERT INTO books_chapters (faculty_id, item_type, title, publisher, pub_date, pdf_path)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (faculty_id, b["item_type"], b["title"].strip(), (b.get("publisher") or "").strip(),
                          b["pub_date"].isoformat() if b.get("pub_date") else "", pdf_path))

            if has_patents == "Yes":
                for pm in st.session_state["patents_models"]:
                    rid = pm["_id"]
                    pdf_dict = st.session_state.get(f"pm_pdf_{rid}__stored")
                    pdf_path = save_uploaded_bytes(pdf_dict, f"patents_models/{faculty_id}") if pdf_dict else None
                    cur.execute("""
                        INSERT INTO patents_models (faculty_id, item_type, title, item_date, details, pdf_path)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (faculty_id, (pm.get("item_type") or "").strip(), (pm.get("title") or "").strip(),
                          pm["item_date"].isoformat(), (pm.get("details") or "").strip(), pdf_path))

            if has_sponsored == "Yes":
                for sp in st.session_state["sponsored"]:
                    rid = sp["_id"]
                    sanction_dict = st.session_state.get(f"sp_san_{rid}__stored")
                    completion_dict = st.session_state.get(f"sp_comp_{rid}__stored")

                    sanction_path = save_uploaded_bytes(sanction_dict, f"sponsored/{faculty_id}/sanction")
                    completion_path = save_uploaded_bytes(completion_dict, f"sponsored/{faculty_id}/completion") if completion_dict else None

                    cur.execute("""
                        INSERT INTO sponsored_projects (
                            faculty_id, project_date, pi_name, co_pi, dept_sanctioned, project_title,
                            funding_agency, duration, amount_lakhs, status,
                            sanction_pdf_path, completion_pdf_path
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (faculty_id, sp["project_date"].isoformat(), (sp.get("pi_name") or "").strip(),
                          (sp.get("co_pi") or "").strip(), (sp.get("dept_sanctioned") or "").strip(),
                          (sp.get("project_title") or "").strip(), (sp.get("funding_agency") or "").strip(),
                          (sp.get("duration") or "").strip(), float(sp.get("amount_lakhs") or 0.0),
                          (sp.get("status") or "").strip(), sanction_path, completion_path))

            if has_consultancy == "Yes":
                for cw in st.session_state["consultancy"]:
                    rid = cw["_id"]
                    sanction_dict = st.session_state.get(f"cw_san_{rid}__stored")
                    completion_dict = st.session_state.get(f"cw_comp_{rid}__stored")

                    sanction_path = save_uploaded_bytes(sanction_dict, f"consultancy/{faculty_id}/approval") if sanction_dict else None
                    completion_path = save_uploaded_bytes(completion_dict, f"consultancy/{faculty_id}/completion") if completion_dict else None

                    cur.execute("""
                        INSERT INTO consultancy_work (
                            faculty_id, project_date, pi_name, co_pi, dept_sanctioned, project_title,
                            funding_agency, duration, amount_lakhs, status,
                            sanction_pdf_path, completion_pdf_path
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (faculty_id, cw["project_date"].isoformat(), (cw.get("pi_name") or "").strip(),
                          (cw.get("co_pi") or "").strip(), (cw.get("dept_sanctioned") or "").strip(),
                          (cw.get("project_title") or "").strip(), (cw.get("funding_agency") or "").strip(),
                          (cw.get("duration") or "").strip(), float(cw.get("amount_lakhs") or 0.0),
                          (cw.get("status") or "").strip(), sanction_path, completion_path))

            conn.commit()
            conn.close()

            st.success(f"Submitted successfully ✅  |  Faculty ID: {faculty_id}")


# ============================
# TAB 2: ADMIN (Download)
# ============================
with tab_admin:
    st.title("Admin Downloads")

    admin_pw = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not admin_pw:
        st.error("Admin access is not configured. Set ADMIN_PASSWORD in Streamlit Secrets.")
        st.stop()

    entered = st.text_input("Enter Admin Password", type="password")
    if entered != admin_pw:
        st.warning("Enter the correct admin password to access downloads.")
        st.stop()

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
        "consultancy_work",
    ]

    dfs = {t: fetch_table_df(t) for t in table_names}

    st.subheader("Download All Data")
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
        st.info("Excel export needs 'openpyxl'. Install it using: python -m pip install openpyxl (CSV still works)")

    st.subheader("Download Individual Tables (CSV)")
    for t in table_names:
        st.download_button(
            label=f"⬇️ Download {t}.csv",
            data=dfs[t].to_csv(index=False).encode("utf-8"),
            file_name=f"{t}.csv",
            mime="text/csv",
            key=f"dl_{t}"
        )

    st.subheader("Preview Data")
    table_to_preview = st.selectbox("Select table to preview", table_names)
    st.dataframe(dfs[table_to_preview], use_container_width=True)

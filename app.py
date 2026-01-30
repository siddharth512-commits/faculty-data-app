import uuid
from datetime import datetime, date
from io import BytesIO
from typing import Dict, Any, List, Optional

import pandas as pd
import streamlit as st
from supabase import create_client, Client


# ----------------------------
# Config / Secrets
# ----------------------------
st.set_page_config(page_title="Faculty Data Collection", layout="wide")

SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_ANON = st.secrets["supabase"]["anon_key"]
SUPABASE_SERVICE = st.secrets["supabase"]["service_role_key"]
BUCKET = st.secrets["supabase"].get("bucket", "faculty_uploads")

ADMIN_PASSWORD = st.secrets["app"].get("admin_password", "")

DEFAULT_DATE = date.today()


@st.cache_resource
def get_supabase() -> Client:
    # Use service role key so app can write without user auth
    return create_client(SUPABASE_URL, SUPABASE_SERVICE)


sb = get_supabase()


# ----------------------------
# Helpers (repeatable rows + PDF persistence)
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


def persist_pdf_uploader(label: str, widget_key: str, required: bool = False):
    """
    Keeps uploaded PDF bytes across reruns/validation errors.
    Returns stored dict: {"name":..., "bytes":...} or None.
    """
    store_key = f"{widget_key}__stored"
    uploaded = st.file_uploader(label, type=["pdf"], key=widget_key)

    if uploaded is not None:
        st.session_state[store_key] = {"name": uploaded.name, "bytes": uploaded.getvalue()}

    stored = st.session_state.get(store_key)

    if stored is not None and uploaded is None:
        colA, colB = st.columns([6, 1])
        colA.caption(f"✅ Uploaded: {stored['name']}")
        if colB.button("Clear", key=f"{widget_key}__clear"):
            st.session_state.pop(store_key, None)
            st.rerun()

    if required and stored is None:
        st.caption("⚠️ PDF required for this entry.")
    return stored


def upload_to_supabase_storage(file_dict: Dict[str, Any], path: str) -> str:
    """
    Uploads PDF bytes to Supabase Storage bucket (private).
    Returns stored path.
    """
    if not file_dict:
        raise ValueError("No file provided for upload.")
    data = file_dict["bytes"]
    name = file_dict["name"]
    if len(data) == 0:
        raise ValueError("Empty file uploaded.")

    # Upload (upsert to avoid collisions if rerun)
    sb.storage.from_(BUCKET).upload(
        path=path,
        file=data,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )
    return path


def signed_url(path: str, expires_in: int = 3600) -> str:
    """
    Create a signed URL for a private file (admin use).
    """
    res = sb.storage.from_(BUCKET).create_signed_url(path, expires_in)
    return res.get("signedURL", "")


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
        "date_text": "",
        "location": "",
        "organised_by": ""
    }


def course_factory():
    return {"_id": new_row_id(), "date_text": "", "course_name": "", "offered_by": "", "grade": ""}


def support_factory():
    return {"_id": new_row_id(), "project_name": "", "event_date_text": "", "place": "", "website_link": ""}


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
# UI Tabs
# ----------------------------
tab_entry, tab_admin = st.tabs(["📝 Data Entry", "🔐 Admin"])


# ============================
# TAB 1: DATA ENTRY
# ============================
with tab_entry:
    st.title("Faculty Data Collection (Supabase Database + Storage)")
    st.info("All data is stored permanently in Supabase (no loss after Streamlit sleep).")

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

    # 1 Basic
    st.subheader("1. Basic Details")
    faculty_name = st.text_input("Name of the Faculty *")
    designation = st.selectbox("Designation *", ["AP", "Associate Professor", "Professor"])
    st.divider()

    # 2 Membership
    st.subheader("2. Professional Membership")
    has_membership = st.radio("Professional Membership (Yes/No) *", ["No", "Yes"], horizontal=True)
    if has_membership == "Yes":
        for m in st.session_state["memberships"]:
            rid = m["_id"]
            cols = st.columns([3, 3, 2, 3, 1])
            m["body_name"] = cols[0].text_input("Body Name *", value=m["body_name"], key=f"m_body_{rid}")
            m["membership_number"] = cols[1].text_input("Membership Number *", value=m["membership_number"], key=f"m_no_{rid}")
            m["level"] = cols[2].selectbox("Level *", ["National", "International"],
                                           index=0 if m["level"] == "National" else 1, key=f"m_lvl_{rid}")
            m["grade_position"] = cols[3].text_input("Level/Grade/Position *", value=m["grade_position"], key=f"m_pos_{rid}")
            if cols[4].button("➖", key=f"m_rm_{rid}"):
                remove_row_by_id("memberships", rid)
                st.rerun()

        if st.button("➕ Add Membership"):
            add_row("memberships", membership_factory)
            st.rerun()

    st.divider()

    # 3 FDP/STTP
    st.subheader("3. As resource person in FDP/STTP")
    has_fdp = st.radio("Resource person entries (Yes/No) *", ["No", "Yes"], horizontal=True)
    if has_fdp == "Yes":
        for f in st.session_state["fdps"]:
            rid = f["_id"]
            cols0 = st.columns([2.2, 3.8, 1])
            f["program_type"] = cols0[0].selectbox("Select Type *", ["FDP", "STTP", "SWAYAM", "NPTEL", "MOOCs"], key=f"f_type_{rid}")
            f["program_name"] = cols0[1].text_input(f"Name of {f['program_type']} *", value=f["program_name"], key=f"f_name_{rid}")
            if cols0[2].button("➖", key=f"f_rm_{rid}"):
                remove_row_by_id("fdps", rid)
                st.rerun()

            cols = st.columns([2, 2, 3, 3])
            f["involvement"] = cols[0].selectbox("Attended / Organised *", ["Attended", "Organised"], key=f"f_inv_{rid}")
            f["date_text"] = cols[1].text_input("Date (DD/MM/YYYY) *", value=f["date_text"], key=f"f_date_{rid}")
            f["location"] = cols[2].text_input("Location *", value=f["location"], key=f"f_loc_{rid}")
            f["organised_by"] = cols[3].text_input("Organised By *", value=f["organised_by"], key=f"f_org_{rid}")
            st.markdown("---")

        if st.button("➕ Add Entry"):
            add_row("fdps", fdp_factory)
            st.rerun()

    st.divider()

    # 4 Courses
    st.subheader("4. Courses Passed")
    has_courses = st.radio("Courses Passed (Yes/No) *", ["No", "Yes"], horizontal=True)
    if has_courses == "Yes":
        for c in st.session_state["courses"]:
            rid = c["_id"]
            cols = st.columns([2, 3, 3, 2, 1])
            c["date_text"] = cols[0].text_input("Date (DD/MM/YYYY) *", value=c["date_text"], key=f"c_date_{rid}")
            c["course_name"] = cols[1].text_input("Course Name *", value=c["course_name"], key=f"c_name_{rid}")
            c["offered_by"] = cols[2].text_input("Course Offered By *", value=c["offered_by"], key=f"c_by_{rid}")
            c["grade"] = cols[3].text_input("Grade Obtained *", value=c["grade"], key=f"c_grade_{rid}")
            if cols[4].button("➖", key=f"c_rm_{rid}"):
                remove_row_by_id("courses", rid)
                st.rerun()

        if st.button("➕ Add Course"):
            add_row("courses", course_factory)
            st.rerun()

    st.divider()

    # 5 Student support
    st.subheader("5. Faculty Support in Student Innovative Projects")
    has_support = st.radio("Support Provided (Yes/No) *", ["No", "Yes"], horizontal=True)
    if has_support == "Yes":
        for s in st.session_state["student_support"]:
            rid = s["_id"]
            cols = st.columns([3, 2, 2, 3, 1])
            s["project_name"] = cols[0].text_input("Name of Project/Initiative/Event *", value=s["project_name"], key=f"s_name_{rid}")
            s["event_date_text"] = cols[1].text_input("Date of Event (DD/MM/YYYY) *", value=s["event_date_text"], key=f"s_date_{rid}")
            s["place"] = cols[2].text_input("Place of Event *", value=s["place"], key=f"s_place_{rid}")
            s["website_link"] = cols[3].text_input("Website Link (if any)", value=s["website_link"], key=f"s_link_{rid}")
            if cols[4].button("➖", key=f"s_rm_{rid}"):
                remove_row_by_id("student_support", rid)
                st.rerun()

        if st.button("➕ Add Project/Initiative/Event"):
            add_row("student_support", support_factory)
            st.rerun()

    st.divider()

    # 6 Industry
    st.subheader("6. Faculty Internship/Training/Collaboration with Industry")
    has_industry = st.radio("Industry entries (Yes/No) *", ["No", "Yes"], horizontal=True)
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

        if st.button("➕ Add Industry Entry"):
            add_row("industry", industry_factory)
            st.rerun()

    st.divider()

    # 7 Academic research (Yes/No) + pubs
    st.subheader("7. Academic Research")
    has_academic = st.radio("Academic Research entries (Yes/No) *", ["No", "Yes"], horizontal=True)

    pub_confirm = True
    if has_academic == "Yes":
        st.markdown("### 7A. Journal & Conference Publications (PDF required)")
        for p in st.session_state["pubs_jc"]:
            rid = p["_id"]
            cols = st.columns([1.6, 3.4, 2.2, 2.4, 2.8, 1])
            p["pub_type"] = cols[0].selectbox("Type *", ["Journal", "Conference"], key=f"jc_type_{rid}")
            p["title"] = cols[1].text_input("Title *", value=p["title"], key=f"jc_title_{rid}")
            p["doi"] = cols[2].text_input("DOI *", value=p["doi"], key=f"jc_doi_{rid}")
            p["pub_date"] = cols[3].date_input("Publication date *", value=p["pub_date"], key=f"jc_date_{rid}")
            with cols[4]:
                persist_pdf_uploader("Upload PDF *", widget_key=f"jc_pdf_{rid}", required=True)
            if cols[5].button("➖", key=f"jc_rm_{rid}"):
                st.session_state.pop(f"jc_pdf_{rid}__stored", None)
                remove_row_by_id("pubs_jc", rid)
                st.rerun()

        if st.button("➕ Add Journal/Conference Publication"):
            add_row("pubs_jc", jc_pub_factory)
            st.rerun()

        pub_confirm = st.checkbox("I confirm PDFs match publication entries above.", value=False)

    st.divider()

    # 7B Books
    st.markdown("### 7B. Books / Book Chapters")
    has_books = st.radio("Books / Book Chapters entries (Yes/No) *", ["No", "Yes"], horizontal=True)

    if has_books == "Yes":
        for b in st.session_state["books"]:
            rid = b["_id"]
            cols = st.columns([1.6, 3.6, 2.6, 2.4, 2.4, 1])
            b["item_type"] = cols[0].selectbox("Type *", ["Book", "Book Chapter"], key=f"bk_type_{rid}")
            b["title"] = cols[1].text_input("Title *", value=b["title"], key=f"bk_title_{rid}")
            b["publisher"] = cols[2].text_input("Publisher (optional)", value=b["publisher"], key=f"bk_publisher_{rid}")
            b["pub_date"] = cols[3].date_input("Publication date (optional)", value=b["pub_date"], key=f"bk_date_{rid}")
            with cols[4]:
                persist_pdf_uploader("Upload PDF (optional)", widget_key=f"bk_pdf_{rid}")
            if cols[5].button("➖", key=f"bk_rm_{rid}"):
                st.session_state.pop(f"bk_pdf_{rid}__stored", None)
                remove_row_by_id("books", rid)
                st.rerun()

        if st.button("➕ Add Book / Book Chapter"):
            add_row("books", book_factory)
            st.rerun()

    st.divider()

    # 7C Patents
    st.markdown("### 7C. Patents / Working Models / Prototypes (last 3 years)")
    has_patents = st.radio("Do you have patents / models / prototypes? *", ["No", "Yes"], horizontal=True)

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

        if st.button("➕ Add Item"):
            add_row("patents_models", patent_factory)
            st.rerun()

    st.divider()

    # 8 Sponsored
    st.subheader("8. Sponsored research projects received from external agencies")
    has_sponsored = st.radio("Sponsored projects (Yes/No) *", ["No", "Yes"], horizontal=True)

    proj_confirm = True
    if has_sponsored == "Yes":
        for sp in st.session_state["sponsored"]:
            rid = sp["_id"]
            cols1 = st.columns([2.0, 2.2, 2.2, 2.6, 1.2, 1])
            sp["project_date"] = cols1[0].date_input("Project date *", value=sp["project_date"], key=f"sp_date_{rid}")
            sp["pi_name"] = cols1[1].text_input("PI Name *", value=sp["pi_name"], key=f"sp_pi_{rid}")
            sp["co_pi"] = cols1[2].text_input("Co-PI (optional)", value=sp["co_pi"], key=f"sp_copi_{rid}")
            sp["dept_sanctioned"] = cols1[3].text_input("Name of Dept., where project is sanctioned *",
                                                        value=sp["dept_sanctioned"], key=f"sp_dept_{rid}")
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
            sp["amount_lakhs"] = cols2[3].number_input("Amount (Lakhs) *", min_value=0.0, step=0.5,
                                                       value=float(sp["amount_lakhs"]), key=f"sp_amt_{rid}")

            cols3 = st.columns([3, 3])
            with cols3[0]:
                persist_pdf_uploader("Upload Sanction/Approval Letter (PDF) *", widget_key=f"sp_san_{rid}", required=True)
            with cols3[1]:
                persist_pdf_uploader("Upload Completion Certificate (PDF) (if completed)", widget_key=f"sp_comp_{rid}")

            st.markdown("---")

        if st.button("➕ Add Sponsored Project"):
            add_row("sponsored", sponsored_factory)
            st.rerun()

        proj_confirm = st.checkbox("I confirm uploaded documents match sponsored projects above.", value=False)

    st.divider()

    # 9 Consultancy
    st.subheader("9. Consultancy Work")
    has_consultancy = st.radio("Consultancy work (Yes/No) *", ["No", "Yes"], horizontal=True)

    consult_confirm = True
    if has_consultancy == "Yes":
        for cw in st.session_state["consultancy"]:
            rid = cw["_id"]
            cols1 = st.columns([2.0, 2.2, 2.2, 2.6, 1.2, 1])
            cw["project_date"] = cols1[0].date_input("Consultancy date *", value=cw["project_date"], key=f"cw_date_{rid}")
            cw["pi_name"] = cols1[1].text_input("PI Name *", value=cw["pi_name"], key=f"cw_pi_{rid}")
            cw["co_pi"] = cols1[2].text_input("Co-PI (optional)", value=cw["co_pi"], key=f"cw_copi_{rid}")
            cw["dept_sanctioned"] = cols1[3].text_input("Name of Dept., where project is sanctioned *",
                                                        value=cw["dept_sanctioned"], key=f"cw_dept_{rid}")
            cw["status"] = cols1[4].selectbox("Status *", ["Ongoing", "Completed"], key=f"cw_status_{rid}")
            if cols1[5].button("➖", key=f"cw_rm_{rid}"):
                st.session_state.pop(f"cw_app_{rid}__stored", None)
                st.session_state.pop(f"cw_comp_{rid}__stored", None)
                remove_row_by_id("consultancy", rid)
                st.rerun()

            cols2 = st.columns([3, 2, 2, 2])
            cw["project_title"] = cols2[0].text_input("Project title *", value=cw["project_title"], key=f"cw_title_{rid}")
            cw["funding_agency"] = cols2[1].text_input("Funding agency / Client *", value=cw["funding_agency"], key=f"cw_ag_{rid}")
            cw["duration"] = cols2[2].text_input("Duration *", value=cw["duration"], key=f"cw_dur_{rid}")
            cw["amount_lakhs"] = cols2[3].number_input("Amount (Lakhs) *", min_value=0.0, step=0.5,
                                                       value=float(cw["amount_lakhs"]), key=f"cw_amt_{rid}")

            cols3 = st.columns([3, 3])
            with cols3[0]:
                persist_pdf_uploader("Upload Approval/Work Order (PDF) (optional)", widget_key=f"cw_app_{rid}")
            with cols3[1]:
                persist_pdf_uploader("Upload Completion/Report (PDF) (optional)", widget_key=f"cw_comp_{rid}")

            st.markdown("---")

        if st.button("➕ Add Consultancy Work"):
            add_row("consultancy", consultancy_factory)
            st.rerun()

        consult_confirm = st.checkbox("I confirm uploaded documents match consultancy items above.", value=False)

    # Submit
    if st.button("✅ Submit"):
        errors = []

        if not faculty_name.strip():
            errors.append("Name of the Faculty is required.")
        if has_academic == "Yes" and not pub_confirm:
            errors.append("Please confirm Journal/Conference PDFs matching.")
        if has_sponsored == "Yes" and not proj_confirm:
            errors.append("Please confirm Sponsored project documents matching.")
        if has_consultancy == "Yes" and not consult_confirm:
            errors.append("Please confirm Consultancy documents matching.")

        if has_membership == "Yes":
            for i, m in enumerate(st.session_state["memberships"], 1):
                if not all([m["body_name"].strip(), m["membership_number"].strip(), m["level"].strip(), m["grade_position"].strip()]):
                    errors.append(f"Membership #{i}: all fields required.")

        if has_fdp == "Yes":
            for i, f in enumerate(st.session_state["fdps"], 1):
                if not all([f["program_type"].strip(), f["program_name"].strip(), f["involvement"].strip(),
                            f["date_text"].strip(), f["location"].strip(), f["organised_by"].strip()]):
                    errors.append(f"Resource person entry #{i}: all fields required.")

        if has_courses == "Yes":
            for i, c in enumerate(st.session_state["courses"], 1):
                if not all([c["date_text"].strip(), c["course_name"].strip(), c["offered_by"].strip(), c["grade"].strip()]):
                    errors.append(f"Course #{i}: all fields required.")

        if has_support == "Yes":
            for i, s in enumerate(st.session_state["student_support"], 1):
                if not all([s["project_name"].strip(), s["event_date_text"].strip(), s["place"].strip()]):
                    errors.append(f"Student support #{i}: project name/date/place required.")

        if has_industry == "Yes":
            for i, a in enumerate(st.session_state["industry"], 1):
                if not all([a["activity_name"].strip(), a["company_place"].strip(), a["duration"].strip(), a["outcomes"].strip()]):
                    errors.append(f"Industry #{i}: all fields required.")

        if has_academic == "Yes":
            for i, p in enumerate(st.session_state["pubs_jc"], 1):
                rid = p["_id"]
                pdf = st.session_state.get(f"jc_pdf_{rid}__stored")
                if not all([p["pub_type"].strip(), p["title"].strip(), p["doi"].strip()]):
                    errors.append(f"Publication #{i}: Type/Title/DOI required.")
                if not pdf:
                    errors.append(f"Publication #{i}: PDF is required.")

        if has_sponsored == "Yes":
            for i, sp in enumerate(st.session_state["sponsored"], 1):
                rid = sp["_id"]
                sanction = st.session_state.get(f"sp_san_{rid}__stored")
                if not sanction:
                    errors.append(f"Sponsored project #{i}: Sanction PDF is required.")

        if errors:
            st.error("Please fix:\n- " + "\n- ".join(errors))
        else:
            submission_id = uuid.uuid4().hex[:12].upper()
            try:
                # 1) Insert submission
                sb.table("faculty_submission").insert({
                    "submission_id": submission_id,
                    "submitted_at": datetime.utcnow().isoformat(),
                    "faculty_name": faculty_name.strip(),
                    "designation": designation,
                    "has_membership": (has_membership == "Yes"),
                    "has_fdp": (has_fdp == "Yes"),
                    "has_courses": (has_courses == "Yes"),
                    "has_support": (has_support == "Yes"),
                    "has_industry": (has_industry == "Yes"),
                    "has_academic": (has_academic == "Yes"),
                    "has_books": (has_books == "Yes"),
                    "has_patents": (has_patents == "Yes"),
                    "has_sponsored": (has_sponsored == "Yes"),
                    "has_consultancy": (has_consultancy == "Yes"),
                }).execute()

                # 2) Membership
                if has_membership == "Yes":
                    rows = []
                    for m in st.session_state["memberships"]:
                        rows.append({
                            "submission_id": submission_id,
                            "body_name": m["body_name"].strip(),
                            "membership_number": m["membership_number"].strip(),
                            "level": m["level"],
                            "grade_position": m["grade_position"].strip(),
                        })
                    if rows:
                        sb.table("membership").insert(rows).execute()

                # 3) FDP
                if has_fdp == "Yes":
                    rows = []
                    for f in st.session_state["fdps"]:
                        rows.append({
                            "submission_id": submission_id,
                            "program_type": f["program_type"].strip(),
                            "program_name": f["program_name"].strip(),
                            "involvement": f["involvement"].strip(),
                            "date_text": f["date_text"].strip(),
                            "location": f["location"].strip(),
                            "organised_by": f["organised_by"].strip(),
                        })
                    if rows:
                        sb.table("fdp_sttp").insert(rows).execute()

                # 4) Courses
                if has_courses == "Yes":
                    rows = []
                    for c in st.session_state["courses"]:
                        rows.append({
                            "submission_id": submission_id,
                            "date_text": c["date_text"].strip(),
                            "course_name": c["course_name"].strip(),
                            "offered_by": c["offered_by"].strip(),
                            "grade": c["grade"].strip(),
                        })
                    if rows:
                        sb.table("courses").insert(rows).execute()

                # 5) Student support
                if has_support == "Yes":
                    rows = []
                    for s in st.session_state["student_support"]:
                        rows.append({
                            "submission_id": submission_id,
                            "project_name": s["project_name"].strip(),
                            "event_date_text": s["event_date_text"].strip(),
                            "place": s["place"].strip(),
                            "website_link": (s.get("website_link") or "").strip(),
                        })
                    if rows:
                        sb.table("student_support").insert(rows).execute()

                # 6) Industry
                if has_industry == "Yes":
                    rows = []
                    for a in st.session_state["industry"]:
                        rows.append({
                            "submission_id": submission_id,
                            "activity_name": a["activity_name"].strip(),
                            "company_place": a["company_place"].strip(),
                            "duration": a["duration"].strip(),
                            "outcomes": a["outcomes"].strip(),
                        })
                    if rows:
                        sb.table("industry").insert(rows).execute()

                # 7A) Publications (upload required PDF)
                if has_academic == "Yes":
                    rows = []
                    for p in st.session_state["pubs_jc"]:
                        rid = p["_id"]
                        pdf = st.session_state.get(f"jc_pdf_{rid}__stored")
                        pdf_path = f"{submission_id}/publications/{rid}_{pdf['name']}"
                        upload_to_supabase_storage(pdf, pdf_path)
                        rows.append({
                            "submission_id": submission_id,
                            "pub_type": p["pub_type"],
                            "title": p["title"].strip(),
                            "doi": p["doi"].strip(),
                            "pub_date": p["pub_date"].isoformat(),
                            "pdf_bucket": BUCKET,
                            "pdf_path": pdf_path,
                        })
                    if rows:
                        sb.table("publications_jc").insert(rows).execute()

                # 7B) Books (optional PDF)
                if has_books == "Yes":
                    rows = []
                    for b in st.session_state["books"]:
                        rid = b["_id"]
                        pdf = st.session_state.get(f"bk_pdf_{rid}__stored")
                        pdf_bucket, pdf_path = None, None
                        if pdf:
                            pdf_path = f"{submission_id}/books/{rid}_{pdf['name']}"
                            upload_to_supabase_storage(pdf, pdf_path)
                            pdf_bucket = BUCKET
                        rows.append({
                            "submission_id": submission_id,
                            "item_type": b["item_type"],
                            "title": b["title"].strip(),
                            "publisher": (b.get("publisher") or "").strip(),
                            "pub_date": b["pub_date"].isoformat() if b.get("pub_date") else None,
                            "pdf_bucket": pdf_bucket,
                            "pdf_path": pdf_path,
                        })
                    if rows:
                        sb.table("books_chapters").insert(rows).execute()

                # 7C) Patents/models (optional PDF)
                if has_patents == "Yes":
                    rows = []
                    for pm in st.session_state["patents_models"]:
                        rid = pm["_id"]
                        pdf = st.session_state.get(f"pm_pdf_{rid}__stored")
                        pdf_bucket, pdf_path = None, None
                        if pdf:
                            pdf_path = f"{submission_id}/patents/{rid}_{pdf['name']}"
                            upload_to_supabase_storage(pdf, pdf_path)
                            pdf_bucket = BUCKET
                        rows.append({
                            "submission_id": submission_id,
                            "item_type": pm["item_type"],
                            "title": pm["title"].strip(),
                            "item_date": pm["item_date"].isoformat(),
                            "details": (pm.get("details") or "").strip(),
                            "pdf_bucket": pdf_bucket,
                            "pdf_path": pdf_path,
                        })
                    if rows:
                        sb.table("patents_models").insert(rows).execute()

                # 8) Sponsored (sanction required)
                if has_sponsored == "Yes":
                    rows = []
                    for sp in st.session_state["sponsored"]:
                        rid = sp["_id"]
                        san = st.session_state.get(f"sp_san_{rid}__stored")
                        comp = st.session_state.get(f"sp_comp_{rid}__stored")

                        san_path = f"{submission_id}/sponsored/{rid}_SAN_{san['name']}"
                        upload_to_supabase_storage(san, san_path)

                        comp_path = None
                        if comp:
                            comp_path = f"{submission_id}/sponsored/{rid}_COMP_{comp['name']}"
                            upload_to_supabase_storage(comp, comp_path)

                        rows.append({
                            "submission_id": submission_id,
                            "project_date": sp["project_date"].isoformat(),
                            "pi_name": sp["pi_name"].strip(),
                            "co_pi": (sp.get("co_pi") or "").strip(),
                            "dept_sanctioned": sp["dept_sanctioned"].strip(),
                            "project_title": sp["project_title"].strip(),
                            "funding_agency": sp["funding_agency"].strip(),
                            "duration": sp["duration"].strip(),
                            "amount_lakhs": float(sp["amount_lakhs"]),
                            "status": sp["status"],
                            "sanction_bucket": BUCKET,
                            "sanction_path": san_path,
                            "completion_bucket": BUCKET if comp_path else None,
                            "completion_path": comp_path,
                        })
                    if rows:
                        sb.table("sponsored_projects").insert(rows).execute()

                # 9) Consultancy (optional PDFs)
                if has_consultancy == "Yes":
                    rows = []
                    for cw in st.session_state["consultancy"]:
                        rid = cw["_id"]
                        app_pdf = st.session_state.get(f"cw_app_{rid}__stored")
                        comp_pdf = st.session_state.get(f"cw_comp_{rid}__stored")

                        app_path = None
                        if app_pdf:
                            app_path = f"{submission_id}/consultancy/{rid}_APP_{app_pdf['name']}"
                            upload_to_supabase_storage(app_pdf, app_path)

                        comp_path = None
                        if comp_pdf:
                            comp_path = f"{submission_id}/consultancy/{rid}_COMP_{comp_pdf['name']}"
                            upload_to_supabase_storage(comp_pdf, comp_path)

                        rows.append({
                            "submission_id": submission_id,
                            "project_date": cw["project_date"].isoformat(),
                            "pi_name": cw["pi_name"].strip(),
                            "co_pi": (cw.get("co_pi") or "").strip(),
                            "dept_sanctioned": cw["dept_sanctioned"].strip(),
                            "project_title": cw["project_title"].strip(),
                            "funding_agency": cw["funding_agency"].strip(),
                            "duration": cw["duration"].strip(),
                            "amount_lakhs": float(cw["amount_lakhs"]),
                            "status": cw["status"],
                            "approval_bucket": BUCKET if app_path else None,
                            "approval_path": app_path,
                            "completion_bucket": BUCKET if comp_path else None,
                            "completion_path": comp_path,
                        })
                    if rows:
                        sb.table("consultancy_work").insert(rows).execute()

                st.success(f"✅ Submitted successfully | Submission ID: {submission_id}")

            except Exception as e:
                st.error("Submission failed. Error details:")
                st.write("Type:", type(e).__name__)
                st.write("repr:", repr(e))
                st.exception(e)


# ============================
# TAB 2: ADMIN (password protected)
# ============================
with tab_admin:
    st.title("Admin Downloads")

    if not ADMIN_PASSWORD:
        st.error("Admin password not set in secrets.")
        st.stop()

    entered = st.text_input("Enter Admin Password", type="password")
    if entered != ADMIN_PASSWORD:
        st.warning("Enter correct password to access admin.")
        st.stop()

    st.success("Admin unlocked ✅")

    def fetch_table(name: str) -> pd.DataFrame:
        res = sb.table(name).select("*").execute()
        data = res.data if hasattr(res, "data") else []
        return pd.DataFrame(data)

    tables = [
        "faculty_submission",
        "membership",
        "fdp_sttp",
        "courses",
        "student_support",
        "industry",
        "publications_jc",
        "books_chapters",
        "patents_models",
        "sponsored_projects",
        "consultancy_work",
    ]

    dfs = {t: fetch_table(t) for t in tables}

    st.subheader("Quick Summary")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Submissions", len(dfs["faculty_submission"]))
    c2.metric("J/C Publications", len(dfs["publications_jc"]))
    c3.metric("Patents/Models", len(dfs["patents_models"]))
    c4.metric("Sponsored", len(dfs["sponsored_projects"]))
    c5.metric("Consultancy", len(dfs["consultancy_work"]))

    st.divider()

    st.subheader("Download CSV (per table)")
    for t, df in dfs.items():
        st.download_button(
            f"⬇️ {t}.csv",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"{t}.csv",
            mime="text/csv",
            key=f"dl_{t}",
        )

    st.divider()

    st.subheader("Generate signed link for a stored PDF (private bucket)")
    st.caption("Paste the file path stored in pdf_path / sanction_path / etc. Link valid for 1 hour.")
    path = st.text_input("Storage file path (e.g. SUBID/publications/...)")
    if st.button("Create signed URL"):
        if not path.strip():
            st.warning("Enter a valid path.")
        else:
            try:
                url = signed_url(path.strip(), expires_in=3600)
                if url:
                    st.write(url)
                else:
                    st.error("Could not create signed URL (check path).")
            except Exception as e:
                st.error(repr(e))

    st.divider()

    st.subheader("Preview")
    table = st.selectbox("Select table", tables)
    st.dataframe(dfs[table], use_container_width=True)

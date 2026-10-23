"""Job Application Assistant - Streamlit GUI.

Run with:  streamlit run app.py

Workflow:
  1. Upload one or more resumes (PDF/DOCX/TXT).
  2. Answer a short questionnaire (location/country, H1B sponsorship need,
     job category, date posted range, etc.).
  3. The tool searches jobs (Adzuna API if configured, else bundled demo
     data), scores each posting against every uploaded resume, and shows
     the top 10 recommended applications with a rough ATS score, best
     resume to use, and an H1B-sponsorship likelihood heuristic.
  4. For any job, you can generate a tailored version of the recommended
     resume (keyword gap suggestions) and download it.
"""
from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from job_search import ADZUNA_COUNTRIES, DATE_RANGE_OPTIONS, get_provider
from resume_parser import parse_resume
from scoring import rank_jobs_for_resumes
from skills import ADZUNA_CATEGORY_TAGS, JOB_CATEGORY_KEYWORDS
from tailor import build_tailoring_suggestions, tailor_resume_docx_bytes, tailor_resume_text

load_dotenv()

st.set_page_config(page_title="Job Application Assistant", page_icon="briefcase", layout="wide")

if "resumes" not in st.session_state:
    st.session_state.resumes = {}  # filename -> ParsedResume
if "results" not in st.session_state:
    st.session_state.results = []
if "searched" not in st.session_state:
    st.session_state.searched = False

st.title("Job Application Assistant")
st.caption(
    "Upload resumes, answer a few questions, and get a ranked shortlist of jobs to apply to - "
    "with a suggested resume, a rough ATS score, and an H1B sponsorship likelihood for each."
)

# ---------------------------------------------------------------------------
# Sidebar: API credentials
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Job search source")
    env_app_id = os.environ.get("ADZUNA_APP_ID", "")
    env_app_key = os.environ.get("ADZUNA_APP_KEY", "")

    app_id = st.text_input("Adzuna App ID (optional)", value=env_app_id, type="default")
    app_key = st.text_input("Adzuna App Key (optional)", value=env_app_key, type="password")

    st.markdown(
        "Get a free key at [developer.adzuna.com](https://developer.adzuna.com/). "
        "Without a key, the tool runs on bundled **demo data** so you can try the full workflow."
    )

    provider = get_provider(app_id, app_key)
    using_demo = provider.__class__.__name__ == "DemoProvider"
    if using_demo:
        st.warning("Running in DEMO mode (sample job data). Add your Adzuna keys above for real listings.")
    else:
        st.success("Connected to the Adzuna API for live job search.")

# ---------------------------------------------------------------------------
# Step 1: Resumes
# ---------------------------------------------------------------------------
st.header("1. Upload your resume(s)")
st.write("You can upload multiple resumes (e.g. tailored for different roles). The tool will pick the best-fit resume per job.")

uploaded_files = st.file_uploader(
    "Resumes (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"], accept_multiple_files=True
)

if uploaded_files:
    for f in uploaded_files:
        if f.name not in st.session_state.resumes:
            try:
                parsed = parse_resume(f.name, f.getvalue())
                st.session_state.resumes[f.name] = parsed
            except RuntimeError as e:
                st.error(str(e))

if st.session_state.resumes:
    st.success(f"{len(st.session_state.resumes)} resume(s) loaded: {', '.join(st.session_state.resumes.keys())}")
    with st.expander("Preview extracted resume keywords"):
        for name, parsed in st.session_state.resumes.items():
            st.markdown(f"**{name}** ({parsed.word_count} words)")
            st.write(", ".join(parsed.keywords[:20]) or "No keywords extracted")
            missing_sections = {"experience", "education", "skills"} - set(parsed.sections_found)
            if missing_sections:
                st.caption(f"Sections not clearly detected: {', '.join(missing_sections)}")
            if not parsed.has_contact_info:
                st.caption("No email/phone detected - ATS systems may penalize missing contact info.")

    remove_choice = st.selectbox(
        "Remove a resume", ["(none)"] + list(st.session_state.resumes.keys()), key="remove_resume"
    )
    if remove_choice != "(none)" and st.button("Remove selected resume"):
        del st.session_state.resumes[remove_choice]
        st.rerun()
else:
    st.info("Upload at least one resume to continue.")

# ---------------------------------------------------------------------------
# Step 2: Questionnaire
# ---------------------------------------------------------------------------
st.header("2. Tell us what you're looking for")

with st.form("search_form"):
    col1, col2 = st.columns(2)

    with col1:
        country_name = st.selectbox(
            "Country", list(ADZUNA_COUNTRIES.keys()), index=list(ADZUNA_COUNTRIES.keys()).index("United States")
        )
        where = st.text_input("City/state (optional, within the country above)", value="")
        job_title_override = st.text_input(
            "Specific job title / keywords (optional - leave blank to auto-use your resume's top keywords)",
            value="",
        )

    with col2:
        h1b_choice = st.radio(
            "H1B / visa sponsorship needed?",
            ["No preference", "Yes, I need sponsorship", "No, I have work authorization"],
            index=0,
        )
        category_choice = st.selectbox("Job category", ["Any"] + list(JOB_CATEGORY_KEYWORDS.keys()))
        date_choice = st.selectbox("Job posted within", list(DATE_RANGE_OPTIONS.keys()), index=3)

    results_per_search = st.slider("Max results to scan per resume", 10, 50, 20)

    submitted = st.form_submit_button("Search jobs", use_container_width=True)

if submitted:
    if not st.session_state.resumes:
        st.error("Please upload at least one resume before searching.")
    else:
        country_code = ADZUNA_COUNTRIES[country_name]
        max_days_old = DATE_RANGE_OPTIONS[date_choice]
        want_h1b = h1b_choice == "Yes, I need sponsorship"
        # Plain-text fallback term for the "what" search query (e.g. "engineer").
        category_fallback_term = JOB_CATEGORY_KEYWORDS.get(category_choice, [""])[0] if category_choice != "Any" else ""
        # Adzuna's API only accepts its own fixed category tags (e.g. "engineering-jobs");
        # arbitrary keywords here cause an HTTP 400, so look up the real tag separately.
        api_category_tag = ADZUNA_CATEGORY_TAGS.get(category_choice) or ""

        all_jobs = []
        with st.spinner("Searching jobs for each resume..."):
            for name, parsed in st.session_state.resumes.items():
                if job_title_override.strip():
                    what_query = job_title_override.strip()
                else:
                    top_terms = [k for k in parsed.keywords if " " not in k][:6]
                    what_query = " ".join(top_terms) or (category_fallback_term or "")

                try:
                    jobs = provider.search(
                        country_code=country_code,
                        what=what_query,
                        where=where,
                        max_days_old=max_days_old,
                        results_per_page=results_per_search,
                        category_tag=api_category_tag,
                    )
                    all_jobs.extend(jobs)
                except Exception as e:
                    st.error(f"Search failed for resume '{name}': {e}")

        if category_choice != "Any":
            cat_terms = [t.lower() for t in JOB_CATEGORY_KEYWORDS.get(category_choice, [])]
            all_jobs = [
                j for j in all_jobs
                if any(t in (j.title + " " + j.description + " " + j.category).lower() for t in cat_terms)
            ]

        ranked = rank_jobs_for_resumes(
            all_jobs, list(st.session_state.resumes.values()), want_h1b=want_h1b, top_n=10
        )
        st.session_state.results = ranked
        st.session_state.searched = True
        st.session_state.want_h1b = want_h1b

        if not ranked:
            st.warning("No jobs matched your criteria. Try widening the date range, location, or category.")

# ---------------------------------------------------------------------------
# Step 3: Results
# ---------------------------------------------------------------------------
if st.session_state.searched and st.session_state.results:
    st.header("3. Top recommended applications")
    st.caption(
        "Ranked by a blend of rough ATS fit score and (if requested) H1B sponsorship likelihood. "
        "H1B detection is a best-effort keyword heuristic based on the job description text - always verify with the employer."
    )

    table_rows = []
    for i, job in enumerate(st.session_state.results, start=1):
        table_rows.append(
            {
                "#": i,
                "Title": job.title,
                "Company": job.company,
                "Location": job.location,
                "Posted": job.created[:10],
                "Best Resume": job.matched_resume,
                "ATS Score": job.ats_score,
                "H1B Likelihood": job.h1b_label,
                "Category": job.category,
            }
        )
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    st.subheader("Details & resume tailoring")
    for i, job in enumerate(st.session_state.results, start=1):
        with st.expander(f"#{i} - {job.title} @ {job.company} (ATS {job.ats_score}/100, {job.h1b_label})"):
            cols = st.columns([2, 1])
            with cols[0]:
                st.markdown(f"**Location:** {job.location}  \n**Category:** {job.category or 'N/A'}  \n**Posted:** {job.created[:10]}")
                if job.salary_min or job.salary_max:
                    st.markdown(f"**Salary range:** {job.salary_min or '?'} - {job.salary_max or '?'}")
                st.markdown(f"**Apply link:** [{job.url}]({job.url})" if job.url else "_No link available (demo data)_")
                st.markdown("**Job description:**")
                st.write(job.description)

            with cols[1]:
                st.markdown(f"**Recommended resume:** {job.matched_resume}")
                st.markdown("**ATS score breakdown:**")
                for k, v in job.score_breakdown.items():
                    if k.startswith("_"):
                        continue
                    st.caption(f"- {k}: {v}")

                resume_obj = st.session_state.resumes.get(job.matched_resume)
                if resume_obj and st.button("Tailor resume for this job", key=f"tailor_{job.job_id}_{i}"):
                    suggestions = build_tailoring_suggestions(resume_obj, job)
                    st.session_state[f"tailored_{job.job_id}_{i}"] = suggestions

                tailor_key = f"tailored_{job.job_id}_{i}"
                if resume_obj and tailor_key in st.session_state:
                    suggestions = st.session_state[tailor_key]
                    st.markdown(f"Keyword match: **{suggestions['match_percent']}%**")
                    if suggestions["missing_keywords"]:
                        st.markdown("Consider adding (if truthful):")
                        st.write(", ".join(suggestions["missing_keywords"][:20]))
                    else:
                        st.markdown("Resume already covers this job's key terms well.")

                    tailored_txt = tailor_resume_text(resume_obj, job)
                    st.download_button(
                        "Download tailored resume (.txt)",
                        data=tailored_txt,
                        file_name=f"tailored_{resume_obj.name.rsplit('.',1)[0]}_{job.company.replace(' ','_')}.txt",
                        mime="text/plain",
                        key=f"dl_txt_{job.job_id}_{i}",
                    )
                    try:
                        docx_bytes = tailor_resume_docx_bytes(resume_obj, job)
                        st.download_button(
                            "Download tailored resume (.docx)",
                            data=docx_bytes,
                            file_name=f"tailored_{resume_obj.name.rsplit('.',1)[0]}_{job.company.replace(' ','_')}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_docx_{job.job_id}_{i}",
                        )
                    except RuntimeError as e:
                        st.caption(str(e))

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

from analytics import get_visit_count, get_visitor_names, log_visitor_name, record_visit
from job_search import ADZUNA_COUNTRIES, DATE_RANGE_OPTIONS, JOB_TYPE_OPTIONS, get_provider
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
if "visit_counted" not in st.session_state:
    # Count once per browser session (not on every widget rerun), using a
    # free zero-setup counter API so the developer can see total visits
    # without exposing anything to regular visitors.
    record_visit()
    st.session_state.visit_counted = True

st.title("Job Application Assistant")
st.caption(
    "Upload resumes, answer a few questions, and get a ranked shortlist of jobs to apply to - "
    "with a suggested resume, a rough ATS score, and an H1B sponsorship likelihood for each."
)

visitor_name = st.text_input(
    "Your name (optional)",
    value="",
    help="Purely optional - lets the developer know who's used this tool. Leave blank to stay anonymous.",
)
if visitor_name.strip() and st.session_state.get("logged_name") != visitor_name.strip():
    if log_visitor_name(visitor_name):
        st.session_state.logged_name = visitor_name.strip()

# Developer-only visit stats, shown only when visiting with ?admin=1 in the
# URL - e.g. https://oreo-job-agent.streamlit.app/?admin=1
if st.query_params.get("admin") == "1":
    visit_total = get_visit_count()
    if visit_total is not None:
        st.info(f"📊 Developer stats: {visit_total} total visits recorded.")
    else:
        st.info("📊 Developer stats: visit counter temporarily unavailable.")

    names_logged = get_visitor_names()
    if names_logged:
        with st.expander(f"👤 Visitors who gave their name ({len(names_logged)})"):
            for entry in reversed(names_logged[-50:]):
                st.caption(f"{entry.get('name', '?')} — {entry.get('time_utc', '?')}")

# ---------------------------------------------------------------------------
# Sidebar: API credentials
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Job search source")
    server_app_id = os.environ.get("ADZUNA_APP_ID", "")
    server_app_key = os.environ.get("ADZUNA_APP_KEY", "")
    server_key_configured = bool(server_app_id and server_app_key)

    if server_key_configured:
        st.success(
            "This app is configured with a shared Adzuna API key for live job search. "
            "Searches made here draw from that shared key's daily quota."
        )
        with st.expander("Use your own Adzuna API key instead (optional)"):
            st.caption(
                "Prefer not to share the quota? Get a free key at "
                "[developer.adzuna.com](https://developer.adzuna.com/) and enter it below - "
                "it's only used in your current browser session and never shown to anyone else."
            )
            own_app_id = st.text_input("Your Adzuna App ID", value="", type="default")
            own_app_key = st.text_input("Your Adzuna App Key", value="", type="password")
        app_id = own_app_id or server_app_id
        app_key = own_app_key or server_app_key
    else:
        app_id = st.text_input("Adzuna App ID (optional)", value="", type="default")
        app_key = st.text_input("Adzuna App Key (optional)", value="", type="password")
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
        job_type_choice = st.selectbox(
            "Job type",
            list(JOB_TYPE_OPTIONS.keys()),
            help="Full-time/Part-time filter how many hours per week; Contract/Permanent filter the employment arrangement. Pick 'Any' to skip this filter.",
        )
        date_choice = st.selectbox("Job posted within", list(DATE_RANGE_OPTIONS.keys()), index=3)

    results_per_search = st.slider(
        "Max results to scan per resume",
        10,
        50,
        20,
        help=(
            "Controls how many job postings are pulled **per uploaded resume** before scoring "
            "and ranking - not how many results you'll see at the end (you'll always get the "
            "top 10 best matches overall).\n\n"
            "- **Higher** (e.g. 50): casts a wider net, more candidates considered before picking "
            "the top 10 -> better chance of finding strong matches, but takes a bit longer and "
            "uses more of your API call quota per search.\n"
            "- **Lower** (e.g. 10): faster and lighter on quota, but might miss good matches "
            "further down the results list."
        ),
    )

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
        api_employment_type = JOB_TYPE_OPTIONS.get(job_type_choice) or ""

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
                        employment_type=api_employment_type,
                        anchor_term=category_fallback_term,
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
                "Job Type": job.employment_type_label,
            }
        )
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    st.subheader("Details & resume tailoring")
    for i, job in enumerate(st.session_state.results, start=1):
        with st.expander(f"#{i} - {job.title} @ {job.company} (ATS {job.ats_score}/100, {job.h1b_label})"):
            cols = st.columns([2, 1])
            with cols[0]:
                st.markdown(f"**Location:** {job.location}  \n**Category:** {job.category or 'N/A'}  \n**Job type:** {job.employment_type_label}  \n**Posted:** {job.created[:10]}")
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
                    if suggestions.get("is_short_description"):
                        st.caption(
                            f"⚠️ This posting's description is short (~{suggestions['job_word_count']} words), "
                            "likely a truncated snippet from the job board/API rather than the full ad. "
                            "Fewer key terms could be extracted from it than a full posting would have."
                        )

                    bcol, acol = st.columns(2)
                    with bcol:
                        st.metric(
                            "Before tailoring",
                            f"{suggestions['ats_before']}/100",
                            help=f"{suggestions['match_percent_before']}% of this job's key terms matched your current resume.",
                        )
                    with acol:
                        st.metric(
                            "After tailoring",
                            f"{suggestions['ats_after']}/100",
                            delta=suggestions["ats_after"] - suggestions["ats_before"],
                            help=f"{suggestions['match_percent_after']}% match IF every suggested keyword below is genuinely added.",
                        )

                    if suggestions["missing_keywords"]:
                        st.markdown("**Keywords that would be added (only keep what's truthful):**")
                        st.write(", ".join(suggestions["missing_keywords"][:20]))
                    else:
                        st.markdown("Nothing to add - resume already covers this job's key terms well.")

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

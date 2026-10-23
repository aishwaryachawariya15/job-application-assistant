"""Rule-based resume tailoring: builds a tailored version of a resume for
a specific job by surfacing missing high-value keywords (taken from the
job posting's own vocabulary) and appending a clearly-labeled "Additional
Relevant Keywords" section. Offline, no API key required.

Also computes a before/after preview so the user can see exactly how much
the match improves if they genuinely add the suggested keywords, instead
of just handing back a modified file with no explanation of what changed.
"""
from __future__ import annotations

import io

from resume_parser import ParsedResume
from job_search import JobPosting
from scoring import ats_score
from skills import SKILLS_DB


def build_tailoring_suggestions(resume: ParsedResume, job: JobPosting) -> dict:
    """Return a dict describing the match BEFORE tailoring, and a simulated
    match AFTER adding every suggested missing keyword (i.e. the best-case
    result if the candidate genuinely incorporates all of them).
    """
    ats_before, breakdown = ats_score(resume, job)

    matched_keywords = breakdown["_matched_keywords"]
    missing_keywords = breakdown["_missing_keywords"]
    match_percent_before = breakdown["_match_percent"]
    format_points = breakdown["_format_points"]
    relevant_skill_count_before = breakdown["_relevant_skill_count"]

    # Simulate adding every missing keyword: by definition the job-keyword
    # match goes to 100%, and any missing keyword that's also a recognized
    # hard skill (SKILLS_DB) now counts toward the skill-depth component too.
    has_any_job_keywords = bool(matched_keywords or missing_keywords)
    match_percent_after = 100.0 if has_any_job_keywords else 0.0
    keyword_points_after = round(min(match_percent_after, 100) * 0.6)

    newly_recognized_skills = [kw for kw in missing_keywords if kw in SKILLS_DB]
    skill_points_after = min((relevant_skill_count_before + len(newly_recognized_skills)) * 3, 15)

    ats_after = max(0, min(100, keyword_points_after + format_points + skill_points_after))

    return {
        "ats_before": ats_before,
        "ats_after": ats_after,
        "match_percent_before": match_percent_before,
        "match_percent_after": match_percent_after,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "is_short_description": breakdown.get("_is_short_description", False),
        "job_word_count": breakdown.get("_job_word_count", 0),
        # Back-compat key some UI code may still reference.
        "match_percent": match_percent_before,
    }


def tailor_resume_text(resume: ParsedResume, job: JobPosting) -> str:
    """Return a tailored plain-text resume: original content plus an
    inserted section calling out keywords from the job posting that were
    missing from the original resume, framed for the candidate to
    genuinely confirm/add if truthfully applicable to their background.
    Clearly shows the before/after match so it's obvious what changed.
    """
    s = build_tailoring_suggestions(resume, job)
    missing = s["missing_keywords"]

    tailored_section_lines = [
        "",
        "=" * 70,
        f"TAILORED FOR: {job.title} at {job.company}",
        "=" * 70,
        "",
        f"BEFORE TAILORING: {s['match_percent_before']}% of this job's key terms matched "
        f"(estimated ATS score: {s['ats_before']}/100)",
        f"AFTER TAILORING:  {s['match_percent_after']}% of this job's key terms matched "
        f"(estimated ATS score: {s['ats_after']}/100, IF all keywords below are genuinely added)",
        "",
        "KEYWORDS ADDED IN THIS TAILORED VERSION",
        "(Only keep items below that genuinely reflect your real experience - do not misrepresent your background.)",
    ]
    if missing:
        for kw in missing[:20]:
            tailored_section_lines.append(f"  + {kw}")
    else:
        tailored_section_lines.append("  (Nothing to add - your resume already covers this job's key terms.)")

    tailored_section_lines.append("=" * 70)

    return resume.raw_text.rstrip() + "\n" + "\n".join(tailored_section_lines)


def tailor_resume_docx_bytes(resume: ParsedResume, job: JobPosting) -> bytes:
    """Return a .docx file (as bytes) containing the original resume text
    paragraph-by-paragraph plus the tailored keyword section (with a clear
    before/after summary), so it can be offered as a download in the UI.
    """
    try:
        import docx
        from docx.shared import Pt
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is required to export tailored resumes. Install with: pip install python-docx"
        ) from exc

    s = build_tailoring_suggestions(resume, job)
    missing = s["missing_keywords"]

    document = docx.Document()

    for line in resume.raw_text.splitlines():
        document.add_paragraph(line)

    document.add_paragraph("")
    heading = document.add_paragraph()
    run = heading.add_run(f"TAILORED FOR: {job.title} at {job.company}")
    run.bold = True
    run.font.size = Pt(13)

    before_after = document.add_paragraph()
    before_after.add_run(
        f"BEFORE: {s['match_percent_before']}% key-term match (ATS ~{s['ats_before']}/100)  ->  "
        f"AFTER: {s['match_percent_after']}% key-term match (ATS ~{s['ats_after']}/100, if all keywords below are added)"
    ).italic = True

    document.add_paragraph(
        "Keywords added in this tailored version "
        "(only keep items that genuinely reflect your real experience):"
    )
    if missing:
        for kw in missing[:20]:
            document.add_paragraph(f"+ {kw}")
    else:
        document.add_paragraph("Nothing to add - your resume already covers this job's key terms.")

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()

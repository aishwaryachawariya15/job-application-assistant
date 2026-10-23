"""Rule-based resume tailoring: builds a tailored version of a resume for
a specific job by surfacing missing high-value keywords and appending a
clearly-labeled "Additional Relevant Keywords" section. Offline, no API
key required.
"""
from __future__ import annotations

import io

from resume_parser import ParsedResume
from job_search import JobPosting
from scoring import keyword_match_score


def build_tailoring_suggestions(resume: ParsedResume, job: JobPosting) -> dict:
    match_percent, matched_keywords, missing_keywords, is_short_description, job_word_count = keyword_match_score(
        resume.keywords, job.description
    )
    return {
        "match_percent": match_percent,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "is_short_description": is_short_description,
        "job_word_count": job_word_count,
    }


def tailor_resume_text(resume: ParsedResume, job: JobPosting) -> str:
    """Return a tailored plain-text resume: original content plus an
    inserted section calling out keywords from the job description that
    were missing from the original resume, framed for the candidate to
    genuinely confirm/add if truthfully applicable to their background.
    """
    suggestions = build_tailoring_suggestions(resume, job)
    missing = suggestions["missing_keywords"]

    tailored_section_lines = [
        "",
        "=" * 70,
        f"TAILORED FOR: {job.title} at {job.company}",
        "=" * 70,
        "",
        "ADDITIONAL RELEVANT KEYWORDS FOR THIS ROLE",
        "(Only include items below that genuinely reflect your experience.)",
    ]
    if missing:
        for kw in missing[:20]:
            tailored_section_lines.append(f"  - {kw}")
    else:
        tailored_section_lines.append("  (Your resume already covers the key terms found in this posting.)")

    tailored_section_lines.append("")
    tailored_section_lines.append(
        f"Keyword match before tailoring: {suggestions['match_percent']}% "
        f"of your resume's top keywords were found in this job description."
    )
    tailored_section_lines.append("=" * 70)

    return resume.raw_text.rstrip() + "\n" + "\n".join(tailored_section_lines)


def tailor_resume_docx_bytes(resume: ParsedResume, job: JobPosting) -> bytes:
    """Return a .docx file (as bytes) containing the original resume text
    paragraph-by-paragraph plus the tailored keyword section, so it can be
    offered as a download in the Streamlit UI.
    """
    try:
        import docx
        from docx.shared import Pt
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is required to export tailored resumes. Install with: pip install python-docx"
        ) from exc

    suggestions = build_tailoring_suggestions(resume, job)
    missing = suggestions["missing_keywords"]

    document = docx.Document()

    for line in resume.raw_text.splitlines():
        document.add_paragraph(line)

    document.add_paragraph("")
    heading = document.add_paragraph()
    run = heading.add_run(f"TAILORED FOR: {job.title} at {job.company}")
    run.bold = True
    run.font.size = Pt(13)

    document.add_paragraph(
        "Additional relevant keywords for this role "
        "(only include items that genuinely reflect your experience):"
    )
    if missing:
        for kw in missing[:20]:
            document.add_paragraph(kw, style=None)
    else:
        document.add_paragraph("Your resume already covers the key terms found in this posting.")

    document.add_paragraph(
        f"Keyword match before tailoring: {suggestions['match_percent']}% of your resume's "
        f"top keywords were found in this job description."
    )

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()

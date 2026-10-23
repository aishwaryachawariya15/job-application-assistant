"""Scoring logic: resume/job keyword matching, rough ATS score, H1B
sponsorship heuristic, and overall ranking of jobs across resumes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from resume_parser import ParsedResume
from job_search import JobPosting
from skills import (
    H1B_NEGATIVE_PHRASES,
    H1B_POSITIVE_PHRASES,
    find_skills_in_text,
    text_contains_keyword,
)

WORD_RE = re.compile(r"[A-Za-z][A-Za-z+#.\-]*")


def detect_h1b(description: str) -> str:
    """Return a best-effort sponsorship likelihood label.

    This is a heuristic based on phrase matching in the job description
    text; it is NOT a guarantee of actual sponsorship policy. Always
    verify directly with the employer before applying/relying on it.
    """
    text = description.lower()
    has_positive = any(phrase in text for phrase in H1B_POSITIVE_PHRASES)
    has_negative = any(phrase in text for phrase in H1B_NEGATIVE_PHRASES)

    if has_positive and not has_negative:
        return "Likely Sponsors"
    if has_negative and not has_positive:
        return "Likely No Sponsorship"
    if has_positive and has_negative:
        return "Mixed Signals"
    return "Not Mentioned"


def keyword_match_score(
    resume_keywords: list[str], job_text: str
) -> tuple[float, list[str], list[str], bool, int]:
    """Return (match_percent, matched_keywords, missing_keywords, is_short_description, job_word_count).

    missing_keywords are resume-relevant SKILLS_DB terms that appear in the
    job description but not in the resume keyword list - useful for the
    "tailor resume" feature.

    Many job boards/APIs (including Adzuna's free tier) only return a
    short snippet of the full posting rather than the complete text. A
    resume's top keywords are compared against whatever text is available,
    so a short snippet can only ever contain a handful of them - this would
    unfairly tank the match percentage if divided by the resume's full
    keyword count. Instead, the percentage is divided by however many
    distinct keyword "slots" the available text could plausibly hold
    (roughly one concept per ~10 words), capped by the resume's own
    keyword count, so short snippets are judged on a fair, smaller scale.
    """
    job_text_lower = job_text.lower()
    resume_kw_lower = {k.lower() for k in resume_keywords}

    matched = [kw for kw in resume_keywords if text_contains_keyword(job_text_lower, kw)]

    job_word_count = len(job_text.split())
    estimated_capacity = max(5, job_word_count // 10)
    effective_denominator = min(len(resume_keywords), estimated_capacity) if resume_keywords else 0
    match_percent = (len(matched) / effective_denominator * 100) if effective_denominator else 0.0
    match_percent = min(match_percent, 100.0)

    is_short_description = job_word_count < 120 or job_text.rstrip().endswith(("…", "..."))

    job_skill_terms = find_skills_in_text(job_text_lower)
    missing = sorted(job_skill_terms - resume_kw_lower)

    return round(match_percent, 1), matched, missing, is_short_description, job_word_count


def ats_score(resume: ParsedResume, job: JobPosting) -> tuple[int, dict]:
    """Produce a rough 0-100 ATS-style compatibility score with a
    breakdown explaining the contributing factors. This approximates how
    an Applicant Tracking System might rank a resume against a job
    description; it is a heuristic, not an official ATS algorithm.
    """
    match_percent, matched_keywords, missing_keywords, is_short_description, job_word_count = keyword_match_score(
        resume.keywords, job.description
    )

    breakdown = {}

    # Keyword overlap: up to 60 points.
    keyword_points = round(min(match_percent, 100) * 0.6)
    keyword_note = f"{keyword_points}/60 ({match_percent}% of resume keywords found in job description)"
    if is_short_description:
        keyword_note += (
            f" - note: this posting's description is short (~{job_word_count} words), likely a "
            "truncated snippet from the job board/API rather than the full ad, so this score was "
            "scaled to the available text. Check the full posting via the apply link for a true picture."
        )
    breakdown["Keyword match"] = keyword_note

    # Resume formatting / completeness: up to 25 points.
    format_points = 0
    format_notes = []
    if resume.has_contact_info:
        format_points += 8
        format_notes.append("contact info present (+8)")
    else:
        format_notes.append("missing clear contact info (email/phone) (+0)")

    key_sections = {"experience", "education", "skills"}
    found_key_sections = key_sections.intersection(set(resume.sections_found))
    section_pts = len(found_key_sections) * 4
    format_points += section_pts
    format_notes.append(f"{len(found_key_sections)}/3 core sections found (experience/education/skills) (+{section_pts})")

    if 250 <= resume.word_count <= 1200:
        format_points += 5
        format_notes.append("resume length in a healthy range (+5)")
    else:
        format_notes.append("resume length may be too short or too long for ATS parsing (+0)")

    breakdown["Formatting/completeness"] = f"{format_points}/25 (" + "; ".join(format_notes) + ")"

    # Skill depth: up to 15 points - rewards resumes with many recognized
    # hard skills relevant to the job's category/description.
    job_lower = job.description.lower()
    relevant_resume_skills = [s for s in resume.matched_skills if text_contains_keyword(job_lower, s)]
    skill_points = min(len(relevant_resume_skills) * 3, 15)
    breakdown["Relevant recognized skills"] = f"{skill_points}/15 ({len(relevant_resume_skills)} overlapping skills: {', '.join(relevant_resume_skills[:8]) or 'none'})"

    total = keyword_points + format_points + skill_points
    total = max(0, min(100, total))

    breakdown["_matched_keywords"] = matched_keywords
    breakdown["_missing_keywords"] = missing_keywords

    return total, breakdown


def category_matches(job: JobPosting, desired_category: str) -> bool:
    if not desired_category or desired_category == "Any":
        return True
    return desired_category.lower() in (job.category or "").lower()


def rank_jobs_for_resumes(
    jobs: list[JobPosting],
    resumes: list[ParsedResume],
    want_h1b: bool,
    top_n: int = 10,
) -> list[JobPosting]:
    """For each job, find the best-matching resume (highest ATS score),
    attach scoring metadata, then return the top N jobs sorted by an
    overall rank score that blends ATS fit, recency, and H1B preference.
    """
    deduped: dict[str, JobPosting] = {}
    for job in jobs:
        key = job.job_id or f"{job.title}|{job.company}|{job.location}"
        if key in deduped:
            continue
        deduped[key] = job

    scored_jobs = []
    for job in deduped.values():
        best_resume = None
        best_score = -1
        best_breakdown = {}
        for resume in resumes:
            score, breakdown = ats_score(resume, job)
            if score > best_score:
                best_score = score
                best_resume = resume
                best_breakdown = breakdown

        job.matched_resume = best_resume.name if best_resume else ""
        job.ats_score = best_score if best_score >= 0 else 0
        job.score_breakdown = best_breakdown
        job.h1b_label = detect_h1b(job.description)

        h1b_bonus = 0.0
        if want_h1b:
            if job.h1b_label == "Likely Sponsors":
                h1b_bonus = 15
            elif job.h1b_label == "Mixed Signals":
                h1b_bonus = 5
            elif job.h1b_label == "Likely No Sponsorship":
                h1b_bonus = -20

        job.rank_score = job.ats_score + h1b_bonus
        scored_jobs.append(job)

    scored_jobs.sort(key=lambda j: j.rank_score, reverse=True)
    return scored_jobs[:top_n]

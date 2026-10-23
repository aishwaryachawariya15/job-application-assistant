# Job Application Assistant

A local Streamlit GUI that helps you find and apply to jobs matching your resume(s).

## What it does

1. **Upload resume(s)** - PDF, DOCX, or TXT. You can upload multiple resumes (e.g. one for
   software roles, one for PM roles); the tool extracts keywords/skills from each.
2. **Answer a short questionnaire**:
   - Country / location (e.g. United States)
   - Whether you need H1B / visa sponsorship
   - Job category (Engineering, Sales, Marketing, Data/Analytics, etc.)
   - Job type (Full-time, Part-time, Contract, Permanent)
   - How recent the posting should be (past 24 hours / 3 / 5 / 7 / 14 / 30 days)
   - Optional manual job title/keyword override
3. **Searches jobs** via the [Adzuna API](https://developer.adzuna.com/) (free tier) if you
   provide an App ID/Key, or uses built-in **demo data** otherwise so you can try the full
   workflow without signing up for anything.
4. **Shows a ranked top-10 shortlist** with, for each job:
   - Which of your uploaded resumes best matches it
   - A rough **ATS compatibility score** (0-100): key terms are extracted from the job posting
     itself and checked against your full resume text (not just a trimmed keyword list) - the
     same direction a real ATS works - with a breakdown of why
   - An **H1B sponsorship likelihood** label (heuristic, based on phrases found in the job
     description - not a guarantee; always confirm with the employer)
   - A button to **tailor the recommended resume** to that job, showing a clear **before/after**
     comparison (match % and estimated ATS score before vs. after adding the suggested keywords),
     plus a downloadable tailored .txt/.docx with the added keywords clearly labeled

## Setup

```powershell
cd job_application_agent
pip install -r requirements.txt
```

Optional (recommended for real job listings): copy `.env.example` to `.env` and add your free
Adzuna `App ID`/`App Key` (https://developer.adzuna.com/). You can also paste the keys directly
into the sidebar inputs in the running app.

## Run

```powershell
streamlit run app.py
```

This opens the tool in your browser (usually http://localhost:8501).

## Notes & limitations

- **ATS score** is a rough heuristic (keyword overlap + resume formatting/completeness +
  recognized-skill overlap). Real ATS software (Workday, Taleo, Greenhouse, etc.) uses
  proprietary, often stricter parsing - treat this score as directional guidance, not gospel.
- **H1B sponsorship detection** scans job description text for phrases like "visa sponsorship",
  "H1B", "will sponsor" vs. "no sponsorship", "US citizens only", etc. Most job postings don't
  mention sponsorship at all, in which case the label is "Not Mentioned" - that does **not**
  mean sponsorship is unavailable, just that it isn't stated in the ad.
  Confirm directly with the employer.
- **Resume tailoring** is rule-based (keyword-gap suggestions appended as a clearly-labeled
  section, with an honest before/after score preview) - it does not fabricate experience. Only
  add suggested keywords that truthfully reflect your background. The "after" score assumes
  every suggested keyword is genuinely added; it's a best-case estimate, not a guarantee.
- Demo mode's sample jobs are static illustrative listings for testing the workflow end-to-end;
  switch to Adzuna credentials for real postings.

## Project layout

- `app.py` - Streamlit UI and workflow orchestration
- `resume_parser.py` - PDF/DOCX/TXT text extraction + keyword extraction
- `job_search.py` - Adzuna API client + demo data provider
- `scoring.py` - ATS scoring, H1B heuristic, job ranking
- `tailor.py` - Resume tailoring suggestions + before/after preview + tailored file export
- `skills.py` - Curated skills/keyword taxonomy and stopwords
- `analytics.py` - Developer-only visit counter + optional visitor name log
- `sample_data/demo_jobs.json` - Sample job postings used in demo mode

"""Curated keyword/skill taxonomy used for resume keyword extraction,
job-resume matching, and resume tailoring suggestions.

The list is intentionally broad (tech, engineering, sales, marketing,
finance, healthcare, soft skills) since the tool targets many job
categories, not just software roles.
"""
import re

SKILLS_DB = {
    # Programming / software
    "python", "java", "c++", "c#", "javascript", "typescript", "sql", "nosql",
    "r", "matlab", "go", "golang", "rust", "scala", "php", "swift", "kotlin",
    "html", "css", "react", "angular", "vue", "node.js", "django", "flask",
    "spring boot", ".net", "rest api", "graphql", "git", "ci/cd", "jenkins",
    "docker", "kubernetes", "terraform", "ansible", "linux", "bash",
    "aws", "azure", "gcp", "cloud computing", "microservices", "devops",
    "machine learning", "deep learning", "data science", "data analysis",
    "data engineering", "etl", "big data", "spark", "hadoop", "airflow",
    "tensorflow", "pytorch", "scikit-learn", "nlp", "computer vision",
    "tableau", "power bi", "excel", "powerpoint", "word", "sharepoint",
    "agile", "scrum", "kanban", "jira", "confluence", "test automation",
    "selenium", "qa", "unit testing", "api testing", "cybersecurity",
    "network security", "penetration testing", "siem", "firewall",
    "database administration", "oracle", "postgresql", "mysql", "mongodb",
    "snowflake", "redshift", "data warehousing", "business intelligence",

    # Engineering (non-software)
    "autocad", "solidworks", "catia", "revit", "plc", "scada",
    "six sigma", "lean manufacturing", "root cause analysis", "fmea",
    "project management", "pmp", "quality assurance", "quality control",
    "manufacturing", "cad", "cam", "cnc", "robotics", "electrical design",
    "mechanical design", "circuit design", "pcb design", "embedded systems",
    "firmware", "hardware testing", "validation", "verification",
    "semiconductor", "process engineering", "supply chain", "logistics",
    "procurement", "inventory management", "iso 9001", "safety compliance",
    "hvac", "civil engineering", "structural analysis", "gis",

    # Sales / marketing / business
    "sales", "business development", "account management", "crm",
    "salesforce", "hubspot", "lead generation", "cold calling",
    "negotiation", "client relations", "customer success", "b2b sales",
    "b2c sales", "seo", "sem", "google analytics", "google ads",
    "social media marketing", "content marketing", "content strategy",
    "email marketing", "marketing automation", "brand management",
    "market research", "competitive analysis", "digital marketing",
    "copywriting", "public relations", "campaign management",
    "product marketing", "go-to-market", "pricing strategy",
    "forecasting", "quota attainment", "pipeline management",
    "territory management", "channel partnerships", "e-commerce",

    # Finance / accounting / operations
    "financial analysis", "financial modeling", "budgeting", "forecasting",
    "accounts payable", "accounts receivable", "bookkeeping", "gaap",
    "sap", "quickbooks", "auditing", "tax preparation", "payroll",
    "risk management", "compliance", "underwriting", "investment analysis",
    "portfolio management", "operations management", "vendor management",

    # Healthcare / other
    "patient care", "clinical research", "emr", "ehr", "nursing",
    "medical coding", "hipaa compliance", "pharmacology", "phlebotomy",

    # Soft skills
    "leadership", "communication", "teamwork", "problem solving",
    "critical thinking", "time management", "collaboration",
    "adaptability", "presentation skills", "stakeholder management",
    "mentoring", "conflict resolution", "decision making",
    "strategic planning", "cross-functional", "multitasking",
    "customer service", "interpersonal skills", "analytical skills",

    # Visa / sponsorship related (used for H1B heuristic as well)
    "h1b", "h-1b", "visa sponsorship", "work authorization",
    "opt", "cpt", "green card",
}

# Generic English stopwords (kept local to avoid extra NLP downloads)
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can",
    "could", "did", "do", "does", "doing", "down", "during", "each", "few",
    "for", "from", "further", "had", "has", "have", "having", "he", "her",
    "here", "hers", "herself", "him", "himself", "his", "how", "i", "if",
    "in", "into", "is", "it", "its", "itself", "just", "me", "more", "most",
    "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own",
    "s", "same", "she", "should", "so", "some", "such", "t", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while",
    "who", "whom", "why", "will", "with", "you", "your", "yours",
    "yourself", "yourselves", "job", "work", "role", "company", "team",
    "years", "year", "experience", "ability", "including", "etc", "using",
    "strong", "must", "plus", "within", "across", "new", "also", "per",
}

# Phrases that suggest a job posting may offer visa / H1B sponsorship.
H1B_POSITIVE_PHRASES = [
    "visa sponsorship", "h1b sponsorship", "h-1b sponsorship", "sponsor h1b",
    "sponsor h-1b", "will sponsor", "able to sponsor", "sponsorship available",
    "sponsor employment visa", "sponsor work visa", "h1b transfer",
    "green card sponsorship", "immigration sponsorship",
]

# Phrases that suggest a job posting explicitly does NOT sponsor.
H1B_NEGATIVE_PHRASES = [
    "no sponsorship", "not sponsor", "unable to sponsor", "without sponsorship",
    "must be authorized to work", "no visa sponsorship",
    "cannot provide sponsorship", "does not offer sponsorship",
    "us citizens only", "u.s. citizens only", "must be a us citizen",
]

_TOKEN_PATTERN_CACHE: dict[str, "re.Pattern"] = {}


def _token_pattern(token: str) -> "re.Pattern":
    """Word-boundary-safe pattern for any keyword/phrase, so short tokens
    like 'r' or 'go' don't match as substrings inside unrelated words
    (e.g. 'r' inside 'experience'). Uses lookaround on alphanumeric
    characters since some skill names contain symbols (c++, c#, .net)
    that \\b handles poorly.
    """
    pattern = _TOKEN_PATTERN_CACHE.get(token)
    if pattern is None:
        pattern = re.compile(
            r"(?<![a-zA-Z0-9])" + re.escape(token) + r"(?![a-zA-Z0-9])"
        )
        _TOKEN_PATTERN_CACHE[token] = pattern
    return pattern


def text_contains_keyword(text_lower: str, keyword: str) -> bool:
    """True if keyword appears in text_lower as a whole token/phrase."""
    return _token_pattern(keyword.lower()).search(text_lower) is not None


def find_skills_in_text(text_lower: str) -> set[str]:
    """Return the subset of SKILLS_DB that appear in text_lower as whole
    tokens/phrases (not as substrings of unrelated words)."""
    return {skill for skill in SKILLS_DB if _token_pattern(skill).search(text_lower)}


def count_skill_occurrences(text_lower: str, skill: str) -> int:
    return len(_token_pattern(skill).findall(text_lower))


JOB_CATEGORY_KEYWORDS = {
    "Engineering": [
        "engineer", "engineering", "hardware", "mechanical", "electrical",
        "circuit", "pcb", "embedded", "semiconductor", "validation",
        "firmware", "systems engineer", "process engineer",
    ],
    "IT / Software": ["software", "developer", "it ", "information technology", "programmer", "devops"],
    "Sales": ["sales", "account executive", "business development"],
    "Marketing": ["marketing", "seo", "brand", "content", "social media"],
    "Finance / Accounting": ["finance", "accounting", "accountant", "financial analyst", "audit"],
    "Operations / Supply Chain": ["operations", "supply chain", "logistics", "procurement"],
    "Customer Service / Support": ["customer service", "support", "customer success"],
    "Human Resources": ["human resources", "hr ", "recruiter", "recruiting", "talent"],
    "Healthcare": ["nurse", "clinical", "medical", "healthcare", "patient"],
    "Data / Analytics": ["data scientist", "data analyst", "data engineer", "analytics", "machine learning"],
    "Project / Product Management": ["project manager", "product manager", "program manager", "scrum"],
    "Manufacturing": ["manufacturing", "production", "assembly", "quality control", "six sigma"],
}

# Adzuna's API only accepts its own fixed category "tag" values (verified via
# the /categories endpoint) - NOT arbitrary keywords. Passing anything else
# as the `category` query param returns an HTTP 400. Categories without a
# solid match are left unmapped (None) so no category filter is sent to the
# API for them; local keyword filtering (JOB_CATEGORY_KEYWORDS, above) still
# narrows results client-side in that case.
ADZUNA_CATEGORY_TAGS = {
    "Engineering": "engineering-jobs",
    "IT / Software": "it-jobs",
    "Sales": "sales-jobs",
    "Marketing": "pr-advertising-marketing-jobs",
    "Finance / Accounting": "accounting-finance-jobs",
    "Operations / Supply Chain": "logistics-warehouse-jobs",
    "Customer Service / Support": "customer-services-jobs",
    "Human Resources": "hr-jobs",
    "Healthcare": "healthcare-nursing-jobs",
    "Data / Analytics": None,
    "Project / Product Management": None,
    "Manufacturing": "manufacturing-jobs",
}

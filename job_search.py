"""Job search providers.

AdzunaClient hits the real Adzuna Jobs API (https://developer.adzuna.com/)
when an App ID / App Key are configured. If no credentials are present,
the DemoProvider returns realistic sample listings so the rest of the
tool (matching, scoring, tailoring) can be exercised end-to-end without
any signup.
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

ADZUNA_COUNTRIES = {
    "United States": "us",
    "United Kingdom": "gb",
    "Canada": "ca",
    "Australia": "au",
    "Germany": "de",
    "France": "fr",
    "India": "in",
    "Italy": "it",
    "Netherlands": "nl",
    "New Zealand": "nz",
    "Poland": "pl",
    "Singapore": "sg",
    "South Africa": "za",
    "Spain": "es",
    "Mexico": "mx",
    "Brazil": "br",
    "Austria": "at",
    "Switzerland": "ch",
}

DATE_RANGE_OPTIONS = {
    "Past 24 hours": 1,
    "Past 3 days": 3,
    "Past 5 days": 5,
    "Past 7 days": 7,
    "Past 14 days": 14,
    "Past 30 days (1 month)": 30,
}


@dataclass
class JobPosting:
    job_id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    created: str
    category: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    source: str = "adzuna"
    matched_resume: str = field(default="")
    ats_score: int = 0
    h1b_label: str = "Unknown"
    rank_score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)


class AdzunaClient:
    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self, app_id: str, app_key: str):
        self.app_id = app_id
        self.app_key = app_key

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_key)

    def get_categories(self, country_code: str) -> list[str]:
        url = f"{self.BASE_URL}/{country_code}/categories"
        try:
            resp = requests.get(
                url, params={"app_id": self.app_id, "app_key": self.app_key}, timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            return [c["label"] for c in data.get("results", [])]
        except Exception:
            return []

    def search(
        self,
        country_code: str,
        what: str,
        where: str = "",
        max_days_old: int = 30,
        results_per_page: int = 20,
        category_tag: str = "",
        page: int = 1,
    ) -> list[JobPosting]:
        url = f"{self.BASE_URL}/{country_code}/search/{page}"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": results_per_page,
            "what": what,
            "max_days_old": max_days_old,
            "content-type": "application/json",
        }
        if where:
            params["where"] = where
        if category_tag:
            params["category"] = category_tag

        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for item in data.get("results", []):
            jobs.append(
                JobPosting(
                    job_id=str(item.get("id", "")),
                    title=item.get("title", "").strip(),
                    company=(item.get("company") or {}).get("display_name", "Unknown"),
                    location=(item.get("location") or {}).get("display_name", where or country_code.upper()),
                    description=item.get("description", ""),
                    url=item.get("redirect_url", ""),
                    created=item.get("created", ""),
                    category=(item.get("category") or {}).get("label", ""),
                    salary_min=item.get("salary_min"),
                    salary_max=item.get("salary_max"),
                    source="adzuna",
                )
            )
        return jobs


class DemoProvider:
    """Generates deterministic-ish sample job postings for testing without
    API credentials. Pulls from sample_data/demo_jobs.json and filters by
    the same criteria a real search would use, so the UI behaves the same.
    """

    def __init__(self):
        data_path = Path(__file__).parent / "sample_data" / "demo_jobs.json"
        with open(data_path, "r", encoding="utf-8") as f:
            raw_jobs = json.load(f)
        # Demo postings store "days_ago" so the sample data always looks
        # fresh relative to whenever the tool is run.
        now = datetime.utcnow()
        self._jobs = []
        for item in raw_jobs:
            item = dict(item)
            item["created"] = (now - timedelta(days=item.pop("days_ago", 0))).isoformat()
            self._jobs.append(item)

    def is_configured(self) -> bool:
        return True

    def get_categories(self, country_code: str) -> list[str]:
        return sorted({j["category"] for j in self._jobs})

    def search(
        self,
        country_code: str,
        what: str,
        where: str = "",
        max_days_old: int = 30,
        results_per_page: int = 20,
        category_tag: str = "",
        page: int = 1,
    ) -> list[JobPosting]:
        what_terms = [t.lower() for t in what.split() if t.strip()]
        cutoff = datetime.utcnow() - timedelta(days=max_days_old)

        results = []
        for item in self._jobs:
            haystack = f"{item['title']} {item['description']} {item['category']}".lower()
            if what_terms and not any(term in haystack for term in what_terms):
                continue
            if where and where.lower() not in item["location"].lower() and where.lower() not in "united states usa us":
                # keep loose matching for demo purposes
                pass
            created_dt = datetime.fromisoformat(item["created"])
            if created_dt < cutoff:
                continue

            results.append(
                JobPosting(
                    job_id=item["job_id"],
                    title=item["title"],
                    company=item["company"],
                    location=item["location"],
                    description=item["description"],
                    url=item["url"],
                    created=item["created"],
                    category=item["category"],
                    salary_min=item.get("salary_min"),
                    salary_max=item.get("salary_max"),
                    source="demo",
                )
            )

        random.shuffle(results)
        return results[:results_per_page]


def get_provider(app_id: str = "", app_key: str = ""):
    """Return an Adzuna client if credentials are present, else DemoProvider."""
    app_id = app_id or os.environ.get("ADZUNA_APP_ID", "")
    app_key = app_key or os.environ.get("ADZUNA_APP_KEY", "")
    client = AdzunaClient(app_id, app_key)
    if client.is_configured():
        return client
    return DemoProvider()

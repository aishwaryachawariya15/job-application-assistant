"""Lightweight, zero-setup visit counter using the free Abacus counter API
(https://abacus.jasoncameron.dev). No signup/API key required. Falls back
silently (counts as unavailable) if the service can't be reached, so a
network hiccup never breaks the app for visitors.
"""
from __future__ import annotations

import requests

NAMESPACE = "oreo-job-agent"
KEY = "page-views"
_BASE_URL = "https://abacus.jasoncameron.dev"
_TIMEOUT = 4


def record_visit() -> int | None:
    """Increment the visit counter by 1 and return the new total, or None
    if the counter service couldn't be reached."""
    try:
        resp = requests.get(f"{_BASE_URL}/hit/{NAMESPACE}/{KEY}", timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("value")
    except Exception:
        return None


def get_visit_count() -> int | None:
    """Read the current visit count without incrementing it, or None if
    the counter service couldn't be reached."""
    try:
        resp = requests.get(f"{_BASE_URL}/get/{NAMESPACE}/{KEY}", timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("value")
    except Exception:
        return None

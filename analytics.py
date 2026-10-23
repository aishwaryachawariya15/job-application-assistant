"""Lightweight, zero-setup visit counter using the free Abacus counter API
(https://abacus.jasoncameron.dev), plus an optional named-visitor log using
a free kvdb.io key-value bucket. No signup/API key required for visitors;
both fail silently (never break the app) if the services are unreachable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import requests

NAMESPACE = "oreo-job-agent"
KEY = "page-views"
_BASE_URL = "https://abacus.jasoncameron.dev"
_TIMEOUT = 4

# Dedicated kvdb.io bucket used only to store the optional "your name" log.
# Reads are open; writes require the bucket owner's email to be verified
# once (a one-time setup step, not something visitors ever see or do).
_KVDB_BUCKET = "3oR6yyPFnwhpgvLyXqrRGU"
_KVDB_BASE = f"https://kvdb.io/{_KVDB_BUCKET}"
_NAMES_KEY = "visitor_names"


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


def log_visitor_name(name: str) -> bool:
    """Append a visitor-supplied name (with a timestamp) to the shared log.
    Only called when a visitor voluntarily fills in the optional name field.
    Returns True on success, False if the log couldn't be updated (e.g. the
    kvdb.io bucket's owner email isn't verified yet) - never raises, so a
    failure here never breaks the app for the visitor.
    """
    name = (name or "").strip()
    if not name:
        return False
    try:
        entries = get_visitor_names()
        entries.append({"name": name, "time_utc": datetime.now(timezone.utc).isoformat()})
        resp = requests.put(
            f"{_KVDB_BASE}/{_NAMES_KEY}", data=json.dumps(entries), timeout=_TIMEOUT
        )
        return resp.status_code in (200, 201, 204)
    except Exception:
        return False


def get_visitor_names() -> list[dict]:
    """Return the list of {name, time_utc} entries logged so far, or an
    empty list if none exist yet / the service is unreachable."""
    try:
        resp = requests.get(f"{_KVDB_BASE}/{_NAMES_KEY}", timeout=_TIMEOUT)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return json.loads(resp.text) if resp.text.strip() else []
    except Exception:
        return []


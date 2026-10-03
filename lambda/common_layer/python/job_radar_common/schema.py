"""Common job schema and dedup hashing shared by every source adapter."""
import hashlib
import re
from datetime import datetime, timezone

DESCRIPTION_MAX_CHARS = 2000

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_html(text):
    """Best-effort HTML-to-text for sources (Remotive, RemoteOK, Arbeitnow, Gupy)
    that return description as HTML markup."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def make_job_id(source, external_id):
    digest = hashlib.sha256(f"{source}:{external_id}".encode("utf-8")).hexdigest()
    return digest


def make_job(*, source, external_id, title, company, url, location_raw="",
             country="", is_remote=False, city="", description="", posted_at=""):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "job_id": make_job_id(source, external_id),
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "location_raw": (location_raw or "").strip(),
        "country": (country or "").strip().upper(),
        "is_remote": bool(is_remote),
        "city": (city or "").strip(),
        "url": url,
        "description": strip_html(description)[:DESCRIPTION_MAX_CHARS],
        "source": source,
        "posted_at": posted_at or now,
        "fetched_at": now,
    }

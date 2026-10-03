"""Per-source job fetchers. Every function returns a list of jobs normalized
via schema.make_job() and never raises on a single bad item -- callers
(the harvester) are still expected to wrap each fetch_* call in try/except,
since a whole source can go down or change shape without notice (this is
especially true for Gupy, which has no official/documented API)."""
import json
import urllib.error
import urllib.parse
import urllib.request

from . import schema

USER_AGENT = "job-radar-harvester/1.0 (+https://github.com/AndersonGabrielBD/job-radar)"
HTTP_TIMEOUT = 15

REMOTE_TEXT_HINTS = ("remote", "remoto", "home office", "home-office", "anywhere", "worldwide")

# Portuguese search terms used against Gupy/Jooble, which index mostly
# Brazilian/Portuguese-language postings.
PT_SEARCH_TERMS = ("desenvolvedor", "engenheiro de software", "backend")


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url, body, headers=None):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _looks_remote(*texts):
    haystack = " ".join(t or "" for t in texts).lower()
    return any(hint in haystack for hint in REMOTE_TEXT_HINTS)


def fetch_remotive():
    url = "https://remotive.com/api/remote-jobs?category=software-dev"
    data = _get_json(url)
    jobs = []
    for raw in data.get("jobs", []):
        jobs.append(schema.make_job(
            source="remotive",
            external_id=raw.get("id"),
            title=raw.get("title"),
            company=raw.get("company_name"),
            url=raw.get("url"),
            location_raw=raw.get("candidate_required_location"),
            is_remote=True,
            description=raw.get("description"),
            posted_at=raw.get("publication_date"),
        ))
    return jobs


def fetch_remoteok():
    data = _get_json("https://remoteok.com/api")
    jobs = []
    for raw in data:
        if not raw.get("id") or "position" not in raw:
            continue  # first item is a legal-notice record, not a job
        jobs.append(schema.make_job(
            source="remoteok",
            external_id=raw.get("id"),
            title=raw.get("position"),
            company=raw.get("company"),
            url=raw.get("url") or raw.get("apply_url"),
            location_raw=raw.get("location"),
            is_remote=True,
            description=raw.get("description"),
            posted_at=raw.get("date"),
        ))
    return jobs


def fetch_arbeitnow():
    data = _get_json("https://www.arbeitnow.com/api/job-board-api")
    jobs = []
    for raw in data.get("data", []):
        jobs.append(schema.make_job(
            source="arbeitnow",
            external_id=raw.get("slug"),
            title=raw.get("title"),
            company=raw.get("company_name"),
            url=raw.get("url"),
            location_raw=raw.get("location"),
            is_remote=bool(raw.get("remote")),
            description=raw.get("description"),
        ))
    return jobs


def fetch_adzuna(app_id, app_key, what="python"):
    """Two queries: one broad search across Brazil (remote detected via text
    heuristics) and one scoped to Maceio (structured location filter)."""
    jobs = []
    base = "https://api.adzuna.com/v1/api/jobs/br/search/1"
    common = {
        "app_id": app_id,
        "app_key": app_key,
        "what": what,
        "results_per_page": "50",
        "content-type": "application/json",
    }

    broad_params = dict(common, where="Brasil")
    broad = _get_json(f"{base}?{urllib.parse.urlencode(broad_params)}")
    for raw in broad.get("results", []):
        title = raw.get("title", "")
        description = raw.get("description", "")
        location = raw.get("location") or {}
        area = location.get("area") or []
        city = area[-1] if area else ""
        jobs.append(schema.make_job(
            source="adzuna",
            external_id=raw.get("id"),
            title=title,
            company=(raw.get("company") or {}).get("display_name"),
            url=raw.get("redirect_url"),
            location_raw=location.get("display_name"),
            country="BR",
            city=city,
            is_remote=_looks_remote(title, description, location.get("display_name")),
            description=description,
            posted_at=raw.get("created"),
        ))

    maceio_params = dict(common, where="Maceió")
    maceio = _get_json(f"{base}?{urllib.parse.urlencode(maceio_params)}")
    for raw in maceio.get("results", []):
        title = raw.get("title", "")
        description = raw.get("description", "")
        location = raw.get("location") or {}
        jobs.append(schema.make_job(
            source="adzuna",
            external_id=raw.get("id"),
            title=title,
            company=(raw.get("company") or {}).get("display_name"),
            url=raw.get("redirect_url"),
            location_raw=location.get("display_name"),
            country="BR",
            city="Maceió",
            is_remote=_looks_remote(title, description, location.get("display_name")),
            description=description,
            posted_at=raw.get("created"),
        ))
    return jobs


def _fetch_gupy_query(params):
    url = f"https://portal.gupy.io/api/job-search/jobs?{urllib.parse.urlencode(params)}"
    data = _get_json(url)
    jobs = []
    for raw in data.get("data", []):
        jobs.append(schema.make_job(
            source="gupy",
            external_id=raw.get("id"),
            title=raw.get("name"),
            company=raw.get("careerPageName"),
            url=raw.get("jobUrl"),
            location_raw=f"{raw.get('city', '')} {raw.get('state', '')}".strip(),
            country="BR",
            city=raw.get("city"),
            is_remote=(raw.get("workplaceType") == "remote"),
            description=raw.get("description"),
            posted_at=raw.get("publishedDate"),
        ))
    return jobs


def fetch_gupy():
    """Gupy's public portal endpoint is undocumented/unofficial and may
    change shape without notice -- callers should isolate this source."""
    jobs = []
    seen_ids = set()
    queries = (
        [{"jobName": term, "workplaceType": "remote", "limit": "30"} for term in PT_SEARCH_TERMS]
        + [{"jobName": term, "city": "Maceió", "limit": "30"} for term in PT_SEARCH_TERMS]
    )
    for params in queries:
        for job in _fetch_gupy_query(params):
            if job["job_id"] in seen_ids:
                continue
            seen_ids.add(job["job_id"])
            jobs.append(job)
    return jobs


def fetch_jooble(api_key):
    url = f"https://jooble.org/api/{api_key}"
    jobs = []
    seen_ids = set()
    for term in PT_SEARCH_TERMS + ("python", "backend"):
        try:
            data = _post_json(url, {"keywords": term, "location": "Brasil"})
        except urllib.error.HTTPError:
            continue
        for raw in data.get("jobs", []):
            external_id = raw.get("id") or raw.get("link")
            if external_id in seen_ids:
                continue
            seen_ids.add(external_id)
            title = raw.get("title", "")
            snippet = raw.get("snippet", "")
            location = raw.get("location", "")
            jobs.append(schema.make_job(
                source="jooble",
                external_id=external_id,
                title=title,
                company=raw.get("company"),
                url=raw.get("link"),
                location_raw=location,
                country="BR",
                is_remote=_looks_remote(title, snippet, location),
                description=snippet,
                posted_at=raw.get("updated"),
            ))
    return jobs


# Sources that need no credentials.
OPEN_SOURCES = (fetch_remotive, fetch_remoteok, fetch_arbeitnow)

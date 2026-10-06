import json
import os

import boto3
from job_radar_common import dynamo, location, matching, seniority, sources, stack_gate

TABLE_NAME = os.environ["TABLE_NAME"]
TTL_DAYS = int(os.environ.get("TTL_DAYS", "50"))
STACK_KEYWORDS_PARAM = os.environ["STACK_KEYWORDS_PARAM"]
ADZUNA_APP_ID_PARAM = os.environ["ADZUNA_APP_ID_PARAM"]
ADZUNA_APP_KEY_PARAM = os.environ["ADZUNA_APP_KEY_PARAM"]
JOOBLE_API_KEY_PARAM = os.environ["JOOBLE_API_KEY_PARAM"]

_ssm = boto3.client("ssm")

# Module-level cache: SSM params are config, not per-invocation state, and
# Lambda warm starts can reuse them across runs.
_config_cache = {}


def _get_param(name, decrypt=False):
    if name not in _config_cache:
        resp = _ssm.get_parameter(Name=name, WithDecryption=decrypt)
        _config_cache[name] = resp["Parameter"]["Value"]
    return _config_cache[name]


def _load_config():
    return {
        "keywords": json.loads(_get_param(STACK_KEYWORDS_PARAM)),
        "adzuna_app_id": _get_param(ADZUNA_APP_ID_PARAM, decrypt=True),
        "adzuna_app_key": _get_param(ADZUNA_APP_KEY_PARAM, decrypt=True),
        "jooble_api_key": _get_param(JOOBLE_API_KEY_PARAM, decrypt=True),
    }


def _fetch_all(config):
    """Fetch every source independently -- one source failing (rate limit,
    schema drift, outage) must never take the whole run down."""
    all_jobs = []
    counts = {}
    for fetch_fn in sources.OPEN_SOURCES:
        name = fetch_fn.__name__
        try:
            jobs = fetch_fn()
            counts[name] = len(jobs)
            all_jobs.extend(jobs)
        except Exception as exc:  # noqa: BLE001 - isolate source failures
            print(f"[harvester] {name} failed: {exc}")
            counts[name] = f"error: {exc}"

    try:
        jobs = sources.fetch_adzuna(config["adzuna_app_id"], config["adzuna_app_key"])
        counts["fetch_adzuna"] = len(jobs)
        all_jobs.extend(jobs)
    except Exception as exc:  # noqa: BLE001
        print(f"[harvester] fetch_adzuna failed: {exc}")
        counts["fetch_adzuna"] = f"error: {exc}"

    try:
        jobs = sources.fetch_gupy()
        counts["fetch_gupy"] = len(jobs)
        all_jobs.extend(jobs)
    except Exception as exc:  # noqa: BLE001
        print(f"[harvester] fetch_gupy failed: {exc}")
        counts["fetch_gupy"] = f"error: {exc}"

    try:
        jobs = sources.fetch_jooble(config["jooble_api_key"])
        counts["fetch_jooble"] = len(jobs)
        all_jobs.extend(jobs)
    except Exception as exc:  # noqa: BLE001
        print(f"[harvester] fetch_jooble failed: {exc}")
        counts["fetch_jooble"] = f"error: {exc}"

    return all_jobs, counts


def handler(event, context):
    run = (event or {}).get("run", "run")
    config = _load_config()

    raw_jobs, fetch_counts = _fetch_all(config)
    print(f"[harvester] ({run}) fetched: {fetch_counts}")

    in_scope = [
        job for job in raw_jobs
        if location.is_in_scope(job)
        and not seniority.is_senior(job.get("title"))
        and not stack_gate.is_other_stack(job.get("title"), job.get("description"))
        and not stack_gate.is_qa_role(job.get("title"))
    ]
    print(f"[harvester] ({run}) {len(in_scope)}/{len(raw_jobs)} jobs passed the location/seniority/stack gate")

    existing_ids = dynamo.filter_existing_ids(TABLE_NAME, (job["job_id"] for job in in_scope))
    new_jobs = [job for job in in_scope if job["job_id"] not in existing_ids]
    print(f"[harvester] ({run}) {len(new_jobs)} new jobs (already seen: {len(existing_ids)})")

    # No high score cutoff here on purpose: stack_gate above already drops
    # the unambiguous noise (.NET/C#/Java/PHP/QA), and anything generic
    # enough to be ambiguous (plain "Desenvolvedor"/"Analista"/"Engenheiro
    # de Software" postings) is cheap to skim and dismiss from the
    # dashboard -- cheaper than risking a real match getting silently
    # dropped here. But score==0 means literally zero keyword overlap --
    # remote/BR postings with no tech signal at all (e.g. "Açougueiro"
    # slipping through arbeitnow's unfiltered feed) -- so that floor still
    # applies. match_score is otherwise kept purely to sort the dashboard
    # by relevance.
    scored_jobs = []
    for job in new_jobs:
        score, matched_keywords = matching.score_job(job, config["keywords"])
        if score == 0:
            continue
        job["match_score"] = score
        job["matched_keywords"] = matched_keywords
        scored_jobs.append(job)

    dynamo.write_jobs(TABLE_NAME, scored_jobs, ttl_seconds=TTL_DAYS * 86400)
    print(f"[harvester] ({run}) wrote {len(scored_jobs)} jobs ({len(new_jobs) - len(scored_jobs)} had zero keyword overlap)")

    return {
        "run": run,
        "fetched": fetch_counts,
        "in_scope": len(in_scope),
        "new": len(new_jobs),
        "written": len(scored_jobs),
    }

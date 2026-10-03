import base64
import hmac
import html
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

import boto3
from job_radar_common import dynamo

TABLE_NAME = os.environ["TABLE_NAME"]
GSI_NAME = os.environ["GSI_NAME"]
DASHBOARD_TOKEN_PARAM = os.environ["DASHBOARD_TOKEN_PARAM"]
DEFAULT_DAYS = int(os.environ.get("DEFAULT_DAYS", "7"))

_ssm = boto3.client("ssm")
_token_cache = {}


def _expected_token():
    if "token" not in _token_cache:
        resp = _ssm.get_parameter(Name=DASHBOARD_TOKEN_PARAM, WithDecryption=True)
        _token_cache["token"] = resp["Parameter"]["Value"]
    return _token_cache["token"]


def _html_response(status, body, extra_headers=None):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "text/html; charset=utf-8", **(extra_headers or {})},
        "body": body,
    }


# Score-tier gradient, loosely modeled on Steam's dark UI (blue accent for
# "good", green for "great", gold/orange fading down to muted gray).
def _score_tier(score):
    if score >= 75:
        return "tier-great"
    if score >= 50:
        return "tier-good"
    if score >= 25:
        return "tier-ok"
    return "tier-low"


# One accent color per source, so the board reads at a glance.
_SOURCE_COLORS = {
    "remotive": "#66c0f4",
    "remoteok": "#b388ff",
    "arbeitnow": "#ff9e4a",
    "adzuna": "#ff6b6b",
    "gupy": "#ff6bb3",
    "jooble": "#4adede",
}


def _source_color(source):
    return _SOURCE_COLORS.get(source, "#8ea4c0")


def _card_html(job, token):
    score = job.get("match_score", 0)
    tier = _score_tier(score)
    title = html.escape(job.get("title", ""))
    company = html.escape(job.get("company", ""))
    url = html.escape(job.get("url", ""), quote=True)
    keywords = job.get("matched_keywords", [])
    keyword_pills = "".join(f"<span class='pill'>{html.escape(k)}</span>" for k in keywords)
    source = job.get("source", "")
    source_color = _source_color(source)
    posted = html.escape((job.get("posted_at") or "")[:10])
    status = job.get("status", "new")

    if status == "applied":
        action_html = f"<span class='applied'>&#10003; Applied {html.escape((job.get('applied_at') or '')[:10])}</span>"
    else:
        job_id = html.escape(job.get("job_id", ""), quote=True)
        token_q = html.escape(token, quote=True)
        action_html = (
            f"<form method='POST' action='/'>"
            f"<input type='hidden' name='job_id' value='{job_id}'>"
            f"<input type='hidden' name='token' value='{token_q}'>"
            f"<button type='submit' class='mark-btn'>Mark Applied</button>"
            f"</form>"
        )

    return f"""
    <div class="card {tier}">
      <div class="score-badge {tier}">{score}</div>
      <div class="card-body">
        <div class="card-top">
          <div>
            <div class="title">{title}</div>
            <div class="company">{company}</div>
          </div>
          <span class="source-pill" style="background:{source_color}22;color:{source_color};border-color:{source_color}55">{html.escape(source)}</span>
        </div>
        <div class="keywords">{keyword_pills}</div>
        <div class="card-bottom">
          <span class="posted">{posted}</span>
          <a class="apply-btn" href="{url}" target="_blank" rel="noopener">Apply &#8599;</a>
          {action_html}
        </div>
      </div>
    </div>
    """


def _render_page(jobs, token, days):
    cards = "".join(_card_html(job, token) for job in jobs)
    token_q = html.escape(token, quote=True)

    def _day_tab(d, label):
        active = "active" if d == days else ""
        return f"<a class='tab {active}' href='/?token={token_q}&days={d}'>{label}</a>"

    tabs = _day_tab(3, "3 dias") + _day_tab(7, "7 dias") + _day_tab(30, "30 dias")

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Radar</title>
<style>
  :root {{
    --bg-top: #1b2838;
    --bg-bottom: #0f1620;
    --card-bg: #223449;
    --card-bg-hover: #2a3f5a;
    --text: #c7d5e0;
    --text-dim: #8ea4c0;
    --blue: #66c0f4;
    --green: #a4d007;
    --gold: #e0ac00;
    --gray: #5c7389;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', -apple-system, sans-serif;
    background: linear-gradient(180deg, var(--bg-top) 0%, var(--bg-bottom) 100%);
    color: var(--text);
    margin: 0;
    padding: 28px;
    min-height: 100vh;
  }}
  h1 {{
    font-size: 24px;
    margin: 0 0 4px;
    background: linear-gradient(90deg, var(--blue), var(--green));
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    font-weight: 800;
  }}
  .subtitle {{ color: var(--text-dim); font-size: 13px; margin-bottom: 18px; }}
  .tabs {{ display: flex; gap: 8px; margin-bottom: 22px; }}
  .tab {{
    text-decoration: none; color: var(--text-dim); font-size: 13px;
    padding: 6px 14px; border-radius: 999px; border: 1px solid #33516d;
    transition: all .15s;
  }}
  .tab:hover {{ color: var(--text); border-color: var(--blue); }}
  .tab.active {{ background: var(--blue); color: #0f1620; font-weight: 700; border-color: var(--blue); }}
  .grid {{ display: flex; flex-direction: column; gap: 10px; }}
  .card {{
    display: flex; gap: 16px; align-items: stretch;
    background: var(--card-bg);
    border-left: 4px solid var(--gray);
    border-radius: 8px;
    padding: 14px 18px;
    box-shadow: 0 2px 6px rgba(0,0,0,.25);
    transition: transform .12s, background .12s;
  }}
  .card:hover {{ background: var(--card-bg-hover); transform: translateY(-1px); }}
  .card.tier-great {{ border-left-color: var(--green); }}
  .card.tier-good {{ border-left-color: var(--blue); }}
  .card.tier-ok {{ border-left-color: var(--gold); }}
  .score-badge {{
    flex: 0 0 52px; display: flex; align-items: center; justify-content: center;
    font-size: 20px; font-weight: 800; border-radius: 8px; color: #0f1620;
  }}
  .score-badge.tier-great {{ background: linear-gradient(160deg, var(--green), #6b8e00); }}
  .score-badge.tier-good {{ background: linear-gradient(160deg, var(--blue), #1a7fc4); color: #08141c; }}
  .score-badge.tier-ok {{ background: linear-gradient(160deg, var(--gold), #a37300); }}
  .score-badge.tier-low {{ background: linear-gradient(160deg, var(--gray), #3c4f61); color: #dfe8ef; }}
  .card-body {{ flex: 1; min-width: 0; }}
  .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
  .title {{ font-weight: 700; font-size: 15px; color: #fff; }}
  .company {{ color: var(--text-dim); font-size: 13px; margin-top: 2px; }}
  .source-pill {{
    font-size: 11px; text-transform: uppercase; letter-spacing: .03em;
    padding: 3px 9px; border-radius: 999px; border: 1px solid; white-space: nowrap;
  }}
  .keywords {{ margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }}
  .pill {{
    font-size: 11px; background: #ffffff14; color: var(--text-dim);
    padding: 2px 8px; border-radius: 6px;
  }}
  .card-bottom {{ margin-top: 12px; display: flex; align-items: center; gap: 12px; }}
  .posted {{ font-size: 12px; color: var(--text-dim); margin-right: auto; }}
  .apply-btn {{
    text-decoration: none; background: var(--blue); color: #08141c;
    font-weight: 700; font-size: 13px; padding: 6px 14px; border-radius: 6px;
  }}
  .apply-btn:hover {{ background: #8ad4ff; }}
  .mark-btn {{
    cursor: pointer; background: transparent; color: var(--text-dim);
    border: 1px solid #33516d; font-size: 13px; padding: 6px 12px; border-radius: 6px;
  }}
  .mark-btn:hover {{ border-color: var(--green); color: var(--green); }}
  .applied {{ color: var(--green); font-size: 13px; font-weight: 600; }}
  form {{ margin: 0; }}
</style>
</head>
<body>
  <h1>Job Radar</h1>
  <div class="subtitle">{len(jobs)} vagas nos &uacute;ltimos {days} dias</div>
  <div class="tabs">{tabs}</div>
  <div class="grid">{cards}</div>
</body>
</html>"""


def _handle_get(query):
    days = int(query.get("days") or DEFAULT_DAYS)
    since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    jobs = dynamo.query_jobs(TABLE_NAME, GSI_NAME, since_iso)
    token = query.get("token", "")
    return _html_response(200, _render_page(jobs, token, days))


def _parse_body(event):
    body_raw = event.get("body", "") or ""
    if event.get("isBase64Encoded"):
        body_raw = base64.b64decode(body_raw).decode("utf-8")
    return urllib.parse.parse_qs(body_raw)


def _handle_post(fields):
    job_id = (fields.get("job_id") or [""])[0]
    token = (fields.get("token") or [""])[0]

    if not job_id:
        return _html_response(400, "missing job_id")

    dynamo.mark_applied(TABLE_NAME, job_id, datetime.now(timezone.utc).isoformat())
    redirect_qs = urllib.parse.urlencode({"token": token})
    return {"statusCode": 302, "headers": {"Location": f"/?{redirect_qs}"}, "body": ""}


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    query = event.get("queryStringParameters") or {}
    post_fields = _parse_body(event) if method == "POST" else None

    token = post_fields.get("token", [""])[0] if post_fields is not None else query.get("token", "")
    if not hmac.compare_digest(token or "", _expected_token()):
        return _html_response(403, "forbidden")

    if method == "GET":
        return _handle_get(query)
    if method == "POST":
        return _handle_post(post_fields)
    return _html_response(405, "method not allowed")

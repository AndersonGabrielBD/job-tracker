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


def _score_color(score):
    if score >= 75:
        return "#1a7f37"
    if score >= 50:
        return "#9a6700"
    return "#6e7781"


def _row_html(job, token):
    score = job.get("match_score", 0)
    title = html.escape(job.get("title", ""))
    company = html.escape(job.get("company", ""))
    url = html.escape(job.get("url", ""), quote=True)
    keywords = ", ".join(html.escape(k) for k in job.get("matched_keywords", []))
    source = html.escape(job.get("source", ""))
    posted = html.escape((job.get("posted_at") or "")[:10])
    status = job.get("status", "new")

    if status == "applied":
        action_html = f"<span class='applied'>Applied {html.escape((job.get('applied_at') or '')[:10])}</span>"
    else:
        job_id = html.escape(job.get("job_id", ""), quote=True)
        token_q = html.escape(token, quote=True)
        action_html = (
            f"<form method='POST' action='/'>"
            f"<input type='hidden' name='job_id' value='{job_id}'>"
            f"<input type='hidden' name='token' value='{token_q}'>"
            f"<button type='submit'>Mark Applied</button>"
            f"</form>"
        )

    return f"""
    <tr>
      <td class="score" style="color:{_score_color(score)}">{score}</td>
      <td>
        <div class="title">{title}</div>
        <div class="company">{company}</div>
        <div class="keywords">{keywords}</div>
      </td>
      <td class="meta">{source}<br>{posted}</td>
      <td><a href="{url}" target="_blank" rel="noopener">Apply &#8599;</a></td>
      <td>{action_html}</td>
    </tr>
    """


def _render_page(jobs, token, days):
    rows = "".join(_row_html(job, token) for job in jobs)
    token_q = html.escape(token, quote=True)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Job Radar</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; background: #f6f8fa; margin: 0; padding: 24px; }}
  h1 {{ font-size: 20px; }}
  table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
  th {{ background: #fafbfc; font-size: 12px; text-transform: uppercase; color: #57606a; }}
  .score {{ font-weight: 700; font-size: 18px; width: 48px; }}
  .title {{ font-weight: 600; }}
  .company {{ color: #57606a; font-size: 13px; }}
  .keywords {{ color: #57606a; font-size: 12px; margin-top: 4px; }}
  .meta {{ color: #57606a; font-size: 12px; white-space: nowrap; }}
  .applied {{ color: #1a7f37; font-size: 13px; }}
  button {{ cursor: pointer; }}
  .filters {{ margin-bottom: 12px; font-size: 13px; color: #57606a; }}
</style>
</head>
<body>
  <h1>Job Radar &mdash; {len(jobs)} vagas (&uacute;ltimos {days} dias)</h1>
  <div class="filters">
    <a href="/?token={token_q}&days=3">3 dias</a> ·
    <a href="/?token={token_q}&days=7">7 dias</a> ·
    <a href="/?token={token_q}&days=30">30 dias</a>
  </div>
  <table>
    <thead><tr><th>Score</th><th>Vaga</th><th>Fonte</th><th>Link</th><th>Status</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
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

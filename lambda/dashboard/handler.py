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


def _score_tier(score):
    if score >= 75:
        return "great"
    if score >= 50:
        return "good"
    if score >= 25:
        return "ok"
    return "low"


_SOURCE_COLORS = {
    "remotive": "#8b5cf6",
    "remoteok": "#ec4899",
    "arbeitnow": "#f59e0b",
    "adzuna": "#ef4444",
    "gupy": "#06b6d4",
    "jooble": "#10b981",
}


def _source_color(source):
    return _SOURCE_COLORS.get(source, "#6b7280")


def _action_form(job_id, token, return_qs, action, label, css_class):
    job_id_q = html.escape(job_id, quote=True)
    token_q = html.escape(token, quote=True)
    return_qs_q = html.escape(return_qs, quote=True)
    return (
        f"<form method='POST' action='/'>"
        f"<input type='hidden' name='job_id' value='{job_id_q}'>"
        f"<input type='hidden' name='token' value='{token_q}'>"
        f"<input type='hidden' name='return_qs' value='{return_qs_q}'>"
        f"<input type='hidden' name='action' value='{action}'>"
        f"<button type='submit' class='{css_class}'>{label}</button>"
        f"</form>"
    )


def _card_html(job, token, return_qs):
    score = job.get("match_score", 0)
    tier = _score_tier(score)
    title = html.escape(job.get("title", ""))
    company = html.escape(job.get("company", ""))
    url = html.escape(job.get("url", ""), quote=True)
    keywords = job.get("matched_keywords", [])
    keyword_pills = "".join(f"<span class='pill'>{html.escape(k)}</span>" for k in keywords[:6])
    source = job.get("source", "")
    posted = html.escape((job.get("posted_at") or "")[:10])
    fetched = html.escape((job.get("fetched_at") or "")[:10])
    status = job.get("status", "new")
    is_disqualified = bool(job.get("is_disqualified"))
    job_id = job.get("job_id", "")

    tags_html = ""
    if status == "applied":
        tags_html += f"<span class='applied-tag'><svg viewBox='0 0 20 20' width='13' height='13'><path fill='currentColor' d='M7.5 13.5 3.8 9.8l1.4-1.4 2.3 2.3 6.3-6.3 1.4 1.4z'/></svg>Aplicada {html.escape((job.get('applied_at') or '')[:10])}</span>"
    if is_disqualified:
        tags_html += f"<span class='disqualified-tag'>Desqualificada {html.escape((job.get('disqualified_at') or '')[:10])}</span>"

    action_buttons = ""
    if status != "applied":
        action_buttons += _action_form(job_id, token, return_qs, "apply", "Marcar aplicada", "btn-ghost")
    if not is_disqualified:
        action_buttons += _action_form(job_id, token, return_qs, "disqualify", "Desqualificar", "btn-danger")

    return f"""
    <article class="card">
      <div class="score score-{tier}">
        <span class="score-num">{score}</span>
      </div>
      <div class="card-main">
        <header class="card-head">
          <div>
            <h3 class="job-title">{title}</h3>
            <div class="job-company">{company}</div>
          </div>
          <span class="source-tag" style="--dot:{_source_color(source)}">{html.escape(source)}</span>
        </header>
        {f'<div class="pills">{keyword_pills}</div>' if keyword_pills else ''}
        {f'<div class="tags">{tags_html}</div>' if tags_html else ''}
        <footer class="card-foot">
          <div class="dates">
            <time class="posted" title="Publicada">Publicada {posted}</time>
            <time class="fetched" title="Chegou no app">Chegou {fetched}</time>
          </div>
          <div class="actions">
            {action_buttons}
            <a class="btn-primary" href="{url}" target="_blank" rel="noopener">Candidatar <svg viewBox="0 0 20 20" width="13" height="13"><path fill="currentColor" d="M5 15 15 5M8 5h7v7" stroke="currentColor" stroke-width="1.6" fill="none"/></svg></a>
          </div>
        </footer>
      </div>
    </article>
    """


def _render_page(jobs, token, filters):
    days = filters["days"]
    date_field = filters["date_field"]
    status = filters["status"]
    show_disqualified = filters["show_disqualified"]

    token_q = html.escape(token, quote=True)

    return_qs = urllib.parse.urlencode({
        "token": token,
        "days": days,
        "date_field": date_field,
        "status": status,
        "show_disqualified": "1" if show_disqualified else "0",
    })

    cards = "".join(_card_html(job, token, return_qs) for job in jobs) or (
        "<div class='empty'>Nenhuma vaga encontrada com esses filtros. "
        "A harvester roda &agrave;s 08h e 18h &mdash; volte mais tarde.</div>"
    )

    applied_count = sum(1 for j in jobs if j.get("status") == "applied")
    disqualified_count = sum(1 for j in jobs if j.get("is_disqualified"))
    avg_score = round(sum(j.get("match_score", 0) for j in jobs) / len(jobs)) if jobs else 0

    def _day_tab(d, label):
        active = "active" if d == days else ""
        qs = urllib.parse.urlencode({
            "token": token, "days": d, "date_field": date_field,
            "status": status, "show_disqualified": "1" if show_disqualified else "0",
        })
        return f"<a class='tab {active}' href='/?{qs}'>{label}</a>"

    tabs = _day_tab(3, "3 dias") + _day_tab(7, "7 dias") + _day_tab(30, "30 dias")

    def _option(value, label, current):
        selected = "selected" if value == current else ""
        return f"<option value='{value}' {selected}>{label}</option>"

    status_options = (
        _option("all", "Todas", status)
        + _option("new", "N&atilde;o aplicadas", status)
        + _option("applied", "Aplicadas", status)
    )
    date_field_options = (
        _option("posted_at", "Data de publica&ccedil;&atilde;o", date_field)
        + _option("fetched_at", "Data que chegou no app", date_field)
    )
    show_disqualified_checked = "checked" if show_disqualified else ""

    filters_html = f"""
    <form class="filters" method="GET" action="/">
      <input type="hidden" name="token" value="{token_q}">
      <div class="filter-group">
        <label>Status</label>
        <select name="status">{status_options}</select>
      </div>
      <div class="filter-group">
        <label>Filtrar por</label>
        <select name="date_field">{date_field_options}</select>
      </div>
      <div class="filter-group">
        <label>&Uacute;ltimos N dias</label>
        <input type="number" name="days" min="1" max="365" value="{days}">
      </div>
      <label class="checkbox">
        <input type="checkbox" name="show_disqualified" value="1" {show_disqualified_checked}>
        Mostrar desqualificadas
      </label>
      <button type="submit" class="btn-primary">Filtrar</button>
    </form>
    """

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #09090f;
    --bg-radial: radial-gradient(circle at 15% 0%, rgba(124,110,242,.12), transparent 45%),
                 radial-gradient(circle at 85% 20%, rgba(16,185,129,.08), transparent 40%);
    --surface: #131319;
    --surface-2: #1a1a22;
    --border: #24242e;
    --border-hover: #34344a;
    --text: #f2f2f5;
    --text-dim: #9999a8;
    --text-faint: #68687a;
    --accent: #7c6ef2;
    --accent-2: #38bdf8;
    --great: #34d399;
    --good: #38bdf8;
    --ok: #fbbf24;
    --low: #6b7280;
    --radius: 14px;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
    background: var(--bg-radial), var(--bg);
    color: var(--text);
    margin: 0;
    padding: 40px 20px 80px;
    min-height: 100vh;
  }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  .top {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 28px; gap: 16px; flex-wrap: wrap; }}
  .brand {{ display: flex; align-items: center; gap: 10px; }}
  .dot {{
    width: 10px; height: 10px; border-radius: 50%; background: var(--accent);
    box-shadow: 0 0 0 4px rgba(124,110,242,.18);
  }}
  h1 {{ font-size: 22px; font-weight: 800; margin: 0; letter-spacing: -.02em; }}
  .stats {{ display: flex; gap: 10px; }}
  .stat {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 8px 14px; text-align: center; min-width: 76px;
  }}
  .stat .n {{ font-size: 17px; font-weight: 700; display: block; }}
  .stat .l {{ font-size: 10.5px; color: var(--text-faint); text-transform: uppercase; letter-spacing: .04em; }}
  .tabs {{ display: inline-flex; gap: 2px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 3px; margin-bottom: 20px; }}
  .tab {{
    text-decoration: none; color: var(--text-dim); font-size: 13px; font-weight: 500;
    padding: 6px 16px; border-radius: 8px; transition: all .15s;
  }}
  .tab:hover {{ color: var(--text); }}
  .tab.active {{ background: var(--accent); color: #fff; font-weight: 600; }}
  .grid {{ display: flex; flex-direction: column; gap: 10px; }}
  .empty {{ color: var(--text-dim); font-size: 14px; padding: 40px 0; text-align: center; }}
  .card {{
    display: flex; gap: 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
    transition: border-color .15s, transform .15s;
  }}
  .card:hover {{ border-color: var(--border-hover); transform: translateY(-1px); }}
  .score {{
    flex: 0 0 50px; height: 50px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 17px;
  }}
  .score-great {{ background: rgba(52,211,153,.14); color: var(--great); }}
  .score-good  {{ background: rgba(56,189,248,.14); color: var(--good); }}
  .score-ok    {{ background: rgba(251,191,36,.14); color: var(--ok); }}
  .score-low   {{ background: rgba(107,114,128,.14); color: var(--low); }}
  .card-main {{ flex: 1; min-width: 0; }}
  .card-head {{ display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }}
  .job-title {{ font-size: 15px; font-weight: 650; margin: 0; color: var(--text); line-height: 1.35; }}
  .job-company {{ font-size: 12.5px; color: var(--text-dim); margin-top: 2px; }}
  .source-tag {{
    flex-shrink: 0; font-size: 10.5px; font-weight: 600; color: var(--text-dim);
    text-transform: uppercase; letter-spacing: .04em; white-space: nowrap;
    display: flex; align-items: center; gap: 5px; padding-top: 3px;
  }}
  .source-tag::before {{ content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--dot); }}
  .pills {{ margin-top: 10px; display: flex; flex-wrap: wrap; gap: 5px; }}
  .pill {{
    font-size: 11px; font-weight: 500; background: var(--surface-2); color: var(--text-dim);
    padding: 3px 9px; border-radius: 6px; border: 1px solid var(--border);
  }}
  .card-foot {{ margin-top: 13px; display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }}
  .dates {{ display: flex; flex-direction: column; gap: 2px; }}
  .posted, .fetched {{ font-size: 11.5px; color: var(--text-faint); }}
  .actions {{ display: flex; align-items: center; gap: 8px; margin-left: auto; }}
  form {{ margin: 0; }}
  .btn-primary {{
    display: inline-flex; align-items: center; gap: 6px;
    text-decoration: none; background: var(--accent); color: #fff;
    font-weight: 600; font-size: 12.5px; padding: 7px 14px; border-radius: 8px;
    transition: background .15s;
  }}
  .btn-primary:hover {{ background: #8f82f5; }}
  .btn-ghost {{
    cursor: pointer; background: transparent; color: var(--text-dim);
    border: 1px solid var(--border); font-size: 12.5px; font-weight: 500;
    padding: 7px 13px; border-radius: 8px; transition: all .15s; font-family: inherit;
  }}
  .btn-ghost:hover {{ border-color: var(--great); color: var(--great); }}
  .btn-danger {{
    cursor: pointer; background: transparent; color: var(--text-dim);
    border: 1px solid var(--border); font-size: 12.5px; font-weight: 500;
    padding: 7px 13px; border-radius: 8px; transition: all .15s; font-family: inherit;
  }}
  .btn-danger:hover {{ border-color: #f87171; color: #f87171; }}
  .applied-tag {{
    display: inline-flex; align-items: center; gap: 5px;
    color: var(--great); font-size: 12.5px; font-weight: 600;
  }}
  .disqualified-tag {{
    display: inline-flex; align-items: center; gap: 5px;
    color: #f87171; font-size: 12.5px; font-weight: 600;
  }}
  .tags {{ margin-top: 10px; display: flex; gap: 10px; flex-wrap: wrap; }}
  .filters {{
    display: flex; align-items: flex-end; gap: 14px; flex-wrap: wrap;
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 16px; margin-bottom: 16px;
  }}
  .filter-group {{ display: flex; flex-direction: column; gap: 5px; }}
  .filter-group label {{ font-size: 11px; color: var(--text-faint); text-transform: uppercase; letter-spacing: .04em; }}
  .filters select, .filters input[type="number"] {{
    background: var(--surface-2); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; padding: 7px 10px; font-size: 13px; font-family: inherit;
  }}
  .filters input[type="number"] {{ width: 90px; }}
  .checkbox {{
    display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-dim);
    padding-bottom: 8px;
  }}
  .filters .btn-primary {{ cursor: pointer; border: none; font-family: inherit; }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div class="brand">
        <span class="dot"></span>
        <h1>Job Radar</h1>
      </div>
      <div class="stats">
        <div class="stat"><span class="n">{len(jobs)}</span><span class="l">Vagas</span></div>
        <div class="stat"><span class="n">{avg_score}</span><span class="l">Score m&eacute;dio</span></div>
        <div class="stat"><span class="n">{applied_count}</span><span class="l">Aplicadas</span></div>
        <div class="stat"><span class="n">{disqualified_count}</span><span class="l">Desqualif.</span></div>
      </div>
    </div>
    {filters_html}
    <div class="tabs">{tabs}</div>
    <div class="grid">{cards}</div>
  </div>
</body>
</html>"""


def _handle_get(query):
    days_raw = query.get("days") or str(DEFAULT_DAYS)
    try:
        days = int(days_raw)
    except ValueError:
        days = DEFAULT_DAYS
    days = min(max(days, 1), 365)

    date_field = query.get("date_field") or "posted_at"
    if date_field not in ("posted_at", "fetched_at"):
        date_field = "posted_at"

    status = query.get("status") or "all"
    if status not in ("all", "new", "applied"):
        status = "all"

    show_disqualified = query.get("show_disqualified") == "1"

    since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    jobs = dynamo.query_jobs(
        TABLE_NAME, GSI_NAME, since_iso,
        date_field=date_field, status=status, show_disqualified=show_disqualified,
    )
    token = query.get("token", "")
    filters = {
        "days": days,
        "date_field": date_field,
        "status": status,
        "show_disqualified": show_disqualified,
    }
    return _html_response(200, _render_page(jobs, token, filters))


def _parse_body(event):
    body_raw = event.get("body", "") or ""
    if event.get("isBase64Encoded"):
        body_raw = base64.b64decode(body_raw).decode("utf-8")
    return urllib.parse.parse_qs(body_raw)


def _handle_post(fields):
    job_id = (fields.get("job_id") or [""])[0]
    token = (fields.get("token") or [""])[0]
    action = (fields.get("action") or ["apply"])[0]
    return_qs = (fields.get("return_qs") or [""])[0]

    if not job_id:
        return _html_response(400, "missing job_id")

    now_iso = datetime.now(timezone.utc).isoformat()
    if action == "disqualify":
        dynamo.mark_disqualified(TABLE_NAME, job_id, now_iso)
    else:
        dynamo.mark_applied(TABLE_NAME, job_id, now_iso)

    location = f"/?{return_qs}" if return_qs else f"/?{urllib.parse.urlencode({'token': token})}"
    return {"statusCode": 302, "headers": {"Location": location}, "body": ""}


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

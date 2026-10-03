"""Weighted keyword-overlap match scoring. Zero cost, zero network calls,
fully deterministic/explainable -- no LLM involved.

`keywords` is a list of [term, weight] pairs so core-stack terms (python,
fastapi, aws lambda...) count for more than generic ones (backend, ci/cd...)
that show up in almost every posting regardless of language/stack."""

TITLE_MULTIPLIER = 2
# Calibrated so ~2 solid core-weight (3) title hits reach 100.
MAX_SCORE_POINTS = 24


def score_job(job, keywords):
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()

    matched = []
    points = 0
    for term, weight in keywords:
        needle = term.lower()
        if not needle:
            continue
        if needle in title:
            points += weight * TITLE_MULTIPLIER
            matched.append(term)
        elif needle in description:
            points += weight
            matched.append(term)

    score = min(100, round(100 * points / MAX_SCORE_POINTS)) if MAX_SCORE_POINTS else 0
    return score, matched

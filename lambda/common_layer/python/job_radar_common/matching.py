"""Keyword-overlap match scoring. Zero cost, zero network calls, fully
deterministic/explainable -- no LLM involved."""

TITLE_WEIGHT = 2
DESCRIPTION_WEIGHT = 1
# Distinct title-weighted keyword hits needed to reach a 100 score.
MAX_SCORE_KEYWORDS = 8


def score_job(job, keywords):
    title = (job.get("title") or "").lower()
    description = (job.get("description") or "").lower()

    matched = []
    points = 0
    for keyword in keywords:
        needle = keyword.lower()
        if not needle:
            continue
        if needle in title:
            points += TITLE_WEIGHT
            matched.append(keyword)
        elif needle in description:
            points += DESCRIPTION_WEIGHT
            matched.append(keyword)

    max_points = MAX_SCORE_KEYWORDS * TITLE_WEIGHT
    score = min(100, round(100 * points / max_points)) if max_points else 0
    return score, matched

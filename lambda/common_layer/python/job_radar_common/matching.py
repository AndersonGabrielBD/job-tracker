"""Weighted keyword-overlap match scoring. Zero cost, zero network calls,
fully deterministic/explainable -- no LLM involved.

`keywords` is a list of [term, weight] pairs so core-stack terms (python,
fastapi, aws lambda...) count for more than generic ones (backend, ci/cd...)
that show up in almost every posting regardless of language/stack."""

TITLE_MULTIPLIER = 2
# Chosen (not 24) so a single core-weight (3) term matched only in the
# description -- points=3 -- clears MIN_SCORE=13: 100*3/23 rounds to 13,
# whereas /24 rounds 12.5 down to 12 (banker's rounding) and silently drops
# a genuine single core-stack mention.
MAX_SCORE_POINTS = 23

# A job only counts if at least one of these actually matched -- otherwise
# generic/secondary terms (aws, docker, sql, ci/cd...) could stack up enough
# weight on their own to clear MIN_SCORE even though the posting has no real
# signal of being a python or javascript/react/typescript job.
ANCHOR_TERMS = {
    "python", "fastapi", "flask", "django",
    "javascript", "typescript", "react", "next.js",
    "engenheiro de dados", "data engineer", "data engineering", "data pipeline",
}


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

    if not any(term.lower() in ANCHOR_TERMS for term in matched):
        return 0, []

    score = min(100, round(100 * points / MAX_SCORE_POINTS)) if MAX_SCORE_POINTS else 0
    return score, matched

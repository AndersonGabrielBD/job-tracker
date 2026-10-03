"""Reject obviously senior-level postings -- personal preference is pleno
or below. Matches "senior"/"sênior"/"sr"/"sr."/"especialista" (Brazilian
leveling term above pleno/senior) as a standalone word in the title,
case-insensitive."""
import re

_SENIOR_PATTERN = re.compile(r"\b(s[êe]nior|sr\.?|especialista)\b", re.IGNORECASE)


def is_senior(title):
    return bool(_SENIOR_PATTERN.search(title or ""))

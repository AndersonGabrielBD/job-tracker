"""Reject obviously senior-level postings -- personal preference is pleno
or below. Matches "senior"/"sênior"/"sr"/"sr." as a standalone word in the
title (PT and EN), case-insensitive."""
import re

_SENIOR_PATTERN = re.compile(r"\b(s[êe]nior|sr\.?)\b", re.IGNORECASE)


def is_senior(title):
    return bool(_SENIOR_PATTERN.search(title or ""))

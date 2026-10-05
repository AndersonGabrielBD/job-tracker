"""Hard-reject postings whose primary stack/role doesn't fit python
(backend/data-eng) or javascript/react/typescript. Keyword scoring alone
isn't enough here: a .NET posting that lists React/TypeScript as a "nice to
have" still contains those substrings and would clear the weighted-score
bar, so conflicting-stack and QA/testing roles are rejected outright before
scoring ever runs."""
import re

_OTHER_STACK_PATTERN = re.compile(
    r"(c#|\.net\b|asp\.net|\bjava\b|\bphp\b|\bdelphi\b|\bsalesforce\b)",
    re.IGNORECASE,
)

_QA_PATTERN = re.compile(
    r"\b(qa|quality assurance|sdet|tester|teste de software|"
    r"an[aá]lista de (?:qualidade|testes?)|automa[cç][aã]o de testes)\b",
    re.IGNORECASE,
)


def is_other_stack(title, description=""):
    return bool(_OTHER_STACK_PATTERN.search(f"{title or ''} {description or ''}"))


def is_qa_role(title):
    return bool(_QA_PATTERN.search(title or ""))

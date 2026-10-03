"""Scope gate: keep remote jobs anywhere, or Brazil jobs that are remote or
based in Maceio specifically (reject on-site jobs in other Brazilian cities)."""
import unicodedata

MACEIO_NEEDLE = "maceio"


def _fold(text):
    text = (text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def is_in_scope(job):
    if job.get("is_remote"):
        return True

    if (job.get("country") or "").upper() != "BR":
        return False

    city = _fold(job.get("city"))
    location_raw = _fold(job.get("location_raw"))
    return MACEIO_NEEDLE in city or MACEIO_NEEDLE in location_raw

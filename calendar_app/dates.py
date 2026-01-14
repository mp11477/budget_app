from datetime import date
from django.utils import timezone

def parse_ymd(date_str: str | None, default: date | None = None) -> date:
    """
    Parse YYYY-MM-DD into a date. Returns default (or today) if missing/invalid.
    """
    if default is None:
        default = timezone.localdate()

    if not date_str:
        return default

    try:
        y, m, d = map(int, date_str.split("-"))
        return date(y, m, d)
    except Exception:
        return default
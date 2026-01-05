from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Any, Iterable, Set, Tuple

from django.utils import timezone

from .models import CalendarSpecial, CalendarRuleSpecial


def aware_range(start_d: date, end_d: date) -> tuple[datetime, datetime]:
    """
    Inclusive date range -> aware datetime min/max.
    """
    start_dt = timezone.make_aware(datetime.combine(start_d, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_d, time.max))
    return start_dt, end_dt


def years_spanned(start_d: date, end_d: date) -> Set[int]:
    return {start_d.year, end_d.year}


def inject_specials_into_events_by_day(
    events_by_day: Dict[date, List[Any]],
    start_d: date,
    end_d: date,
) -> None:
    """
    Inserts special items at the top of events_by_day[occ] (index 0),
    for all occurrences within [start_d, end_d], including year-boundary spans.
    Output matches what your week/month templates already consume.
    """
    years_to_check = years_spanned(start_d, end_d)

    # Fixed-date specials
    for s in CalendarSpecial.objects.all():
        if s.recurring_yearly:
            for y in years_to_check:
                occ = date(y, s.date.month, s.date.day)
                if start_d <= occ <= end_d:
                    events_by_day.setdefault(occ, []).insert(0, {
                        "title": s.title,
                        "all_day": True,
                        "person": s.person or "",
                        "is_special": True,
                        "special_type": s.special_type,
                        "notes": s.notes,
                        "color_key": s.color_key,
                    })
        else:
            occ = s.date
            if start_d <= occ <= end_d:
                events_by_day.setdefault(occ, []).insert(0, {
                    "title": s.title,
                    "all_day": True,
                    "person": s.person or "",
                    "is_special": True,
                    "special_type": s.special_type,
                    "notes": s.notes,
                    "color_key": s.color_key,
                })

    # Rule specials
    for rs in CalendarRuleSpecial.objects.filter(is_enabled=True):
        for y in years_to_check:
            occ = compute_rule_date(rs.rule_key, y)
            if start_d <= occ <= end_d:
                events_by_day.setdefault(occ, []).insert(0, {
                    "title": rs.title_override or rs.get_rule_key_display(),
                    "all_day": True,
                    "person": rs.person or "",
                    "is_special": True,
                    "special_type": rs.special_type,
                    "notes": rs.notes,
                    "color_key": rs.color_key,
                })


# ---- Date rule computations for calendar specials ----
def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))


def last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def easter_western(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def compute_rule_date(rule_key: str, year: int) -> date:
    if rule_key == "easter":
        return easter_western(year)

    if rule_key == "good_friday":
        return easter_western(year) - timedelta(days=2)

    if rule_key == "thanksgiving_us":
        return nth_weekday_of_month(year, 11, weekday=3, n=4)

    if rule_key == "mothers_day_us":
        return nth_weekday_of_month(year, 5, weekday=6, n=2)

    if rule_key == "fathers_day_us":
        return nth_weekday_of_month(year, 6, weekday=6, n=3)

    if rule_key == "memorial_day_us":
        return last_weekday_of_month(year, 5, weekday=0)

    if rule_key == "labor_day_us":
        return nth_weekday_of_month(year, 9, weekday=0, n=1)

    if rule_key == "mlk_day_us":
        return nth_weekday_of_month(year, 1, weekday=0, n=3)

    if rule_key == "presidents_day_us":
        return nth_weekday_of_month(year, 2, weekday=0, n=3)

    raise ValueError(f"Unknown rule_key: {rule_key}")
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Any, Set

from django.utils import timezone

from budget.models import CalendarSpecial, CalendarRuleSpecial

def aware_range(start_d: date, end_d: date) -> tuple[datetime, datetime]:
    """
    Convert an inclusive date range [start_d, end_d] into an *aware* datetime range.

    Returns:
        (start_dt, end_dt) where:
        - start_dt = start_d at 00:00:00 (timezone-aware)
        - end_dt   = end_d at 23:59:59.999999 (timezone-aware)

    Used when querying DateTimeFields (start_dt/end_dt) for a whole-day date window.
    """
    start_dt = timezone.make_aware(datetime.combine(start_d, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_d, time.max))
    return start_dt, end_dt

def years_spanned(start_d: date, end_d: date) -> Set[int]:
    """
    Return the set of calendar years touched by [start_d, end_d].

    Why:
        Month/week grids can span year boundaries (e.g., last week of Dec spills into Jan),
        so recurring/yearly specials must be computed for each year included.

    Example:
        start_d=2026-12-28, end_d=2027-01-03 -> {2026, 2027}
    """
    return {start_d.year, end_d.year}

def inject_specials_into_events_by_day(
    events_by_day: Dict[date, List[Any]],
    start_d: date,
    end_d: date,
) -> None:
    """
    Mutates events_by_day by injecting "special items" into the list for each occurrence date.

    Inputs:
        events_by_day: dict mapping a date -> list of event objects/dicts used by templates.
        start_d/end_d: inclusive range currently being displayed (month/week/day window).

    Behavior:
        - Inserts special items at the *top* of each date's list (index 0), so they render first.
        - Handles:
            1) Fixed-date specials (CalendarSpecial)
               - recurring_yearly=True -> occurs each year on the same month/day
               - recurring_yearly=False -> occurs only on its stored date
            2) Rule-based specials (CalendarRuleSpecial)
               - computed per year from a rule_key like "easter", "thanksgiving_us", etc.

    Output format:
        Inserts dicts shaped the way your templates already expect, e.g.:
            {
              "title": "...",
              "all_day": True,
              "person": "",
              "is_special": True,
              "special_type": "...",
              "notes": "...",
              "color_key": "..."
            }
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

def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """
    Return the date of the nth occurrence of a weekday in a given month.

    Args:
        weekday: Monday=0 ... Sunday=6 (Python's date.weekday())
        n: 1..5 (e.g., 4th Thursday)

    Examples:
        - 4th Thursday of November (US Thanksgiving)
        - 2nd Sunday of May (US Mother's Day)
    """
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))

def last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """
    Return the date of the last occurrence of a weekday in a given month.

    Examples:
        - last Monday of May (US Memorial Day)

    Implementation detail:
        Find the last day of the month, then walk backward to the desired weekday.
    """
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)

    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d

def easter_western(year: int) -> date:
    """
    Compute Western (Gregorian) Easter for a given year.

    Uses the Meeus/Jones/Butcher "Anonymous Gregorian algorithm".
    Returns:
        date object for Easter Sunday in that year.
    """
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
    """
    Convert a CalendarRuleSpecial.rule_key into a concrete date for a given year.

    Supported rule_key values (examples):
        - "easter"
        - "good_friday"
        - "thanksgiving_us"   (4th Thursday of November)
        - "mothers_day_us"    (2nd Sunday of May)
        - "fathers_day_us"    (3rd Sunday of June)
        - "memorial_day_us"   (last Monday of May)
        - "labor_day_us"      (1st Monday of September)
        - "mlk_day_us"        (3rd Monday of January)
        - "presidents_day_us" (3rd Monday of February)

    Raises:
        ValueError if rule_key is unknown (helps catch typos in admin data).
    """
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
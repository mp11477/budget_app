from datetime import date, datetime, time
from typing import Any
from collections import defaultdict

from django.utils import timezone
from calendar_app.models import CalendarEvent  

def get_events_overlapping_range(owner: Any, start_d: date, end_d: date):
    """
    Return events for owner that overlap the inclusive date range [start_d, end_d].
    """
    start_dt = timezone.make_aware(datetime.combine(start_d, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_d, time.max))

    return (
        CalendarEvent.objects
        .filter(user=owner, start_dt__lte=end_dt, end_dt__gte=start_dt)
        .order_by("start_dt")
    )

def group_events_by_start_date(events):
    """
    Group events by the local date of their start_dt.
    Returns dict[date] -> list[CalendarEvent]
    """
    out = defaultdict(list)
    for e in events:
        d = timezone.localtime(e.start_dt).date()
        out[d].append(e)
    return out
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from collections import defaultdict
from calendar import monthrange

from django.utils import timezone

from calendar_app.models import CalendarEvent

@dataclass
class CalendarOccurrence:
    """
    One displayed occurrence of a CalendarEvent.

    For a non-recurring event, start_dt/end_dt are the event's real dates.

    For a recurring event, start_dt/end_dt are calculated dates for this
    particular occurrence while `event` remains the original database row.
    """
    event: CalendarEvent
    start_dt: datetime
    end_dt: datetime

    @property
    def id(self):
        return self.event.id

    @property
    def title(self):
        return self.event.title

    @property
    def person(self):
        return self.event.person

    @property
    def all_day(self):
        return self.event.all_day

    @property
    def recurrence(self):
        return self.event.recurrence

    @property
    def recurrence_end(self):
        return self.event.recurrence_end

    @property
    def occurrence_date(self):
        return timezone.localtime(self.start_dt).date()

    def __getattr__(self, name):
        """
        Fall back to the original CalendarEvent for fields we have not
        explicitly exposed above (location, notes, status, etc.).
        """
        return getattr(self.event, name)


def _add_months(d: date, months: int) -> date:
    """
    Move `d` forward by N calendar months.

    If the target month does not contain the original day number,
    use the last valid day of that month.

    Example:
        Jan 31 + 1 month -> Feb 28/29
    """
    month_index = (d.year * 12 + (d.month - 1)) + months

    year = month_index // 12
    month = (month_index % 12) + 1

    last_day = monthrange(year, month)[1]
    day = min(d.day, last_day)

    return date(year, month, day)


def _replace_local_date(dt: datetime, new_date: date) -> datetime:
    """
    Keep the local clock time from `dt`, but place it on `new_date`.
    """
    local_dt = timezone.localtime(dt)

    naive = datetime.combine(
        new_date,
        local_dt.time().replace(tzinfo=None),
    )

    return timezone.make_aware(
        naive,
        timezone.get_current_timezone(),
    )


def _next_occurrence_date(
    original_start: date,
    current: date,
    recurrence: str,
    occurrence_index: int,
) -> date:
    """
    Calculate the next recurrence date.

    Daily/weekly recurrence advances from the current occurrence because those
    intervals have a fixed number of days.

    Monthly/yearly recurrence is always calculated from the original series
    start date so short months do not permanently shift the series.

    Example:
        Jan 31 monthly
        -> Feb 28
        -> Mar 31
        -> Apr 30
        -> May 31
    """

    if recurrence == "daily":
        return current + timedelta(days=1)

    if recurrence == "weekdays":
        next_date = current + timedelta(days=1)

        while next_date.weekday() >= 5:
            next_date += timedelta(days=1)

        return next_date

    if recurrence == "weekly":
        return current + timedelta(days=7)

    if recurrence == "biweekly":
        return current + timedelta(days=14)

    if recurrence == "monthly":
        return _add_months(
            original_start,
            occurrence_index,
        )

    if recurrence == "bimonthly":
        return _add_months(
            original_start,
            occurrence_index * 2,
        )

    if recurrence == "yearly":
        return _add_months(
            original_start,
            occurrence_index * 12,
        )

    return current


def _event_duration(event: CalendarEvent) -> timedelta:
    return event.end_dt - event.start_dt


def _make_occurrence(
    event: CalendarEvent,
    occurrence_date: date,
) -> CalendarOccurrence:
    occurrence_start = _replace_local_date(
        event.start_dt,
        occurrence_date,
    )

    occurrence_end = occurrence_start + _event_duration(event)

    return CalendarOccurrence(
        event=event,
        start_dt=occurrence_start,
        end_dt=occurrence_end,
    )


def _expand_event(
    event: CalendarEvent,
    start_d: date,
    end_d: date,
) -> list[CalendarOccurrence]:
    """
    Expand one CalendarEvent into the occurrences that overlap
    the inclusive range [start_d, end_d].
    """

    original_start = timezone.localtime(event.start_dt).date()

    if event.recurrence == "weekdays" and original_start.weekday() >= 5:
        while original_start.weekday() >= 5:
            original_start += timedelta(days=1)

    # Ordinary one-time appointment.
    if event.recurrence == "none":
        original_end = timezone.localtime(event.end_dt).date()

        if original_start <= end_d and original_end >= start_d:
            return [
                CalendarOccurrence(
                    event=event,
                    start_dt=event.start_dt,
                    end_dt=event.end_dt,
                )
            ]

        return []

    occurrences = []

    current_date = original_start
    occurrence_index = 0

    while current_date <= end_d:

        # Stop generating once the recurrence end date has passed.
        if (
            event.recurrence_end is not None
            and current_date > event.recurrence_end
        ):
            break

        occurrence = _make_occurrence(event, current_date)

        occurrence_start_date = timezone.localtime(
            occurrence.start_dt
        ).date()

        occurrence_end_date = timezone.localtime(
            occurrence.end_dt
        ).date()

        if (
            occurrence_start_date <= end_d
            and occurrence_end_date >= start_d
        ):
            occurrences.append(occurrence)

        occurrence_index += 1

        next_date = _next_occurrence_date(
            original_start,
            current_date,
            event.recurrence,
            occurrence_index,
        )

        # Safety against an accidental infinite loop.
        if next_date <= current_date:
            break

        current_date = next_date

    return occurrences


def get_events_overlapping_range(
    owner: Any,
    start_d: date,
    end_d: date,
):
    """
    Return CalendarOccurrence objects for all appointments that should
    appear in the inclusive date range [start_d, end_d].

    Recurring CalendarEvent rows are expanded into temporary occurrences.
    No duplicate database rows are created.
    """

    range_end_dt = timezone.make_aware(
        datetime.combine(end_d, time.max)
    )

    events = (
        CalendarEvent.objects
        .filter(
            user=owner,
            start_dt__lte=range_end_dt,
        )
        .order_by("start_dt")
    )

    occurrences = []

    for event in events:
        occurrences.extend(
            _expand_event(
                event,
                start_d,
                end_d,
            )
        )

    occurrences.sort(key=lambda occurrence: occurrence.start_dt)

    return occurrences


def group_events_by_start_date(events):
    """
    Group CalendarOccurrence objects by their displayed local start date.

    Returns:
        dict[date] -> list[CalendarOccurrence]
    """
    out = defaultdict(list)

    for event in events:
        d = timezone.localtime(event.start_dt).date()
        out[d].append(event)

    return out

def get_occurrence_for_date(
    event: CalendarEvent,
    occurrence_date: date,
) -> CalendarOccurrence | None:
    """
    Return the occurrence of `event` that starts on `occurrence_date`.

    Returns None if that date is not actually part of the recurring series.
    """

    occurrences = _expand_event(
        event,
        occurrence_date,
        occurrence_date,
    )

    for occurrence in occurrences:
        if occurrence.occurrence_date == occurrence_date:
            return occurrence

    return None
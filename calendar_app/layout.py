from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, List, Tuple

from django.utils import timezone


@dataclass
class EventBlock:
    """
    A rendered event "block" for the day timeline.

    top/height are pixels based on minutes since midnight.
    col/col_count handle simple overlap columns.
    """
    id: int
    title: str
    person: str
    start_dt: datetime
    end_dt: datetime
    top: int
    height: int
    col: int
    col_count: int


def _minutes_since_midnight(dt: datetime) -> int:
    local = timezone.localtime(dt)
    return local.hour * 60 + local.minute


def build_day_timeline_blocks(
    events: Iterable[Any],
    day: date,
) -> tuple[list[Any], list[EventBlock]]:
    """
    Split a day's events into:
      - all_day_events: events flagged all_day=True
      - event_blocks: timed events positioned for the vertical timeline

    Overlap handling:
      - assigns events into columns within "clusters" of overlapping events.
      - sets col_count = number of columns used by that overlap cluster.
    """
    all_day_events: list[Any] = []
    timed: list[Any] = []

    for e in events:
        if getattr(e, "all_day", False):
            all_day_events.append(e)
        else:
            timed.append(e)

    # Sort by start time
    timed.sort(key=lambda e: e.start_dt)

    # Build blocks with initial geometry (top/height)
    raw_blocks: list[EventBlock] = []
    for e in timed:
        start_min = max(0, _minutes_since_midnight(e.start_dt))
        end_min = max(start_min + 1, _minutes_since_midnight(e.end_dt))
        top = start_min  # 1px per minute
        height = max(28, end_min - start_min)  # enforce min height like your CSS

        raw_blocks.append(EventBlock(
            id=e.id,
            title=e.title,
            person=getattr(e, "person", "") or "",
            start_dt=timezone.localtime(e.start_dt),
            end_dt=timezone.localtime(e.end_dt),
            top=top,
            height=height,
            col=0,
            col_count=1,
        ))

    # --- Assign overlap columns ---
    # Greedy column assignment within overlap clusters
    def overlaps(a: EventBlock, b: EventBlock) -> bool:
        a_end = a.top + a.height
        b_end = b.top + b.height
        return not (a_end <= b.top or b_end <= a.top)

    i = 0
    while i < len(raw_blocks):
        # Find an overlap cluster starting at i
        cluster = [raw_blocks[i]]
        j = i + 1
        while j < len(raw_blocks):
            if any(overlaps(raw_blocks[j], c) for c in cluster):
                cluster.append(raw_blocks[j])
                j += 1
            else:
                break

        # Assign columns to the cluster
        cols: list[list[EventBlock]] = []
        for b in cluster:
            placed = False
            for col_idx, col in enumerate(cols):
                if not overlaps(b, col[-1]):
                    b.col = col_idx
                    col.append(b)
                    placed = True
                    break
            if not placed:
                b.col = len(cols)
                cols.append([b])

        col_count = len(cols)
        for b in cluster:
            b.col_count = col_count

        i += len(cluster)

    return all_day_events, raw_blocks

def build_weeks(grid_start: date, grid_end: date) -> list[list[date]]:
    days = []
    d = grid_start
    while d <= grid_end:
        days.append(d)
        d += timedelta(days=1)
    return [days[i:i+7] for i in range(0, len(days), 7)]
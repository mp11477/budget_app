from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_GET

from .dates import parse_ymd
from .devices import looks_like_tablet
from .layout import build_day_timeline_blocks, build_weeks
from .queries import get_events_overlapping_range, group_events_by_start_date
from .specials import inject_specials_into_events_by_day, get_special_items_for_day
from .weather import get_cached_weather
from .permissions import kiosk_enabled, kiosk_edit_required, edit_actor
from .url_helpers import calendar_home_url

from calendar_app.models import CalendarEvent 
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from calendar import monthrange

from pathlib import Path

#Pure Helper functions
def add_month(year, month, delta):
    # delta = -1 or +1
    new_month = month + delta
    new_year = year
    if new_month == 0:
        new_month = 12
        new_year -= 1
    elif new_month == 13:
        new_month = 1
        new_year += 1
    return new_year, new_month

#Calendar ownership functions
User = get_user_model()  #remember what the User model is, so I can query it later

def get_calendar_owner():
    """
    Return the User that "owns" the shared family calendar.

    Priority:
      1) settings.KIOSK_CALENDAR_OWNER_USERNAME (if set and exists)
      2) first superuser (common home-server setup)
      3) first user in DB (last resort)

    Raises:
      RuntimeError if no users exist (fresh DB).
    """
    # 1) If explicitly configured, try it
    username = getattr(settings, "KIOSK_CALENDAR_OWNER_USERNAME", None)
    if username:
        owner = User.objects.filter(username=username).first()
        if owner:
            return owner

    # 2) Fallback: first superuser (works on wall tablet + admin setups)
    owner = User.objects.filter(is_superuser=True).order_by("id").first()
    if owner:
        return owner

    # 3) Final fallback: first user
    owner = User.objects.order_by("id").first()
    if owner:
        return owner

    raise RuntimeError(
        "No users exist in this database. Create a superuser with: python manage.py createsuperuser"
    )

#Health / Fragments
@require_GET
def health_ping(request):
    """
    Lightweight heartbeat endpoint for kiosk/tablet clients.

    Used by client-side polling to detect when the server is reachable again.
    Returns HTTP 200 with JSON {"ok": true}.
    """
    return JsonResponse({"ok": True})

@require_GET
def weather_fragment(request):
    """
    AJAX endpoint used by the kiosk/tablet to refresh only the weather UI.

    Returns JSON:
      { ok: true, html: "<rendered partial>" }

    The template rendered here MUST be a fragment (no {% extends %}).
    """
    weather_ctx = get_cached_weather()
    html = render_to_string("partials/_weather_block.html", weather_ctx, request=request)
    return JsonResponse({"ok": True, "html": html})

#Calendar Views
def calendar_entry(request):
    """
    Router entry-point:
      - tablet -> week view in kiosk mode
      - server -> month view
    """
    today = timezone.localdate().strftime("%Y-%m-%d")

    if looks_like_tablet(request):
        url = reverse("calendar:calendar_week")
        return redirect(f"{url}?date={today}&kiosk=1")

    url = reverse("calendar:calendar_month")
    d = timezone.localdate()
    return redirect(f"{url}?y={d.year}&m={d.month}")

@ensure_csrf_cookie
def main_calendar(request):
    """
    Calendar home screen.

    - Loads rotating background images from static (kiosk-friendly “photo frame”)
    - Loads cached weather context for the weather overlay
    - Shows a small "today" summary list (today_events) for quick glance
    - Adds kiosk context flags so base.html can hide/show kiosk UI
    """
    
    # image directory for calendar page backgrounds
    # 1. Get the absolute path to your static images folder
    photos_dir = Path(settings.BASE_DIR) / "static" / "budget" / "calendar_photos"
         
    # match jpg/JPG/jpeg/JPEG (and optionally png)
    exts = {".jpg", ".jpeg", ".png"}
    image_files = []
    if photos_dir.exists():
        image_files = [p for p in photos_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]

    # Convert to STATIC-relative paths for `{% static ... %}`
    image_list = [f"budget/calendar_photos/{p.name}" for p in image_files]

    weather_ctx = get_cached_weather()

    # Pass daily events to template
    owner = get_calendar_owner()  # same owner logic you're using elsewhere
    today = timezone.localdate()
    start_dt = timezone.make_aware(datetime.combine(today, time.min))
    end_dt = timezone.make_aware(datetime.combine(today, time.max))

    today_events = (CalendarEvent.objects
        .filter(user=owner, start_dt__lte=end_dt, end_dt__gte=start_dt)
        .order_by("start_dt"))
    
   # Build a 7-day strip starting Sunday
    start = today - timedelta(days=(today.weekday() + 1) % 7)  # Sunday start
    end = start + timedelta(days=6)

    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        days.append({"date": d, "is_today": d == today})

    start_dt = timezone.make_aware(datetime.combine(start, time.min))
    end_dt = timezone.make_aware(datetime.combine(end, time.max))

    week_events = (CalendarEvent.objects
        .filter(user=owner, start_dt__lte=end_dt, end_dt__gte=start_dt)
        .order_by("start_dt")
    )

    events_by_date = defaultdict(list)
    tz = timezone.get_current_timezone()

    for ev in week_events:
        ev_start = ev.start_dt.astimezone(tz).date()
        ev_end = ev.end_dt.astimezone(tz).date()

        d = max(ev_start, start)
        last = min(ev_end, end)

        while d <= last:
            events_by_date[d].append(ev)
            d += timedelta(days=1)

    # Optional: keep today_events for your agenda section
    today_events = events_by_date.get(today, [])
           
    context = {
    "image_list": image_list if image_list else [],
    "today_events": today_events,
    "today": today,
    "days": days,
    "events_by_date": dict(events_by_date),
    "owner": owner,
    **weather_ctx,
    }

    return render(request, 'calendar/calendar_home.html', context)

@ensure_csrf_cookie
def calendar_month(request):
    """
    Month grid view.

    Query params:
      - y=YYYY, m=1..12 (defaults to current month)

    Behavior:
      - Builds a Sunday→Saturday calendar grid range (grid_start/grid_end)
      - Fetches events overlapping the grid range
      - Groups them into `events_by_day` keyed by date
      - Injects specials so they display first on each day
      - Builds `weeks` as a list of 7-day date arrays for the template
      - Groups by local start date (timezone.localtime).
    """
    # pick month/year from querystring or default to current
    today = timezone.localdate()
    owner = get_calendar_owner()

    try:
        year = int(request.GET.get("y", today.year))
    except (TypeError, ValueError):
        year = today.year
    
    try:
        month = int(request.GET.get("m", today.month))
    except (TypeError, ValueError):
        month = today.month

    if month < 1 or month > 12:
        month = today.month

    prev_y, prev_m = add_month(year, month, -1)
    next_y, next_m = add_month(year, month, +1)

    first_day = date(year, month, 1)
    _, last_day_num = monthrange(year, month)
    last_day = date(year, month, last_day_num)

    # build grid start (Sunday) -> grid end (Saturday)
    grid_start = first_day - timedelta(days=(first_day.weekday() + 1) % 7)
    grid_end = last_day + timedelta(days=(6 - ((last_day.weekday() + 1) % 7)))

    events = get_events_overlapping_range(owner, grid_start, grid_end)

    # group by date for easy template rendering
    events_by_day = group_events_by_start_date(events)

    inject_specials_into_events_by_day(events_by_day, grid_start, grid_end)

    # build list of weeks (each week is 7 dates)
    weeks = build_weeks(grid_start, grid_end)

    context = {
        "today": today,
        "weeks": weeks,
        "events_by_day": events_by_day,
        "year": year,
        "month": month,
        "prev_y": prev_y, "prev_m": prev_m,
        "next_y": next_y, "next_m": next_m,
    }
    
    return render(request, "calendar/calendar_month.html", context)

@ensure_csrf_cookie
def calendar_week(request):
    """
    Week list view (Sunday → Saturday).

    Query params:
      - date=YYYY-MM-DD (defaults to today; used to choose the week)

    Behavior:
      - Computes week_start/week_end with Sunday as first day
      - Groups overlapping events by local start date into `events_by_day`
      - Injects specials (fixed + rule-based) into events_by_day so templates
        can render them at the top of each day.
      - Groups by local start date into `events_by_day`
    """
    today = timezone.localdate()
    owner = get_calendar_owner()

    day = parse_ymd(request.GET.get("date"), default=today)         # context day defaults to today

    # Make Sunday the first day of the week
    # Python weekday(): Mon=0..Sun=6
    # We want an offset where Sun -> 0, Mon -> 1, ... Sat -> 6
    sunday_offset = (day.weekday() + 1) % 7
    week_start = day - timedelta(days=sunday_offset)
    week_end = week_start + timedelta(days=6)

    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    events = get_events_overlapping_range(owner, week_start, week_end)

    # group events by date
    events_by_day = group_events_by_start_date(events)

    days = [week_start + timedelta(days=i) for i in range(7)]

    inject_specials_into_events_by_day(events_by_day, week_start, week_end)
    
    context = {
        "today": today,
        "day": day,  # handy for links
        "week_start": week_start,
        "week_end": week_end,
        "prev_week": prev_week,
        "next_week": next_week,
        "days": days,
        "events_by_day": events_by_day,
        
        }

    return render(request, "calendar/calendar_week.html", context)

@ensure_csrf_cookie
def calendar_day(request):
    """
    Day view (timeline).

    Query params:
      - date=YYYY-MM-DD (defaults to today)

    Behavior:
      - Fetches events that overlap the day (start<=end_of_day AND end>=start_of_day)
      - Splits all-day vs timed events
      - Builds `event_blocks` with pixel offsets (1px/minute) and overlap columns
      - Builds `special_items` (fixed + rule-based) displayed at top
      - Adds kiosk context so links can preserve kiosk=1 if needed
    """
    today = timezone.localdate()
    owner = get_calendar_owner()
    
    day = parse_ymd(request.GET.get("date"), default=today)     # default context day = today
    
    start_dt = timezone.make_aware(datetime.combine(day, time.min))
    end_dt = timezone.make_aware(datetime.combine(day, time.max))

    prev_day = day - timedelta(days=1)
    next_day = day + timedelta(days=1)

    events = (CalendarEvent.objects
              .filter(user=owner, start_dt__lte=end_dt, end_dt__gte=start_dt)
              .order_by("start_dt"))
    
    #build grid for display in html
    all_day_events, event_blocks = build_day_timeline_blocks(events, day)

    # special day handling
    special_items = get_special_items_for_day(day)

    context = {
        "day": day,
        "today": today,
        "prev_day": prev_day,
        "next_day": next_day,
        "events": events,               # keep if you want for lists / all-day
        "all_day_events": all_day_events,
        "event_blocks": event_blocks,         # for grid
        "hours": range(24),
        "special_items": special_items,
    }

    return render(request, "calendar/calendar_day.html", context)

#Event CRUD
def calendar_event_detail(request, event_id):
    owner = get_calendar_owner()
    event = get_object_or_404(CalendarEvent, id=event_id, user=owner)

    is_kiosk = kiosk_enabled(request)
    default_return = calendar_home_url(is_kiosk)
    return_to = request.GET.get("return_to") or default_return

    context = {
        "event": event,
        "return_to": return_to,
    }
    
    return render(request, "calendar/calendar_event_detail.html", context)

@ensure_csrf_cookie
@kiosk_edit_required
def calendar_event_create(request):
    owner = get_calendar_owner()

    is_kiosk = kiosk_enabled(request)

    default_return = calendar_home_url(is_kiosk)
    return_to = request.GET.get("return_to") or default_return

    # date prefill: ?date=YYYY-MM-DD
    date_str = request.GET.get("date")
    default_date = timezone.localdate()
    if date_str:
        try:
            default_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    if request.method == "POST":
        # IMPORTANT: for POST, take return_to from the hidden input first
        return_to = request.POST.get("return_to") or return_to

        title = (request.POST.get("title") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        location = (request.POST.get("location") or "").strip()
        person = request.POST.get("person", "mike")
        all_day = request.POST.get("all_day") == "on"

        if not title:
            context = {"date": default_date, "return_to": return_to, "event": None, "error": "Title is required."}
            return render(request, "calendar/calendar_event_form.html", context)

        if all_day:
            start_dt = timezone.make_aware(datetime.combine(default_date, time.min))
            end_dt = timezone.make_aware(datetime.combine(default_date, time.max))
        else:
            start_time = request.POST.get("start_time", "09:00")
            end_time = request.POST.get("end_time", "10:00")

            try:
                st = datetime.strptime(start_time, "%H:%M").time()
                et = datetime.strptime(end_time, "%H:%M").time()
            except ValueError:
                context = {"date": default_date, "return_to": return_to, "event": None, "error": "Invalid time format."}
                return render(request, "calendar/calendar_event_form.html", context)

            if et <= st:
                return render(request, "calendar/calendar_event_form.html", {
                    "date": default_date,
                    "return_to": return_to,
                    "error": "End time must be after start time.",
                    "event": event,
                })

            start_dt = timezone.make_aware(datetime.combine(default_date, st))
            end_dt = timezone.make_aware(datetime.combine(default_date, et))

        event = CalendarEvent.objects.create(
            user=owner,
            title=title,
            person=person,
            start_dt=start_dt,
            end_dt=end_dt,
            all_day=all_day,
            notes=notes,
            location=location,
        )

        actor = edit_actor(request)
        event.created_by = actor
        event.last_edited_by = actor
        event.save(update_fields=["created_by", "last_edited_by"])

        return redirect(return_to)

    # GET
    context = {"date": default_date, "return_to": return_to, "event": None}
    return render(request, "calendar/calendar_event_form.html", context)

@ensure_csrf_cookie
@kiosk_edit_required
def calendar_event_edit(request, event_id):
    owner = get_calendar_owner()
    event = get_object_or_404(CalendarEvent, id=event_id, user=owner)
    return_to = request.GET.get("return_to") or default_return


    is_kiosk = kiosk_enabled(request)
    default_return = calendar_home_url(is_kiosk)
    
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        notes = request.POST.get("notes", "").strip()
        location = request.POST.get("location", "").strip()
        person = request.POST.get("person", "mike")
        all_day = request.POST.get("all_day") == "on"
        return_to = request.POST.get("return_to") or default_return

        if not title:
            return render(request, "calendar/calendar_event_form.html", {
                "date": event.start_dt.date(),
                "return_to": return_to,
                "error": "Title is required.",
                "event": event,
            })
        
        # date is locked for MVP; we can add change-date later
        d = event.start_dt.date()

        if all_day:
            start_dt = timezone.make_aware(datetime.combine(d, time.min))
            end_dt = timezone.make_aware(datetime.combine(d, time.max))
        else:
            try:
                st = datetime.strptime(request.POST.get("start_time", "09:00"), "%H:%M").time()
                et = datetime.strptime(request.POST.get("end_time", "10:00"), "%H:%M").time()
            except ValueError:
                context = {"date": start_dt, "return_to": return_to, "event": None, "error": "Invalid time format."}
                return render(request, "calendar/calendar_event_form.html", context)

            if et <= st:
                return render(request, "calendar/calendar_event_form.html", {
                    "date": d,
                    "return_to": request.POST.get("return_to", "/calendar/"),
                    "error": "End time must be after start time.",
                    "event": event,
                })
            start_dt = timezone.make_aware(datetime.combine(d, st))
            end_dt = timezone.make_aware(datetime.combine(d, et))

        event.title = title
        event.notes = notes
        event.location = location
        event.person = person
        event.all_day = all_day
        event.start_dt = start_dt
        event.end_dt = end_dt
        if not event.created_by:
            event.created_by = edit_actor(request)
        event.last_edited_by = edit_actor(request)

        event.save()

        return redirect(request.POST.get("return_to", "/calendar/"))
    
    context = {
        "date": event.start_dt.date(),
        "return_to": request.GET.get(return_to) or default_return,
        "event": event,
        }
    
    return render(request, "calendar/calendar_event_form.html", context)

@ensure_csrf_cookie
@kiosk_edit_required
def calendar_event_delete(request, event_id):
    owner = get_calendar_owner()
    event = get_object_or_404(CalendarEvent, id=event_id, user=owner)

    is_kiosk = kiosk_enabled(request)

    default_return = calendar_home_url(is_kiosk)
    return_to = request.GET.get("return_to") or default_return

    if request.method == "POST":
        event.delete()
        return redirect(request.POST.get("return_to") or default_return)
    
    context = {
        "event": event,
        "return_to": return_to,
    }

    return render(request, "calendar/calendar_event_delete.html", context)      

#Kiosk Actions
def kiosk_unlock_page(request):
    """
    Shows the PIN entry page (GET).
    The actual unlock happens in kiosk_unlock() via POST.
    """
    is_kiosk = kiosk_enabled(request)
    default_return = calendar_home_url(is_kiosk)
    return_to = request.GET.get("return_to") or default_return

    context = {
        "return_to": return_to,
        "error": request.GET.get("error", ""),
        "hide_kiosk_bar": True,
    }
   
    return render(request, "calendar/kiosk_unlock.html", context)

def kiosk_unlock(request):
    if request.method != "POST":
        return JsonResponse({"ok": False}, status=405)

    pin = (request.POST.get("pin") or "").strip()
    return_to = request.POST.get("return_to") or "/calendar/"

    pins = getattr(settings, "KIOSK_PINS", {})
    matched_key = None
    for key, configured_pin in pins.items():
        if pin == str(configured_pin):
            matched_key = key
            break

    if not matched_key:
        context = {"error": "Invalid PIN.", "return_to": return_to}
        return render(request, "calendar/kiosk_unlock.html", context, status=403)

    mins = int(getattr(settings, "KIOSK_UNLOCK_MINUTES", 10))
    until = timezone.now() + timedelta(minutes=mins)

    request.session["kiosk_unlocked_until"] = until.isoformat()
    request.session["kiosk_unlocked_by"] = matched_key  # ✅ KEEP THIS

    if "kiosk=1" not in return_to:
        joiner = "&" if "?" in return_to else "?"
        return_to = f"{return_to}{joiner}kiosk=1"

    return redirect(return_to)

@require_POST
def kiosk_lock(request):
    request.session.pop("kiosk_unlocked_until", None)
    request.session.pop("kiosk_unlocked_by", None)
    request.session.modified = True
    return JsonResponse({"ok": True})
    


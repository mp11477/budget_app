from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as dateformat 
from django.utils.dateparse import parse_datetime

from functools import wraps

from .devices import looks_like_tablet

#Kiosk state + permissions 
def kiosk_enabled(request) -> bool:
    """
    Determine whether this request is in kiosk mode.

    Rules:
      - ?kiosk=1 turns kiosk mode on and persists via session
      - ?kiosk=0 turns it off and persists via session
      - First-time tablet UA defaults to kiosk mode
    """
    if request.GET.get("kiosk") == "1":
        request.session["kiosk_enabled"] = True
        return True

    if request.GET.get("kiosk") == "0":
        request.session["kiosk_enabled"] = False
        return False

    if "kiosk_enabled" not in request.session and looks_like_tablet(request):
        request.session["kiosk_enabled"] = True

    return bool(request.session.get("kiosk_enabled", False))

def kiosk_is_unlocked(request):
    """
    Return True if the kiosk is currently unlocked for editing.

    Unlock state is stored in session:
      - kiosk_unlocked_until (ISO datetime)
      - kiosk_unlocked_by (who unlocked)
    """
    until_str = request.session.get("kiosk_unlocked_until")
    if not until_str:
        return False

    until = parse_datetime(until_str)
    if until is None:
        return False

    if timezone.is_naive(until):
        until = timezone.make_aware(until)

    return timezone.now() < until

def can_user_edit(request):
    """
    Editing rules:
      - Non-kiosk (server) always editable
      - Kiosk/tablet requires unlock window to be active
    """
    # Server (not kiosk) = always editable
    if not kiosk_enabled(request):
        return True

    # Tablet kiosk = only editable if unlocked
    return kiosk_is_unlocked(request)

def edit_actor(request) -> str:
    """
    Tag the source of edits for audit/debug:

      - 'server' when not kiosk
      - kiosk key (e.g., 'mike', 'wife') when unlocked on tablet
      - 'kiosk' fallback if unlocked_by is missing
    """
    # Server edits: not kiosk => "server"
    if not kiosk_enabled(request):
        return "server"

    # Kiosk edits: whoever unlocked (mike/wife)
    return request.session.get("kiosk_unlocked_by") or "kiosk"

def kiosk_context(request):
    is_kiosk = kiosk_enabled(request)
    by = request.session.get("kiosk_unlocked_by", "N/A")
    labels = getattr(settings, "KIOSK_PIN_LABELS", {})
    label = labels.get(by, by)

    until_str = request.session.get("kiosk_unlocked_until")
    until_disp = None
    if until_str:
        until = parse_datetime(until_str)
        if until and timezone.is_naive(until):
            until = timezone.make_aware(until)
        if until:
            until_disp = dateformat(timezone.localtime(until), "g:i A") #e.g. "3:45 PM"
    
    return {
        "is_kiosk": is_kiosk,
        "kiosk_qs": "kiosk=1" if is_kiosk else "",
        "kiosk_qs_prefix": "?kiosk=1" if is_kiosk else "",
        "kiosk_qs_amp": "&kiosk=1" if is_kiosk else "",
        "can_edit": can_user_edit(request),
        "kiosk_unlocked_by": by,
        "kiosk_unlocked_label": label,
        "kiosk_unlocked_until_display": until_disp,
    }

def kiosk_edit_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not can_user_edit(request):
            # Optional: preserve kiosk=1 when redirecting
            if kiosk_enabled(request):
                url = reverse("calendar:calendar_home")
                return redirect(f"{url}?kiosk=1")
            return redirect("calendar:calendar_month")
        return view_func(request, *args, **kwargs)
    return _wrapped

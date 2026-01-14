from __future__ import annotations

from typing import Dict, Any

from .permissions import kiosk_context


def calendar_ui(request) -> Dict[str, Any]:
    """
    Global calendar UI context available to templates.

    Provides kiosk/tablet state and edit permissions in a consistent way so
    templates can preserve kiosk querystring params and show/hide edit controls.

    This intentionally does NOT include view-specific data (events, weeks, etc.).
    """
    return kiosk_context(request)
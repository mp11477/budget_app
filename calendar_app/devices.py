def looks_like_tablet(request) -> bool:
    ua = (request.META.get("HTTP_USER_AGENT") or "").lower()

    # obvious tablets
    if any(x in ua for x in ["ipad", "android"]) and "mobile" not in ua:
        return True

    # common kiosk/tablet browsers
    if any(x in ua for x in ["silk/", "kindle", "tablet"]):
        return True

    return False
from __future__ import annotations

from collections import defaultdict, Counter
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone as dj_timezone

import requests

CACHE_KEY = "weather:v4"
CACHE_SECONDS = 5 * 60  # 5 minutes

def degrees_to_cardinal(degrees):
    """
    Convert wind direction in degrees (0..360) into one of 16 compass directions.

    Examples:
        0   -> N
        90  -> E
        180 -> S
        270 -> W

    Uses 16-wind compass rose:
        N, NNE, NE, ENE, E, ESE, SE, SSE, S, SSW, SW, WSW, W, WNW, NW, NNW
    """
    if degrees is None:
        degrees = 0

    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
    ]
    # The degree range for each direction is 360 / 16 = 22.5 degrees.
    # We add 11.25 to shift the boundary so North is centered around 0 degrees,
    # then use modulo 360 to handle values outside the 0-360 range,
    # and finally integer division to get the index.
    index = int((degrees + 11.25) % 360 // 22.5)
    return directions[index]

def weather_api_error(error, coordinates):
    """
    Convert an OpenWeather HTTP status code into a human-friendly error string.

    Args:
        error: HTTP status code from OpenWeather (e.g., 401, 404, 429)
        coordinates: the query string used (for 404 messages)

    Returns:
        A display-safe string for templates/logs.
    """
    if error == 401:
        # 401: Unauthorized/Invalid API Key
        status = "Error 401: Inv API key or unauthorized request."
     
    elif error == 404:
        # 404: Loc coordinates Not Found
        status = f"Error 404: Location '{coordinates}' not found by API."

    elif error == 429:
        # 429: Too Many Requests
        status = "Error 429: Rate limit exceeded.  Try again in 10 minutes."
               
    elif error >= 400 and error < 500:
        # General Client Error
        status = f"Client Error: {error}.  Check your request parameters."
       
    elif error >= 500:
        # Server Error
        status = f"Server Error: {error} - The weather service is down."
        
    else:
        # Any other status code
        status = f"Unexpected Error: Status Code {error}"
            
    return status

def get_cached_weather() -> Dict[str, Any]:
    """
    Return cached weather context if available; otherwise fetch and cache it.

    Why:
        The calendar home page hits weather frequently (page loads + periodic AJAX refresh).
        Caching prevents excessive OpenWeather calls and speeds up render.

    Cache behavior:
        - Key: CACHE_KEY ("weather:v1")
        - TTL: CACHE_SECONDS (default 5 minutes)
    """
    cached = cache.get(CACHE_KEY)

    try:
        fresh = fetch_weather_context()
        # defensive copy + debug flag
        fresh = dict(fresh)
        fresh["cache_hit"] = False

        cache.set(CACHE_KEY, fresh, timeout=CACHE_SECONDS)
        return fresh

    except Exception as e:
        if cached is not None:
            stale = dict(cached)
            stale["cache_hit"] = True
            stale["stale_due_to_error"] = str(e)
            return stale

        raise  # no cache and fetch failed; propagate

def fetch_weather_context() -> Dict[str, Any]:
    """
    Fetch current weather (OpenWeather) + daily 5-day cards (NWS),
    and enrich daily cards with OpenWeather-derived precip details when available.

    Why two providers?
      - OpenWeather /forecast is 3-hour timesteps and is NOT a true daily high/low,
        especially for 'today' later in the day.
      - NWS provides true daily min/max directly (free, no key).

    Return keys (always present):
      - current_temperature, current_temperature_display, weather_icon, feels_like,
        description, humidity, wind_display, wind_deg_to, precipitation_1h,
        weather_error, forecast_status, forecast_list, weather_updated_at
    """
    api_key = getattr(settings, "OPENWEATHER_API_KEY", None)
    lat = getattr(settings, "LAT", None)
    lon = getattr(settings, "LON", None)

    # Safe defaults FIRST
    ctx: Dict[str, Any] = {
        "current_temperature": "N/A",
        "current_temperature_display": "N/A",
        "weather_icon": "",
        "feels_like": "N/A",
        "description": "N/A",
        "humidity": "N/A",
        "wind_speed": "N/A",
        "wind_direction": "N/A",
        "wind_display": "N/A",
        "wind_deg_to": 0,
        "precipitation_1h": 0,
        "weather_error": "",
        "forecast_status": "",
        "forecast_list": [],
        "weather_updated_at": "",
    }

    if lat is None or lon is None:
        ctx["weather_error"] = "Weather is not configured (LAT/LON missing)."
        return ctx

    # 1) Daily forecast (authoritative highs/lows) – NWS
    try:
        nws_cards = fetch_daily_forecast_nws(float(lat), float(lon), days=5)
    except Exception as e:
        ctx["forecast_status"] = f"Daily forecast error (NWS): {e}"
        nws_cards = []

    # 2) Optional enrich daily cards – OpenWeather slots (icons/precip)
    # This does NOT set highs/lows.
    try:
        ow_extras = fetch_openweather_daily_extras(float(lat), float(lon))
        cards = merge_daily_forecasts(nws_cards, ow_extras)
    except Exception as e:
        # Non-fatal – your cards still render from Open-Meteo.
        if not ctx["forecast_status"]:
            ctx["forecast_status"] = f"Forecast extras error (OpenWeather): {e}"

    ctx["forecast_list"] = cards

    # 3) Current conditions – OpenWeather (only if api_key exists)
    if not api_key:
        ctx["weather_error"] = "Weather is not configured (OPENWEATHER_API_KEY missing)."
        ctx["weather_updated_at"] = dj_timezone.localtime().strftime("%I:%M %p")
        return ctx

    try:
        apply_openweather_current(ctx, api_key, lat, lon)
    except Exception as e:
        ctx["weather_error"] = f"Current weather error: {e}"

    ctx["weather_updated_at"] = dj_timezone.localtime().strftime("%I:%M %p")
    return ctx

def apply_openweather_current(ctx: Dict[str, Any], api_key: str, lat: Any, lon: Any) -> None:
    """Mutates ctx with current conditions from OpenWeather."""
    coords = f"?lat={lat}&lon={lon}"
    weather_url = f"https://api.openweathermap.org/data/2.5/weather{coords}&appid={api_key}&units=imperial"

    r = requests.get(weather_url, timeout=8)
    if r.status_code != 200:
        ctx["weather_error"] = weather_api_error(r.status_code, coords)
        return

    w = r.json()
    temp_val = w.get("main", {}).get("temp")
    temp = "N/A" if temp_val is None else round(temp_val)

    ctx["current_temperature"] = temp
    ctx["current_temperature_display"] = f"{temp}°F" if temp != "N/A" else "N/A"
    ctx["feels_like"] = f'{round(w["main"]["feels_like"])}°F'
    ctx["description"] = (w["weather"][0]["description"] or "").capitalize()

    icon = w["weather"][0]["icon"]
    ctx["weather_icon"] = f'https://openweathermap.org/img/wn/{icon}@2x.png'
    
    ctx["humidity"] = f'{w["main"]["humidity"]}%'

    ctx["wind_speed"] = f'{w["wind"]["speed"]}'
    deg = w["wind"].get("deg", 0)

    ctx["wind_direction"] = degrees_to_cardinal(deg)
    ctx["wind_gust"] = w["wind"].get("gust", "N/A")
    ctx["wind_display"] = f"From the {ctx['wind_direction']} @ {ctx['wind_speed']} mph, gusting to {ctx['wind_gust']} mph."
    ctx["wind_deg_to"] = (deg + 180) % 360

    precip_1hr = w.get("rain", {}).get("1h", 0) + w.get("snow", {}).get("1h", 0)
    ctx["precipitation_1h"] = round(float(precip_1hr or 0), 2)

def fetch_openweather_daily_extras(lat: float, lon: float) -> Dict[str, Dict[str, Any]]:
    """
    Uses OpenWeather 3-hour forecast to derive per-day *extras* (not high/low):
      - representative day icon
      - description
      - optional precip slot (icon + kind + time_of_day + pop)

    Returns:
      dict keyed by date string 'YYYY-MM-DD'
      {
        "2026-02-08": {
           "icon": "...",
           "description": "...",
           "precip": {...} or None
        },
        ...
      }
    """
    api_key = getattr(settings, "OPENWEATHER_API_KEY", None)
    if not api_key:
        return {}

    coords = f"?lat={lat}&lon={lon}"
    forecast_url = f"https://api.openweathermap.org/data/2.5/forecast{coords}&appid={api_key}&units=imperial"

    fr = requests.get(forecast_url, timeout=8)
    fr.raise_for_status()
    f = fr.json()

    daily: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    local_tz = dj_timezone.get_current_timezone()

    for item in f.get("list", []):
        ts = item.get("dt")
        if not ts:
            continue

        dt_local = datetime.fromtimestamp(ts, tz=dt_timezone.utc).astimezone(local_tz)
        date_key = dt_local.strftime("%Y-%m-%d")
        time_str = dt_local.strftime("%H:%M:%S")

        weather0 = (item.get("weather") or [{}])[0]
        daily[date_key].append({
            "time": time_str,
            "pop": float(item.get("pop", 0) or 0),
            "icon": weather0.get("icon", ""),
            "desc": (weather0.get("description") or "").lower(),
        })

    precip_words = ("rain", "snow", "sleet", "storm", "thunder", "drizzle")

    extras: Dict[str, Dict[str, Any]] = {}
    for date_key, slots in daily.items():
        if not slots:
            continue

        # representative icon from daytime where possible
        daytime = [s for s in slots if 9 <= int(s["time"][:2]) <= 18]
        icon_source = daytime if daytime else slots
        icon = Counter(s["icon"] for s in icon_source).most_common(1)[0][0]
        day_icon = f'https://openweathermap.org/img/wn/{icon}@2x.png'
        
        # description from mid-slot
        mid_slot = icon_source[len(icon_source) // 2]
        day_desc = (mid_slot.get("desc") or "").capitalize()

        # precip slot: highest POP among precip-like descriptions
        precip_slots = [
            s for s in slots
            if s["pop"] > 0 and any(w in (s.get("desc") or "") for w in precip_words)
        ]
        best = max(precip_slots, key=lambda s: s["pop"]) if precip_slots else None

        precip_info = None

        if best:
            kind = precip_kind(best.get("desc") or "")
            precip_info = {
                "pop": int(round(best["pop"] * 100)),
                "time_of_day": time_to_daypart(best["time"]),
                "kind": kind,
                "icon": f'https://openweathermap.org/img/wn/{best["icon"]}@2x.png',
                "desc": (best.get("desc") or "").capitalize(),
            }

        extras[date_key] = {
            "icon": day_icon,
            "description": day_desc,
            "precip": precip_info,
        }

    return extras

def time_to_daypart(time_str: str) -> str:
    h = int((time_str or "0").split(":")[0])
    if 0 <= h < 6:
        return "Early AM"
    if 6 <= h < 12:
        return "AM"
    if 12 <= h < 18:
        return "PM"
    return "Late PM"

def merge_daily_forecasts(
    daily_cards: List[Dict[str, Any]],
    extras_by_date: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Merge OpenWeather-derived extras onto NWS daily cards.

    NWS drives:
      - temp_high/temp_low/pop/date/day_label

    OpenWeather overrides (for readability at small size):
      - icon/description
    And optionally adds:
      - precip (pop/kind/time_of_day/icon)
    """
    out: List[Dict[str, Any]] = []
    for card in daily_cards:
        # NWS 'date' in your card is "MM-DD-YYYY". Convert back to YYYY-MM-DD for matching.
        dt = datetime.strptime(card["date"], "%m-%d-%Y")
        key = dt.strftime("%Y-%m-%d")

        extras = extras_by_date.get(key, {})
        
        merged = {**card, **extras}

        # ensure keys exist for template safety
        merged.setdefault("icon", "")
        merged.setdefault("description", "")
        merged.setdefault("precip", None)
                      
        merged.setdefault("description", extras.get("description", ""))
    
        out.append(merged)

    return out

def precip_kind(desc: str) -> str:
    d = (desc or "").lower()
    if "snow" in d: return "Snow"
    if "sleet" in d: return "Sleet"
    if "drizzle" in d: return "Drizzle"
    if "thunder" in d or "storm" in d: return "Storm"
    if "rain" in d: return "Rain"
    return "Precip"

def fetch_daily_forecast_nws(lat: float, lon: float, days: int = 5) -> List[Dict[str, Any]]:
    """
    NWS (api.weather.gov) daily forecast, no API key required (US only).

    Returns list of dicts compatible with your forecast cards:
      - date: "MM-DD-YYYY"
      - day_label: "Mon"
      - temp_high: int
      - temp_low: int
      - pop: int (0-100)
      - icon: str (URL)
      - description: str

    Notes:
      - NWS forecasts are returned as "periods" (Day / Night). We pair them by date.
      - You MUST send a User-Agent header per NWS guidance (include app + contact).
    """
    headers = {
        "User-Agent": getattr(settings, "NWS_USER_AGENT", "BudgetAppCalendar/1.0 (admin@example.com)"),
        "Accept": "application/geo+json",
    }

    # 1) Resolve gridpoint forecast URL for this lat/lon
    points_url = f"https://api.weather.gov/points/{lat},{lon}"
    pr = requests.get(points_url, headers=headers, timeout=10)
    pr.raise_for_status()
    props = pr.json()["properties"]

    forecast_url = props["forecast"]  # general forecast (periods)
    fr = requests.get(forecast_url, headers=headers, timeout=10)
    fr.raise_for_status()
    periods = fr.json()["properties"]["periods"]

    # 2) Pair day/night by local date
    by_date: Dict[str, Dict[str, Any]] = {}

    for p in periods:
        # startTime is ISO8601
        start = datetime.fromisoformat(p["startTime"].replace("Z", "+00:00"))
        date_key = start.date().isoformat()

        entry = by_date.setdefault(date_key, {
            "date": start.strftime("%m-%d-%Y"),
            "day_label": start.strftime("%a"),
            "temp_high": None,
            "temp_low": None,
            "pop": 0,
            "icon": "",
            "description": "",
        })

        temp = p.get("temperature")
        is_day = bool(p.get("isDaytime"))

        pop_obj = p.get("probabilityOfPrecipitation") or {}
        pop_val = pop_obj.get("value")
        if pop_val is not None:
            entry["pop"] = max(entry["pop"], int(pop_val))

        # Prefer daytime icon/summary for the card
        if is_day and p.get("icon"):
            entry["icon"] = p["icon"]
            entry["description"] = (p.get("shortForecast") or "").strip()

        if temp is None:
            continue

        if is_day:
            entry["temp_high"] = int(temp)
        else:
            entry["temp_low"] = int(temp)

    # 3) Build ordered list and fill any missing hi/lo conservatively
    out: List[Dict[str, Any]] = []
    for date_key in sorted(by_date.keys())[:days]:
        e = by_date[date_key]

        # If one side missing (sometimes happens), fall back to available temp
        if e["temp_high"] is None and e["temp_low"] is not None:
            e["temp_high"] = e["temp_low"]
        if e["temp_low"] is None and e["temp_high"] is not None:
            e["temp_low"] = e["temp_high"]

        # Template safety
        e["temp_high"] = int(e["temp_high"] or 0)
        e["temp_low"] = int(e["temp_low"] or 0)
        e.setdefault("icon", "")
        e.setdefault("description", "")
        e.setdefault("precip", None)  # keep your existing template checks happy

        out.append(e)

    return out

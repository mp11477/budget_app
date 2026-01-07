from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

CACHE_KEY = "weather:v1"
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
    if cached is not None:
        return cached

    data = fetch_weather_context()
    cache.set(CACHE_KEY, data, timeout=CACHE_SECONDS)
    return data

def fetch_weather_context() -> Dict[str, Any]:
    """
    Fetch current weather + forecast from OpenWeather and return a context dict.

    Guarantees:
        Always returns a dict with the keys the weather template expects,
        even if the API fails or weather is not configured.

    Expected settings:
        OPENWEATHER_API_KEY (str)
        LAT (float/str)
        LON (float/str)

    Returns keys (always present):
        current_temperature, weather_icon, feels_like, description, humidity,
        wind_speed, wind_direction, weather_error,
        forecast_status, forecast_list, weather_updated_at

    Notes:
        - Uses OpenWeather "weather" endpoint for current conditions
        - Uses OpenWeather "forecast" endpoint for 5-day / 3-hour forecast
        - Forecast is collapsed to daily high/low + max precipitation probability (POP)
    """
    api_key = getattr(settings, "OPENWEATHER_API_KEY", None)
    lat = getattr(settings, "LAT", None)
    lon = getattr(settings, "LON", None)

    # Safe defaults (template never breaks)
    ctx: Dict[str, Any] = {
        "current_temperature": "N/A",
        "weather_icon": "",
        "feels_like": "N/A",
        "description": "N/A",
        "humidity": "N/A",
        "wind_speed": "N/A",
        "wind_direction": "N/A",
        "weather_error": "",
        "forecast_status": "",
        "forecast_list": [],
    }

    if not api_key or lat is None or lon is None:
        ctx["weather_error"] = "Weather is not configured."
        return ctx

    coords = f"?lat={lat}&lon={lon}"
    weather_url = f"https://api.openweathermap.org/data/2.5/weather{coords}&appid={api_key}&units=imperial"
    forecast_url = f"https://api.openweathermap.org/data/2.5/forecast{coords}&appid={api_key}&units=imperial"

    # --- Current weather ---
    try:
        r = requests.get(weather_url, timeout=8)
        if r.status_code != 200:
            ctx["weather_error"] = weather_api_error(r.status_code, coords)
        else:
            w = r.json()
            temp = int(w["main"]["temp"])
            ctx["current_temperature"] = f"{temp}°F"
            ctx["feels_like"] = f'{int(w["main"]["feels_like"])}°F'
            ctx["description"] = (w["weather"][0]["description"] or "").capitalize()
            icon = w["weather"][0]["icon"]
            ctx["weather_icon"] = f"https://openweathermap.org/img/wn/{icon}@2x.png"
            ctx["humidity"] = f'{w["main"]["humidity"]}%'
            ctx["wind_speed"] = f'{w["wind"]["speed"]} mph'
            deg = w["wind"].get("deg", 0)
            ctx["wind_direction"] = degrees_to_cardinal(deg)
    except requests.RequestException as e:
        ctx["weather_error"] = f"Network error: {e}"

    # --- Forecast ---
    try:
        fr = requests.get(forecast_url, timeout=8)
        if fr.status_code != 200:
            ctx["forecast_status"] = weather_api_error(fr.status_code, coords)
        else:
            f = fr.json()
            daily = defaultdict(lambda: {"temps": [], "icons": [], "pops": [], "descriptions": []})

            for item in f.get("list", []):
                date_str = item.get("dt_txt", "").split(" ")[0]
                if not date_str:
                    continue
                daily[date_str]["temps"].append(item["main"]["temp"])
                daily[date_str]["pops"].append(item.get("pop", 0))
                daily[date_str]["icons"].append(item["weather"][0]["icon"])
                daily[date_str]["descriptions"].append(item["weather"][0]["description"])

            forecast_list: List[Dict[str, Any]] = []
            for date_str in sorted(daily.keys())[:5]:
                info = daily[date_str]
                high = int(max(info["temps"]))
                low = int(min(info["temps"]))
                pop = int(max(info["pops"]) * 100)
                mid = len(info["icons"]) // 2

                forecast_list.append({
                    "date": datetime.strptime(date_str, "%Y-%m-%d").strftime("%m-%d-%Y"),
                    "temp_high": high,
                    "temp_low": low,
                    "pop": pop,
                    "description": (info["descriptions"][mid] or "").capitalize(),
                    "icon": f"https://openweathermap.org/img/wn/{info['icons'][mid]}@2x.png",
                })

            ctx["forecast_list"] = forecast_list
    except requests.RequestException as e:
        ctx["forecast_status"] = f"Forecast network error: {e}"

    ctx["weather_updated_at"] = timezone.localtime().strftime("%I:%M %p")
    return ctx


from django.urls import reverse

def calendar_home_url(is_kiosk: bool) -> str:
    url = reverse("calendar:calendar_home")
    return f"{url}?kiosk=1" if is_kiosk else url
from django.urls import path
from budget import views  # TEMP: reuse existing view funcs without moving code yet
#from calendar_app import views   ---Turn this on after moving calendar views to calendar_app and deleting from budget---

app_name = "calendar"

urlpatterns = [
    path("", views.main_calendar, name="calendar_home"),  # /calendar/
   
    path("month/", views.calendar_month, name="calendar_month"),
    path("day/", views.calendar_day, name="calendar_day"),
    path("week/", views.calendar_week, name="calendar_week"),

    path("entry/", views.calendar_entry, name="calendar_entry"),  # tablet

    path("kiosk/unlock/", views.kiosk_unlock_page, name="kiosk_unlock_page"),
    path("kiosk/unlock/submit/", views.kiosk_unlock, name="kiosk_unlock"),
    path("kiosk/lock/", views.kiosk_lock, name="kiosk_lock"),

    path("event/new/", views.calendar_event_create, name="calendar_event_create"),
    path("event/<int:event_id>/", views.calendar_event_detail, name="calendar_event_detail"),
    path("event/<int:event_id>/edit/", views.calendar_event_edit, name="calendar_event_edit"),
    path("event/<int:event_id>/delete/", views.calendar_event_delete, name="calendar_event_delete"),

    path("weather/fragment/", views.weather_fragment, name="weather_fragment"),
    path("ping/", views.health_ping, name="health_ping"),
]
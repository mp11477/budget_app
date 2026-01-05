from django.urls import path
from . import views

urlpatterns = [
    path("main_calendar/", views.main_calendar, name="calendar_home"),
    path("calendar/", views.calendar_month, name="calendar_month"),
    path("calendar/day/", views.calendar_day, name="calendar_day"),
    path("calendar/week/", views.calendar_week, name="calendar_week"),

    path("calendar-entry/", views.calendar_entry, name="calendar_entry"), #tablet
    
    path("calendar/kiosk/unlock/", views.kiosk_unlock_page, name="kiosk_unlock_page"),
    path("calendar/kiosk/unlock/submit/", views.kiosk_unlock, name="kiosk_unlock"),
    path("calendar/kiosk/lock/", views.kiosk_lock, name="kiosk_lock"),
   
    path("calendar/event/new/", views.calendar_event_create, name="calendar_event_create"),
    path("calendar/event/<int:event_id>/", views.calendar_event_detail, name="calendar_event_detail"),
    path("calendar/event/<int:event_id>/edit/", views.calendar_event_edit, name="calendar_event_edit"),
    path("calendar/event/<int:event_id>/delete/", views.calendar_event_delete, name="calendar_event_delete"),

    path("calendar/weather/fragment/", views.weather_fragment, name="weather_fragment"),

    path("calendar/ping/", views.health_ping, name="health_ping"),
]
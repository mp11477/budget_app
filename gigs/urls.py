from django.urls import path
from budget import views  # TEMP: keep using existing gig views for now

urlpatterns = [
    path("entry/", views.gig_entry, name="gig_entry"),
    path("summary/", views.gig_summary, name="gig_summary"),
    path("mileage-rate/", views.mileage_rate_settings, name="mileage_rate_settings"),
]
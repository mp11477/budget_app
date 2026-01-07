from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
  
    # Budget app owns these routes
    path("", include("budget.urls")),

    # calendar app owns these routes
    path("calendar/", include("calendar_app.urls")),

    #gigs app owns these routes
    path("gigs/", include("gigs.urls")),

    # Jobtracker app owns these routes
    # path("jobtracker/", include("jobtracker.urls")),
]
    
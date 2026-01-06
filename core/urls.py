from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
  
    # Budget app owns these routes
    path("", include("budget.urls")),

    # calendar app owns these routes
    path("calendar/", include("calendar_app.urls")),
    # path("jobtracker/", include("jobtracker.urls")),
]
    
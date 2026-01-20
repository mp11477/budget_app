from django.urls import path
from . import views

app_name = "jobtracker"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("jobs/", views.jobs_list, name="jobs_list"),
    path("jobs/add/", views.job_create, name="job_create"),
    path("jobs/<int:job_id>/edit/", views.job_edit, name="job_edit"),
    path("jobs/<int:job_id>/", views.job_detail, name="job_detail"),

    path("applications/", views.applications_list, name="applications_list"),
    path("applications/add/", views.application_create, name="application_create"),
    path("jobs/<int:job_id>/applications/add/", views.application_create_for_job, name="application_create_for_job"),
    path("applications/<int:app_id>/", views.application_detail, name="application_detail"),
    path("applications/<int:app_id>/edit/", views.application_edit, name="application_edit"),

    path("companies/add/", views.company_create, name="company_create"),
    path("companies/", views.companies_list, name="companies_list"),
    path("companies/<int:company_id>/", views.company_detail, name="company_detail"),
    path("companies/<int:company_id>/contacts/add/", views.contact_create, name="contact_create"),
]
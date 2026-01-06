from django.contrib import admin
from .models import Company, Contact, Job, Application, Communication


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "title", "email")
    search_fields = ("name", "company__name", "email")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "location", "priority")
    list_filter = ("priority",)
    search_fields = ("title", "company__name", "location")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("job", "status", "applied_date", "next_followup_date")
    list_filter = ("status",)
    search_fields = ("job__title", "job__company__name", "resume_version")


@admin.register(Communication)
class CommunicationAdmin(admin.ModelAdmin):
    list_display = ("application", "when", "method", "inbound", "summary")
    list_filter = ("method", "inbound")
    search_fields = ("summary", "application__job__title", "application__job__company__name")
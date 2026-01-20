from django.contrib import admin
from .models import Company, Contact, Job, Application, Communication


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("name", "website")


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    search_fields = ("name", "email", "phone")
    list_filter = ("company",)
    list_display = ("name", "company", "title", "email", "phone")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    search_fields = ("title", "company__name", "req_id")
    list_filter = ("priority", "company")
    list_display = ("title", "company", "priority", "location", "source")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    search_fields = ("job__title", "job__company__name")
    list_filter = ("status", "applied_date")
    list_display = ("job", "status", "applied_date", "next_followup_date", "last_contact_date")


@admin.register(Communication)
class CommunicationAdmin(admin.ModelAdmin):
    search_fields = ("summary", "application__job__title", "application__job__company__name")
    list_filter = ("method", "inbound")
    list_display = ("when", "method", "inbound", "application", "summary")
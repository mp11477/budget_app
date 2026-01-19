from django.contrib import admin
from .models import GigCompany, GigShift, GigCompanyEntry


@admin.register(GigCompany)
class GigCompanyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "payout_account")
    search_fields = ("code", "name")

@admin.register(GigShift)
class GigShiftAdmin(admin.ModelAdmin):
    list_display = ("date", "start_time", "end_time", "miles")
    list_filter = ("date",)

@admin.register(GigCompanyEntry)
class GigCompanyEntryAdmin(admin.ModelAdmin):
    list_display = ("shift", "company", "deliveries", "gross_earnings")
    list_filter = ("company",)
from django.contrib import admin
from .models import CalendarSpecial, CalendarRuleSpecial

@admin.register(CalendarSpecial)
class CalendarSpecialAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "special_type", "person", "recurring_yearly")
    list_filter = ("special_type", "person", "recurring_yearly")
    search_fields = ("title",)

@admin.register(CalendarRuleSpecial)
class CalendarRuleSpecialAdmin(admin.ModelAdmin):
    list_display = ("rule_key", "is_enabled", "title_override", "color_key")
    list_editable = ("is_enabled", "color_key")
    search_fields = ("rule_key", "title_override")
from django.contrib import admin
from .models import Account, Category, SubCategory, Transaction, Transfer, GigCompany, GigShift, GigCompanyEntry

# Simple registrations (no custom admin behavior)
admin.site.register(Category)
admin.site.register(SubCategory)

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

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'account_type', 'active')
    list_filter = ('account_type', 'active')
    search_fields = ('name',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'date', 'account', 'description', 'debit', 'amount',
        'subcategory', 'is_expense_flag', 'credit',
        'cleared', 'write_off', 'is_carryover', 
    )
    list_filter = (
        'cleared', 'write_off', 'is_carryover',
        'account', 'subcategory', 'date', 'account__account_type', 
        'subcategory__category__is_expense'
    )
    search_fields = (
        'description', 'amount', 'account__name',
        'subcategory__name', 'subcategory__category__name'
    )
    date_hierarchy = 'date'

   
@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ('date', 'from_account', 'to_account', 'amount', 'description', 'cleared', 'write_off')
    list_filter = ('cleared', 'write_off', 'from_account', 'to_account', 'date')
    search_fields = ('description',)

    fieldsets = (
        (None, {
            'fields': ('date', 'from_account', 'to_account',  'amount')
        }),
        ('Optional Info', {
            'fields': ('description', 'cleared', 'write_off'),
            'classes': ('collapse',),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.description:
            obj.description = f"Transfer from {obj.from_account.name} to {obj.to_account.name}"
        super().save_model(request, obj, form, change)

    # def delete_model(self, request, obj):
    #     obj.delete()
        
    # def delete_queryset(self, request, queryset):
    #     for obj in queryset:
    #         obj.delete()


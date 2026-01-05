# models.py
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import datetime, date
from decimal import Decimal

class Account(models.Model):
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)
    account_type = models.CharField(
        max_length=20, 
        choices=[
        ("Deposit", "Deposit"), 
        ("Charge", "Charge"), 
        ("Personal Loan", "Personal Loan"),
        ("Vehicle Loan", "Vehicle Loan")
        ]
    )

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

class Category(models.Model):
    name = models.CharField(max_length=100)
    is_expense = models.BooleanField(default=True)
    is_income = models.BooleanField(default=False) 

    class Meta:
        ordering = ('name',)
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if self.is_expense:
            self.is_income = False
        super().save(*args, **kwargs)

class SubCategory(models.Model):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name
    
    

class Transfer(models.Model):
    from_account = models.ForeignKey(Account, related_name='transfers_out', on_delete=models.CASCADE)
    to_account = models.ForeignKey(Account, related_name='transfers_in', on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=200, blank=True)
    cleared = models.BooleanField(default=False)
    write_off = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        transfer_between = SubCategory.objects.get(name="Transfer between accounts")

        if self.to_account.account_type == 'Charge':
            transfer_subcat_to = SubCategory.objects.get(name="Credit Card Payments")
            transfer_subcat_from = transfer_between
        else:
            transfer_subcat_to = transfer_between
            transfer_subcat_from = transfer_between


        # OUTGOING transaction (from_account)
        Transaction.objects.update_or_create(
            account=self.from_account,
            date=self.date,
            amount=-self.amount,
            subcategory=transfer_subcat_from,
            defaults={
                'transfer': self,
                'description': self.description or f"Transfer to {self.to_account.name}",
                'debit': self.amount,
                'credit': None,
                'cleared': self.cleared,
                'write_off': self.write_off,
            }
        )

        # INCOMING transaction (to_account)
        Transaction.objects.update_or_create(
            account=self.to_account,
            date=self.date,
            amount=self.amount,
            subcategory=transfer_subcat_to,
            defaults={
                'transfer': self,
                'description': self.description or f"Transfer from {self.from_account.name}",
                'debit': None,
                'credit': self.amount,
                'cleared': self.cleared,
                'write_off': self.write_off,
            }
        )

    def delete(self, *args, **kwargs):
        print(f"Deleting Transfer ID: {self.id}")
        Transaction.objects.filter(transfer=self).delete()
        super().delete(*args, **kwargs)

class Transaction(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    transfer = models.ForeignKey(Transfer, null=True, blank=True, on_delete=models.CASCADE)
    date = models.DateField()
    description = models.TextField(blank=True)
    debit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    credit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False, null=True)
    subcategory = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True, blank=True)
    cleared = models.BooleanField(default=False)
    write_off = models.BooleanField(default=False)
    is_carryover = models.BooleanField(default=False)

    class Meta:
        unique_together = ('transfer', 'account')

    def is_expense_flag(self):
        if self.subcategory and self.subcategory.category:
            return self.subcategory.category.is_expense
        return None  # or False if you want to default

    is_expense_flag.short_description = "Is Expense"
    is_expense_flag.boolean = True

    def __str__(self):
        return f"{self.date} - {self.account.name} - ${self.amount}"

    def save(self, *args, **kwargs):
        self.amount = (self.credit or 0) - (self.debit or 0)
        super().save(*args, **kwargs)

    @property
    def nature(self):
        if self.subcategory and "transfer" in self.subcategory.name.lower():
            return "TRANSFER"
        elif self.debit:
            return "EXPENSE"
        elif self.credit:
            return "INCOME"
        if self.subcategory and "loan" in self.subcategory.name.lower():
            return "LOAN_PAYMENT"
        return "UNKNOWN"

class GigShift(models.Model):
    date = models.DateField(default=timezone.now)
    start_time = models.TimeField()
    end_time = models.TimeField()

    miles = models.DecimalField(max_digits=7, decimal_places=2)
    mpg = models.DecimalField(max_digits=4, decimal_places=1)
    gas_price = models.DecimalField(max_digits=4, decimal_places=3)

    # optional shorthand notes like "WM/DD/UE"
    company_mix_note = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional (e.g. WM/DD/UE)",
    )

    mileage_deduction_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0.67,   # adjust to actual IRS rate
    )

    class Meta:
        ordering = ["-date", "-start_time"]

    def __str__(self):
        return f"{self.date} ({self.start_time}-{self.end_time})"

    # ---------- SHIFT-LEVEL CALCULATED FIELDS ----------

    @property
    def hours(self):
        start = datetime.combine(self.date, self.start_time)
        end = datetime.combine(self.date, self.end_time)
        diff = end - start
        seconds = diff.total_seconds()
        return seconds / 3600 if seconds > 0 else 0

    @property
    def projected_earnings(self):
        h = self.hours
        if h > 5:
            return 100
        elif h > 4:
            return 80
        elif h > 3:
            return 60
        return 0

    @property
    def fuel_cost(self):
        if not self.mpg or not self.gas_price:
            return 0.0
        return (float(self.miles) / float(self.mpg)) * float(self.gas_price)

    # ----- AGGREGATES FROM PER-COMPANY ROWS -----

    @property
    def total_gross(self):
        return sum(c.gross_earnings for c in self.company_entries.all())

    @property
    def total_deliveries(self):
        return sum(c.deliveries for c in self.company_entries.all())

    @property
    def total_tips_amount(self):
        return sum(c.tips_amount for c in self.company_entries.all())

    @property
    def total_tips_count(self):
        return sum(c.tips_count for c in self.company_entries.all())

    @property
    def total_earnings_before_tips(self):
        return sum(c.earnings_before_tips for c in self.company_entries.all())

    @property
    def difference(self):
        # projected_earnings is already a float/int, so cast total_gross to float
        return float(self.total_gross or 0) - float(self.projected_earnings or 0)

    @property
    def net_after_gas(self):
        # both as floats
        return float(self.total_gross or 0) - float(self.fuel_cost or 0)

    @property
    def gross_per_hour(self):
        return (float(self.total_gross or 0) / self.hours) if self.hours else 0.0

    @property
    def net_per_hour(self):
        return (float(self.net_after_gas or 0) / self.hours) if self.hours else 0.0

    @property
    def gross_per_mile(self):
        return (float(self.total_gross or 0) / float(self.miles)) if self.miles else 0.0

    @property
    def net_per_mile(self):
        return (float(self.net_after_gas or 0) / float(self.miles)) if self.miles else 0.0

    @property
    def tip_percent_overall(self):
        return (100*(self.total_tips_count / self.total_deliveries)) if self.total_deliveries else 0

    @property
    def avg_tip_overall(self):
        return (self.total_tips_amount / self.total_deliveries) if self.total_deliveries else 0

    @property
    def deduction(self):
        # also keep this as float for consistency
        return float(self.miles or 0) * float(self.mileage_deduction_rate or 0)
    
    #---Mileage deduction property uses MileageRate model and utility function---
    @property
    def effective_mileage_rate(self) -> Decimal:
        """
        Rate in $/mile, determined by the shift date.
        """
        if not self.date:
            return Decimal("0")
        return get_mileage_rate_for_date(self.date)
    
    @property
    def effective_deduction(self) -> Decimal:
        """
        Deduction amount = miles * effective rate.
        """
        miles = self.miles or Decimal("0")
        rate = self.effective_mileage_rate or Decimal("0")
        return miles * rate


class GigCompany(models.Model):
    code = models.CharField(max_length=10, unique=True)   # "DD", "UE", "WM"
    name = models.CharField(max_length=50)                # "DoorDash", etc.

    # point these at your existing models
    payout_account = models.ForeignKey(
        "Account", 
        on_delete=models.PROTECT,
        help_text="Which account receives this company's payouts"
    )
    # income_subcategory = models.ForeignKey(
    #     "SubCategory", 
    #     on_delete=models.PROTECT,
    #     help_text="Subcategory to use for income transactions (e.g. 'Salary - Gig Work')"
    # )

    income_subcategory = models.ForeignKey(
        "SubCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f"{self.code} - {self.name}"

class GigCompanyEntry(models.Model):
    shift = models.ForeignKey(
        "GigShift",  # <= string, not bare GigShift
        related_name="company_entries",
        on_delete=models.CASCADE,
    )

    company = models.ForeignKey(
        "GigCompany",   # string ref
        on_delete=models.PROTECT,
        related_name="gig_entries",
    )

    deliveries = models.IntegerField()
    tips_count = models.IntegerField(help_text="Number of deliveries that had a tip")
    tips_amount = models.DecimalField(
        max_digits=7, decimal_places=2, 
        default=0,
    )
    earnings_before_tips = models.DecimalField(
        max_digits=7, decimal_places=2,
        default=0,
    )
    gross_earnings = models.DecimalField(
        max_digits=7, decimal_places=2,
        help_text="Base pay + tips for this company during this shift"
    )

    # Link to the budget Transaction created for this entry
    income_transaction = models.OneToOneField(
        "Transaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gig_income_entry",
        help_text="Automatically-created income transaction for this company+shift",
    )

    class Meta:
        ordering = ["company__code"]

    def __str__(self):
        return f"{self.company.code} ({self.shift.date})"

    @property
    def tip_percent(self):
        return (self.tips_count / self.deliveries) if self.deliveries else 0

    @property
    def avg_tip(self):
        return (self.tips_amount / self.deliveries) if self.deliveries else 0
       
    def save(self, *args, **kwargs):
        """
        Always keep earnings_before_tips = gross_earnings - tips_amount.
        """
        gross = self.gross_earnings or 0
        tips = self.tips_amount or 0
        self.earnings_before_tips = gross - tips
        super().save(*args, **kwargs)

class MileageRate(models.Model):
    """
    Stores IRS (or your chosen) mileage deduction rate with an effective date.
    Example: 2025-01-01 → $0.67 per mile
    """
    effective_date = models.DateField(
        help_text="Date this rate becomes effective (inclusive)."
    )
    rate = models.DecimalField(
        max_digits=5,  # e.g. 0.670 or 1.234
        decimal_places=3,
        help_text="Deduction per mile in dollars, e.g. 0.670",
    )
    note = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional note (e.g. 'IRS 2025 standard rate')",
    )

    class Meta:
        ordering = ["-effective_date"]
        verbose_name = "Mileage rate"
        verbose_name_plural = "Mileage rates"
        # You usually only need one row per effective date
        constraints = [
            models.UniqueConstraint(
                fields=["effective_date"],
                name="unique_mileage_rate_per_effective_date",
            )
        ]

    def __str__(self):
        return f"{self.effective_date} → {self.rate} $/mile"
    

def get_mileage_rate_for_date(on_date: date) -> Decimal:
    """
    Returns the mileage rate that applies on `on_date`.
    Chooses the latest MileageRate with effective_date <= on_date.
    Returns Decimal('0') if nothing is configured.
    """
    from .models import MileageRate  # if this is in a separate utils module, remove this import

    qs = MileageRate.objects.filter(effective_date__lte=on_date).order_by("-effective_date")
    row = qs.first()
    if row is None:
        return Decimal("0")
    return row.rate

class CalendarAccount(models.Model):
    PROVIDERS = [
        ("google", "Google"),
        ("icloud", "iCloud (CalDAV)"),
        ("outlook", "Outlook (Graph)"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    provider = models.CharField(max_length=20, choices=PROVIDERS)
    display_name = models.CharField(max_length=120, blank=True)
    # Store tokens/credentials securely (see notes below)
    credentials_json = models.JSONField(default=dict)  # encrypted at rest ideally
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user} - {self.provider} ({self.display_name or 'account'})"

class CalendarSource(models.Model):
    """
    A specific calendar within an account (e.g., 'Personal', 'Work', 'Family').
    """
    account = models.ForeignKey(CalendarAccount, on_delete=models.CASCADE)
    external_calendar_id = models.CharField(max_length=255)  # Google calendarId / CalDAV URL / Outlook id
    name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=64, default="America/New_York")
    is_primary = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_cursor = models.CharField(max_length=255, blank=True)  # optional, provider-dependent

    def __str__(self):
        return f"{self.account.provider}: {self.name}"

class CalendarEvent(models.Model):
    """
    Your unified event record.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    source = models.ForeignKey(CalendarSource, on_delete=models.SET_NULL, null=True, blank=True)

    external_event_id = models.CharField(max_length=255, blank=True)  # provider event id / UID
    title = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    start_dt = models.DateTimeField()
    end_dt = models.DateTimeField()
    all_day = models.BooleanField(default=False)
    status = models.CharField(max_length=32, default="confirmed")  # confirmed/cancelled/tentative
    event_type = models.CharField(max_length=20, default="normal")  # normal/special
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.CharField(max_length=20, blank=True, default="")
    last_edited_by = models.CharField(max_length=20, blank=True, default="")

    EVENT_PEOPLE = [
        ("mike", "Mike"),
        ("wife", "Stef"),
        ("kid1", "Max"),
        ("kid2", "Leo"),
    ]

    person = models.CharField(
        max_length=20,
        choices=EVENT_PEOPLE,
        default="mike",
    )

    # Conflict handling
    last_synced_at = models.DateTimeField(null=True, blank=True)
    provider_etag = models.CharField(max_length=255, blank=True)  # Google etag or similar
    provider_last_modified = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "start_dt"]),
            models.Index(fields=["external_event_id"]),
        ]  
        
    def __str__(self):
        return f"{self.title} ({self.start_dt})"

class CalendarSpecial(models.Model):
    SPECIAL_TYPES = [
        ("birthday", "Birthday"),
        ("anniversary", "Anniversary"),
        ("holiday", "Holiday"),
        ("milestone", "Milestone"),
        ("reminder", "Reminder"),
    ]

    title = models.CharField(max_length=255)
    date = models.DateField()

    special_type = models.CharField(max_length=20, choices=SPECIAL_TYPES, default="reminder")
    person = models.CharField(max_length=50, blank=True)

    recurring_yearly = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    # optional: if you want to control display color separate from person
    color_key = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.title} ({self.date})"
    
class CalendarRuleSpecial(models.Model):
    """
    Specials that are computed from a rule each year (Easter, Thanksgiving, etc.).
    """
    title = models.CharField(max_length=255)

    RULES = [
        ("easter", "Easter (Western)"),
        ("good_friday", "Good Friday"),
        ("thanksgiving_us", "Thanksgiving (US)"),
        ("mothers_day_us", "Mother's Day (US)"),
        ("fathers_day_us", "Father's Day (US)"),
        ("memorial_day_us", "Memorial Day (US)"),
        ("labor_day_us", "Labor Day (US)"),
        ("mlk_day_us", "MLK Day (US)"),
        ("presidents_day_us", "Presidents Day (US)"),
    ]
    rule_key = models.CharField(max_length=50, choices=RULES)
    title_override = models.CharField(max_length=255, blank=True)  # optional custom label

    # optional metadata consistent with your other specials
    special_type = models.CharField(max_length=20, choices=CalendarSpecial.SPECIAL_TYPES, default="holiday")
    person = models.CharField(max_length=50, blank=True)  # allow extended family names/keys
    notes = models.TextField(blank=True)
    color_key = models.CharField(max_length=20, blank=True)

    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.title_override or self.get_rule_key_display()
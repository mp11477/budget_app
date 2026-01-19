from django.db import models
from django.utils import timezone
from datetime import datetime, date
from decimal import Decimal

"""
gigs.models

Holds models for tracking gig-delivery work (DoorDash/Uber Eats/Walmart Spark, etc.).

Core concepts:
- GigShift: One work session (date + time window + mileage + fuel assumptions).
- GigCompany: A gig platform (DD/UE/WM) and how payouts map into the budget app.
- GigCompanyEntry: Per-company performance within a shift (deliveries, tips, gross).
- MileageRate: Mileage deduction rate configuration over time.

Note:
This app intentionally references budget models (Account/SubCategory/Transaction)
to integrate gig income into the existing ledger.
"""

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
    
    class Meta:
        db_table = "budget_gigshift"


class GigCompany(models.Model):
    """
    Represents a gig platform (DoorDash, Uber Eats, Walmart Spark, etc).

    This model also stores how to map payouts into the budgeting ledger:
    - payout_account: where deposits land
    - income_subcategory: which subcategory is used for the income Transaction created
    """
    code = models.CharField(max_length=10, unique=True)   # "DD", "UE", "WM"
    name = models.CharField(max_length=50)                # "DoorDash", etc.

    # point these at your existing models
    payout_account = models.ForeignKey(
        "budget.Account", 
        on_delete=models.PROTECT,
        help_text="Which account receives this company's payouts"
    )
    # income_subcategory = models.ForeignKey(
    #     "SubCategory", 
    #     on_delete=models.PROTECT,
    #     help_text="Subcategory to use for income transactions (e.g. 'Salary - Gig Work')"
    # )

    income_subcategory = models.ForeignKey(
        "budget.SubCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f"{self.code} - {self.name}"
    
    class Meta:
        db_table = "budget_gigcompany"

class GigCompanyEntry(models.Model):
    """
    Per-company stats for a single GigShift.

    Each entry can auto-create (or update) a linked budget.Transaction representing
    income from that company for that shift.

    Fields:
    - deliveries: total deliveries for this company during the shift
    - tips_count: how many deliveries included tips
    - tips_amount: total tips received
    - gross_earnings: base pay + tips
    - earnings_before_tips: maintained automatically as (gross_earnings - tips_amount)
    """
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
        "budget.Transaction",
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
        """Fraction of deliveries that included a tip (0.0–1.0)."""
        return (self.tips_count / self.deliveries) if self.deliveries else 0

    @property
    def avg_tip(self):
        """Average tip per delivery (includes zero-tip deliveries)."""
        return (self.tips_amount / self.deliveries) if self.deliveries else 0
       
    def save(self, *args, **kwargs):
        """
        Always keep earnings_before_tips = gross_earnings - tips_amount.
        """
        gross = self.gross_earnings or 0
        tips = self.tips_amount or 0
        self.earnings_before_tips = gross - tips
        super().save(*args, **kwargs)

    class Meta:
        db_table = "budget_gigcompanyentry"
        ordering = ["company__code"]

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
    
    class Meta:
        db_table = "budget_mileagerate"
    

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

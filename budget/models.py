# models.py
from django.db import models
from django.utils import timezone
from datetime import datetime, timedelta

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

class SubCategory(models.Model):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if self.is_expense:
            self.is_income = False
        super().save(*args, **kwargs)

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
    gas_price = models.DecimalField(max_digits=4, decimal_places=2)

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
        return f"{self.date} ({self.start_time}–{self.end_time})"

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
        if not self.mpg:
            return 0
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
        return self.total_gross - self.projected_earnings

    @property
    def net_after_gas(self):
        return self.total_gross - self.fuel_cost

    @property
    def gross_per_hour(self):
        return self.total_gross / self.hours if self.hours else 0

    @property
    def net_per_hour(self):
        return self.net_after_gas / self.hours if self.hours else 0

    @property
    def gross_per_mile(self):
        return self.total_gross / self.miles if self.miles else 0

    @property
    def net_per_mile(self):
        return self.net_after_gas / self.miles if self.miles else 0

    @property
    def tip_percent_overall(self):
        return (self.total_tips_count / self.total_deliveries) if self.total_deliveries else 0

    @property
    def avg_tip_overall(self):
        return (self.total_tips_amount / self.total_deliveries) if self.total_deliveries else 0

    @property
    def deduction(self):
        return float(self.miles) * float(self.mileage_deduction_rate)


class GigCompany(models.Model):
    code = models.CharField(max_length=10, unique=True)   # "DD", "UE", "WM"
    name = models.CharField(max_length=50)                # "DoorDash", etc.

    # point these at your existing models
    payout_account = models.ForeignKey(
        "Account", 
        on_delete=models.PROTECT,
        help_text="Which account receives this company's payouts"
    )
    income_category = models.ForeignKey(
        "Category", 
        on_delete=models.PROTECT,
        help_text="Usually your 'Salary - Gig Work' category"
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
    tips_amount = models.DecimalField(max_digits=7, decimal_places=2)
    earnings_before_tips = models.DecimalField(max_digits=7, decimal_places=2)
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
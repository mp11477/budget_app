# models.py
from django.db import models


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



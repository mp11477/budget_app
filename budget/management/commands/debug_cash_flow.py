import csv
from django.db.models import Sum, Q
from django.db.models.functions import TruncMonth
from django.core.management.base import BaseCommand
from budget.models import Transaction  # replace with your app name
from pathlib import Path

class Command(BaseCommand):

    output_path = Path(r"c:\python\scripts\budget_app\debug_cash_flow.csv")

    qs = Transaction.objects.filter(is_carryover=False).annotate(month=TruncMonth("date"))

    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "Month",
            "Date",
            "Account",
            "Subcategory",
            "Category",
            "Amount",
            "Credit",
            "Debit",
            "Is Income",
            "Is Expense",
        ])
        
        for tx in qs.select_related("account", "subcategory__category"):
            writer.writerow([
                tx.month.strftime("%Y-%m") if tx.month else "",
                tx.date.strftime("%Y-%m-%d"),
                tx.account.name if tx.account else "",
                tx.subcategory.name if tx.subcategory else "",
                tx.subcategory.category.name if tx.subcategory and tx.subcategory.category else "",
                tx.amount,
                tx.credit,
                tx.debit,
                tx.subcategory.category.is_income if tx.subcategory and tx.subcategory.category else "",
                tx.subcategory.category.is_expense if tx.subcategory and tx.subcategory.category else "",
            ])

    print(f"✅ CSV export saved to: {output_path}")
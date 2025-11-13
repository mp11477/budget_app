import csv
from django.core.management.base import BaseCommand
from budget.models import Account, SubCategory, Transaction
from datetime import datetime

class Command(BaseCommand):
    help = "Import transactions from CSV"

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')

    def handle(self, *args, **kwargs):
        file_path = kwargs['csv_file']

        with open(file_path, newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            imported = 0
            skipped = 0

            for row in reader:
                try:
                    account = Account.objects.get(name=row['account'].strip())
                    subcat = SubCategory.objects.get(name=row['subcategory'].strip())

                    tx = Transaction(
                        account=account,
                        date = datetime.strptime(row['date'], "%m/%d/%Y").date(),
                        description=row['description'].strip(),
                        debit=float(row['debit']) if row['debit'].strip() else None,
                        credit=float(row['credit']) if row['credit'].strip() else None,
                        subcategory=subcat,
                        cleared=row['cleared'].strip().lower() in ("true", "1", "yes"),
                        write_off=row['write-off'].strip().lower() in ("true", "1", "yes")
                    )
                    tx.save()
                    imported += 1
                except Exception as e:
                    skipped += 1
                    self.stderr.write(f"⚠️ Skipping row due to error: {e}")

            self.stdout.write(self.style.SUCCESS(f"✅ Imported {imported} transactions"))
            if skipped:
                self.stdout.write(self.style.WARNING(f"⚠️ Skipped {skipped} rows"))
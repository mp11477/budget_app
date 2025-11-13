# inventory/management/commands/split_loan_cc_payment.py

from django.core.management.base import BaseCommand
from budget.models import Transaction


class Command(BaseCommand):
    help = "Split LOAN_PAYMENT into CC_PAYMENT and LOAN_PAYMENT based on account name"

    def handle(self, *args, **options):
        cc_keywords = ['visa', 'mastercard', 'cc', 'credit']
        loan_keywords = ['loan', 'auto', 'mortgage', 'student']

        updated_cc = 0
        updated_loan = 0
        skipped = 0

        transactions = Transaction.objects.filter(transaction_type='LOAN_PAYMENT')

        for tx in transactions:
            account_name = tx.account.name.lower()

            if any(keyword in account_name for keyword in cc_keywords):
                tx.transaction_type = 'CC_PAYMENT'
                tx.save(update_fields=['transaction_type'])
                updated_cc += 1
            elif any(keyword in account_name for keyword in loan_keywords):
                tx.transaction_type = 'LOAN_PAYMENT'
                tx.save(update_fields=['transaction_type'])
                updated_loan += 1
            else:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"🔶 Skipped ambiguous account: {tx.account.name}"))

        self.stdout.write(self.style.SUCCESS(f"✅ Updated {updated_cc} to CC_PAYMENT"))
        self.stdout.write(self.style.SUCCESS(f"✅ Updated {updated_loan} to LOAN_PAYMENT"))
        self.stdout.write(self.style.WARNING(f"⚠️ Skipped {skipped} transactions due to unrecognized account names"))

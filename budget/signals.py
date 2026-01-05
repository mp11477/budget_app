from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import GigCompanyEntry

@receiver(post_save, sender=GigCompanyEntry)
def sync_gig_entry_to_transaction(sender, instance: GigCompanyEntry, **kwargs):
    """
    Ensure each GigCompanyEntry has a matching income Transaction.
    Uses credit (income) and the company's configured payout account
    and income_subcategory
    """
    from .models import Transaction  # avoid circular import

    shift = instance.shift
    company = instance.company

    # Decide what amount you want to post to the budget:
    amount = instance.gross_earnings or 0 # you historically used total earnings per company

     # Require a payout account and subcategory, otherwise bail out quietly
    if not company.payout_account or not company.income_subcategory:
        return

    # Create or update the linked Transaction
    if instance.income_transaction:
        tx = instance.income_transaction
        tx.date = shift.date
        tx.account = company.payout_account
        tx.amount = amount
        tx.description = f"Gig earnings - {company.code}"
        tx.subcategory = company.income_subcategory
        tx.cleared = False
        tx.write_off = False
        # if you have transaction_type:
        # tx.transaction_type = Transaction.Type.INCOME  # adjust to your enum
        tx.save()
    else:
        # Create a new transaction
        tx = Transaction.objects.create(
            account=company.payout_account,
            date=shift.date,
            description=f"Gig earnings - {company.code}",
            debit=None,
            credit=amount,
            subcategory=company.income_subcategory,
            cleared=False,
            write_off=False,
        )
        # Link it back to the GigCompanyEntry without re-triggering recursion
        instance.income_transaction = tx
        GigCompanyEntry.objects.filter(pk=instance.pk).update(income_transaction=tx)


@receiver(post_delete, sender=GigCompanyEntry)
def delete_gig_entry_transaction(sender, instance: GigCompanyEntry, **kwargs):
    """
    If you delete a gig entry, also delete its linked Transaction.
    (Optional - you could instead leave the Transaction orphaned if you prefer.)
    """
    if instance.income_transaction:
        instance.income_transaction.delete()
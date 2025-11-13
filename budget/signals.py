from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import GigCompanyEntry

@receiver(post_save, sender=GigCompanyEntry)
def sync_gig_entry_to_transaction(sender, instance: GigCompanyEntry, **kwargs):
    """
    Ensure each GigCompanyEntry has a matching income Transaction.
    """
    from .models import Transaction  # avoid circular import

    shift = instance.shift
    company = instance.company

    # Decide what amount you want to post to the budget:
    amount = instance.gross_earnings  # you historically used total earnings per company

    # Create or update the linked Transaction
    if instance.income_transaction:
        tx = instance.income_transaction
        tx.date = shift.date
        tx.account = company.payout_account
        tx.amount = amount
        tx.description = f"Gig earnings - {company.code}"
        tx.category = company.income_category
        # if you have transaction_type:
        # tx.transaction_type = Transaction.Type.INCOME  # adjust to your enum
        tx.save()
    else:
        tx = Transaction.objects.create(
            date=shift.date,
            account=company.payout_account,
            amount=amount,
            description=f"Gig earnings - {company.code}",
            category=company.income_category,
            # transaction_type=Transaction.Type.INCOME,
        )
        instance.income_transaction = tx
        # avoid infinite recursion: update without re-triggering logic if needed
        GigCompanyEntry.objects.filter(pk=instance.pk).update(
            income_transaction=tx
        )


@receiver(post_delete, sender=GigCompanyEntry)
def delete_gig_entry_transaction(sender, instance: GigCompanyEntry, **kwargs):
    """
    If you delete a gig entry, also delete its linked Transaction.
    (Optional - you could instead leave the Transaction orphaned if you prefer.)
    """
    if instance.income_transaction:
        instance.income_transaction.delete()
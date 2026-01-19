from django.urls import include, path
from . import views

app_name = "budget"

urlpatterns = [
   
    ### Additional budget-related routes ###
    path("dashboard/", views.dashboard, name="dashboard"),
    path("account/<int:account_id>/transactions/", views.account_transactions, name="account_transactions"),
    path("summary/deposits/", views.deposit_summary_transactions, name="deposit_summary_transactions"),
    path("summary/loans/", views.loan_summary_transactions, name="loan_summary_transactions"),
    path("complex_algorithm/", views.complex_algorithm, name="complex_algorithm"),
    path("add-transaction/", views.add_transaction, name="add_transaction"),
    path("add-transfer/", views.add_transfer, name="add_transfer"),
    path("transactions/recent/", views.recent_transactions_ajax, name="recent_transactions_ajax"),
    path("recent-transfers-ajax/", views.recent_transfers_ajax, name="recent_transfers_ajax"),
    path("mark-transaction-cleared/<int:tx_id>/", views.mark_transaction_cleared, name="mark_transaction_cleared"),
    path("charts/", views.charts_view, name="charts"),
    path("update-subcategory/<int:txn_id>/", views.update_subcategory, name="update_subcategory"),

]
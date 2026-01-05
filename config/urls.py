from django.contrib import admin
from django.urls import path, include
from budget import views  



urlpatterns = [
    path('admin/', admin.site.urls),
    path('dashboard_test/', views.dashboard_test, name='dashboard_test'),
    path('dashboard/', views.dashboard, name='dashboard'),  
    path('account/<int:account_id>/transactions/', views.account_transactions, name='account_transactions'),
    path('summary/deposits/', views.deposit_summary_transactions, name='deposit_summary_transactions'),
    path('summary/loans/', views.loan_summary_transactions, name='loan_summary_transactions'),
    path('complex_algorithm/', views.complex_algorithm, name='complex_algorithm'),
    path('add-transaction/', views.add_transaction, name='add_transaction'),
    path('add-transfer/', views.add_transfer, name='add_transfer'),
    path('transactions/recent/', views.recent_transactions_ajax, name='recent_transactions_ajax'),
    path('recent-transfers-ajax/', views.recent_transfers_ajax, name='recent_transfers_ajax'),
    path("mark-transaction-cleared/<int:tx_id>/", views.mark_transaction_cleared, name="mark_transaction_cleared"),
    path('charts/', views.charts_view, name="charts"),
    path('update-subcategory/<int:txn_id>/', views.update_subcategory, name='update_subcategory'),
    path('gig-entry/', views.gig_entry, name='gig_entry'),
    path('gig-summary/', views.gig_summary, name='gig_summary'),
    path('mileage-rate/', views.mileage_rate_settings, name='mileage_rate_settings'),
    path("", include("budget.urls")),
    path('', views.dashboard, name='home'),
    
        
]
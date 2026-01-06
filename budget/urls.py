from django.urls import path
from . import views

urlpatterns = [
    path("main_calendar/", views.main_calendar, name="calendar_home"),
    path("calendar/", views.calendar_month, name="calendar_month"),
    path("calendar/day/", views.calendar_day, name="calendar_day"),
    path("calendar/week/", views.calendar_week, name="calendar_week"),

    path("calendar-entry/", views.calendar_entry, name="calendar_entry"), #tablet
    
    path("calendar/kiosk/unlock/", views.kiosk_unlock_page, name="kiosk_unlock_page"),
    path("calendar/kiosk/unlock/submit/", views.kiosk_unlock, name="kiosk_unlock"),
    path("calendar/kiosk/lock/", views.kiosk_lock, name="kiosk_lock"),
   
    path("calendar/event/new/", views.calendar_event_create, name="calendar_event_create"),
    path("calendar/event/<int:event_id>/", views.calendar_event_detail, name="calendar_event_detail"),
    path("calendar/event/<int:event_id>/edit/", views.calendar_event_edit, name="calendar_event_edit"),
    path("calendar/event/<int:event_id>/delete/", views.calendar_event_delete, name="calendar_event_delete"),

    path("calendar/weather/fragment/", views.weather_fragment, name="weather_fragment"),

    path("calendar/ping/", views.health_ping, name="health_ping"),

    path('gig-entry/', views.gig_entry, name='gig_entry'),
    path('gig-summary/', views.gig_summary, name='gig_summary'),
    path('mileage-rate/', views.mileage_rate_settings, name='mileage_rate_settings'),


    ### Additional budget-related routes ###
    path("dashboard_test/", views.dashboard_test, name="dashboard_test"),
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
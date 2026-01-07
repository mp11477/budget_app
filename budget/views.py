from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Q, Case, When, Value, F, DecimalField
from django.db.models.functions import ExtractMonth, ExtractYear, TruncMonth
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie

from collections import defaultdict, OrderedDict
from decimal import Decimal
from pathlib import Path
from calendar_app.specials import inject_specials_into_events_by_day, compute_rule_date
from calendar_app.weather import get_cached_weather
from .forms import TransactionForm, TransferForm, GigShiftForm, GigCompanyFormSet, MileageRateForm
from .models import (Account, Transaction, Transfer, Category, SubCategory, GigShift, GigCompany, MileageRate, CalendarEvent, CalendarSpecial,
            CalendarRuleSpecial)

import calendar, json, datetime
from calendar import month_name, monthrange
from datetime import date, time, datetime, timedelta
from functools import wraps

def dashboard_test(request):
    return render(request, 'dashboard_test.html', {})

def dashboard(request):
    deposit_accounts = Account.objects.filter(active=True, account_type="Deposit")
    loan_accounts = Account.objects.filter(active=True).exclude(account_type="Deposit")

    uncleared_transactions = Transaction.objects.filter(cleared=False, account__account_type="Deposit").order_by('-date')[:20]
    uncleared_cc_transactions = Transaction.objects.filter(cleared=False).exclude(account__account_type="Deposit").order_by('-date')[:20]

    update_subcategory = Transaction.objects.filter(subcategory__name__isnull =True).order_by('-date')[:20]
    sub_cat_name = [(s.name, s.name) for s in SubCategory.objects.all().order_by("category__name", "name")]

    def summarize(accounts):
        summary = []
        cleared_total = 0
        total = 0

        for account in accounts:
            transactions = Transaction.objects.filter(account=account)

            cleared_tx = transactions.filter(cleared=True)
            all_tx = transactions

            cleared_sum = cleared_tx.aggregate(total=Sum('amount'))['total'] or 0
            total_sum = all_tx.aggregate(total=Sum('amount'))['total'] or 0

            cleared_total += cleared_sum
            total += total_sum

            summary.append({
                'id': account.id,
                'name': account.name,
                'type': account.account_type,
                'cleared_balance': cleared_sum,
                'total_balance': total_sum,
            })

        return summary, cleared_total, total

    deposit_summary, deposit_cleared_total, deposit_total = summarize(deposit_accounts)
    loan_summary, loan_cleared_total, loan_total = summarize(loan_accounts)

    today = date.today()
    context = {
        'deposit_summary': deposit_summary,
        'loan_summary': loan_summary,
        'deposit_cleared_total': deposit_cleared_total,
        'deposit_total': deposit_total,
        'loan_cleared_total': loan_cleared_total,
        'loan_total': loan_total,
        'current_month': today.month,
        'current_year': today.year,
        'uncleared_transactions': uncleared_transactions,
        'uncleared_cc_transactions': uncleared_cc_transactions,
        'update_subcategory': update_subcategory,
        'sub_cat_name': sub_cat_name,
        }

    return render(request, 'budget/dashboard.html', context)

@require_POST
def mark_transaction_cleared(request, tx_id):
    transaction = get_object_or_404(Transaction, id=tx_id)
    transaction.cleared = True
    transaction.save()
    return redirect('budget:dashboard')

def get_month_choices():
    return [
        {"value": "", "name": "All Months"}
    ] + [
        {"value": str(i), "name": month_name[i]} for i in range(1, 13)
    ]

def get_year_range():
    return [str(y) for y in range(2023, 2027)]

def get_category_choices(transactions):
    categories = Category.objects.filter(
        subcategory__transaction__in=transactions
        ).distinct()  # Optional: sort alphabetically
   
    return [(cat.name, cat.name) for cat in categories]

def get_subcategory_choices(transactions):
    subcategories = SubCategory.objects.filter(
        transaction__in=transactions
        ).distinct().order_by('name')  # Optional: sort alphabetically

    return [(subcat.name, subcat.name) for subcat in subcategories]

def apply_transaction_filters(transactions, month, year, cleared, write_off, cat_name, sub_cat_name, search):
    if month:
        transactions = transactions.filter(date__month=int(month))
    if year:
        transactions = transactions.filter(date__year=int(year))
    if cleared == "yes":
        transactions = transactions.filter(cleared=True)
    elif cleared == "no":
        transactions = transactions.filter(cleared=False)
    if write_off == "yes":
        transactions = transactions.filter(write_off=True)
    elif write_off == "no":
        transactions = transactions.filter(write_off=False)
        
    if cat_name:
        transactions = transactions.filter(
            subcategory__isnull=False,
            subcategory__category__name__icontains=cat_name
        )

    if sub_cat_name:
        transactions = transactions.filter(
            subcategory__isnull=False,
            subcategory__name__icontains=sub_cat_name
        )

    if search:
        try:
            amount = abs(float(search))
            transactions = transactions.filter(Q(description__icontains=search) |
                                               Q(amount__exact=amount) |
                                               Q(amount__exact=-amount))
        except ValueError:
            transactions = transactions.filter(description__icontains=search)
    
    return transactions

def update_subcategory(request, txn_id):
    if request.method == 'POST':
        txn = get_object_or_404(Transaction, id=txn_id)
        new_type = request.POST.get('sub_cat_name')
        subcategory = SubCategory.objects.filter(name=new_type).first()
        if subcategory:
            txn.subcategory = subcategory
            txn.save()
    return redirect('budget:dashboard')

def calculate_totals(transactions):
    debit_total = transactions.aggregate(total=Sum('debit'))['total'] or 0
    credit_total = transactions.aggregate(total=Sum('credit'))['total'] or 0
    net_amount = transactions.aggregate(total=Sum('amount'))['total'] or 0
    return {
        "debit": debit_total,
        "credit": credit_total,
        "amount": net_amount
    }

def account_transactions(request, account_id):
    account = get_object_or_404(Account, id=account_id)
    cleared = request.GET.get("cleared")
    write_off = request.GET.get("write_off")
    month = request.GET.get("month")
    year = request.GET.get("year")
    cat_name = request.GET.get('cat_name')
    sub_cat_name = request.GET.get('sub_cat_name')
    search = request.GET.get("search", "").strip()

    today = date.today()
    if year is None:
        year = str(today.year)
    if month is None:
        month = str(today.month)

    transactions = Transaction.objects.filter(account=account)
    transactions = apply_transaction_filters(transactions, month, year, cleared, write_off, cat_name, sub_cat_name, search)
    transactions = transactions.order_by("date")

    totals = calculate_totals(transactions)

    context = {
        "account": account,
        "transactions": transactions,
        "month": month,
        "year": year,
        "cleared": cleared,
        "write_off": write_off,
        "cat_name": cat_name,
        "sub_cat_name": sub_cat_name,
        "search": search,
        "month_choices": get_month_choices(),
        "year_range": get_year_range(),
        "cat_name_choices": get_category_choices(transactions),
        "sub_cat_name_choices": get_subcategory_choices(transactions),
        "totals": totals,
        
    }

    return render(request, "budget/transactions.html", context)

def deposit_summary_transactions(request):
    deposit_accounts = Account.objects.filter(active=True, account_type="Deposit")
    transactions = Transaction.objects.filter(account__in=deposit_accounts).order_by('date')

    cleared = request.GET.get("cleared")
    write_off = request.GET.get("write_off")
    month = request.GET.get("month")
    year = request.GET.get("year")
    cat_name = request.GET.get('cat_name')
    sub_cat_name = request.GET.get('sub_cat_name')
    search = request.GET.get("search", "").strip()

    today = date.today()
    if year is None:
        year = str(today.year)
    if month is None:
        month = str(today.month)

    transactions = apply_transaction_filters(transactions, month, year, cleared, write_off, cat_name, sub_cat_name, search)
    totals = calculate_totals(transactions)

    return render(request, "budget/transactions.html", {
        "account": None,
        "transactions": transactions,
        "month": month,
        "year": year,
        "cleared": cleared,
        "write_off": write_off,
        "cat_name": cat_name,
        "sub_cat_name": sub_cat_name,
        "search": search,
        "month_choices": get_month_choices(),
        "year_range": get_year_range(),
        "cat_name_choices": get_category_choices(transactions),
        "sub_cat_name_choices": get_subcategory_choices(transactions),
        "totals": totals,
    })

def loan_summary_transactions(request):
    loan_accounts = Account.objects.filter(active=True).exclude(account_type="Deposit")
    transactions = Transaction.objects.filter(account__in=loan_accounts).order_by('date')

    cleared = request.GET.get("cleared")
    write_off = request.GET.get("write_off")
    month = request.GET.get("month")
    year = request.GET.get("year")
    cat_name = request.GET.get('cat_name')
    sub_cat_name = request.GET.get('sub_cat_name')
    search = request.GET.get("search", "").strip()

    today = date.today()
    if year is None:
        year = str(today.year)
    if month is None:
        month = str(today.month)

    transactions = apply_transaction_filters(transactions, month, year, cleared, write_off, cat_name, sub_cat_name, search)
    totals = calculate_totals(transactions)

    return render(request, "budget/transactions.html", {
        "account": None,
        "transactions": transactions,
        "month": month,
        "year": year,
        "cleared": cleared,
        "write_off": write_off,
        "cat_name": cat_name,
        "sub_cat_name": sub_cat_name,
        "search": search,
        "month_choices": get_month_choices(),
        "year_range": get_year_range(),
        "cat_name_choices": get_category_choices(transactions),
        "sub_cat_name_choices": get_subcategory_choices(transactions),
        "totals": totals,
    })

def complex_algorithm(request):
    today = date.today()
    current_year = today.year
    current_month = today.month

    # Month filter from dropdown
    selected_month = request.GET.get("month")

    if selected_month == "":
        selected_month = None  # Explicitly requested All Months
    elif selected_month:
        try:
            selected_month = int(selected_month)
            if not (1 <= selected_month <= 12):
                selected_month = current_month
        except ValueError:
            selected_month = current_month
    else:
        selected_month = current_month  # Default case (no month param at all)

    deposit_accounts = Account.objects.filter(account_type='Deposit')
    dormant = []

    if selected_month:
        # 🟢 Specific month logic (as you already wrote)
        sel_month_first = date(current_year, selected_month, 1)
        sel_month_last = date(current_year, selected_month, monthrange(current_year, selected_month)[1])

        for account in deposit_accounts:
            balances = Transaction.objects.filter(
                account=account,
                amount__isnull=False
            ).aggregate(
                start_balance=Sum(
                    Case(
                        When(date__lte=sel_month_first, then=F('amount')),
                        default=Value(0),
                        output_field=DecimalField()
                    )
                ),
                activity=Sum(
                    Case(
                        When(date__gte=sel_month_first, date__lte=sel_month_last, then=F('amount')),
                        default=Value(0),
                        output_field=DecimalField()
                    )
                )
            )

            start_balance = balances['start_balance'] or 0
            activity = balances['activity'] or 0
            end_balance = start_balance + (activity - start_balance)

            if activity == start_balance and start_balance == 0 and end_balance == 0:
                dormant.append(account.name)

    else:
        # 🔴 Global filtering: check activity across entire year
        jan_1 = date(current_year, 1, 1)
        dec_31 = date(current_year, 12, 31)

        for account in deposit_accounts:
            balances = Transaction.objects.filter(
                account=account,
                amount__isnull=False
            ).aggregate(
                start_balance=Sum(
                    Case(
                        When(date__lt=jan_1, then=F('amount')),
                        default=Value(0),
                        output_field=DecimalField()
                    )
                ),
                activity=Sum(
                    Case(
                        When(date__gte=jan_1, date__lte=dec_31, then=F('amount')),
                        default=Value(0),
                        output_field=DecimalField()
                    )
                )
            )

            start_balance = balances['start_balance'] or 0
            activity = balances['activity'] or 0
            end_balance = start_balance + (activity - start_balance)

            if activity == 0 and start_balance == 0 and end_balance == 0:
                dormant.append(account.name)

    # ❌ Remove all dormant accounts (Note, this will also remove them from the complex_algorithm.html view)
    #deposit_accounts = deposit_accounts.exclude(name__in=dormant)
    #print("📦 Dormant Accounts:", dormant) #debug line to print Dormant Accounts to terminal

    all_tx = Transaction.objects.filter(
        account__in=deposit_accounts,
        date__year=current_year
    ).order_by('date')

    tx_by_month_account = defaultdict(lambda: defaultdict(list))
    for tx in all_tx:
        tx_month = tx.date.month
        tx_by_month_account[tx_month][tx.account].append(tx)

    carryovers = defaultdict(float)
    jan1 = date(current_year, 1, 1)
    carryover_tx = Transaction.objects.filter(
        account__in=deposit_accounts,
        date=jan1,
        is_carryover=True
    )
    for tx in carryover_tx:
        carryovers[tx.account.id] += float(tx.amount)

    monthly_data = []
    ytd_debits = 0
    ytd_credits = 0
    running_balances = carryovers.copy()

    for m in range(1, current_month + 1):
        month_name = calendar.month_name[m]
        is_future = m > current_month
        month_accounts = []
        total_start = 0
        total_end = 0
        total_debit = 0
        total_credit = 0

        for acct in deposit_accounts:
            txs = [t for t in tx_by_month_account[m].get(acct, []) if not t.is_carryover]
            debit = sum(float(t.debit or 0) for t in txs)
            credit = sum(float(t.credit or 0) for t in txs)
            computed_change = credit - debit

            beginning_balance = running_balances[acct.id]
            ending_balance = beginning_balance + computed_change
            match = round(credit - debit, 2) == round(ending_balance - beginning_balance, 2)

            running_balances[acct.id] = ending_balance

            total_start += beginning_balance
            total_end += ending_balance
            total_debit += debit
            total_credit += credit

            ytd_debits += debit
            ytd_credits += credit

            month_accounts.append({
                'account': acct,
                'transactions': txs,
                'debit': debit,
                'credit': credit,
                'computed_change': credit - debit,
                'actual_change': ending_balance - beginning_balance,
                'beginning_balance': beginning_balance,
                'ending_balance': ending_balance,
                'match': match,
                'is_dormant': acct.name in dormant,
            })

        month_summary_match = round(total_credit - total_debit, 2) == round(total_end - total_start, 2)

        monthly_data.append({
            'month': m,
            'month_name': month_name,
            'year': current_year,
            'is_future': is_future,
            'accounts': month_accounts,
            'summary': {
                'total_start': total_start,
                'total_end': total_end,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'computed_change': total_credit - total_debit,
                'actual_change': total_end - total_start,
                'match': month_summary_match,
            },
            'ytd_summary': {
                'debit': ytd_debits,
                'credit': ytd_credits,
                'diff': ytd_credits - ytd_debits
            },
            'is_selected': m == selected_month
        })

    monthly_data.reverse()

    return render(request, 'budget/complex_algorithm.html', {
        'monthly_data': monthly_data,
        'current_month': current_month,
        'current_year': current_year,
        'selected_month': selected_month,
    })

def add_transaction(request):
    form = TransactionForm(request.POST or None)
    selected_account_id = request.GET.get("account_id") or request.POST.get("account")
    recent_transactions = []

    if selected_account_id:
        recent_transactions = Transaction.objects.filter(account_id=selected_account_id).order_by('-date')[:10]

    if request.method == 'POST':
        if form.is_valid():
            transaction = form.save()
            if 'save_and_add_another' in request.POST:
                return redirect(f"{request.path}?account_id={transaction.account.id}")
            return redirect('budget:dashboard')

    return render(request, 'budget/add_transaction.html', {
        'form': form,
        'recent_transactions': recent_transactions,
    })

def add_transfer(request):
    form = TransferForm(request.POST or None)
    recent_transfers = []

    from_account_id = request.GET.get('from_account') or request.POST.get('from_account')
    to_account_id = request.GET.get('to_account') or request.POST.get('to_account')

    if from_account_id or to_account_id:
        recent_transfers = Transfer.objects.filter(
            Q(from_account_id=from_account_id) | Q(to_account_id=to_account_id)
        ).order_by('-date')[:10]

    if request.method == 'POST':
        form = TransferForm(request.POST)
        if form.is_valid():
            transfer = form.save()

            if 'save_and_add_another' in request.POST:
                return redirect(f"{request.path}?from_account={transfer.from_account.id}&to_account={transfer.to_account.id}")
            return redirect('budget:dashboard')
        
        else:
            form = TransferForm()

    # Add transaction objects for display
    for transfer in recent_transfers:
        txs = transfer.transaction_set.all()
        transfer.from_tx = next((tx for tx in txs if tx.account == transfer.from_account), None)
        transfer.to_tx = next((tx for tx in txs if tx.account == transfer.to_account), None)

    return render(request, 'add_transfer.html', {
        'form': form,
        'recent_transfers': recent_transfers,
    })

def recent_transactions_ajax(request):
    account_id = request.GET.get('account_id')
    if not account_id:
        return JsonResponse({'html': ''})

    transactions = Transaction.objects.filter(account_id=account_id).order_by('-date')[:10]
    html = render_to_string('partials/recent_transactions.html', {'recent_transactions': transactions})
    return JsonResponse({'html': html})

def recent_transfers_ajax(request):
    from_account_id = request.GET.get('from_account')
    to_account_id = request.GET.get('to_account')
    debit_transfer_type = request.GET.get('')

    if not from_account_id or not to_account_id:
        return JsonResponse({'html': ''})

    transfers = Transfer.objects.filter(
        Q(from_account_id=from_account_id, to_account_id=to_account_id) |
        Q(from_account_id=to_account_id, to_account_id=from_account_id)
    ).order_by('-date')[:10]

    for transfer in transfers:
        txs = transfer.transaction_set.all()
        transfer.from_tx = next((tx for tx in txs if tx.account == transfer.from_account), None)
        transfer.to_tx = next((tx for tx in txs if tx.account == transfer.to_account), None)

    html = render_to_string('partials/recent_transfers.html', {'recent_transfers': transfers})
    # print("From:", from_account_id, "To:", to_account_id)
    # print("Transfer count:", transfers.count())
    return JsonResponse({'html': html})

def charts_view(request):
    # BAR CHART: Total Spend by Month
    monthly_spend_qs = Transaction.objects.filter(
        subcategory__isnull=False,
        subcategory__category__is_expense=True,
        account__account_type__in=["Deposit", "Charge"]
    ).exclude(subcategory__name__iexact="Transfer between accounts")

    monthly_totals = (
        monthly_spend_qs
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('debit'))
        .order_by('month')
    )

    monthly_labels = [m['month'].strftime("%B %Y") for m in monthly_totals]
    monthly_data = [float(m['total'] or 0) for m in monthly_totals]

    # DOUGHNUT CHART
    account_totals = (
        monthly_spend_qs
        .values('account__name')
        .annotate(total=Sum('debit'))
        .order_by('-total')
    )

    account_labels = [a['account__name'] for a in account_totals]
    account_data = [float(a['total'] or 0) for a in account_totals]
    total_spend = sum(account_data)

    # TREEMAP
    category_totals = (
        monthly_spend_qs
        .values('subcategory__category__name')
        .annotate(total=Sum('debit'))
        .order_by('-total')
    )

    treemap_labels = [c['subcategory__category__name'] for c in category_totals]
    treemap_data = [float(c['total'] or 0) for c in category_totals]

    # LINE CHART: Spend by Category by Month
    spend_by_month_category = (
        Transaction.objects.filter(
            account__account_type__in=["Deposit", "Charge"],
            subcategory__category__is_expense=True
        )
        .annotate(year=ExtractYear("date"), month=ExtractMonth("date"))
        .values("subcategory__category__name", "year", "month")
        .annotate(total=Sum("debit"))
        .order_by("year", "month")
    )

    month_keys = sorted({(r["year"], r["month"]) for r in spend_by_month_category})
    line_labels = [f"{month_name[m[1]]} {m[0]}" for m in month_keys]
    month_idx_map = {k: i for i, k in enumerate(month_keys)}

    from collections import defaultdict
    line_series = defaultdict(lambda: [0] * len(month_keys))

    for row in spend_by_month_category:
        idx = month_idx_map[(row["year"], row["month"])]
        cat = row["subcategory__category__name"]
        line_series[cat][idx] = float(row["total"] or 0)

    # PIE CHART
    pie_qs = Transaction.objects.filter(
        account__account_type__in=["Deposit", "Charge"],
        subcategory__category__is_expense=True
    )

    pie_totals = (
        pie_qs
        .values('subcategory__category__name')
        .annotate(total=Sum('debit'))
        .order_by('-total')
    )

    pie_labels = [p['subcategory__category__name'] for p in pie_totals]
    pie_data = [float(p['total'] or 0) for p in pie_totals]

    # CASH FLOW CHART
    # Cash Flow Calculation
    qs = Transaction.objects.filter(is_carryover=False)

    #This section is used to debug and visualize the monthly transaction breakdown in the console.  
    #    run python manage.py debug_cash_flow to generate a CSV file with the data
    '''

    from collections import defaultdict

    monthly_tx = defaultdict(list)

    for tx in qs.order_by("date"):
        month_str = tx.date.strftime("%b %Y")
        monthly_tx[month_str].append({
            "date": tx.date,
            "account": tx.account.name,
            "subcategory": tx.subcategory.name,
            "category": tx.subcategory.category.name,
            "amount": tx.amount,
            "credit": tx.credit,
            "debit": tx.debit,
            "is_income": tx.subcategory.category.is_income,
            "is_expense": tx.subcategory.category.is_expense,
        })

   
   
    for month, txns in monthly_tx.items():
        print(f"\n📆 {month}")
        for tx in txns:
            print(f"  {tx['date']} | {tx['account'][:15]:<15} | {tx['subcategory'][:20]:<20} | {tx['category'][:18]:<18} | "
                f"${tx['amount']:>8.2f} | Cr: {tx['credit'] or 0:>8.2f} | Db: {tx['debit'] or 0:>8.2f} | "
                f"Income: {tx['is_income']} | Expense: {tx['is_expense']}")

    '''

    net_qs_data = (
        qs.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(
            income=Sum("amount", filter=Q(subcategory__category__is_income=True)),
            expenses=Sum("amount", filter=Q(subcategory__category__is_expense=True)),
            debt=Sum(
                "amount",
                filter=Q(
                    subcategory__name="Credit Card Payments",
                    subcategory__category__name="Transfers (Internal)",
                    account__account_type="Charge",
                    credit__gt=0
                )
            )
        )          
        .order_by("month")
    )
    
    net_labels = [entry["month"].strftime("%b %Y") for entry in net_qs_data]
    net_income_data = [float(entry["income"] or 0) for entry in net_qs_data]
    net_expense_data = [float(entry["expenses"] or 0) for entry in net_qs_data]
    net_debt_data = [float(entry["debt"] or 0) for entry in net_qs_data]
    net_cash_data = [i + e for i, e in zip(net_income_data, net_expense_data)]
    liquidity_data = [i + e - d for i, e, d in zip(net_income_data, net_expense_data, net_debt_data)]

    monthly_balances = get_monthly_balances()
    balance_labels = net_labels  # ← exact match with net chart
    start_balances = []
    end_balances = []

    for label in net_labels:
        # label is like "Jan 2025"
        bal = monthly_balances.get(label)
        if bal:
            try:
                start_balances.append(float(bal['start']) if bal['start'] is not None else 0.0)
                end_balances.append(float(bal['end']) if bal['end'] is not None else 0.0)
            except Exception as e:
                start_balances.append(0.0)
                end_balances.append(0.0)
        else:
            start_balances.append(0.0)
            end_balances.append(0.0)

        
    for i, label in enumerate(net_labels):
        start = start_balances[i]
        income = net_income_data[i]
        expense = net_expense_data[i]
        debt = -net_debt_data[i]
        end = end_balances[i]

        expected_end = start + income + expense + debt
        diff = round(expected_end - end, 2)

        print(f"{label}:")
        print(f"  Start:   ${start:,.2f}")
        print(f"  Income:  ${income:,.2f}")
        print(f"  Expense: ${expense:,.2f}")
        print(f"  Debt:    ${debt:,.2f}")
        print(f"  Expected End: ${expected_end:,.2f}")
        print(f"  Actual End:   ${end:,.2f}")
        print(f"  ❗ Difference: ${diff:,.2f}")

    
    context = {
        'monthly_labels': monthly_labels,
        'monthly_data': monthly_data,  # ✅ bar chart data
        'account_labels': account_labels,
        'account_data': account_data,
        'total_spend': f"${total_spend:.2f}",
        'treemap_labels': treemap_labels,
        'treemap_data': treemap_data,
        'line_labels': line_labels,
        'line_data': dict(line_series),
        'pie_labels': pie_labels,
        'pie_data': pie_data,
        'net_labels': net_labels,
        'net_income_data': net_income_data,
        'net_expense_data': net_expense_data,
        'net_debt_data': net_debt_data,
        'net_cash_data': net_cash_data,
        'liquidity_data': liquidity_data,
        'monthly_balances': monthly_balances,
        'balance_labels': balance_labels,
        'start_balances': start_balances,
        'end_balances': end_balances,
        }
    
 
    return render(request, "budget/charts.html", context)

def get_monthly_balances():
    deposit_accounts = Account.objects.filter(account_type='Deposit')

    # Get all months with at least one transaction
    months = (
        Transaction.objects
        .filter(account__in=deposit_accounts)
        .dates('date', 'month')
        .order_by('date')
    )

    balances = OrderedDict()

    for dt in months:
        year = dt.year
        month = dt.month
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])

        if month == 1:
            start_balance = (
            Transaction.objects
            .filter(account__in=deposit_accounts, date__lte=first_day, is_carryover=True)
            .aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            )
            
        else:
            start_balance = (
                Transaction.objects
                .filter(account__in=deposit_accounts, date__lt=first_day)
                .aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            )

        end_balance = (
            Transaction.objects
            .filter(account__in=deposit_accounts, date__lte=last_day)
            .aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        )

        balances[first_day.strftime('%b %Y')] = {
            'start': start_balance,
            'end': end_balance
        }

    print(f"Month: {first_day.strftime('%b %Y')}, Start: {start_balance}, End: {end_balance}")

    return balances

def gig_entry(request):
    """
    Create a new gig shift + per-company entries.
    """
    if request.method == "POST":
        action = request.POST.get("action", "save")  # "save" or "save_add"
        shift_form = GigShiftForm(request.POST)
        formset = GigCompanyFormSet(request.POST)

        if shift_form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    shift = shift_form.save()
                    formset.instance = shift
                    formset.save()

                    # --- Auto-fill company_mix_note from companies on this shift ---
                    codes_qs = (
                        shift.company_entries
                        .filter(company__isnull=False)
                        .values_list("company__code", flat=True)
                        .distinct()
                    )
                    codes = sorted(codes_qs)
                    shift.company_mix_note = "/".join(codes)
                    shift.save(update_fields=["company_mix_note"])

                if action == "save_add":
                    messages.success(request, "Shift saved. You can add another one.")
                    return redirect("gigs:gig_entry")
                else:
                    messages.success(request, "Shift saved.")
                    return redirect("gigs:gig_summary")
            except Exception:
                shift_form.add_error(
                    None,
                    "An unexpected error occurred while saving this shift. "
                    "Nothing was saved. Please try again.",
                )
        # invalid forms → fall through and re-render with errors
    else:
        shift_form = GigShiftForm(initial={"date": timezone.now().date()})
        formset = GigCompanyFormSet()

    return render(
        request,
        "gigs/gig_entry.html",
        {"shift_form": shift_form, "formset": formset},
    )

def _month_range(year: int, month: int):
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end

def _next_month(d: date) -> date:
    """Helper: first day of the next month."""
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1, day=1)
    return d.replace(month=d.month + 1, day=1)

def gig_summary(request):
    today = timezone.localdate()
    current_month_start = today.replace(day=1)

    # --- 1) Parse requested month (YYYY-MM) or default to current month ---
    month_param = request.GET.get("month")
    if month_param:
        try:
            year, month = map(int, month_param.split("-"))
            selected_month_start = date(year, month, 1)
        except Exception:
            selected_month_start = current_month_start
    else:
        selected_month_start = current_month_start

    selected_month_end = _next_month(selected_month_start)

    # --- 2) Get list of months that actually have gig shifts (for dropdown) ---
    all_dates = (
        GigShift.objects
        .order_by("-date")
        .values_list("date", flat=True)
        .distinct()
    )
    months = sorted({d.replace(day=1) for d in all_dates}, reverse=True)

    # --- 3) Base queryset for the selected month ---
    base_qs = (
        GigShift.objects
        .filter(date__gte=selected_month_start, date__lt=selected_month_end)
        .prefetch_related("company_entries", "company_entries__company")
    )

    using_fallback = False

    # If no shifts for requested month, fall back to most recent month with data
    if not base_qs.exists() and months:
        fallback_start = months[0]
        if fallback_start != selected_month_start:
            using_fallback = True
            selected_month_start = fallback_start
            selected_month_end = _next_month(selected_month_start)
            base_qs = (
                GigShift.objects
                .filter(date__gte=selected_month_start, date__lt=selected_month_end)
                .prefetch_related("company_entries", "company_entries__company")
            )

    shifts_qs = base_qs

    # --- 4) Company filter (by code) ---
    company_code = request.GET.get("company", "ALL")

    # Companies that appear in this month (from base_qs, before company filter)
    companies_for_month = (
        GigCompany.objects
        .filter(gig_entries__shift__in=base_qs)
        .distinct()
        .order_by("code")
    )

    if company_code and company_code != "ALL":
        shifts_qs = shifts_qs.filter(company_entries__company__code=company_code).distinct()

    # --- 5) Chart data based on filtered shifts ---
    labels = []
    gross_data = []
    net_data = []
    miles_data = []
    hourly_gross_data = []
    hourly_net_data = []

    ordered_shifts = shifts_qs.order_by("date", "start_time")

    for shift in ordered_shifts:
        labels.append(shift.date.strftime("%m/%d"))
        gross_data.append(float(shift.total_gross or 0))
        net_data.append(float(shift.net_after_gas or 0))
        miles_data.append(float(shift.miles or 0))
        hourly_gross_data.append(float(shift.gross_per_hour or 0))
        hourly_net_data.append(float(shift.net_per_hour or 0))

    context = {
        "shifts": ordered_shifts,
        "selected_month": selected_month_start,
        "current_month": current_month_start,
        "months": months,
        "using_fallback": using_fallback,

        # chart data as JSON strings
        "chart_labels": json.dumps(labels),
        "chart_gross": json.dumps(gross_data),
        "chart_net": json.dumps(net_data),
        "chart_miles": json.dumps(miles_data),
        "chart_hourly_gross": json.dumps(hourly_gross_data),
        "chart_hourly_net": json.dumps(hourly_net_data),

        # company filter context
        "company_code": company_code,
        "companies": companies_for_month,
    }

    return render(request, "gigs/gig_summary.html", context)

@login_required
def mileage_rate_settings(request):
    """
    Simple page to view and add mileage rates.
    """
    rates = MileageRate.objects.all()  # ordered by -effective_date due to Meta.ordering

    if request.method == "POST":
        form = MileageRateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Mileage rate saved.")
            return redirect("mileage_rate_settings")
    else:
        form = MileageRateForm()

    return render(
        request,
        "gigs/mileage_rate_settings.html",
        {
            "form": form,
            "rates": rates,
        },
    )

#Calendar Views
User = get_user_model()  #remember what the User model is, so I can query it later

@ensure_csrf_cookie
def main_calendar(request):
    """
    Main calendar view showing all events.
    """
    events = 'Test Events Data'  # Placeholder for actual event data retrieval logic

    # image directory for calendar page backgrounds
    # 1. Get the absolute path to your static images folder
    photos_dir = Path(settings.BASE_DIR) / "static" / "budget" / "calendar_photos"
      
    # match jpg/JPG/jpeg/JPEG (and optionally png)
    exts = {".jpg", ".jpeg", ".png"}
    image_files = [p for p in photos_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]

    # Convert to STATIC-relative paths for `{% static ... %}`
    image_list = [f"budget/calendar_photos/{p.name}" for p in image_files]

    weather_ctx = get_cached_weather()

    # Pass daily events to template
    owner = get_calendar_owner()  # same owner logic you're using elsewhere
    today = timezone.localdate()
    start_dt = timezone.make_aware(datetime.combine(today, time.min))
    end_dt = timezone.make_aware(datetime.combine(today, time.max))

    today_events = (CalendarEvent.objects
        .filter(user=owner, start_dt__lte=end_dt, end_dt__gte=start_dt)
        .order_by("start_dt"))
        
    context = {
    "events": events if events else [],
    "image_list": image_list if image_list else [],
    "today_events": today_events,
    "today": today,
    **weather_ctx,
}

    context.update(kiosk_context(request))
    return render(request, 'calendar/calendar_home.html', context)

@require_GET
def weather_fragment(request):
    """
    Returns rendered HTML for just the weather block.
    """
    weather_ctx = get_cached_weather()
    html = render_to_string("partials/_weather_block.html", weather_ctx, request=request)
    return JsonResponse({"ok": True, "html": html})

def get_calendar_owner():
    # 1) If explicitly configured, try it
    username = getattr(settings, "KIOSK_CALENDAR_OWNER_USERNAME", None)
    if username:
        owner = User.objects.filter(username=username).first()
        if owner:
            return owner

    # 2) Fallback: first superuser (works on wall tablet + admin setups)
    owner = User.objects.filter(is_superuser=True).order_by("id").first()
    if owner:
        return owner

    # 3) Final fallback: first user
    owner = User.objects.order_by("id").first()
    if owner:
        return owner

    raise RuntimeError(
        "No users exist in this database. Create a superuser with: python manage.py createsuperuser"
    )

@ensure_csrf_cookie
def calendar_day(request):
    owner = get_calendar_owner()

    today = timezone.localdate()   # actual today
    day = today                    # default context day = today
    
    date_str = request.GET.get("date")
    if date_str:
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    start_dt = timezone.make_aware(datetime.combine(day, time.min))
    end_dt = timezone.make_aware(datetime.combine(day, time.max))

    prev_day = day - timedelta(days=1)
    next_day = day + timedelta(days=1)

    events = (CalendarEvent.objects
              .filter(user=owner, start_dt__lte=end_dt, end_dt__gte=start_dt)
              .order_by("start_dt"))
    
    all_day_events = []
    event_blocks = []
    for e in events:
        if e.all_day:
            all_day_events.append(e)
            continue

        s = timezone.localtime(e.start_dt)
        en = timezone.localtime(e.end_dt)

        start_min = s.hour * 60 + s.minute
        end_min = en.hour * 60 + en.minute

        # guard
        if end_min <= start_min:
            end_min = start_min + 30

        event_blocks.append({
            "id": e.id,
            "title": e.title,
            "person": e.person,
            # "all_day": e.all_day,
            "location": e.location,
            "notes": e.notes,
            "start_dt": s,
            "end_dt": en,
            "top": start_min,                  # px, 1px per minute
            "height": max(28, end_min - start_min),
        })

    #Calendar day view columns:
    # Build overlap groups (simple sweep)
    blocks = sorted(event_blocks, key=lambda b: (b["top"], b["top"] + b["height"]))

    active = []
    for b in blocks:
        b_start = b["top"]
        b_end = b["top"] + b["height"]   #optional; not needed

        # drop inactive
        active = [a for a in active if (a["top"] + a["height"]) > b_start]

        # find used columns
        used = {a["col"] for a in active if "col" in a}
        col = 0
        while col in used:
            col += 1
        b["col"] = col

        active.append(b)

        # compute current max columns among active
        max_cols = max(a["col"] for a in active) + 1
        for a in active:
            a["col_count"] = max_cols

    # special day handling
    special_items = []

    # fixed-date
    for s in CalendarSpecial.objects.all():
        occ = date(day.year, s.date.month, s.date.day) if s.recurring_yearly else s.date
        if occ == day:
            special_items.append({
                "title": s.title,
                "color_key": s.color_key,
                "special_type": s.special_type,
                "person": s.person,
                "notes": s.notes,
            })

    # rule-based
    for rs in CalendarRuleSpecial.objects.filter(is_enabled=True):
        occ = compute_rule_date(rs.rule_key, day.year)
        if occ == day:
            special_items.append({
                "title": rs.title_override or rs.get_rule_key_display(),
                "color_key": rs.color_key,
                "special_type": rs.special_type,
                "person": rs.person,
                "notes": rs.notes,
            })

    context = {
        "today": today,
        "day": day,
        "prev_day": prev_day,
        "next_day": next_day,
        "events": events,               # keep if you want for lists / all-day
        "all_day_events": all_day_events,
        "event_blocks": blocks,         # for grid
        "hours": range(24),
        "special_items": special_items,
    }

    context.update(kiosk_context(request))
    return render(request, "calendar/calendar_day.html", context)

@ensure_csrf_cookie
def calendar_week(request):
    owner = get_calendar_owner()

    today = timezone.localdate()  # actual today
    day = today                   # context day defaults to today

    date_str = request.GET.get("date")
    if date_str:
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Make Sunday the first day of the week
    # Python weekday(): Mon=0..Sun=6
    # We want an offset where Sun -> 0, Mon -> 1, ... Sat -> 6
    sunday_offset = (day.weekday() + 1) % 7
    week_start = day - timedelta(days=sunday_offset)
    week_end = week_start + timedelta(days=6)

    start_dt = timezone.make_aware(datetime.combine(week_start, time.min))
    end_dt = timezone.make_aware(datetime.combine(week_end, time.max))

    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    events = (CalendarEvent.objects
              .filter(user=owner, start_dt__lte=end_dt, end_dt__gte=start_dt)
              .order_by("start_dt"))

    # group events by date
    events_by_day = {}
    for e in events:
        d = timezone.localtime(e.start_dt).date()
        events_by_day.setdefault(d, []).append(e)

    days = [week_start + timedelta(days=i) for i in range(7)]

    inject_specials_into_events_by_day(events_by_day, week_start, week_end)
    
    context = {
        "today": today,
        "day": day,  # handy for links
        "week_start": week_start,
        "week_end": week_end,
        "prev_week": prev_week,
        "next_week": next_week,
        "days": days,
        "events_by_day": events_by_day,
        
        }

    context.update(kiosk_context(request))
    return render(request, "calendar/calendar_week.html", context)

@ensure_csrf_cookie
def calendar_month(request):
    # pick month/year from querystring or default to current
    owner = get_calendar_owner()

    today = timezone.localdate()
    year = int(request.GET.get("y", today.year))
    month = int(request.GET.get("m", today.month))

    prev_y, prev_m = add_month(year, month, -1)
    next_y, next_m = add_month(year, month, +1)

    first_day = date(year, month, 1)
    _, last_day_num = monthrange(year, month)
    last_day = date(year, month, last_day_num)

    # build grid start (Sunday) -> grid end (Saturday)
    grid_start = first_day - timedelta(days=(first_day.weekday() + 1) % 7)
    grid_end = last_day + timedelta(days=(6 - ((last_day.weekday() + 1) % 7)))

    start_dt = timezone.make_aware(datetime.combine(grid_start, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(grid_end, datetime.max.time()))

    events = (CalendarEvent.objects
              .filter(user=owner, start_dt__lte=end_dt, end_dt__gte=start_dt)
              .order_by("start_dt"))

    # group by date for easy template rendering
    events_by_day = {}
    for e in events:
        day = timezone.localtime(e.start_dt).date()
        events_by_day.setdefault(day, []).append(e)

    inject_specials_into_events_by_day(events_by_day, grid_start, grid_end)

    # build list of weeks (each week is 7 dates)
    days = []
    d = grid_start
    while d <= grid_end:
        days.append(d)
        d += timedelta(days=1)

    weeks = [days[i:i+7] for i in range(0, len(days), 7)]

    context = {
        "weeks": weeks,
        "events_by_day": events_by_day,
        "year": year,
        "month": month,
        "today": today,
        "prev_y": prev_y, "prev_m": prev_m,
        "next_y": next_y, "next_m": next_m,
    }
    context.update(kiosk_context(request))
    return render(request, "calendar/calendar_month.html", context)
        
def kiosk_edit_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not can_user_edit(request):
            # Optional: preserve kiosk=1 when redirecting
            if kiosk_enabled(request):
                url = reverse("calendar:calendar_home")
                return redirect(f"{url}?kiosk=1")
            return redirect("calendar:calendar_month")
        return view_func(request, *args, **kwargs)
    return _wrapped
    
def kiosk_context(request):
    is_kiosk = kiosk_enabled(request)
    by = request.session.get("kiosk_unlocked_by", "N/A")
    labels = getattr(settings, "KIOSK_PIN_LABELS", {})
    label = labels.get(by, by)

    until_str = request.session.get("kiosk_unlocked_until")
    until_disp = None
    if until_str:
        until = parse_datetime(until_str)
        if until and timezone.is_naive(until):
            until = timezone.make_aware(until)
        if until:
            until_disp = date_format(timezone.localtime(until), "g:i A") #e.g. "3:45 PM"
    
    return {
        "is_kiosk": is_kiosk,
        "kiosk_qs": "kiosk=1" if is_kiosk else "",
        "kiosk_qs_prefix": "?kiosk=1" if is_kiosk else "",
        "kiosk_qs_amp": "&kiosk=1" if is_kiosk else "",
        "can_edit": can_user_edit(request),
        "kiosk_unlocked_by": by,
        "kiosk_unlocked_label": label,
        "kiosk_unlocked_until_display": until_disp,
    }

def kiosk_is_unlocked(request):
    until_str = request.session.get("kiosk_unlocked_until")
    if not until_str:
        return False

    until = parse_datetime(until_str)
    if until is None:
        return False

    if timezone.is_naive(until):
        until = timezone.make_aware(until)

    return timezone.now() < until

def kiosk_unlock(request):
    if request.method != "POST":
        return JsonResponse({"ok": False}, status=405)

    pin = (request.POST.get("pin") or "").strip()
    return_to = request.POST.get("return_to") or "/calendar/"

    pins = getattr(settings, "KIOSK_PINS", {})
    matched_key = None
    for key, configured_pin in pins.items():
        if pin == str(configured_pin):
            matched_key = key
            break

    if not matched_key:
        ctx = kiosk_context(request)
        context = {"error": "Invalid PIN.", "return_to": return_to}
        context.update(ctx)
        return render(request, "calendar/kiosk_unlock.html", context, status=403)

    mins = int(getattr(settings, "KIOSK_UNLOCK_MINUTES", 10))
    until = timezone.now() + timedelta(minutes=mins)
    request.session["kiosk_unlocked_until"] = until.isoformat()
    request.session["kiosk_unlocked_by"] = matched_key

    if "kiosk=1" not in return_to:
        joiner = "&" if "?" in return_to else "?"
        return_to = f"{return_to}{joiner}kiosk=1"

    return redirect(return_to)

def kiosk_unlocked_by(request):
    return request.session.get("kiosk_unlocked_by")

def kiosk_unlock_page(request):
    """
    Shows the PIN entry page (GET).
    The actual unlock happens in kiosk_unlock() via POST.
    """
    ctx = kiosk_context(request)
    is_kiosk = ctx.get("is_kiosk", False)
    default_return = "/calendar/?kiosk=1" if is_kiosk else "/calendar/"
    return_to = request.GET.get("return_to") or default_return

    context = {
        "return_to": return_to,
        "error": request.GET.get("error", ""),
        "hide_kiosk_bar": True,
    }
    context.update(ctx)
    return render(request, "calendar/kiosk_unlock.html", context)

@require_POST
def kiosk_lock(request):
    request.session.pop("kiosk_unlocked_until", None)
    request.session.pop("kiosk_unlocked_by", None)
    request.session.modified = True
    return JsonResponse({"ok": True})
    
def kiosk_enabled(request) -> bool:
    if request.GET.get("kiosk") == "1":
        request.session["kiosk_enabled"] = True
        return True

    if request.GET.get("kiosk") == "0":
        request.session["kiosk_enabled"] = False
        return False

    if "kiosk_enabled" not in request.session and looks_like_tablet(request):
        request.session["kiosk_enabled"] = True

    return bool(request.session.get("kiosk_enabled", False))

def looks_like_tablet(request) -> bool:
    ua = (request.META.get("HTTP_USER_AGENT") or "").lower()
    
    # obvious tablets
    if any(x in ua for x in ["ipad", "android"]) and "mobile" not in ua:
        return True
    return False

def edit_actor(request) -> str:
    # Server edits: not kiosk => "server"
    if not kiosk_enabled(request):
        return "server"

    # Kiosk edits: whoever unlocked (mike/wife)
    return request.session.get("kiosk_unlocked_by") or "kiosk"

def add_month(year, month, delta):
    # delta = -1 or +1
    new_month = month + delta
    new_year = year
    if new_month == 0:
        new_month = 12
        new_year -= 1
    elif new_month == 13:
        new_month = 1
        new_year += 1
    return new_year, new_month

@ensure_csrf_cookie
@kiosk_edit_required
def calendar_event_create(request):
    owner = get_calendar_owner()

    ctx = kiosk_context(request)
    is_kiosk = ctx.get("is_kiosk", False)

    default_return = "/calendar/?kiosk=1" if is_kiosk else "/calendar/"
    return_to = request.GET.get("return_to") or default_return

    # date prefill: ?date=YYYY-MM-DD
    date_str = request.GET.get("date")
    default_date = timezone.localdate()
    if date_str:
        try:
            default_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    if request.method == "POST":
        # IMPORTANT: for POST, take return_to from the hidden input first
        return_to = request.POST.get("return_to") or return_to

        title = (request.POST.get("title") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        location = (request.POST.get("location") or "").strip()
        person = request.POST.get("person", "mike")
        all_day = request.POST.get("all_day") == "on"

        if not title:
            context = {"date": default_date, "return_to": return_to, "event": None, "error": "Title is required."}
            context.update(ctx)
            return render(request, "calendar/calendar_event_form.html", context)

        if all_day:
            start_dt = timezone.make_aware(datetime.combine(default_date, time.min))
            end_dt = timezone.make_aware(datetime.combine(default_date, time.max))
        else:
            start_time = request.POST.get("start_time", "09:00")
            end_time = request.POST.get("end_time", "10:00")

            st = datetime.strptime(start_time, "%H:%M").time()
            et = datetime.strptime(end_time, "%H:%M").time()

            if et <= st:
                context = {"date": default_date, "return_to": return_to, "event": None, "error": "End time must be after start time."}
                context.update(ctx)
                return render(request, "calendar/calendar_event_form.html", context)

            start_dt = timezone.make_aware(datetime.combine(default_date, st))
            end_dt = timezone.make_aware(datetime.combine(default_date, et))

        event = CalendarEvent.objects.create(
            user=owner,
            title=title,
            person=person,
            start_dt=start_dt,
            end_dt=end_dt,
            all_day=all_day,
            notes=notes,
            location=location,
        )

        actor = edit_actor(request)
        event.created_by = actor
        event.last_edited_by = actor
        event.save(update_fields=["created_by", "last_edited_by"])

        return redirect(return_to)

    # GET
    context = {"date": default_date, "return_to": return_to, "event": None}
    context.update(ctx)
    return render(request, "calendar/calendar_event_form.html", context)

@ensure_csrf_cookie
@kiosk_edit_required
def calendar_event_edit(request, event_id):
    owner = get_calendar_owner()
    event = get_object_or_404(CalendarEvent, id=event_id, user=owner)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        notes = request.POST.get("notes", "").strip()
        location = request.POST.get("location", "").strip()
        person = request.POST.get("person", "mike")
        all_day = request.POST.get("all_day") == "on"

        if not title:
            return render(request, "calendar/calendar_event_form.html", {
                "date": event.start_dt.date(),
                "return_to": request.POST.get("return_to", "/calendar/"),
                "error": "Title is required.",
                "event": event,
            })
        
        # date is locked for MVP; we can add change-date later
        d = event.start_dt.date()

        if all_day:
            start_dt = timezone.make_aware(datetime.combine(d, time.min))
            end_dt = timezone.make_aware(datetime.combine(d, time.max))
        else:
            st = datetime.strptime(request.POST.get("start_time", "09:00"), "%H:%M").time()
            et = datetime.strptime(request.POST.get("end_time", "10:00"), "%H:%M").time()
            if et <= st:
                return render(request, "calendar/calendar_event_form.html", {
                    "date": d,
                    "return_to": request.POST.get("return_to", "/calendar/"),
                    "error": "End time must be after start time.",
                    "event": event,
                })
            start_dt = timezone.make_aware(datetime.combine(d, st))
            end_dt = timezone.make_aware(datetime.combine(d, et))

        event.title = title
        event.notes = notes
        event.location = location
        event.person = person
        event.all_day = all_day
        event.start_dt = start_dt
        event.end_dt = end_dt
        if not event.created_by:
            event.created_by = edit_actor(request)
        event.last_edited_by = edit_actor(request)

        event.save()

        return redirect(request.POST.get("return_to", "/calendar/"))
    
    context = {
        "date": event.start_dt.date(),
        "return_to": request.GET.get("return_to", "/calendar/"),
        "event": event,
        }
    context.update(kiosk_context(request))
    return render(request, "calendar/calendar_event_form.html", context)

@ensure_csrf_cookie
@kiosk_edit_required
def calendar_event_delete(request, event_id):
    owner = get_calendar_owner()
    event = get_object_or_404(CalendarEvent, id=event_id, user=owner)

    ctx = kiosk_context(request)
    is_kiosk = ctx.get("is_kiosk", False)

    default_return = "/calendar/?kiosk=1" if is_kiosk else "/calendar/"
    return_to = request.GET.get("return_to") or default_return

    if request.method == "POST":
        event.delete()
        return redirect(request.POST.get("return_to") or default_return)
    
    context = {
        "event": event,
        "return_to": return_to,
    }

    context.update(ctx)
    return render(request, "calendar/calendar_event_delete.html", context)

def calendar_event_detail(request, event_id):
    owner = get_calendar_owner()
    event = get_object_or_404(CalendarEvent, id=event_id, user=owner)

    ctx = kiosk_context(request)
    is_kiosk = ctx.get("is_kiosk", False)

    default_return = "/calendar/?kiosk=1" if is_kiosk else "/calendar/"
    return_to = request.GET.get("return_to") or default_return

    context = {
        "event": event,
        "return_to": return_to,
    }
    context.update(ctx)
    return render(request, "calendar/calendar_event_detail.html", context)

def can_user_edit(request):
    # Server (not kiosk) = always editable
    if not kiosk_enabled(request):
        return True

    # Tablet kiosk = only editable if unlocked
    return kiosk_is_unlocked(request)

def calendar_entry(request):
    today = timezone.localdate().strftime("%Y-%m-%d")
    if looks_like_tablet(request):
        return redirect(f"/calendar/week/?date={today}&kiosk=1")
    return redirect(f"/calendar/month/?y={timezone.localdate().year}&m={timezone.localdate().month}")

@require_GET
def health_ping(request):
    return JsonResponse({"ok": True})
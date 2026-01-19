from django.db.models import Sum, Q, Case, When, Value, F, DecimalField
from django.db.models.functions import ExtractMonth, ExtractYear, TruncMonth
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from collections import defaultdict, OrderedDict
from decimal import Decimal
from datetime import date

from .forms import TransactionForm, TransferForm
from .models import Account, Transaction, Transfer, Category, SubCategory

import calendar
from calendar import month_name, monthrange

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


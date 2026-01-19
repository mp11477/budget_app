from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone

from datetime import date

from .forms import GigShiftForm, GigCompanyFormSet, MileageRateForm
from .models import GigShift, GigCompany, MileageRate
from .queries import _month_range, _next_month

import json

def gig_entry(request):
    """
    Create or edit a GigShift and its per-company entries.

    - GET: renders an entry form for a new shift.
    - POST: validates and saves shift + inline company entries in a single DB transaction.

    Redirects:
      - back to the entry page if user chooses "Save and add another"
      - to summary page otherwise
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

def gig_summary(request):
    """
    Monthly gig summary dashboard.

    Behavior:
    - If month is selected, shows only that month.
    - If selected month has no data, falls back to most recent month with data.
    - Aggregates totals across shifts and company entries.
    """
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
    Manage MileageRate entries (effective_date + rate + optional note).

    Used for:
    - IRS mileage deduction assumptions
    - internal reporting consistency
    """
    rates = MileageRate.objects.all()  # ordered by -effective_date due to Meta.ordering

    if request.method == "POST":
        form = MileageRateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Mileage rate saved.")
            return redirect("gigs:mileage_rate_settings")
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

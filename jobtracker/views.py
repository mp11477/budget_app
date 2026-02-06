import csv
from fileinput import filename

from django.db.models import Case, When, Value, IntegerField, Count, Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

from datetime import timedelta 

from .forms import (JobForm, ApplicationForm, ApplicationEditForm, CompanyForm, CommunicationForm, ContactForm,
                    JobEditForm)
from .models import Job, Application, Communication, Company


def dashboard(request):
    """
    JobTracker dashboard.

    Shows quick pipeline stats and a follow-up queue so you can act fast.
    """
    today = timezone.localdate()

    # Follow-ups due (today or earlier) and not closed out
    followups_due = Application.objects.select_related("job", "job__company").filter(
        next_followup_date__isnull=False,
        next_followup_date__lte=today,
    ).exclude(status__in=["REJECTED", "WITHDRAWN"])

    # Pipeline counts
    pipeline = (
        Application.objects.values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )

    # add display labels
    status_label = dict(Application.Status.choices)
    for row in pipeline:
        row["label"] = status_label.get(row["status"], row["status"])

    context = {
        "current": "jobtracker",
        "today": today,
        "followups_due": followups_due[:25],
        "pipeline": pipeline,
    }
    return render(request, "jobtracker/jobtracker_dashboard.html", context)

def _add_query_param(url: str, key: str, value: str) -> str:
    parts = urlparse(url)
    q = parse_qs(parts.query)
    q[key] = [value]
    new_query = urlencode(q, doseq=True)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, new_query, parts.fragment))


def job_create(request):
    """
    Create a new Job entry.
    Supports ?next=... so you can return back to the originating form.
    If next is present, appends ?job_id=<new_job_id> so the caller can auto-select it.
    """
    next_url = request.GET.get("next") or request.POST.get("next") or ""

    if request.method == "POST":
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save()

            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(_add_query_param(next_url, "job_id", str(job.id)))

            return redirect("jobtracker:jobs_list")
    else:
        company_id = request.GET.get("company_id")
        if company_id:
            form = JobForm(initial={"company": company_id})
        else:
            form = JobForm()

    return render(
        request,
        "jobtracker/job_form.html",
        {"current": "jobtracker", "form": form, "next": next_url},
    )

def job_edit(request, job_id: int):
    """
    Edit a Job record.
    """
    job = get_object_or_404(Job.objects.select_related("company"), pk=job_id)

    if request.method == "POST":
        form = JobEditForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            return redirect("jobtracker:job_detail", job_id=job.id)
    else:
        form = JobEditForm(instance=job)

    return render(
        request,
        "jobtracker/job_edit.html",
        {"current": "jobtracker", "job": job, "form": form},
    )

def jobs_list(request):
    """
    List jobs being tracked.

    Includes application count to show what has momentum.
    """
    jobs = (
        Job.objects.select_related("company")
        .annotate(app_count=Count("applications"))
        .order_by("company__name", "-priority", "title")
    )
    return render(request, "jobtracker/jobs_list.html", {"current": "jobtracker", "jobs": jobs})

def job_detail(request, job_id: int):
    """
    Job detail page.

    Shows job fields + applications associated with this job.
    """
    job = get_object_or_404(Job.objects.select_related("company"), pk=job_id)
    apps = job.applications.order_by("-applied_date").all()
    return render(
        request,
        "jobtracker/job_detail.html",
        {"current": "jobtracker", "job": job, "apps": apps},
    )

def application_create(request):
    """
    Create a new Application and track status/follow-ups.
    """
    if request.method == "POST":
        form = ApplicationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("jobtracker:applications_list")
    else:
        job_id = request.GET.get("job_id")
        if job_id:
            form = ApplicationForm(initial={"job": job_id})
        else:
            form = ApplicationForm()

    return render(
        request,
        "jobtracker/application_form.html",
        {"current": "jobtracker", "form": form},
    )

def application_create_for_job(request, job_id: int):
    """
    Create an Application for a specific Job, with the job pre-selected/locked.
    """
    job = get_object_or_404(Job.objects.select_related("company"), pk=job_id)

    if request.method == "POST":
        form = ApplicationForm(request.POST, job_locked=job)
        if form.is_valid():
            app = form.save(commit=False)
            app.job = job  # belt & suspenders
            app.save()
            return redirect("jobtracker:application_detail", app_id=app.id)
    else:
        form = ApplicationForm(job_locked=job)

    return render(
        request,
        "jobtracker/application_form_for_job.html",
        {"current": "jobtracker", "job": job, "form": form},
    )

def applications_list(request):
    """
    List applications with optional filters.

    Query params:
    - status: one of Application.Status values (e.g. APPLIED)
    - due: "1" to show follow-ups due today or earlier (excluding terminal statuses)
    - q: search string across company/job/title/resume/cover letter
    - company: company id
    """
    days = (request.GET.get("days") or "").strip()
    today = timezone.localdate()
    qs = Application.objects.select_related("job", "job__company")
    week = (request.GET.get("week") or "").strip()

    if week == "1":
        # Sunday = 6 when using weekday() where Monday=0
        days_since_sunday = (today.weekday() + 1) % 7
        start_date = today - timedelta(days=days_since_sunday)
        qs = qs.filter(applied_date__gte=start_date)
    
    elif days.isdigit():
        n = int(days)
        if 1 <= n <= 365:
            start_date = today - timedelta(days=n - 1)
            qs = qs.filter(applied_date__gte=start_date)

    status = (request.GET.get("status") or "").strip()
    due = (request.GET.get("due") or "").strip()
    q = (request.GET.get("q") or "").strip()
    company_id = (request.GET.get("company") or "").strip()

    if status:
        qs = qs.filter(status=status)

    if company_id.isdigit():
        qs = qs.filter(job__company_id=int(company_id))

    if due == "1":
        qs = qs.filter(
            next_followup_date__isnull=False,
            next_followup_date__lte=today,
        ).exclude(status__in=["REJECTED", "WITHDRAWN"])

    if q:
        qs = qs.filter(
            Q(job__title__icontains=q)
            | Q(job__company__name__icontains=q)
            | Q(resume_version__icontains=q)
            | Q(cover_letter_version__icontains=q)
        )

    apps = (
        qs.annotate(
            followup_is_null=Case(
                When(next_followup_date__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("followup_is_null", "next_followup_date", "-applied_at", "-created_at")
    )

    # For dropdown
    companies = Company.objects.order_by("name")

    return render(
        request,
        "jobtracker/applications_list.html",
        {
            "current": "jobtracker",
            "apps": apps,
            "companies": companies,
            "filters": {
                "status": status,
                "due": due,
                "q": q,
                "company": company_id,
                "days": days,
                "week": week,
            },
        },
    )

def applications_export_csv(request):
    """
    Export applications as CSV using the SAME filters as applications_list.
    Intended for unemployment proof / audit logs.
    """
    today = timezone.localdate()
    qs = Application.objects.select_related("job", "job__company")

    #for filename during export
    range_label = "all"
    range_start = None
    range_end = today

    week = (request.GET.get("week") or "").strip()
    if week == "1":
        days_since_sunday = (today.weekday() + 1) % 7
        range_start = today - timedelta(days=days_since_sunday)
        qs = qs.filter(applied_date__gte=range_start)
        range_label = "this_week"

    elif days.isdigit():
        n = int(days)
        if 1 <= n <= 365:
            range_start = today - timedelta(days=n - 1)
            qs = qs.filter(applied_date__gte=range_start)
            range_label = f"last_{n}_days"

    status = (request.GET.get("status") or "").strip()
    due = (request.GET.get("due") or "").strip()
    q = (request.GET.get("q") or "").strip()
    company_id = (request.GET.get("company") or "").strip()
    days = (request.GET.get("days") or "").strip()

    if status:
        qs = qs.filter(status=status)

    if company_id.isdigit():
        qs = qs.filter(job__company_id=int(company_id))

    if due == "1":
        qs = qs.filter(
            next_followup_date__isnull=False,
            next_followup_date__lte=today,
        ).exclude(status__in=["REJECTED", "WITHDRAWN"])

    if days.isdigit():
        n = int(days)
        if 1 <= n <= 365:
            start_date = today - timedelta(days=n - 1)
            qs = qs.filter(applied_date__gte=start_date)

    if q:
        qs = qs.filter(
            Q(job__title__icontains=q)
            | Q(job__company__name__icontains=q)
            | Q(resume_version__icontains=q)
            | Q(cover_letter_version__icontains=q)
        )

    apps = (
        qs.annotate(
            followup_is_null=Case(
                When(next_followup_date__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("followup_is_null", "next_followup_date", "-applied_at", "-applied_date", "-created_at")
    )

    resp = HttpResponse(content_type="text/csv")
    if range_start:
        filename = f"applications_{range_label}_{range_start}_to_{range_end}.csv"
    else:
        filename = "applications_all.csv"

    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
  
    w = csv.writer(resp)
    w.writerow([
        "Company",
        "Job Title",
        "Status",
        "Applied At",
        "Applied Date",
        "Next Follow-up",
        "Last Contact",
        "Source",
        "Req ID",
        "Location",
        "Job URL",
        "Resume Version",
        "Cover Letter Version",
    ])

    for a in apps:
        applied_at = timezone.localtime(a.applied_at).strftime("%Y-%m-%d %I:%M %p") if a.applied_at else ""
        w.writerow([
            a.job.company.name,
            a.job.title,
            a.get_status_display(),
            applied_at,
            a.applied_date.isoformat() if a.applied_date else "",
            a.next_followup_date.isoformat() if a.next_followup_date else "",
            a.last_contact_date.isoformat() if a.last_contact_date else "",
            a.job.source or "",
            a.job.req_id or "",
            a.job.location or "",
            a.job.job_url or "",
            a.resume_version or "",
            a.cover_letter_version or "",
        ])

    return resp

def application_detail(request, app_id: int):
    """
    Application detail page.

    Shows full application info plus communication history.
    Allows adding a Communication inline.
    """
    app = get_object_or_404(
        Application.objects.select_related("job", "job__company"),
        pk=app_id,
    )

    if request.method == "POST":
        form = CommunicationForm(request.POST)
        if form.is_valid():
            comm: Communication = form.save(commit=False)
            comm.application = app
            comm.save()

            # Auto-update last_contact_date to communication date (localdate)
            app.last_contact_date = timezone.localdate(comm.when)

            # Optional: set/bump next followup from today
            days = form.cleaned_data.get("followup_in_days")
            if days is not None:
                app.next_followup_date = timezone.localdate() + timedelta(days=int(days))

            app.save(update_fields=["last_contact_date", "next_followup_date", "updated_at"])
            return redirect("jobtracker:application_detail", app_id=app.id)
    else:
        form = CommunicationForm()

    comms = app.communications.order_by("-when").all()

    return render(
        request,
        "jobtracker/application_detail.html",
        {
            "current": "jobtracker",
            "app": app,
            "comms": comms,
            "form": form,
        },
    )

def application_edit(request, app_id: int):
    """
    Edit an application.

    Automation:
    - If status is a terminal state (REJECTED/WITHDRAWN), clear next_followup_date.
    """
    app = get_object_or_404(
        Application.objects.select_related("job", "job__company"),
        pk=app_id,
    )

    if request.method == "POST":
        form = ApplicationEditForm(request.POST, instance=app)
        if form.is_valid():
            updated = form.save(commit=False)

            # Terminal statuses: no follow-up needed
            if updated.status in ("REJECTED", "WITHDRAWN"):
                updated.next_followup_date = None

            updated.save()
            return redirect("jobtracker:application_detail", app_id=app.id)
    else:
        form = ApplicationEditForm(instance=app)

    return render(
        request,
        "jobtracker/application_edit.html",
        {"current": "jobtracker", "app": app, "form": form},
    )

def company_create(request):
    """
    Create a new company.

    This is intentionally lightweight so you can quickly add a company while tracking jobs.
    """
    next_url = request.GET.get("next") or request.POST.get("next") or ""

    if request.method == "POST":
        form = CompanyForm(request.POST)
        if form.is_valid():
            company = form.save()

            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(_add_query_param(next_url, "company_id", str(company.id)))

            return redirect("jobtracker:companies_list")
    else:
        form = CompanyForm()

    return render(
        request,
        "jobtracker/company_form.html",
        {"current": "jobtracker", "form": form, "next": next_url},
    )

def companies_list(request):
    """
    List companies tracked in JobTracker.

    Shows quick counts so you can spot where activity exists.
    """
    companies = (
        Company.objects
        .annotate(job_count=Count("jobs", distinct=True))
        .annotate(contact_count=Count("contacts", distinct=True))
        .order_by("name")
    )
    return render(
        request,
        "jobtracker/companies_list.html",
        {"current": "jobtracker", "companies": companies},
    )

def company_detail(request, company_id: int):
    """
    Company detail hub.

    Shows:
    - company basics
    - contacts at that company
    - jobs being tracked
    - applications across those jobs
    """
    company = get_object_or_404(Company, pk=company_id)

    contacts = company.contacts.order_by("name")
    jobs = company.jobs.order_by("-priority", "title").all()

    apps = (
        Application.objects.select_related("job", "job__company")
        .filter(job__company=company)
        .order_by("-applied_date")
    )

    return render(
        request,
        "jobtracker/company_detail.html",
        {
            "current": "jobtracker",
            "company": company,
            "contacts": contacts,
            "jobs": jobs,
            "apps": apps,
        },
    )

def contact_create(request, company_id: int):
    """
    Add a contact for a specific company.
    """
    company = get_object_or_404(Company, pk=company_id)

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.company = company
            contact.save()
            return redirect("jobtracker:company_detail", company_id=company.id)
    else:
        form = ContactForm()

    return render(
        request,
        "jobtracker/contact_form.html",
        {"current": "jobtracker", "company": company, "form": form},
    )

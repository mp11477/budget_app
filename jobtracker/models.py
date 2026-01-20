from django.db import models
from django.utils import timezone

"""
jobtracker.models

Job search tracking models.

Flow:
Company -> Job -> Application -> Communication
Company -> Contact (people at the company)

Design goals:
- Minimal but useful fields for real job hunting.
- Support follow-up reminders via next_followup_date.
- Keep history of outreach via Communication.
"""

class Company(models.Model):
    name = models.CharField(max_length=200, unique=True)
    website = models.URLField(blank=True)

    def __str__(self) -> str:
        return self.name


class Contact(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=200)
    title = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    linkedin_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.company.name})"


class Job(models.Model):
    class Priority(models.TextChoices):
        HIGH = "HIGH", "High"
        MEDIUM = "MED", "Medium"
        LOW = "LOW", "Low"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="jobs")
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True)
    job_url = models.URLField(blank=True)
    req_id = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=100, blank=True)  # LinkedIn, Indeed, referral, etc.
    salary_range = models.CharField(max_length=100, blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.company.name} - {self.title}"


class Application(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPLIED = "APPLIED", "Applied"
        SCREEN = "SCREEN", "Recruiter Screen"
        INTERVIEW = "INTERVIEW", "Interviewing"
        OFFER = "OFFER", "Offer"
        REJECTED = "REJECTED", "Rejected"
        GHOSTED = "GHOSTED", "Ghosted"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    applied_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPLIED)

    resume_version = models.CharField(max_length=120, blank=True)  # filename or tag
    cover_letter_version = models.CharField(max_length=120, blank=True)

    last_contact_date = models.DateField(null=True, blank=True)
    next_followup_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.job} ({self.status})"


class Communication(models.Model):
    class Method(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        PHONE = "PHONE", "Phone"
        LINKEDIN = "LINKEDIN", "LinkedIn"
        TEXT = "TEXT", "Text"
        OTHER = "OTHER", "Other"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="communications")
    when = models.DateTimeField(default=timezone.now)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.EMAIL)
    inbound = models.BooleanField(default=False)
    summary = models.CharField(max_length=300)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        direction = "In" if self.inbound else "Out"
        return f"{direction} {self.method} - {self.application}"
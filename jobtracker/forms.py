from django import forms
from .models import Job, Company, Application, Communication, Contact


class JobForm(forms.ModelForm):
    company = forms.ModelChoiceField(
        queryset=Company.objects.order_by("name"),
        empty_label="Select a company",
    )

    class Meta:
        model = Job
        fields = [
            "company",
            "title",
            "location",
            "job_url",
            "req_id",
            "source",
            "salary_range",
            "priority",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
class JobEditForm(forms.ModelForm):
    """
    Edit an existing Job.
    """
    class Meta:
        model = Job
        fields = [
            "title",
            "location",
            "job_url",
            "req_id",
            "source",
            "salary_range",
            "priority",
            "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

class ApplicationForm(forms.ModelForm):
    job = forms.ModelChoiceField(
        queryset=Job.objects.select_related("company").order_by("company__name", "title"),
        empty_label="Select a job",
        required=True,
    )

    def __init__(self, *args, job_locked=None, **kwargs):
        """
        If job_locked is provided:
        - preselect that job
        - disable the dropdown so the user can’t change it
        """
        super().__init__(*args, **kwargs)
        if job_locked is not None:
            self.fields["job"].initial = job_locked
            self.fields["job"].disabled = True

    def clean_job(self):
        """
        If the job field is disabled, Django won't post it. Ensure we return the initial job.
        """
        job = self.cleaned_data.get("job")
        if job is None and self.fields["job"].disabled:
            return self.fields["job"].initial
        return job

    class Meta:
        model = Application
        fields = [
            "job",
            "applied_date",
            "status",
            "resume_version",
            "cover_letter_version",
            "last_contact_date",
            "next_followup_date",
        ]
        widgets = {
            "resume_version": forms.TextInput(attrs={"placeholder": "e.g., Resume_v3_QA"}),
            "cover_letter_version": forms.TextInput(attrs={"placeholder": "e.g., CL_Tobii_2026-01"}),
        }

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "website"]

class CommunicationForm(forms.ModelForm):
    """
    Inline communication entry for an application detail page.

    This form is intentionally lightweight: log an outreach event quickly.
    """
    # Optional helper field: set follow-up days from today
    followup_in_days = forms.IntegerField(
        required=False,
        min_value=0,
        label="Set follow-up (days from today)",
        help_text="Optional. If set, updates the application's next follow-up date.",
    )

    class Meta:
        model = Communication
        fields = ["when", "method", "inbound", "summary", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "summary": forms.TextInput(attrs={"placeholder": "e.g., Follow-up email sent"}),
        }

class ApplicationEditForm(forms.ModelForm):
    """
    Edit an existing Application (status + follow-up + metadata).
    """
    class Meta:
        model = Application
        fields = [
            "status",
            "applied_date",
            "resume_version",
            "cover_letter_version",
            "last_contact_date",
            "next_followup_date",
        ]

class ContactForm(forms.ModelForm):
    """
    Create/edit a contact associated with a company.
    """
    class Meta:
        model = Contact
        fields = ["name", "title", "email", "phone", "linkedin_url", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}
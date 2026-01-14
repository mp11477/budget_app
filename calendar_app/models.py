from django.db import models
from django.contrib.auth.models import User

class CalendarAccount(models.Model):
    PROVIDERS = [
        ("google", "Google"),
        ("icloud", "iCloud (CalDAV)"),
        ("outlook", "Outlook (Graph)"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    provider = models.CharField(max_length=20, choices=PROVIDERS)
    display_name = models.CharField(max_length=120, blank=True)
    # Store tokens/credentials securely (see notes below)
    credentials_json = models.JSONField(default=dict)  # encrypted at rest ideally
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user} - {self.provider} ({self.display_name or 'account'})"
    
    class Meta:
        db_table = "budget_calendaraccount"

class CalendarSource(models.Model):
    """
    A specific calendar within an account (e.g., 'Personal', 'Work', 'Family').
    """
    account = models.ForeignKey(CalendarAccount, on_delete=models.CASCADE)
    external_calendar_id = models.CharField(max_length=255)  # Google calendarId / CalDAV URL / Outlook id
    name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=64, default="America/New_York")
    is_primary = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_cursor = models.CharField(max_length=255, blank=True)  # optional, provider-dependent

    def __str__(self):
        return f"{self.account.provider}: {self.name}"
    
    class Meta:
        db_table = "budget_calendarsource"

class CalendarEvent(models.Model):
    """
    Your unified event record.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    source = models.ForeignKey(CalendarSource, on_delete=models.SET_NULL, null=True, blank=True)

    external_event_id = models.CharField(max_length=255, blank=True)  # provider event id / UID
    title = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    start_dt = models.DateTimeField()
    end_dt = models.DateTimeField()
    all_day = models.BooleanField(default=False)
    status = models.CharField(max_length=32, default="confirmed")  # confirmed/cancelled/tentative
    event_type = models.CharField(max_length=20, default="normal")  # normal/special
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.CharField(max_length=20, blank=True, default="")
    last_edited_by = models.CharField(max_length=20, blank=True, default="")

    EVENT_PEOPLE = [
        ("mike", "Mike"),
        ("wife", "Stef"),
        ("kid1", "Max"),
        ("kid2", "Leo"),
    ]

    person = models.CharField(
        max_length=20,
        choices=EVENT_PEOPLE,
        default="mike",
    )

    # Conflict handling
    last_synced_at = models.DateTimeField(null=True, blank=True)
    provider_etag = models.CharField(max_length=255, blank=True)  # Google etag or similar
    provider_last_modified = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "start_dt"]),
            models.Index(fields=["external_event_id"]),
        ]  
        
    def __str__(self):
        return f"{self.title} ({self.start_dt})"
    
    class Meta:
        db_table = "budget_calendarevent"

class CalendarSpecial(models.Model):
    SPECIAL_TYPES = [
        ("birthday", "Birthday"),
        ("anniversary", "Anniversary"),
        ("holiday", "Holiday"),
        ("milestone", "Milestone"),
        ("reminder", "Reminder"),
    ]

    title = models.CharField(max_length=255)
    date = models.DateField()

    special_type = models.CharField(max_length=20, choices=SPECIAL_TYPES, default="reminder")
    person = models.CharField(max_length=50, blank=True)

    recurring_yearly = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    # optional: if you want to control display color separate from person
    color_key = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.title} ({self.date})"
    
    class Meta:
        db_table = "budget_calendarspecial"
    
class CalendarRuleSpecial(models.Model):
    """
    Specials that are computed from a rule each year (Easter, Thanksgiving, etc.).
    """
    title = models.CharField(max_length=255)

    RULES = [
        ("easter", "Easter (Western)"),
        ("good_friday", "Good Friday"),
        ("thanksgiving_us", "Thanksgiving (US)"),
        ("mothers_day_us", "Mother's Day (US)"),
        ("fathers_day_us", "Father's Day (US)"),
        ("memorial_day_us", "Memorial Day (US)"),
        ("labor_day_us", "Labor Day (US)"),
        ("mlk_day_us", "MLK Day (US)"),
        ("presidents_day_us", "Presidents Day (US)"),
    ]
    rule_key = models.CharField(max_length=50, choices=RULES)
    title_override = models.CharField(max_length=255, blank=True)  # optional custom label

    # optional metadata consistent with your other specials
    special_type = models.CharField(max_length=20, choices=CalendarSpecial.SPECIAL_TYPES, default="holiday")
    person = models.CharField(max_length=50, blank=True)  # allow extended family names/keys
    notes = models.TextField(blank=True)
    color_key = models.CharField(max_length=20, blank=True)

    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.title_override or self.get_rule_key_display()
    
    class Meta:
        db_table = "budget_calendarrulespecial"

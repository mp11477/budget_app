from django.test import TestCase

from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from calendar_app.models import CalendarEvent
from calendar_app.queries import get_events_overlapping_range


class CalendarRecurrenceTests(TestCase):
    """
    Tests the calendar recurrence engine.

    These tests verify that CalendarEvent database records are expanded into
    the correct CalendarOccurrence objects for a requested date range.

    Recurring appointments are stored as a single CalendarEvent row. The
    recurrence engine generates temporary occurrences for display rather than
    creating duplicate database records for every future appointment.

    Important behavior protected here includes:
    - Non-recurring appointments appearing exactly once.
    - Daily, weekly, and biweekly recurrence calculations.
    - Recurrence end dates being inclusive ("Repeat through").
    - Ending a recurring series without removing historical occurrences.
    - Clearing an end date restoring an open-ended recurring series.
    """

    def setUp(self):
        """
        Create a dedicated user for each test.

        Django runs these tests against a temporary test database, so no
        calendar data from dev.sqlite3 or the live database is modified.
        """
        User = get_user_model()

        self.user = User.objects.create_user(
            username="calendar_test_user",
            password="test-password",
        )

    def make_event(
        self,
        *,
        title="Test Event",
        year=2026,
        month=8,
        day=13,
        start_hour=18,
        end_hour=19,
        recurrence="none",
        recurrence_end=None,
    ):
        """
        Create a CalendarEvent with convenient defaults for recurrence tests.

        The default event starts August 13, 2026 at 6:00 PM and ends at
        7:00 PM. Individual tests override only the values relevant to the
        behavior they are testing.
        """
        start_dt = timezone.make_aware(
            datetime(
                year,
                month,
                day,
                start_hour,
                0,
            )
        )

        end_dt = timezone.make_aware(
            datetime(
                year,
                month,
                day,
                end_hour,
                0,
            )
        )

        return CalendarEvent.objects.create(
            user=self.user,
            title=title,
            person="mike",
            start_dt=start_dt,
            end_dt=end_dt,
            recurrence=recurrence,
            recurrence_end=recurrence_end,
        )

    def occurrence_dates(self, events):
        """
        Return only the occurrence dates from a collection of occurrences.

        This keeps recurrence tests focused on which calendar dates were
        generated rather than repeatedly comparing complete event objects.
        """
        return [
            event.occurrence_date
            for event in events
        ]

    def test_single_event_appears_once(self):
        """
        Verify that a non-recurring appointment appears exactly once.

        A CalendarEvent with recurrence="none" must not be duplicated by the
        recurrence engine when querying a date range containing the event.
        """
        self.make_event()

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 8, 1).date(),
            datetime(2026, 8, 31).date(),
        )

        self.assertEqual(
            self.occurrence_dates(events),
            [datetime(2026, 8, 13).date()],
        )

    def test_weekly_recurrence(self):
        """
        Verify that weekly recurrence generates an occurrence every 7 days.

        The original appointment date counts as the first occurrence, followed
        by each 7-day interval falling within the requested date range.
        """
        self.make_event(
            recurrence="weekly",
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 8, 13).date(),
            datetime(2026, 9, 10).date(),
        )

        self.assertEqual(
            self.occurrence_dates(events),
            [
                datetime(2026, 8, 13).date(),
                datetime(2026, 8, 20).date(),
                datetime(2026, 8, 27).date(),
                datetime(2026, 9, 3).date(),
                datetime(2026, 9, 10).date(),
            ],
        )

    def test_daily_recurrence(self):
        """
        Verify that daily recurrence generates an occurrence every calendar day.

        The original appointment date and every subsequent day within the
        requested range should be returned.
        """
        self.make_event(
            recurrence="daily",
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 8, 13).date(),
            datetime(2026, 8, 16).date(),
        )

        self.assertEqual(
            self.occurrence_dates(events),
            [
                datetime(2026, 8, 13).date(),
                datetime(2026, 8, 14).date(),
                datetime(2026, 8, 15).date(),
                datetime(2026, 8, 16).date(),
            ],
        )

    def test_biweekly_recurrence(self):
        """
        Verify that "Every 2 weeks" recurrence advances in 14-day intervals.

        This protects biweekly appointments from accidentally behaving like
        ordinary weekly appointments.
        """
        self.make_event(
            recurrence="biweekly",
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 8, 13).date(),
            datetime(2026, 9, 30).date(),
        )

        self.assertEqual(
            self.occurrence_dates(events),
            [
                datetime(2026, 8, 13).date(),
                datetime(2026, 8, 27).date(),
                datetime(2026, 9, 10).date(),
                datetime(2026, 9, 24).date(),
            ],
        )

    def test_recurrence_end_is_inclusive(self):
        """
        Verify that recurrence_end represents "Repeat through", not "stop before".

        If a weekly series has recurrence_end=August 27 and August 27 is a
        scheduled occurrence, that occurrence must remain visible. Only
        occurrences after August 27 should be excluded.

        This test protects the user-facing "Repeat through" semantics.
        """
        self.make_event(
            recurrence="weekly",
            recurrence_end=datetime(
                2026,
                8,
                27,
            ).date(),
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 8, 1).date(),
            datetime(2026, 9, 30).date(),
        )

        self.assertEqual(
            self.occurrence_dates(events),
            [
                datetime(2026, 8, 13).date(),
                datetime(2026, 8, 20).date(),
                datetime(2026, 8, 27).date(),
            ],
        )

    def test_shortening_series_preserves_history(self):
        """
        Verify that ending a recurring series removes only future occurrences.

        Setting recurrence_end on an existing open-ended series must preserve
        occurrences on and before that date while preventing later occurrences
        from being generated.

        This protects historical calendar appointments when a recurring
        activity is discontinued.
        """
        event = self.make_event(
            recurrence="weekly",
        )

        event.recurrence_end = datetime(
            2026,
            8,
            27,
        ).date()

        event.save(
            update_fields=["recurrence_end"]
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 8, 1).date(),
            datetime(2026, 9, 30).date(),
        )

        dates = self.occurrence_dates(events)

        self.assertIn(
            datetime(2026, 8, 13).date(),
            dates,
        )

        self.assertIn(
            datetime(2026, 8, 20).date(),
            dates,
        )

        self.assertIn(
            datetime(2026, 8, 27).date(),
            dates,
        )

        self.assertNotIn(
            datetime(2026, 9, 3).date(),
            dates,
        )

    def test_clearing_recurrence_end_restores_future_occurrences(self):
        """
        Verify that removing recurrence_end makes a series open-ended again.

        If an existing recurring series previously had a Repeat-through date,
        clearing that date should allow future occurrences to be generated
        again without creating a new CalendarEvent.
        """
        event = self.make_event(
            recurrence="weekly",
            recurrence_end=datetime(
                2026,
                8,
                27,
            ).date(),
        )

        event.recurrence_end = None

        event.save(
            update_fields=["recurrence_end"]
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 8, 1).date(),
            datetime(2026, 9, 10).date(),
        )

        dates = self.occurrence_dates(events)

        self.assertIn(
            datetime(2026, 9, 3).date(),
            dates,
        )

        self.assertIn(
            datetime(2026, 9, 10).date(),
            dates,
        )

    def test_monthly_recurrence(self):
        """
        Verify that monthly recurrence advances by one calendar month.

        A normal day-of-month such as the 13th should remain the 13th as the
        recurring series moves through subsequent months.
        """
        self.make_event(
            recurrence="monthly",
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 8, 1).date(),
            datetime(2026, 11, 30).date(),
        )

        self.assertEqual(
            self.occurrence_dates(events),
            [
                datetime(2026, 8, 13).date(),
                datetime(2026, 9, 13).date(),
                datetime(2026, 10, 13).date(),
                datetime(2026, 11, 13).date(),
            ],
        )

    def test_bimonthly_recurrence(self):
        """
        Verify that "Every 2 months" advances by two calendar months.

        This protects bimonthly recurrence from being interpreted as twice per
        month or from accidentally behaving like ordinary monthly recurrence.
        """
        self.make_event(
            recurrence="bimonthly",
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 8, 1).date(),
            datetime(2027, 2, 28).date(),
        )

        self.assertEqual(
            self.occurrence_dates(events),
            [
                datetime(2026, 8, 13).date(),
                datetime(2026, 10, 13).date(),
                datetime(2026, 12, 13).date(),
                datetime(2027, 2, 13).date(),
            ],
        ) 

    def test_yearly_recurrence(self):
        """
        Verify that yearly recurrence advances by one calendar year.

        The month and day should remain unchanged when that date exists in each
        subsequent year.
        """
        self.make_event(
            recurrence="yearly",
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 1, 1).date(),
            datetime(2029, 12, 31).date(),
        )

        self.assertEqual(
            self.occurrence_dates(events),
            [
                datetime(2026, 8, 13).date(),
                datetime(2027, 8, 13).date(),
                datetime(2028, 8, 13).date(),
                datetime(2029, 8, 13).date(),
            ],
        )

    def test_monthly_recurrence_handles_end_of_month(self):
        """
        Verify that monthly recurrence remains anchored to the original day.

        A January 31 series should use February's final valid day, then return
        to the 31st in months where that date exists instead of permanently
        shifting to the 28th.
        """
        self.make_event(
            year=2026,
            month=1,
            day=31,
            recurrence="monthly",
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2026, 1, 1).date(),
            datetime(2026, 4, 30).date(),
        )

        self.assertEqual(
            self.occurrence_dates(events),
            [
                datetime(2026, 1, 31).date(),
                datetime(2026, 2, 28).date(),
                datetime(2026, 3, 31).date(),
                datetime(2026, 4, 30).date(),
            ],
        )  

    def test_yearly_recurrence_handles_leap_day(self):
        """
        Verify that yearly leap-day recurrence stays anchored to February 29.

        Non-leap years should use February 28, but when the next leap year
        arrives the series should return to February 29 rather than remaining
        permanently shifted to February 28.
        """
        self.make_event(
            year=2028,
            month=2,
            day=29,
            recurrence="yearly",
        )

        events = get_events_overlapping_range(
            self.user,
            datetime(2028, 1, 1).date(),
            datetime(2032, 12, 31).date(),
        )

        self.assertEqual(
            self.occurrence_dates(events),
            [
                datetime(2028, 2, 29).date(),
                datetime(2029, 2, 28).date(),
                datetime(2030, 2, 28).date(),
                datetime(2031, 2, 28).date(),
                datetime(2032, 2, 29).date(),
            ],
        )


    
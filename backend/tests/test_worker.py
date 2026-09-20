"""
The two things about the worker's schedule no API test can reach: when its cron
fires, and in which timezone.

Everything else the schedule does is driven through the Inbox in
`test_scheduled_reviews.py`, because the cron runs the very same function. What
is left is the timetable, and an hour set wrong there has no other guard.
"""

from app.clock import ARGENTINA
from app.worker import WorkerSettings


def test_the_scheduled_reviews_run_on_the_first_at_six():
    [job] = WorkerSettings.cron_jobs

    assert (job.day, job.hour, job.minute) == (1, 6, 0)


def test_the_hour_is_read_in_buenos_aires():
    """ARQ would otherwise read crons in whatever timezone the machine is in."""
    assert WorkerSettings.timezone is ARGENTINA

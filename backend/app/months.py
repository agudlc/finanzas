"""Month arithmetic. A month is named "YYYY-MM" and stored as its first day."""

import calendar
import re
from datetime import date as Date

MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def parse_month(month: str) -> Date:
    """The first day of the month named "YYYY-MM"."""
    if not MONTH_PATTERN.match(month):
        raise ValueError(f"'{month}' is not a month of the form YYYY-MM")
    year, number = month.split("-")
    return Date(int(year), int(number), 1)


def format_month(day: Date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def month_of(day: Date) -> Date:
    return day.replace(day=1)


def days_in_month(day: Date) -> int:
    return calendar.monthrange(day.year, day.month)[1]


def last_day_of_month(day: Date) -> Date:
    return day.replace(day=days_in_month(day))


def add_months(day: Date, months: int) -> Date:
    """
    The same day of month, `months` later.

    A day the later month is too short for lands on its last day, so the 31st
    of January plus one month is the 28th of February.
    """
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    return Date(year, month, min(day.day, calendar.monthrange(year, month)[1]))

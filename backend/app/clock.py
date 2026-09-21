from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


class Clock:
    """Where "today" comes from. Injected so date-dependent behaviour is testable."""

    def today(self) -> date:
        return datetime.now(ARGENTINA).date()

    def now(self) -> datetime:
        """
        This moment, in UTC.

        The day is what almost everything asks for; this is for the few things
        measured in minutes rather than days, like a Review that waits a couple
        of them before it starts. UTC because that is how the timestamps are
        stored, and the two are compared.
        """
        return datetime.now(UTC)


def get_clock() -> Clock:
    return Clock()

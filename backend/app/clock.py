from datetime import date, datetime
from zoneinfo import ZoneInfo

ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


class Clock:
    """Where "today" comes from. Injected so date-dependent behaviour is testable."""

    def today(self) -> date:
        return datetime.now(ARGENTINA).date()


def get_clock() -> Clock:
    return Clock()

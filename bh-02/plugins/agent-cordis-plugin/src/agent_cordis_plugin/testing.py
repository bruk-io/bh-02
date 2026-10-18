"""Fakes for the clock the loop reads (`records.Clock`): for tests, which never wait on the real one."""

import datetime

from agent_cordis_plugin.records import Clock

__all__ = ["Stepped", "noon", "on"]

_START = datetime.datetime(2026, 10, 18, 3, 47, 12, 345000, tzinfo=datetime.UTC)


def noon(day: str) -> datetime.datetime:
    """Noon on `day` (`2026-10-07`) where the test runs, as an aware time: the loop tells the
    person's day (`records.day_of`), so a time of day that is `day` in every zone is the local one."""
    return datetime.datetime.fromisoformat(f"{day}T12:00:00").astimezone()


def on(day: str) -> Clock:
    """A clock that reads noon on `day`, and stands still."""
    return Clock(now=lambda: noon(day))


class Stepped:
    """A clock a test moves: `now()` and `monotonic()` read what `advance` has added since the
    start, and nothing else moves them. `clock` is the value a loop is given."""

    def __init__(self, start: datetime.datetime = _START) -> None:
        self._start = start
        self._seconds = 0.0

    def advance(self, seconds: float) -> None:
        self._seconds += seconds

    def now(self) -> datetime.datetime:
        return self._start + datetime.timedelta(seconds=self._seconds)

    def monotonic(self) -> float:
        return 5000.0 + self._seconds

    @property
    def clock(self) -> Clock:
        return Clock(now=self.now, monotonic=self.monotonic)

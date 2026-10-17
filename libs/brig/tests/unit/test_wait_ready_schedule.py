"""The schedule `Process.wait_ready` asks readiness on (TASK-0079.21): 2ms first, a tenth of the
time spent after, no more than the 20ms a fixed interval used to be.

A jail's process binds its socket some milliseconds after it starts, and a fixed 20ms interval
saw the bind on the 20ms mark or the 40ms one. `brig/run/readiness.py` is the loop, and its wait
is pure (`_next_wait`), so the schedule is a value here and the loop runs on a clock of its own:
`sleep` advances it and nothing really waits. That the real thing gets there sooner is the
integration tier's (`tests/integration/test_wait_ready.py`) and the start's own numbers (the
task's notes).
"""

from __future__ import annotations

import types
from collections.abc import Callable

import pytest

from brig.run import WaitReadyTimeout, readiness
from brig.run.readiness import _next_wait, poll_ready

pytestmark = pytest.mark.unit

#: What a fixed interval waited before it asked again; the schedule never waits longer.
_OLD_INTERVAL_S = 0.02


class _Clock:
    """A clock that moves only when something sleeps on it, and remembers each sleep."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _bound_at(clock: _Clock, bind_at: float) -> Callable[[], bool]:
    """`ready` for a socket that is bound once the clock reaches `bind_at`."""
    return lambda: clock.now >= bind_at


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(
        readiness, "time", types.SimpleNamespace(monotonic=fake.monotonic, sleep=fake.sleep)
    )
    return fake


def test_the_first_wait_is_two_milliseconds_and_none_is_longer_than_the_old_interval() -> None:
    assert _next_wait(0.0) == 0.002
    assert _next_wait(0.019) == 0.002
    waits = [_next_wait(elapsed / 1000) for elapsed in range(0, 3000)]
    assert waits == sorted(waits), "a wait never shortens as the wait goes on"
    assert max(waits) == _OLD_INTERVAL_S
    assert _next_wait(0.2) == _OLD_INTERVAL_S
    assert 0.002 < _next_wait(0.1) < _OLD_INTERVAL_S, "between the two, a tenth of the time spent"
    assert _next_wait(0.1) == pytest.approx(0.01)


def test_a_bind_in_the_first_milliseconds_is_seen_within_two_of_it(clock: _Clock) -> None:
    """The point of the schedule: a process that binds 15ms after it starts was found on the
    20ms mark (5ms late, or 25ms when the first check came just before) and is found on the
    16ms one. THE PLANT: a fixed 20ms wait puts `clock.now` at 0.02 and fails this."""
    bind_at = 0.015
    poll_ready(_bound_at(clock, bind_at), channel="agent", endpoint="/j/chan/a.sock", timeout=10.0)
    assert bind_at <= clock.now <= bind_at + 0.002
    assert clock.sleeps[0] == 0.002


def test_the_first_check_is_not_waited_for(clock: _Clock) -> None:
    """A control: a socket already bound is seen at once, with no sleep."""
    poll_ready(lambda: True, channel="agent", endpoint="/j/chan/a.sock", timeout=10.0)
    assert clock.sleeps == []


def test_a_late_bind_is_overshot_by_no_more_than_the_old_interval(clock: _Clock) -> None:
    """The bound the elapsed-time assertions were chosen against holds for a bind at any time."""
    for bind_at in (0.3, 0.5, 1.0, 1.7):
        clock.now = 0.0
        poll_ready(
            _bound_at(clock, bind_at),
            channel="agent",
            endpoint="/j/chan/a.sock",
            timeout=10.0,
        )
        assert bind_at <= clock.now <= bind_at + _OLD_INTERVAL_S


def test_a_bind_that_never_comes_times_out_within_the_old_interval_of_the_deadline(
    clock: _Clock,
) -> None:
    with pytest.raises(WaitReadyTimeout) as raised:
        poll_ready(lambda: False, channel="agent", endpoint="/j/chan/a.sock", timeout=1.0)
    assert (raised.value.channel, raised.value.endpoint, raised.value.timeout) == (
        "agent",
        "/j/chan/a.sock",
        1.0,
    )
    assert 1.0 <= clock.now <= 1.0 + _OLD_INTERVAL_S


def test_what_the_runtime_refuses_is_raised_at_once_and_not_waited_out(clock: _Clock) -> None:
    def refuses() -> bool:
        raise RuntimeError("a runtime's refusal, not 'not yet'")

    with pytest.raises(RuntimeError, match="not 'not yet'"):
        poll_ready(refuses, channel="agent", endpoint="/j/chan/a.sock", timeout=10.0)
    assert clock.sleeps == []

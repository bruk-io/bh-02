"""`_sample_outcome`, the pure classifier behind the leak poller's retry (TASK-0198).

The poller samples `/bin/ps` every 50ms for the whole session; `tests/conftest.py`'s own
`_ps_rows` docstring documents a transient failure class under heavy concurrent spawning (an
`EFAULT` racing a live environment write, 58 of 298 spawns in one stress run). Before TASK-0198 a
single such blip, anywhere in the session, failed the whole run -- attributed to whichever test
happened to be executing when the session-scoped `run_id` fixture tore down, never the one that
actually hit it. `_poll_once` now retries once immediately and `_sample_outcome` decides, from the
attempts' outcomes alone, whether that retry cleared it.
"""

from __future__ import annotations

import pytest

from tests import conftest

pytestmark = pytest.mark.unit


def test_a_read_that_succeeds_outright_is_not_a_failure() -> None:
    assert conftest._sample_outcome([None]) is None


def test_a_failure_the_immediate_retry_clears_is_not_reported() -> None:
    """The transient class: `_ps_rows` failed once, the very next attempt returned rows."""
    first = OSError("EFAULT")
    assert conftest._sample_outcome([first, None]) is None


def test_a_failure_the_retry_does_not_clear_is_reported_as_the_retrys_own_error() -> None:
    """The persistent class: both attempts failed, so this sample counts -- named by the LAST
    attempt's error, which is what a reader investigating actually wants to see."""
    first = OSError("EFAULT")
    second = FileNotFoundError("/bin/ps")
    outcome = conftest._sample_outcome([first, second])
    assert outcome == repr(second)
    assert "FileNotFoundError" in outcome


def test_no_attempts_at_all_is_not_a_failure() -> None:
    """`_poll_once` always makes at least one attempt; this is the function's own total
    boundary, not a shape `_poll_once` ever actually produces."""
    assert conftest._sample_outcome([]) is None


def test_a_lone_first_failure_with_no_retry_attempt_is_reported() -> None:
    """The pre-TASK-0198 shape (one `/bin/ps` call, no retry) judged a transient failure on the
    first attempt alone, which is indistinguishable from a persistent one -- `_sample_outcome`
    given only that one attempt (as `_poll_once` would call it if its retry were ever removed)
    still reports it, which is what makes `_poll_once`'s own retry -- a second attempt actually
    made, per `test_a_failure_the_immediate_retry_clears_is_not_reported` above -- the thing
    that does the absorbing, not this function silently treating one failure as always fine."""
    first = OSError("EFAULT")
    assert conftest._sample_outcome([first]) == repr(first)

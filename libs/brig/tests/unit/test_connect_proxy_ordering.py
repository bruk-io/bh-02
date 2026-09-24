"""Where `connect_proxy` sits in the composition order, and why moving it breaks.

task-080 / decision-135. Two claims that look alike and are not:

- The ORDER is matrix-derived, and this pins it by observing the composed
  argv rather than by reading `COMPATIBILITY_MATRIX` back to itself. A test
  that asserted the matrix contains what the matrix contains would pass for
  a stack that composed in the opposite order.
- The HELPER's exemption from wrapping is NOT an ordering property at all.
  It belongs to `run.launcher._start_helpers`, which spawns `helper.argv`
  directly while only the workload becomes `wrapped_argv`. No matrix entry
  can protect it, so it is pinned separately, at the launcher.
"""

from __future__ import annotations

import inspect
import sys

import pytest

import brig.stack
from brig.core import EnvMode, EnvPolicy, NetworkPolicy, Spec
from brig.mech import CompileCtx
from brig.mech.connect_proxy import PORT_FILE, ConnectProxy
from brig.mech.env_scrub import EnvScrub
from brig.mech.rlimits import Rlimits
from brig.mech.seatbelt import Seatbelt

pytestmark = pytest.mark.unit

_PY = "/usr/bin/python3"
_JAIL = "/private/tmp/jail-ordering"
_CTX = CompileCtx(jail_dir=_JAIL, platform=sys.platform)
_WORKLOAD = ("/bin/echo", "hello")


def _spec() -> Spec:
    return Spec(
        network=NetworkPolicy(allowed_domains=("example.com",)),
        env=EnvPolicy(mode=EnvMode.SCRUB),
    )


def _composed(mechanisms: list[object]) -> tuple[str, ...]:
    stack = brig.stack.Stack(mechanisms)  # type: ignore[arg-type]
    return stack.compile(_spec(), ctx=_CTX).wrap(_WORKLOAD)


def _index_of(argv: tuple[str, ...], needle: str) -> int:
    for i, token in enumerate(argv):
        if needle in token:
            return i
    raise AssertionError(f"{needle!r} not found in composed argv {argv!r}")


def test_connect_proxy_composes_inside_env_scrub_so_env_i_cannot_wipe_the_proxy_vars() -> None:
    """decision-135 (1), the forcing argument, observed in the argv.

    `env_scrub`'s SCRUB render is `exec /usr/bin/env -i ... "$@"`. Whichever
    of the two runs LAST before the workload wins the environment. This
    asserts `connect_proxy`'s export runs after `env -i`, which is the only
    order in which the workload actually receives `HTTPS_PROXY`.
    """
    argv = _composed([EnvScrub(), ConnectProxy(_PY)])
    env_i = _index_of(argv, "-i")
    proxy_export = _index_of(argv, "HTTPS_PROXY")
    assert env_i < proxy_export, (
        "env_scrub's `env -i` must run BEFORE connect_proxy's export, i.e. "
        "connect_proxy composes innermost. In the reverse order the workload "
        "starts with the proxy variables unset and reaches the network "
        f"directly. composed argv: {argv!r}"
    )


def test_the_order_is_matrix_derived_not_construction_order() -> None:
    """decision-135 (1): the same two mechanisms in the REVERSE construction
    order compose identically, because `Stack.compile` sorts by the matrix's
    `outer` field and never by the list literal. This is the claim that
    would survive someone reordering a preset's list."""
    forward = _composed([EnvScrub(), ConnectProxy(_PY)])
    reverse = _composed([ConnectProxy(_PY), EnvScrub()])
    assert forward == reverse


def test_rlimits_stays_outermost_of_connect_proxy() -> None:
    """decision-135 (3): `rlimits` is outermost against every mechanism, so
    its caps bound connect_proxy's own port-waiting `/bin/sh` and not just
    the final workload."""
    argv = _composed([ConnectProxy(_PY), Rlimits()])
    assert _index_of(argv, "brig.mech.trampoline") < _index_of(argv, PORT_FILE)


def test_the_proxy_helper_is_spawned_unwrapped_by_the_launcher() -> None:
    """decision-135 (4). NOT an ordering claim -- a launcher one.

    `_start_helpers` spawns `list(helper.argv)`; only the workload is
    spawned as `wrapped_argv`. That is what lets the proxy reach upstream
    while seatbelt denies the workload's network, and no matrix entry can
    protect it. Asserted against the launcher's source because the
    alternative -- actually launching a jail -- is not a unit test.

    If this fails, someone routed helpers through the composed wrap and the
    proxy is now inside the jail it filters for: egress breaks, or worse,
    the proxy is scrubbed of the environment it needs and the workload
    silently loses its filter.
    """
    from brig.run import launcher

    source = inspect.getsource(launcher._start_helpers)
    assert "wrapped_argv" not in source, (
        "_start_helpers must never spawn the composed wrap: a helper that "
        "passes through seatbelt cannot reach upstream, and one that passes "
        "through env_scrub loses its environment."
    )
    assert "helper.argv" in source


# ---------------------------------------------------------------------------
# task-079 AC#3/AC#4: the grade is raised by the OBSERVER, never by the
# mechanism, and never past best_effort.
# ---------------------------------------------------------------------------


def _network(stack: brig.stack.Stack):  # type: ignore[no-untyped-def]
    from brig.core import Axis

    return stack.compile(_spec(), ctx=_CTX).report.axes[Axis.NETWORK]


def test_connect_proxy_alone_still_self_grades_cooperative() -> None:
    """decision-134 sub-ruling 1 STANDS. The mechanism is unchanged by
    task-079: on its own it cannot see a confinement and must not claim one.
    This is the baseline the raise is measured against -- without it, a test
    that only checked the paired case would pass for a mechanism that graded
    best_effort unconditionally."""
    from brig.core import Grade

    assert _network(brig.stack.Stack([ConnectProxy(_PY)])).grade is Grade.COOPERATIVE


@pytest.mark.skipif(sys.platform != "darwin", reason="seatbelt is darwin-only")
def test_the_observed_pairing_raises_network_to_best_effort_and_no_further() -> None:
    """task-079 AC#3/AC#4: raised by `Stack.compile`, which holds both
    mechanisms, and capped at best_effort."""
    from brig.core import Grade

    graded = _network(brig.stack.Stack([Seatbelt(cedes_network=True), ConnectProxy(_PY)]))
    # Asserted against the RANK, not by restating `is not Grade.ENFORCED`:
    # mypy narrows the line above to a literal, so the negative form is a
    # type error rather than an assertion. Same trap, same fix, as
    # `test_connect_proxy_compile.test_grade_is_cooperative_and_names_both_gaps`.
    assert graded.grade is Grade.BEST_EFFORT
    assert not graded.grade.is_at_least(Grade.ENFORCED)


@pytest.mark.skipif(sys.platform != "darwin", reason="seatbelt is darwin-only")
def test_the_raised_detail_names_both_gaps_not_only_sni() -> None:
    """task-079 AC#3 as amended by decision-136 (4). The loopback-wide
    allowance is a SECOND hole, independent of SNI co-hosting, and a detail
    naming only one of them understates what the operator is accepting."""
    detail = _network(brig.stack.Stack([Seatbelt(cedes_network=True), ConnectProxy(_PY)])).detail
    assert "SNI" in detail
    assert "loopback" in detail


@pytest.mark.skipif(sys.platform != "darwin", reason="seatbelt is darwin-only")
def test_a_non_ceding_seatbelt_cannot_pair_at_all_so_nothing_is_raised() -> None:
    """THE CONTROL for the raise. A seatbelt that still CLAIMS network denies
    the proxy hop, so the pairing is not merely ungraded -- it is
    uncomposable, and the axis conflict says so rather than compiling
    something that would silently fail at runtime."""
    with pytest.raises(brig.stack.AxisClaimConflict):
        brig.stack.Stack([Seatbelt(), ConnectProxy(_PY)]).compile(_spec(), ctx=_CTX)

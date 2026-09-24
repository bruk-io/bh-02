"""`Handle.signatures` survives a real launch AND a genuinely separate-process
rehydration, unchanged (task-047).

## THE GAP THIS TASK CLOSES

`tests/unit/test_stack_signature_book.py` already proves `Stack.compile`
assembles the `SignatureBook` correctly as PURE data. This file is the seam
`tests/unit/` cannot reach on its own (`stack -> launcher -> Handle`,
`.claude/rules/integration-tests.md`'s own scope): a REAL `degraded()`
stack, launched through the REAL `SubprocessLauncher`, whose `Handle`
carries that same book through `to_dict()`/`from_dict()` -- including
across an actual OS process boundary, the failure mode `SPEC.md §9` names
outright ("kill paths that lose ... identity when a relay pid dies").

`tests/integration/_rehydrate_and_kill_helper.py`'s own `to_dict` field is
generic -- it is `handle.to_dict()` from the rehydrated `Handle`, whatever
keys that carries -- so this file reuses it UNCHANGED (task-047's own
Deliverable note: "the idiom `tests/integration/
_rehydrate_and_kill_helper.py` already uses"), in `--no-kill` mode: this
file's subject is serialization fidelity, not teardown, so it follows
`tests/integration/test_handle_rehydration.py`'s own
`test_rehydrated_round_trip_carries_a_channel_and_a_non_empty_detail`
precedent of reusing the SAME helper in that mode for a non-teardown claim.
"""

from __future__ import annotations

import itertools
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from brig.core import Axis, Limits, Spec
from brig.core.signatures import SignatureBook
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import degraded
from tests.conftest import teardown_group, workload_argv

_HELPER = str(pathlib.Path(__file__).parent / "_rehydrate_and_kill_helper.py")
_HELPER_TIMEOUT_S = 30.0

_jail_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>sb<n>` -- never `tmp_path`
    (CLAUDE.md: `sun_path` is 104 bytes on darwin). The `sb` ("signature
    book") infix keeps this file's jail-dir sequence out of the shared,
    order-dependent `/tmp/bg<pid>-<n>` namespace other integration files'
    own docstrings document colliding across files that share one pytest
    process."""
    return f"/tmp/bg{os.getpid()}sb{next(_jail_counter)}"


def _launch(run_id: str, *, jail_id: str) -> Handle:
    """A REAL `degraded()` stack -- `rlimits` + `env_scrub`, the two
    mechanisms that exist as of M3/M4 -- compiled against a generous cpu
    limit (this file's subject is signature-book fidelity, not the cpu
    axis actually tripping) and launched through the REAL
    `SubprocessLauncher`, exactly as `test_stack_matrix_ordering.py` does
    for its own composed-stack claims."""
    spec = Spec(limits=Limits(cpu_seconds=30))
    jail = degraded().compile(spec)
    jail_dir = _new_jail_dir()
    launcher = SubprocessLauncher()
    argv = workload_argv(run_id, "sleep 30")
    return launcher.launch(
        jail,
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=jail_id,
        jail_dir=jail_dir,
    )


def _run_helper(json_path: str, *extra_args: str) -> dict[str, object]:
    """Run `_HELPER` as a genuinely separate interpreter (`sys.executable`,
    not this process), and parse its single JSON line of stdout. Identical
    shape to `test_handle_rehydration.py::_run_helper`, reproduced here
    rather than imported (no cross-integration-file private-helper imports
    elsewhere in this suite)."""
    argv = [sys.executable, _HELPER, json_path, *extra_args]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=_HELPER_TIMEOUT_S,
    )
    print(f"HELPER ARGV: {argv}")
    print(f"HELPER stdout: {proc.stdout!r}")
    print(f"HELPER stderr: {proc.stderr!r}")
    assert proc.returncode == 0, (
        f"helper {argv} exited {proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, f"helper {argv} printed no output"
    return dict(json.loads(lines[-1]))


def _killpg_cleanup(handle: Handle) -> None:
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #4 -- the book survives a real launch AND cross-process rehydration.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_the_book_survives_a_real_launch_and_rehydration(run_id: str) -> None:
    """AC #4. A REAL `degraded()` jail is launched (`rlimits` claims
    `Axis.LIMITS` under a real cpu limit -- the same non-vacuous claim
    `tests/unit/test_stack_signature_book.py`'s AC #1 test pins). The
    live handle's own `signatures.for_axis(Axis.LIMITS)` is asserted
    BEFORE serialization, so a later mismatch can be pinned to the round
    trip specifically. Its `to_dict()` is written to disk -- the helper's
    SOLE input, same idiom as `test_handle_rehydration.py` -- and rehydrated
    in a genuinely separate interpreter (`--no-kill` mode: this claim is
    about the book, not teardown). The rehydrated book's `Axis.LIMITS`
    claim's `mechanism` and pattern SOURCES (`re.Pattern.pattern`, since a
    compiled pattern itself never crosses the process boundary -- see
    AC #5 below) equal the live handle's."""
    handle = _launch(run_id, jail_id="jail-sigbook-rehydrate")
    try:
        live_claim = handle.signatures.for_axis(Axis.LIMITS)
        assert live_claim is not None
        assert live_claim.mechanism == "rlimits"
        assert len(live_claim.signatures) > 0
        live_sources = [pattern.pattern for pattern in live_claim.signatures]

        original_dict = handle.to_dict()
        json_path = os.path.join(handle.jail_dir, "handle.json")
        with open(json_path, "w") as f:
            json.dump(original_dict, f)

        result = _run_helper(json_path, "--no-kill")
        assert result["pid"] != os.getpid()
        assert result["alive"] is True

        rehydrated_dict = result["to_dict"]
        assert rehydrated_dict == original_dict

        rehydrated_book = SignatureBook.from_list(rehydrated_dict["signatures"])
        rehydrated_claim = rehydrated_book.for_axis(Axis.LIMITS)
        assert rehydrated_claim is not None
        assert rehydrated_claim.mechanism == live_claim.mechanism == "rlimits"
        rehydrated_sources = [pattern.pattern for pattern in rehydrated_claim.signatures]
        assert rehydrated_sources == live_sources
        print(f"AC #4: live LIMITS sources={live_sources} rehydrated={rehydrated_sources}")
    finally:
        _killpg_cleanup(handle)


# ---------------------------------------------------------------------------
# AC #5 -- to_dict carries pattern SOURCES only, never a compiled re.Pattern.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_to_dict_carries_no_compiled_pattern(run_id: str) -> None:
    """AC #5. `json.dumps(handle.to_dict())` succeeds (an `re.Pattern`
    object is not JSON-serializable, so this alone already fails if one
    leaked through), and every serialized `signatures` entry is a plain
    `str`. THE CONTROL, in the same test: after `Handle.from_dict`
    round-trips the same dict, the reconstructed book's `Axis.LIMITS`
    claim's `signatures` ARE `re.Pattern` objects again -- proving the
    string-only shape above is `to_dict`'s doing, not `SignatureBook`
    simply never carrying compiled patterns at all."""
    handle = _launch(run_id, jail_id="jail-sigbook-nopattern")
    try:
        d = handle.to_dict()
        serialized = json.dumps(d)  # raises TypeError if a re.Pattern leaked through
        assert isinstance(serialized, str)

        signature_entries = d["signatures"]
        assert isinstance(signature_entries, list)
        assert len(signature_entries) > 0
        for entry in signature_entries:
            for source in entry["signatures"]:
                assert isinstance(source, str), (
                    f"expected a pattern SOURCE (str) in to_dict(), got {source!r} "
                    f"({type(source)!r}) in entry {entry!r}"
                )

        # THE CONTROL: from_dict re-compiles those sources back into real
        # re.Pattern objects -- the string-only shape above is to_dict's
        # serialization choice, not a property SignatureBook always had.
        limits_entry = next(e for e in signature_entries if e["axis"] == Axis.LIMITS.value)
        assert limits_entry["mechanism"] == "rlimits"
        assert len(limits_entry["signatures"]) > 0

        rehydrated = Handle.from_dict(d)
        rehydrated_claim = rehydrated.signatures.for_axis(Axis.LIMITS)
        assert rehydrated_claim is not None
        assert len(rehydrated_claim.signatures) > 0
        assert all(isinstance(p, re.Pattern) for p in rehydrated_claim.signatures)
    finally:
        _killpg_cleanup(handle)

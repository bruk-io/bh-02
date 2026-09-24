"""`seatbelt`'s socket-bind channel against the real darwin sandbox kernel:
task-061, MILESTONES.md M5-lite exit criterion 2, verbatim:

    Socket-bind channel: with a LISTEN channel declared, the jail binds
    exactly the declared endpoint and a bind at any other path is denied;
    with no channel declared, a bind attempt is denied -- the control that
    keeps `network: enforced` from covering an unscoped bind permission.

SPEC.md §10.1, readiness, verbatim:

    Observable means a connect succeeds -- not that the endpoint path
    exists. A socket file outlives the process that bound it, so path
    existence reports ready for a jail that has already died. Readiness
    connects and closes; path-existence is never readiness.

**Three observations, each made by a JAILED process attempting a real bind
and reporting the outcome** (`.claude/rules/integration-tests.md`'s "observe
from inside the jail, not from the outside"):

1. `test_declared_endpoint_binds_readiness_by_connect_and_second_path_denied`
   -- the declared endpoint binds (readiness proved by `handle.wait_ready`'s
   own trusted-side `connect`, never `os.path.exists`), and, in the SAME
   jailed process's SAME run, a bind at a second, undeclared path is denied,
   matching seatbelt's own declared denial signature.
2. `test_no_channel_declared_denies_bind_and_profile_carries_no_network_bind_allow`
   -- a spec with zero channels: the bind attempt is denied, AND the
   profile this test itself compiled is asserted to carry zero
   `(allow network-bind)` lines, so the denial is pinned to the rule that
   is actually absent rather than merely observed and hoped.
3. `test_control_unconfined_stack_binds_succeed_at_both_denied_paths` --
   the control `.claude/rules/integration-tests.md` requires for every
   denial: the identical probes run through `Stack([])` (zero mechanisms,
   `wrap` is the identity) succeed at BOTH paths seatbelt denied above,
   proving those two denials are the jail's doing, not the filesystem's.

Plus one mutation check
(`test_mutation_check_removing_endpoint_write_rule_denies_the_declared_bind`):
strip the `(allow file-write* (literal "<endpoint>"))` line from THIS
TEST's own already-compiled profile (an in-memory `CompiledJail.staged`
mutation, `dataclasses.replace` -- `brig/mech/seatbelt/` itself is never
opened for writing, and its module file's `sha256` is asserted identical
before and after, proving that literally) and re-run observation 1's own
bind: it must now be denied. Per decision-074, and per task-060's own
sibling note about ITS mutation check: this mutates a value this test holds
in memory, never a tracked file, so "restore" is the sha256 equality this
test asserts directly, not a file copy-back.

**Why the parent's emission-order finding (named in this task's own
Description) does not surface here.** That finding is about whether
`(allow network-bind)` precedes `(deny network* (with no-log))` -- an
ordering question `tests/unit/test_seatbelt_profile.py` already owns and
pins with a golden. This file's own job is behavioural: does the compiled
profile, run for real, actually bind where it says it will and deny
everywhere else. Observation 1 succeeding IS the check that the render's
`network-bind` line, wherever it sits, does what it claims.

`sun_path` is 104 bytes on darwin (CLAUDE.md's trap list): every endpoint
here lives directly under a short `/tmp/bg<pid>ch<n>` scratch root, never
pytest's `tmp_path`, and its realpath'd `/private/tmp/...` form (the one the
kernel actually checks) stays comfortably under the limit by construction.

Darwin-gated at module level with a visible skip reason, same posture as
`test_seatbelt_smoke.py`: `sandbox-exec` and SBPL do not exist elsewhere.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import os
import pathlib
import shutil
import sys

import pytest

from brig.core import Channel, ChannelKind, Spec
from brig.mech import StagedFile
from brig.mech.seatbelt import seatbelt
from brig.run.compile_ctx import build_compile_ctx
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import CompiledJail, Stack
from tests.conftest import teardown_group

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="seatbelt/sandbox-exec is darwin-only (SPEC.md §6's seatbelt roster row)",
)

_jail_counter = itertools.count()
_WAIT_TIMEOUT_S = 10.0

#: Path to the ONE file this task's mutation check must prove it never wrote
#: to -- `brig/mech/seatbelt/profile.py`, which owns `render_sbpl` (this
#: task's own Out-of-scope section forbids editing `brig/mech/seatbelt/`
#: outright; the mutation check operates on an in-memory `CompiledJail`
#: copy instead, and this path is what its sha256-equality assertion reads).
_PROFILE_PY_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "brig"
    / "mech"
    / "seatbelt"
    / "profile.py"
)

_PAIR_BIND_SCRIPT_TEMPLATE = """\
import socket
import sys


def _try_bind(path):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.bind(path)
    except OSError as e:
        return None, str(e)
    return s, None


s1, err1 = _try_bind({ep1!r})
if s1 is None:
    print("BIND1_FAIL:" + err1, flush=True)
    sys.exit(1)
s1.listen(1)
print("BIND1_OK", flush=True)

s2, err2 = _try_bind({ep2!r})
if s2 is None:
    print("BIND2_FAIL:" + err2, flush=True)
else:
    print("BIND2_OK", flush=True)
    s2.close()

# The trusted-side connect (this test's own handle.wait_ready call) queues
# in the kernel backlog the instant listen() above runs -- accept() here
# only has to complete it, never block waiting on the jail's own doing.
conn, _addr = s1.accept()
conn.close()
s1.close()
print("DONE", flush=True)
"""

_SINGLE_BIND_SCRIPT_TEMPLATE = """\
import socket

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    s.bind({ep!r})
except OSError as e:
    print("BIND_FAIL:" + str(e), flush=True)
else:
    print("BIND_OK", flush=True)
    s.close()
"""


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>ch<n>` -- never `tmp_path`. The
    `ch` infix ("channel") keeps this file's jail dirs from colliding with
    any sibling integration file's own counter (same convention as
    `test_seatbelt_smoke.py`'s own `sb` infix, `test_env_scrub.py`'s `es`,
    etc.)."""
    return f"/tmp/bg{os.getpid()}ch{next(_jail_counter)}"


def _pair_bind_script(ep1: str, ep2: str) -> str:
    return _PAIR_BIND_SCRIPT_TEMPLATE.format(ep1=ep1, ep2=ep2)


def _single_bind_script(ep: str) -> str:
    return _SINGLE_BIND_SCRIPT_TEMPLATE.format(ep=ep)


def _teardown(handle: Handle, jail_dir: str) -> None:
    """Group-kill the workload regardless of how the test above fared, then
    remove the whole jail directory -- AC #8's "every socket the test binds
    is unlinked by the test's own teardown". The kill is deliberately
    hand-rolled (`killpg`), same posture as `test_wait_ready.py`'s own
    `_teardown`: a test's cleanup path must not be the code under test.
    `handle.wait()` blocks until the launcher's exit-waiter has reaped it
    (task-073)."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)
    shutil.rmtree(jail_dir, ignore_errors=True)


def _staged_profile(jail: CompiledJail) -> StagedFile:
    for staged in jail.staged:
        if staged.relpath == "seatbelt.sb":
            return staged
    raise AssertionError("compiled jail carries no seatbelt.sb staged file")


# ---------------------------------------------------------------------------
# Observation 1 + 2: the declared endpoint binds (readiness by connect), and
# a second, undeclared path is denied -- SAME jailed process, SAME run.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_declared_endpoint_binds_readiness_by_connect_and_second_path_denied() -> None:
    """AC #2 and #3. One jailed `python3 -c` process: binds+listens at the
    declared LISTEN channel's own endpoint (`ep1`), then attempts a second
    bind at an undeclared path (`ep2`) inside the same scratch root, then
    `accept()`s the trusted-side connect and exits.

    Observation 1's readiness is proved by THIS test's own
    `handle.wait_ready` call -- SPEC.md §10.1's own connect, never
    `os.path.exists(ep1)`, which this test never calls on `ep1` at all.
    Observation 2's denial is read from the jailed process's OWN captured
    stdout (never from argv), and matched against seatbelt's declared
    denial signature in both directions is AC #5, split out into its own
    control-bearing assertion below (`pattern.search` on the BIND2 line
    only, never on the BIND1_OK / DONE lines)."""
    jail_dir = _new_jail_dir()
    ep1 = f"{jail_dir}/ep1.sock"
    ep2 = f"{jail_dir}/ep2.sock"
    channel = Channel(name="ch", kind=ChannelKind.LISTEN, endpoint=ep1)
    spec = Spec(channels=(channel,))
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="darwin")
    jail = Stack([seatbelt]).compile(spec, ctx=ctx)
    pattern = seatbelt.compile(spec, ctx).denial_signatures[0]

    launcher = SubprocessLauncher()
    handle = launcher.launch(
        jail,
        argv=[sys.executable, "-c", _pair_bind_script(ep1, ep2)],
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="seatbelt-channel-pair",
        jail_dir=jail_dir,
    )
    try:
        # Observation 1: readiness proved by a trusted-side CONNECT that
        # succeeds. If the declared endpoint's own bind were denied, this
        # raises WaitReadyTimeout instead of returning -- there is no path
        # through this test that reads "ready" from the socket FILE merely
        # existing.
        handle.wait_ready("ch", timeout=_WAIT_TIMEOUT_S)

        status = handle.wait()
        with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
            stdout_text = f.read()

        assert status == 0, (
            f"jailed probe did not exit cleanly: status={status} out={stdout_text!r}"
        )
        assert "BIND1_OK" in stdout_text, (
            f"declared endpoint bind did not report success: {stdout_text!r}"
        )
        assert "DONE" in stdout_text, f"probe did not reach its own accept()/exit: {stdout_text!r}"

        # Observation 2, same jail, same run.
        bind2_line = next(
            (line for line in stdout_text.splitlines() if line.startswith("BIND2_")), None
        )
        assert bind2_line is not None, f"no BIND2 result captured in {stdout_text!r}"
        assert bind2_line.startswith("BIND2_FAIL:"), (
            f"bind to a second, undeclared path unexpectedly succeeded: {bind2_line!r}"
        )
        # AC #5, denial direction: the jailed process's own captured text
        # for the SECOND path matches seatbelt's declared signature.
        assert pattern.search(bind2_line) is not None, (
            f"second-path denial text did not match seatbelt's declared "
            f"signature {pattern.pattern!r}: {bind2_line!r}"
        )
        # AC #5, control direction: that same signature does NOT match the
        # declared endpoint's own successful bind line.
        assert pattern.search("BIND1_OK") is None
    finally:
        _teardown(handle, jail_dir)


# ---------------------------------------------------------------------------
# Observation 3: no channel declared -- every bind is denied, and the
# profile this test compiled is asserted to carry zero unscoped
# network-bind allows (so the denial is pinned to the absent rule).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_no_channel_declared_denies_bind_and_profile_carries_no_network_bind_allow() -> None:
    """AC #4. `spec.channels == ()`: `render_sbpl` emits zero
    `(allow network-bind)` lines (`brig.mech.seatbelt.profile`'s own
    documented conditionality, plan ambiguity A2) -- asserted directly
    against the profile THIS test compiled and staged, not merely assumed.
    A jailed bind attempt against that exact profile is then denied,
    matching seatbelt's declared signature."""
    jail_dir = _new_jail_dir()
    ep = f"{jail_dir}/nobind.sock"
    spec = Spec()
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="darwin")
    jail = Stack([seatbelt]).compile(spec, ctx=ctx)
    pattern = seatbelt.compile(spec, ctx).denial_signatures[0]

    profile_text = _staged_profile(jail).content
    assert "(allow network-bind)" not in profile_text, (
        "a spec with zero channels must compile zero unscoped network-bind "
        f"allows, but the compiled profile carries one:\n{profile_text}"
    )

    launcher = SubprocessLauncher()
    handle = launcher.launch(
        jail,
        argv=[sys.executable, "-c", _single_bind_script(ep)],
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="seatbelt-channel-none",
        jail_dir=jail_dir,
    )
    try:
        status = handle.wait()
        with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
            stdout_text = f.read()

        assert status == 0, (
            f"jailed probe did not exit cleanly: status={status} out={stdout_text!r}"
        )
        assert "BIND_FAIL:" in stdout_text, (
            f"bind with no channel declared unexpectedly succeeded: {stdout_text!r}"
        )
        assert pattern.search(stdout_text) is not None, (
            f"no-channel denial text did not match seatbelt's declared "
            f"signature {pattern.pattern!r}: {stdout_text!r}"
        )
    finally:
        _teardown(handle, jail_dir)


# ---------------------------------------------------------------------------
# AC #7: the control against the ENVIRONMENT, not the jail. Same probes,
# Stack([]) -- zero mechanisms, wrap is the identity -- succeed at both
# paths the two tests above found denied.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_control_unconfined_stack_binds_succeed_at_both_denied_paths() -> None:
    """AC #7. The exact same two probes as the two denial tests above,
    launched through `Stack([])` -- no mechanisms, so `CompiledJail.wrap`
    is the identity and the workload runs entirely unconfined -- succeed at
    every path that was denied under seatbelt: the second, undeclared path
    from observation 2, and the no-channel bind from observation 3. This is
    what proves those two denials were the JAIL's doing (SBPL) and not, say,
    ordinary POSIX permissions on a scratch `/tmp` directory this test's own
    user already owns."""
    launcher = SubprocessLauncher()

    # --- the pair probe, unconfined: BOTH binds succeed -----------------
    jail_dir = _new_jail_dir()
    ep1 = f"{jail_dir}/ep1.sock"
    ep2 = f"{jail_dir}/ep2.sock"
    channel = Channel(name="ch", kind=ChannelKind.LISTEN, endpoint=ep1)
    spec = Spec(channels=(channel,))
    jail = Stack([]).compile(spec)

    handle = launcher.launch(
        jail,
        argv=[sys.executable, "-c", _pair_bind_script(ep1, ep2)],
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="seatbelt-channel-control-pair",
        jail_dir=jail_dir,
    )
    try:
        handle.wait_ready("ch", timeout=_WAIT_TIMEOUT_S)
        status = handle.wait()
        with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
            stdout_text = f.read()
        assert status == 0, (
            f"control probe did not exit cleanly: status={status} out={stdout_text!r}"
        )
        assert "BIND1_OK" in stdout_text
        assert "BIND2_OK" in stdout_text, (
            f"control (Stack([]), no jail) must succeed at the SECOND path "
            f"too -- that is what makes observation 2's own denial the "
            f"jail's doing, not the filesystem's: {stdout_text!r}"
        )
    finally:
        _teardown(handle, jail_dir)

    # --- the no-channel probe, unconfined: still succeeds ----------------
    jail_dir2 = _new_jail_dir()
    ep3 = f"{jail_dir2}/nobind.sock"
    spec2 = Spec()
    jail2 = Stack([]).compile(spec2)

    handle2 = launcher.launch(
        jail2,
        argv=[sys.executable, "-c", _single_bind_script(ep3)],
        cwd=jail_dir2,
        io=IoPolicy(),
        jail_id="seatbelt-channel-control-none",
        jail_dir=jail_dir2,
    )
    try:
        status2 = handle2.wait()
        with open(handle2.stdout_path, encoding="utf-8", errors="replace") as f:
            stdout_text2 = f.read()
        assert status2 == 0, (
            f"control probe did not exit cleanly: status={status2} out={stdout_text2!r}"
        )
        assert "BIND_OK" in stdout_text2, (
            f"control (Stack([]), no channel) must still succeed -- that is "
            f"what makes observation 3's own denial the jail's doing, not "
            f"the filesystem's: {stdout_text2!r}"
        )
    finally:
        _teardown(handle2, jail_dir2)


# ---------------------------------------------------------------------------
# AC #6: mutation check. Strip the endpoint's own file-write literal rule
# from THIS TEST's already-compiled profile (in-memory only) and re-run
# observation 1's own bind -- it must go red (denied).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_mutation_check_removing_endpoint_write_rule_denies_the_declared_bind() -> None:
    """AC #6. Never edits `brig/mech/seatbelt/` (this task's Out-of-scope
    section forbids it outright) -- mutates only an in-memory
    `CompiledJail.staged` copy this test itself built, via
    `dataclasses.replace`. `brig/mech/seatbelt/profile.py`'s own sha256 is
    asserted byte-identical before and after: that IS this mutation's
    "restore", per decision-074 read together with task-060's own sibling
    note that ITS mutation check touches a value held in memory, never a
    tracked file -- there is nothing on disk to copy back because nothing
    on disk was ever opened for writing.

    With the LISTEN channel's own `(allow file-write* (literal "..."))`
    line gone, `render_sbpl`'s docstring says plainly what must happen:
    "the channel's own bind rule would compile as text but the child could
    never actually create its socket file there." This test proves exactly
    that clause, for real, against the real kernel."""
    digest_before = hashlib.sha256(_PROFILE_PY_PATH.read_bytes()).hexdigest()

    jail_dir = _new_jail_dir()
    ep1 = f"{jail_dir}/ep1.sock"
    channel = Channel(name="ch", kind=ChannelKind.LISTEN, endpoint=ep1)
    spec = Spec(channels=(channel,))
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="darwin")
    jail = Stack([seatbelt]).compile(spec, ctx=ctx)
    pattern = seatbelt.compile(spec, ctx).denial_signatures[0]

    original = _staged_profile(jail)
    resolved_ep1 = ctx.resolved_paths[ep1]
    victim_line = f'(allow file-write* (literal "{resolved_ep1}"))'
    assert victim_line in original.content, (
        f"expected line {victim_line!r} not found in the compiled profile "
        f"-- this test's own fixture has drifted from profile.py's render:\n"
        f"{original.content}"
    )
    mutated_lines = [line for line in original.content.splitlines() if line != victim_line]
    mutated_content = "\n".join(mutated_lines) + "\n"
    mutated_staged = StagedFile(relpath="seatbelt.sb", content=mutated_content, mode=original.mode)
    mutated_jail = dataclasses.replace(jail, staged=(mutated_staged,))

    launcher = SubprocessLauncher()
    handle = launcher.launch(
        mutated_jail,
        argv=[sys.executable, "-c", _single_bind_script(ep1)],
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="seatbelt-channel-mutation",
        jail_dir=jail_dir,
    )
    try:
        status = handle.wait()
        with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
            stdout_text = f.read()
        assert status == 0, (
            f"mutated probe did not exit cleanly: status={status} out={stdout_text!r}"
        )
        assert "BIND_FAIL:" in stdout_text, (
            "MUTATION CHECK FAILED TO GO RED -- removing the endpoint's own "
            f"file-write literal rule did not deny the bind: {stdout_text!r}"
        )
        assert pattern.search(stdout_text) is not None, (
            f"mutated-profile denial text did not match seatbelt's declared "
            f"signature {pattern.pattern!r}: {stdout_text!r}"
        )
    finally:
        _teardown(handle, jail_dir)

    digest_after = hashlib.sha256(_PROFILE_PY_PATH.read_bytes()).hexdigest()
    assert digest_after == digest_before, (
        "brig/mech/seatbelt/profile.py must be byte-identical before and "
        "after this mutation check -- only the in-memory compiled artifact "
        f"was mutated. before={digest_before} after={digest_after}"
    )

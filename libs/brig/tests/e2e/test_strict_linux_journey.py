"""`strict_linux()` driven through the public API, end to end, on a real
linux host: compile against floors, launch, cross the declared channel,
observe the enforcement from inside, tear down and check the report.

The linux counterpart of `tests/e2e/test_scratch_darwin_batteries.py`'s
journey half. What this file adds over
`tests/integration/test_bwrap_fs.py` is composition: three mechanisms at
once, in the matrix's own order, with the trampoline outside the jail and
`env_scrub`'s `/bin/sh -c 'exec env -i ...'` INSIDE it -- which is the one
arrangement the unit tier can only assert about an argv, and which fails
loudly here if `/bin/sh` or `/usr/bin/env` is not reachable inside an
allowlist jail.

Six things happen in one run, and each is a claim:

1. The stack compiles against `fs_read`/`fs_write`/`network` `enforced` as
   FLOORS -- so the preset's own report is what admits it, not this file's
   opinion of it.
2. The workload starts at all, which is the whole `bwrap`-outside-
   `env_scrub` ordering claim: two more images (`/bin/sh`, `/usr/bin/env`)
   have to exist inside the jail before the workload's own does.
3. Its environment carries nothing from the launching process -- a canary
   set here is gone, and the only name that survives is one the interpreter
   sets for itself -- proving `env_scrub` ran innermost.
4. It writes inside the workspace and is refused outside it.
5. It binds the declared LISTEN channel's socket, `wait_ready` observes the
   bind by CONNECTING (not by looking for the path), and the trusted side
   exchanges a line over it -- the channel crossing bwrap's stage-6
   directory bind exists for.
6. `handle.kill()` ends the process group and its `KillReport` says
   `ENDED` after the verification rung, not merely "signal sent".

**Skips visibly by name.** bubblewrap is linux-only and installed by no
default image; `python3` is needed inside the jail because `dash` cannot
bind a socket.

**Executed on linux 2026-09-08.** The development machine is darwin, where
this file skips; it was run on a real linux kernel in a container by
`tools/linux-check.sh` (the keel workspace's reproduction of the
`verify-linux` CI job) and passes there. What that is NOT is a GitHub
Actions run: the job itself has still never been observed, and a container
is not the runner image.

Running it found three things that had never been true, only written:
`env_scrub`'s empty environment is empty but for the `LC_CTYPE` CPython
sets on ITSELF (PEP 538); a single `accept()` here spent the socket on
`wait_ready`'s own readiness connect and left this test's connect to be
reset; and bwrap mounted the channel's directory over the `write_denies`
carve-out inside it, so the jail wrote the path it was denied
(decision-163, a real hole, fixed in the mechanism rather than around it
here).
"""

from __future__ import annotations

import os
import socket
import sys

import pytest

from brig.core import (
    Channel,
    ChannelKind,
    FsPolicy,
    Grade,
    ReadModel,
    Spec,
    require,
)
from brig.mech.bwrap import DEFAULT_BWRAP_PATH
from brig.run.compile_ctx import build_compile_ctx
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import strict_linux

_PYTHON = "/usr/bin/python3"

#: The skip is an AUTOUSE FIXTURE rather than a module-level
#: `pytest.mark.skipif`, and the reason is mechanical: `skipif`'s condition
#: is evaluated at IMPORT time, so probing for the binary there is an
#: import-time `os.path.exists` -- which pypeeker's
#: `import-time-side-effects` rule refuses, workspace-wide, for good
#: reasons that do not stop applying inside a test file. A fixture asks the
#: same question at setup time and reports the same visible, named skip.


@pytest.fixture(autouse=True)
def _needs_bubblewrap_and_python() -> None:
    if (
        sys.platform != "linux"
        or not os.path.exists(DEFAULT_BWRAP_PATH)
        or not os.path.exists(_PYTHON)
    ):
        pytest.skip(
            f"strict_linux() needs bubblewrap at {DEFAULT_BWRAP_PATH} and an "
            f"interpreter at {_PYTHON} on linux (sys.platform is {sys.platform!r}); "
            "install the `bubblewrap` package"
        )


_READY_TIMEOUT_S = 30.0
_SYSTEM_ROOTS = ("/bin", "/usr", "/lib", "/lib64", "/etc")

_WORKLOAD = """
import os, socket, sys

endpoint = sys.argv[1]
workspace = sys.argv[2]
denied = sys.argv[3]

with open(os.path.join(workspace, "control.txt"), "w") as f:
    f.write("wrote")
print("CONTROL_WRITE_OK", flush=True)

try:
    with open(os.path.join(denied, "pre-commit"), "w") as f:
        f.write("pwned")
except OSError as exc:
    print("DENIED:", exc, file=sys.stderr, flush=True)
else:
    print("DENIAL_FAILED", flush=True)

print("ENVKEYS", ",".join(sorted(os.environ)), flush=True)

server = socket.socket(socket.AF_UNIX)
server.bind(endpoint)
server.listen(2)
# Serve every caller, not one: `wait_ready` proves the bind by CONNECTING
# (SPEC.md sec 10.1), so the trusted side opens TWO connections -- the
# readiness probe first, then the test's own. A single `accept()` here spent
# the socket on the probe and left the second connect to be reset, which is
# exactly what happened the first time this file was ever executed
# (2026-09-08). The loop ends when the group is killed, which is claim 6.
while True:
    conn, _ = server.accept()
    try:
        conn.sendall(b"hello from the jail\\n")
    except OSError:
        # The readiness probe connects and hangs up without reading, so the
        # greeting written to IT is undeliverable. Unguarded, that killed
        # this server on its first connection and left the test's own
        # connect to be reset -- the second half of the same 2026-09-08
        # finding as the accept loop above.
        pass
    finally:
        conn.close()
"""


#: Names the workload may carry that did NOT come from the launching
#: process. CPython sets `LC_CTYPE=C.UTF-8` on itself at startup under a
#: POSIX locale (PEP 538's legacy C locale coercion), AFTER `env -i` has
#: already emptied the environment -- so "the child's environment is empty"
#: was a claim about darwin, where the coercion does not fire, and it failed
#: the first time this file ran on linux (2026-09-08). What `env_scrub`
#: actually promises is that nothing crosses from the PARENT, which is what
#: the canary below proves; this set is the interpreter's own doing.
_INTERPRETER_SET_NAMES = frozenset({"LC_CTYPE"})

#: Set in this process's environment so its absence inside the jail means
#: something. A name no tool reads, so nothing but a leak can put it there.
_CANARY_NAME = "BRIG_STRICT_LINUX_JOURNEY_CANARY"


@pytest.mark.e2e
def test_the_linux_preset_confines_launches_and_talks_over_its_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_CANARY_NAME, "leaked")
    jail_dir = f"/tmp/bg{os.getpid()}sl0"
    workspace = f"{jail_dir}/ws"
    hooks = f"{workspace}/.git/hooks"
    endpoint = f"{jail_dir}/agent.sock"
    os.makedirs(hooks, exist_ok=True)

    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(p for p in _SYSTEM_ROOTS if os.path.exists(p)),
            write_allows=(workspace,),
            write_denies=(hooks,),
        ),
        channels=(Channel(name="agent", kind=ChannelKind.LISTEN, endpoint=endpoint),),
    )
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")

    # Claim 1: the preset's own report admits it, against real floors.
    jail = strict_linux().compile(
        spec,
        require(fs_read=Grade.ENFORCED, fs_write=Grade.ENFORCED, network=Grade.ENFORCED),
        ctx=ctx,
    )

    handle = SubprocessLauncher().launch(
        jail,
        argv=[_PYTHON, "-c", _WORKLOAD, endpoint, workspace, hooks],
        cwd=workspace,
        io=IoPolicy(),
        jail_id="strict-linux-journey",
        jail_dir=jail_dir,
    )
    try:
        # Claim 5a: readiness is a CONNECT, not a path check (SPEC.md sec 10).
        handle.wait_ready("agent", _READY_TIMEOUT_S)

        # Claim 5b: the crossing carries bytes. This is the SECOND
        # connection the jail serves; `wait_ready` above made the first.
        client = socket.socket(socket.AF_UNIX)
        client.settimeout(_READY_TIMEOUT_S)
        client.connect(endpoint)
        greeting = client.recv(64)
        client.close()
        assert greeting == b"hello from the jail\n"

        with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
            stdout = f.read()
        with open(handle.stderr_path, encoding="utf-8", errors="replace") as f:
            stderr = f.read()

        # Claims 2 and 4: it started (so /bin/sh and /usr/bin/env were
        # inside the jail) and the workspace write landed.
        assert "CONTROL_WRITE_OK" in stdout
        assert os.path.isfile(f"{workspace}/control.txt")
        assert "DENIAL_FAILED" not in stdout
        assert "DENIED:" in stderr
        assert not os.path.exists(f"{hooks}/pre-commit")

        # Claim 3: env_scrub really did run innermost. The canary this
        # test put in its OWN environment is the discriminating half --
        # without `env -i` the launcher hands the workload this process's
        # environment, canary included -- and the whole surviving set is
        # pinned beside it, so a second name appearing is a visible failure
        # rather than something this assertion is blind to.
        envkeys_line = next(
            (line for line in stdout.splitlines() if line.startswith("ENVKEYS")), None
        )
        assert envkeys_line is not None, stdout
        names = {name for name in envkeys_line.removeprefix("ENVKEYS").strip().split(",") if name}
        assert _CANARY_NAME not in names, f"the parent environment reached the jail: {names}"
        assert names <= _INTERPRETER_SET_NAMES, (
            f"the jail carries a name neither env_scrub nor the interpreter accounts for: {names}"
        )
    finally:
        report = handle.kill()

    # Claim 6: the ladder's last rung is verification, per item.
    outcomes = {item.kind: item.outcome.value for item in report.items}
    # The workload serves connections until it is killed, so the group is
    # alive when `kill()` runs: `ENDED` is the outcome, and `ALREADY_GONE`
    # is accepted only because a jail that died on its own is not this
    # claim's business.
    assert outcomes["workload_group"] in {"ENDED", "ALREADY_GONE"}
    assert not handle.alive()

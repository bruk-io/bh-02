"""`bwrap`'s `fs_read`/`fs_write` enforcement, observed from INSIDE a real
bubblewrap jail on linux -- never asserted about the argv handed to
`bwrap`, which is `tests/unit/test_bwrap_compile.py`'s job.

Every claim here is a PAIR: a denial and its own control, made by the same
jailed `/bin/sh` in the same run, reporting through the launcher's captured
stdio. A probe that would pass identically against an unconfined process
proves nothing, so the control is what makes each denial mean the jail.

Three pairs, one per shape the mount plan has:

1. A write to a path outside every write root is denied and matches the
   mechanism's own declared `Read-only file system` signature; a write
   inside the workspace succeeds.
2. A write into a `write_denies` carve-out that EXISTS -- compiled as the
   read-only bind form -- is denied and matches the same signature; a
   sibling path inside the same workspace, in the same run, succeeds.
3. A write at a `write_denies` carve-out that does NOT exist -- compiled as
   the empty read-only tmpfs form -- is refused, and the host path is still
   not a file afterwards. This pair asserts the ENFORCEMENT and
   deliberately does NOT assert the signature: an empty tmpfs is a
   DIRECTORY, so the shell's own message is "Is a directory" rather than
   the read-only one, and "Is a directory" is exactly the generic text a
   denial signature may not match (SPEC.md sec 6). The consequence is
   named in the mechanism's `fs_write` grade detail rather than papered
   over here.

A fourth observation, which is the allowlist model itself: a path that is
in no `read_allows` entry cannot be read, and fails by ABSENCE (ENOENT)
rather than with a denial message. That is why this mechanism declares no
`fs_read` signature at all, and the test asserts the absence rather than a
match.

**Skips visibly by name.** bubblewrap is linux-only and is not installed by
default anywhere; the skip reason names the binary and the path it was
looked for at, so a skipped run says which package to install rather than
merely being green. The workflow installs `bubblewrap` on its ubuntu job
for exactly this reason.

**Executed on linux 2026-09-08.** The development machine is darwin, where
this file skips; it was run on a real linux kernel in a container by
`tools/linux-check.sh` (the keel workspace's reproduction of the
`verify-linux` CI job) and passes there. What that is NOT is a GitHub
Actions run: the job itself has still never been observed, and a container
is not the runner image.

The read-allowlist test below is the one test in this suite that launches
TWICE into a single jail directory, and running it on linux is how brig's
stale-exit-record defect was found (decision-162): the control's `wait()`
answered with the FIRST launch's status.
"""

from __future__ import annotations

import itertools
import os
import re
import sys

import pytest

from brig.core import Channel, ChannelKind, FsPolicy, ReadModel, Spec
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, bwrap
from brig.run.compile_ctx import build_compile_ctx
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack

#: The skip is an AUTOUSE FIXTURE rather than a module-level
#: `pytest.mark.skipif`, and the reason is mechanical: `skipif`'s condition
#: is evaluated at IMPORT time, so probing for the binary there is an
#: import-time `os.path.exists` -- which pypeeker's
#: `import-time-side-effects` rule refuses, workspace-wide, for good
#: reasons that do not stop applying inside a test file. A fixture asks the
#: same question at setup time and reports the same visible, named skip.


@pytest.fixture(autouse=True)
def _needs_bubblewrap() -> None:
    if sys.platform != "linux" or not os.path.exists(DEFAULT_BWRAP_PATH):
        pytest.skip(
            f"bwrap needs bubblewrap at {DEFAULT_BWRAP_PATH} on linux "
            f"(sys.platform is {sys.platform!r}); install the `bubblewrap` package"
        )


_jail_counter = itertools.count()
_WAIT_TIMEOUT_S = 30.0

#: The system tree a jailed `/bin/sh` needs to exist at all under an
#: ALLOWLIST read model. Filtered by existence at fixture time -- a
#: distribution without `/lib64` is a fact about the host, and mounting a
#: path that is not there is a launch failure, not a policy.
_SYSTEM_ROOTS = ("/bin", "/usr", "/lib", "/lib64", "/etc")


def _system_read_allows() -> tuple[str, ...]:
    return tuple(path for path in _SYSTEM_ROOTS if os.path.exists(path))


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>bw<n>` -- never `tmp_path`. The
    `bw` infix keeps this file's jail dirs from colliding with a sibling
    integration file's own counter in the same pytest session."""
    return f"/tmp/bg{os.getpid()}bw{next(_jail_counter)}"


def _denial_signature() -> re.Pattern[str]:
    """The mechanism's OWN declared read-only signature, fetched from a
    real compiled `Step` rather than hand-copied as a literal, so this file
    tests what `bwrap` actually declares. Computed inside a test (never at
    import time) so nothing runs during collection ahead of the skip."""
    spec = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST))
    ctx = build_compile_ctx(spec, jail_dir=_new_jail_dir(), platform="linux")
    return bwrap.compile(spec, ctx).denial_signatures[0]


def _run_in_jail(*, jail_dir: str, spec: Spec, script: str, label: str) -> tuple[int, str, str]:
    """Compile `spec` through a real `Stack([bwrap])`, run `script` in a
    real jailed `/bin/sh`, and return `(status, stdout, stderr)` read from
    the jail's own log files -- observed from inside the jail, never from
    the compiled `Step`.

    `cwd` is the workspace rather than the jail dir: the workspace is
    always bind-mounted, and a cwd that does not exist inside the jail is
    not a thing bwrap can honour.
    """
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    jail = Stack([bwrap]).compile(spec, ctx=ctx)
    handle = SubprocessLauncher().launch(
        jail,
        argv=["/bin/sh", "-c", script],
        cwd=spec.fs.write_allows[0],
        io=IoPolicy(),
        jail_id=f"bwrap-fs-{label}",
        jail_dir=jail_dir,
    )
    status = handle.wait(timeout=_WAIT_TIMEOUT_S)
    with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
        stdout = f.read()
    with open(handle.stderr_path, encoding="utf-8", errors="replace") as f:
        stderr = f.read()
    return status, stdout, stderr


def _seed_workspace(jail_dir: str) -> tuple[str, str, str]:
    """Create the jail dir and a workspace holding an EXISTING carve-out
    (`.git/hooks`) beside an ABSENT one (`.envrc`). Returns the three
    paths."""
    workspace = f"{jail_dir}/ws"
    hooks = f"{workspace}/.git/hooks"
    envrc = f"{workspace}/.envrc"
    os.makedirs(hooks, exist_ok=True)
    return workspace, hooks, envrc


def _spec_for(workspace: str, hooks: str, envrc: str, *, endpoint: str | None = None) -> Spec:
    channels = (
        (Channel(name="agent", kind=ChannelKind.LISTEN, endpoint=endpoint),)
        if endpoint is not None
        else ()
    )
    return Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=_system_read_allows(),
            write_allows=(workspace,),
            write_denies=(hooks, envrc),
        ),
        channels=channels,
    )


@pytest.mark.integration
def test_a_write_outside_every_write_root_is_denied_and_inside_succeeds() -> None:
    """Pair 1. `/etc` is in `read_allows`, so it EXISTS inside the jail and
    is mounted read-only -- which is what makes this a denial with the
    mechanism's own signature rather than a mere absence."""
    jail_dir = _new_jail_dir()
    workspace, hooks, envrc = _seed_workspace(jail_dir)
    spec = _spec_for(workspace, hooks, envrc)

    status, stdout, stderr = _run_in_jail(
        jail_dir=jail_dir,
        spec=spec,
        script=f"echo pwned > /etc/brig-canary; echo ok > {workspace}/control.txt; echo CONTROL",
        label="outside",
    )

    assert _denial_signature().search(stderr) is not None, stderr
    assert "CONTROL" in stdout
    assert os.path.isfile(f"{workspace}/control.txt"), "the control write did not land"
    assert not os.path.exists("/etc/brig-canary")
    assert status == 0  # the trailing control command is what sets the status


@pytest.mark.integration
def test_an_existing_write_denies_carveout_is_denied_and_a_sibling_succeeds() -> None:
    """Pair 2, the read-only BIND form. The carve-out sits INSIDE the
    granted workspace, so nothing but `write_denies` can be denying it --
    which is what the sibling write in the same run proves."""
    jail_dir = _new_jail_dir()
    workspace, hooks, envrc = _seed_workspace(jail_dir)
    spec = _spec_for(workspace, hooks, envrc)

    status, stdout, stderr = _run_in_jail(
        jail_dir=jail_dir,
        spec=spec,
        script=(
            f"echo pwned > {hooks}/pre-commit; echo ok > {workspace}/sibling.txt; echo CONTROL"
        ),
        label="carveout-bind",
    )

    assert _denial_signature().search(stderr) is not None, stderr
    assert "CONTROL" in stdout
    assert not os.path.exists(f"{hooks}/pre-commit")
    assert os.path.isfile(f"{workspace}/sibling.txt")
    assert status == 0


@pytest.mark.integration
def test_an_absent_write_denies_carveout_cannot_be_created() -> None:
    """Pair 3, the empty read-only TMPFS form -- the one an `--ro-bind-try`
    would have skipped silently, leaving the jail free to write the
    `.envrc` it was denied. Enforcement is asserted (the write fails, and
    the host path is still not a file); the signature deliberately is not,
    for the reason this module's docstring gives.

    Whether bubblewrap materialises the mount point under the writable root
    is bwrap's own behaviour rather than a claim brig makes, so it is left
    unasserted here -- `isfile`, not `exists`, is the enforcement
    question."""
    jail_dir = _new_jail_dir()
    workspace, hooks, envrc = _seed_workspace(jail_dir)
    spec = _spec_for(workspace, hooks, envrc)

    _status, stdout, _stderr = _run_in_jail(
        jail_dir=jail_dir,
        spec=spec,
        script=(
            f"echo pwned > {envrc} && echo DENIAL_FAILED; "
            f"echo ok > {workspace}/sibling.txt && echo CONTROL"
        ),
        label="carveout-tmpfs",
    )

    assert "DENIAL_FAILED" not in stdout
    assert "CONTROL" in stdout
    assert not os.path.isfile(envrc), "the jail created the file it was denied"


@pytest.mark.integration
def test_a_path_outside_read_allows_is_absent_rather_than_denied() -> None:
    """The allowlist model itself, and the reason this mechanism declares
    no `fs_read` signature. A file seeded OUTSIDE every `read_allows` entry
    is unreadable inside the jail; the same read succeeds through
    `Stack([])` -- the permanent control, which is what makes this an
    observation about the jail rather than about this host's own file
    permissions."""
    jail_dir = _new_jail_dir()
    workspace, hooks, envrc = _seed_workspace(jail_dir)
    secret = f"{jail_dir}/secret.txt"
    with open(secret, "w") as f:
        f.write("SECRETVALUE")
    spec = _spec_for(workspace, hooks, envrc)

    _status, stdout, stderr = _run_in_jail(
        jail_dir=jail_dir, spec=spec, script=f"cat {secret}", label="read-absent"
    )

    assert "SECRETVALUE" not in stdout
    assert "No such file or directory" in stderr
    # None of the mechanism's declared signatures may match an absence --
    # a signature that did would turn this into a false PASS in the probe
    # engine (SPEC.md sec 12).
    for pattern in bwrap.compile(
        spec, build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    ).denial_signatures:
        assert pattern.search(stderr) is None

    # The control: without the jail, the same read succeeds.
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    unjailed = Stack([]).compile(spec, ctx=ctx)
    handle = SubprocessLauncher().launch(
        unjailed,
        argv=["/bin/sh", "-c", f"cat {secret}"],
        cwd=workspace,
        io=IoPolicy(stdout_name="control-stdout.log", stderr_name="control-stderr.log"),
        jail_id="bwrap-fs-read-absent-control",
        jail_dir=jail_dir,
    )
    handle.wait(timeout=_WAIT_TIMEOUT_S)
    with open(handle.stdout_path, encoding="utf-8", errors="replace") as f:
        assert "SECRETVALUE" in f.read()


@pytest.mark.integration
def test_a_read_carve_out_inside_the_workspace_is_refused_and_a_sibling_reads() -> None:
    """decision-164, observed. A credential FILE and a state DIRECTORY sit
    inside the writable workspace, named in `read_denies`: the file reads
    EACCES (the null device, bound `nodev`), the directory can be neither
    listed, read beneath, written into, nor chmod'ed back open (an empty
    mode-0000 read-only tmpfs), and a sibling file in the same workspace
    reads in the same run -- the control that makes the refusals the
    carve-outs' doing. The host's files are untouched."""
    jail_dir = _new_jail_dir()
    workspace, hooks, envrc = _seed_workspace(jail_dir)
    secret, state = f"{workspace}/local.env", f"{workspace}/state"
    os.makedirs(f"{state}/deep")
    for path, text in (
        (secret, "SECRETVALUE"),
        (f"{state}/deep/key", "DEEPVALUE"),
        (f"{workspace}/notes.txt", "fine"),
    ):
        with open(path, "w") as f:
            f.write(text)
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=_system_read_allows(),
            write_allows=(workspace,),
            write_denies=(hooks, envrc),
            read_denies=(secret, state),
        )
    )
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform="linux")
    assert bwrap.compile(spec, ctx).grades  # compiles: both carve-outs exist, so both are masked

    _status, stdout, stderr = _run_in_jail(
        jail_dir=jail_dir,
        spec=spec,
        script=(
            f"cat {secret}; ls {state}; cat {state}/deep/key; echo x > {state}/new; "
            f"chmod 755 {state}; cat {workspace}/notes.txt && echo CONTROL"
        ),
        label="read-carve-out",
    )

    assert "SECRETVALUE" not in stdout and "DEEPVALUE" not in stdout
    assert f"cat: {secret}: Permission denied" in stderr, stderr
    assert f"ls: cannot open directory '{state}': Permission denied" in stderr, stderr
    assert f"cat: {state}/deep/key: Permission denied" in stderr, stderr
    assert f"chmod: changing permissions of '{state}': Read-only file system" in stderr, stderr
    assert "fine" in stdout and "CONTROL" in stdout  # the sibling read, same run
    with open(secret) as f:
        assert f.read() == "SECRETVALUE"  # the host's file, untouched
    assert not os.path.exists(f"{state}/new")


@pytest.mark.integration
def test_an_absent_write_carve_out_is_a_directory_on_the_host_until_someone_removes_it() -> None:
    """What the tmpfs form costs, measured (decision-164 corrected the
    docstring that said it materialised "inside the jail"): bwrap makes the
    mount point inside the write root's bind of the HOST directory, so an
    absent denied `.envrc` is an empty `.envrc/` on the host, and it outlives
    the jail. Removing it is the embedder's, after teardown."""
    jail_dir = _new_jail_dir()
    workspace = f"{jail_dir}/ws"
    os.makedirs(workspace)
    missing_parent = f"{workspace}/.cfg/hooks"  # its parent is absent too
    envrc = f"{workspace}/.envrc"
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=_system_read_allows(),
            write_allows=(workspace,),
            write_denies=(envrc, missing_parent),
        )
    )
    status, stdout, _stderr = _run_in_jail(
        jail_dir=jail_dir, spec=spec, script="echo CONTROL", label="materialised"
    )
    assert status == 0 and "CONTROL" in stdout
    assert os.path.isdir(envrc) and not os.listdir(envrc)
    assert os.path.isdir(missing_parent) and not os.listdir(missing_parent)

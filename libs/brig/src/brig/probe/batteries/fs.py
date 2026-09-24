"""Probe batteries for filesystem write and read axes (SPEC.md §5, §12).

SPEC.md §5 defines write_denies threat (a jail that can write .git/hooks,
.envrc, or an agent config file inside its granted workspace executes code
outside the jail later). These batteries probe that threat and the read
confinement.

SPEC.md §12: Every battery includes positive controls (an action that must
succeed -- write inside the workspace, dial the declared channel) so a
broken probe mechanism cannot impersonate a perfect jail.

This module is pure: no I/O, no clock, no randomness, and it spawns nothing
of its own -- it only returns data describing argv for a caller to run.
`os`, `os.path`, `pathlib`, and `subprocess` are never imported here (see
`tests/unit/test_battery_fs.py`'s purity test) -- resolving a target against
the host is precisely the caller's job, never this module's.

`doc-016` §7 deviation 4 / `doc-016` §9 ask 1 / MILESTONES.md M5-lite's
"battery target-resolution fix" -- three stacked defects, and this module's
shape is the fix for all three:

1. **`"$HOME"` expansion inside the jail.** The old probes embedded the
   literal shell text `"$HOME"/.ssh`; under an env-scrubbing spec `HOME` is
   scrubbed, the jail's own shell expands it to the empty string, and the
   probe targets `/.ssh` instead of the operator's real `~/.ssh` -- a
   target that depends on the JAIL's environment can never be evidence
   about a mechanism (decision-108), because the same probe means a
   different path depending on what it is run against. **The fix**: every
   target this module emits is a plain string handed in by the caller at
   construction time, substituted into argv positionally (`"$0"`, never a
   named shell variable) -- nothing in the rendered script depends on the
   runtime environment at all.
2. **`write_outside_workspace` targeted `/`.** A read-only volume on darwin
   regardless of any jail, so a DENIAL there proves nothing about
   enforcement -- it would "pass" against an empty stack too. **The fix**:
   every write DENIAL probe's target lives under the caller-supplied
   `outside_writable` root, a scratch path the caller owns, genuinely
   writable by an unjailed process, and disposable.
3. **`read_aws_credentials` targeted a file that may not exist.** Absence
   masquerades as denial -- `ENOENT` and "policy denied" are both a
   non-zero exit with no distinguishing text a probe without a mechanism's
   own declared signature can tell apart. **The fix**: every read DENIAL
   probe's target is the caller-supplied `credential_canary`, a path the
   caller has already seeded to exist and be readable before the battery
   runs.

**Every write-shaped probe's target begins with `outside_writable` or the
workspace -- never the real home.** A DENIAL probe proves target resolution
only if it genuinely reaches its target when nothing stops it, which means
against a stack with no fs mechanism every write DENIAL probe here
*succeeds*. A probe that targeted the operator's real `~/.ssh` would plant a
canary file in it on every unjailed integration run -- unacceptable
(`doc-016` §7 deviation 5's "leave the machine as you found it" rule). So
the probe's *name* keeps saying what threat it stands for
(`write_into_home_ssh`); its *target* is a credential-shaped path under a
root the caller owns and cleans up, never the real path the name evokes.

Read probes are the opposite case: reading is non-destructive, so each read
DENIAL probe targets its own caller-seeded, guaranteed-to-exist path rather
than a scratch root it would have to clean up -- `read_aws_credentials`
targets `credential_canary` (a FILE, read with `cat`) and
`read_home_ssh_directory` targets `ssh_directory_canary` (a DIRECTORY, read
with `ls`). Two separate parameters, not one path read two ways: a single
path handed to both `cat` and `ls` collapses either into a vacuous case --
`cat` on a directory fails `EISDIR` (a non-policy failure, `VACUOUS`, about
nothing -- defect 3 reintroduced in a new shape), and `ls` on a plain file
lists only itself, proving nothing about directory-shaped confinement.
Defect 3 is exactly why both are seeded rather than assumed to exist: an
absent path and a denied path are indistinguishable without a declared
signature, and seeding removes "absent" from the space of explanations
entirely.

**Convention every probe in this module follows, and that any later-added
probe must too**: the last element of a probe's `argv` is always its
resolved target path, substituted positionally as `"$0"` rather than
interpolated into the script text -- `probe.argv[-1]` is "the probe's
target" for any test inspecting this module's output (see
`tests/unit/test_battery_fs.py`'s SAFETY test, which asserts over this
convention across the whole probe tuple).
"""

from __future__ import annotations

from brig.core.grades import Axis
from brig.core.probes import ProbeShape
from brig.core.spec import Spec
from brig.probe.battery import Battery, Expectation, Probe


def fs_write_battery(spec: Spec, *, outside_writable: str) -> Battery:
    """A battery for the fs-write axis.

    Probes:
    - write_inside_workspace (CONTROL): must succeed
    - write_outside_workspace (DENIAL): must be denied
    - write_into_home_ssh (DENIAL): must be denied
    - write_into_git_hooks_carveout (DENIAL): must be denied

    Args:
        spec: A Spec with a non-empty write_allows. Raises ValueError if
            write_allows is empty (no workspace, no control).
        outside_writable: A HOST-resolved scratch root, genuinely writable
            by an unjailed process and owned/cleaned-up by the caller. Every
            write DENIAL probe's target lives under this root (module
            docstring, defect 2). Required keyword-only; omitting it raises
            TypeError, and an empty string raises ValueError naming the
            argument -- a battery must never default this to something that
            resolves to the real home.

    Returns:
        A Battery on Axis.FS_WRITE with four probes.
    """
    if not spec.fs.write_allows:
        raise ValueError(
            "fs_write_battery (axis fs_write): write_allows is empty, "
            "no workspace for the required CONTROL probe"
        )
    if not outside_writable:
        raise ValueError(
            "fs_write_battery (axis fs_write): outside_writable must not be empty "
            "(a battery must never default a write target -- doc-016 §7 deviation 4)"
        )

    workspace = spec.fs.write_allows[0]

    probes = (
        Probe(
            name="write_inside_workspace",
            shape=ProbeShape.CONTROL,
            axis=Axis.FS_WRITE,
            argv=(
                "/bin/sh",
                "-c",
                'printf brig-ok > "$0"/brig-probe-control && cat "$0"/brig-probe-control',
                workspace,
            ),
            expect=Expectation(token="brig-ok"),
        ),
        Probe(
            name="write_outside_workspace",
            shape=ProbeShape.DENIAL,
            axis=Axis.FS_WRITE,
            argv=(
                "/bin/sh",
                "-c",
                'printf x > "$0"/brig-probe-outside-canary',
                outside_writable,
            ),
            expect=Expectation(),
        ),
        Probe(
            name="write_into_home_ssh",
            shape=ProbeShape.DENIAL,
            axis=Axis.FS_WRITE,
            argv=(
                "/bin/sh",
                "-c",
                'printf x > "$0"/brig-probe-home-ssh-canary',
                outside_writable,
            ),
            expect=Expectation(),
        ),
        Probe(
            name="write_into_git_hooks_carveout",
            shape=ProbeShape.DENIAL,
            axis=Axis.FS_WRITE,
            argv=(
                "/bin/sh",
                "-c",
                'printf x > "$0"/.git/hooks/brig-probe-canary',
                workspace,
            ),
            expect=Expectation(),
        ),
    )

    return Battery(name="fs_write", axis=Axis.FS_WRITE, probes=probes)


def fs_read_battery(spec: Spec, *, credential_canary: str, ssh_directory_canary: str) -> Battery:
    """A battery for the fs-read axis.

    Probes:
    - read_a_workspace_file (CONTROL): must succeed
    - read_home_ssh_directory (DENIAL): must be denied
    - read_aws_credentials (DENIAL): must be denied

    Args:
        spec: A Spec with a non-empty write_allows. Raises ValueError if
            write_allows is empty (no workspace, no control).
        credential_canary: A HOST-resolved FILE path the caller has already
            SEEDED to exist and be readable before the battery runs.
            `read_aws_credentials` targets it with `cat` (module docstring,
            defect 3). Required keyword-only; omitting it raises TypeError,
            and an empty string raises ValueError naming the argument -- a
            battery must never assume a credential path exists rather than
            being told it does.
        ssh_directory_canary: A HOST-resolved DIRECTORY path the caller has
            already SEEDED to exist, be listable, and contain at least one
            entry. `read_home_ssh_directory` targets it with `ls` (module
            docstring -- a separate parameter from `credential_canary`
            because a single path read both ways collapses one of the two
            probes to a vacuous case). Required keyword-only; same
            TypeError/ValueError refusal as `credential_canary`.

    Returns:
        A Battery on Axis.FS_READ with three probes.
    """
    if not spec.fs.write_allows:
        raise ValueError(
            "fs_read_battery (axis fs_read): write_allows is empty, "
            "no workspace for the required CONTROL probe"
        )
    if not credential_canary:
        raise ValueError(
            "fs_read_battery (axis fs_read): credential_canary must not be empty "
            "(a battery must never assume a credential path exists -- doc-016 §7 "
            "deviation 4 defect 3)"
        )
    if not ssh_directory_canary:
        raise ValueError(
            "fs_read_battery (axis fs_read): ssh_directory_canary must not be empty "
            "(a battery must never assume a credential path exists -- doc-016 §7 "
            "deviation 4 defect 3)"
        )

    workspace = spec.fs.write_allows[0]

    probes = (
        Probe(
            name="read_a_workspace_file",
            shape=ProbeShape.CONTROL,
            axis=Axis.FS_READ,
            argv=(
                "/bin/sh",
                "-c",
                'printf brig-ok > "$0"/brig-probe-readable && cat "$0"/brig-probe-readable',
                workspace,
            ),
            expect=Expectation(token="brig-ok"),
        ),
        Probe(
            name="read_home_ssh_directory",
            shape=ProbeShape.DENIAL,
            axis=Axis.FS_READ,
            argv=("/bin/sh", "-c", 'ls "$0"', ssh_directory_canary),
            expect=Expectation(),
        ),
        Probe(
            name="read_aws_credentials",
            shape=ProbeShape.DENIAL,
            axis=Axis.FS_READ,
            argv=("/bin/sh", "-c", 'cat "$0"', credential_canary),
            expect=Expectation(),
        ),
    )

    return Battery(name="fs_read", axis=Axis.FS_READ, probes=probes)


__all__ = ("fs_read_battery", "fs_write_battery")

"""`bwrap`: the linux mechanism -- bubblewrap mount and network namespaces.

SPEC.md §6 roster row, verbatim:

    | `bwrap` | fs (allowlist-capable), network (netns) | linux | mount-order semantics; pairs with `connect_proxy` in-netns or `pasta` |

`compile` is a pure `spec -> argv` render, the same shape as `rlimits` and
`env_scrub`: no I/O, no clock, no randomness, no subprocess. Everything it
needs that only a filesystem can answer -- a path's realpath'd form, and
whether the path exists at all -- arrives on `CompileCtx`
(`resolved_paths`, decision-115; `path_exists`, decision-159), because
`run` is the layer permitted to look and `mech` is not. A path this render
needs and cannot find in either mapping is a REFUSAL naming the path, never
a fallback: a mount rule that silently does not hold is the exact failure
this library exists to refuse.

**Allowlist, and only allowlist.** SPEC.md §5: "Two read models, declared
not layered. Denylist (Seatbelt-native) and allowlist (container/bwrap/
nix-native) are different shapes. A mechanism declares which model(s) it
implements; compiling the other model through it is a refusal or an honest
downgrade in the report, never silent." This mechanism is the allowlist
half, exactly as seatbelt is the denylist half, and it REFUSES
`ReadModel.DENY_LIST` (`ReadModelUnsupported`) rather than emulating it.
The emulation was considered and rejected on the merits, not on effort: a
denylist under bwrap means binding the host root read-only and masking each
`read_denies` entry with a mount, and a mount cannot mask a path that is
not there -- so a `read_denies` entry naming a path the operator has not
created yet would compile to nothing, silently, in exactly the credential
directories that list exists for. Refusing is law 2's posture and leaves
the door open for a mechanism that can do it honestly.

**The mount order IS the policy, and it is documented here because bwrap
applies operations in the order they appear on its command line and a later
mount stacks over an earlier one.** One rule, no exceptions: LATER WINS,
and the stages are ordered so that "later" means "more specific and more
restrictive".

    1. `--unshare-all`                     namespaces: mount, pid, ipc, uts,
                                           cgroup, user (try), and NET --
                                           the network axis's whole
                                           enforcement (deny-all).
    2. `--proc /proc`, `--dev /dev`        the jail's OWN furniture: a proc
                                           for its own pid namespace and a
                                           minimal device set. First among
                                           the mounts, so every spec-derived
                                           mount below stacks ON TOP of it
                                           rather than being shadowed by it.
    3. `--ro-bind SRC DEST` per            the readable tree: an ALLOWLIST,
       `fs.read_allows`                    so what is not named here does not
                                           exist inside the jail at all.
    4. `--bind SRC DEST` per declared      the LISTEN channel's own directory
       channel's endpoint DIRECTORY        (see below), before the write
                                           roots: it is the one mount whose
                                           path policy did not choose, so it
                                           is the one that may CONTAIN them
                                           -- decision-163.
    5. `--bind SRC DEST` per               the writable roots, layered over
       `fs.write_allows`                   the two stages above.
    6. per `fs.write_denies`:              the carve-outs INSIDE the write
       `--ro-bind SRC DEST` (exists) or    roots -- deny-over-allow, which is
       `--tmpfs DEST --remount-ro DEST`    only true because this stage comes
       (does not exist)                    AFTER stage 5. SPEC.md §5's
                                           "submounts", literally.
    7. per `fs.read_denies` inside a       the READ carve-outs (decision-164),
       mounted root and existing:          last, so nothing stacks over them.
       `--ro-bind /dev/null DEST` (file)   A file reads EACCES (bwrap mounts
       or `--perms 0000 --tmpfs DEST       nodev); a directory is an empty,
       --remount-ro DEST` (directory)      mode-0000, read-only tmpfs.
    8. `--` then the workload's argv.

**Read carve-outs inside the allowlist (decision-164).** An allowlist
denies by absence, but a secret can sit INSIDE an allowed root: a
credential file at the top of a workspace the jail may write. So
`read_denies` is active under ALLOW_LIST too, and each entry is one of
three cases, decided against the resolved mounted roots (read allows, the
channel directories, write allows): OUTSIDE every root it is inert -- the
path is already absent from the jail, which is the allowlist's own
enforcement; INSIDE a root and existing it is masked at stage 7; INSIDE a
root and ABSENT it is not mounted at all, and `fs_read` grades
`best_effort` with the path named. That last case is the objection that
rejected the denylist emulation above, met honestly rather than silently:
a mask needs a mount point, and a mount point at an absent path is a
directory bwrap CREATES ON THE HOST (see `write_denies` below) -- a
`local.env/` directory where the person's next `local.env` file should go.
So the path is left alone and the grade says a file created there after
launch is readable.

**Stage 4 moved ahead of the write roots on 2026-09-08 (decision-163), and
it was a real hole.** A jail directory that HOLDS the workspace is the
ordinary arrangement, and binding it read-write last stacked it over every
carve-out inside it: `write_denies` compiled, mounted, and then silently
unmade by the next mount, so the jail could write the very path it was
denied. It was found the first time this library's e2e tier ran on
linux. Nothing protects the endpoint from the carve-outs that now come
after it EXCEPT the refusal below -- an endpoint under a `write_denies`
subpath is `ChannelInsideWriteDeny`, never ordered around -- which is why
that refusal is load-bearing rather than defensive.

**Why `write_denies` has two forms, and why the choice needs `path_exists`.**
A bind mount needs a source that exists; a tmpfs mount needs a mount point
it may create. Neither form covers both cases, and getting it wrong is not
cosmetic:

- `--ro-bind` alone fails the LAUNCH for a denied path that is not there --
  and `.envrc`, `.git/hooks`, `CLAUDE.md` are exactly the paths a workspace
  usually does NOT have yet.
- `--ro-bind-try` alone (bwrap's own skip-if-missing variant) SILENTLY
  SKIPS them, which leaves the jail free to CREATE the file it was denied
  -- the self-escalation threat `write_denies` exists for (SPEC.md §5),
  reopened by a flag that reads like a convenience.
- `--tmpfs` alone fails for a denied path that exists as a FILE (you cannot
  mount a filesystem onto a regular file), which is most of that same list
  once a workspace is a few days old.

So the render branches on `ctx.path_exists`, and BOTH branches enforce: an
existing path is bind-mounted over itself read-only (its contents stay
readable, which is what a *write* deny asks for, and it cannot be unlinked
or renamed because it is a mount point), and an absent path becomes an
empty read-only tmpfs (nothing can be created at it, and it cannot be
rmdir'd for the same reason). Two consequences are named rather than
hidden: an absent denied path materialises as an empty DIRECTORY inside the
jail, and bwrap creates the mount point to put it there -- ON THE HOST, not
only inside the jail, because the mount point is made inside the write
root's bind of the host directory, missing parents included (measured
2026-09-28, decision-164: a jail denied `.envrc` leaves an empty `.envrc/`
in the host workspace, and one denied `.git/hooks` in a directory that is
not a repository leaves `.git/hooks/`). They outlive the jail; removing
them is the embedder's, after teardown, and never while the jail lives --
a mount point removed on the host is detached inside the jail, which would
unmake the carve-out. And the
compile-to-launch window is a REFUSAL on both sides rather than a hole --
a denied path created as a file in that window makes the `--tmpfs` fail,
one deleted in that window makes the `--ro-bind` fail, and a failed mount
is a jail that does not start.

**The LISTEN channel costs a writable directory, and seatbelt's does not.**
SPEC.md §10.1 makes each mechanism compile the crossing; seatbelt can name
the socket's exact path (`(allow file-write* (literal ...))`) because SBPL
matches paths, but a bind mount needs an object that already exists and the
socket does not exist until the jail binds it. So the smallest thing bwrap
can grant is the endpoint's DIRECTORY, bound writable. That is a real,
mechanism-shaped fidelity difference against seatbelt, it is named in the
`fs_write` grade's own detail (not only here), and it is why a channel
whose endpoint falls under a `write_denies` subpath is REFUSED
(`ChannelInsideWriteDeny`) instead of being ordered around: since
decision-163 the carve-outs are mounted AFTER the channel directory, so a
socket under one would be read-only, and a refusal is the honest answer.

**Denial signatures, and the one an allowlist cannot have.** Two patterns,
both specific, neither generic: `Read-only file system` (EROFS -- SPEC.md
§6's own quoted example for this mechanism) and `Network is unreachable`
(ENETUNREACH, what a connect finds in a network namespace holding nothing
but loopback). There is deliberately no `fs_read` signature: an allowlist
denies by ABSENCE, so a read of an unmounted path fails with "No such file
or directory", which is precisely the generic text a signature may not
match (SPEC.md §6; the unit tier pins the not-match direction). Per SPEC.md
§12 that is a routing fact rather than a gap -- `fs_read` here is proved by
an `ABSENCE` probe plus the battery's positive control, the same shape
`env_scrub` already has.

**Flags deliberately NOT emitted, each for a reason that would otherwise
have to be rediscovered:**

- `--new-session`. It calls `setsid()`, which would put the workload in a
  process group of its own -- outside the one `Handle.kill`'s ladder and
  `Handle.interrupt` signal (SPEC.md §9, law 7: control must not require
  cooperation). Its own benefit (no TIOCSTI on an inherited terminal) buys
  nothing here: `IoPolicy` gives the workload `/dev/null` for stdin and no
  controlling terminal at all.
- `--die-with-parent`. A second, mechanism-owned control path that nothing
  in the report grades and no teardown rung accounts for. Control is the
  handle's, and a jail that also dies for its own reasons makes
  `KillReport`'s verification rung answer a question it was not asked.
- `--tmpfs /tmp`. SPEC.md §5: temp space is per-jail and INSIDE
  `write_allows`. Handing the jail writable space no `write_allows` entry
  named would make the `fs_write` claim false by exactly one directory.

**`events` is `None`, and that is a decision.** What this mechanism knows
the instant it compiles is its own argv -- which `Handle` already carries
verbatim, having launched it. A sensor payload restating it would be the
copy decision-152 deleted the event stream for. Nothing about how the
workload EXITS is bwrap's to classify either: a mount denial is an EROFS
inside the workload, not a status on the way out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from brig.core import Axis, Grade, Graded, ReadModel, Spec
from brig.mech.contract import ArgvTransformer, CompileCtx, Step

#: Absolute, never the bare name `bwrap` (decision-026 rule 1's family, the
#: same reason seatbelt names `/usr/bin/sandbox-exec` in full): a bare name
#: is resolved through whatever `PATH` the launching process happens to
#: carry, which is authority no `Spec` granted. Overridable per instance --
#: see `Bwrap.__init__` -- because unlike `sandbox-exec` this binary is not
#: shipped by the OS and a distribution may put it elsewhere.
DEFAULT_BWRAP_PATH: Final[str] = "/usr/bin/bwrap"

_LINUX: Final[str] = "linux"

#: SPEC.md §6's own quoted denial signature for this mechanism ("bwrap
#: 'Read-only file system'"), plus the netns one. Matched against the probe
#: engine's normalized denial string (decision-068), never raw stdout.
_EROFS_SIGNATURE: Final[re.Pattern[str]] = re.compile(r"Read-only file system")
_ENETUNREACH_SIGNATURE: Final[re.Pattern[str]] = re.compile(r"Network is unreachable")

#: Must contain the literal token "allowlist": reads are default-DENY here.
#: The jail's root is bwrap's own tmpfs and only what is mounted into it
#: exists at all, which is the opposite shape from seatbelt's denylist.
_FS_READ_DETAIL: Final[str] = (
    "bwrap enforces fs_read as an allowlist: the jail's root is a fresh "
    "namespace containing only what this mechanism mounts into it -- "
    "spec.fs.read_allows read-only, the write roots, the declared channel's "
    "own directory, and the jail's own /proc and /dev furniture. A path "
    "outside that set is not readable because it does not exist inside the "
    "jail, so it denies by ABSENCE (ENOENT) and not by a denial message; "
    "this axis is proved by an ABSENCE probe plus the battery's positive "
    "control (SPEC.md sec 12), never by a signature match. A read_denies "
    "entry inside that set that exists is masked after every other mount: a "
    "file by the null device (EACCES), a directory by an empty mode-0000 "
    "read-only tmpfs."
)

#: Must contain the literal token "write_denies": the carve-outs are
#: submounts INSIDE the granted write roots, and the detail says how each
#: form is chosen and what the channel directory costs.
_FS_WRITE_DETAIL: Final[str] = (
    "bwrap enforces fs_write by mounting everything read-only except "
    "spec.fs.write_allows, which are bind-mounted read-write; write_denies "
    "carve-outs are compiled as submounts INSIDE those write roots, after "
    "them on bwrap's command line, so deny-over-allow holds by mount order. "
    "A denied path that exists is bind-mounted over itself read-only (its "
    "contents stay readable, which is what a write deny asks) and one that "
    "does not exist becomes an empty read-only tmpfs, so the deny holds "
    "either way and an absent denied path appears inside the jail as an "
    "empty directory. One path is writable that no write_allows entry "
    "named: the declared LISTEN channel's own endpoint DIRECTORY, bound "
    "read-write because a jail cannot bind a socket into a directory it "
    "cannot write, and a bind mount cannot name a socket that does not "
    "exist yet the way seatbelt's path rule can."
)

#: Must contain the literal token "unshare": the whole network claim is the
#: namespace, and it is deny-ALL -- there is no filtered form here.
_NETWORK_DETAIL: Final[str] = (
    "bwrap denies all network by unshare: the workload runs in its own "
    "network namespace holding nothing but loopback, so there is no route "
    "off the host and no host interface to bind. This is deny-all and "
    "nothing else -- a spec granting allowed_domains is refused rather than "
    "run under a claim this mechanism cannot make (per-domain egress is "
    "connect_proxy's, and reaching it from inside an unshared netns needs "
    "pasta or slirp4netns, SPEC.md sec 6's roster)."
)

#: What a masked FILE is bound to (stage 7, decision-164): the host's null
#: device. bwrap binds with `nodev`, so opening it inside the jail fails with
#: EACCES -- a read of the masked path is refused, not answered with nothing.
_NULL: Final[str] = "/dev/null"

_AXES: Final[frozenset[Axis]] = frozenset({Axis.FS_READ, Axis.FS_WRITE, Axis.NETWORK})


class PlatformUnsupported(ValueError):
    """Raised when `Bwrap.compile` is asked to compile for
    `ctx.platform != 'linux'`: mount and network namespaces, and the
    `bwrap` binary itself, are linux-only. Names the offending platform."""


class ReadModelUnsupported(ValueError):
    """Raised when `spec.fs.read_model` is `ReadModel.DENY_LIST`: bwrap is
    the ALLOWLIST half of SPEC.md §5's two declared read models, and
    compiling the other one through it would mean masking each denied path
    with a mount -- which cannot mask a path that does not exist yet. Names
    the model it was asked to compile."""


class NetworkUnsupported(ValueError):
    """Raised when `spec.network.allowed_domains` is non-empty: an unshared
    network namespace is deny-all, and bwrap has no way to let one domain
    through. Per-domain egress is `connect_proxy`'s, and it needs a
    mechanism that puts a route back into the namespace (`pasta`,
    `slirp4netns`) before the pairing means anything. Names the domain(s)."""


class UnresolvedPath(ValueError):
    """Raised when a path this render needs is missing from
    `ctx.resolved_paths` -- a `read_allows`/`write_allows`/`write_denies`
    entry, or a LISTEN `Channel.endpoint`. Names the path; this render
    never falls back to the lexical form (SPEC.md §6, decision-115)."""


class UnknownPathExistence(ValueError):
    """Raised when a `write_denies` entry is missing from
    `ctx.path_exists`. The render cannot pick between the bind form and the
    tmpfs form without knowing, and guessing is how a carve-out silently
    stops holding -- so it refuses, naming the path (SPEC.md §6,
    decision-159)."""


class UnknownPathKind(ValueError):
    """Raised when a `read_denies` entry stage 7 must mask is missing from
    `ctx.path_is_dir`. A file is masked by binding `/dev/null` over it and a
    directory by an empty tmpfs, a bind cannot cover one kind with the
    other, and guessing is a launch that fails -- so it refuses, naming the
    path (decision-164)."""


class ChannelInsideWriteDeny(ValueError):
    """Raised when a LISTEN `Channel`'s resolved endpoint falls under a
    resolved `write_denies` subpath. The channel's own directory is bound
    read-write AFTER the carve-outs, so compiling the pair would silently
    reverse the deny for that subtree; and compiling it the other way round
    would give the jail a socket path it can never create. Names both the
    resolved endpoint and the `write_denies` subpath it falls under -- the
    same refusal, for the same reason, that
    `brig.mech.seatbelt.profile` makes on its own side."""


def _resolve(path: str, resolved: Mapping[str, str]) -> str:
    """`path`'s realpath'd form, or a refusal naming `path`. Never the
    lexical fallback (SPEC.md §6, law 2's refusal-not-downgrade posture)."""
    try:
        return resolved[path]
    except KeyError:
        raise UnresolvedPath(f"no resolved form for path {path!r} in ctx.resolved_paths") from None


def _exists(path: str, path_exists: Mapping[str, bool]) -> bool:
    """Whether `path` existed when `run` built the context, or a refusal
    naming `path`. Never a default -- see `UnknownPathExistence`."""
    try:
        return path_exists[path]
    except KeyError:
        raise UnknownPathExistence(
            f"no existence answer for path {path!r} in ctx.path_exists; bwrap "
            "cannot choose between its bind and tmpfs forms without one"
        ) from None


def _is_dir(path: str, path_is_dir: Mapping[str, bool] | None) -> bool:
    """Whether `path` was a directory when `run` built the context, or a
    refusal naming `path`. Never a default -- see `UnknownPathKind`."""
    try:
        return (path_is_dir or {})[path]
    except KeyError:
        raise UnknownPathKind(
            f"no directory answer for path {path!r} in ctx.path_is_dir; bwrap "
            "masks a file and a directory differently and cannot mask one without it"
        ) from None


def _parent(path: str) -> str:
    """The directory component of an absolute POSIX path.

    Plain string work rather than `os.path.dirname`: this module imports no
    `os` (`tests/unit/test_mech_events_purity.py` pins its import set), and
    bwrap is linux-only, so POSIX separators are the only ones that can
    reach here. A path with no separator at all, or one whose parent is the
    root, yields `"/"`."""
    head = path.rsplit("/", 1)[0]
    return head or "/"


def _is_subpath(candidate: str, root: str) -> bool:
    """True if the already-resolved `candidate` is `root` or lies under it.
    String containment on resolved forms -- no filesystem read on either
    side (same helper, same reason, as seatbelt's own)."""
    if root == "/":
        return True
    return candidate == root or candidate.startswith(root + "/")


def render_bwrap_prefix(
    spec: Spec,
    *,
    resolved: Mapping[str, str],
    path_exists: Mapping[str, bool],
    path_is_dir: Mapping[str, bool] | None = None,
    bwrap_path: str = DEFAULT_BWRAP_PATH,
) -> tuple[str, ...]:
    """Render `spec` into the bwrap argv PREFIX. Pure: no I/O, no clock.

    The result ends in `"--"`, so `prefix + argv` is the whole command line
    and `Step.wrap` stays a PURE ARGV PREFIX -- which `handle.exec`
    (SPEC.md §9, `run.launcher._derive_wrap_prefix`) requires in order to
    place a sibling inside the same confinement, and which every probe in
    this library depends on because probes run through `exec`.

    Each mount names its SOURCE by the realpath'd form and its DESTINATION
    by the path the `Spec` itself carries. That split is deliberate and
    load-bearing in both directions: mounting the resolved source is what
    makes a symlinked path (`/bin` -> `usr/bin`, `/tmp` -> `/private/tmp`)
    mount the tree it actually points at, and mounting it AT the spec's own
    path is what makes the workload's own view match the policy that was
    written -- a jail where `/bin/sh` is missing because `/bin` was
    normalised away is a jail that cannot start.

    Args:
        spec: The full `Spec` to render bwrap's slice of. Must be
              `ReadModel.ALLOW_LIST` and must not grant `allowed_domains`.
        resolved: Every `Spec` path this render needs, mapped to its
              realpath'd form, keyed exactly as the `Spec` carries it.
        path_exists: Every `write_denies` entry, and every `read_denies`
              entry inside a mounted root, mapped to whether it existed
              when the context was built.
        path_is_dir: Every `read_denies` entry stage 7 masks, mapped to
              whether it is a directory (decision-164).
        bwrap_path: Absolute path to the `bwrap` binary.

    Raises:
        ReadModelUnsupported, NetworkUnsupported, UnresolvedPath,
        UnknownPathExistence, UnknownPathKind, ChannelInsideWriteDeny -- each
        naming its own subject; see the classes' own docstrings.
    """
    if spec.fs.read_model is not ReadModel.ALLOW_LIST:
        raise ReadModelUnsupported(
            f"bwrap only compiles ReadModel.ALLOW_LIST specs, got {spec.fs.read_model!r}"
        )
    if spec.network.allowed_domains:
        raise NetworkUnsupported(
            "bwrap unshares the network namespace, which is deny-all: it cannot "
            "let a domain through. Got "
            f"spec.network.allowed_domains={spec.network.allowed_domains!r}"
        )

    # Stage 1 and 2: the namespaces, then the jail's own furniture.
    args: list[str] = [bwrap_path, "--unshare-all", "--proc", "/proc", "--dev", "/dev"]

    # Stage 3: the readable tree (allowlist).
    for path in spec.fs.read_allows:
        args += ["--ro-bind", _resolve(path, resolved), path]

    resolved_write_denies = [_resolve(path, resolved) for path in spec.fs.write_denies]

    # Stage 4: the declared LISTEN channel's own directory, read-write, and
    # BEFORE the write roots -- decision-163. `LISTEN` is the only
    # `ChannelKind` there is (decision-153), so "declares a LISTEN channel"
    # is "declares a channel". `spec.channels` arrives sorted by name, so
    # this order needs no sort of its own.
    #
    # This directory is the one mount whose path the Spec does not choose
    # for policy reasons, so it is the one that can turn out to CONTAIN a
    # write root or a carve-out (a jail dir holding the workspace is the
    # ordinary shape). Emitted last, as it was until decision-163, an
    # ancestor bind stacked over the carve-outs and silently unmade them.
    # Emitted here it can only be stacked ON, which is the direction "later
    # means more specific" asks for. What keeps the endpoint itself safe
    # from the later carve-outs is not order but the refusal below: an
    # endpoint under a `write_denies` subpath is refused outright.
    seen_dirs: set[str] = set()
    for channel in spec.channels:
        resolved_endpoint = _resolve(channel.endpoint, resolved)
        for deny_root in resolved_write_denies:
            if _is_subpath(resolved_endpoint, deny_root):
                raise ChannelInsideWriteDeny(
                    f"LISTEN channel {channel.name!r} resolved endpoint "
                    f"{resolved_endpoint!r} falls under write_denies subpath "
                    f"{deny_root!r}"
                )
        dest_dir = _parent(channel.endpoint)
        if dest_dir in seen_dirs:
            continue
        seen_dirs.add(dest_dir)
        args += ["--bind", _parent(resolved_endpoint), dest_dir]

    # Stage 5: the writable roots, layered over stages 3 and 4.
    for path in spec.fs.write_allows:
        args += ["--bind", _resolve(path, resolved), path]

    # Stage 6: the carve-outs, AFTER stage 5 -- that order IS the
    # deny-over-allow precedence SPEC.md §5 requires, and it is the one
    # line of this render a mutation check moves (put this loop above the
    # write_allows loop and both the ordering test and the golden go red).
    for path, resolved_deny in zip(spec.fs.write_denies, resolved_write_denies, strict=True):
        if _exists(path, path_exists):
            args += ["--ro-bind", resolved_deny, path]
        else:
            args += ["--tmpfs", path, "--remount-ro", path]

    # Stage 7: the read carve-outs that exist inside a mounted root, last, so
    # no later mount can stack over them (decision-164). The absent ones are
    # `unmasked_read_denies`' business: not mounted, and graded.
    for path in _masked_read_denies(spec, resolved=resolved, path_exists=path_exists):
        if _is_dir(path, path_is_dir):
            args += ["--perms", "0000", "--tmpfs", path, "--remount-ro", path]
        else:
            args += ["--ro-bind", _NULL, path]

    args.append("--")
    return tuple(args)


def _mounted_roots(spec: Spec, resolved: Mapping[str, str]) -> tuple[str, ...]:
    """Every tree this render mounts from the host, resolved: the read allows,
    the channel directories and the write roots."""
    return (
        *(_resolve(path, resolved) for path in spec.fs.read_allows),
        *(_parent(_resolve(channel.endpoint, resolved)) for channel in spec.channels),
        *(_resolve(path, resolved) for path in spec.fs.write_allows),
    )


def _inside_the_jail(spec: Spec, resolved: Mapping[str, str]) -> tuple[str, ...]:
    """The `read_denies` entries a mounted root reaches: at or under one, or an
    ancestor of one. The rest are absent from the jail already, which is the
    allowlist's own enforcement, and need no mount."""
    roots = _mounted_roots(spec, resolved)
    return tuple(
        path
        for path in spec.fs.read_denies
        if any(
            _is_subpath(_resolve(path, resolved), root)
            or _is_subpath(root, _resolve(path, resolved))
            for root in roots
        )
    )


def _masked_read_denies(
    spec: Spec, *, resolved: Mapping[str, str], path_exists: Mapping[str, bool]
) -> tuple[str, ...]:
    """The read carve-outs stage 7 masks: inside the jail, and existing."""
    return tuple(path for path in _inside_the_jail(spec, resolved) if _exists(path, path_exists))


def unmasked_read_denies(
    spec: Spec, *, resolved: Mapping[str, str], path_exists: Mapping[str, bool]
) -> tuple[str, ...]:
    """The read carve-outs inside a mounted root that did NOT exist when the
    context was built, so nothing masks them: a file the host creates there
    after launch is readable in the jail. Pure; `Bwrap.compile` grades
    `fs_read` `best_effort` naming each one (decision-164)."""
    return tuple(
        path for path in _inside_the_jail(spec, resolved) if not _exists(path, path_exists)
    )


def _fs_read_graded(unmasked: tuple[str, ...]) -> Graded:
    """`enforced` when every read carve-out inside the jail is masked, else
    `best_effort` naming the ones that are not."""
    if not unmasked:
        return Graded(Grade.ENFORCED, _FS_READ_DETAIL)
    return Graded(
        Grade.BEST_EFFORT,
        f"{_FS_READ_DETAIL} Not masked, because they did not exist at launch and a "
        "mask would need a mount point bwrap creates on the host: "
        f"{', '.join(unmasked)}. A file created at one of these after launch is "
        "readable inside the jail.",
    )


class Bwrap:
    """SPEC.md §6's `bwrap` mechanism: linux namespaces via bubblewrap.

    Args:
        bwrap_path: Absolute path to the `bwrap` binary, defaulting to
            `DEFAULT_BWRAP_PATH`. A constructor argument rather than a
            lookup because resolving a name through `PATH` is I/O, and
            `compile` may no more perform I/O than it may read a clock --
            the same posture `ConnectProxy(python=...)` takes for the
            interpreter it spawns its helper with.
    """

    name = "bwrap"
    axes: frozenset[Axis] = _AXES

    def __init__(self, bwrap_path: str = DEFAULT_BWRAP_PATH) -> None:
        self._bwrap_path = bwrap_path

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        """Refuses on a non-linux platform (`PlatformUnsupported`) and then
        propagates `render_bwrap_prefix`'s own refusals UNCHANGED -- never
        catching, re-raising or swallowing one. `fs_read` is `enforced`
        unless a read carve-out inside the jail could not be masked
        (`unmasked_read_denies`), and then `best_effort`, naming it."""
        if ctx.platform != _LINUX:
            raise PlatformUnsupported(
                f"bwrap only compiles for ctx.platform == {_LINUX!r}, got {ctx.platform!r}"
            )

        prefix = render_bwrap_prefix(
            spec,
            resolved=ctx.resolved_paths,
            path_exists=ctx.path_exists,
            path_is_dir=ctx.path_is_dir,
            bwrap_path=self._bwrap_path,
        )
        unmasked = unmasked_read_denies(
            spec, resolved=ctx.resolved_paths, path_exists=ctx.path_exists
        )

        def wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
            return (*prefix, *argv)

        wrap_transformer: ArgvTransformer = wrap

        return Step(
            wrap=wrap_transformer,
            env={},
            staged=(),
            helpers=(),
            requires=frozenset(),
            grades={
                Axis.FS_READ: _fs_read_graded(unmasked),
                Axis.FS_WRITE: Graded(Grade.ENFORCED, _FS_WRITE_DETAIL),
                Axis.NETWORK: Graded(Grade.ENFORCED, _NETWORK_DETAIL),
            },
            denial_signatures=(_EROFS_SIGNATURE, _ENETUNREACH_SIGNATURE),
        )


#: The mechanism instance embedders and `Stack` compose against -- same
#: posture as `brig.mech.seatbelt`'s own module-level `seatbelt` instance.
bwrap: Bwrap = Bwrap()

__all__ = (
    "DEFAULT_BWRAP_PATH",
    "Bwrap",
    "ChannelInsideWriteDeny",
    "NetworkUnsupported",
    "PlatformUnsupported",
    "ReadModelUnsupported",
    "UnknownPathExistence",
    "UnknownPathKind",
    "UnresolvedPath",
    "bwrap",
    "render_bwrap_prefix",
    "unmasked_read_denies",
)

"""`oci`: a container as the jail -- the flags of `docker create`, compiled from a `Spec`.

SPEC.md §6 roster row, as built (decision-202):

    | `oci` | fs (allowlist, the image's root named), network (none), env, limits (cpu) | docker | ... |

decision-0001's migration step 5, first half. `compile` is a pure `spec -> flags` render, the shape
`bwrap`'s is: no I/O, no clock, no randomness, no subprocess, and no `os` (the env file is the
runtime's to write, `brig.runtime.oci`). What only a filesystem can answer arrives on `CompileCtx`
(`resolved_paths`, `path_exists`, `path_is_dir`, `euid`) and a path it needs and cannot find is a
refusal naming it, never a guess. Its `Step` has no wrap (nothing wraps a host argv: a container's
argv is its own), no helper, no staged file and no sensor, and carries `Step.container`, the
`ContainerPlan` the runtime makes the container from.

**It compiles `env_scrub`'s and `rlimits`' effect itself, so it claims their axes and the matrix
refuses them beside it** (SPEC.md §7): an `env_scrub` wrap is a shell around a host argv, and the
`rlimits` trampoline needs brig in the image. Both are `AxisClaimConflict` first (rule 1), and
refused pairs in the matrix too.

The flags, in order (`render_flags`):

    1. `--user <euid> --network none --cap-drop ALL --security-opt no-new-privileges
       --read-only`: the embedder's uid, so files the workload writes into a project are not owned
       by root (an unknown user is a refusal, never root); the loopback and nothing else; no
       capability and no privilege gained by an exec (decision-177's analogue: root in the container
       holds none either); and a read-only root filesystem (decision-166's analogue: a write outside
       every write root is denied, not answered in the image's writable layer). `--init` is not
       here: it belongs to the exec variant (decision-203, below).
    2. `--env-file <jail_dir>/oci.env`: the environment is a file (law 9), written by the runtime
       with mode 0600 and removed once `docker create` returns. Never `-e K=V`, which is argv.
    3. `--ulimit cpu=N:N+1` for `limits.cpu_seconds` N (decision-161: a soft limit equal to the hard
       one is delivered as `SIGKILL`, never `SIGXCPU`).
    4. The mounts, which Docker orders by the depth of their destination, so a carve-out is mounted
       over its write root whatever the order of the flags: `read_allows` as read-only binds,
       `write_allows` as binds, the runtime's channel directory `<jail_dir>/chan` bound read-write
       at its own resolved path (decision-203: the rendezvous, the exec files and every channel's
       socket are in it), the pins (decision-168: each existing directory between a write root
       and a carve-out, bound over itself, so it is a mount point and cannot be renamed away),
       `write_denies` a writable tree reaches as read-only binds over themselves (existing) or empty
       read-only tmpfses (absent), and `read_denies` inside a mounted root as masks (decision-164:
       a file by `/dev/null`, a directory by a mode-0001 read-only tmpfs: Docker reads mode 0 as
       unset, and an unset mode is 1777, which lists).

**Two variants, one per agent (decision-203, SPEC.md §8).** `Oci(image, interpreter="/usr/bin/python3")`
names the interpreter to try brig's supervisor under inside the image; `None` names none. The plan
renders both variants (`ContainerPlan.create_flags`, `create_command`): the supervisor's is these flags
plus the supervisor's program bound read-only from `<jail_dir>/oci-supervisor.py`, no `--init` (the
supervisor is PID 1 and reaps) and the command that runs it with the path of the control socket
(`<chan>/agent.sock`); the exec variant's is `--init` and the idle command. Which one a container is
made as is the runtime's to find out (`brig.runtime.oci`): this is a pure render of both.

**Refusals** (law 2), each naming its subject: a platform other than linux (Docker Desktop's mounts
and uid mapping are not measured), a denylist `Spec` (`bwrap` refuses it for the reason SPEC.md §6
gives, and a container has no host paths to deny but the ones mounted), `allowed_domains` (per-domain
egress is a sidecar proxy, decision-0001, not built), `EnvPolicy.PASS` (the host's whole environment,
in a container's configuration, for an image not built for it), an unknown `euid`, a path `--mount`
cannot carry, an env name or value an env file cannot carry, a carve-out above a mounted root (Docker
mounts the shallower path first, so it could never be laid over the root: a deny that silently did not
hold), and a write root at or above the jail directory or at or under its `procs/` (the records are
kill authority, decision-173's promise, which bwrap keeps by sealing the directory; sealing is not
built here).

**Grades** (SPEC.md §6), as far as the flags can deliver them: `network` `enforced`; `fs_write`
`enforced` against the host, naming what stays writable and never reaches it; `fs_read` `best_effort`,
**the gap being the image**, whose files are readable whatever `read_allows` says; `env` `enforced`
scoped to the host's environment; `limits` `best_effort` (cpu only) when `cpu_seconds` is set, and
unclaimed when it is not (decision-092). `events` is `None`: what this mechanism knows at compile
time is its flags, which the runtime's record carries (decision-152).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from brig.core import Axis, EnvMode, Grade, Graded, ReadModel, Spec
from brig.core.runtime import (
    AGENT_SOCKET_NAME,
    PROCS_DIRNAME,
    ContainerPlan,
    EnvNotRepresentable,
    RuntimeKind,
    env_refusal,
)
from brig.mech.bwrap import DEFAULT_INTERPRETER, pins
from brig.mech.contract import ArgvTransformer, CompileCtx, Step

_LINUX: Final[str] = "linux"

#: The env file's name in the jail directory (decision-202): `--env-file <jail_dir>/oci.env`.
ENV_FILE_NAME: Final[str] = "oci.env"

#: The exec variant's process (decision-203): idle, under `--init`, for `docker exec` to start
#: the jail's processes beside.
IDLE_COMMAND: Final[tuple[str, ...]] = ("sleep", "infinity")

#: The supervisor's program on the host, in the jail directory (decision-203): the runtime writes
#: it from `SUPERVISOR_SOURCE` and Docker binds it read-only at `SUPERVISOR_SOURCE_PATH`.
SUPERVISOR_SOURCE_FILE: Final[str] = "oci-supervisor.py"

_AXES: Final[frozenset[Axis]] = frozenset(
    {Axis.FS_READ, Axis.FS_WRITE, Axis.NETWORK, Axis.ENV, Axis.LIMITS}
)

#: What a `--mount` value cannot carry: it is CSV, so a comma or a quote would add a key or end a
#: field, and a line break or a NUL is no path.
_UNMOUNTABLE: Final[str] = ',"\n\r\0'

_EROFS_SIGNATURE: Final[re.Pattern[str]] = re.compile(r"Read-only file system")
_ENETUNREACH_SIGNATURE: Final[re.Pattern[str]] = re.compile(r"Network is unreachable")

#: Must contain the literal token "allowlist". The gap is the image, named.
_FS_READ_DETAIL: Final[str] = (
    "oci enforces fs_read as an allowlist of the HOST's paths: nothing of the host is in the "
    "container but the spec.fs.read_allows and write_allows it mounts, so a host path outside "
    "them is not readable because it does not exist there. The gap, which is why this is not "
    "enforced: the container is made of its IMAGE, whose files are readable whatever read_allows "
    "says (they are the embedder's chosen furniture, not host data), and read_allows are binds of "
    "the host's paths over the image's. A read_denies entry inside a mounted root that exists is "
    "masked: a file by the null device (it reads as empty, and a write to it is discarded), a "
    "directory by an empty read-only tmpfs of mode 0001, which lists and reads as EACCES. One "
    "outside every mounted root is inert, and an image file at it is not masked."
)

#: Must contain the literal token "write_denies".
_FS_WRITE_DETAIL: Final[str] = (
    "oci enforces fs_write against the host: the container's root is read-only (--read-only), "
    "spec.fs.write_allows and the runtime's own channel directory <jail_dir>/chan (where the "
    "supervisor's control socket and each start's socket are made) are the only host paths bound "
    "read-write, no write root may reach the rest of the jail directory, and write_denies carve-outs "
    "are read-only submounts inside those roots (a denied path that exists is bound over itself "
    "read-only, one that does not exist becomes an empty read-only tmpfs, and the directories "
    "between a write root and a carve-out are pinned so they cannot be renamed away). Root in "
    "the container holds no capability and gains no privilege by an exec, so it cannot remount "
    "a read-only bind. What stays writable never reaches the host: /dev (a tmpfs of the "
    "container's), /dev/shm, /dev/mqueue and the tmpfs Docker lays over a few /proc files. An "
    "absent denied path appears as an empty directory, and its mount point is made inside the "
    "write root's bind of the host directory, so an empty directory is left ON THE HOST and "
    "outlives the container (removing it is the embedder's, after destroy, never while the "
    "container lives). Every carve-out is a mount on a host directory entry, so enforced is "
    "against the workload, not the host: a file the host renames over a denied path is writable "
    "inside until a new container starts."
)

#: Must contain the literal token "none": the whole network claim is the flag.
_NETWORK_DETAIL: Final[str] = (
    "oci denies all network with --network none: the container has its own network namespace "
    "holding nothing but loopback, so there is no route off the host. This is deny-all and "
    "nothing else -- a spec granting allowed_domains is refused rather than run under a claim "
    "this mechanism cannot make (per-domain egress is a sidecar proxy on an --internal network, "
    "decision-0001, not built)."
)

_ENV_DETAIL: Final[str] = (
    "enforced AGAINST THE HOST'S ENVIRONMENT: nothing of the creating process's environment "
    "reaches the container but the names spec.env.allow_names forwards and the spec.env.set "
    "pairs, which travel in an env file (mode 0600, removed once docker create has returned), "
    "never in argv (law 9). It is not the environment of the process: the image's own ENV "
    "(PATH, and whatever it sets) and the HOSTNAME and HOME the daemon adds are in it. The "
    "values are in the container's configuration, so anyone who can talk to the daemon reads "
    "them with docker inspect."
)

#: Same form as `rlimits`' detail: the `uncovered:` marker, then the comma-joined fields.
_LIMITS_DETAIL: Final[str] = (
    "oci enforces the limits axis for cpu only (--ulimit cpu, RLIMIT_CPU with a second of "
    "headroom so SIGXCPU is delivered); uncovered: memory, tasks, wall, output"
)


class PlatformUnsupported(ValueError):
    """Raised when `Oci.compile` is asked to compile for `ctx.platform != 'linux'`: Docker
    Desktop's bind mounts and uid mapping are not measured, and a mechanism claims what it can
    deliver on the platform it compiled for. Names the platform."""


class ReadModelUnsupported(ValueError):
    """Raised when `spec.fs.read_model` is `ReadModel.DENY_LIST`: a container is an allowlist
    (the host's paths it mounts and nothing else), as `bwrap` is. Names the model."""


class NetworkUnsupported(ValueError):
    """Raised when `spec.network.allowed_domains` is non-empty: `--network none` is deny-all,
    and per-domain egress is a sidecar proxy that is not built. Names the domain(s)."""


class JailDirReachable(ValueError):
    """Raised when a `write_allows` root is at or above the jail directory, or at or under its
    `procs/`: the jail's records are kill authority, so no write root may reach them
    (decision-173), and bwrap keeps that by sealing the directory under the root. A container does
    not seal it (decision-203); it refuses. Names the root and the directory, and says to put the
    jail directory outside the write root."""


class EnvPassUnsupported(ValueError):
    """Raised when `spec.env.mode` is `EnvMode.PASS`: it is the host's whole environment, which an
    image's userland is not built for, and which would be written, secrets and all, into a
    container's configuration. Says to use `SCRUB` and `allow_names`."""


class UnknownUser(ValueError):
    """Raised when `ctx.euid` is `None`: `--user` is the embedder's uid, so that files the
    workload writes into a project are not owned by root, and this mechanism never guesses root."""


class ContextMissing(ValueError):
    """Raised when a path this render needs is missing from `ctx.resolved_paths`, `path_exists` or
    `path_is_dir`. Names the path and the field; never a lexical fallback or a guess (SPEC.md §6,
    decisions 115, 159 and 164)."""


class PathNotMountable(ValueError):
    """Raised when a path holds a comma, a double quote, a line break or a NUL: `--mount` takes
    CSV, and such a path would add a key or end a field. Names the path."""


class CarveOutAboveRoot(ValueError):
    """Raised when a `write_denies` or `read_denies` entry is strictly above a root it would carve
    out of: Docker mounts the shallower path first, so the root would be laid over the carve-out and
    the deny would silently not hold. Names both."""


def _resolve(path: str, resolved: Mapping[str, str]) -> str:
    try:
        return resolved[path]
    except KeyError:
        raise ContextMissing(
            f"no resolved form for path {path!r} in ctx.resolved_paths; oci mounts the resolved "
            "path and never falls back to the lexical one"
        ) from None


def _fact(path: str, facts: Mapping[str, bool], field: str) -> bool:
    try:
        return facts[path]
    except KeyError:
        raise ContextMissing(
            f"no answer for path {path!r} in ctx.{field}; oci cannot choose between its mount "
            "forms without one"
        ) from None


def _is_subpath(candidate: str, root: str) -> bool:
    """True if the already-resolved `candidate` is `root` or lies under it. Lexical."""
    if root == "/":
        return True
    return candidate == root or candidate.startswith(root + "/")


def _mountable(path: str) -> str:
    """`path`, if `--mount` can carry it.

    Raises:
        PathNotMountable: it holds a comma, a double quote, a line break or a NUL.
    """
    if any(char in path for char in _UNMOUNTABLE):
        raise PathNotMountable(
            f"the path {path!r} holds a comma, a double quote, a line break or a NUL, which "
            "--mount (CSV) cannot carry; mount a path without one"
        )
    return path


def _bind(src: str, dst: str, *, readonly: bool) -> tuple[str, ...]:
    mount = f"type=bind,src={_mountable(src)},dst={_mountable(dst)}"
    return ("--mount", mount + (",readonly" if readonly else ""))


def _tmpfs(dst: str, mode: str) -> tuple[str, ...]:
    return ("--mount", f"type=tmpfs,dst={_mountable(dst)},tmpfs-mode={mode},readonly")


def _above(path: str, root: str) -> bool:
    """Whether the resolved `path` is strictly above the resolved `root`."""
    return path != root and _is_subpath(root, path)


def _refuse_above(kind: str, path: str, resolved_path: str, roots: tuple[str, ...]) -> None:
    """Refuse a carve-out strictly above one of `roots` (all resolved).

    Raises:
        CarveOutAboveRoot: it is.
    """
    for root in roots:
        if _above(resolved_path, root):
            raise CarveOutAboveRoot(
                f"the {kind} entry {path!r} (resolved {resolved_path!r}) is above the mounted "
                f"root {root!r}: Docker mounts the shallower path first, so the root would be "
                "laid over it and the deny would not hold. Name the path inside the root"
            )


def _read_denies_inside(
    spec: Spec, resolved: Mapping[str, str], roots: tuple[str, ...]
) -> tuple[str, ...]:
    """The `read_denies` entries at or under a mounted root. Refuses one above a root."""
    inside: list[str] = []
    for path in spec.fs.read_denies:
        found = _resolve(path, resolved)
        _refuse_above("read_denies", path, found, roots)
        if any(_is_subpath(found, root) for root in roots):
            inside.append(path)
    return tuple(inside)


def unmasked_read_denies(
    spec: Spec, *, resolved: Mapping[str, str], path_exists: Mapping[str, bool]
) -> tuple[str, ...]:
    """The read carve-outs inside a mounted root that did NOT exist when the context was built, so
    nothing masks them (a mask's mount point would be made on the host, decision-164). Pure;
    `Oci.compile` grades `fs_read` naming each one."""
    roots = tuple(
        _resolve(path, resolved) for path in (*spec.fs.read_allows, *spec.fs.write_allows)
    )
    return tuple(
        path
        for path in _read_denies_inside(spec, resolved, roots)
        if not _fact(path, path_exists, "path_exists")
    )


def render_flags(
    spec: Spec,
    *,
    resolved: Mapping[str, str],
    path_exists: Mapping[str, bool],
    path_is_dir: Mapping[str, bool],
    env_file: str,
    euid: int,
    channel_dir: str,
) -> tuple[str, ...]:
    """Render `spec` into the flags of `docker create` both variants share, between its verb and
    the image (`--init` and the supervisor's mount are the variants' own). `channel_dir` is the
    runtime's channel directory, already resolved, bound read-write at itself. Pure.

    Raises:
        ContextMissing, PathNotMountable, CarveOutAboveRoot: each naming its own subject; see the
            classes' docstrings.
    """
    flags: list[str] = [
        "--user",
        str(euid),
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--env-file",
        env_file,
    ]
    cpu = spec.limits.cpu_seconds
    if cpu:
        flags += ["--ulimit", f"cpu={cpu}:{cpu + 1}"]

    for path in spec.fs.read_allows:
        flags += _bind(_resolve(path, resolved), path, readonly=True)
    write_roots = tuple(_resolve(path, resolved) for path in spec.fs.write_allows)
    for path in spec.fs.write_allows:
        flags += _bind(_resolve(path, resolved), path, readonly=False)
    # The channel directory (decision-203), at its own resolved path. No write root contains it
    # (`_refuse_reachable_jail_dir`), so no carve-out is laid over it and it is laid over nothing.
    flags += _bind(channel_dir, channel_dir, readonly=False)

    # The pins (decision-168): each existing directory between a write root and a carve-out, bound
    # over itself, so it is a mount point and `mv .git .git-moved` finds it busy.
    for path in pins(spec.fs.write_allows, spec.fs.write_denies):
        if _fact(path, path_exists, "path_exists") and _fact(path, path_is_dir, "path_is_dir"):
            flags += _bind(_resolve(path, resolved), path, readonly=False)

    # The write carve-outs a writable tree reaches (one outside is unwritable already, and
    # binding it would be a READ grant: decision-165).
    for path in spec.fs.write_denies:
        found = _resolve(path, resolved)
        _refuse_above("write_denies", path, found, write_roots)
        if not any(_is_subpath(found, root) for root in write_roots):
            continue
        if _fact(path, path_exists, "path_exists"):
            flags += _bind(found, path, readonly=True)
        else:
            flags += _tmpfs(path, "0555")

    # The read carve-outs that exist inside a mounted root: masked. The absent ones are
    # `unmasked_read_denies`' business: not mounted, and graded.
    mounted = (*(_resolve(path, resolved) for path in spec.fs.read_allows), *write_roots)
    for path in _read_denies_inside(spec, resolved, mounted):
        if not _fact(path, path_exists, "path_exists"):
            continue
        if _fact(path, path_is_dir, "path_is_dir"):
            flags += _tmpfs(path, "0001")
        else:
            flags += _bind("/dev/null", path, readonly=True)
    return tuple(flags)


def _refuse_unrepresentable_env(spec: Spec) -> None:
    """Refuse an allowed name, a `set` name or a `set` value an env file cannot carry.

    Raises:
        EnvNotRepresentable: naming the variable, never the value.
    """
    for name in spec.env.allow_names:
        reason = env_refusal(name)
        if reason is not None:
            raise EnvNotRepresentable(f"spec.env.allow_names: {reason}")
    for name, value in spec.env.set:
        reason = env_refusal(name, value)
        if reason is not None:
            raise EnvNotRepresentable(f"spec.env.set: {reason}")


def _refuse_reachable_jail_dir(spec: Spec, resolved: Mapping[str, str], jail_dir: str) -> None:
    """Refuse a write root at or above the jail directory, or at or under its `procs/`.

    Raises:
        JailDirReachable: it is.
    """
    records = f"{jail_dir.rstrip('/')}/{PROCS_DIRNAME}"
    for path in spec.fs.write_allows:
        root = _resolve(path, resolved)
        if _is_subpath(jail_dir, root) or _is_subpath(root, records):
            raise JailDirReachable(
                f"the write root {path!r} (resolved {root!r}) reaches the jail directory "
                f"{jail_dir!r}, where the records of the jail's processes are (kill authority, "
                "decision-173), and a container does not seal it. Put the jail directory outside "
                "every write root"
            )


def _identity(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


class Oci:
    """SPEC.md §6's `oci` mechanism: a container as the jail, for `image`.

    Args:
        image: The image to create the container from. The runtime never pulls (`--pull never`),
            so the embedder names an image it has. A name, not an option: not empty, no
            whitespace, not starting with `-`.
        interpreter: The absolute path inside the image of the Python that brig's supervisor runs
            under as the container's PID 1 (Python 3.9 or later), `DEFAULT_INTERPRETER` by default.
            The runtime tries it first and, when the image has none (`docker start` answers
            127), makes the container again as the exec variant (decision-203). `None` names no
            interpreter: processes are started with `docker exec`, and the attempt is skipped.

    Raises:
        ValueError: `image` is not an image name, or `interpreter` is not an absolute path.
    """

    name = "oci"
    axes: frozenset[Axis] = _AXES
    #: A container lives and dies through the Docker daemon, not a host process (decision-202).
    runtime: RuntimeKind | None = RuntimeKind.OCI

    def __init__(self, image: str, *, interpreter: str | None = DEFAULT_INTERPRETER) -> None:
        if not image or image.startswith("-") or any(char.isspace() for char in image):
            raise ValueError(
                f"Oci(image): {image!r} is not an image name (not empty, no whitespace, not "
                "starting with '-')"
            )
        if interpreter is not None and not interpreter.startswith("/"):
            raise ValueError(
                f"Oci(interpreter={interpreter!r}): the interpreter is an absolute path inside the "
                "image (the container's PATH is the image's, and brig names no program by a bare "
                "name), or None to start processes with `docker exec`"
            )
        self._image = image
        self._interpreter = interpreter

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        """Refuse what a container cannot deliver (see the module docstring) and render the
        flags. `fs_read` is `best_effort`, naming the image and any read carve-out left unmasked.

        Raises:
            PlatformUnsupported, ReadModelUnsupported, NetworkUnsupported, EnvPassUnsupported,
            UnknownUser, EnvNotRepresentable, ContextMissing, PathNotMountable, CarveOutAboveRoot,
            JailDirReachable: each naming its own subject.
        """
        if ctx.platform != _LINUX:
            raise PlatformUnsupported(
                f"oci only compiles for ctx.platform == {_LINUX!r}, got {ctx.platform!r}: "
                "Docker Desktop's bind mounts and uid mapping are not measured"
            )
        if spec.fs.read_model is not ReadModel.ALLOW_LIST:
            raise ReadModelUnsupported(
                f"oci only compiles ReadModel.ALLOW_LIST specs, got {spec.fs.read_model!r}"
            )
        if spec.network.allowed_domains:
            raise NetworkUnsupported(
                "oci runs the container with --network none, which is deny-all: it cannot let a "
                f"domain through. Got spec.network.allowed_domains={spec.network.allowed_domains!r}"
            )
        if spec.env.mode is EnvMode.PASS:
            raise EnvPassUnsupported(
                "oci cannot pass the host's whole environment into a container: an image's "
                "userland is not built for it, and it would be written, secrets and all, into the "
                "container's configuration. Use EnvPolicy(mode=SCRUB, allow_names=...) to forward "
                "the names the process needs"
            )
        if ctx.euid is None:
            raise UnknownUser(
                "ctx.euid is None: --user is the embedder's uid, so that files the workload "
                "writes are not owned by root, and oci never guesses root. Build the context "
                "with build_compile_ctx"
            )
        _refuse_unrepresentable_env(spec)
        _refuse_reachable_jail_dir(spec, ctx.resolved_paths, ctx.jail_dir)

        jail_dir = ctx.jail_dir.rstrip("/")
        env_file = f"{jail_dir}/{ENV_FILE_NAME}"
        chan = ctx.channel_dir
        source = _mountable(f"{jail_dir}/{SUPERVISOR_SOURCE_FILE}")
        flags = render_flags(
            spec,
            resolved=ctx.resolved_paths,
            path_exists=ctx.path_exists,
            path_is_dir=ctx.path_is_dir,
            env_file=env_file,
            euid=ctx.euid,
            channel_dir=chan,
        )
        unmasked = unmasked_read_denies(
            spec, resolved=ctx.resolved_paths, path_exists=ctx.path_exists
        )
        grades: dict[Axis, Graded] = {
            Axis.FS_READ: _fs_read_graded(unmasked),
            Axis.FS_WRITE: Graded(Grade.ENFORCED, _FS_WRITE_DETAIL),
            Axis.NETWORK: Graded(Grade.ENFORCED, _NETWORK_DETAIL),
            Axis.ENV: Graded(Grade.ENFORCED, _ENV_DETAIL),
        }
        if spec.limits.cpu_seconds:
            grades[Axis.LIMITS] = Graded(Grade.BEST_EFFORT, _LIMITS_DETAIL)
        wrap: ArgvTransformer = _identity
        return Step(
            wrap=wrap,
            env={},
            staged=(),
            helpers=(),
            requires=frozenset(),
            grades=grades,
            denial_signatures=(_EROFS_SIGNATURE, _ENETUNREACH_SIGNATURE),
            container=ContainerPlan(
                image=self._image,
                flags=flags,
                command=IDLE_COMMAND,
                env_file=env_file,
                env_forward=spec.env.allow_names,
                env_set=spec.env.set,
                channel_dir=chan,
                interpreter=self._interpreter,
                supervisor_source=source,
                rendezvous=f"{chan}/{AGENT_SOCKET_NAME}",
            ),
        )


def _fs_read_graded(unmasked: tuple[str, ...]) -> Graded:
    """`best_effort` always -- the image is the gap -- naming the read carve-outs left unmasked."""
    if not unmasked:
        return Graded(Grade.BEST_EFFORT, _FS_READ_DETAIL)
    return Graded(
        Grade.BEST_EFFORT,
        f"{_FS_READ_DETAIL} Not masked, because they did not exist when the context was built and "
        f"a mask would need a mount point made on the host: {', '.join(unmasked)}. A file created "
        "at one of these after the container starts is readable inside it.",
    )


__all__ = (
    "ENV_FILE_NAME",
    "IDLE_COMMAND",
    "SUPERVISOR_SOURCE_FILE",
    "CarveOutAboveRoot",
    "ContextMissing",
    "EnvPassUnsupported",
    "JailDirReachable",
    "NetworkUnsupported",
    "Oci",
    "PathNotMountable",
    "PlatformUnsupported",
    "ReadModelUnsupported",
    "UnknownUser",
    "render_flags",
    "unmasked_read_denies",
)

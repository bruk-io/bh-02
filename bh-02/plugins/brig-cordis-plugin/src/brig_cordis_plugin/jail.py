"""The `jail` value over brig: a Spec built from where the work is, compiled, launched, graded.

`spec_for` is the whole policy as a pure function. What an input may write: the project root
(`write`) and a scratch directory of the jail's own. What it may not, even inside those: the
composition's layer files (an input rewriting one would reshape the program running it, outside
the jail), every path the host imports code from (`sys.path` entries and the interpreter's
prefix), and brig's own self-modification list (`.git/hooks`, `.git/config`, shell rc files,
CLAUDE.md, ...). What it may not read: brig's credential list under the home directory, `hide`
under the project, and what the `layers` value names as `secrets` (bh-02's own `local.env`,
wherever bh-02 runs from, and the sessions' state, where Claude Code keeps its tokens). No
network: seatbelt allows only the kernel's own socket. The worker's environment is scrubbed
to a short allowlist. brig's host process, which starts the worker from outside the jail,
keeps bh-02's own environment: brig's launcher composes `{**os.environ, **jail.env}` by its
spec, and `jail.env` can add keys but not remove them. So a variable of the launching shell (a
`CLAUDE_*` of a Claude Code that launched bh-02, say) sits in that process, out of an input's
reach (in the jail, `ps` fails with a permission error; measured). bh-02's own token is never there: it goes
only to the Claude Code child.

darwin only for now: the Linux preset (`strict_linux`) reads by allowlist, which needs the
interpreter's whole tree spelled out and has never been run here. Elsewhere `start` refuses and
says to use `kernel:unjailed`.
"""

import asyncio
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from sys import path as import_path
from sys import platform, prefix
from typing import Protocol, runtime_checkable

from brig.core import (
    CREDENTIAL_READ_DENIES_HOME_RELATIVE,
    SELF_MODIFY_WORKSPACE_RELATIVE,
    Channel,
    ChannelKind,
    EnvMode,
    EnvPolicy,
    FsPolicy,
    Spec,
)
from brig.run import Handle, IoPolicy, SubprocessLauncher, build_compile_ctx
from brig.stack import CompiledJail, scratch_darwin

__all__ = ["BrigConfig", "BrigJail", "Layers", "self_modify_denied", "spec_for"]

_READY_TIMEOUT_S = 10.0


@runtime_checkable
class Layers(Protocol):
    """What the jail needs of the `layers` value (CONTRACTS.md: layers): the composition's files,
    which an input may not write, and the credential files, which it may not read."""

    @property
    def paths(self) -> tuple[str, ...]: ...
    @property
    def secrets(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class BrigConfig:
    """`write`: where an input may write besides its scratch dir (relative to the kernel's root).
    `deny`: more paths it may not write. `allow`: names from brig's self-modification list
    (`SELF_MODIFY_WORKSPACE_RELATIVE`: `.git/hooks`, `CLAUDE.md`, ...) an input may write after all;
    by default the project's guidance files, which editing is ordinary work. The rest stay denied:
    they can run code outside the jail later (hooks, shell rc files, editor and Claude settings).
    `hide`: paths it may not read (relative to the root): a project's `local.env` may hold a
    credential. `env`: the variables that survive the scrub."""

    write: Sequence[str] = (".",)
    deny: Sequence[str] = ()
    allow: Sequence[str] = ("CLAUDE.md", "AGENTS.md")
    hide: Sequence[str] = ("local.env",)
    env: Sequence[str] = ("PATH", "HOME", "LANG", "LC_ALL", "TERM")


def spec_for(
    *,
    root: str,
    endpoint: str,
    scratch: str,
    home: str,
    config: BrigConfig,
    layers: Sequence[str],
    host: Sequence[str],
    secrets: Sequence[str] = (),
) -> Spec:
    """The jail's Spec. `host` is every path the host process loads code from; any under a
    writable root is denied, as are the layer files and brig's self-modification list.
    `secrets` (absolute) may not be read, wherever they are."""
    roots = [str(Path(root, w).resolve()) for w in config.write]
    writable = [*roots, scratch]
    # A host import path *inside* a writable root is denied. One that *is* a root (the project
    # itself on sys.path, as under `python -m bh_02`) is not: denying it would make the project
    # read-only. What that leaves: a module an input writes at the project root could shadow one
    # the host has not imported yet. The `bh-02` console script never puts the root on sys.path.
    under = [p for p in host if p not in writable and any(p.startswith(r + "/") for r in writable)]
    selfmod = [str(Path(r, name)) for r in roots for name in self_modify_denied(config.allow)]
    denies = [*layers, *under, *selfmod, *(str(Path(root, d).resolve()) for d in config.deny)]
    return Spec(
        fs=FsPolicy(
            write_allows=tuple(writable),
            write_denies=tuple(denies),
            read_denies=(
                *(str(Path(home, name)) for name in CREDENTIAL_READ_DENIES_HOME_RELATIVE),
                *(str(Path(root, name).resolve()) for name in config.hide),
                *secrets,
            ),
        ),
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=tuple(config.env), set=(("TMPDIR", scratch),)),
        channels=(Channel(name="kernel", kind=ChannelKind.LISTEN, endpoint=endpoint),),
    )


def self_modify_denied(allow: Sequence[str]) -> tuple[str, ...]:
    """brig's self-modification list without the names `allow` lets an input write. A name that
    is not on the list is a mistake in the row's config, never silently ignored."""
    unknown = [name for name in allow if name not in SELF_MODIFY_WORKSPACE_RELATIVE]
    if unknown:
        raise ValueError(
            f"the jail row's `allow` names {', '.join(map(repr, unknown))}, which brig does not deny "
            f"in the first place; `allow` takes only names from its self-modification list: "
            f"{', '.join(SELF_MODIFY_WORKSPACE_RELATIVE)}. To let an input write another path, "
            "use `write`"
        )
    return tuple(name for name in SELF_MODIFY_WORKSPACE_RELATIVE if name not in allow)


class _Jailed:
    """A program brig started: interrupt is SIGINT to its group, stop is brig's teardown."""

    def __init__(self, handle: Handle, jail_dir: str) -> None:
        self._handle = handle
        self._jail_dir = jail_dir

    def interrupt(self) -> bool:
        return self._handle.interrupt()

    async def stop(self) -> None:
        await asyncio.to_thread(self._handle.kill)
        shutil.rmtree(self._jail_dir, ignore_errors=True)


class BrigJail:
    """Implements `Jail` (CONTRACTS.md: jail) with brig's `scratch_darwin()` stack."""

    def __init__(self, config: BrigConfig, layers: Layers) -> None:
        self._config = config
        self._layers = layers
        # The grades are known before anything starts: compile once against a throwaway directory.
        with tempfile.TemporaryDirectory(prefix="bh-j-", dir="/tmp") as probe:
            self._report: Mapping[str, str] = self._compile(probe, str(Path(probe, "k.sock")), ".")[1]

    def report(self) -> Mapping[str, str]:
        return self._report

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> _Jailed:
        if platform != "darwin":
            raise RuntimeError(
                f"brig:jail runs on darwin here (seatbelt); this is {platform}. "
                "Use `kernel:unjailed` for the jail row (or `bh-02 --no-jail`), knowing it confines nothing"
            )
        jail_dir = tempfile.mkdtemp(prefix="bh-j-", dir="/tmp")
        jail, self._report = self._compile(jail_dir, endpoint, cwd)
        handle = await asyncio.to_thread(
            SubprocessLauncher().launch,
            jail,
            argv=list(argv),
            cwd=cwd,
            io=IoPolicy(),
            jail_id=Path(jail_dir).name,
            jail_dir=jail_dir,
        )
        started = _Jailed(handle, jail_dir)
        try:
            await asyncio.to_thread(handle.wait_ready, "kernel", _READY_TIMEOUT_S)
        except BaseException as error:
            log = Path(jail_dir, "stderr.log")
            detail = log.read_text(errors="replace")[-2000:] if log.is_file() else ""
            await started.stop()
            raise RuntimeError(f"the jailed kernel never listened: {error}\n{detail}") from error
        return started

    def _compile(self, jail_dir: str, endpoint: str, cwd: str) -> tuple[CompiledJail, Mapping[str, str]]:
        scratch = str(Path(jail_dir, "tmp"))
        Path(scratch).mkdir(parents=True, exist_ok=True)
        host = [str(Path(p).resolve()) for p in (*import_path, prefix) if p]
        spec = spec_for(
            root=cwd,
            endpoint=endpoint,
            scratch=scratch,
            home=str(Path.home()),
            config=self._config,
            layers=self._layers.paths,
            host=host,
            secrets=self._layers.secrets,
        )
        jail = scratch_darwin().compile(
            spec, ctx=build_compile_ctx(spec, jail_dir=jail_dir, platform=platform)
        )
        return jail, {axis.value: graded.grade.value for axis, graded in jail.report.axes.items()}

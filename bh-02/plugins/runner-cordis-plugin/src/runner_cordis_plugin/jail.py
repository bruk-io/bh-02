"""The confined runner's shell over brig (`runner:confined`): the policy (`policy.spec_for`, a
`Policy` of bh-02's own) gathered from the host, shaped for the platform, turned into brig's
policies (`brig_spec.to_brig`, the one converter), launched and graded. This module and that one
are the only ones that import brig, and they import only what `brig` exports.

Linux only, for now. brig has a bubblewrap jail (`create_bwrap_jail`) and no darwin one yet, so
on darwin `start` refuses, naming `runner:unconfined`; a seatbelt jail is TASK-0176.05's.

The jail reads by allowlist, so `allowlisted` turns the policy into one: what is readable is the
system tree (`/usr`, `/etc`, ...), the interpreter (`sys.base_prefix`, `sys.prefix`, and the
tree a link on the way to bh-02's interpreter leads to: brig runs its supervisor, the jail's PID 1,
under bh-02's own interpreter and refuses a policy that does not mount it), the directories the
command names, bh-02's own code (`code`, read-only: the extensions process imports cordis, with an
editable install from the workspace), and what the policy lets an input write. Everything else
does not exist in the jail, the home directory included. The secrets stay masks, brig's
carve-outs inside that tree. A write deny or a mask at a path that is not there is held by a
directory brig makes there for the jail's life (and removes with it).

bubblewrap holds each of those paths with a mount on the host's own directory entry, and a mount
can be undone from the host (a file renamed over a denied or masked one, as a host `git config`
does to `.git/config`; a placeholder removed), and from then on an input could write or read that
path. So the jail watches every path it holds (`mounts.tripwired`, `tripwire.Tripwire`) and ends
itself at the first such change: the next input's jail holds the path again, and the input says
why (`ended`). Until it has ended (a few milliseconds; measured in the README) a program already
running in it can get one write or read in, so brig grades `fs_write` and `fs_read` best-effort
while the jail holds such a path, and `notice()` says which secrets (`mounts.held`,
`mounts.notice_for`). The tripwire is armed once brig has made the jail, so a host change in the
moments between bubblewrap mounting a path and the watch being set is not seen.

The jail ends with bh-02, however it ends: brig starts bubblewrap with `--die-with-parent`.
"""

import asyncio
import contextlib
import os
import shutil
import signal
import tempfile
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from sys import base_prefix, prefix
from sys import executable as host_executable
from sys import path as import_path
from sys import platform as host_platform
from typing import Protocol, assert_never, runtime_checkable

from brig import (
    Channel,
    ChannelJailFinished,
    ChannelNotReady,
    ChannelReady,
    ChannelRefused,
    Jail,
    await_channel_ready,
    create_bwrap_jail,
    destroy_jail,
    interrupt_jail,
    reserve_channels,
)
from host_paths import state_home
from runner_cordis_plugin.brig_spec import report_of, to_brig
from runner_cordis_plugin.facts import git_identity, instead, interpreter_files, links_on_the_way
from runner_cordis_plugin.mounts import held, mountable, notice_for, released_for, tripwired
from runner_cordis_plugin.policy import (
    BrigConfig,
    Policy,
    allowlisted,
    git_author,
    readable_roots,
    spec_for,
    told_reads,
)
from runner_cordis_plugin.runner import ArgvFor
from runner_cordis_plugin.tripwire import Tripwire

__all__ = ["CHANNEL", "PLANNED", "SYSTEM_READABLE", "BrigJail", "Host", "planned"]

#: The name of the one channel a program listens on: the socket its owner dials.
CHANNEL = "program"

_READY_TIMEOUT_S = 10.0

#: The system tree a Linux jail may read: what the interpreter links against and reads at
#: start (`/lib`, `/usr/lib`, `/etc/ld.so.cache`, locale data) and what an input runs (`/bin/sh`,
#: `git`, ...). Entries that do not exist on a host (`/lib64` on arm64) are dropped at start.
SYSTEM_READABLE: tuple[str, ...] = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc")

#: The grades a start of the jail can earn at most, known before anything starts (what `approval`
#: reads): `fs_write` and `fs_read` are best-effort because bh-02's policy always holds write
#: denies under the project (the layer files, `.git/hooks`, ...), and may hold a secret there, with a
#: mount the host can undo; brig grades each start itself (`BrigJail.start`), which can only be
#: stronger for `fs_read`.
PLANNED: Mapping[str, str] = {
    "fs_read": "best_effort",
    "fs_write": "best_effort",
    "network": "enforced",
    "env": "enforced",
}


@runtime_checkable
class Host(Protocol):
    """What the jail needs of the `host` value (CONTRACTS.md: host): the composition's files,
    which an input may not write; the secrets, which it may not read; bh-02's configuration directories
    (`trusted`), whose files the host reads and trusts, which it may not write; the directories
    bh-02 runs its own code from (`code`), which every jail reads and no input writes; and the
    project's auto memory directory (`auto_memory`), which it may write ('' for none)."""

    @property
    def paths(self) -> tuple[str, ...]: ...
    @property
    def secrets(self) -> tuple[str, ...]: ...
    @property
    def trusted(self) -> tuple[str, ...]: ...
    @property
    def code(self) -> tuple[str, ...]: ...
    @property
    def auto_memory(self) -> str: ...


def _not_ready_message(outcome: ChannelNotReady | ChannelRefused | ChannelJailFinished) -> str:
    """Why the jailed program never listened, as brig's `await_channel_ready` answered."""
    match outcome:
        case ChannelNotReady():
            return f"nothing listened on its channel within {_READY_TIMEOUT_S:g} s"
        case ChannelJailFinished():
            return "it ended before it listened"
        case ChannelRefused(reason=reason):
            return f"brig refused what answered on its channel ({reason})"
        case _ as unreachable:
            assert_never(unreachable)


@dataclass(frozen=True, slots=True)
class _Facts:
    """What one start of the jail is, kept with that start for whoever started it (CONTRACTS.md:
    runner): its grades (brig's), what the person should know about it (`notice_for`), the trees
    its program reads when that is all it reads (`told_reads`) and the roots it may write but its
    scratch. A jail starts more than one program (the Python process, the extensions process),
    each from its own command: what one start is never replaces what another is."""

    report: Mapping[str, str]
    notice: str = ""
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()


class _Jailed:
    """A program brig started (`jail`): interrupt is brig's, stop is brig's teardown of the jail
    (`destroy_jail`), then the directories the jail made on the host (`directories`) once it is
    gone. `facts` is what this start is (`report`, `notice`, `reads`, `writes`), read whether or not
    it still runs. `group` is the process group the jail leads (bubblewrap's).

    `wire` watches the paths the jail holds with a mount and ends the jail when the host undoes
    one (`Tripwire`); `ended` says so. `stop` stops it first: brig removing the directories it
    made would read as the host undoing them."""

    def __init__(
        self, jail: Jail, endpoint: str, facts: _Facts, directories: Sequence[str], wire: Tripwire
    ) -> None:
        self.endpoint = endpoint
        self.group = jail.process.pid
        self._jail = jail
        self._facts = facts
        self._wire = wire
        self._directories = tuple(directories)
        self._stopping: asyncio.Future[None] | None = None
        self._destroyed = False
        self._destroying = threading.Lock()

    def interrupt(self) -> bool:
        return bool(interrupt_jail(self._jail))

    def ended(self) -> str:
        """Why the jail ended its program itself (the host undid a mount, `tripped_for`), or ""."""
        return self._wire.tripped

    def report(self) -> Mapping[str, str]:
        """This start's grades, brig's own."""
        return self._facts.report

    def notice(self) -> str:
        """What the person should know about this start's jail (`notice_for`): the secrets it
        holds with a mount the host can undo."""
        return self._facts.notice

    def reads(self) -> tuple[str, ...]:
        """The trees this start's program can read, when that is all it can read (`told_reads`):
        the jail's allowlist (the system, the interpreter, the program's own directory, bh-02's own
        code) and the roots it may write."""
        return self._facts.reads

    def writes(self) -> tuple[str, ...]:
        """The directories this start's program may write, but the jail's own scratch: the
        project and what `write` adds."""
        return self._facts.writes

    @property
    def stopped(self) -> bool:
        """Whether it has been stopped, by whoever started it or by the jail's `release`."""
        return self._stopping is not None

    def end(self) -> None:
        """End the jail now: brig's teardown, once however many ask (the tripwire's thread, `stop`).

        Raises:
            JailTeardownFailed: a process of the jail survived the kill.
        """
        with self._destroying:
            if not self._destroyed:
                destroy_jail(self._jail)
                self._destroyed = True

    def kill(self) -> None:
        """SIGKILL to the jail's process group: what the tripwire does when `end` raised."""
        os.killpg(self.group, signal.SIGKILL)

    async def stop(self) -> None:
        """brig's teardown, then what the jail made, once: whoever started the program and the
        jail's `release` may both stop it, and the second waits for the first."""
        if self._stopping is None:
            self._stopping = asyncio.ensure_future(self._teardown())
        await asyncio.shield(self._stopping)

    async def _teardown(self) -> None:
        try:
            await asyncio.to_thread(self._wire.stop)
            await asyncio.to_thread(self.end)
        finally:
            for directory in self._directories:
                shutil.rmtree(directory, ignore_errors=True)


def planned(
    config: BrigConfig,
    host: Host,
    *,
    scratch_root: str,
    cwd: str,
    argv: Sequence[str],
    author: Sequence[tuple[str, str]] = (),
) -> Policy:
    """The policy for `argv` in `cwd` as the Linux jail takes it: the host's `spec_for`, reading by
    allowlist, its denies made ones bubblewrap can mount, the git author (`author`) set. Reads the
    host (the interpreter and its links, which paths exist) and makes the jail's scratch directory
    under `scratch_root`."""
    scratch = str(Path(scratch_root, "tmp"))
    Path(scratch).mkdir(parents=True, exist_ok=True)
    hosted = [str(Path(p).resolve()) for p in (*import_path, prefix) if p]
    names = (host_executable, str(Path(base_prefix, "bin", "python3")))  # how the host reaches its Python
    policy = spec_for(
        root=cwd,
        scratch=scratch,
        home=str(Path.home()),
        config=config,
        layers=host.paths,
        host=hosted,
        secrets=host.secrets,
        trusted=host.trusted,
        code=host.code,
        interpreters=interpreter_files(names),
        links=[link.entry for link in links_on_the_way(names)],
        memory=host.auto_memory,
    )
    readable = readable_roots(
        argv=argv, interpreter=(base_prefix, prefix), system=SYSTEM_READABLE, code=host.code
    )
    # a tree reached through a link must be named as the link too: bubblewrap mounts a tree
    # at the path the policy spells (a uv venv's `python` points into `cpython-3.15-...`, a
    # link to the `cpython-3.15.0rc2-...` that `sys.base_prefix` names; measured: without it
    # the worker's exec fails with "No such file or directory"), and brig refuses a policy that
    # does not mount every link on the way to the interpreter it runs its supervisor under
    links = [
        link.entry
        for each in (*(os.path.abspath(arg) for arg in argv if arg.startswith("/")), *names)
        for link in links_on_the_way([each])
        if link.through
    ]
    policy = allowlisted(policy, [p for p in (*readable, *links) if Path(p).exists()])
    denies = mountable(policy.write_denies, instead(policy.write_denies, policy.writable))
    return replace(policy, write_denies=denies, env_set=(*policy.env_set, *author))


def _jails_root() -> Path:
    """Where each jail keeps its scratch directory: beneath the person's state directory, not
    `/tmp`, where a jail that could write would share a directory with sockets other programs
    listen on (brig grades `channel_exclusivity` violated for a jail that sees one)."""
    return Path(state_home(os.environ, Path.home()), "bh-02", "jails")


class BrigJail:
    """The confined runner's mechanism (`runner.Mechanism`): a bubblewrap jail through brig, on
    Linux. `platform` is where this runs (only tests pass it); anywhere else `start` refuses and
    names `runner:unconfined`."""

    def __init__(
        self, config: BrigConfig, host: Host, *, platform: str = host_platform, note: str = ""
    ) -> None:
        self._config = config
        self._host = host
        self._note = note
        self._platform = platform
        # every program this jail started that may still run, and the starts under way: what
        # `release` waits for (a start under way) and says still runs (an owner that kept its own)
        self._live: list[_Jailed] = []
        self._starting: set[asyncio.Future[None]] = set()

    def report(self) -> Mapping[str, str]:
        """The grades, known before anything starts (what `approval` reads): the most a start can
        earn (`PLANNED`). A started program's own are its `report()`."""
        return PLANNED

    async def release(self) -> str:
        """For `/release`, once each owner has stopped its own program (`runner.Runner`): wait for
        a start under way, then say whether a program of this jail's still runs (`released_for`).
        brig removes what a jail made on the host when the jail ends, so nothing else is held."""
        await asyncio.gather(*self._starting)
        self._live = [started for started in self._live if not started.stopped]
        return released_for(running=bool(self._live))

    async def start(self, argv_for: ArgvFor, *, cwd: str) -> _Jailed:
        """Start the program `argv_for(endpoint)` in `cwd`, in a jail of its own made from the
        policy, listening on the endpoint brig reserved for this start (`started.endpoint`).

        Raises:
            RuntimeError: this is not Linux, or there is no bubblewrap, or the program never
                listened. brig's own refusals of the policy (`PolicyRootAbsent`, ...) cross as they are.
        """
        starting: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._starting.add(starting)
        try:
            started = await self._launched(argv_for, cwd=cwd)
            self._live = [*(each for each in self._live if not each.stopped), started]
            return started
        finally:
            self._starting.discard(starting)
            if not starting.done():  # a `release` cancelled as it waited cancels it
                starting.set_result(None)

    async def _launched(self, argv_for: ArgvFor, *, cwd: str) -> _Jailed:
        if self._platform != "linux":
            raise RuntimeError(
                f"runner:confined runs on Linux (bubblewrap) for now; this is {self._platform}, and brig "
                "has no jail for it yet (a seatbelt jail for darwin is TASK-0176.05). "
                "Use `runner:unconfined` for the runner row (or `bh-02 --no-jail`), knowing it "
                "confines nothing"
            )
        if shutil.which("bwrap") is None:
            raise RuntimeError(
                "runner:confined runs programs under bubblewrap on Linux, and there is no `bwrap` on "
                "PATH: install the `bubblewrap` package, or use `runner:unconfined` for the runner row "
                "(or `bh-02 --no-jail`), knowing it confines nothing"
            )
        root = _jails_root()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        scratch_root = tempfile.mkdtemp(prefix="bh-j-", dir=root)
        # The program's streams go to files outside every writable root (brig refuses otherwise),
        # and the project may be the person's home: a directory of its own under /tmp.
        logs = tempfile.mkdtemp(prefix="bh-l-", dir="/tmp")
        directories = (scratch_root, logs)
        try:
            reservations = reserve_channels((Channel(CHANNEL),))
            reservation = reservations.reservations[0]
            argv = tuple(argv_for(reservation.endpoint))
            author = git_author(*git_identity(cwd))
            policy = planned(
                self._config, self._host, scratch_root=scratch_root, cwd=cwd, argv=argv, author=author
            )
            brigged = to_brig(
                policy,
                environ=os.environ,
                stdout=str(Path(logs, "stdout.log")),
                stderr=str(Path(logs, "stderr.log")),
            )
            launching = asyncio.ensure_future(
                asyncio.to_thread(
                    create_bwrap_jail,
                    argv,
                    env=brigged.env,
                    policy=brigged.fs,
                    env_policy=brigged.env_policy,
                    channels=reservations,
                    cwd=cwd,
                    stdio=brigged.stdio,
                )
            )
            try:
                jail = await asyncio.shield(launching)
            except asyncio.CancelledError:
                # The launch's thread runs on whatever happens here: wait for it, and end what it
                # started. A launch that raised has nothing to end (brig cleaned up after itself).
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(destroy_jail, await launching)
                raise
            try:
                wire = Tripwire(tripwired(policy))
            except BaseException:
                await asyncio.to_thread(destroy_jail, jail)
                raise
        except BaseException:
            for directory in directories:
                shutil.rmtree(directory, ignore_errors=True)
            raise
        started = _Jailed(
            jail, reservation.endpoint, self._facts(policy, jail, scratch_root), directories, wire
        )
        wire.arm(started.end, fallback=started.kill)
        try:
            outcome = await asyncio.to_thread(
                await_channel_ready, jail, reservation, timeout_s=_READY_TIMEOUT_S
            )
            if not isinstance(outcome, ChannelReady):
                log = Path(logs, "stderr.log")
                detail = log.read_text(errors="replace")[-2000:] if log.is_file() else ""
                raise RuntimeError(
                    f"the jailed program never listened: {_not_ready_message(outcome)}\n{detail}"
                )
        except BaseException:
            with contextlib.suppress(Exception):
                await started.stop()
            raise
        return started

    def _facts(self, policy: Policy, jail: Jail, scratch_root: str) -> _Facts:
        """What a start of `policy` is, for whoever started it: brig's grades of the jail, its
        notice, the trees it reads and the roots it may write but its scratch."""
        writes = tuple(w for w in policy.writable if not Path(w).is_relative_to(scratch_root))
        return _Facts(
            report_of(jail.report),
            "\n".join(filter(None, (self._note, notice_for(self._platform, held(policy))))),
            told_reads((*policy.readable, *policy.writable), (scratch_root,)),
            writes,
        )

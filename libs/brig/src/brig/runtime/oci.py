"""`OciRuntime`: a container as a jail's instance, created and ended through the Docker daemon.

SPEC.md §8 (decision-202), decision-0001's migration step 5, first half. The `oci` mechanism
(`brig/mech/oci.py`) compiles a `Spec` to a `ContainerPlan`; this runtime makes the container from
it, identifies it, checks it and ends it. A container is created and ended through the daemon,
never by signalling a host process group; nothing is started in it through brig yet, so it has no
supervisor (TASK-0079.10's), and `Jail.start` is absent on its jails (SPEC.md §9).

**The daemon is the runtime object's, never a record's.** Every `docker` runs with `DOCKER_HOST`
set to `docker_host` and an environment of its own (`_cli_env`): the settings the CLI needs to reach
a daemon and nothing else, so an inherited `DOCKER_CONTEXT`, which the CLI prefers to `DOCKER_HOST`,
cannot move it, and the creating process's environment is not the CLI's. The record
(`ContainerRecord`) holds the container's id and the daemon's id, an identity and not an address.

**Nothing acts on an identity it cannot verify.** `alive` and `destroy` ask the daemon for its id
and refuse one that is not the record's, then `docker inspect` the container and require its id and
its `brig.jail` label to be the record's and the jail's (`standing`, pure). `destroy` is `docker rm
-f`, verified by a second `docker inspect` that finds nothing: the report's evidence is that
observation and never the exit code (law 7).

**The tether is a host watcher** (decision-167's idea, a container's shape): `/bin/sh`, detached in a
session of its own, with the tether as its stdin. It reads to end-of-file, which is every write end
closed (the embedder closed it, or the kernel did because the embedder died, `SIGKILL` included), and
then runs `docker rm -f` on the container's id. It is the jail's one `JAIL_LIFETIME` helper
(`helper_pids`), so `destroy` ends it and a rehydrated jail can.

**The environment is an env file, never `-e`** (law 9): `create` writes it with mode 0600, created
exclusively and not through a link, in the jail directory, names it with `--env-file`, and removes
it as soon as `docker create` has returned, whatever came of it.

The decisions (`standing`, `create_args`, `daemon_id_of`) are pure and tested with the CLI's own
output; the rest is the shell that runs `docker`.
"""

import contextlib
import json
import os
import socket
import subprocess
from dataclasses import dataclass
from typing import Final, assert_never

from brig.core.runtime import Capability, ContainerPlan, RuntimeKind
from brig.run import _identity
from brig.run._tether import HeldTether
from brig.run.host import LaunchRefused
from brig.run.runtime import (
    ContainerRecord,
    JailRecord,
    ProcessRecord,
    Reservation,
    Supervisor,
)
from brig.run.teardown import (
    DEFAULT_GRACE_S,
    KillItem,
    KillOutcome,
    KillReport,
    end_group,
)
from brig.stack import CompiledJail

#: The default daemon: Docker's own socket.
DEFAULT_DOCKER_HOST: Final = "unix:///var/run/docker.sock"

#: Absolute, never the bare name `docker` (decision-026 rule 1): a bare name is resolved through
#: whatever `PATH` the process happens to carry, which is authority no `Spec` granted.
DEFAULT_DOCKER: Final = "/usr/bin/docker"

#: The label that identifies a container as a jail's (decision-0001, "Records and rehydration").
JAIL_LABEL: Final = "brig.jail"

#: How long any one `docker` call may take before it is called failed. Generous: a start is a
#: namespace and a few mounts, and this is for a wedged daemon, not honest slowness.
_DOCKER_TIMEOUT_S: Final = 120.0

#: The settings the CLI reads to reach a daemon, and nothing else of the process's environment.
_CLI_ENV_NAMES: Final = ("PATH", "HOME", "DOCKER_CONFIG", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY")

#: The tether watcher's script, run by `/bin/sh -c` with the docker path and the container's id as
#: its positional parameters (never interpolated into the text). It reads the tether, its stdin,
#: to end-of-file, then removes the container, a few times over a few seconds so a daemon that is
#: restarting at that moment is waited for. `--` keeps the id an operand.
_WATCHER_SCRIPT: Final = (
    'cat >/dev/null; for _ in 1 2 3 4 5; do "$1" rm -f -- "$2" && exit 0; sleep 1; done'
)


class OciUnavailable(RuntimeError):
    """The daemon cannot be asked, or its answer is not one this runtime may act on: the `docker`
    CLI could not be run or did not answer in time, the daemon is not the one the record names,
    or the container is not this jail's. `alive` raises it, since a bool cannot say "unknown";
    `destroy` reports it as a `FAILED` item instead. Says which."""


class OciCreateRefused(ValueError):
    """`create` was given a compiled jail it cannot make a container from: not an `OCI` one, with
    no container plan, or with helpers or staged files the `oci` mechanism does not produce (a
    runtime that ignored them would be a downgrade, law 2). Nothing was made."""


class OciCreateFailed(RuntimeError):
    """`docker create` or `docker start` failed, so there is no jail (anything `create` had
    made is removed first). The message carries docker's own error."""


# ---------------------------------------------------------------------------------------------
# The decisions: pure, read from the CLI's output.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Gone:
    """`docker inspect` found no such container."""


@dataclass(frozen=True, slots=True)
class Ours:
    """The container is the record's, carrying the jail's label. `running`: `State.Running`."""

    running: bool


@dataclass(frozen=True, slots=True)
class NotOurs:
    """The container exists and is not this jail's: another id, or another jail's label. `why`
    says which. Nothing is done to it."""

    why: str


@dataclass(frozen=True, slots=True)
class Unknown:
    """The daemon's answer cannot be acted on: it did not answer, is not the record's, or said
    something unreadable. `why` says which."""

    why: str


type Standing = Gone | Ours | NotOurs | Unknown


def daemon_id_of(returncode: int, stdout: str, stderr: str) -> str | None:
    """The daemon's id from `docker info --format '{{.ID}}'`, or `None` when it did not answer
    (a non-zero status) or printed no id. Pure."""
    del stderr
    found = stdout.strip()
    if returncode != 0 or not found:
        return None
    return found


def standing(
    returncode: int, stdout: str, stderr: str, *, container_id: str, jail_id: str
) -> Standing:
    """What `docker inspect --type container <container_id>` says of the container, for the jail
    `jail_id`. Pure. "No such" in the error of a failed inspect is `Gone`, the one failure that
    is an answer; any other failure is `Unknown`, and so is output that is not one container's
    JSON. A container whose id is not `container_id` (a prefix or a name matched something else)
    or whose `brig.jail` label is not `jail_id` is `NotOurs`."""
    if returncode != 0:
        if "no such" in stderr.lower():
            return Gone()
        return Unknown(f"docker inspect failed (status {returncode}): {stderr.strip()[:300]}")
    try:
        parsed = json.loads(stdout)
        (entry,) = parsed
        found = entry["Id"]
        running = entry["State"]["Running"]
        labels = entry["Config"]["Labels"] or {}
    except ValueError, KeyError, TypeError:
        return Unknown("docker inspect printed something that is not one container's JSON")
    if found != container_id:
        return NotOurs(f"the container {container_id} inspects as {found}")
    if labels.get(JAIL_LABEL) != jail_id:
        return NotOurs(
            f"the container {container_id} carries {JAIL_LABEL}={labels.get(JAIL_LABEL)!r}, not "
            f"this jail's {jail_id!r}"
        )
    return Ours(running=running is True)


def create_args(plan: ContainerPlan, jail_id: str) -> tuple[str, ...]:
    """The arguments `docker` is run with to create the container for `plan`: never pulls
    (`--pull never`), labels the container with the jail, then the plan's flags, image and
    command. The environment is in the file the flags name, never here (law 9). Pure."""
    return (
        "create",
        "--pull",
        "never",
        "--label",
        f"{JAIL_LABEL}={jail_id}",
        *plan.flags,
        plan.image,
        *plan.command,
    )


# ---------------------------------------------------------------------------------------------
# The shell: running `docker`.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Done:
    returncode: int
    stdout: str
    stderr: str


def _write_env_file(path: str, text: str) -> None:
    """Write `text` to `path`, mode 0600, created exclusively and not through a link: a stale file
    of an earlier create is removed first (its content is a secret nobody should keep), and a link
    planted at the path is removed as the link it is and never followed.

    Raises:
        OSError: the file could not be written.
    """
    with contextlib.suppress(FileNotFoundError):
        os.unlink(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as env_file:
        env_file.write(text)


@dataclass(frozen=True, slots=True)
class OciRuntime:
    """A container as a jail's instance (decision-202). Holds no state: everything a later call
    needs is the `JailRecord` `create` returns (its `container`: the container's id and the
    daemon's), so a record rehydrated in another process is controlled the same way, by a runtime
    the embedder builds with the daemon it means.

    `docker` is the absolute path of the CLI; `docker_host` the daemon's address, which is the
    runtime object's and no record's."""

    docker: str = DEFAULT_DOCKER
    docker_host: str = DEFAULT_DOCKER_HOST

    @property
    def kind(self) -> RuntimeKind:
        return RuntimeKind.OCI

    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset()

    def _cli_env(self) -> dict[str, str]:
        """The environment of every `docker` this runtime runs: the settings the CLI needs to
        reach a daemon, and `DOCKER_HOST` from this object."""
        env = {name: os.environ[name] for name in _CLI_ENV_NAMES if name in os.environ}
        env["DOCKER_HOST"] = self.docker_host
        return env

    def _run(self, *args: str) -> _Done:
        """Run `docker *args` and return what it said. A call that cannot be run at all, or that
        times out, is a non-zero status with the reason as its error, never an exception, so that
        every decision above reads one shape.

        Raises:
            OciUnavailable: the CLI could not be started (not there, not executable).
        """
        try:
            done = subprocess.run(
                [self.docker, *args],
                capture_output=True,
                text=True,
                check=False,
                env=self._cli_env(),
                stdin=subprocess.DEVNULL,
                timeout=_DOCKER_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return _Done(-1, "", f"docker {args[0]} timed out after {_DOCKER_TIMEOUT_S:.0f}s")
        except OSError as error:
            raise OciUnavailable(f"cannot run {self.docker!r}: {error}") from error
        return _Done(done.returncode, done.stdout, done.stderr)

    def _daemon_id(self) -> str | None:
        """The id of the daemon this object names, or `None` when it did not answer.

        Raises:
            OciUnavailable: the CLI could not be started.
        """
        done = self._run("info", "--format", "{{.ID}}")
        return daemon_id_of(done.returncode, done.stdout, done.stderr)

    def _standing(self, record: ContainerRecord, jail_id: str) -> Standing:
        """The container's standing, after checking that the daemon is the record's.

        Raises:
            OciUnavailable: the CLI could not be started.
        """
        daemon = self._daemon_id()
        if daemon is None:
            return Unknown(f"the daemon at {self.docker_host} did not answer `docker info`")
        if daemon != record.daemon_id:
            return Unknown(
                f"the daemon at {self.docker_host} is {daemon}, and this jail's container was "
                f"made by {record.daemon_id}: pass the runtime of the daemon that made it"
            )
        done = self._run("inspect", "--type", "container", record.container_id)
        return standing(
            done.returncode,
            done.stdout,
            done.stderr,
            container_id=record.container_id,
            jail_id=jail_id,
        )

    def _remove(self, container_id: str) -> None:
        """`docker rm -f` a container `create` made and is abandoning. Best effort: the error that
        sent us here is the one that is raised.

        Raises:
            OciUnavailable: the CLI could not be started.
        """
        self._run("rm", "-f", "--", container_id)

    def _start_watcher(self, container_id: str, tether: int) -> subprocess.Popen[bytes]:
        """Start the tether watcher on `container_id`: see the module docstring. `tether` is
        handed to it as its stdin; nothing else of this process is."""
        return subprocess.Popen(
            ["/bin/sh", "-c", _WATCHER_SCRIPT, "brig-oci-watcher", self.docker, container_id],
            stdin=tether,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=self._cli_env(),
            start_new_session=True,
            close_fds=True,
        )

    def create(
        self,
        jail: CompiledJail,
        *,
        cwd: str,
        jail_id: str,
        jail_dir: str,
        tether: int | None,
    ) -> JailRecord:
        """Make the jail's instance: a created and started container, labelled with `jail_id`,
        with nothing of brig's in it (`sleep infinity` under `--init`; TASK-0079.10 replaces it
        with the supervisor), and a tether watcher when `tether` is given.

        `tether` is the read end of a pipe whose write end the caller keeps; the runtime holds a
        duplicate while it starts the watcher, so the caller may close its own once this returns.
        The env file is written, named by `--env-file` and removed before `docker create` is
        judged. If anything after the container exists fails, the container and the watcher are
        removed before the error is raised.

        Raises:
            OciCreateRefused: `jail` is not an `OCI` jail with a container plan, or has helpers
                or staged files.
            LaunchRefused: `jail.requires` names a capability this runtime lacks (it has none).
            TetherClosed: `tether` has already ended.
            OciUnavailable: the CLI could not be run or the daemon did not answer `docker info`.
            EnvNotRepresentable: a forwarded variable cannot be a line of the env file (it names
                the variable, never the value).
            OciCreateFailed: `docker create` or `docker start` failed, or the container is not
                running right after it; carries docker's error.
            OSError: `tether` is not open, or `jail_dir` or the env file could not be written.
        """
        plan = jail.container
        if jail.runtime is not RuntimeKind.OCI or plan is None:
            raise OciCreateRefused(
                f"OciRuntime.create: the jail was compiled for the {jail.runtime.value} runtime "
                f"with {'no ' if plan is None else 'a '}container plan; only an OCI jail made by "
                "the `oci` mechanism can be made into a container"
            )
        if jail.helpers or jail.staged:
            raise OciCreateRefused(
                "OciRuntime.create: the jail has helpers or staged files, which the `oci` "
                "mechanism does not produce and this runtime would ignore; refusing rather than "
                "run a container without them"
            )
        missing = jail.requires - self.capabilities
        if missing:
            raise LaunchRefused(missing, "oci")

        hold = None if tether is None else HeldTether(tether)
        try:
            tether_fd = None if hold is None else hold.fd()
            daemon = self._daemon_id()
            if daemon is None:
                raise OciUnavailable(
                    f"the daemon at {self.docker_host} did not answer `docker info`; is it "
                    "running, and is the address right? (OciRuntime(docker_host=...))"
                )
            container_id = self._create_container(plan, jail_id, jail_dir)
            watcher: subprocess.Popen[bytes] | None = None
            try:
                if tether_fd is not None:
                    watcher = self._start_watcher(container_id, tether_fd)
                started = self._run("start", container_id)
                if started.returncode != 0:
                    raise OciCreateFailed(
                        f"docker start failed (status {started.returncode}): "
                        f"{started.stderr.strip()[:500]}"
                    )
                self._require_running(container_id, jail_id, plan)
            except BaseException:
                self._remove(container_id)
                if watcher is not None:
                    end_group(
                        "helper", watcher.pid, watcher.pid, _identity.start_stamp(watcher.pid)
                    )
                raise
        finally:
            if hold is not None:
                hold.release()

        helper_pids = () if watcher is None else (watcher.pid,)
        helper_stamps = () if watcher is None else (_identity.start_stamp(watcher.pid),)
        return JailRecord(
            kind=self.kind,
            jail_id=jail_id,
            jail_dir=jail_dir,
            cwd=cwd,
            jail_env=frozendict(jail.env),
            wrap_prefix=None,
            helper_pids=helper_pids,
            helper_stamps=helper_stamps,
            container=ContainerRecord(container_id=container_id, daemon_id=daemon),
        )

    def _require_running(self, container_id: str, jail_id: str, plan: ContainerPlan) -> None:
        """Ask once that the container started is running: under `--init` a command that is not in
        the image ends the container at once and `docker start` still returns 0, and a jail that
        does not run is no jail. One question, not a wait: a command that ends later reads gone by
        `alive`.

        Raises:
            OciCreateFailed: the container is not running.
            OciUnavailable: the CLI could not be started.
        """
        done = self._run("inspect", "--type", "container", container_id)
        found = standing(
            done.returncode, done.stdout, done.stderr, container_id=container_id, jail_id=jail_id
        )
        match found:
            case Ours(running=True):
                return
            case Ours() | Gone() | NotOurs() | Unknown():
                raise OciCreateFailed(
                    f"the container is not running right after docker start; its command "
                    f"{' '.join(plan.command)!r} may not be in the image {plan.image!r}"
                )
            case _ as unreachable:
                assert_never(unreachable)

    def _create_container(self, plan: ContainerPlan, jail_id: str, jail_dir: str) -> str:
        """Write the env file, `docker create`, remove the file; the container's full id.

        Raises:
            EnvNotRepresentable: a forwarded variable cannot be a line of the env file.
            OciCreateFailed: `docker create` failed.
            OciUnavailable: the CLI could not be started.
            OSError: `jail_dir` or the env file could not be written.
        """
        os.makedirs(jail_dir, mode=0o700, exist_ok=True)
        text = plan.env_file_text(os.environ)
        try:
            _write_env_file(plan.env_file, text)
            done = self._run(*create_args(plan, jail_id))
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(plan.env_file)
        container_id = done.stdout.strip()
        if done.returncode != 0 or not container_id:
            raise OciCreateFailed(
                f"docker create failed (status {done.returncode}): {done.stderr.strip()[:500]}"
            )
        return container_id

    def alive(self, jail: JailRecord) -> bool:
        """Whether the container still runs (`State.Running`), the container being the record's
        and the daemon the record's. A jail with no container reads gone.

        Raises:
            OciUnavailable: the daemon cannot be asked, is not the record's, or holds a
                container that is not this jail's: "unknown" is not a bool.
        """
        if jail.container is None:
            return False
        found = self._standing(jail.container, jail.jail_id)
        match found:
            case Gone():
                return False
            case Ours(running=running):
                return running
            case NotOurs(why=why) | Unknown(why=why):
                raise OciUnavailable(f"cannot say whether jail {jail.jail_id!r} is alive: {why}")
            case _ as unreachable:
                assert_never(unreachable)

    def processes(self, jail: JailRecord) -> tuple[ProcessRecord, ...]:
        """The processes `jail` holds: none. Nothing is started in a container through brig yet."""
        return jail.processes

    def tethered(self, jail: JailRecord) -> bool | None:
        """`None`: this runtime records nothing apart from the dict, and nothing asks until a
        start exists (TASK-0079.10)."""
        del jail
        return None

    def process_alive(self, jail: JailRecord, process: ProcessRecord) -> bool:
        """`False`: no process of a container jail is brig's to ask after."""
        del jail, process
        return False

    def destroy(self, jail: JailRecord, *, grace: float = DEFAULT_GRACE_S) -> KillReport:
        """`docker rm -f` the container, verified by `docker inspect`; then the tether watcher.
        One `container` item and one `helper` item. Total: raises nothing from an item.

        `grace` is accepted and has no effect: `docker rm -f` kills at once, which is what
        `grace=0` asks for everywhere (decision-193); a graceful stop is the process scope's."""
        del grace
        items: list[KillItem] = []
        if jail.container is not None:
            items.append(self._destroy_container(jail.container, jail.jail_id))
        items.extend(
            end_group("helper", pid, pid, stamp)
            for pid, stamp in zip(jail.helper_pids, jail.helper_stamps, strict=True)
        )
        return KillReport(items=tuple(items))

    def _destroy_container(self, record: ContainerRecord, jail_id: str) -> KillItem:
        """The container's item: ended only on the evidence of a second inspect, and never a
        container that is not the record's and the jail's."""
        try:
            return self._end_container(record, jail_id)
        except OciUnavailable as error:
            return _container_item(record, KillOutcome.FAILED, str(error))

    def _end_container(self, record: ContainerRecord, jail_id: str) -> KillItem:
        """`destroy`'s container item.

        Raises:
            OciUnavailable: the CLI could not be started.
        """
        before = self._standing(record, jail_id)
        match before:
            case Gone():
                return _container_item(
                    record, KillOutcome.ALREADY_GONE, "docker inspect found no such container"
                )
            case NotOurs(why=why) | Unknown(why=why):
                return _container_item(
                    record,
                    KillOutcome.FAILED,
                    f"not acted on, because it cannot be verified: {why}",
                )
            case Ours():
                pass
            case _ as unreachable:
                assert_never(unreachable)
        removed = self._run("rm", "-f", "--", record.container_id)
        after = self._standing(record, jail_id)
        match after:
            case Gone():
                return _container_item(
                    record,
                    KillOutcome.ENDED,
                    f"docker rm -f returned {removed.returncode}, and docker inspect then found "
                    "no such container",
                )
            case Ours() | NotOurs() | Unknown():
                return _container_item(
                    record,
                    KillOutcome.FAILED,
                    f"docker rm -f returned {removed.returncode} ({removed.stderr.strip()[:300]}) "
                    "and the container could not be found gone afterwards",
                )
            case _ as unreachable:
                assert_never(unreachable)

    def supervisor(self, jail: JailRecord) -> Supervisor | None:
        """`None`: no supervisor runs in a container yet (TASK-0079.10), so it can only be
        destroyed, and `Jail.start` is absent (SPEC.md section 9)."""
        del jail
        return None

    def reserve(self, jail: JailRecord, channel: str) -> Reservation:
        """Refused: the `oci` mechanism refuses a `Spec` that declares a channel, so there is none
        to reserve a socket for.

        Raises:
            ValueError: always.
        """
        raise ValueError(
            f"jail {jail.jail_id!r} cannot reserve a socket for channel {channel!r}: a container "
            "jail declares no channel (the channel directory is TASK-0079.10's)"
        )

    def endpoint(self, jail: JailRecord, process: ProcessRecord) -> str | None:
        """`None`: no process of a container jail has a channel."""
        del jail, process
        return None

    def ready(self, jail: JailRecord, process: ProcessRecord) -> bool:
        """`False`: a process with no channel is never ready, as the protocol says."""
        del jail, process
        return False

    def connect(self, jail: JailRecord, process: ProcessRecord) -> socket.socket:
        """Refused: the process was started with no channel.

        Raises:
            ValueError: always.
        """
        del jail
        raise ValueError(f"process {process.id} was started with no channel to connect to")


def _container_item(record: ContainerRecord, outcome: KillOutcome, detail: str) -> KillItem:
    return KillItem(kind="container", identity=record.container_id, outcome=outcome, detail=detail)


__all__ = (
    "DEFAULT_DOCKER",
    "DEFAULT_DOCKER_HOST",
    "JAIL_LABEL",
    "Gone",
    "NotOurs",
    "OciCreateFailed",
    "OciCreateRefused",
    "OciRuntime",
    "OciUnavailable",
    "Ours",
    "Standing",
    "Unknown",
    "create_args",
    "daemon_id_of",
    "standing",
)

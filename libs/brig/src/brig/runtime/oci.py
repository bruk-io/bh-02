"""`OciRuntime`: a container as a jail's instance, created and ended through the Docker daemon.

SPEC.md §8 (decision-202, decision-203), decision-0001's migration step 5. The `oci` mechanism
(`brig/mech/oci.py`) compiles a `Spec` to a `ContainerPlan`; this runtime makes the container from
it, identifies it, checks it and ends it. A container is created and ended through the daemon,
never by signalling a host process group.

**Its processes have an agent, found out at `create`** (decision-203). The container is made as the
supervisor's first (brig's supervisor as its PID 1, `brig/runtime/_oci_agent.py`): when `docker
start` answers that the interpreter is not in the image (exit code 127) it is removed and made again
as the exec variant (`--init`, idle), whose processes are started with `docker exec`
(`brig/runtime/_oci_exec.py`). `ContainerRecord.agent` says which. Either way the channel directory is
bind-mounted and each start's socket is dialled from the host through the verified dial.

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

from brig.core.runtime import Capability, ContainerAgent, ContainerPlan, RuntimeKind
from brig.run import _channels, _identity, _records
from brig.run._jail_dir import clear_earlier_records, make_channel_dir
from brig.run._supervised import LinkedSupervisor, namespaces_of
from brig.run._supervisor_link import SupervisorLink
from brig.run._tether import HeldTether
from brig.run.host import LaunchRefused
from brig.run.runtime import (
    ContainerRecord,
    Held,
    JailRecord,
    ProcessNamespaces,
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
from brig.runtime._oci_agent import (
    AgentStartFailed,
    StartVerdict,
    accept_hello,
    bind_rendezvous,
    container_state,
    missing_interpreter_reason,
    release_rendezvous,
    start_verdict,
    write_source,
)
from brig.runtime._oci_exec import ExecSupervisor
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
    """The container is the record's, carrying the jail's label. `running`: `State.Running`;
    `pid`: `State.Pid`, the host's pid of its PID 1 (0 when it is not running)."""

    running: bool
    pid: int = 0


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
        pid = entry["State"].get("Pid", 0)
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
    return Ours(running=running is True, pid=pid if type(pid) is int else 0)


def create_args(plan: ContainerPlan, jail_id: str, agent: ContainerAgent) -> tuple[str, ...]:
    """The arguments `docker` is run with to create the container for `plan` as the variant of
    `agent`: never pulls (`--pull never`), labels the container with the jail, then the variant's
    flags, the image and the variant's command. The environment is in the file the flags name, never
    here (law 9). Pure."""
    return (
        "create",
        "--pull",
        "never",
        "--label",
        f"{JAIL_LABEL}={jail_id}",
        *plan.create_flags(agent),
        plan.image,
        *plan.create_command(agent),
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
        its processes' agent found out (decision-203), and a tether watcher when `tether` is given.

        The container is made as the first of the plan's agents. For the supervisor that is: the
        program written to `<jail_dir>/oci-supervisor.py`, a listener bound at `<chan>/agent.sock`,
        the container created and started, the connection accepted from its PID 1 and its hello
        read. `docker start` answering that the interpreter is not in the image (exit code 127)
        removes the container and makes it again as the exec variant, idle under `--init`, and the
        record says why. `tether` is the read end of a pipe whose write end the caller keeps; the
        jail holds a duplicate (`Held`), so the caller may close its own once this returns. The env
        file is written, named by `--env-file` and removed before `docker create` is judged. If
        anything after a container exists fails, the container and the watcher are removed before
        the error is raised.

        Raises:
            OciCreateRefused: `jail` is not an `OCI` jail with a container plan, or has helpers
                or staged files.
            LaunchRefused: `jail.requires` names a capability this runtime lacks (it has none).
            TetherClosed: `tether` has already ended.
            JailDirInUse: `jail_dir` holds an earlier jail's records and something they name
                runs, or brig can't tell.
            OciUnavailable: the CLI could not be run or the daemon did not answer `docker info`.
            EnvNotRepresentable: a forwarded variable cannot be a line of the env file (it names
                the variable, never the value).
            OciCreateFailed: `docker create` or `docker start` failed, the container is not
                running right after it, or the supervisor never connected and spoke; carries
                docker's error, or the container's logs.
            OSError: `tether` is not open, or `jail_dir`, the channel directory, the env file, the
                supervisor's program or its socket could not be made.
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
            os.makedirs(jail_dir, mode=0o700, exist_ok=True)
            clear_earlier_records(jail_dir)
            make_channel_dir(jail_dir)
            made, agent, reason = self._make_agent_container(plan, jail_id, tether_fd)
        except BaseException:
            if hold is not None:
                hold.release()
            raise

        helper_pids = () if made.watcher is None else (made.watcher.pid,)
        helper_stamps = () if made.watcher is None else (_identity.start_stamp(made.watcher.pid),)
        return JailRecord(
            kind=self.kind,
            jail_id=jail_id,
            jail_dir=jail_dir,
            cwd=cwd,
            jail_env=frozendict(jail.env),
            wrap_prefix=None,
            helper_pids=helper_pids,
            helper_stamps=helper_stamps,
            namespaces=made.namespaces,
            container=ContainerRecord(
                container_id=made.container_id,
                daemon_id=daemon,
                agent=agent,
                agent_reason=reason,
                init_pid=made.init_pid,
            ),
            held=Held(wrap=jail.wrap, sensors=jail.sensors, tether=hold, link=made.link),
        )

    def _make_agent_container(
        self, plan: ContainerPlan, jail_id: str, tether_fd: int | None
    ) -> tuple[_Made, ContainerAgent, str]:
        """Make the container as each of the plan's agents in turn until one starts: the made
        container, the agent that holds it, and why it is not the supervisor when it is not.

        Raises:
            EnvNotRepresentable, OciCreateFailed, OciUnavailable, OSError: as `create`.
        """
        reason = missing_interpreter_reason(None, plan.image) if plan.interpreter is None else ""
        for agent in plan.agents():
            attempt = self._attempt(plan, agent, jail_id, tether_fd)
            match attempt:
                case _Made():
                    return attempt, agent, reason
                case _NoInterpreter():
                    reason = missing_interpreter_reason(plan.interpreter, plan.image)
                case _ as unreachable:
                    assert_never(unreachable)
        raise OciCreateFailed(
            f"no agent could be made for the image {plan.image!r}: {reason}"
        )  # pragma: no cover  (EXEC is last and never answers _NoInterpreter)

    def _attempt(
        self, plan: ContainerPlan, agent: ContainerAgent, jail_id: str, tether_fd: int | None
    ) -> _Made | _NoInterpreter:
        """One try at the container as the variant of `agent`: create it, start the tether
        watcher, `docker start`, and see the agent in. The supervisor's rendezvous and program are
        made first and removed after, whatever came of it.

        Raises:
            EnvNotRepresentable, OciCreateFailed, OciUnavailable, OSError: as `create`.
        """
        listener: socket.socket | None = None
        if agent is ContainerAgent.SUPERVISOR:
            write_source(plan.supervisor_source)
            listener = bind_rendezvous(plan.rendezvous)
        try:
            container_id = self._create_container(plan, agent, jail_id)
            watcher: subprocess.Popen[bytes] | None = None
            try:
                if tether_fd is not None:
                    watcher = self._start_watcher(container_id, tether_fd)
                started = self._run("start", container_id)
                if started.returncode != 0:
                    return self._start_failed(plan, agent, container_id, jail_id, started, watcher)
                init_pid = self._require_running(container_id, jail_id, plan, agent)
                if listener is None:
                    return _Made(container_id, watcher, None, None, init_pid)
                link, namespaces = self._see_supervisor_in(listener, container_id, init_pid)
                return _Made(container_id, watcher, link, namespaces, init_pid)
            except BaseException:
                self._abandon(container_id, watcher)
                raise
        finally:
            if listener is not None:
                release_rendezvous(listener, plan.rendezvous)

    def _start_failed(
        self,
        plan: ContainerPlan,
        agent: ContainerAgent,
        container_id: str,
        jail_id: str,
        started: _Done,
        watcher: subprocess.Popen[bytes] | None,
    ) -> _NoInterpreter:
        """`docker start` failed: if the supervisor's command is not in the image, abandon the
        container and say so (the caller tries the next agent); otherwise it is a failure, and the
        caller abandons the container.

        Raises:
            OciCreateFailed: any other failure.
            OciUnavailable: the CLI could not be started.
        """
        inspected = self._run("inspect", "--type", "container", container_id)
        state = container_state(inspected.stdout) if inspected.returncode == 0 else None
        verdict = start_verdict(started.returncode, state)
        if verdict is StartVerdict.NO_INTERPRETER and agent is ContainerAgent.SUPERVISOR:
            self._abandon(container_id, watcher)
            return _NoInterpreter()
        raise OciCreateFailed(
            f"docker start failed (status {started.returncode}) for the {agent.name.lower()} "
            f"variant of {plan.image!r}: {started.stderr.strip()[:500]}"
        )

    def _abandon(self, container_id: str, watcher: subprocess.Popen[bytes] | None) -> None:
        """Remove a container `create` is giving up on, and its tether watcher. Best effort: the
        error that sent us here is the one that is raised.

        Raises:
            OciUnavailable: the CLI could not be started.
        """
        self._remove(container_id)
        if watcher is not None:
            end_group("helper", watcher.pid, watcher.pid, _identity.start_stamp(watcher.pid))

    def _see_supervisor_in(
        self, listener: socket.socket, container_id: str, init_pid: int
    ) -> tuple[SupervisorLink, ProcessNamespaces]:
        """Accept the supervisor from the container's PID 1 and read its hello: its link, and what
        it found of the namespaces its processes could have (decision-195).

        Raises:
            OciCreateFailed: it never connected and spoke, with what `docker logs` said.
            OciUnavailable: the CLI could not be started.
        """

        def alive() -> bool:
            done = self._run("inspect", "--type", "container", container_id)
            state = container_state(done.stdout) if done.returncode == 0 else None
            return state is not None and state.status == "running"

        def unresponsive() -> None:
            with contextlib.suppress(OciUnavailable):
                self._remove(container_id)

        try:
            link, hello = accept_hello(
                listener, init_pid=init_pid, alive=alive, unresponsive=unresponsive
            )
        except AgentStartFailed as error:
            logs = self._run("logs", "--tail", "40", container_id)
            said = (logs.stderr + logs.stdout).strip()[-1500:]
            raise OciCreateFailed(
                f"brig's supervisor did not start in container {container_id[:12]}: {error}. Its "
                f"logs said: {said or 'nothing'}. Usual causes: an interpreter older than Python "
                "3.9, or a kernel without pidfd_open (Linux 5.3)"
            ) from error
        return link, namespaces_of(hello)

    def _require_running(
        self, container_id: str, jail_id: str, plan: ContainerPlan, agent: ContainerAgent
    ) -> int:
        """Ask once that the container started is running, and for the host's pid of its PID 1:
        under `--init` a command that is not in the image ends the container at once and `docker
        start` still returns 0, and a jail that does not run is no jail. One question, not a wait:
        a command that ends later reads gone by `alive`.

        Raises:
            OciCreateFailed: the container is not running.
            OciUnavailable: the CLI could not be started.
        """
        done = self._run("inspect", "--type", "container", container_id)
        found = standing(
            done.returncode, done.stdout, done.stderr, container_id=container_id, jail_id=jail_id
        )
        match found:
            case Ours(running=True, pid=pid) if pid > 0:
                return pid
            case Ours() | Gone() | NotOurs() | Unknown():
                raise OciCreateFailed(
                    f"the container is not running right after docker start; its command "
                    f"{' '.join(plan.create_command(agent))!r} may not be in the image "
                    f"{plan.image!r}"
                )
            case _ as unreachable:
                assert_never(unreachable)

    def _create_container(self, plan: ContainerPlan, agent: ContainerAgent, jail_id: str) -> str:
        """Write the env file, `docker create` the variant of `agent`, remove the file; the
        container's full id.

        Raises:
            EnvNotRepresentable: a forwarded variable cannot be a line of the env file.
            OciCreateFailed: `docker create` failed.
            OciUnavailable: the CLI could not be started.
            OSError: the env file could not be written.
        """
        text = plan.env_file_text(os.environ)
        try:
            _write_env_file(plan.env_file, text)
            done = self._run(*create_args(plan, jail_id, agent))
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
        """The processes `jail` holds, by the records it holds, then every other readable record
        under `<jail_dir>/procs`, each in start order (as `HostRuntime.processes`)."""
        held = {process.id for process in jail.processes}
        return (
            *jail.processes,
            *(p for p in _records.scan(jail.jail_dir).records if p.id not in held),
        )

    def tethered(self, jail: JailRecord) -> bool | None:
        """`None`: this runtime records nothing apart from the dict, so a rehydrated container jail
        cannot say it was created untethered and has no `start` (decision-203)."""
        del jail
        return None

    def process_alive(self, jail: JailRecord, process: ProcessRecord) -> bool:
        """Whether `process`'s leader holds its identity, by the host's own reading of it: a
        recycled pid and a zombie read gone (decision-155, decision-171)."""
        del jail
        return _identity.identity_holds(process.pid, process.start_time)

    def destroy(self, jail: JailRecord, *, grace: float = DEFAULT_GRACE_S) -> KillReport:
        """`docker rm -f` the container, verified by `docker inspect`; then the tether watcher.
        One `container` item and one `helper` item. Total: raises nothing from an item. A
        supervisor's link is closed after the removal.

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
        if jail.held is not None and jail.held.link is not None:
            jail.held.link.close()
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
        """The agent of `jail`'s processes (decision-203): a `LinkedSupervisor` over the link to
        brig's supervisor when the container's PID 1 is one, an `ExecSupervisor` when its agent is
        `docker exec`, and `None` for a jail whose agent is not known here (rehydrated: the link
        was a socket, and the exec agent is the creating process's knowledge), which can only be
        destroyed, and whose `Jail.start` is absent (SPEC.md section 9)."""
        container = jail.container
        if container is None:
            return None
        link = None if jail.held is None else jail.held.link
        if link is not None:
            return LinkedSupervisor(jail, link)
        if container.agent is ContainerAgent.EXEC:
            return ExecSupervisor(jail, self.docker, self._cli_env())
        return None

    def reserve(self, jail: JailRecord, channel: str) -> Reservation:
        """A fresh socket in the jail's channel directory for `channel`, which the caller has
        checked the jail declares (decision-184): the same `<chan>/<16 hex>.sock` a process binds
        and the host dials. Makes nothing: the process binds it."""
        return _channels.reserve(jail, channel)

    def endpoint(self, jail: JailRecord, process: ProcessRecord) -> str | None:
        """The path to dial `process`'s socket at: the one it binds, in the directory bind-mounted
        into the container (decision-203). `None` for a process started with no channel."""
        del jail
        return _channels.endpoint_of(process)

    def ready(self, jail: JailRecord, process: ProcessRecord) -> bool:
        """Whether `connect` to `process`'s socket succeeds now, closed at once; never whether the
        path exists. `False` for a process with no channel and while nothing listens.

        Raises:
            EndpointRefused: what is at its socket is not its own listener (decision-185).
        """
        del jail
        return _channels.is_ready(process)

    def connect(self, jail: JailRecord, process: ProcessRecord) -> socket.socket:
        """A connected socket to `process`'s reserved socket through the verified dial
        (decision-185): the listener is a process of the started process's group, whose leader
        holds its recorded identity, as the kernel numbers it in the host's pid namespace.

        Raises:
            ValueError: `process` was started with no channel.
            EndpointRefused: the path is a link or not a socket, or the peer is not `process`'s.
            OSError: nothing listens there yet.
        """
        del jail
        return _channels.connect_to(process)


@dataclass(frozen=True, slots=True)
class _Made:
    """A container an attempt made and started: its id, its tether watcher, and for the
    supervisor's variant the link to it, what it found of namespaces, and in either the host's pid
    of the container's PID 1."""

    container_id: str
    watcher: subprocess.Popen[bytes] | None
    link: SupervisorLink | None
    namespaces: ProcessNamespaces | None
    init_pid: int


@dataclass(frozen=True, slots=True)
class _NoInterpreter:
    """An attempt at the supervisor's variant found the interpreter is not in the image; the
    container was removed."""


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

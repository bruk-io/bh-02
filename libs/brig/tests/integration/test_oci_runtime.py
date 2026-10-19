"""`OciRuntime` against the Docker daemon of the machine (decision-202, TASK-0079.09).

A container is created, checked and destroyed through the daemon, identified by a `brig.jail` label
and the daemon's id, with `DOCKER_HOST` from the runtime object and never a record, and its
environment in a mode-0600 file that is gone after the create and never on a command line (law 9).

Every observation here is made through `tests/oci_jail.py`'s own door to the daemon (`docker
inspect`, `docker exec`), not through the runtime under test. The tier skips, naming `docker info`,
where the daemon does not answer (`needs_docker`).
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import threading
import uuid
from collections.abc import Callable
from typing import Any

import pytest

from brig.core import EnvPolicy, Limits, Spec
from brig.run import Jail, KillOutcome, RuntimeKind, TetherClosed
from brig.runtime.oci import (
    JAIL_LABEL,
    OciCreateFailed,
    OciRuntime,
    OciUnavailable,
)
from tests.conftest import NewJailDir
from tests.oci_jail import IMAGE, allow_list, container_of, docker, inspect
from tests.oci_jail import make as oci_make

pytestmark = pytest.mark.integration

Make = Callable[..., Jail]


def _containers_labelled(jail_id: str) -> list[str]:
    done = docker("ps", "-a", "--no-trunc", "--filter", f"label={JAIL_LABEL}={jail_id}", "-q")
    return done.stdout.split()


def _item(report: Any, kind: str) -> Any:
    (item,) = [item for item in report.items if item.kind == kind]
    return item


# --- AC1: the container is what the Spec compiled to ---------------------------------------


def test_the_container_is_labelled_and_has_the_flags_the_spec_compiled(
    make_oci_jail: Make, new_jail_dir: NewJailDir
) -> None:
    reference, workspace = new_jail_dir(), new_jail_dir()
    spec = Spec(
        fs=allow_list(read_allows=(reference,), write_allows=(workspace,)),
        limits=Limits(cpu_seconds=9),
    )
    jail = make_oci_jail(spec)
    entry = inspect(container_of(jail))
    assert entry is not None
    config, host = entry["Config"], entry["HostConfig"]

    assert config["Labels"][JAIL_LABEL] == jail.jail_id
    assert config["User"] == str(os.geteuid())  # the embedder's uid, so no file is root's
    assert host["Init"] is True
    assert host["NetworkMode"] == "none"
    assert host["ReadonlyRootfs"] is True
    assert host["CapDrop"] == ["ALL"] and host["SecurityOpt"] == ["no-new-privileges"]
    assert host["Ulimits"] == [{"Name": "cpu", "Hard": 10, "Soft": 9}]
    chan = os.path.realpath(jail.jail_dir) + "/chan"
    assert {m["Destination"]: (m["Type"], m["Source"], m["RW"]) for m in entry["Mounts"]} == {
        reference: ("bind", reference, False),
        workspace: ("bind", workspace, True),
        chan: ("bind", chan, True),  # decision-203: the runtime's channel directory, always
    }
    assert (config["Image"], config["Cmd"]) == (IMAGE, ["sleep", "infinity"])
    assert entry["State"]["Running"] is True


def test_the_report_of_a_container_jail_is_the_one_the_mechanism_and_runtime_graded(
    make_oci_jail: Make,
) -> None:
    jail = make_oci_jail()
    axes = jail.report.axes
    assert {axis.value: graded.grade.value for axis, graded in axes.items()} == {
        "fs_read": "best_effort",
        "fs_write": "enforced",
        "network": "enforced",
        "limits": "unenforced",
        "env": "enforced",
        "channel_exclusivity": "unenforced",
        "control": "enforced",
    }


# --- AC1, law 9: the environment is a file ------------------------------------------------


def test_the_environment_in_the_container_is_what_the_spec_allowed_and_nothing_else(
    make_oci_jail: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRIG_OCI_ALLOWED", 'allowed value, with "quotes" and $HOME')
    monkeypatch.setenv("BRIG_OCI_NOT_ALLOWED", "must not arrive")
    monkeypatch.delenv("BRIG_OCI_ABSENT", raising=False)
    spec = Spec(
        fs=allow_list(),
        env=EnvPolicy(
            allow_names=("BRIG_OCI_ALLOWED", "BRIG_OCI_ABSENT"),
            set=(("BRIG_OCI_SET", "a literal"),),
        ),
    )
    jail = make_oci_jail(spec)
    config_env = inspect(container_of(jail))["Config"]["Env"]  # type: ignore[index]
    image_env = json.loads(
        docker("image", "inspect", IMAGE, "--format", "{{json .Config.Env}}").stdout
    )

    assert set(config_env) == set(image_env) | {
        'BRIG_OCI_ALLOWED=allowed value, with "quotes" and $HOME',
        "BRIG_OCI_SET=a literal",
    }
    assert not [entry for entry in config_env if "NOT_ALLOWED" in entry or "ABSENT" in entry]


def _ps_lines() -> list[str]:
    out = subprocess.run(
        ["/bin/ps", "-Ao", "args="], capture_output=True, text=True, check=False
    ).stdout
    return out.splitlines()


def test_no_value_of_the_environment_is_ever_in_an_argv(
    make_oci_jail: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The claim is an absence, so the test makes sure it could have seen the presence: every
    `docker` the runtime runs is recorded at the OS boundary (`subprocess.run`) and the host's own
    process table is polled while a jail is created, and both must have seen the `docker create`
    of THIS jail (its label) before a value's absence from them counts."""
    secret, literal = f"s3cr3t-{uuid.uuid4().hex}", f"lit-{uuid.uuid4().hex}"
    monkeypatch.setenv("BRIG_OCI_TOKEN", secret)
    spec = Spec(
        fs=allow_list(),
        env=EnvPolicy(allow_names=("BRIG_OCI_TOKEN",), set=(("BRIG_OCI_SET", literal),)),
    )
    argvs: list[list[str]] = []
    real_run = subprocess.run

    def recording(argv: Any, *args: Any, **kwargs: Any) -> Any:
        argvs.append([str(word) for word in argv])
        return real_run(argv, *args, **kwargs)

    seen_in_ps: list[str] = []
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            seen_in_ps.extend(line for line in _ps_lines() if "docker" in line)

    controlled = False
    for _ in range(12):
        jail_id = f"oci-argv-{uuid.uuid4().hex[:8]}"
        argvs.clear()
        seen_in_ps.clear()
        stop.clear()
        poller = threading.Thread(target=poll, daemon=True)
        with monkeypatch.context() as scoped:
            scoped.setattr(subprocess, "run", recording)
            poller.start()
            try:
                make_oci_jail(spec, jail_id=jail_id)
            finally:
                stop.set()
                poller.join(timeout=5)
        create = [argv for argv in argvs if "create" in argv and f"{JAIL_LABEL}={jail_id}" in argv]
        assert len(create) == 1, "the runtime's docker create was not recorded"
        assert "--env-file" in create[0] and "-e" not in create[0] and "--env" not in create[0]
        assert not [argv for argv in argvs if secret in " ".join(argv) or literal in " ".join(argv)]
        assert not [line for line in seen_in_ps if secret in line or literal in line]
        if [line for line in seen_in_ps if f"{JAIL_LABEL}={jail_id}" in line]:
            controlled = True
            break
    assert controlled, "the process-table poll never saw a docker create, so it proved nothing"


def test_the_env_file_is_mode_0600_while_docker_reads_it_and_gone_after(
    make_oci_jail: Make, monkeypatch: pytest.MonkeyPatch, new_jail_dir: NewJailDir
) -> None:
    monkeypatch.setenv("BRIG_OCI_TOKEN", "in-the-file")
    spec = Spec(fs=allow_list(), env=EnvPolicy(allow_names=("BRIG_OCI_TOKEN",)))
    jail_dir = new_jail_dir()
    at_create: list[tuple[str, int, int, str]] = []
    real_run = subprocess.run

    def looking(argv: Any, *args: Any, **kwargs: Any) -> Any:
        words = [str(word) for word in argv]
        if "create" in words and "--env-file" in words:
            path = words[words.index("--env-file") + 1]
            info = os.lstat(path)
            with open(path, encoding="utf-8") as env_file:
                at_create.append((path, stat.S_IMODE(info.st_mode), info.st_uid, env_file.read()))
        return real_run(argv, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(subprocess, "run", looking)
        make_oci_jail(spec, jail_dir=jail_dir)

    ((path, mode, owner, content),) = at_create
    assert path == os.path.join(jail_dir, "oci.env")
    assert (mode, owner, content) == (0o600, os.geteuid(), "BRIG_OCI_TOKEN=in-the-file\n")
    assert not os.path.lexists(path) and os.listdir(jail_dir) == ["chan"]


def test_a_create_that_fails_leaves_no_env_file_and_no_container(
    make_oci_jail: Make, monkeypatch: pytest.MonkeyPatch, new_jail_dir: NewJailDir
) -> None:
    monkeypatch.setenv("BRIG_OCI_TOKEN", "must-not-stay")
    spec = Spec(fs=allow_list(), env=EnvPolicy(allow_names=("BRIG_OCI_TOKEN",)))
    jail_dir, jail_id = new_jail_dir(), f"oci-fail-{uuid.uuid4().hex[:8]}"
    with pytest.raises(OciCreateFailed, match="docker create failed") as caught:
        oci_make(spec, jail_dir, jail_id=jail_id, image="brig-no-such-image:0")
    assert "must-not-stay" not in str(caught.value)
    assert os.listdir(jail_dir) == ["chan"]
    assert _containers_labelled(jail_id) == []


def test_an_env_file_path_that_is_a_link_is_replaced_never_written_through(
    make_oci_jail: Make, monkeypatch: pytest.MonkeyPatch, new_jail_dir: NewJailDir
) -> None:
    """A stale file or a planted link at the env file's path: the secret goes to a fresh file."""
    monkeypatch.setenv("BRIG_OCI_TOKEN", "secret-value")
    jail_dir = new_jail_dir()
    victim = os.path.join(jail_dir, "victim")
    with open(victim, "w", encoding="utf-8") as victim_file:
        victim_file.write("untouched")
    os.symlink(victim, os.path.join(jail_dir, "oci.env"))
    spec = Spec(fs=allow_list(), env=EnvPolicy(allow_names=("BRIG_OCI_TOKEN",)))
    make_oci_jail(spec, jail_dir=jail_dir)
    with open(victim, encoding="utf-8") as victim_file:
        assert victim_file.read() == "untouched"
    assert sorted(os.listdir(jail_dir)) == ["chan", "victim"]


# --- AC2: create, check, destroy -----------------------------------------------------------


def test_destroy_is_docker_rm_f_and_inspect_then_cannot_find_the_container(
    make_oci_jail: Make,
) -> None:
    jail = make_oci_jail()
    container = container_of(jail)
    assert jail.alive() and inspect(container) is not None

    report = jail.destroy()

    item = _item(report, "container")
    assert (item.identity, item.outcome) == (container, KillOutcome.ENDED)
    assert "docker inspect then found no such container" in item.detail
    assert inspect(container) is None  # the test's own door: it is gone
    assert not jail.alive()
    again = _item(jail.destroy(), "container")
    assert again.outcome is KillOutcome.ALREADY_GONE


def test_alive_follows_the_container_whoever_ends_it(make_oci_jail: Make) -> None:
    stopped, removed = make_oci_jail(), make_oci_jail()
    assert stopped.alive() and removed.alive()
    assert docker("stop", "--time", "0", container_of(stopped)).returncode == 0
    assert not stopped.alive()  # exists, not running
    assert docker("rm", "-f", container_of(removed)).returncode == 0
    assert not removed.alive()  # no such container
    assert _item(stopped.destroy(), "container").outcome is KillOutcome.ENDED
    assert _item(removed.destroy(), "container").outcome is KillOutcome.ALREADY_GONE


def test_a_container_jail_holds_no_process_until_one_is_started(make_oci_jail: Make) -> None:
    """decision-203: a container jail made here offers `start` (its agent is `docker exec` for this
    image), and holds nothing until one is started. Its dict names no supervisor: the agent is the
    creating process's knowledge, as a supervised jail's namespaces are."""
    jail = make_oci_jail()
    assert jail.processes() == () and jail.instance_group is None
    assert hasattr(jail, "start") and hasattr(jail, "probe")
    assert jail.to_dict()["runtime"] == "OCI" and jail.to_dict()["supervisor"] is None


def test_the_container_survives_the_runtime_object_and_a_rehydrated_jail_destroys_it(
    make_oci_jail: Make,
) -> None:
    jail = make_oci_jail()
    container = container_of(jail)
    saved = json.loads(json.dumps(jail.to_dict()))
    assert saved["container"]["id"] == container and set(saved["container"]) == {"id", "daemon"}

    rehydrated = Jail.from_dict(saved, runtimes={RuntimeKind.OCI: OciRuntime()})

    assert rehydrated.alive() and inspect(container) is not None
    assert not hasattr(rehydrated, "start")
    assert _item(rehydrated.destroy(), "container").outcome is KillOutcome.ENDED
    assert inspect(container) is None


# --- AC2: the identity is checked, and the daemon is the runtime object's -------------------


def test_an_inherited_docker_host_or_context_does_not_move_the_runtime_but_does_move_the_cli(
    make_oci_jail: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent/docker.sock")
    monkeypatch.setenv("DOCKER_CONTEXT", "nonexistent")
    # The control: the ambient settings really do redirect a bare CLI call.
    assert docker("info", "--format", "{{.ID}}").returncode != 0
    jail = make_oci_jail()
    assert jail.alive() and inspect(container_of(jail)) is None  # the test's CLI is redirected too
    monkeypatch.delenv("DOCKER_HOST")
    monkeypatch.delenv("DOCKER_CONTEXT")
    assert inspect(container_of(jail)) is not None  # ... and the container is on the real daemon


def test_a_runtime_for_another_daemon_does_not_touch_the_container(make_oci_jail: Make) -> None:
    jail = make_oci_jail()
    container = container_of(jail)
    elsewhere = OciRuntime(docker_host="unix:///nonexistent/docker.sock")
    stranger = Jail.from_dict(jail.to_dict(), runtimes={RuntimeKind.OCI: elsewhere})

    item = _item(stranger.destroy(), "container")

    assert item.outcome is KillOutcome.FAILED and "did not answer" in item.detail
    with pytest.raises(OciUnavailable, match="did not answer"):
        stranger.alive()
    assert inspect(container)["State"]["Running"] is True  # type: ignore[index]
    # The control: the runtime of the daemon that made it ends it.
    assert _item(jail.destroy(), "container").outcome is KillOutcome.ENDED


def test_a_record_of_another_daemons_container_is_not_acted_on(make_oci_jail: Make) -> None:
    jail = make_oci_jail()
    container = container_of(jail)
    forged = jail.to_dict()
    forged["container"]["daemon"] = "someone-elses-daemon"
    foreign = Jail.from_dict(forged, runtimes={RuntimeKind.OCI: OciRuntime()})

    item = _item(foreign.destroy(), "container")

    assert item.outcome is KillOutcome.FAILED
    assert "someone-elses-daemon" in item.detail and "pass the runtime of the daemon" in item.detail
    with pytest.raises(OciUnavailable, match="someone-elses-daemon"):
        foreign.alive()
    assert inspect(container)["State"]["Running"] is True  # type: ignore[index]


def test_a_container_that_carries_another_label_is_not_destroyed_and_one_that_carries_ours_is(
    make_oci_jail: Make,
) -> None:
    """The record names a container id; the label is the second half of the identity. A container
    with that id and another jail's label is left alone, and the same record with the right label is
    the control that the refusal is the label's."""
    jail = make_oci_jail()
    saved = jail.to_dict()
    other = docker(
        "create", "--pull", "never", "--label", f"{JAIL_LABEL}=someone-else", IMAGE, "true"
    )
    other_id = other.stdout.strip()
    try:
        assert other.returncode == 0 and len(other_id) == 64
        record = {**saved, "container": {"id": other_id, "daemon": saved["container"]["daemon"]}}
        mine = Jail.from_dict(record, runtimes={RuntimeKind.OCI: OciRuntime()})

        refused = _item(mine.destroy(), "container")

        assert refused.outcome is KillOutcome.FAILED and "someone-else" in refused.detail
        assert inspect(other_id) is not None
        # The control: label it as this jail's and the same record is destroyed.
        docker("rm", "-f", other_id)
        again = docker(
            "create", "--pull", "never", "--label", f"{JAIL_LABEL}={jail.jail_id}", IMAGE, "true"
        )
        other_id = again.stdout.strip()
        ours = Jail.from_dict(
            {**saved, "container": {"id": other_id, "daemon": saved["container"]["daemon"]}},
            runtimes={RuntimeKind.OCI: OciRuntime()},
        )
        assert _item(ours.destroy(), "container").outcome is KillOutcome.ENDED
        assert inspect(other_id) is None
    finally:
        docker("rm", "-f", other_id)


def test_a_record_naming_a_container_that_is_not_there_reads_already_gone(
    make_oci_jail: Make,
) -> None:
    jail = make_oci_jail()
    ghost = jail.to_dict()
    ghost["container"]["id"] = "0" * 64
    gone = Jail.from_dict(ghost, runtimes={RuntimeKind.OCI: OciRuntime()})
    assert not gone.alive()
    assert _item(gone.destroy(), "container").outcome is KillOutcome.ALREADY_GONE


# --- refusals at create ---------------------------------------------------------------------


def test_a_closed_tether_is_refused_before_anything_is_made(make_oci_jail: Make) -> None:
    read_end, write_end = os.pipe()
    os.close(write_end)
    jail_id = f"oci-closed-{uuid.uuid4().hex[:8]}"
    try:
        with pytest.raises(TetherClosed):
            make_oci_jail(jail_id=jail_id, tether=read_end)
    finally:
        os.close(read_end)
    assert _containers_labelled(jail_id) == []


def test_a_start_that_fails_removes_the_container_and_the_watcher_before_it_raises(
    monkeypatch: pytest.MonkeyPatch, new_jail_dir: NewJailDir
) -> None:
    """`docker create` and `docker start` succeeded and the container is not running (the command is
    not in the image, so `--init` ends it at once): the container is removed and the tether watcher
    ended before the error is raised."""
    import dataclasses
    import sys

    from brig.mech import Oci
    from brig.run import build_compile_ctx
    from brig.stack import Stack
    from tests import oci_jail
    from tests.supervised_jail import process_state, until

    oci_jail.needs_docker()
    spec = Spec(fs=allow_list())
    jail_dir = new_jail_dir()
    jail_id = f"oci-nostart-{uuid.uuid4().hex[:8]}"
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
    compiled = Stack([Oci(IMAGE, interpreter=None)]).compile(spec, ctx=ctx)
    assert compiled.container is not None
    broken = dataclasses.replace(
        compiled, container=dataclasses.replace(compiled.container, command=("/no/such/program",))
    )
    watchers: list[subprocess.Popen[bytes]] = []
    real_start = OciRuntime._start_watcher

    def spy(self: OciRuntime, container_id: str, tether: int) -> subprocess.Popen[bytes]:
        watchers.append(real_start(self, container_id, tether))
        return watchers[-1]

    monkeypatch.setattr(OciRuntime, "_start_watcher", spy)
    read_end, write_end = os.pipe()
    try:
        with pytest.raises(OciCreateFailed, match="not running right after docker start"):
            OciRuntime().create(
                broken, cwd="/", jail_id=jail_id, jail_dir=jail_dir, tether=read_end
            )
        assert _containers_labelled(jail_id) == []
        assert os.listdir(jail_dir) == ["chan"]
        (watcher,) = watchers  # it was started, so its ending below is the failure path's doing
        assert until(lambda: process_state(watcher.pid) in ("gone", "Z"), 5.0)
    finally:
        os.close(read_end)
        os.close(write_end)

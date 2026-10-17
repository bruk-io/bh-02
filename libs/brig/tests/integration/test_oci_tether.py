"""A tethered container jail ends when its embedder is gone, `SIGKILL` included (decision-202).

SPEC.md §8 (decision-167's idea, a container's shape). `Jail.create(..., tether=fd)` takes the read
end of a pipe whose write end the embedder keeps and nothing else holds. A host watcher reads it to
end-of-file, which is every write end closed (the embedder closed it, or the kernel did because the
embedder died), and then runs `docker rm -f` on the container. The watcher cannot report, so the proof
that it works is the container gone, read from the daemon by the test's own door (`docker inspect`),
against a stand-in embedder process killed with `SIGKILL`.

Each claim has its control in the same test: a second embedder that is still alive keeps its
container, and an untethered jail outlives the same kill.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator

import pytest

from brig.core import EnvPolicy, Spec
from brig.run import Jail, KillOutcome
from tests.oci_jail import allow_list, container_of, docker, inspect, new_jail_dir
from tests.supervised_jail import running_with, until

pytestmark = pytest.mark.integration

Make = Callable[..., Jail]

#: A stand-in embedder: creates a container jail (tethered or not), prints its container's id, and
#: waits to be killed. The write end of the tether is held by this process alone.
_EMBEDDER = """
import os, sys, time
from brig.core import FsPolicy, ReadModel, Spec
from brig.mech import Oci
from brig.run import Jail, build_compile_ctx
from brig.runtime.oci import OciRuntime
from brig.stack import Stack

jail_dir, jail_id, tethered, image = sys.argv[1:5]
spec = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST))
ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
compiled = Stack([Oci(image)]).compile(spec, ctx=ctx)
read_end, write_end = os.pipe()
jail = Jail.create(
    compiled, runtime=OciRuntime(), cwd="/", jail_id=jail_id, jail_dir=jail_dir,
    **({"tether": read_end} if tethered == "1" else {}),
)
os.close(read_end)
print(jail.to_dict()["container"]["id"], flush=True)
time.sleep(600)
"""

_GONE_WITHIN_S = 30.0


@pytest.fixture
def embedders(run_id: str) -> Iterator[Callable[..., tuple[subprocess.Popen[str], str]]]:
    """`start(tethered=...)` is a stand-in embedder with a container jail, and its container's id.
    Every embedder is killed and every container removed afterwards."""
    from tests import oci_jail

    oci_jail.needs_docker()
    started: list[tuple[subprocess.Popen[str], str]] = []
    directories: list[str] = []

    def start(*, tethered: bool) -> tuple[subprocess.Popen[str], str]:
        directories.append(new_jail_dir())
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                _EMBEDDER,
                directories[-1],
                f"oci-{run_id}-{uuid.uuid4().hex[:8]}",
                "1" if tethered else "0",
                oci_jail.IMAGE,
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert process.stdout is not None
        container = process.stdout.readline().strip()
        assert len(container) == 64, f"the stand-in embedder printed {container!r}"
        started.append((process, container))
        return process, container

    yield start
    for process, container in started:
        process.kill()
        process.wait()
        docker("rm", "-f", "--", container)
    for directory in directories:
        shutil.rmtree(directory, ignore_errors=True)


def _running(container: str) -> bool:
    entry = inspect(container)
    return entry is not None and entry["State"]["Running"] is True


def test_a_tethered_container_is_removed_when_its_embedder_is_killed_and_a_live_ones_is_kept(
    embedders: Callable[..., tuple[subprocess.Popen[str], str]],
) -> None:
    doomed, doomed_container = embedders(tethered=True)
    live, live_container = embedders(tethered=True)
    assert _running(doomed_container) and _running(live_container)

    doomed.send_signal(signal.SIGKILL)
    doomed.wait()

    assert until(lambda: inspect(doomed_container) is None, _GONE_WITHIN_S), (
        "the container outlived its SIGKILLed embedder"
    )
    # The control: the other embedder is alive, so its tether is open and its container is kept.
    assert _running(live_container)
    time.sleep(1.0)
    assert _running(live_container)
    # ... and it goes the same way when its embedder does.
    live.send_signal(signal.SIGKILL)
    live.wait()
    assert until(lambda: inspect(live_container) is None, _GONE_WITHIN_S)


def test_an_untethered_container_outlives_its_killed_embedder(
    embedders: Callable[..., tuple[subprocess.Popen[str], str]],
) -> None:
    """The control for the claim above: without the tether nothing ends the container, which is what
    makes the removal the tether's and not the embedder's death alone."""
    process, container = embedders(tethered=False)
    process.send_signal(signal.SIGKILL)
    process.wait()
    time.sleep(2.0)
    assert _running(container)


def test_closing_the_tether_without_a_kill_removes_the_container_too(make_oci_jail: Make) -> None:
    read_end, write_end = os.pipe()
    try:
        jail = make_oci_jail(tether=read_end)
    finally:
        os.close(read_end)  # the jail holds its own duplicate until the watcher has it
    container = container_of(jail)
    assert _running(container)
    os.close(write_end)
    assert until(lambda: inspect(container) is None, _GONE_WITHIN_S)
    report = jail.destroy()
    assert {item.kind: item.outcome for item in report.items} == {
        "container": KillOutcome.ALREADY_GONE,
        "helper": KillOutcome.ALREADY_GONE,
    }


def test_destroy_ends_the_watcher_and_closing_the_tether_afterwards_removes_nothing(
    make_oci_jail: Make,
) -> None:
    read_end, write_end = os.pipe()
    try:
        jail = make_oci_jail(tether=read_end)
    finally:
        os.close(read_end)
    container = container_of(jail)
    marker = f"brig-oci-watcher /usr/bin/docker {container}"
    assert len(running_with(marker)) == 1, "the watcher is the jail's one helper and it runs"

    report = jail.destroy()

    assert {item.kind: item.outcome for item in report.items} == {
        "container": KillOutcome.ENDED,
        "helper": KillOutcome.ENDED,
    }
    assert until(lambda: not running_with(marker))
    # Closing the tether now finds no watcher to act: a container made after is not touched.
    other = docker("create", "--pull", "never", "--label", f"brig.jail=oci-bystander-{container[:8]}",
                   "ubuntu:24.04", "true")  # fmt: skip
    os.close(write_end)
    time.sleep(1.0)
    try:
        assert inspect(other.stdout.strip()) is not None
    finally:
        docker("rm", "-f", "--", other.stdout.strip())


def test_the_watcher_gets_the_daemon_and_the_cli_settings_and_nothing_of_the_creators_environment(
    make_oci_jail: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRIG_OCI_CREATOR_SECRET", "creator-only")
    read_end, write_end = os.pipe()
    try:
        jail = make_oci_jail(
            Spec(fs=allow_list(), env=EnvPolicy(allow_names=("BRIG_OCI_CREATOR_SECRET",))),
            tether=read_end,
        )
    finally:
        os.close(read_end)
    try:
        (pid,) = jail.to_dict()["helper_pids"]
        with open(f"/proc/{pid}/environ", "rb") as environ:
            raw = environ.read()
        names = {entry.split(b"=", 1)[0].decode() for entry in raw.split(b"\0") if entry}
        assert "DOCKER_HOST" in names
        assert names <= {
            "PATH",
            "HOME",
            "DOCKER_CONFIG",
            "DOCKER_CERT_PATH",
            "DOCKER_TLS_VERIFY",
            "DOCKER_HOST",
        }
        assert b"creator-only" not in raw
        # the control: the variable is set in this process, the creator
        assert os.environ["BRIG_OCI_CREATOR_SECRET"] == "creator-only"
    finally:
        os.close(write_end)

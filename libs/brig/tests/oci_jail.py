"""Helpers for tests that run a real container jail (decision-202, TASK-0079.09).

A jail here is `Stack([Oci(IMAGE)])` compiled for an allowlist `Spec`, created through
`OciRuntime` against the Docker daemon of the machine the tests run on. Everything a test learns
about it, it learns from the daemon through the CLI itself (`docker inspect`, `docker exec`), not
through the runtime under test: an observation made with the code under test is not an observation
(WORKFLOW.md, evidence rules). `needs_docker` is the skip, naming `docker info`.

The leak check for containers (`tests/conftest.py`: "containers (M10)") is `leaked_containers`:
every jail a test makes carries the run's token in its id, so a container labelled with it that
outlives the session is a leak, found without any test registering it.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import os
import subprocess
import sys
import tempfile
from typing import Any

import pytest

from brig.core import FsPolicy, ReadModel, Spec
from brig.mech import Oci
from brig.run import Jail, build_compile_ctx
from brig.runtime.oci import DEFAULT_DOCKER, JAIL_LABEL, OciRuntime
from brig.stack import Stack

#: The image the tier uses. It is cached on the machines the tier runs on and the runtime never
#: pulls, so the tier pulls nothing either: a missing image is a visible skip.
IMAGE = "ubuntu:24.04"


def docker(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    """`docker *args` as the test's own door to the daemon, outside the runtime under test."""
    return subprocess.run(
        [DEFAULT_DOCKER, *args],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
    )


@functools.cache
def _why_not() -> str | None:
    """Why this machine cannot run the container tier, or `None`: asked once."""
    if not os.path.exists(DEFAULT_DOCKER):
        return f"{DEFAULT_DOCKER} is not there; the container tier needs the docker CLI"
    try:
        info = docker("info", "--format", "{{.ID}}", timeout=30.0)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"`docker info` could not be run: {error}"
    if info.returncode != 0:
        return (
            f"`docker info` did not answer (status {info.returncode}): {info.stderr.strip()[:200]}"
        )
    if docker("image", "inspect", IMAGE).returncode != 0:
        return f"the image {IMAGE} is not present, and the tier pulls nothing (`docker image ls`)"
    return None


def needs_docker() -> None:
    """Skip, visibly and by name, where there is no Docker daemon to run a container jail on."""
    reason = _why_not()
    if reason is not None:
        pytest.skip(f"a container jail needs a Docker daemon: {reason}")


def inspect(container_id: str) -> dict[str, Any] | None:
    """`docker inspect` of a container as the test sees it, or `None` when there is none."""
    done = docker("inspect", "--type", "container", container_id)
    if done.returncode != 0:
        return None
    (entry,) = json.loads(done.stdout)
    assert isinstance(entry, dict)
    return entry


def exec_in(container_id: str, script: str) -> subprocess.CompletedProcess[str]:
    """`script` run with `sh -c` inside the container by `docker exec`, the test's own door."""
    return docker("exec", container_id, "sh", "-c", script)


def new_jail_dir() -> str:
    return tempfile.mkdtemp(prefix="bg-oci-", dir="/tmp")


def allow_list(**fs: Any) -> FsPolicy:
    return FsPolicy(read_model=ReadModel.ALLOW_LIST, **fs)


def make(
    spec: Spec,
    jail_dir: str,
    *,
    jail_id: str,
    tether: int | None = None,
    runtime: OciRuntime | None = None,
    image: str = IMAGE,
    euid: int | None = None,
) -> Jail:
    """A container jail for `spec` made by `OciRuntime` (or `runtime`). `euid` stands in for the
    embedder's uid in the compile context, which is the real one otherwise."""
    ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
    if euid is not None:
        ctx = dataclasses.replace(ctx, euid=euid)
    compiled = Stack([Oci(image)]).compile(spec, ctx=ctx)
    return Jail.create(
        compiled,
        runtime=OciRuntime() if runtime is None else runtime,
        cwd="/",
        jail_id=jail_id,
        jail_dir=jail_dir,
        tether=tether,
    )


def container_of(jail: Jail) -> str:
    """The container's full id, from the jail's own dict."""
    record = jail.to_dict()["container"]
    assert record is not None
    return str(record["id"])


def leaked_containers(token: str) -> list[str]:
    """Every container whose jail label carries the run's `token` (the ids tests make carry it),
    removed. A non-empty answer is a leak: a test made a jail and did not destroy it."""
    listed = docker(
        "ps", "-a", "--no-trunc", "--filter", f"label={JAIL_LABEL}", "--format",
        '{{.ID}} {{.Label "' + JAIL_LABEL + '"}}',
    )  # fmt: skip
    if listed.returncode != 0:
        return []
    leaked = [
        line.split(" ", 1)[0]
        for line in listed.stdout.splitlines()
        if token in line.split(" ", 1)[-1]
    ]
    for container_id in leaked:
        docker("rm", "-f", "--", container_id)
    return leaked

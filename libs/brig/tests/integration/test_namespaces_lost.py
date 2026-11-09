"""A mount a process's isolation needs, refused (decision-212): the jail's processes lose their
namespaces, and the embedder is told, loudly. Planted in the supervisor this test's jails run, since
the kernel has no switch that refuses one type of mount alone; the rest is a real jail. What each
refusal must not be is a failed start, or silent."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import warnings
from collections.abc import Callable, Iterator

import pytest

from brig.run import HostRuntime, Jail, NamespacesLost, build_compile_ctx
from brig.run._supervisor_program import SUPERVISOR_SOURCE
from brig.stack import strict_linux
from tests.conftest import NewJailDir
from tests.supervised_jail import (
    INTERPRETER,
    create_jail,
    needs_a_supervised_jail,
    needs_namespaces,
    sh,
    spec_for,
    stderr_of,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _needs_a_jail() -> None:
    needs_a_supervised_jail()


@pytest.fixture
def under_dev_shm() -> Iterator[Callable[[], str]]:
    """Directories on the host's `/dev/shm`, removed after."""
    if not os.access("/dev/shm", os.W_OK):
        pytest.skip("this host has no /dev/shm to write")
    made: list[str] = []

    def make_one() -> str:
        made.append(tempfile.mkdtemp(prefix="brig-", dir="/dev/shm"))
        os.chmod(made[-1], 0o777)
        return made[-1]

    yield make_one
    for each in made:
        shutil.rmtree(each, ignore_errors=True)


def _refusing(monkeypatch: pytest.MonkeyPatch, condition: str) -> None:
    """The supervisor has its `mount` refuse what `condition` names, with the `EPERM` a host would."""
    start = "def mount(source, target, fstype, flags, options=None):\n"
    assert SUPERVISOR_SOURCE.count(start) == 1
    monkeypatch.setattr(
        "brig.run.host.SUPERVISOR_SOURCE",
        SUPERVISOR_SOURCE.replace(
            start,
            f"{start}    if {condition}:\n        raise OSError(1, 'Operation not permitted')\n",
        ),
    )


@pytest.mark.skipif(
    os.geteuid() == 0, reason="uid 0 never tries the bundle, so never has this refused"
)
@pytest.mark.parametrize(
    ("condition", "target"),
    [
        ("fstype == 'devpts'", "/dev/pts"),
        ("fstype == 'tmpfs'", "/dev/shm"),
        ("str(source).startswith('/proc/self/fd/')", "/dev/shm/"),
    ],
    ids=["devpts", "tmpfs", "carried"],
)
def test_a_refused_mount_warns_the_embedder_naming_it_and_what_it_cost(
    monkeypatch: pytest.MonkeyPatch,
    new_jail_dir: NewJailDir,
    under_dev_shm: Callable[[], str],
    condition: str,
    target: str,
) -> None:
    needs_namespaces()
    _refusing(monkeypatch, condition)
    workspace = under_dev_shm()
    jails: list[Jail] = []
    try:
        with pytest.warns(NamespacesLost, match=target) as caught:
            jails.append(create_jail(new_jail_dir(), workspace=workspace))
        said = str(caught[0].message)
        assert "refused" in said and "no namespaces of their own" in said, said
        process = jails[0].start(sh("exit 0"))  # not a failed start: the graded fallback
        assert process.wait(15) == 0, stderr_of(process)
        assert process.namespaces is False and target in process.control.detail
    finally:
        for jail in jails:
            jail.destroy()


@pytest.mark.skipif(
    os.geteuid() == 0, reason="uid 0 never tries the bundle, so never has this refused"
)
def test_an_embedder_that_shows_it_itself_is_told_and_nothing_is_warned(
    monkeypatch: pytest.MonkeyPatch, new_jail_dir: NewJailDir
) -> None:
    needs_namespaces()
    _refusing(monkeypatch, "fstype == 'devpts'")
    told: list[str] = []
    spec = spec_for(new_jail_dir())
    jail_dir = new_jail_dir()
    compiled = strict_linux(INTERPRETER).compile(
        spec, ctx=build_compile_ctx(spec, jail_dir=jail_dir, platform=sys.platform)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        jail = Jail.create(
            compiled,
            runtime=HostRuntime(),
            cwd="/",
            jail_id="told",
            jail_dir=jail_dir,
            told=told.append,
        )
    jail.destroy()
    assert len(told) == 1 and "/dev/pts" in told[0], told

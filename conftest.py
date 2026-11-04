"""Which tests share the host's state, so that pytest-xdist runs them one after another.

`scripts/check` runs the suite as `pytest -n auto --dist loadgroup`: the tests spread over every core,
except that the tests of one group below run on one worker, in turn. A bare `pytest PATH` stays serial
(`-n` is not in `addopts`) and ignores the groups. A test joins a group when it takes something of the
host's that one test at a time may hold; the group is named here, with why, because a group can span
members (a mark in each test file would repeat its name and its reason). A new test that takes the same
thing goes into the group, in this table.
"""

import contextlib
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Group:
    """Tests that must not run beside each other: `modules` are paths from the repository root, the test
    files whose tests all belong."""

    name: str
    why: str
    modules: tuple[str, ...]


GROUPS = (
    Group(
        name="jails",
        why=(
            "These tests start real bubblewrap jails (runner_cordis_plugin.jail) and measure how long "
            "one takes to end (the tripwire's milliseconds, a killed bh-02's jail going with it), which "
            "a worker loaded with other jails' namespaces flakes. brig keeps its placeholders and the "
            "lock over them under its own state directory (`BRIG_HOME`), which the fixture below gives "
            "each test, so none shares that. test_host_values.py boots runner:confined and expects it "
            "to refuse before any jail starts; it is here because a regression in that refusal would "
            "start one. test_runner_approval.py builds a BrigJail to read its report without starting "
            "it, for the same reason."
        ),
        modules=(
            "bh-02/app/tests/test_host_values.py",
            "bh-02/app/tests/test_python_repl.py",
            "bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py",
            "bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py",
            "bh-02/plugins/runner-cordis-plugin/tests/test_runner_live_egress.py",
            "bh-02/plugins/runner-cordis-plugin/tests/test_runner_tmux.py",
            "bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py",
        ),
    ),
)


@pytest.fixture(autouse=True, scope="session")
def _a_brig_home_of_its_own(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """brig keeps its state (the jails' channel directories and the placeholders it makes, with the
    lock over them) in `BRIG_HOME`, else `~/.brig`: each test process names a directory of its own,
    so no test writes the person's. One for the process, not for each test: brig resolves the
    directory once per process and keeps it, and the processes a test starts inherit it. Short (a
    socket path must fit in about 100 bytes)."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("BRIG_HOME", str(tmp_path_factory.mktemp("brig")))
        yield


_RUN_TEMP = pytest.StashKey[Path]()
_STALE_S = 24 * 3600  # a run's temp directory older than this is a run that is gone


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Every test's `tmp_path` is under `$XDG_CACHE_HOME/bh-02-pytest/` (else `~/.cache/...`), in a
    directory of this run's own, not under `/tmp`, unless `--basetemp` says otherwise. A jail refuses
    a root at or under a place hosts keep sockets (`/tmp`, `/var/tmp`, `/run`, `$XDG_RUNTIME_DIR`:
    `runner_cordis_plugin.policy.socket_refusal`), and the tests that start real jails make their
    projects, state and memory under `tmp_path`. Not inside the checkout: a test's project there would
    be a directory of a git repository, and bh-02's own project. One directory per run, never shared,
    so two runs at once (a lead's and a worker's) never empty each other's; it is removed when the run
    passes and kept when it fails, and one older than a day is swept. pytest-xdist's workers are handed
    the controller's, so only the controller makes one."""
    if config.option.basetemp is None and not hasattr(config, "workerinput"):
        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "bh-02-pytest"
        cache.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for old in cache.glob("run-*"):
            with contextlib.suppress(OSError):
                if now - old.stat().st_mtime > _STALE_S:
                    shutil.rmtree(old, ignore_errors=True)
        run = Path(tempfile.mkdtemp(prefix=f"run-{_ROOT.name}-", dir=cache))
        config.option.basetemp = run / "t"  # pytest empties and makes the basetemp itself
        config.stash[_RUN_TEMP] = run


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Remove this run's temp directory when the run passed; keep it to look at when it failed."""
    run = session.config.stash.get(_RUN_TEMP, None)
    if run is not None and exitstatus == 0:
        shutil.rmtree(run, ignore_errors=True)


def group_of(module: str) -> str | None:
    """The name of the group the test file `module` (a path from the repository root) belongs to."""
    return next((group.name for group in GROUPS if module in group.modules), None)


@pytest.hookimpl(tryfirst=True)  # before pytest-xdist reads the marks to name each test's group
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(_ROOT) and (name := group_of(item.path.relative_to(_ROOT).as_posix())):
            item.add_marker(pytest.mark.xdist_group(name))

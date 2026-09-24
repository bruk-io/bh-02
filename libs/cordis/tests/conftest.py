"""A throwaway plugin package on disk, for the tests that scan or resolve one."""

import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

PLUGIN = '''
from dataclasses import dataclass
from functools import partial
from typing import Protocol, runtime_checkable

from cordis import Effects, bind, component, enter


@runtime_checkable
class Subprocess(Protocol):
    async def run(self, *argv: str) -> str: ...


@dataclass(frozen=True, slots=True)
class GitConfig:
    binary: str = "git"


class GitClient:
    """Git over the composition's subprocess seam, so sandboxing applies to it too."""

    def __init__(self, binary: str, subprocess: Subprocess) -> None:
        self.binary, self.subprocess, self.closed = binary, subprocess, False

    async def __aenter__(self) -> "GitClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.closed = True

    async def status(self, path: str = ".") -> str:
        return await self.subprocess.run(self.binary, "status", path)


class FakeSubprocess:
    def __init__(self, reply: str = "clean\\n") -> None:
        self.reply, self.calls = reply, []

    async def run(self, *argv: str) -> str:
        self.calls.append(argv)
        return self.reply


async def git_status(path: str = ".", *, git: GitClient) -> str:
    """Working-tree status."""
    return await git.status(path)


@component(provides=("subprocess",))
async def subprocess(*, config: dict | None = None) -> Effects:
    yield bind("subprocess", FakeSubprocess((config or {}).get("reply", "clean\\n")))


@component(provides=("git",))
async def git(*, config: GitConfig, subprocess: Subprocess) -> Effects:
    client: GitClient = yield enter(GitClient(config.binary, subprocess))
    yield bind("git", client)


@component(provides=("git_status",))
async def git_tools(*, git: GitClient) -> Effects:
    """The callables, bound together so they share one lifetime."""
    yield bind("git_status", partial(git_status, git=git))
'''


@pytest.fixture
def plugin(tmp_path: Path) -> Iterator[object]:
    """An importable one-module package named `git_plugin`, gone again after the test."""
    package = tmp_path / "git_plugin"
    package.mkdir()
    (package / "__init__.py").write_text(PLUGIN)
    sys.path.insert(0, str(tmp_path))
    try:
        import git_plugin

        yield git_plugin
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("git_plugin", None)
        shutil.rmtree(package, ignore_errors=True)

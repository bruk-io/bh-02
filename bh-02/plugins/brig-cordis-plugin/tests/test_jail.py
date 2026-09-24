"""The policy as a function, and the row. Real cells in a real jail are
bh-02/app/tests/test_python_cells.py's: they need a kernel, which is another plugin."""

from dataclasses import dataclass

import pytest

from brig_cordis_plugin import BrigConfig, BrigJail, jail, self_modify_denied, spec_for
from cordis.testing import drive


@dataclass(frozen=True)
class Layers:
    paths: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()


def test_the_spec_denies_what_would_reach_outside_the_jail_later() -> None:
    spec = spec_for(
        root="/w/app",
        endpoint="/tmp/k/k.sock",
        scratch="/tmp/j/tmp",
        home="/Users/me",
        config=BrigConfig(),
        layers=("/w/app/mine.toml", "/elsewhere/chat.toml"),
        host=("/w/app/src", "/usr/lib/python3.15", "/w/app/.venv", "/w/app"),
        secrets=("/src/bh/local.env",),
    )
    assert spec.fs.write_allows == ("/tmp/j/tmp", "/w/app")
    denies = set(spec.fs.write_denies)
    assert {"/w/app/mine.toml", "/elsewhere/chat.toml"} <= denies  # the composition's own files
    assert {
        "/w/app/src",
        "/w/app/.venv",
    } <= denies and "/usr/lib/python3.15" not in denies  # host code inside
    assert "/w/app" not in denies  # the project itself on sys.path (`python -m`) stays writable
    assert {
        "/w/app/.git/hooks",
        "/w/app/.git/config",
        "/w/app/.claude",
    } <= denies  # brig's self-modify list
    assert not {"/w/app/CLAUDE.md", "/w/app/AGENTS.md"} & denies  # but the guidance files: `allow`'s default
    assert "/Users/me/.ssh" in spec.fs.read_denies
    assert "/w/app/local.env" in spec.fs.read_denies  # a credential beside the project
    assert "/src/bh/local.env" in spec.fs.read_denies  # bh-02's own, wherever the project is
    assert dict(spec.env.set) == {"TMPDIR": "/tmp/j/tmp"} and "PATH" in spec.env.allow_names
    assert [c.endpoint for c in spec.channels] == ["/tmp/k/k.sock"]


def test_allow_takes_names_off_brig_s_self_modification_list_and_only_those() -> None:
    assert "CLAUDE.md" not in self_modify_denied(("CLAUDE.md",))
    assert {".git/hooks", ".git/config", "AGENTS.md"} <= set(self_modify_denied(("CLAUDE.md",)))
    assert ".git/config" in self_modify_denied(())  # nothing allowed: the whole list
    with pytest.raises(ValueError) as raised:
        self_modify_denied(("README.md",))
    assert "'README.md'" in str(raised.value) and "use `write`" in str(raised.value)


async def test_the_row_binds_a_brig_jail_over_the_layers_it_was_given() -> None:
    effects = await drive(jail(config=BrigConfig(), layers=Layers()))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "jail")]
    assert isinstance(effects[0].args[1], BrigJail)

"""Agent types as data: a type file parsed, every refusal saying what to write, where type files
are read from, and the decisions a child's start and run make (its tools, the questions its start
asks, its steps, its usage), as functions."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any

import pytest

from agents_cordis_plugin import (
    EXPLORE,
    GENERAL,
    SHIPPED,
    AgentType,
    Report,
    Steps,
    TypeFile,
    asked_why,
    child_rows,
    denied,
    known_types,
    limited,
    parsed_type,
    session_model,
    start_request,
    stepped,
    type_files,
    usage_event,
    waited,
)

_SOURCE = "/home/me/.config/bh-02/agents/reviewer.toml"
_GRANTABLE = ("python", "echo")


def _parsed(text: str, name: str = "reviewer") -> AgentType:
    return parsed_type(name, text, _SOURCE, _GRANTABLE)


def test_a_type_file_is_its_prompt_model_steps_and_tools() -> None:
    kind = _parsed('prompt = "You are agent {name}."\nmodel = "haiku"\nsteps = 5\ntools = ["python"]\n')
    assert kind == AgentType("reviewer", "You are agent {name}.", "haiku", 5, ("python",))


def test_a_type_file_naming_only_its_prompt_gets_the_session_model_30_steps_and_every_tool() -> None:
    assert _parsed('prompt = "Look."') == AgentType("reviewer", "Look.", None, 30, _GRANTABLE)
    assert _parsed('prompt = "Look."\ntools = []').tools == ()


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("prompt = ", "is not TOML ("),
        (
            'prompt = "x"\ncolour = "red"',
            "there is no field 'colour'; a type has `prompt`, `model`, `steps` and `tools`: take it out",
        ),
        ('model = "haiku"', "`prompt` is missing; write the type's section of a sub-agent's prompt there"),
        ('prompt = "  "', "`prompt` is '  '; write the type's section"),
        ('prompt = "x"\nmodel = 3', '`model` is 3, not a model\'s name; write one, such as model = "haiku"'),
        ('prompt = "x"\nmodel = ""', "`model` is '', not a model's name"),
        (
            'prompt = "x"\nsteps = 0',
            "`steps` is 0; write how many model steps it may take, a whole number of at least 1, "
            "such as steps = 30",
        ),
        ('prompt = "x"\nsteps = true', "`steps` is True; write how many model steps"),
        ('prompt = "x"\nsteps = "ten"', "`steps` is 'ten'; write how many model steps"),
        (
            'prompt = "x"\ntools = "python"',
            "`tools` is 'python'; write the rows it may use as a list of names, such as tools = [\"python\"]",
        ),
        (
            'prompt = "x"\ntools = ["agents"]',
            "`tools` names 'agents', but a sub-agent can't start one of its own (depth one, "
            "decision-0002): take it out",
        ),
        (
            'prompt = "x"\ntools = ["extensions"]',
            "`tools` names 'extensions', which a type can't grant: only bh-02's own tool rows a "
            "sub-agent's conversation has (python, echo), never extensions or MCP; take it out",
        ),
        ('prompt = "x"\ntools = ["mcp"]', "`tools` names 'mcp', which a type can't grant"),
        ('prompt = "x"\ntools = ["shell"]', "`tools` names 'shell', which a type can't grant"),
    ],
)
def test_a_malformed_type_file_is_refused_naming_the_file_the_field_and_what_to_write(
    text: str, said: str
) -> None:
    with pytest.raises(ValueError) as why:
        _parsed(text)
    assert str(why.value).startswith(f"the agent type file {_SOURCE}")
    assert said in str(why.value)


@pytest.mark.parametrize("name", ["Reviewer", "1st", "a b", "../x", "x" * 33, ""])
def test_a_type_file_whose_name_is_not_a_type_s_is_refused_saying_how_to_name_it(name: str) -> None:
    with pytest.raises(ValueError, match="is not a type's name; name the file for its type"):
        _parsed('prompt = "x"', name=name)


def test_the_shipped_types_are_explore_and_general_and_a_person_s_file_replaces_one() -> None:
    assert sorted(SHIPPED) == ["explore", "general"] and SHIPPED["general"] is GENERAL
    assert "change nothing" in EXPLORE.section and "of type explore" in EXPLORE.section
    files = [
        TypeFile("general", "/c/agents/general.toml", 'prompt = "mine"\nsteps = 3'),
        TypeFile("broken", "/c/agents/broken.toml", "steps = 3"),
        TypeFile("far", "/p/agents/far.toml", None, "not read: it is in the project"),
    ]
    known = known_types(files, _GRANTABLE)
    assert known["explore"] is EXPLORE
    assert known["general"] == AgentType("general", "mine", None, 3, _GRANTABLE)
    assert isinstance(known["broken"], str) and "`prompt` is missing" in known["broken"]
    assert known["far"] == "not read: it is in the project"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_type_files_are_read_from_the_trusted_directories_the_first_of_a_name_kept(tmp_path: Path) -> None:
    run, default = tmp_path / "run", tmp_path / "home" / ".config" / "bh-02"
    _write(run / "agents" / "reviewer.toml", 'prompt = "run\'s"')
    _write(default / "agents" / "reviewer.toml", 'prompt = "default\'s"')
    _write(default / "agents" / "scout.toml", 'prompt = "scout"')
    _write(default / "agents" / "notes.txt", "not a type")
    (default / "agents" / "dir.toml").mkdir()
    project = tmp_path / "project"
    project.mkdir()
    found = type_files([str(run), str(default), str(run), str(tmp_path / "none")], project)
    assert [(f.name, f.text) for f in found] == [
        ("reviewer", 'prompt = "run\'s"'),
        ("scout", 'prompt = "scout"'),
    ]


def test_a_type_file_whose_reading_passes_through_the_project_is_not_read(tmp_path: Path) -> None:
    """In the project (bh-02 run from a directory that holds its config), or a link into it:
    the model's code could write either, and a type chooses a model."""
    project = tmp_path / "project"
    inside = project / "cfg"
    _write(inside / "agents" / "mine.toml", 'prompt = "the model wrote me"')
    outside = tmp_path / "cfg"
    _write(project / "planted.toml", 'prompt = "planted"')
    (outside / "agents").mkdir(parents=True)
    os.symlink(project / "planted.toml", outside / "agents" / "linked.toml")
    found = {f.name: f for f in type_files([str(inside), str(outside)], project)}
    assert set(found) == {"mine", "linked"}
    for each in found.values():
        assert each.text is None and each.refused is not None
        assert "is not read: reading it passes through the project" in each.refused
    known = known_types(found.values(), _GRANTABLE)
    assert isinstance(known["mine"], str) and isinstance(known["linked"], str)


def test_a_type_file_is_read_through_no_link_whatever_the_link_leads_to(tmp_path: Path) -> None:
    """A link made after the project check, or one the check let through (it leads outside the
    project), is not followed: the file is read from the descriptor it was opened as, so there is
    no gap between the check and the read for a link to be swapped into."""
    project = tmp_path / "project"
    project.mkdir()
    cfg, elsewhere = tmp_path / "cfg", tmp_path / "elsewhere"
    _write(elsewhere / "real.toml", 'prompt = "a file the person keeps elsewhere"')
    _write(cfg / "agents" / "plain.toml", 'prompt = "plain"')
    os.symlink(elsewhere / "real.toml", cfg / "agents" / "linked.toml")
    _write(elsewhere / "second.toml", 'prompt = "a second name for a file elsewhere"')
    os.link(elsewhere / "second.toml", cfg / "agents" / "twice.toml")
    found = {f.name: f for f in type_files([str(cfg)], project)}
    assert set(found) == {"plain", "linked", "twice"}
    linked = found["linked"]
    assert linked.text is None
    assert linked.refused == (
        f"the agent type file {cfg / 'agents' / 'linked.toml'} is a link to {elsewhere / 'real.toml'}, which "
        "bh-02 does not follow; keep the type's file itself in bh-02's config directory"
    )
    assert found["twice"].text is None  # a hard link is a second name for a file kept elsewhere
    assert "is not a regular file with one name" in str(found["twice"].refused)
    assert found["plain"].text == 'prompt = "plain"' and found["plain"].refused is None
    known = known_types(found.values(), _GRANTABLE)
    assert isinstance(known["plain"], AgentType)
    assert isinstance(known["linked"], str) and isinstance(known["twice"], str)


def test_a_type_file_beneath_an_agents_directory_that_is_a_link_is_not_read(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    cfg = tmp_path / "cfg"
    _write(tmp_path / "dotfiles" / "scout.toml", 'prompt = "scout"')
    cfg.mkdir()
    os.symlink(tmp_path / "dotfiles", cfg / "agents")
    [scout] = type_files([str(cfg)], project)
    assert scout.text is None
    assert scout.refused == (
        f"the agent type file {cfg / 'agents' / 'scout.toml'} is reached through {cfg / 'agents'}, "
        "which is a link, so bh-02 did not read it; keep the agents directory itself in bh-02's config "
        "directory"
    )


def test_a_type_file_that_is_too_large_or_not_text_is_refused_saying_so(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    cfg = tmp_path / "cfg"
    _write(cfg / "agents" / "long.toml", 'prompt = "' + "x" * 70_000 + '"')
    (cfg / "agents" / "binary.toml").write_bytes(b'prompt = "\xff\xfe"')
    found = {f.name: f for f in type_files([str(cfg)], project)}
    assert found["long"].text is None and found["long"].refused == (
        f"the agent type file {cfg / 'agents' / 'long.toml'} is larger than 65,536 bytes, "
        "so bh-02 did not read it"
    )
    assert found["binary"].text is None
    assert str(found["binary"].refused).startswith(
        f"the agent type file {cfg / 'agents' / 'binary.toml'} is not UTF-8 text ("
    )


@dataclass(frozen=True)
class _Entry:
    id: str
    use: str
    config: Mapping[str, Any] = field(default_factory=dict)
    disabled: bool = False


_PARENT = [
    _Entry("loop", "agent:loop"),
    _Entry("model", "models:model", {"default": "sonnet"}),
    _Entry("python", "python:tool"),
    _Entry("echo", "test:echo"),
]


def test_a_child_gets_the_tool_rows_its_type_grants_and_every_other_row() -> None:
    def rows(tools: tuple[str, ...]) -> list[str]:
        kind = AgentType("t", "{name}", tools=tools)
        made = child_rows(
            _PARENT,
            name="t-1",
            kind=kind,
            kept=("loop", "model", "python", "echo"),
            tools=_GRANTABLE,
            transcript_row="transcript",
            model_row="model",
            place=PurePath("/s/agents/t-1"),
            hand=None,
        )
        return [r.id.removeprefix("agents/t-1/") for r in made]

    assert rows(("python", "echo")) == ["loop", "model", "python", "echo", "output", "agent"]
    assert rows(("echo",)) == ["loop", "model", "echo", "output", "agent"]
    assert rows(()) == ["loop", "model", "output", "agent"]


def test_a_start_is_asked_past_the_session_budget_and_for_a_model_other_than_its_type_s() -> None:
    assert session_model(_PARENT, "model") == "sonnet" and session_model(_PARENT, "nope") is None
    general, cheap = GENERAL, AgentType("cheap", "x", model="haiku")
    assert asked_why(started=15, budget=16, kind=general, model=None, session="sonnet") == ()
    assert asked_why(started=15, budget=16, kind=general, model="sonnet", session="sonnet") == ()
    assert asked_why(started=0, budget=16, kind=cheap, model="haiku", session="sonnet") == ()
    assert asked_why(started=16, budget=16, kind=general, model=None, session="sonnet") == (
        "the session's budget of 16 sub-agents is spent: 16 have started",
    )
    assert asked_why(started=0, budget=16, kind=cheap, model="opus", session="sonnet") == (
        "it names the model 'opus', not its type's (haiku)",
    )
    assert asked_why(started=0, budget=16, kind=general, model="opus", session=None) == (
        "it names the model 'opus', not its type's (the session model)",
    )
    assert len(asked_why(started=20, budget=16, kind=general, model="opus", session="sonnet")) == 2
    why = ("the session's budget of 16 sub-agents is spent: 16 have started",)
    request = start_request(general, {"prompt": "look\nhard", "type": "general"}, why)
    assert request["name"] == "agent" and "agent" not in {k for k in request if k != "name"}
    assert request["title"] == f"Start a general sub-agent ({why[0]})?"
    assert request["lines"] == ["look", "hard"]
    assert denied("general", why) == (
        f"denied: the person said no to starting a general sub-agent ({why[0]}), so none started; "
        "ask them what they want instead"
    )


def _steps(events: list[Mapping[str, Any]], limit: int) -> list[bool]:
    """Whether the limit ends the reply at each event."""
    steps, ended = Steps(), []
    for event in events:
        steps = stepped(steps, event)
        ended.append(limited(steps, event, limit))
    return ended


def test_a_step_ends_with_its_last_call_s_result_or_a_stop_and_the_limit_ends_the_reply_there() -> None:
    two_calls = [
        {"type": "text", "text": "a"},
        {"type": "tool_call", "id": "1"},
        {"type": "tool_call", "id": "2"},
        {"type": "usage", "input_tokens": 1},
        {"type": "tool_result", "call_id": "1"},
        {"type": "tool_result", "call_id": "2"},
        {"type": "note", "text": "aside"},
    ]
    assert _steps(two_calls, 1) == [False, False, False, False, False, True, True]
    assert _steps([*two_calls, {"type": "tool_call", "id": "3"}, {"type": "tool_result"}], 2)[-1] is True
    fed_back = [{"type": "stop", "reason": "silent"}]
    assert _steps(fed_back, 1) == [True]  # the loop would feed it back: another step
    assert _steps([{"type": "stop", "reason": "answered"}], 1) == [False]  # it answered: done
    assert _steps([{"type": "stop", "reason": "refused"}], 1) == [False]


def test_a_child_s_usage_is_one_usage_event_or_none() -> None:
    assert usage_event(Report("x", "answered")) is None
    assert usage_event(Report("x", "answered", 300, 30, None, 100)) == {
        "type": "usage",
        "input_tokens": 300,
        "output_tokens": 30,
        "cache_read_input_tokens": 100,
    }
    assert usage_event(Report("x", "answered", 0, 0, 0.5)) == {
        "type": "usage",
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.5,
    }


def test_agent_wait_says_the_reports_in_order_then_who_still_runs_then_names_it_has_none_of() -> None:
    said = waited([("a-2", "Report two"), ("a-1", "Report one")], ["a-3"], ["zz"], ["a-1", "a-2", "a-3"])
    assert said == (
        "Report two\n\nReport one\n\nStill running: a-3; agent_wait again for their reports.\n\n"
        "error: no background agent is named 'zz'; the background agents of this session are a-1, a-2, a-3"
    )
    assert waited([], [], [], []).startswith("No agents named")

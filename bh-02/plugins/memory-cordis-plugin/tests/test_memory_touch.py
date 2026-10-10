"""The on-touch row: what loads on demand for the files an input opened, told with its result,
each once a conversation, a resumed one too; and the rows' wiring."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from cordis.testing import drive
from cordis_helpers import Hooks
from memory_cordis_plugin import Memory, MemoryConfig, OnTouch, Transcript, files, on_touch


class _Kept:
    """A `transcript` value over the messages given, counting how often they are read."""

    def __init__(self, *messages: Mapping[str, Any]) -> None:
        self._messages = messages
        self.reads = 0

    @property
    def messages(self) -> tuple[Mapping[str, Any], ...]:
        self.reads += 1
        return self._messages


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _project(tmp_path: Path) -> tuple[OnTouch, Path]:
    home, root = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    root.mkdir()
    found = Memory(MemoryConfig(root=str(root), home=str(home), managed=str(tmp_path / "none")))
    return OnTouch(found, _Kept()), root.resolve()


def test_a_file_opened_brings_its_memory_once(tmp_path: Path) -> None:
    told, root = _project(tmp_path)
    _write(root / "src/db/CLAUDE.md", "Use the session.")
    _write(root / ".claude/rules/db.md", "---\npaths: src/db/**\n---\nMigrations by hand.")
    first = told({"touched": (str(root / "src/db/models.py"),)})
    assert first == (
        "From src/db/CLAUDE.md, instructions for work under src/db/:\n\nUse the session.\n\n"
        "From .claude/rules/db.md, a rule for src/db/**:\n\nMigrations by hand."
    )
    assert told({"touched": (str(root / "src/db/other.py"),)}) == ""
    _write(root / "src/db/CLAUDE.md", "Use the pool.")  # changed since: told again
    assert "Use the pool." in told({"touched": (str(root / "src/db/models.py"),)})


def test_a_memory_file_the_model_opened_itself_is_not_told_after(tmp_path: Path) -> None:
    """Claude Code does not load a subdirectory's CLAUDE.md its own tools read: it is in the
    conversation already."""
    told, root = _project(tmp_path)
    guide = _write(root / "docs/CLAUDE.md", "Docs guidance.")
    assert told({"touched": (str(guide),)}) == ""
    assert told({"touched": (str(root / "docs/x.md"),)}) == ""


def test_a_text_the_cap_cut_is_told_whole_with_a_later_input_that_opens_its_files(tmp_path: Path) -> None:
    """Two 12,000-character files, and one input that opens a file under each: the aside holds the
    first whole and is cut in the second, so the second is not told yet, and a later input that
    opens a file under it is told it whole. One longer than the cap by itself is told once, cut."""
    told, root = _project(tmp_path)
    a, b = "A" * 12_000, "B" * 12_000
    _write(root / "a/CLAUDE.md", a)
    _write(root / "b/CLAUDE.md", b)
    first = told({"touched": (str(root / "a/x.py"), str(root / "b/x.py"))})
    assert a in first and b not in first and first.endswith(" more chars of memory]")
    later = told({"touched": (str(root / "b/y.py"),)})
    assert later.startswith("From b/CLAUDE.md") and later.endswith(b)
    assert told({"touched": (str(root / "b/z.py"),)}) == ""
    _write(root / "c/CLAUDE.md", "C" * 30_000)
    assert told({"touched": (str(root / "c/x.py"),)}).endswith(" more chars of memory]")
    assert told({"touched": (str(root / "c/y.py"),)}) == ""


class _Said:
    """A `memory` value that says what it is given to say, and keeps what it was asked."""

    def __init__(self, *said: tuple[str, str]) -> None:
        self.said = said
        self.asked: list[Sequence[str]] = []

    def touched(self, paths: Sequence[str]) -> Sequence[tuple[str, str]]:
        self.asked.append(paths)
        return self.said


def test_it_asks_the_memory_value_and_tells_each_once() -> None:
    found = _Said(("/p/a.md", "A."), ("/p/b.md", "B."), ("/p/a.md", "A."))
    told = OnTouch(found, _Kept())
    assert told({"touched": (Path("/p/src/x.py"),)}) == "A.\n\nB."  # each once, in order
    assert found.asked == [["/p/src/x.py"]]  # as text, as it crosses to another plugin
    assert told({"touched": ("/p/src/y.py",)}) == ""
    assert told({"code": "1"}) == "" and len(found.asked) == 2  # nothing opened: nothing asked


def test_a_resumed_conversation_from_before_the_loop_kept_asides_is_searched_for_what_it_told() -> None:
    """A resumed session (or the row reloaded) starts a new `OnTouch`, but the transcript holds
    what the model was told. An entry from before the loop kept `asides` holds it only in its
    text: a text it holds whole, after a blank line, is told already. One the person quoted, one
    an entry starts with (an input printed it), one cut short and one that changed since were
    not, so each is told. The transcript is read once, at the
    first input that opens a file; an empty one (after /clear) tells each afresh."""
    rule = "From .claude/rules/db.md, a rule for src/db/**:\n\nMigrations by hand.\n\nNever by script."
    guide = "From src/db/CLAUDE.md, instructions for work under src/db/:\n\nUse the session."
    long, quoted, printed = "From long.md:\n\n" + "L" * 30, "From q.md:\n\nQ.", "From p.md:\n\nP."
    transcript = _Kept(
        {"role": "user", "content": f"what is this?\n\n{quoted}"},
        {"role": "tool", "content": f"6\n\n{guide}\n\n{rule}", "call_id": "c0"},
        {"role": "tool", "content": f"{printed}\n\n(this input ran `cat` ...)", "call_id": "c1"},
        {"role": "tool", "content": f"0\n\n{long[:20]}\n... [12 more chars of memory]", "call_id": "c2"},
    )
    assert isinstance(transcript, Transcript)
    changed = rule.replace("by hand", "by the tool")
    said = [(f"/p/{n}.md", text) for n, text in enumerate((guide, rule, long, quoted, printed, changed))]
    told = OnTouch(_Said(*said), transcript)
    assert told({"code": "1"}) == "" and transcript.reads == 0  # nothing opened: nothing read
    assert told({"touched": ("/p/src/db/x.py",)}) == "\n\n".join((long, quoted, printed, changed))
    assert told({"touched": ("/p/src/db/y.py",)}) == "" and transcript.reads == 1
    afresh = OnTouch(_Said(*said), _Kept())
    assert afresh({"touched": ("/p/src/db/x.py",)}) == "\n\n".join(text for _, text in said)


def test_a_text_cut_back_since_a_resumed_conversation_was_told_it_is_told_again() -> None:
    """A rule cut back to its first paragraphs since the conversation was told it is still whole
    in the old aside, but with the paragraph now gone after it: told again. A text counts as told
    only where its aside ends: at the entry's end, at the mark of an aside cut short, or where
    another aside begins (bh-02's begin with `(`, memory's with `From `)."""
    rule = "From .claude/rules/db.md, a rule for src/db/**:\n\nMigrations by hand."
    guide = "From src/db/CLAUDE.md, instructions for work under src/db/:\n\nUse the session."
    near, changed = "From near.md:\n\nN.", "(bh-02: your instructions have changed ...)"
    transcript = _Kept(
        {"role": "tool", "content": f"6\n\n{rule}\n\nNever touch prod.", "call_id": "c0"},
        {"role": "tool", "content": f"7\n\n{guide}\n\n{changed}", "call_id": "c1"},
        {"role": "tool", "content": f"8\n\n{near}\n... [40 more chars of guidance]", "call_id": "c2"},
    )
    said = [("/p/rule.md", rule), ("/p/CLAUDE.md", guide), ("/p/near.md", near)]
    assert OnTouch(_Said(*said), transcript)({"touched": ("/p/src/db/x.py",)}) == rule


_RULE = "From .claude/rules/db.md, a rule for src/db/**:\n\nMigrations by hand."
_GUIDE = "From src/db/CLAUDE.md, instructions for work under src/db/:"


def test_a_resumed_conversation_reads_what_was_told_from_the_asides_kept_on_each_entry() -> None:
    """The loop keeps the asides it told with a result on its entry (`asides`), so another row's
    aside sorting after this row's is not taken for more of a text, and a text the result printed
    is not one told."""
    guide, other = f"{_GUIDE}\n\nUse the session.", "Zebra: another row's aside."
    printed = "From p.md, instructions for work under p/:\n\nP."
    transcript = _Kept(
        {
            "role": "tool",
            "content": f"6\n\n{guide}\n\n{_RULE}\n\n{other}",
            "call_id": "c0",
            "asides": [f"{guide}\n\n{_RULE}", other],
        },
        {"role": "tool", "content": f"7\n\n{printed}", "call_id": "c1", "asides": []},
    )
    said = [("/p/CLAUDE.md", guide), ("/p/rule.md", _RULE), ("/p/p.md", printed)]
    assert OnTouch(_Said(*said), transcript)({"touched": ("/p/src/db/x.py",)}) == printed


def test_a_file_cut_back_after_a_paragraph_in_brackets_is_told_again_after_a_resume() -> None:
    """A file cut back since its text was told is still whole at the start of the old text, the
    paragraphs now gone after it, however they begin: told again. In one aside, a text ends where
    the aside ends, where it was cut short, or where the next text begins, after a blank line, as
    memory writes them (`From FILE, instructions ...` or `From FILE, a rule for ...`). A file a
    text imports is part of that text, not the next one."""
    trimmed = f"{_GUIDE}\n\nUse the session."
    near = "From .claude/rules/near.md, a rule for near/**:\n\nN."
    cut = "From cut/CLAUDE.md, instructions for work under cut/:\n\nC."
    asides = (
        f"{trimmed}\n\n(Never by script.)",
        f"{_RULE}\n\nFrom the repository's root, run them with `make migrate`.",
        f"{near}\n\n{cut}\n... [40 more chars of memory]",
        f"{trimmed}\n\nFrom docs/db.md, imported by src/db/CLAUDE.md:\n\nOld.",
    )
    transcript = _Kept(
        *(
            {"role": "tool", "content": f"{n}\n\n{aside}", "call_id": f"c{n}", "asides": [aside]}
            for n, aside in enumerate(asides)
        )
    )
    said = [("/p/CLAUDE.md", trimmed), ("/p/rule.md", _RULE), ("/p/near.md", near), ("/p/cut.md", cut)]
    assert OnTouch(_Said(*said), transcript)({"touched": ("/p/src/db/x.py",)}) == f"{trimmed}\n\n{_RULE}"


class _Access:
    """The `access` value as the on-touch row needs it: what it asks before a write."""

    def __init__(self) -> None:
        self.writes: Hooks[Callable[[str], str | None]] = Hooks()

    def before_write(self, fn: Callable[[str], str | None]) -> Callable[[], None]:
        return self.writes.add(fn)


async def test_the_on_touch_row_adds_its_function_to_asides_and_asks_before_a_write(tmp_path: Path) -> None:
    asides: Hooks[Callable[[Mapping[str, Any]], str]] = Hooks()
    access = _Access()
    found = Memory(MemoryConfig(root=str(tmp_path), home=str(tmp_path)))
    effects = await drive(on_touch(memory=found, asides=asides, transcript=_Kept(), access=access))
    assert [e.name for e in effects] == ["acquire", "acquire"]
    assert effects[0].args[0] == asides.add and isinstance(told := effects[0].args[1], OnTouch)
    assert effects[1].args == (access.before_write, told.before_write)


def test_the_first_write_to_a_file_with_untold_instructions_is_refused_until_they_are_told(
    tmp_path: Path,
) -> None:
    """Before a write, a file covered by what loads on demand that this conversation has not been
    told is refused, naming those files; the refused file is among what the call touched, so they
    follow as its aside, and the next write goes ahead. A memory file itself, and a file with none,
    are never refused."""
    told, root = _project(tmp_path)
    guide = _write(root / "src/db/CLAUDE.md", "Use the session.")
    _write(root / ".claude/rules/db.md", "---\npaths: src/db/**\n---\nMigrations by hand.")
    models = str(root / "src/db/models.py")
    refused = told.before_write(models)
    assert refused == (
        f"instructions that apply to it ({guide}, {root / '.claude/rules/db.md'}) have not been told "
        "in this conversation; they come with this input's result, and nothing was written to it: "
        "read them, then write it again"
    )
    assert told.before_write(models) == refused  # asking does not tell them
    assert "Use the session." in told({"touched": (models,)})  # the refused call's aside
    assert told.before_write(models) is None
    assert told.before_write(str(root / "README.md")) is None  # nothing applies to it
    assert told.before_write(str(guide)) is None  # the memory file itself: its text is what changes


class _Prompt:
    def __init__(self) -> None:
        self.sections: list[Callable[[], str]] = []

    def add(self, name: str, section: Callable[[], str]) -> Callable[[], None]:
        self.sections.append(section)
        return lambda: self.sections.remove(section)


class _Commands:
    def __init__(self) -> None:
        self.runs: dict[str, Callable[[str], Awaitable[Any]]] = {}

    def register(self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]) -> Callable[[], None]:
        self.runs[spec["name"]] = run
        return lambda: None


class _NoAuto:
    auto_memory = ""


async def test_the_memory_row_binds_memory_adds_its_section_and_offers_slash_memory(tmp_path: Path) -> None:
    _write(tmp_path / "CLAUDE.md", "Project.")
    prompt, commands = _Prompt(), _Commands()
    config = MemoryConfig(root=str(tmp_path), home=str(tmp_path / "home"), managed=str(tmp_path / "none"))
    effects = await drive(files(system=prompt, commands=commands, host=_NoAuto(), config=config))
    assert [(e.name, e.args[0]) for e in effects] == [
        ("bind", "memory"),
        ("acquire", prompt.add),
        ("acquire", commands.register),
    ]
    found = effects[0].args[1]
    assert isinstance(found, Memory) and effects[1].args[1:] == ("memory", found.text)
    assert "Contents of CLAUDE.md (project instructions" in found.text()
    run = effects[2].args[2]
    assert "  ✓ CLAUDE.md: project instructions, checked into the codebase" in await run("")

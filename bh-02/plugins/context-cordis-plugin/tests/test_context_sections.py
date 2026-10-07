"""bh-02's own section functions, over files in a temporary home and project."""

from collections.abc import Callable
from pathlib import Path

import pytest

from context_cordis_plugin import frontmatter, named, place, place_touched, rule, rules, rules_touched, whole


def _tree(base: Path, files: dict[str, str]) -> list[Path]:
    paths = []
    for name, text in files.items():
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        paths.append(path)
    return paths


def test_place_reads_what_covers_the_project_broadest_first_and_names_the_rest(tmp_path: Path) -> None:
    home, root = tmp_path / "home", tmp_path / "home" / "src" / "app"
    root.mkdir(parents=True)
    project = _tree(root, {"AGENTS.md": "Use uv.", "CLAUDE.md": "Use uv.", "engine/AGENTS.md": "Engine."})
    own = _tree(home, {"AGENTS.md": "I like short answers."})
    text = place([*project, *own], root=root, home=home)  # the person's own given last, still read first
    assert text.startswith("Guidance written for whichever agent works here")
    assert "where it names Claude Code or another agent it means you" in text
    assert text.index("From ~/AGENTS.md:\n\nI like short answers.") < text.index("From AGENTS.md:\n\nUse uv.")
    assert "From CLAUDE.md" not in text  # the same text as AGENTS.md beside it: read once
    assert "Some directories have guidance of their own: engine/AGENTS.md. Before you work" in text
    assert "Engine." not in text
    assert place([], root=root, home=home) == ""


def test_rules_apply_as_their_frontmatter_says(tmp_path: Path) -> None:
    files = _tree(
        tmp_path,
        {
            "plain.md": "Always use type hints.",  # no frontmatter: always (Claude Code's rules)
            "api.md": '---\npaths:\n  - "src/api/**/*.ts"\n---\nValidate inputs.',
            "db.mdc": "---\ndescription: Database conventions\nglobs: src/db/**, migrations/*\n"
            "alwaysApply: false\n---\nx",
            "style.mdc": "---\ndescription: How we name things\nalwaysApply: false\n---\nx",
            "core.mdc": "---\nalwaysApply: true\n---\nNever print secrets.",
            "manual.mdc": "---\nalwaysApply: false\n---\nOnly when asked.",  # Cursor's manual rule
        },
    )
    text = rules(files, root=tmp_path, home=tmp_path / "nowhere")
    assert (
        "From plain.md:\n\nAlways use type hints." in text
        and "From core.mdc:\n\nNever print secrets." in text
    )
    assert "api.md (for src/api/**/*.ts)" in text and "db.mdc (for src/db/**, migrations/*)" in text
    assert "Rules to read when what they are for bears on your work: style.mdc (How we name things)." in text
    assert "manual.mdc" not in text and "Only when asked" not in text


def test_frontmatter_reads_the_shapes_rule_files_use() -> None:
    said, body = frontmatter(
        '---\npaths: ["a/**", "b/*"]\ndescription: "Quoted"\nlist:\n  - one\n  - two\n---\nBody'
    )
    assert (
        said == {"paths": ["a/**", "b/*"], "description": "Quoted", "list": ["one", "two"]} and body == "Body"
    )
    assert frontmatter("No frontmatter") == ({}, "No frontmatter")
    assert rule("r.md", "---\nglobs: x/*\n---\n").applies == "paths"


def test_whole_and_named(tmp_path: Path) -> None:
    files = _tree(tmp_path, {"NOTES.md": "Remember this.", "EMPTY.md": "  "})
    assert whole(files, root=tmp_path, home=tmp_path) == "From NOTES.md:\n\nRemember this."
    assert (
        named(files, root=tmp_path, home=tmp_path)
        == "Files to read when they bear on your work: NOTES.md, EMPTY.md."
    )
    assert named([], root=tmp_path, home=tmp_path) == ""


def test_place_touched_gives_the_guidance_covering_a_file_opened_broadest_first(tmp_path: Path) -> None:
    home, root = tmp_path / "home", tmp_path / "project"
    files = _tree(
        root,
        {
            "AGENTS.md": "Root.",  # in the prompt already: never given on touch
            "src/AGENTS.md": "Src.",
            "src/db/AGENTS.md": "Db.",
            "src/db/CLAUDE.md": "Db.",  # the same text beside it: once
            "src/ui/AGENTS.md": "Ui.",
        },
    )
    told = place_touched(files, [root / "src/db/models.py"], root=root, home=home)
    assert list(told) == [root / "src/AGENTS.md", root / "src/db/AGENTS.md"]
    assert told[root / "src/db/AGENTS.md"] == (
        "From src/db/AGENTS.md, guidance for work under src/db/, where it wins over the guidance "
        "before it:\n\nDb."
    )
    assert place_touched(files, [root / "README.md"], root=root, home=home) == {}


def test_rules_touched_gives_each_rule_whose_paths_match_a_file_opened(tmp_path: Path) -> None:
    files = _tree(
        tmp_path,
        {
            "api.md": '---\npaths:\n  - "src/api/**/*.ts"\n---\nValidate inputs.',
            "db.mdc": "---\nglobs: src/db/**, migrations/*\n---\nUse the session.",
            "tsx.mdc": "---\nglobs: *.tsx\n---\nHooks only.",
            "always.md": "Always.",  # in the prompt already
            "asked.mdc": "---\ndescription: naming\n---\nx",
        },
    )
    root = tmp_path
    told = rules_touched(files, [root / "src/db/models.py", root / "web/App.tsx"], root=root, home=root)
    assert set(told) == {root / "db.mdc", root / "tsx.mdc"}
    assert told[root / "db.mdc"] == ("From db.mdc, a rule for src/db/**, migrations/*:\n\nUse the session.")
    assert "api.md" not in str(rules_touched(files, [root / "src/api/x.js"], root=root, home=root))
    assert set(rules_touched(files, [root / "src/api/v1/x.ts"], root=root, home=root)) == {root / "api.md"}


def test_a_rule_s_braces_are_its_alternatives(tmp_path: Path) -> None:
    """`src/**/*.{ts,tsx}`, as Claude Code's docs write `paths`: in a list of either form, or in a
    `globs` string, whose commas inside braces don't split a pattern."""
    files = _tree(
        tmp_path,
        {
            "ts.md": '---\npaths:\n  - "src/**/*.{ts,tsx}"\n---\nTypes.',
            "inline.md": '---\npaths: ["{web,app}/**/*.{css,scss}", "*.md"]\n---\nStyles.',
            "cursor.mdc": "---\nglobs: src/**/*.{ts,tsx}, lib/{a,b}/*.py\n---\nBoth.",
            "nested.mdc": "---\nglobs: docs/{api,{guide,howto}/*}.txt\n---\nDocs.",
            "many.mdc": "---\nglobs: " + "/".join(["{a,b}"] * 30) + "\n---\nNever.",
        },
    )
    root = tmp_path

    def told(*opened: str) -> set[str]:
        return {p.name for p in rules_touched(files, [root / o for o in opened], root=root, home=root)}

    assert told("src/ui/App.tsx") == told("src/x.ts") == {"ts.md", "cursor.mdc"}
    assert told("src/x.js") == set() and told("web/x.ts") == set()
    assert told("app/theme/main.scss") == told("web/a.css") == {"inline.md"}
    assert told("lib/b/x.py") == {"cursor.mdc"} and told("lib/c/x.py") == set()
    assert told("docs/api.txt") == told("docs/howto/x.txt") == {"nested.mdc"}
    assert told("docs/guide.txt") == set()
    assert told("README.md") == {"inline.md"}  # its `*.md`, at any depth
    # thirty groups are 2**30 ways, tried a bounded number of them: it ends, matching nothing here
    assert told("a/b/c.py") == set()
    # read as written: each rule's patterns whole, and named as they are
    assert rule("c.mdc", "---\nglobs: src/**/*.{ts,tsx}, lib/*\n---\n").paths == (
        "src/**/*.{ts,tsx}",
        "lib/*",
    )
    assert frontmatter('---\npaths: ["a/{b,c}", d]\n---\n')[0] == {"paths": ["a/{b,c}", "d"]}
    text = rules(files[:3], root=root, home=root)
    assert "cursor.mdc (for src/**/*.{ts,tsx}, lib/{a,b}/*.py)" in text
    assert "inline.md (for {web,app}/**/*.{css,scss}, *.md)" in text
    said = rules_touched(files, [root / "src/x.ts"], root=root, home=root)
    assert (
        said[root / "cursor.mdc"] == "From cursor.mdc, a rule for src/**/*.{ts,tsx}, lib/{a,b}/*.py:\n\nBoth."
    )


def test_bh_02_s_own_functions_follow_no_link_in_the_project_but_one_to_another_of_their_files(
    tmp_path: Path,
) -> None:
    """However a link to a secret came to be among a section's files (made after they were
    checked), none of bh-02's own functions reads through it; a link to another of the files
    they were given (a CLAUDE.md linking to the AGENTS.md beside it) is read as that file."""
    home, root = tmp_path / "home", tmp_path / "project"
    secret = _tree(home, {".ssh/id_test": "FAKE-KEY"})[0]
    agents = _tree(root, {"src/AGENTS.md": "Below."})[0]
    (root / "src/CLAUDE.md").symlink_to("AGENTS.md")
    assert whole([root / "src/CLAUDE.md", agents], root=root, home=home) == (
        "From src/CLAUDE.md:\n\nBelow.\n\nFrom src/AGENTS.md:\n\nBelow."
    )
    for name in ("AGENTS.md", "src/db/AGENTS.md", "rule.md"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).symlink_to(secret)
    opened = [root / "src/db/x.py"]
    calls: list[Callable[[], object]] = [
        lambda: place([root / "AGENTS.md"], root=root, home=home),
        lambda: place_touched([root / "src/db/AGENTS.md"], opened, root=root, home=home),
        lambda: rules([root / "rule.md"], root=root, home=home),
        lambda: rules_touched([root / "rule.md"], opened, root=root, home=home),
        lambda: whole([root / "rule.md"], root=root, home=home),
    ]
    for call in calls:
        with pytest.raises(OSError, match="so bh-02 did not read it"):
            call()

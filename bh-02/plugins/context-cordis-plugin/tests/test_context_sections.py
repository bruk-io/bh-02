"""bh-02's own section functions, over files in a temporary home and project."""

from pathlib import Path

from context_cordis_plugin import frontmatter, named, place, rule, rules, whole


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

"""Rule files as Claude Code reads them: `paths` frontmatter, and the patterns it matches."""

from pathlib import PurePath

from memory_cordis_plugin import Rule, frontmatter, matches, rule


def test_a_rule_is_for_the_paths_its_frontmatter_names_or_for_everything() -> None:
    assert rule("Always use type hints.") == Rule((), "Always use type hints.")
    assert rule('---\npaths:\n  - "src/api/**/*.ts"\n---\nValidate inputs.') == Rule(
        ("src/api/**/*.ts",), "Validate inputs."
    )
    assert rule("---\npaths: src/**/*.{ts,tsx}, lib/*\n---\nBoth.").paths == ("src/**/*.{ts,tsx}", "lib/*")


def test_frontmatter_reads_the_shapes_rule_files_use() -> None:
    said, body = frontmatter(
        '---\npaths: ["a/**", "b/*"]\ndescription: "Quoted"\nlist:\n  - one\n  - two\n---\nBody'
    )
    assert (
        said == {"paths": ["a/**", "b/*"], "description": "Quoted", "list": ["one", "two"]} and body == "Body"
    )
    assert frontmatter("No frontmatter") == ({}, "No frontmatter")
    assert frontmatter('---\npaths: ["a/{b,c}", d]\n---\n')[0] == {"paths": ["a/{b,c}", "d"]}


def test_a_pattern_matches_from_the_root_or_with_no_slash_at_any_depth() -> None:
    assert matches(PurePath("src/api/v1/x.ts"), "src/api/**/*.ts")
    assert not matches(PurePath("src/api/x.js"), "src/api/**/*.ts")
    assert matches(PurePath("web/App.tsx"), "*.tsx") and matches(PurePath("App.tsx"), "*.tsx")
    assert matches(PurePath("src/db/models.py"), "./src/db/**")


def test_a_rule_s_braces_are_its_alternatives() -> None:
    """`src/**/*.{ts,tsx}`, as Claude Code's docs write `paths`; a group inside another is one
    alternative too, and thirty groups (2**30 ways) are tried a bounded number of times."""
    assert matches(PurePath("src/ui/App.tsx"), "src/**/*.{ts,tsx}") and matches(
        PurePath("src/x.ts"), "src/**/*.{ts,tsx}"
    )
    assert not matches(PurePath("src/x.js"), "src/**/*.{ts,tsx}")
    assert matches(PurePath("app/theme/main.scss"), "{web,app}/**/*.{css,scss}")
    assert matches(PurePath("docs/howto/x.txt"), "docs/{api,{guide,howto}/*}.txt")
    assert not matches(PurePath("docs/guide.txt"), "docs/{api,{guide,howto}/*}.txt")
    assert not matches(PurePath("a/b/c.py"), "/".join(["{a,b}"] * 30))

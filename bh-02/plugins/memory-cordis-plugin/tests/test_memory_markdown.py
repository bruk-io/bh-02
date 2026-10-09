"""What Claude Code reads in a memory file: its imports, and its text with comments taken out."""

from memory_cordis_plugin import imports, uncommented, without_trailing


def test_an_import_is_at_a_lines_start_or_after_whitespace() -> None:
    text = "See @README for an overview and @package.json for commands.\n- git @docs/git.md\n@~/mine.md"
    assert imports(text) == ["README", "package.json", "docs/git.md", "~/mine.md"]
    assert imports("Mail name@example.com, or (@docs/a.md)") == ["docs/a.md)"]  # resolved without the ")"


def test_code_and_quotes_are_not_imports() -> None:
    text = (
        "Write `@README` to mention it.\n```\n@inside/a.md\n```\n~~~~\n@also.md\n~~~~\n"
        'Then @"quoted.md" and @after.md'
    )
    assert imports(text) == ["after.md"]


def test_a_space_in_a_path_is_written_with_a_backslash() -> None:
    assert imports(r"- API conventions @Design\ Docs/api.md here") == ["Design Docs/api.md"]
    assert imports("@Design Docs/api.md") == ["Design"]  # the path ends at the first plain space


def test_a_sentence_s_punctuation_after_an_import_can_be_taken_off() -> None:
    assert without_trailing("README.") == "README" and without_trailing("a.md),") == "a.md"


def test_block_level_comments_are_taken_out_and_the_rest_stays() -> None:
    text = (
        "Keep.\n<!-- maintainer notes -->\nAlso keep.\n  <!-- a comment\n  across lines -->\n"
        "Inline <!-- stays --> here.\n<!-- stays --> with text after.\n```\n<!-- in code -->\n```\nEnd.\n"
    )
    assert uncommented(text) == (
        "Keep.\nAlso keep.\nInline <!-- stays --> here.\n<!-- stays --> with text after.\n"
        "```\n<!-- in code -->\n```\nEnd.\n"
    )

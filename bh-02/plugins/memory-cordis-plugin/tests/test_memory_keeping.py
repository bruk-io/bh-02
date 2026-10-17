"""The `memory` tool, as pure functions: what a call is understood to ask (or why it is refused,
saying what to fix), how a memory is written, and how MEMORY.md's lines for it are kept while the
lines a person wrote are left as they are."""

from typing import Any

import pytest

from memory_cordis_plugin import MEMORY, Delete, Read, Save, frontmatter, topic_text, understood, with_line

_SAVE: dict[str, Any] = {
    "action": "save",
    "name": "prefers-tabs",
    "type": "feedback",
    "description": "Tabs, not spaces, in this project",
    "body": "Use tabs.\n\n**Why:** the person said so.\n**How to apply:** every edit.",
}


def test_the_spec_names_the_three_actions_and_what_each_needs() -> None:
    assert MEMORY["name"] == "memory"
    properties = MEMORY["parameters"]["properties"]
    assert properties["action"]["enum"] == ["save", "read", "delete"]
    assert properties["type"]["enum"] == ["user", "feedback", "project", "reference"]
    assert MEMORY["parameters"]["required"] == ["action", "name"]


def test_a_save_is_understood_with_what_it_will_write() -> None:
    assert understood(_SAVE) == Save(
        "prefers-tabs", "feedback", "Tabs, not spaces, in this project", _SAVE["body"]
    )
    padded = understood({**_SAVE, "description": "  one line  ", "body": "\n  text \n\n"})
    assert padded == Save("prefers-tabs", "feedback", "one line", "text")


def test_a_read_and_a_delete_need_only_a_name() -> None:
    assert understood({"action": "read", "name": "prefers-tabs"}) == Read("prefers-tabs")
    assert understood({"action": "delete", "name": "prefers-tabs", "body": "ignored"}) == Delete(
        "prefers-tabs"
    )


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("Prefers Tabs", id="capitals-and-a-space"),
        pytest.param("prefers_tabs", id="underscore"),
        pytest.param("-tabs", id="leading-hyphen"),
        pytest.param("tabs-", id="trailing-hyphen"),
        pytest.param("two--hyphens", id="double-hyphen"),
        pytest.param("../escape", id="parent-directory"),
        pytest.param("a/b", id="a-path"),
        pytest.param("tabs.md", id="extension"),
        pytest.param("", id="empty"),
        pytest.param("x" * 65, id="too-long"),
        pytest.param("memory", id="memory-md-on-a-case-insensitive-disk"),
        pytest.param(7, id="not-text"),
    ],
)
@pytest.mark.parametrize("action", ["save", "read", "delete"])
def test_a_name_that_is_not_a_slug_is_refused_saying_what_a_name_is(name: object, action: str) -> None:
    refused = understood({**_SAVE, "action": action, "name": name})
    assert isinstance(refused, str) and refused.startswith("error: ")
    assert "name" in refused and ("slug" in refused or "MEMORY.md" in refused)


@pytest.mark.parametrize("kind", [None, "", "note", "Feedback", 3])
def test_a_save_whose_type_is_unknown_is_refused_naming_the_kinds(kind: object) -> None:
    refused = understood({**_SAVE, "type": kind})
    assert isinstance(refused, str) and refused.startswith("error: ")
    assert "`type`" in refused and "user, feedback, project or reference" in refused


def test_a_save_without_a_type_is_refused_the_same_way() -> None:
    refused = understood({k: v for k, v in _SAVE.items() if k != "type"})
    assert (
        isinstance(refused, str) and "`type`" in refused and "user, feedback, project or reference" in refused
    )


@pytest.mark.parametrize(
    "description",
    [
        pytest.param("first line\nsecond line", id="newline"),
        pytest.param("first\r\nsecond", id="crlf"),
        pytest.param("first second", id="unicode-line-separator"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="blank"),
        pytest.param(None, id="missing"),
        pytest.param(["a"], id="not-text"),
    ],
)
def test_a_save_whose_description_is_not_one_line_is_refused_saying_what_to_fix(description: object) -> None:
    refused = understood({**_SAVE, "description": description})
    assert isinstance(refused, str) and refused.startswith("error: ") and "`description`" in refused
    assert "one line" in refused or "one specific line" in refused


def test_a_save_without_a_body_is_refused() -> None:
    for body in (None, "", " \n ", 5):
        refused = understood({**_SAVE, "body": body})
        assert isinstance(refused, str) and "`body`" in refused


def test_an_action_that_is_not_one_of_the_three_is_refused() -> None:
    for action in (None, "list", "SAVE", 1):
        refused = understood({**_SAVE, "action": action})
        assert isinstance(refused, str) and "save, read or delete" in refused


def test_a_topic_file_opens_with_the_three_frontmatter_keys_then_the_body() -> None:
    save = understood(_SAVE)
    assert isinstance(save, Save)
    text = topic_text(save)
    assert text.startswith(
        "---\nname: prefers-tabs\ndescription: Tabs, not spaces, in this project\ntype: feedback\n---\n"
    )
    said, body = frontmatter(text)
    assert said == {
        "name": "prefers-tabs",
        "description": "Tabs, not spaces, in this project",
        "type": "feedback",
    }
    assert body.strip() == save.body and text.endswith("\n") and not text.endswith("\n\n")


_LINE = "- [prefers-tabs](prefers-tabs.md): Tabs, not spaces, in this project"


def test_the_index_gets_a_line_for_a_new_memory_at_its_end() -> None:
    assert with_line("", "prefers-tabs", _LINE) == _LINE + "\n"
    assert (
        with_line("- [other](other.md): x\n", "prefers-tabs", _LINE) == f"- [other](other.md): x\n{_LINE}\n"
    )


def test_a_line_that_ends_the_index_with_no_newline_is_kept_and_a_newline_follows_it() -> None:
    assert with_line("- by hand", "prefers-tabs", _LINE) == f"- by hand\n{_LINE}\n"


def test_a_memory_has_one_line_which_a_second_save_replaces_where_it_stands() -> None:
    index = f"- [a](a.md): first\n{_LINE}\n- [b](b.md): last\n"
    changed = "- [prefers-tabs](prefers-tabs.md): changed"
    assert with_line(index, "prefers-tabs", changed) == f"- [a](a.md): first\n{changed}\n- [b](b.md): last\n"
    twice = f"{_LINE}\n- [a](a.md): between\n{_LINE}\n"  # a duplicate made by hand: one line remains
    assert with_line(twice, "prefers-tabs", changed) == f"{changed}\n- [a](a.md): between\n"


def test_a_delete_takes_out_its_lines_and_no_others() -> None:
    index = f"- [a](a.md): first\n{_LINE}\n- [b](b.md): last\n"
    assert with_line(index, "prefers-tabs", None) == "- [a](a.md): first\n- [b](b.md): last\n"
    assert with_line(index, "absent", None) == index


def test_lines_a_person_wrote_are_kept_as_they_are() -> None:
    """Nothing but the lines that link a memory's own file are touched: a heading, a note, a link
    to a page, a line for a file that is not there, odd line ends and bytes alike."""
    by_hand = (
        "# Memory\r\n"
        "\r\n"
        "Read this first. Then the rest.\n"
        "- [A page](https://example.com/page): points at no topic file\n"
        "- [Old note](old-note.md): written by hand, and no such file\n"
        "  - nested [x](prefers-tabs.md) is not at its start\n"
        "- caf\udce9 in a byte that is not UTF-8\n"
    )
    added = with_line(by_hand, "prefers-tabs", _LINE)
    assert added == by_hand + _LINE + "\n"
    assert with_line(added, "prefers-tabs", None) == by_hand


def test_a_description_that_links_another_memory_does_not_make_its_line_that_memory_s() -> None:
    mention = "- [mention](mention.md): see [other](other.md)"
    index = f"- [other](other.md): the real one\n{mention}\n"
    assert with_line(index, "other", None) == mention + "\n"


def test_a_bullet_may_be_a_star_or_a_plus_or_none_and_the_title_anything() -> None:
    for line in (
        "* [Tabs](prefers-tabs.md) - hook",
        "+ [Use tabs](prefers-tabs.md): hook",
        "[x](prefers-tabs.md)",
    ):
        assert with_line(f"{line}\nkept\n", "prefers-tabs", None) == "kept\n"

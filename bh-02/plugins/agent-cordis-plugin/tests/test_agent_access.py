"""The `access` broker: what is asked before a file is read or written."""

import pytest

from agent_cordis_plugin import Access, access
from cordis.testing import drive


def test_it_names_the_kinds_some_function_is_asked_about() -> None:
    """A tool need not ask about a kind nothing would refuse: with no function, nothing is asked."""
    broker = Access()
    assert broker.asking() == ()
    remove = broker.before_write(lambda path: None)
    assert broker.asking() == ("write",)
    broker.before_read(lambda path: None)
    assert broker.asking() == ("read", "write")
    remove()
    assert broker.asking() == ("read",)


def test_a_refusal_is_every_function_s_refusal_sorted_and_none_when_all_let_it_go_ahead() -> None:
    broker = Access()
    broker.before_write(lambda path: "zebra says no" if path.endswith(".lock") else None)
    broker.before_write(lambda path: "apple says no" if path.endswith(".lock") else "")
    assert broker.refusal("write", "/p/x.py") is None
    assert broker.refusal("write", "/p/x.lock") == "apple says no\n\nzebra says no"
    assert broker.refusal("read", "/p/x.lock") is None  # the writes' functions are not asked about reads


def test_a_function_that_fails_refuses_saying_so() -> None:
    """A check that could not be made is not a yes."""

    def broken(path: str) -> str | None:
        raise OSError("rules unreadable")

    broker = Access()
    broker.before_read(broken)
    said = broker.refusal("read", "/p/x.py")
    assert said is not None and said.startswith("bh-02 could not check it (")
    assert "broken failed: rules unreadable); tell the person" in said
    with pytest.raises(ValueError, match="'read' or 'write', not 'delete'"):
        broker.refusal("delete", "/p/x.py")


async def test_the_access_row_binds_an_empty_broker() -> None:
    effects = await drive(access())
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "access")]
    assert isinstance(effects[0].args[1], Access) and effects[0].args[1].asking() == ()

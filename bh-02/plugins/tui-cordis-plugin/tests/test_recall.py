"""`recall`: the lines sent this run and the steps through them, pure."""

from tui_cordis_plugin.recall import Recall, newer, older, recalled, remember


def _sent(*lines: str) -> Recall:
    recall = Recall()
    for line in lines:
        recall = remember(recall, line)
    return recall


def test_a_line_sent_is_the_newest_and_the_person_is_writing_again() -> None:
    walking = older(_sent("a", "b"), "draft")
    assert walking is not None
    after = remember(walking.recall, "c")
    assert after == Recall(("a", "b", "c"))  # no longer at a line, no draft kept


def test_older_walks_back_from_the_newest_keeping_the_draft_until_the_oldest() -> None:
    first = older(_sent("a", "b", "c"), "my draft")
    assert first is not None and first.text == "c" and first.recall.draft == "my draft"
    second = older(first.recall, "c")  # the text shown is not the draft
    assert second is not None and second.text == "b" and second.recall.draft == "my draft"
    third = older(second.recall, "b")
    assert third is not None and third.text == "a"
    assert older(third.recall, "a") is None  # nothing older than the oldest


def test_nothing_sent_gives_no_step_either_way() -> None:
    assert older(Recall(), "typing") is None
    assert newer(Recall()) is None


def test_newer_walks_forward_and_past_the_newest_gives_the_draft_back() -> None:
    first = older(_sent("a", "b"), "my draft")
    assert first is not None
    second = older(first.recall, "b")
    assert second is not None and second.text == "a"
    forward = newer(second.recall)
    assert forward is not None and forward.text == "b"
    back = newer(forward.recall)
    assert back is not None and back.text == "my draft"
    assert back.recall == Recall(("a", "b"))  # writing their own text again, the draft handed back
    assert newer(back.recall) is None


def test_the_lines_sent_are_never_changed_in_place() -> None:
    sent = _sent("a", "b")
    walking = older(sent, "")
    assert walking is not None
    edited = remember(walking.recall, "b, edited")
    assert edited.sent == ("a", "b", "b, edited")
    assert sent.sent == ("a", "b")  # the old value is untouched, as a frozen value must be


def test_recalled_is_a_line_shown_as_it_was_sent_and_not_once_edited() -> None:
    walking = older(_sent("/model"), "")
    assert walking is not None
    assert recalled(walking.recall, "/model")
    assert not recalled(walking.recall, "/model ")  # edited: the person's own again
    assert not recalled(_sent("/model"), "/model")  # not walking: it is just text

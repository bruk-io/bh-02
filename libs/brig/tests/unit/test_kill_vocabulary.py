"""Unit tests for KillItem vocabulary closure and validation.

decision-054: the vocabulary of KillItem.kind is a closed set, pinned as
data in brig/run/teardown.KILL_ITEM_KINDS, and a KillItem constructed with
a kind outside the vocabulary must fail. The vocabulary set is verified by
a unit test that asserts set equality, not membership — both adding and
dropping a kind is loud.
"""

from __future__ import annotations

import pytest

from brig.run.teardown import KILL_ITEM_KINDS, KillItem, KillOutcome


@pytest.mark.unit
class TestKillItemVocabularyClosure:
    """Acceptance Criterion #1: set-equality pin."""

    def test_kill_item_kinds_has_exactly_four_values(self) -> None:
        """KILL_ITEM_KINDS contains exactly the kinds named by SPEC.md §9.
        Five until decision-154 (2026-09-08) deleted the `tmux` launcher
        and `"pane"` with it: nothing can produce one now, and a kind
        nothing produces is a vocabulary entry that lies about what a
        report can contain."""
        expected = {"workload_group", "exec_sibling", "helper", "container"}
        assert set(KILL_ITEM_KINDS) == expected

    def test_kill_item_kinds_is_tuple_in_exact_order(self) -> None:
        """KILL_ITEM_KINDS is a tuple (not just any iterable) in the exact
        order the spec lists them: workload_group, exec_sibling, helper,
        container. This is load-bearing for audit trails and report
        ordering."""
        expected_order = ("workload_group", "exec_sibling", "helper", "container")
        assert expected_order == KILL_ITEM_KINDS
        assert isinstance(KILL_ITEM_KINDS, tuple)


@pytest.mark.unit
class TestKillItemVocabularyMutation:
    """Acceptance Criterion #2: mutation checks (to be run manually
    outside this test file).

    These tests verify the baseline behavior. The mutation checks
    (plant 'helper' deletion, add 'sandbox', revert) are run as named
    invocations and their output pasted into the task notes.
    """

    def test_vocabulary_baseline_passes(self) -> None:
        """Baseline: the vocabulary is as spec'd, both membership and
        order."""
        assert set(KILL_ITEM_KINDS) == {
            "workload_group",
            "exec_sibling",
            "helper",
            "container",
        }
        assert KILL_ITEM_KINDS == (
            "workload_group",
            "exec_sibling",
            "helper",
            "container",
        )


@pytest.mark.unit
class TestKillItemRefusalOnBadKind:
    """Acceptance Criterion #3: KillItem construction refuses kinds
    outside the vocabulary."""

    def test_kill_item_construction_raises_on_invalid_kind(self) -> None:
        """Constructing a KillItem with kind='sandbox' (outside the
        vocabulary) raises ValueError naming the bad kind and listing the
        legal ones."""
        with pytest.raises(ValueError) as exc_info:
            KillItem(kind="sandbox", identity="1234", outcome=KillOutcome.FAILED, detail="")

        error_str = str(exc_info.value)
        # AC #3: message must contain the offending kind
        assert "sandbox" in error_str
        # AC #3: message must contain every legal name. Hardcoded
        # literals, deliberately NOT `for k in KILL_ITEM_KINDS` -- iterating
        # the same tuple the message interpolates from would make this
        # assertion pass for any tuple's contents, coupling it to AC #1's
        # pin instead of standing alone (ATTEMPT 1 VERIFIER's reservation).
        assert "workload_group" in error_str
        assert "exec_sibling" in error_str
        assert "helper" in error_str
        assert "container" in error_str

    def test_kill_item_construction_raises_on_unknown_kind(self) -> None:
        """Another invalid kind also raises ValueError with the bad kind
        and legal names in the message."""
        with pytest.raises(ValueError) as exc_info:
            KillItem(
                kind="zombie_reaper",
                identity="5678",
                outcome=KillOutcome.ENDED,
                detail="",
            )

        error_str = str(exc_info.value)
        assert "zombie_reaper" in error_str
        # Hardcoded literals; see the comment in the test above.
        assert "workload_group" in error_str
        assert "exec_sibling" in error_str
        assert "helper" in error_str
        assert "container" in error_str


@pytest.mark.unit
class TestKillItemControlAllLegalKinds:
    """Acceptance Criterion #4: control for the refusal test. Every legal
    kind constructs successfully."""

    def test_kill_item_construction_succeeds_for_workload_group(self) -> None:
        """workload_group is a legal kind."""
        item = KillItem(
            kind="workload_group",
            identity="1234",
            outcome=KillOutcome.ENDED,
            detail="",
        )
        assert item.kind == "workload_group"
        assert item.identity == "1234"
        assert item.outcome is KillOutcome.ENDED

    def test_kill_item_construction_succeeds_for_exec_sibling(self) -> None:
        """exec_sibling is a legal kind."""
        item = KillItem(
            kind="exec_sibling",
            identity="5678",
            outcome=KillOutcome.ENDED,
            detail="",
        )
        assert item.kind == "exec_sibling"

    def test_kill_item_construction_succeeds_for_helper(self) -> None:
        """helper is a legal kind."""
        item = KillItem(
            kind="helper",
            identity="9999",
            outcome=KillOutcome.ALREADY_GONE,
            detail="",
        )
        assert item.kind == "helper"

    def test_kill_item_construction_succeeds_for_helper_when_failed(self) -> None:
        """The FAILED outcome constructs too -- the case `"pane"` used to
        carry before decision-154 deleted that kind."""
        item = KillItem(
            kind="helper",
            identity="2222",
            outcome=KillOutcome.FAILED,
            detail="details",
        )
        assert item.outcome is KillOutcome.FAILED

    def test_kill_item_construction_succeeds_for_container(self) -> None:
        """container is a legal kind."""
        item = KillItem(
            kind="container",
            identity="3333",
            outcome=KillOutcome.ENDED,
            detail="details",
        )
        assert item.kind == "container"

    def test_all_five_legal_kinds_construct_without_error(self) -> None:
        """All five legal kinds can be constructed in one loop, proving
        the refusal test distinguishes 'raises on bad kind' from 'raises
        on every kind'."""
        for kind in KILL_ITEM_KINDS:
            item = KillItem(
                kind=kind,
                identity="test_id",
                outcome=KillOutcome.ENDED,
                detail="",
            )
            assert item.kind == kind

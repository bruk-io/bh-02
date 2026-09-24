"""Tests for brig.core.signatures: AxisClaim, SignatureBook, denial_subject.

SPEC.md §6 (the normalized denial subject: stderr, then a canonical
termination summary line carrying `signal:...`/`exit:...` tokens; "a
signature must match the real token and must NOT match a generic failure"),
§12 (the empty signatures tuple is a routing fact, not a gap), §13 (the book
lives in core because probe may not import mech).
"""

import re
import signal

import pytest

from brig.core.grades import Axis
from brig.core.signatures import AxisClaim, SignatureBook, denial_subject

# rlimits' own denial signature, quoted here as a LITERAL string rather than
# imported from brig.mech.rlimits -- core may not import mech (SPEC.md §13),
# and this test lives in the unit tier for brig.core, so it must not reach
# into brig.mech even for a value. Source of truth: brig/mech/rlimits.py's
# `_DENIAL_SIGNATURE = re.compile(r"signal:SIGXCPU")`.
_RLIMITS_DENIAL_SIGNATURE = re.compile(r"signal:SIGXCPU")


@pytest.mark.unit
def test_denial_subject_renders_a_signal_termination() -> None:
    """AC #2: a negative returncode renders as `signal:<NAME>`. 24 is
    SIGXCPU on darwin; asserted via signal.SIGXCPU, not the literal 24, so
    this test states the real relationship rather than hard-coding a
    platform-specific number."""
    subject = denial_subject("boom", -signal.SIGXCPU)
    assert subject.endswith(f"signal:{signal.SIGXCPU.name}")
    assert subject.endswith("signal:SIGXCPU")


@pytest.mark.unit
def test_denial_subject_renders_an_exit_status() -> None:
    """AC #2: a non-negative returncode renders as `exit:<n>`."""
    subject = denial_subject("", 137)
    assert subject.endswith("exit:137")


@pytest.mark.unit
def test_denial_subject_renders_an_unnamed_signal_as_its_number() -> None:
    """denial_subject's documented fallback: a signal number Python's
    `signal` module does not name renders as `signal:<n>`, not a crash.
    9999 is not a signal any platform defines, so `signal.Signals(9999)`
    reliably raises ValueError, exercising the fallback branch."""
    unnamed_signal_number = 9999
    subject = denial_subject("", -unnamed_signal_number)
    assert subject.endswith(f"signal:{unnamed_signal_number}")


@pytest.mark.unit
def test_rlimits_signature_matches_its_own_token() -> None:
    """AC #3, direction one: rlimits' quoted signature matches
    denial_subject's rendering of its own SIGXCPU termination."""
    subject = denial_subject("", -signal.SIGXCPU)
    assert _RLIMITS_DENIAL_SIGNATURE.search(subject) is not None


@pytest.mark.unit
def test_rlimits_signature_does_not_match_generic_failures() -> None:
    """AC #3, direction two (the anti-vacuous rule,
    .claude/rules/unit-tests.md: "must NOT match generic failures"):
    rlimits' SIGXCPU signature must not match an unrelated command-not-found
    or file-not-found failure, in either of two different shapes -- a
    signature that matched these would manufacture false PASSes for probes
    that merely failed for the wrong reason (SPEC.md §12: VACUOUS, not
    PASS)."""
    command_not_found = denial_subject("sh: nosuchcmd: command not found", 127)
    assert _RLIMITS_DENIAL_SIGNATURE.search(command_not_found) is None

    file_not_found = denial_subject("cat: /nope: No such file or directory", 1)
    assert _RLIMITS_DENIAL_SIGNATURE.search(file_not_found) is None


@pytest.mark.unit
def test_signature_book_roundtrips_through_pattern_sources() -> None:
    """AC #4: from_list(book.to_list()) == book, for a book carrying both a
    compiled-pattern claim and an empty-signature claim (SPEC.md §12: the
    empty tuple is a routing fact a mechanism like env_scrub declares, not a
    gap -- the book must carry that shape too). to_list()'s signatures are
    plain str, never re.Pattern (re.Pattern is not JSON-serializable)."""
    book = SignatureBook(
        claims=(
            AxisClaim(
                axis=Axis.LIMITS,
                mechanism="rlimits",
                signatures=(_RLIMITS_DENIAL_SIGNATURE,),
            ),
            AxisClaim(
                axis=Axis.ENV,
                mechanism="env_scrub",
                signatures=(),
            ),
        )
    )

    serialized = book.to_list()
    for entry in serialized:
        signatures = entry["signatures"]
        assert isinstance(signatures, list)
        for signature in signatures:
            assert isinstance(signature, str)

    # re.purge() clears CPython's internal compiled-pattern cache, which is
    # the discriminating control: it rules out an equality that only held
    # because from_list()'s re.compile(source) happened to hand back the
    # SAME cached object as book's own pattern, rather than a genuinely
    # equal one built from the serialized source string.
    re.purge()
    assert SignatureBook.from_list(serialized) == book


@pytest.mark.unit
def test_signature_book_refuses_a_duplicate_axis() -> None:
    """AC #5: two claims on the same axis do not construct; the error names
    the axis. Control in the same test: two claims on DIFFERENT axes
    construct fine, proving the refusal is about the duplicate axis and not
    about having more than one claim."""
    with pytest.raises(ValueError, match="limits"):
        SignatureBook(
            claims=(
                AxisClaim(axis=Axis.LIMITS, mechanism="rlimits", signatures=()),
                AxisClaim(axis=Axis.LIMITS, mechanism="systemd_scope", signatures=()),
            )
        )

    # Control: different axes construct.
    book = SignatureBook(
        claims=(
            AxisClaim(axis=Axis.LIMITS, mechanism="rlimits", signatures=()),
            AxisClaim(axis=Axis.ENV, mechanism="env_scrub", signatures=()),
        )
    )
    assert book.for_axis(Axis.LIMITS) is not None
    assert book.for_axis(Axis.ENV) is not None
    assert book.for_axis(Axis.NETWORK) is None


@pytest.mark.unit
def test_signature_book_from_list_refuses_malformed_entries() -> None:
    """from_list is a deserialization boundary (task-047 feeds it rehydrated
    Handle data), so it refuses with a named ValueError rather than an
    assert -- the same posture Event.from_json_line takes in
    brig/core/events.py, and one an assert loses under `python -O`."""
    with pytest.raises(ValueError, match="axis"):
        SignatureBook.from_list([{"axis": 7, "mechanism": "rlimits", "signatures": []}])

    with pytest.raises(ValueError, match="mechanism"):
        SignatureBook.from_list([{"axis": "limits", "mechanism": 7, "signatures": []}])

    with pytest.raises(ValueError, match="signatures"):
        SignatureBook.from_list([{"axis": "limits", "mechanism": "rlimits", "signatures": "x"}])

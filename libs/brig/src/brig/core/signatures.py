"""The denial-signature book: `AxisClaim`, `SignatureBook`, and
`denial_subject`, SPEC.md §6's classification subject as pure data and a
pure function.

Per SPEC.md §13's layer table, `mech` declares each mechanism's own denial
signatures (`Step.denial_signatures`); this module holds the vocabulary a
higher layer assembles them into (a `SignatureBook`, one `AxisClaim` per
claimed axis) and the pure function (`denial_subject`) that builds the
string a signature is matched against. Both live in `core`, alongside
`brig.core.probes`, for the same reason: `probe` may not import `mech`
(SPEC.md §13), so the book it reads has to be built by something else and
handed to it as data -- the same shape `Graded` and `Event` already ship.

This module is pure: no I/O, no clock, no randomness, no subprocess. `re`
and `signal` are both closed, deterministic stdlib modules -- `re.compile`
does no I/O, and `signal.Signals` is a pure name lookup against a fixed
table, not a call that touches the process's actual signal handlers.
"""

from __future__ import annotations

import re
import signal
from dataclasses import dataclass

from brig.core.grades import Axis


@dataclass(frozen=True, slots=True)
class AxisClaim:
    """One mechanism's denial-signature claim on one axis.

    Attributes:
        axis: Which of the seven axes this claim is about.
        mechanism: The claiming mechanism's name (`brig.mech`'s
            `Mechanism.name`, quoted as a plain `str` here rather than
            imported -- `core` may not import `mech`, SPEC.md §13).
        signatures: The mechanism's `denial_signatures`
            (`brig.mech.Step.denial_signatures`), copied in as compiled
            patterns. The empty tuple is a routing fact, not a gap
            (SPEC.md §12, decision-068/decision-099): a mechanism with
            nothing to match by signature has its axis proved by an
            `ABSENCE` probe plus the battery's `CONTROL` instead.
    """

    axis: Axis
    mechanism: str
    signatures: tuple[re.Pattern[str], ...]


@dataclass(frozen=True, slots=True)
class SignatureBook:
    """Every mechanism's `AxisClaim`, one per axis, assembled from a stack's
    compiled `Step`s.

    A duplicate axis does not construct: two claims on the same axis is the
    same claim-conflict shape SPEC.md §7 already refuses for grades, applied
    here to signatures.
    """

    claims: tuple[AxisClaim, ...]

    def __post_init__(self) -> None:
        seen: dict[Axis, str] = {}
        for claim in self.claims:
            prior_mechanism = seen.get(claim.axis)
            if prior_mechanism is not None:
                raise ValueError(
                    f"SignatureBook: duplicate claim for axis {claim.axis.value!r} "
                    f"(already claimed by {prior_mechanism!r}, and again by "
                    f"{claim.mechanism!r})"
                )
            seen[claim.axis] = claim.mechanism

    def for_axis(self, axis: Axis) -> AxisClaim | None:
        """This book's claim on `axis`, or `None` if nothing claims it."""
        for claim in self.claims:
            if claim.axis is axis:
                return claim
        return None

    def to_list(self) -> list[dict[str, object]]:
        """Serialize to plain data: pattern *sources* (`str`), never
        `re.Pattern` objects, because `re.Pattern` is not JSON-serializable.
        """
        return [
            {
                "axis": claim.axis.value,
                "mechanism": claim.mechanism,
                "signatures": [pattern.pattern for pattern in claim.signatures],
            }
            for claim in self.claims
        ]

    @classmethod
    def from_list(cls, data: list[dict[str, object]]) -> SignatureBook:
        """Inverse of `to_list`: `re.compile` each pattern source on read."""
        claims = []
        for entry in data:
            axis_value = entry["axis"]
            if not isinstance(axis_value, str):
                raise ValueError(
                    f"SignatureBook.from_list: 'axis' must be a str, got {axis_value!r}"
                )
            mechanism = entry["mechanism"]
            if not isinstance(mechanism, str):
                raise ValueError(
                    f"SignatureBook.from_list: 'mechanism' must be a str, got {mechanism!r}"
                )
            signature_sources = entry["signatures"]
            if not isinstance(signature_sources, list):
                raise ValueError(
                    f"SignatureBook.from_list: 'signatures' must be a list, "
                    f"got {signature_sources!r}"
                )
            claims.append(
                AxisClaim(
                    axis=Axis(axis_value),
                    mechanism=mechanism,
                    signatures=tuple(re.compile(source) for source in signature_sources),
                )
            )
        return cls(claims=tuple(claims))


def denial_subject(stderr: str, returncode: int) -> str:
    """SPEC.md §6's normalized denial string: `stderr`, then a newline, then
    a canonical termination summary line.

    `returncode` is Python's own `subprocess` encoding: non-negative is an
    exit code (`exit:<n>`); negative is a signal (`-returncode` is the
    signal number), rendered `signal:<NAME>` via `signal.Signals(...).name`,
    or `signal:<n>` for a number Python's `signal` module does not name.

    The join is a single literal `\\n` between `stderr` and the termination
    line, unconditionally -- `stderr` is passed through exactly as captured,
    never stripped or rstripped. A `stderr` that already ends in its own
    trailing newline therefore produces a blank line immediately before the
    termination line; this is deliberate (the subject is `stderr` verbatim,
    not a cleaned-up version of it) and every signature match is a regex
    `search`, not `endswith`, so a blank line ahead of the termination token
    does not change what matches.
    """
    if returncode >= 0:
        termination = f"exit:{returncode}"
    else:
        signal_number = -returncode
        try:
            termination = f"signal:{signal.Signals(signal_number).name}"
        except ValueError:
            termination = f"signal:{signal_number}"
    return f"{stderr}\n{termination}"


__all__ = (
    "AxisClaim",
    "SignatureBook",
    "denial_subject",
)

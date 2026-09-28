"""`EventSource` purity and `brig/mech/`'s import surface: task-031,
decision-060, decision-069.

Three claims, each falsifiable on its own, same posture as task-028's
`tests/unit/test_core_events_purity.py`:

1. `brig/mech/`'s file set is pinned -- a new module joining the package
   cannot silently escape review.
2. Every one of those files' top-level imports is pinned EXACTLY (set
   equality, not membership), per file.
3. `EventSource` is a `Protocol`, not a `dataclass`, and its shape is
   satisfiable by both of M3's two known cases (decision-069).

**The `brig/mech/trampoline/` carve-out.** `brig/mech/__init__.py`'s own
docstring calls this module's purity claim "Pure module: no I/O, no clock,
no randomness, no subprocess" -- but `brig/mech/trampoline/` (task-035,
Done, M3) ships a program whose entire job is `resource.setrlimit` and
`os.execvp`; its own module docstring's first paragraph says so. It lives
under `brig/mech/` for namespacing -- it is the argv program the `rlimits`
mechanism's `Step.wrap` points at (`python -m brig.mech.trampoline --cpu N
-- argv...`) -- not because it is part of the "mech" CONTRACT layer SPEC.md
§6 calls pure ("mech performs no I/O of its own during compile"). That
claim is about `Mechanism.compile()` and the types compile() produces
(`Step`, `EventSource`, ...), all of which live in `brig/mech/contract.py`
alone (in `brig/mech/__init__.py` until the workspace's task-0017 moved them) -- corroborated by task-031 AC#6's own plant/revert, which names
`brig/mech/__init__.py` specifically, not the trampoline package.

So this file does NOT silently skip the trampoline package: its two files
are in `_EXPECTED_IMPORTS_BY_FILE` below, pinned exactly like every other
file, imports and all -- `os`, `resource`, `sys` included, with the reason
stated inline. What changes is only the banned-set check
(`test_only_the_mech_contract_layer_is_import_pure`), which is scoped to
`__init__.py`, the one file the purity claim is actually about.

**task-036 adds a fourth file, `rlimits.py`, forced rather than chosen.**
The file-set pin above (`test_mech_module_set_is_pinned`) goes red the
instant any file joins `brig/mech/`, including one a *different* task's own
Deliverable creates -- so extending this pin is not scope creep, it is what
the pin exists to force a reviewer of the diff to notice. `rlimits.py` is
NOT a carve-out like the trampoline package: SPEC.md §6 says `compile`
performs no I/O, and `rlimits.py`'s `Mechanism.compile` is a pure
`spec -> argv` render (`brig/mech/rlimits.py`'s own module docstring), so it
stays inside `test_only_the_mech_contract_layer_is_import_pure`'s scan
rather than joining the `_TRAMPOLINE_PREFIX` exemption. `rlimits.py` imports
`signal` and `sys` at module level -- both readable, closed-form attribute
lookups (`signal.SIGXCPU`, `sys.executable`), never syscalls, and neither
name is in `_BANNED_IMPORT_NAMES`, so their presence does not need a carve-
out of its own.

**task-058 adds two more files, `seatbelt/__init__.py` and
`seatbelt/profile.py`, forced rather than chosen -- the identical shape as
the `rlimits.py` paragraph above.** Per that paragraph's own precedent
("extending this pin is not scope creep, it is what the pin exists to
force a reviewer of the diff to notice"), the pin below is extended here.
task-058's own Deliverable lists `tests/unit/test_seatbelt_profile.py` as
its one test file and separately says every EXISTING test file is out of
scope -- but leaving this file's `test_mech_module_set_is_pinned` red is
`./scripts/verify.sh fast` failing outright (task-058 AC #10), which is
the exact "no authorized role could satisfy both" shape decision-079 names
and decision-122(3)/(4) permits an in-flight repair for, applied here by
the implementer rather than pre-authorized by an orchestrator note --
flagged in task-058's own attempt notes as a decision-113b candidate for
the orchestrator's next pass, on this established precedent rather than as
a new judgment call. Neither new file is a carve-out like the trampoline
package: `render_sbpl` is a pure `spec -> str` render (`brig/mech/seatbelt/
profile.py`'s own module docstring; task-058's AC #4 ASTs its import set
directly), so both files stay inside
`test_only_the_mech_contract_layer_is_import_pure`'s scan below rather
than joining `_TRAMPOLINE_PREFIX`.

**task-059 extends `seatbelt/__init__.py`'s own pinned import set and
`__init__.py`'s (the top-level `brig/mech/__init__.py`'s) pinned set, same
forced shape again.** task-059's Deliverable puts the `Seatbelt` mechanism
class directly in `brig/mech/seatbelt/__init__.py` (same posture as
`brig.mech.env_scrub`, one file), which needs `Axis`/`ChannelKind`/`Grade`/
`Graded`/`Spec` from `brig.core`, `ArgvTransformer`/`CompileCtx`/
`StagedFile`/`Step` from `brig.mech` itself (the identical "submodule
imports back from its own package's `__init__`" shape `rlimits.py` already
uses, one level deeper -- a package rather than a plain module -- verified
clean by `pypeeker check --strict`, not merely assumed), and `re` for its
own denial-signature pattern. `brig/mech/__init__.py`'s own bottom-of-file
import list grows one more pair (`Seatbelt`/`seatbelt`) for the same
reason `rlimits`/`env_scrub` are already there. `Seatbelt.compile` is
still a pure `spec -> Step` render -- no I/O, no clock, no subprocess -- so
both files stay inside `test_only_the_mech_contract_layer_is_import_pure`'s
scan below; `re` is not in `_BANNED_IMPORT_NAMES`.

Every mechanism (`rlimits.py`, `env_scrub.py`, `bwrap.py`, `connect_proxy.py`,
`seatbelt/__init__.py`) imports the contract from `brig.mech.contract`, never from
`brig.mech` itself. An older layout defined the contract in `brig/mech/__init__.py` and had
the mechanisms import it back from there, with `__init__` importing them at the bottom of the
file; newer pypeeker reports that as a `no-import-cycles` violation, which brig's gate runs.
The pins above hold the new shape: `contract.py` imports no mechanism, and `__init__.py`
imports only `brig.mech.*` modules (it re-exports).
"""

from __future__ import annotations

import ast
import dataclasses
import typing
from pathlib import Path
from typing import Final

import pytest

from brig.core import DataValue, EventKind
from brig.mech import EventPayload, EventSource, ExitOutcome

_MECH_ROOT = Path(__file__).resolve().parents[2] / "src" / "brig" / "mech"


#: Same helper as tests/unit/test_core_events_purity.py: only `tree.body`
#: (module-level statements) is walked, so an import nested in a function
#: or class -- a different claim entirely -- is not what this test is about.
def _top_level_imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


#: Every module file under brig/mech/, relative to brig/mech/ itself, paired
#: with the EXACT set of top-level import module names it is allowed. Pinned
#: per file (not unioned across the package) so a new module cannot silently
#: inherit an unreviewed allowance -- and the file SET itself is pinned by
#: test_mech_module_set_is_pinned, so a new module can't silently join
#: either.
_EXPECTED_IMPORTS_BY_FILE: Final[dict[str, frozenset[str]]] = {
    # The contract layer itself: every type SPEC.md §6 calls pure (`Step`,
    # `CompileCtx`, `EventSource`, ...). It imports no mechanism, and every
    # mechanism imports it directly, which is what keeps `no-import-cycles`
    # on in brig's gate (task-0017 of the workspace backlog).
    "contract.py": frozenset(
        {
            "__future__",
            "collections.abc",
            "dataclasses",
            "enum",
            "re",
            "types",
            "typing",
            "brig.core",
        }
    ),
    # Re-exports only: the contract, then each mechanism.
    "__init__.py": frozenset(
        {
            "brig.mech.contract",
            "brig.mech.bwrap",
            "brig.mech.env_scrub",
            "brig.mech.rlimits",
            "brig.mech.seatbelt",
        }
    ),
    # The carve-out (see module docstring): a program that sets rlimits and
    # execs, by design, per task-035.
    "trampoline/__init__.py": frozenset(
        {"__future__", "collections.abc", "dataclasses", "os", "resource", "sys"}
    ),
    "trampoline/__main__.py": frozenset({"__future__", "sys", "brig.mech.trampoline"}),
    # task-036: the `rlimits` mechanism. NOT a carve-out (see module
    # docstring) -- `signal`/`sys` here are pure attribute reads
    # (`signal.SIGXCPU`, `sys.executable`), never syscalls, so this file
    # stays inside the banned-import scan below.
    "rlimits.py": frozenset(
        {"__future__", "brig.core", "brig.mech.contract", "re", "signal", "sys"}
    ),
    # task-034: the `env_scrub` mechanism. NOT a carve-out either -- its
    # `compile()` is a pure spec -> argv render (the actual environment
    # values it forwards are read by `/bin/sh` at RUN time, never by this
    # module at compile time -- see `brig/mech/env_scrub.py`'s own module
    # docstring), so it stays inside the banned-import scan below too.
    # `typing` joins at decision-143: `_SCRUB_DETAIL` is a `Final` constant.
    "env_scrub.py": frozenset({"__future__", "typing", "brig.core", "brig.mech.contract"}),
    # task-058/task-059: the `seatbelt` package. NOT a carve-out (see
    # module docstring's task-058/task-059 paragraphs) -- pure, no I/O, no
    # clock -- so both files stay inside the banned-import scan below too.
    # `__init__.py` grew task-059's `Seatbelt` mechanism class on top of
    # task-058's re-exports; `profile.py` is unchanged (task-059 does not
    # own it and does not edit it).
    "seatbelt/__init__.py": frozenset(
        {
            "__future__",
            "re",
            "brig.core",
            "brig.mech.contract",
            "brig.mech.seatbelt.profile",
            # task-079/decision-136: `_AXES_OWNING_NETWORK` /
            # `_AXES_CEDING_NETWORK` are `Final`.
            "typing",
        }
    ),
    # `typing` joins the pin at task-079/decision-136: `_LOOPBACK_REMOTE` is a
    # `Final` constant, the same stdlib-typing-only shape the other rows carry.
    "seatbelt/profile.py": frozenset({"__future__", "collections.abc", "typing", "brig.core"}),
    # `bwrap.py` (2026-09-08, decision-159): the linux mechanism. NOT a
    # carve-out either -- `Bwrap.compile` is a pure `spec -> argv` render,
    # and the two filesystem facts it needs (a path's realpath'd form, and
    # whether it exists) arrive on `CompileCtx` from the `run` layer rather
    # than being fetched here, which is exactly why `os` is absent from this
    # row while `_parent()` does POSIX dirname by string. `re` is its denial
    # signatures, `typing` its `Final` constants, `collections.abc` the
    # `Mapping` its two ctx lookups take.
    "bwrap.py": frozenset(
        {"__future__", "collections.abc", "re", "typing", "brig.core", "brig.mech.contract"}
    ),
    # `connect_proxy.py` (M6). Note what is NOT here: `brig.proxy`. The
    # proxy process it starts has an empty layer row (decision-133) and
    # this mechanism may not import it, which is why the denial-signature
    # constant is duplicated and pinned equal by
    # `tests/unit/test_connect_proxy_compile.py` instead.
    "connect_proxy.py": frozenset({"__future__", "re", "brig.core", "brig.mech.contract"}),
}

#: task-031 AC#5's literal banned list. "open" is listed in the AC's prose
#: but cannot appear here: nobody writes `import open` -- it is a builtin,
#: not a module, so it is not a name `ast.Import`/`ast.ImportFrom` can ever
#: produce. It stands for "no file I/O" in the AC's shorthand; a literal
#: `open(...)` CALL is a different, unaddressed risk this import-level scan
#: cannot see, noted here rather than silently claimed to be covered.
_BANNED_IMPORT_NAMES: Final = frozenset({"os", "io", "time", "random", "subprocess", "pathlib"})

_TRAMPOLINE_PREFIX = "trampoline/"


@pytest.mark.unit
def test_mech_module_set_is_pinned() -> None:
    """The file set under brig/mech/ is exactly the three pinned paths --
    a fourth module joining (or one of the three vanishing) is loud."""
    actual_files = {
        str(p.relative_to(_MECH_ROOT))
        for p in _MECH_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    }
    expected_files = set(_EXPECTED_IMPORTS_BY_FILE)
    assert actual_files == expected_files, (
        f"brig/mech/ file set mismatch. Missing: {expected_files - actual_files}. "
        f"Extra: {actual_files - expected_files}."
    )


@pytest.mark.unit
@pytest.mark.parametrize("relpath", sorted(_EXPECTED_IMPORTS_BY_FILE))
def test_mech_file_imports_exactly_the_pinned_set(relpath: str) -> None:
    """AC#5's technique (ast-parsed, set equality, same posture as
    task-028's core pin), applied per file. This is the test AC#6's plant
    targets, by name, for `__init__.py`: `test_mech_file_imports_exactly_
    the_pinned_set[__init__.py]`."""
    actual = _top_level_imported_modules((_MECH_ROOT / relpath).read_text())
    expected = _EXPECTED_IMPORTS_BY_FILE[relpath]
    assert actual == expected, (
        f"{relpath} imports outside its pinned set. "
        f"Extra: {actual - expected}. Missing: {expected - actual}."
    )


@pytest.mark.unit
def test_only_the_mech_contract_layer_is_import_pure() -> None:
    """AC#5's literal claim, stated directly rather than only implied by
    the pinned-set tests above: every NON-trampoline module under
    brig/mech/ -- the contract layer (contract.py) and every mechanism -- never
    top-level-imports open/os/io/time/random/subprocess/pathlib.

    Re-parses each file with ast (does NOT read from
    `_EXPECTED_IMPORTS_BY_FILE`): a test that only compared two frozenset
    literals it wrote itself would be a tautology, unable to fail short of
    someone editing the test -- exactly the "true-as-tested but weaker than
    it reads" defect CLAUDE.md names as this repo's recurring one. Iterates
    the pinned dict's KEYS only, to know which files exist and which are the
    documented trampoline carve-out; the file set itself is proven equal to
    the real files by test_mech_module_set_is_pinned above.
    """
    violations: dict[str, frozenset[str]] = {}
    for relpath in _EXPECTED_IMPORTS_BY_FILE:
        if relpath.startswith(_TRAMPOLINE_PREFIX):
            continue
        actual = _top_level_imported_modules((_MECH_ROOT / relpath).read_text())
        overlap = actual & _BANNED_IMPORT_NAMES
        if overlap:
            violations[relpath] = frozenset(overlap)
    assert not violations, f"banned import(s) found: {violations}"


@pytest.mark.unit
def test_event_source_is_protocol_not_dataclass() -> None:
    """task-031 AC#7 -- the exact defect task-015 ATTEMPT 2 was rejected
    for, applied here to EventSource instead of Mechanism: it must be a
    typing.Protocol, and it must NOT carry __dataclass_fields__."""
    assert dataclasses.is_dataclass(EventSource) is False
    assert typing.is_protocol(EventSource) is True
    # Control: something that is neither is neither.
    assert typing.is_protocol(EventPayload) is False


@pytest.mark.unit
def test_event_source_is_runtime_checkable_with_a_negative_control() -> None:
    """EventSource is @runtime_checkable (like Mechanism above it), so a
    structurally-matching stub isinstance-checks true and a
    non-matching object isinstance-checks false -- the control that proves
    this isn't just isinstance() no-op-passing (same posture as
    test_mechanism_is_runtime_checkable_via_isinstance in
    tests/unit/test_mech_contract.py)."""

    class _Matches:
        def known_at_compile(self) -> tuple[EventPayload, ...]:
            return ()

        def classify_exit(self, outcome: ExitOutcome) -> EventPayload | None:
            return None

    assert isinstance(_Matches(), EventSource)
    assert not isinstance(object(), EventSource)


@pytest.mark.unit
def test_event_source_expresses_the_compile_time_fact_case() -> None:
    """task-031 AC#8, case 1: a compile-time-known fact -- which env names
    env_scrub scrubbed -- as a stub EventSource implementation. Asserts a
    mypy-checked static binding to EventSource (proving the shape
    satisfies the Protocol, not merely that isinstance() likes it, since
    runtime_checkable only checks method presence, not signatures), plus
    the mechanical form of decision-069's constraint 2 ("run performs
    every write, stamping ts and jail_id"): no EventPayload this source
    returns carries a 'ts' or 'jail_id' key, and every data value is a
    DataValue scalar.
    """

    class CompileFactSource:
        """Stub: env_scrub reporting which names it scrubbed, known the
        moment compile() finishes -- no clock, no I/O, no spawn."""

        def __init__(self, scrubbed_names: tuple[str, ...]) -> None:
            self._scrubbed_names = scrubbed_names

        def known_at_compile(self) -> tuple[EventPayload, ...]:
            return (
                EventPayload(
                    kind=EventKind.SPAWN,
                    data={"scrubbed_env_names": ",".join(self._scrubbed_names)},
                ),
            )

        def classify_exit(self, outcome: ExitOutcome) -> EventPayload | None:
            return None

    src: EventSource = CompileFactSource(scrubbed_names=("AWS_SECRET_ACCESS_KEY", "GH_TOKEN"))
    assert isinstance(src, EventSource)

    payloads = src.known_at_compile()
    assert len(payloads) == 1
    payload = payloads[0]
    assert isinstance(payload, EventPayload)
    assert payload.kind == EventKind.SPAWN
    assert payload.data == {"scrubbed_env_names": "AWS_SECRET_ACCESS_KEY,GH_TOKEN"}

    # Mechanical form of decision-069 constraint 2: no self-stamping.
    assert "ts" not in payload.data
    assert "jail_id" not in payload.data
    for value in payload.data.values():
        assert type(value) in (str, int, float, bool, type(None)), (
            f"non-DataValue-scalar payload value: {value!r} ({type(value)!r})"
        )

    # classify_exit is still callable and pure (no outcome recognized).
    assert src.classify_exit(ExitOutcome(returncode=0)) is None


@pytest.mark.unit
def test_event_source_expresses_the_exit_classification_case() -> None:
    """task-031 AC#8, case 2: a classification of how the workload ended --
    rlimits recognizing its own SIGXCPU trip -- as a stub EventSource
    implementation. Same static-binding and no-self-stamping assertions as
    the compile-time-fact test above, so both cases are proven against the
    identical Protocol, not two different ones."""

    _SIGXCPU = 24

    class CpuLimitExitSource:
        """Stub: rlimits recognizing a SIGXCPU termination as its own cpu
        limit tripping -- pure function of `outcome`, no I/O."""

        def known_at_compile(self) -> tuple[EventPayload, ...]:
            return ()

        def classify_exit(self, outcome: ExitOutcome) -> EventPayload | None:
            if outcome.returncode == -_SIGXCPU:
                return EventPayload(
                    kind=EventKind.LIMIT_TRIP,
                    data={"denial": "rlimits_cpu_trip", "signal": _SIGXCPU},
                )
            return None

    src: EventSource = CpuLimitExitSource()
    assert isinstance(src, EventSource)

    # Control: an ending this sensor does not recognize.
    assert src.classify_exit(ExitOutcome(returncode=0)) is None

    payload = src.classify_exit(ExitOutcome(returncode=-_SIGXCPU))
    assert payload is not None
    assert isinstance(payload, EventPayload)
    assert payload.kind == EventKind.LIMIT_TRIP
    assert payload.data == {"denial": "rlimits_cpu_trip", "signal": _SIGXCPU}

    assert "ts" not in payload.data
    assert "jail_id" not in payload.data
    for value in payload.data.values():
        assert type(value) in (str, int, float, bool, type(None)), (
            f"non-DataValue-scalar payload value: {value!r} ({type(value)!r})"
        )

    assert src.known_at_compile() == ()


@pytest.mark.unit
def test_event_payload_refuses_ts_and_jail_id_keys() -> None:
    """decision-069 constraint 2, enforced at construction, not just by
    convention: an EventPayload carrying 'ts' or 'jail_id' in its data is
    a ValueError, both keys, plus the control that a payload without
    either constructs fine. The error names exactly the offending key(s)
    -- checked with a discriminating `match` (a 'ts'-only violation must
    NOT mention 'jail_id' and vice versa), not just "the message contains
    'ts' somewhere," which a fixed two-key message would satisfy either way."""
    with pytest.raises(ValueError, match=r"^EventPayload\.data must not carry \['ts'\]") as exc_ts:
        EventPayload(kind=EventKind.SPAWN, data={"ts": 1.0})
    assert "jail_id" not in str(exc_ts.value)

    with pytest.raises(
        ValueError, match=r"^EventPayload\.data must not carry \['jail_id'\]"
    ) as exc_jail_id:
        EventPayload(kind=EventKind.SPAWN, data={"jail_id": "j1"})
    assert "'ts'" not in str(exc_jail_id.value)

    with pytest.raises(ValueError, match=r"^EventPayload\.data must not carry \['ts', 'jail_id'\]"):
        EventPayload(kind=EventKind.SPAWN, data={"ts": 1.0, "jail_id": "j1"})

    # Control.
    payload = EventPayload(kind=EventKind.SPAWN, data={"ok": "yes"})
    assert dict(payload.data) == {"ok": "yes"}


@pytest.mark.unit
def test_event_payload_data_defensive_copy_from_source() -> None:
    """Same posture as Step.env/Step.grades: mutate the source dict after
    construction, observe the EventPayload unchanged."""
    data_dict: dict[str, DataValue] = {"k": "v"}
    payload = EventPayload(kind=EventKind.SPAWN, data=data_dict)
    data_dict["k"] = "mutated"
    data_dict["k2"] = "new"
    assert dict(payload.data) == {"k": "v"}


@pytest.mark.unit
def test_step_events_defaults_to_none_and_accepts_a_source() -> None:
    """Step.events is optional (defaults to None, so no pre-M3 construction
    site breaks) and, when supplied, accepts anything structurally matching
    EventSource."""
    import brig.core
    import brig.mech

    def _identity(argv: tuple[str, ...]) -> tuple[str, ...]:
        return argv

    step_without = brig.mech.Step(
        wrap=_identity,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        grades={axis: brig.core.Graded(brig.core.UNENFORCED) for axis in brig.core.AXES},
        denial_signatures=(),
    )
    assert step_without.events is None

    class _NoOpSource:
        def known_at_compile(self) -> tuple[EventPayload, ...]:
            return ()

        def classify_exit(self, outcome: ExitOutcome) -> EventPayload | None:
            return None

    step_with = brig.mech.Step(
        wrap=_identity,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        grades={axis: brig.core.Graded(brig.core.UNENFORCED) for axis in brig.core.AXES},
        denial_signatures=(),
        events=_NoOpSource(),
    )
    assert isinstance(step_with.events, EventSource)

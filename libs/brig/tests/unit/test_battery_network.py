"""Tests for brig.probe.batteries.network: network_battery factory.

decision-117 (operator ruling round 17, item 4) requires two things this
battery structurally cannot get wrong:

- Defect A: every DENIAL probe targets the caller-supplied LITERAL address
  (`denied_address`, a required keyword-only argument) -- never a hostname,
  so no probe can fail for a DNS reason and be mistaken for a policy denial
  (`decision-108`).
- Defect B: the CONTROL probe is an action the Spec provably PERMITS --
  binding the declared LISTEN endpoint (`decision-116`), or reaching a
  granted domain -- never a caller-supplied endpoint that may or may not be
  reachable under a deny-all spec. A Spec permitting neither makes this
  battery refuse to construct (SPEC.md §6's no-work-to-do rule), rather than
  being permanently VACUOUS against the preset it exists for.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from brig.core.grades import Axis
from brig.core.probes import ProbeShape
from brig.core.spec import Channel, ChannelKind, NetworkPolicy, Spec
from brig.probe.batteries.network import network_battery
from brig.probe.battery import Probe

_NETWORK_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "brig" / "probe" / "batteries" / "network.py"
)

_LISTEN_SPEC = Spec(channels=(Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint="ctl.sock"),))
_DOMAIN_SPEC = Spec(network=NetworkPolicy(allowed_domains=("example.com",)))
_NO_WORK_SPEC = Spec()

_DENIED_ADDRESS = "192.0.2.1:80"

#: A naive "label.tld" hostname shape -- letters, then a dot, then two-or-more
#: letters. Matches "brig-probe-denied.invalid"; does NOT match a dotted
#: numeric literal like "192.0.2.1" (no run of letters either side of the
#: final dot).
_HOSTNAME_SHAPED_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9-]*\.[a-zA-Z]{2,}")


def _argv_text(probe: Probe) -> str:
    return " ".join(probe.argv)


# ---------------------------------------------------------------------------
# AC #10 -- the refusal, and its own two-sided control.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_spec_with_no_listen_channel_and_no_granted_domain_refuses() -> None:
    """No LISTEN channel and no granted domain: no honest positive control
    exists, so construction raises ValueError naming BOTH missing
    declarations by name -- 'channel' and 'domain' -- so a reader knows
    exactly what to add."""
    with pytest.raises(ValueError) as exc_info:
        network_battery(_NO_WORK_SPEC, denied_address=_DENIED_ADDRESS)
    message = str(exc_info.value)
    assert "LISTEN channel" in message
    assert "domain" in message


@pytest.mark.unit
def test_a_listen_channel_alone_is_sufficient_to_construct() -> None:
    """The control on the refusal above: a Spec with a LISTEN channel and NO
    granted domains constructs cleanly."""
    battery = network_battery(_LISTEN_SPEC, denied_address=_DENIED_ADDRESS)
    assert battery.axis is Axis.NETWORK


@pytest.mark.unit
def test_a_granted_domain_alone_is_sufficient_to_construct() -> None:
    """The other control on the refusal above: a Spec with a granted domain
    and NO LISTEN channel constructs cleanly."""
    battery = network_battery(_DOMAIN_SPEC, denied_address=_DENIED_ADDRESS)
    assert battery.axis is Axis.NETWORK


# ---------------------------------------------------------------------------
# AC #3 -- denied_address is a required keyword argument.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_denied_address_is_a_required_keyword_argument() -> None:
    """Omitting denied_address entirely raises TypeError -- Python's own
    call mechanism, since it is a required keyword-only parameter."""
    with pytest.raises(TypeError):
        network_battery(_LISTEN_SPEC)  # type: ignore[call-arg]


@pytest.mark.unit
def test_denied_address_empty_string_raises_value_error_naming_the_argument() -> None:
    """An empty denied_address raises ValueError naming 'denied_address' --
    distinct from the no-work-to-do refusal, isolated here by using a Spec
    (_LISTEN_SPEC) that already has a valid positive control."""
    with pytest.raises(ValueError, match="denied_address"):
        network_battery(_LISTEN_SPEC, denied_address="")


@pytest.mark.unit
def test_denied_address_without_a_colon_also_raises() -> None:
    """A denied_address with no ':' separator (so no host/port split is
    possible) raises the same named ValueError."""
    with pytest.raises(ValueError, match="denied_address"):
        network_battery(_LISTEN_SPEC, denied_address="192.0.2.1")


# ---------------------------------------------------------------------------
# AC #2 -- Defect A: DENIAL probes carry the literal address, never a
# hostname-shaped token.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("spec", [_LISTEN_SPEC, _DOMAIN_SPEC], ids=["listen-shape", "domain-shape"])
def test_every_denial_probe_carries_the_literal_address_and_no_hostname(spec: Spec) -> None:
    """Every DENIAL-shaped probe's argv contains the caller-supplied literal
    address and matches no hostname-shaped token -- so no probe in this
    battery can fail for a name-resolution reason (decision-117 Defect A).
    Parametrized over both control shapes: the claim is about the DENIAL
    probe, which is unchanged by which CONTROL shape the Spec selects."""
    battery = network_battery(spec, denied_address=_DENIED_ADDRESS)
    denial_probes = [p for p in battery.probes if p.shape is ProbeShape.DENIAL]
    assert denial_probes, "expected at least one DENIAL probe"
    for probe in denial_probes:
        argv_text = _argv_text(probe)
        assert _DENIED_ADDRESS in argv_text, (
            f"DENIAL probe {probe.name!r} argv does not carry the caller-supplied "
            f"literal address {_DENIED_ADDRESS!r}: {probe.argv!r}"
        )
        assert not _HOSTNAME_SHAPED_TOKEN.search(argv_text), (
            f"DENIAL probe {probe.name!r} argv contains a hostname-shaped token: {probe.argv!r}"
        )


@pytest.mark.unit
def test_a_different_denied_address_is_interpolated_not_hardcoded() -> None:
    """Changing denied_address changes the DENIAL probe's argv -- catches a
    hardcoded literal masquerading as the caller-supplied one."""
    battery1 = network_battery(_LISTEN_SPEC, denied_address="192.0.2.1:80")
    battery2 = network_battery(_LISTEN_SPEC, denied_address="198.51.100.7:443")

    denial1 = next(p for p in battery1.probes if p.shape is ProbeShape.DENIAL)
    denial2 = next(p for p in battery2.probes if p.shape is ProbeShape.DENIAL)

    assert "192.0.2.1:80" in _argv_text(denial1)
    assert "198.51.100.7:443" in _argv_text(denial2)
    assert "192.0.2.1:80" not in _argv_text(denial2)
    assert "198.51.100.7:443" not in _argv_text(denial1)


# ---------------------------------------------------------------------------
# AC #4, #5 -- Defect B: the CONTROL probe in both spec-permitted shapes.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_with_a_listen_channel_the_control_binds_that_declared_endpoint() -> None:
    """With a LISTEN channel declared, the CONTROL probe performs a network
    action against THAT DECLARED ENDPOINT: the endpoint's own value
    ('ctl.sock') appears in the probe's argv. Not a no-op -- it carries a
    real stdout token the runner must observe (Expectation(token='brig-ok'))."""
    battery = network_battery(_LISTEN_SPEC, denied_address=_DENIED_ADDRESS)
    control = next(p for p in battery.probes if p.shape is ProbeShape.CONTROL)
    assert control.name == "bind_the_declared_listen_endpoint"
    assert "ctl.sock" in _argv_text(control)
    assert control.expect.token == "brig-ok"


@pytest.mark.unit
def test_with_a_granted_domain_the_control_reaches_that_domain() -> None:
    """With a domain granted (and no LISTEN channel), the CONTROL probe
    reaches a granted endpoint: the domain's own value ('example.com')
    appears in the probe's argv, asserted the same way as the LISTEN case."""
    battery = network_battery(_DOMAIN_SPEC, denied_address=_DENIED_ADDRESS)
    control = next(p for p in battery.probes if p.shape is ProbeShape.CONTROL)
    assert control.name == "connect_to_a_granted_domain"
    assert "example.com" in _argv_text(control)
    assert control.expect.token == "brig-ok"


@pytest.mark.unit
@pytest.mark.parametrize(
    "spec,action_marker",
    [(_LISTEN_SPEC, "s.bind("), (_DOMAIN_SPEC, "urlopen(")],
    ids=["listen-shape", "domain-shape"],
)
def test_the_control_prints_success_only_after_the_network_action(
    spec: Spec, action_marker: str
) -> None:
    """Not a no-op, pinned precisely: the CONTROL's 'brig-ok' token is
    emitted only AFTER the real network action (bind, or connect) runs in
    its script -- never unconditionally at script start, which would let
    the probe PASS whether or not the action actually succeeded
    (decision-108's 'green, honest, and not about the thing', reintroduced
    at battery level). The pre-fix domain-shape script
    ('printf brig-ok && exec 3<>/dev/tcp/...') is exactly the shape this
    test catches: the token there precedes the action, so this assertion
    would fail against it.

    The domain-shape marker moved from `/dev/tcp/` to `urlopen(` at
    decision-141: the control now honours the proxy variables, because a
    direct socket connect can never succeed under a confined egress stack
    and would report a correctly-confined jail as broken. The PROPERTY
    under test is unchanged -- the token still must follow the action."""
    battery = network_battery(spec, denied_address=_DENIED_ADDRESS)
    control = next(p for p in battery.probes if p.shape is ProbeShape.CONTROL)
    script = control.argv[2]
    assert action_marker in script
    assert script.index(action_marker) < script.index("brig-ok")


@pytest.mark.unit
def test_the_two_control_shapes_have_different_names() -> None:
    """AC #5: the CONTROL probe's NAME differs between the two spec shapes,
    so a ProbeReport reader cannot mistake a channel-bind control for an
    egress control."""
    listen_control = next(
        p
        for p in network_battery(_LISTEN_SPEC, denied_address=_DENIED_ADDRESS).probes
        if p.shape is ProbeShape.CONTROL
    )
    domain_control = next(
        p
        for p in network_battery(_DOMAIN_SPEC, denied_address=_DENIED_ADDRESS).probes
        if p.shape is ProbeShape.CONTROL
    )
    assert listen_control.name != domain_control.name
    assert listen_control.name == "bind_the_declared_listen_endpoint"
    assert domain_control.name == "connect_to_a_granted_domain"


# ---------------------------------------------------------------------------
# AC #7 -- the battery still refuses to construct without a positive
# control; a battery built from this module always carries one.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("spec", [_LISTEN_SPEC, _DOMAIN_SPEC], ids=["listen-shape", "domain-shape"])
def test_the_battery_always_carries_at_least_one_control_probe(spec: Spec) -> None:
    """task-048's structural rule (Battery.__post_init__) is not weakened
    here: a Battery built from this module, in either spec shape, carries at
    least one CONTROL-shaped probe."""
    battery = network_battery(spec, denied_address=_DENIED_ADDRESS)
    assert any(p.shape is ProbeShape.CONTROL for p in battery.probes)


# ---------------------------------------------------------------------------
# Every probe's axis and battery shape.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("spec", [_LISTEN_SPEC, _DOMAIN_SPEC], ids=["listen-shape", "domain-shape"])
def test_the_battery_has_axis_network_and_two_probes(spec: Spec) -> None:
    battery = network_battery(spec, denied_address=_DENIED_ADDRESS)
    assert battery.name == "network"
    assert battery.axis is Axis.NETWORK
    assert len(battery.probes) == 2
    assert all(p.axis is Axis.NETWORK for p in battery.probes)


# ---------------------------------------------------------------------------
# AC #6 -- PURITY: this module's own top-level imports carry none of the
# forbidden impure modules.
# ---------------------------------------------------------------------------

_FORBIDDEN_TOP_LEVEL_IMPORT_MODULES = frozenset({"os", "socket", "subprocess", "pathlib"})


def _top_level_imported_modules(source: str) -> set[str]:
    """The set of module names named by top-level `import`/`from ... import`
    statements in `source`. Only `tree.body` (module-level statements) is
    walked -- this module's argv strings mention 'socket' as TEXT for the
    jailed process to import, which is not a top-level import of THIS
    module and must not trip this check."""
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


@pytest.mark.unit
def test_network_module_imports_none_of_the_forbidden_impure_modules() -> None:
    """AC #6: an AST test over brig/probe/batteries/network.py asserts its
    import set contains none of os, socket, subprocess, pathlib. AST-parsed
    rather than imported or grepped, so the 'socket' text embedded in the
    control probe's own Python-source argv string (a call the JAILED process
    makes, not this module) cannot cause a false positive."""
    actual = _top_level_imported_modules(_NETWORK_MODULE_PATH.read_text())
    forbidden_present = actual & _FORBIDDEN_TOP_LEVEL_IMPORT_MODULES
    assert forbidden_present == set(), (
        f"brig/probe/batteries/network.py imports forbidden impure module(s): {forbidden_present}"
    )

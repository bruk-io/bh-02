"""`connect_proxy.compile()`: a pure render, tested as one.

The mechanism decides three things, and each is checked here: what the
helper's argv is, what the wrap script says, and what is claimed on the
network axis. The integration tier then proves only that a real launch
honours the render.
"""

from __future__ import annotations

import sys

import pytest

from brig.core import Axis, Grade, NetworkPolicy, Spec
from brig.mech import CompileCtx, HelperLifetime
from brig.mech.connect_proxy import (
    _DENIAL_PREFIX,
    _PROXY_MODULE,
    DECISIONS_FILE,
    PORT_FILE,
    ConnectProxy,
)
from brig.proxy.filter import DENIAL_PREFIX

pytestmark = pytest.mark.unit

_PY = "/usr/bin/python3"
_JAIL = "/private/tmp/jail-x"


def _step(domains: tuple[str, ...] = ("example.com",)):  # type: ignore[no-untyped-def]
    spec = Spec(network=NetworkPolicy(allowed_domains=domains))
    return ConnectProxy(_PY).compile(spec, CompileCtx(jail_dir=_JAIL, platform=sys.platform))


def test_the_duplicated_denial_prefix_has_not_drifted() -> None:
    """`mech` may not import `brig.proxy` (decision-133's empty row), so
    the signature constant is written in both places. Prevention is not
    available; detection is. This test is the detection: it imports both
    and compares.

    If this fails, the proxy's wire text and the mechanism's signature
    have diverged, which means every probe reading that signature has
    silently stopped recognising a real denial.
    """
    assert _DENIAL_PREFIX == DENIAL_PREFIX


def test_the_duplicated_module_path_still_resolves() -> None:
    """The other duplicated literal: the helper's `-m` target.

    Asked of the import SYSTEM (`find_spec`) rather than by importing the
    name. The claim is "this string still names a real module", which is what
    `python -m <string>` needs and all this test ever wanted; importing it
    would additionally run it. It also keeps the workspace's import gate
    honest: `keel-imports` refuses `import_module` with a non-literal target,
    because pypeeker cannot resolve one and the import graph would carry a
    hole it does not know about. `find_spec` opens no edge to lose.
    """
    import importlib.util

    assert importlib.util.find_spec(_PROXY_MODULE) is not None


def test_helper_is_jail_lifetime_and_carries_every_allowed_domain() -> None:
    step = _step(("example.com", "*.internal.test"))
    assert len(step.helpers) == 1
    helper = step.helpers[0]
    assert helper.lifetime is HelperLifetime.JAIL_LIFETIME, (
        "the proxy must live as long as the jail; a LAUNCH_SCOPED proxy exits "
        "before the workload it is supposed to filter for ever starts"
    )
    assert helper.argv[:3] == (_PY, "-m", _PROXY_MODULE)
    allows = [helper.argv[i + 1] for i, tok in enumerate(helper.argv) if tok == "--allow"]
    assert allows == ["*.internal.test", "example.com"], (
        f"allow list did not survive the render: {helper.argv!r}"
    )
    assert f"{_JAIL}/{PORT_FILE}" in helper.argv
    assert f"{_JAIL}/{DECISIONS_FILE}" in helper.argv


def test_an_empty_allow_list_still_starts_a_proxy_that_denies_everything() -> None:
    """Deny-all is a policy, not an absence of one. A mechanism that
    quietly declined to run here would leave the workload with no proxy
    variables and full direct egress -- the opposite of what an empty
    allow list asks for."""
    step = _step(())
    assert len(step.helpers) == 1
    assert "--allow" not in step.helpers[0].argv
    assert step.grades[Axis.NETWORK].grade is Grade.COOPERATIVE


def test_grade_is_cooperative_and_names_both_gaps() -> None:
    """`compile()` sees one `Spec` and cannot know what else is in the
    stack, so it cannot know whether a transport confinement pairs with
    it -- and grading from a hope about composition is the "never grade
    up" law broken. Cooperative, with both gaps named."""
    graded = _step().grades[Axis.NETWORK]
    # mypy narrows the line above to a literal, so restating "and not
    # BEST_EFFORT" is a type error rather than an assertion. The claim is
    # made against the rank instead, which is the form that survives:
    # cooperative must not satisfy a best_effort floor.
    assert graded.grade is Grade.COOPERATIVE
    assert not graded.grade.is_at_least(Grade.BEST_EFFORT)
    lowered = graded.detail.lower()
    assert "hostile process ignores" in lowered, graded.detail
    assert "sni" in lowered, "the SNI co-hosting gap is unnamed in detail"


def test_wrap_waits_for_the_port_and_execs_the_workload_unparsed() -> None:
    step = _step()
    argv = step.wrap(("/bin/echo", "hi; rm -rf /"))
    assert argv[:2] == ("/bin/sh", "-c")
    script = argv[2]
    # The workload rides in positional parameters, so its own text is
    # never re-parsed as shell syntax.
    assert argv[3:] == ("sh", "/bin/echo", "hi; rm -rf /")
    assert "hi; rm -rf /" not in script

    assert f"{_JAIL}/{PORT_FILE}" in script
    assert 'exec "$@"' in script
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        assert f'{name}="http://127.0.0.1:$p"' in script, f"{name} is not pointed at the proxy"
    # NO_PROXY is deliberately absent: a loopback exemption would put
    # everything reachable on this host outside the allow list, and buys
    # nothing, since channels are UNIX sockets no proxy variable touches.
    assert "NO_PROXY" not in script, script


def test_wrap_refuses_rather_than_running_unproxied_when_the_port_never_appears() -> None:
    """The branch that matters most. A workload started with unset
    proxy variables reaches the network directly -- a silent, total loss
    of the policy -- so the script must exit, not exec."""
    script = _step().wrap(("/bin/true",))[2]
    assert "exit 71" in script
    assert "never published a port" in script


def test_the_signature_matches_the_proxy_denial_and_not_a_generic_403() -> None:
    """Both directions. A bare `403` would also match an upstream
    server's own rejection, which would let a probe report "denied by
    policy" about a site that merely refused the request."""
    pattern = _step().denial_signatures[0]
    assert pattern.search(f"{DENIAL_PREFIX}example.com\nnot in allow list")
    for unrelated in (
        "HTTP/1.1 403 Forbidden",
        "403 Forbidden",
        "curl: (7) Failed to connect to example.com port 443",
        "Could not resolve host",
    ):
        assert not pattern.search(unrelated), (
            f"signature matched an unrelated failure: {unrelated!r}"
        )


def test_events_report_the_allow_list_and_never_classify_an_exit() -> None:
    step = _step(("example.com",))
    assert step.events is not None
    payloads = step.events.known_at_compile()
    assert len(payloads) == 1
    assert payloads[0].data["allowed_domains"] == "example.com"
    assert payloads[0].data["decisions_path"] == f"{_JAIL}/{DECISIONS_FILE}"

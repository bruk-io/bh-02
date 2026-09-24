"""network_battery: a probe battery for network egress enforcement
(SPEC.md §12, §6; decision-116; decision-117).

**Defect A (name resolution is not policy).** The DENIAL probe targets a
LITERAL address the caller supplies -- never a hostname. Resolving a name is
DNS's business, not the sandbox's, and a name that fails to resolve
(`EAI_NONAME`) produces the *same* shell failure text regardless of whether
any policy was even consulted -- that is `decision-108`'s "green, honest, and
not about the thing". A literal IP:port removes name resolution from the
picture entirely, so the only thing that can stop the connection is policy.

**Defect B (a positive control is an action the Spec provably permits,
`decision-117`).** SPEC.md §12 names controls as ACTIONS -- "write inside the
workspace, dial the declared channel" -- never a non-action, and never merely
an action that happens to succeed. Dialing loopback under a deny-all spec
fails by construction, which would mark this whole battery `VACUOUS`
regardless of how well the jail enforces (SPEC.md §12's three-way battery
logic). So the CONTROL probe here targets one of the two actions the Spec
itself can be read to permit:

1. **A declared LISTEN channel** -- `decision-116` records that
   `(allow network-bind)` is emitted, unscoped, ONLY when a LISTEN channel is
   declared: it is the one network action a deny-all Seatbelt profile is
   compiled to allow. The control therefore BINDS an AF_UNIX socket at the
   channel's own declared endpoint (never dialing it -- nothing is listening
   there, and binding is the permitted action decision-116 names). Its name,
   `bind_the_declared_listen_endpoint`, says exactly that.
2. **A granted domain** -- the control reaches that domain, as SPEC.md §12's
   own "dial the declared channel" example anticipates for egress. Its name,
   `connect_to_a_granted_domain`, says exactly that -- distinct from the
   LISTEN-shape control's name, so a `ProbeReport` reader can never mistake
   a channel-bind control for an egress control.

**A Spec permitting neither -- no LISTEN channel, no granted domain -- gives
this battery no honest action to control for.** Per SPEC.md §6's no-work-to-do
rule ("a mechanism claims an axis only when the spec gives it work to do on
that axis"), construction REFUSES rather than shipping a battery that would
be permanently `VACUOUS` against the very preset it was built for --
`VACUOUS` is a verdict about a *run*, not a permanent state a construction
choice may manufacture (`decision-117`, superseding `doc-017` A3's
"probe-transport liveness check performing no network action" -- that shape
is deliberately NOT what this module builds).

This module is pure: no I/O, no clock, no randomness, no child processes.
"""

from __future__ import annotations

from brig.core.grades import Axis
from brig.core.probes import ProbeShape
from brig.core.spec import Spec
from brig.probe.battery import Battery, Expectation, Probe

#: The port the CONTROL probe dials for a granted-domain Spec. A brig Spec
#: grants a domain, not a domain+port pair (SPEC.md §5's NetworkPolicy), and
#: `connect_proxy`/per-domain egress enforcement is M6 (out of scope here) --
#: 443 is this battery's own, documented choice of a plausible egress port,
#: not a fact read from the Spec.
#: decision-141: the granted-domain control fetches over https, through the
#: proxy when one is routed and directly when not. `HOST` is substituted at
#: probe time so this module never names a hostname in its own source (the
#: same Defect A discipline the DENIAL probe follows).
_GRANTED_DOMAIN_CONTROL_URL = "https://HOST/"


def network_battery(spec: Spec, *, denied_address: str, control_url: str | None = None) -> Battery:
    """Factory for the network enforcement battery.

    Args:
        spec: A Spec object (validated but not read beyond construction, plus
            the network-shape check below). Must declare at least one
            `Channel` (every declared channel is a LISTEN channel), or at least one
            `spec.network.allowed_domains` entry, or construction refuses
            (see Raises) -- SPEC.md §6's no-work-to-do rule, `decision-117`.
        control_url: Optional URL for the positive control, with the literal
            token `HOST` standing in for the granted domain (e.g.
            "http://HOST:8080/x"). Defaults to "https://HOST/". Supplied
            when the granted domain does not serve on 443 -- the battery has
            no way to discover that, the same gap `denied_address` fills on
            the other side.
        denied_address: A required "host:port" string naming a LITERAL
            address (e.g. "192.0.2.1:80", RFC 5737 TEST-NET-1) -- never a
            hostname. The battery's DENIAL probe dials exactly this address,
            so no name resolution happens and only policy can stop it
            (Defect A above). Must be non-empty and contain a ':', or
            ValueError is raised naming this parameter.

    Returns:
        A Battery with axis=Axis.NETWORK and exactly two probes: one
        CONTROL, whose name and target depend on which spec-permitted action
        is available (a declared LISTEN channel takes priority over a
        granted domain when a Spec somehow carries both), and one DENIAL.

    Raises:
        TypeError: `denied_address` is not supplied -- it is a required
            keyword-only argument; Python's own call mechanism enforces this
            before this function's body ever runs.
        ValueError: `spec` declares no LISTEN channel and grants no domains
            (no network action the Spec provably permits for a positive
            control); or `denied_address` is empty or has no ':' separator.
    """
    # Every declared channel is a LISTEN channel: `LISTEN` is the only
    # `ChannelKind` there is since decision-153, so this no longer filters.
    listen_channels = spec.channels
    granted_domains = spec.network.allowed_domains

    if not listen_channels and not granted_domains:
        raise ValueError(
            "network_battery: spec declares no LISTEN channel (spec.channels) "
            "and grants no domains (spec.network.allowed_domains) -- there is "
            "no network action this Spec provably permits for a positive "
            "control (SPEC.md §6's no-work-to-do rule), so this battery "
            "refuses to construct rather than being permanently VACUOUS "
            "against the preset it was built for (decision-117)"
        )

    if not denied_address or ":" not in denied_address:
        raise ValueError(
            "denied_address must be a non-empty 'host:port' string naming a "
            f"literal address (never a hostname); got {denied_address!r}"
        )

    if listen_channels:
        # The one network action decision-116 records as permitted on a
        # deny-all Seatbelt profile: binding the jail's own declared LISTEN
        # endpoint. Nothing need be listening there -- a successful bind is
        # itself the permitted action, and this control never connects.
        endpoint = listen_channels[0].endpoint
        bind_code = (
            "import socket;"
            "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM);"
            f"s.bind({endpoint!r});"
            "s.close();"
            "print('brig-ok')"
        )
        control_probe = Probe(
            name="bind_the_declared_listen_endpoint",
            shape=ProbeShape.CONTROL,
            axis=Axis.NETWORK,
            argv=("python3", "-c", bind_code),
            expect=Expectation(token="brig-ok"),
        )
    else:
        # A granted domain: an egress action, distinct in name and in kind
        # from the bind control above so a ProbeReport reader cannot
        # mistake one for the other.
        domain = granted_domains[0]
        # decision-141: this control HONOURS the proxy variables, and the
        # DENIAL probe below deliberately does not. The asymmetry is the
        # whole point -- the control takes the sanctioned path, the denial
        # takes the unsanctioned one, and a battery whose two probes shared
        # a transport could not tell a working policy from a broken network.
        #
        # It used to be a raw `exec 3<>/dev/tcp/$0/443`. That was correct
        # for every stack that existed when it was written, and is
        # GUARANTEED to fail under a confined egress stack: the seatbelt
        # denies all non-loopback outbound precisely so a workload ignoring
        # HTTP_PROXY cannot dial out, and /dev/tcp ignores HTTP_PROXY by
        # construction. The battery would then report a CORRECTLY confined
        # stack as broken -- a failing control cannot distinguish "policy
        # denied this" from "nothing works here" (decision-108's vacuous
        # battery, arriving through a new door).
        #
        # `urllib` reads http_proxy/https_proxy from the environment itself,
        # so this passes against an open-egress stack (connecting directly)
        # AND against a proxied one (routing through it), without the probe
        # needing to know which it is in. The token prints only after the
        # request returns, never unconditionally.
        # decision-141: the battery cannot know which PORT a granted domain
        # serves, so `control_url` is a parameter for exactly the reason
        # `denied_address` already is -- a caller pointing this at a real
        # origin (a loopback server in a test, say) must be able to say
        # where it lives. `HOST` is substituted from the granted domain at
        # probe time, so this module still never names a hostname itself.
        url = control_url or _GRANTED_DOMAIN_CONTROL_URL
        control_code = (
            "import sys,urllib.request;"
            f"urllib.request.urlopen({url!r}.replace("
            "'HOST',sys.argv[1]),timeout=15).read(1);"
            "print('brig-ok')"
        )
        control_probe = Probe(
            name="connect_to_a_granted_domain",
            shape=ProbeShape.CONTROL,
            axis=Axis.NETWORK,
            argv=("python3", "-c", control_code, domain),
            expect=Expectation(token="brig-ok"),
        )

    # DENIAL probe: attempt to connect to the caller-supplied LITERAL
    # address. ${0%%:*} / ${0##*:} split "host:port" without ever naming a
    # hostname in this module's own source -- see Defect A above.
    denial_probe = Probe(
        name="connect_to_a_denied_literal_address",
        shape=ProbeShape.DENIAL,
        axis=Axis.NETWORK,
        argv=(
            "/bin/sh",
            "-c",
            "exec 3<>/dev/tcp/${0%%:*}/${0##*:}",
            denied_address,
        ),
        expect=Expectation(),
    )

    return Battery(
        name="network",
        axis=Axis.NETWORK,
        probes=(control_probe, denial_probe),
    )


__all__ = ("network_battery",)

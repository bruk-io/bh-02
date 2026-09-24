"""`connect_proxy`: the `network` axis mechanism -- a filtering proxy.

SPEC.md §6 roster row, verbatim:

    | `connect_proxy` | network | all | standalone HTTP(S) CONNECT filter;
    `best_effort` when paired with an enforced transport confinement,
    `cooperative` when only env-vars route to it; SNI-co-hosting gap named
    in detail |

This module is the MECHANISM: it decides that a proxy should run, renders
how the workload is pointed at it, and grades the result. The proxy process
itself is `brig/proxy/` -- a separate program with an empty layer row
(decision-133), which this layer therefore cannot import. See "The
duplicated constants" below for how the two stay in step.

**This mechanism grades `cooperative`, always -- never `best_effort`.**
The roster row's `best_effort` is available only "when paired with an
enforced transport confinement", and a `compile()` is a pure function of one
`Spec`: it cannot see what else is in the stack, so it cannot know whether
such a pairing exists. Grading from a hope about composition is precisely
the "never grade up" law. Routing here is by `HTTP_PROXY`/`HTTPS_PROXY`,
which a hostile process ignores by simply not reading them -- the textbook
`cooperative`. If a later composition step wants to raise this to
`best_effort` because a seatbelt rule or a netns actually confines the
workload's transport, that upgrade belongs to whatever can OBSERVE the
pairing, and it must still name the SNI gap that keeps it off `enforced`.

**The port is not knowable at compile time, and that shapes the render.**
The proxy binds port 0 so two jails cannot collide, which means the number
exists only after it has started -- while `compile()` may not perform I/O.
So the same trick `env_scrub` uses applies: the SCRIPT TEXT is pure,
compile-time data, and the *read* happens when the script runs. `wrap`
renders a `/bin/sh -c` that waits (bounded) for the proxy's port file,
exports the proxy variables against the port it finds, and `exec`s the
workload.

**Why the wait is in the wrap and not a `LAUNCH_SCOPED` helper.** Both
work: `_start_helpers` processes helpers in declared order, so a
`JAIL_LIFETIME` proxy followed by a `LAUNCH_SCOPED` waiter would also
guarantee the port exists before the workload starts. The wrap is chosen
because it makes that guarantee independent of helper ORDERING -- an
ordering nothing else in the codebase currently relies on, and which would
become load-bearing and silently breakable the moment it did. The wrap has
to read the port file anyway; making it also wait costs one shell loop.

**What happens when the proxy never comes up.** The script exits non-zero
with a message naming the missing port file, rather than exec'ing the
workload with no proxy variables set. A workload that starts with an unset
`HTTPS_PROXY` reaches the network directly -- a silent, complete loss of the
policy -- so failing loudly is the only honest branch. This is a launch
failure, not a denial, and it carries no denial signature: a probe must not
read "the sandbox refused this" from "the sandbox never started".

**The duplicated constants.** `_DENIAL_PREFIX` and the proxy's module path
are written here as literals because `mech` may not import `brig.proxy`
(the empty row is the whole point of decision-133, and a signature constant
is not worth punching a hole in it). Drift is caught rather than prevented:
`tests/unit/test_connect_proxy_compile.py` imports BOTH this module and
`brig.proxy.filter` and asserts the two constants are equal, so a change to
one without the other reddens the unit tier immediately.

**`denial_signatures` names the proxy's 403, not any 403.** SPEC.md §8
gives `proxy "403"` as the example, but a bare `403` would also match an
upstream server's own rejection, which would let a probe report "denied by
policy" about a site that simply refused the request -- vacuous by
construction. The signature is the proxy's own prefix line, which no
upstream produces.

**`Step.events` reports what is known at compile: the allow list.** The
proxy's live allow/deny decisions are written by the proxy process itself,
as JSONL, for a `run`-layer reader to fold in -- they cannot travel through
`EventSource`, whose methods are pure and run at compile time, long before
any connection is made. `classify_exit` returns `None`: a workload that
failed because egress was denied exits however ITS OWN error handling
exits, and inventing a status for that would be the same vacuous match the
signature above avoids.
"""

from __future__ import annotations

import re

from brig.core import Axis, EventKind, Grade, Graded, NetworkPolicy, Spec
from brig.mech import (
    ArgvTransformer,
    CompileCtx,
    EventPayload,
    ExitOutcome,
    Helper,
    HelperLifetime,
    Step,
)

_SHELL = "/bin/sh"
_POSITIONAL_ARGS = '"$@"'

#: Must equal `brig.proxy.filter.DENIAL_PREFIX`; pinned equal by
#: `tests/unit/test_connect_proxy_compile.py` (see the module docstring on
#: why this is duplicated rather than imported).
_DENIAL_PREFIX = "brig: egress denied by policy: "

#: The signature as a compiled pattern. `re.escape`, because the prefix
#: contains a `:` and a `.` and is meant to match LITERALLY -- a signature
#: that quietly behaved as a regex would be a matcher nobody audited.
_DENIAL_PATTERN = re.compile(re.escape(_DENIAL_PREFIX))

#: Must equal the proxy package's import path.
_PROXY_MODULE = "brig.proxy"

#: File names under `jail_dir`. Compile-time-known, which is what lets a
#: pure render name them.
PORT_FILE = "proxy.port"
DECISIONS_FILE = "proxy-decisions.jsonl"

#: How long the wrap waits for the port file before refusing to run the
#: workload. Generous: the cost of waiting is a slow start, the cost of
#: giving up early is a workload running with no proxy at all.
_WAIT_SECONDS = 30

#: The variables pointed at the proxy. Both cases are set because the
#: ecosystem is split -- curl reads the lowercase names, many libraries the
#: uppercase -- and setting only one silently leaves the other tool
#: unrouted.
#:
#: **`NO_PROXY` is deliberately NOT set, not even for loopback.** The
#: obvious default -- exempting `localhost,127.0.0.1,::1` so a jail's own
#: channels are not dialled through their own egress filter -- turns out to
#: buy nothing and cost the policy: SPEC.md §10's channels are UNIX sockets,
#: which no proxy variable has ever affected, so there is nothing to
#: protect; while a loopback exemption means anything the workload can
#: reach on this host over TCP is outside the allow list entirely. An empty
#: `NO_PROXY` is the stricter and the simpler reading, so it is the one
#: taken; a spec that genuinely needs loopback egress names it in
#: `allowed_domains` like any other destination.
_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")


def _render_wait_script(port_path: str) -> str:
    """The `/bin/sh -c` text: wait for the port, export, exec.

    Pure: every value in it is compile-time data (a path, a count, literal
    variable names). No substitution happens here; `$p` is expanded by the
    shell at run time, which is the only moment the port exists.
    """
    exports = " ".join(f'{name}="http://127.0.0.1:$p"' for name in _PROXY_VARS)
    return (
        f"n=0; "
        f"while [ ! -s '{port_path}' ]; do "
        f"n=$((n+1)); "
        f"if [ $n -gt {_WAIT_SECONDS * 20} ]; then "
        f'echo "brig: egress proxy never published a port at {port_path}" >&2; '
        f"exit 71; "
        f"fi; "
        f"sleep 0.05; "
        f"done; "
        f"p=$(cat '{port_path}'); "
        f"export {' '.join(_PROXY_VARS)}; "
        f"{exports}; "
        f"exec {_POSITIONAL_ARGS}"
    )


def _render_wrap(port_path: str) -> ArgvTransformer:
    script = _render_wait_script(port_path)

    def wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
        # `sh -c SCRIPT sh <argv...>`: the workload's argv arrives as
        # positional parameters and is never re-parsed as shell syntax.
        return (_SHELL, "-c", script, "sh", *argv)

    return wrap


def _render_helper_argv(
    python: str, port_path: str, log_path: str, policy: NetworkPolicy
) -> tuple[str, ...]:
    argv: list[str] = [
        python,
        "-m",
        _PROXY_MODULE,
        "--port-file",
        port_path,
        "--log",
        log_path,
    ]
    for domain in policy.allowed_domains:
        argv += ["--allow", domain]
    return tuple(argv)


class _ConnectProxyEventSource:
    """The compile-time fact: which destinations this jail's proxy will
    permit. The live decisions are the proxy process's own JSONL output --
    see the module docstring."""

    def __init__(self, policy: NetworkPolicy, decisions_path: str) -> None:
        self._policy = policy
        self._decisions_path = decisions_path

    def known_at_compile(self) -> tuple[EventPayload, ...]:
        return (
            EventPayload(
                kind=EventKind.SPAWN,
                data={
                    "network_policy": "connect_proxy",
                    "allowed_domains": ",".join(self._policy.allowed_domains),
                    "decisions_path": self._decisions_path,
                },
            ),
        )

    def classify_exit(self, outcome: ExitOutcome) -> EventPayload | None:
        del outcome
        return None


class ConnectProxy:
    """SPEC.md §6's `connect_proxy` mechanism: `network`, all platforms.

    `python` is the interpreter the helper is spawned with. It is a
    constructor argument rather than something `compile()` discovers,
    because `compile()` may not read `sys.executable` any more than it may
    read a clock -- the caller that builds the stack supplies it.
    """

    name = "connect_proxy"
    axes: frozenset[Axis] = frozenset({Axis.NETWORK})

    def __init__(self, python: str) -> None:
        self._python = python

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        policy = spec.network
        # `jail_dir` arrives already realpath'd (CompileCtx's contract), which
        # matters on darwin: `/tmp` is a symlink, and a port file named
        # through the symlinked form is a different string to two processes
        # that resolve it differently.
        port_path = f"{ctx.jail_dir}/{PORT_FILE}"
        log_path = f"{ctx.jail_dir}/{DECISIONS_FILE}"

        detail = (
            "routed by HTTP_PROXY/HTTPS_PROXY only, which a hostile process ignores; "
            "and the filter binds the host the client ASKED for, so a permitted host "
            "co-hosted with a forbidden one on the same address is reachable inside an "
            "opened tunnel (SNI co-hosting). Pairing with an enforced transport "
            "confinement is what would raise this to best_effort; this mechanism does "
            "not deliver that confinement and does not claim it."
        )
        return Step(
            wrap=_render_wrap(port_path),
            env={},
            staged=(),
            helpers=(
                Helper(
                    name="connect_proxy",
                    argv=_render_helper_argv(self._python, port_path, log_path, policy),
                    lifetime=HelperLifetime.JAIL_LIFETIME,
                ),
            ),
            requires=frozenset(),
            grades={Axis.NETWORK: Graded(Grade.COOPERATIVE, detail)},
            denial_signatures=(_DENIAL_PATTERN,),
            events=_ConnectProxyEventSource(policy, log_path),
        )

"""The incident-triage family: services in production, one deploy of which makes its callers fail.

A world is a value (`world(seed, size)`): services with dependencies, pods (named, as Kubernetes
names them, by their pod template's hash, so a pod left on an old version has an older hash), a few
days of deploy history, and two hours of request logs, 13:00 to 15:00 on 2026-11-03. A little
before 14:00 one service is rolled out to a new version, and from then on a share of its callers'
requests to it time out (status 504); the rollout leaves one or two of its pods on the old version.
Decoys: an unrelated deploy near the same time, and a noisy service whose cache-miss warnings and
closed-connection errors are harmless. A problem no rule sees: one service logs nothing for one
minute.

The tools (`call`) return everything they have, as many real MCP servers do: every pod, every log
line of a service in a time window. `scenarios.incident_mcp` serves them. Truths are worked out from
the world. SCENARIOS.md has the design.
"""

import json
import random
from dataclasses import dataclass
from typing import Any

from evals.truth import Absent, Exact, Items, Needle, Number, Truth

DAY = "2026-11-03"
_SERVICES = (
    "gateway",
    "checkout",
    "payments",
    "cart",
    "catalogue",
    "search",
    "inventory",
    "shipping",
    "auth",
    "pricing",
    "reviews",
    "notifications",
)
_TEAMS = ("storefront", "money", "platform", "fulfilment", "discovery")
_ROUTES = {
    "gateway": ("GET /", "GET /health", "POST /api/session"),
    "checkout": ("POST /api/checkout", "GET /api/checkout/{id}"),
    "payments": ("POST /v1/charges", "POST /v1/refunds", "GET /v1/charges/{id}"),
    "cart": ("GET /api/cart", "POST /api/cart/items", "DELETE /api/cart/items/{id}"),
    "catalogue": ("GET /api/products", "GET /api/products/{id}"),
    "search": ("GET /api/search", "GET /api/suggest"),
    "inventory": ("GET /stock/{sku}", "POST /stock/reserve"),
    "shipping": ("POST /quotes", "GET /tracking/{id}"),
    "auth": ("POST /token", "GET /userinfo"),
    "pricing": ("POST /price", "GET /rules"),
    "reviews": ("GET /api/reviews/{id}", "POST /api/reviews"),
    "notifications": ("POST /send", "GET /status/{id}"),
}
_SIZES = {"M": (8, (4, 6), 2), "L": (12, (12, 18), 9)}  # services, pods per service, requests a minute
_WINDOW = 120  # minutes, from 13:00
_POD_CHARS = "bcdfghjklmnpqrstvwxz2456789"  # the characters Kubernetes draws a pod's suffix from


@dataclass(frozen=True)
class Pod:
    name: str
    service: str
    version: str
    node: str
    ip: str
    restarts: int
    started: str  # when it started, as an ISO time


@dataclass(frozen=True)
class Deploy:
    service: str
    version: str
    at: str  # ISO time
    author: str
    note: str


@dataclass(frozen=True)
class Line:
    second: int  # seconds after 13:00
    service: str
    text: str
    status: int


@dataclass(frozen=True)
class Fault:
    service: str  # the one rolled out
    old: str
    new: str
    minute: int  # minutes after 13:00
    victim: str  # the caller whose requests to it time out
    rate: float


@dataclass(frozen=True)
class World:
    seed: int
    size: str
    services: tuple[str, ...]
    deps: tuple[tuple[str, tuple[str, ...]], ...]
    teams: tuple[tuple[str, str], ...]
    pods: tuple[Pod, ...]
    deploys: tuple[Deploy, ...]
    lines: tuple[Line, ...]
    fault: Fault
    noisy: str  # the service whose noise is harmless
    gap: tuple[str, int]  # the service that logs nothing for one minute, and that minute


def _hex(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def _clock(second: int) -> str:
    return f"{DAY}T{13 + second // 3600:02d}:{second // 60 % 60:02d}:{second % 60:02d}"


def minute_name(minute: int) -> str:
    return f"{13 + minute // 60:02d}:{minute % 60:02d}"


def _version(rng: random.Random) -> tuple[int, int, int]:
    return (rng.randrange(1, 5), rng.randrange(0, 30), rng.randrange(0, 10))


def _v(t: tuple[int, int, int]) -> str:
    return ".".join(map(str, t))


def world(seed: int, size: str = "M") -> World:
    """The world a seed builds: the same seed, the same world.

    Raises:
        ValueError: `size` names no size (M or L).
    """
    if size not in _SIZES:
        raise ValueError(f"no size {size!r}: use one of {', '.join(_SIZES)}")
    n_services, (lo, hi), per_minute = _SIZES[size]
    rng = random.Random(f"incident/{size}/{seed}")
    services = ("gateway", *rng.sample([s for s in _SERVICES if s != "gateway"], n_services - 1))
    deps = {
        s: tuple(rng.sample(services[i + 1 :], min(2, len(services) - i - 1))) for i, s in enumerate(services)
    }
    callers = [(s, d) for s in services for d in deps[s] if s != "gateway"]
    victim, faulty = rng.choice(callers)
    others = [s for s in services if s not in (victim, faulty)]
    noisy, gap_service, decoy = rng.sample(others, 3)
    minute = rng.randrange(52, 64)
    versions = {s: _version(rng) for s in services}
    old = versions[faulty]
    new = (old[0], old[1] + 1, 0)
    while new in versions.values():  # the rollout's version names one deploy only
        new = (new[0], new[1], new[2] + 1)
    # pods: every service on its current version; the faulty one on the new version but one or two
    nodes = [
        f"ip-10-0-{rng.randrange(1, 9)}-{rng.randrange(10, 250)}" for _ in range(6 if size == "M" else 14)
    ]
    pods = []
    for s in services:
        current = _v(new) if s == faulty else _v(versions[s])
        replicas = rng.randrange(lo, hi + 1)
        stale = rng.choice((1, 2)) if s == faulty else 0
        hashes = {current: _hex(rng, 9), _v(old): _hex(rng, 9)}
        for i in range(replicas):
            version = _v(old) if i < stale else current
            started = (
                _clock(minute * 60 + rng.randrange(30, 300))
                if s == faulty and i >= stale
                else (f"2026-11-0{rng.randrange(1, 3)}T{rng.randrange(0, 24):02d}:{rng.randrange(60):02d}:00")
            )
            pods.append(
                Pod(
                    f"{s}-{hashes[version]}-{''.join(rng.choice(_POD_CHARS) for _ in range(5))}",
                    s,
                    version,
                    rng.choice(nodes),
                    f"10.0.{rng.randrange(0, 64)}.{rng.randrange(2, 250)}",
                    rng.choice((0, 0, 0, 0, 1, 2)),
                    started,
                )
            )
    rng.shuffle(pods)
    # deploys: a few days of history, then the faulty rollout and the decoy near it
    authors = ("ada", "lin", "sam", "noor", "kai", "ines")
    notes = (
        "bump dependencies",
        "tune timeouts",
        "add metrics",
        "fix flaky retry",
        "refactor handlers",
        "update config",
    )
    history = []
    for s in services:
        v = list(versions[s])
        for k in range(rng.randrange(1, 4)):
            day = 30 + k + rng.randrange(0, 2)
            month, dom = (10, day) if day <= 31 else (11, day - 31)
            stamp = f"2026-{month}-{dom:02d}T{rng.randrange(8, 19):02d}:{rng.randrange(60):02d}:00"
            history.append(
                Deploy(
                    s,
                    _v((v[0], max(0, v[1] - k - 1), rng.randrange(0, 10))),
                    stamp,
                    rng.choice(authors),
                    rng.choice(notes),
                )
            )
    history.append(
        Deploy(
            faulty,
            _v(new),
            _clock(minute * 60 + rng.randrange(0, 50)),
            rng.choice(authors),
            rng.choice(notes),
        )
    )
    decoy_version = list(versions[decoy])
    history.append(
        Deploy(
            decoy,
            _v((decoy_version[0], decoy_version[1], decoy_version[2] + 1)),
            _clock((minute + rng.choice((-6, -4, 3, 5))) * 60 + rng.randrange(0, 50)),
            rng.choice(authors),
            rng.choice(notes),
        )
    )
    history.sort(key=lambda d: d.at)
    fault = Fault(faulty, _v(old), _v(new), minute, victim, rng.choice((0.25, 0.35, 0.5)))
    gap_minute = rng.randrange(10, _WINDOW - 10)
    lines = _logs(rng, services, deps, pods, fault, noisy, (gap_service, gap_minute), per_minute)
    teams = tuple((s, rng.choice(_TEAMS)) for s in services)
    return World(
        seed,
        size,
        services,
        tuple(deps.items()),
        teams,
        tuple(pods),
        tuple(history),
        lines,
        fault,
        noisy,
        (gap_service, gap_minute),
    )


def _logs(
    rng: random.Random,
    services: tuple[str, ...],
    deps: dict[str, tuple[str, ...]],
    pods: list[Pod],
    fault: Fault,
    noisy: str,
    gap: tuple[str, int],
    per_minute: int,
) -> tuple[Line, ...]:
    by_service: dict[str, list[Pod]] = {}
    for p in pods:
        by_service.setdefault(p.service, []).append(p)
    out = []
    for s in services:
        for m in range(_WINDOW):
            if (s, m) == gap:
                continue
            for _ in range(max(1, per_minute + rng.randrange(-1, 2))):
                second = m * 60 + rng.randrange(60)
                pod = rng.choice(by_service[s]).name
                req, trace = f"req-{_hex(rng, 8)}", _hex(rng, 16)
                route = (
                    rng.choice(_ROUTES[s])
                    .replace("{id}", str(rng.randrange(1000, 99999)))
                    .replace("{sku}", f"SKU-{rng.randrange(100, 999)}")
                )
                upstream = rng.choice(deps[s]) if deps[s] else "-"
                status, dur, level, extra = 200, rng.randrange(8, 240), "INFO", ""
                if (
                    s == fault.victim
                    and upstream == fault.service
                    and m >= fault.minute
                    and rng.random() < fault.rate
                ):
                    status, dur, level = 504, 3000 + rng.randrange(0, 40), "ERROR"
                    extra = f' error="upstream {fault.service} timed out after 3000ms"'
                elif rng.random() < 0.02:
                    status = 404
                out.append(
                    Line(
                        second,
                        s,
                        f"{_clock(second)}.{rng.randrange(1000):03d}Z {level:<5} {s} pod={pod} {req} {route}"
                        f" status={status}"
                        f" dur_ms={dur} upstream={upstream} trace={trace}{extra}",
                        status,
                    )
                )
            if s == noisy:  # harmless noise, before and after the fault alike
                for _ in range(rng.randrange(1, 4)):
                    second = m * 60 + rng.randrange(60)
                    out.append(
                        Line(
                            second,
                            s,
                            f"{_clock(second)}.{rng.randrange(1000):03d}Z WARN  {s} cache miss"
                            f" key=prod:{_hex(rng, 6)} fallback=origin",
                            0,
                        )
                    )
                if rng.random() < 0.15:
                    second = m * 60 + rng.randrange(60)
                    out.append(
                        Line(
                            second,
                            s,
                            f"{_clock(second)}.{rng.randrange(1000):03d}Z ERROR {s} client closed request"
                            " before response status=499",
                            499,
                        )
                    )
    out.sort(key=lambda line: (line.text[:24], line.service))  # by the full timestamp, milliseconds too
    return tuple(out)


# --- the tools -----------------------------------------------------------------------------------


def _seconds(clock: str) -> int:
    """'13:00' or '14:05:30' as seconds after 13:00."""
    parts = [int(p) for p in clock.split(":")] + [0, 0]
    return (parts[0] - 13) * 3600 + parts[1] * 60 + parts[2]


def list_services(w: World) -> str:
    deps, teams = dict(w.deps), dict(w.teams)
    count = {s: sum(p.service == s for p in w.pods) for s in w.services}
    rows = [
        {"name": s, "team": teams[s], "depends_on": list(deps[s]), "replicas": count[s]} for s in w.services
    ]
    return json.dumps({"namespace": "prod", "services": rows}, indent=2)


def list_pods(w: World, namespace: str = "prod") -> str:
    teams = dict(w.teams)
    items = [
        {
            "name": p.name,
            "namespace": namespace,
            "labels": {"app": p.service, "team": teams[p.service], "version": p.version},
            "node": p.node,
            "podIP": p.ip,
            "phase": "Running",
            "ready": True,
            "restarts": p.restarts,
            "startedAt": p.started + "Z",
            "image": f"registry.internal/{p.service}:{p.version}",
            "resources": {"cpu": "250m", "memory": "512Mi"},
        }
        for p in w.pods
    ]
    return json.dumps({"kind": "PodList", "items": items}, indent=2)


def list_deploys(w: World) -> str:
    rows = [
        {"service": d.service, "version": d.version, "at": d.at + "Z", "author": d.author, "note": d.note}
        for d in w.deploys
    ]
    return json.dumps({"deploys": rows}, indent=2)


def get_logs(w: World, service: str, since: str = "13:00", until: str = "15:00") -> str:
    """Every log line of a service from `since` up to `until` (HH:MM or HH:MM:SS, on 2026-11-03).

    Raises:
        ValueError: no such service.
    """
    if service not in w.services:
        raise ValueError(f"no service {service!r}: list_services names them")
    lo, hi = _seconds(since), _seconds(until)
    return (
        "\n".join(line.text for line in w.lines if line.service == service and lo <= line.second < hi) + "\n"
    )


def get_metrics(
    w: World, service: str, metric: str = "errors", since: str = "13:00", until: str = "15:00"
) -> str:
    """A per-minute series: requests, errors (status 500 and up) or p95_ms.

    Raises:
        ValueError: no such service or metric.
    """
    if service not in w.services:
        raise ValueError(f"no service {service!r}: list_services names them")
    if metric not in ("requests", "errors", "p95_ms"):
        raise ValueError(f"no metric {metric!r}: use requests, errors or p95_ms")
    lo, hi = _seconds(since) // 60, _seconds(until) // 60
    points = []
    for m in range(max(0, lo), min(_WINDOW, hi)):
        mine = [
            line for line in w.lines if line.service == service and line.second // 60 == m and line.status
        ]
        if metric == "requests":
            value: float = len(mine)
        elif metric == "errors":
            value = sum(line.status >= 500 for line in mine)
        else:
            durs = sorted(
                int(line.text.split("dur_ms=")[1].split()[0]) for line in mine if "dur_ms=" in line.text
            )
            value = durs[min(len(durs) - 1, int(len(durs) * 0.95))] if durs else 0
        points.append({"t": f"{DAY}T{minute_name(m)}:00Z", "value": value})
    return json.dumps({"service": service, "metric": metric, "points": points}, indent=2)


TOOLS = ("list_services", "list_pods", "list_deploys", "get_logs", "get_metrics")


def call(w: World, tool: str, args: dict[str, Any]) -> str:
    """A tool's output for a call, as the MCP server gives it.

    Raises:
        ValueError: no such tool.
    """
    match tool:
        case "list_services":
            return list_services(w)
        case "list_pods":
            return list_pods(w, **args)
        case "list_deploys":
            return list_deploys(w)
        case "get_logs":
            return get_logs(w, **args)
        case "get_metrics":
            return get_metrics(w, **args)
    raise ValueError(f"no tool {tool!r}: use one of {', '.join(TOOLS)}")


# --- the tasks -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """A task in a world: the prompt, its truth, and the tool calls its answer usually needs
    (`probes`), whose outputs layer 1 folds and checks without a model."""

    task_id: str
    kind: str  # the answer instruction's kind: spot | count | enumerate | lookup | absent
    prompt: str
    truth: Truth
    probes: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]  # (tool, its arguments)
    prefix: str = ""
    path: str = ""


def failures(w: World, since: int, until: int) -> int:
    """The victim's requests with status 500 and up, from minute `since` up to `until`."""
    return sum(
        line.service == w.fault.victim and line.status >= 500 and since * 60 <= line.second < until * 60
        for line in w.lines
    )


def tasks(w: World) -> tuple[Task, ...]:
    f, prefix = w.fault, f"incident-{w.size}-{w.seed}"
    stale = frozenset(p.name for p in w.pods if p.service == f.service and p.version != f.new)
    gap_service, gap_minute = w.gap
    rollout = next(d for d in w.deploys if d.service == f.service and d.version == f.new)
    return (
        Task(
            f"{prefix}-cause",
            "spot",
            f"{f.victim} has been returning errors since about {minute_name(f.minute + 2)}."
            " Which deploy caused"
            " it? Answer with the service and its version.",
            Needle(f.new, frozenset({f"v{f.new}"})),
            (
                ("list_deploys", ()),
                ("get_logs", (("service", f.victim),)),
                ("get_metrics", (("service", f.victim),)),
            ),
        ),
        Task(
            f"{prefix}-count",
            "count",
            f"How many {f.victim} requests returned a 5xx status from 14:00 up to 15:00?",
            Number(failures(w, 60, _WINDOW)),
            (
                ("get_logs", (("service", f.victim), ("since", "14:00"))),
                ("get_logs", (("service", f.victim),)),
            ),
        ),
        Task(
            f"{prefix}-stale",
            "enumerate",
            f"{f.service} was rolled out to {f.new} at {rollout.at[11:16]}."
            " Are any of its pods still running an"
            " older version? List them by name.",
            Items(stale, frozenset(p.name for p in w.pods if p.service == f.service)),
            (("list_pods", ()),),
        ),
        Task(
            f"{prefix}-gap",
            "lookup",
            f"Between 13:00 and 15:00, was there a minute in which {gap_service} logged nothing at all?"
            " Give that"
            " minute as HH:MM.",
            Exact(minute_name(gap_minute)),
            (("get_logs", (("service", gap_service),)),),
        ),
        Task(
            f"{prefix}-healthy",
            "absent",
            f"The {w.noisy} team says its logs have looked noisy all day. Is anything actually wrong with"
            f" {w.noisy}? Name what is wrong, or answer none.",
            Absent(frozenset({w.noisy, *(p.name for p in w.pods if p.service == w.noisy)})),
            (("get_logs", (("service", w.noisy),)), ("get_metrics", (("service", w.noisy),))),
        ),
    )

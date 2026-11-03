"""Synthetic payloads with a chosen set of planted items, for the eval tasks.

One generator per format. `planted` is the set of item indices that carry the anomaly (empty for
the absent control, one for spot, several for count and enumerate). `quiet` plants an anomaly the
fold has no rule for (a numeric outlier, an unremarkable-looking line, a zero amount, a half-width
card) instead of one it has a rule for (a crash-looping phase, an ERROR line, a disabled button, a
hidden layer). Names, refs and ids are random and unique, so neither a name nor arithmetic gives
an answer away. The same seed always gives the same payload.
"""

import json
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Payload:
    raw: str
    names: tuple[str, ...]  # every item's name, in order: the candidates an answer could name
    planted: tuple[str, ...]  # the names of the planted items
    lookups: tuple[tuple[str, str], ...]  # (an item's name, its unique value), for every item


def _unique(rng: random.Random, n: int, make) -> list[str]:
    seen: set[str] = set()
    out = []
    while len(out) < n:
        v = make()
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def pods(size: int, planted: frozenset[int], seed: str, quiet: bool = False) -> Payload:
    rng = random.Random(seed)
    names = _unique(rng, size, lambda: f"web-{rng.getrandbits(40):010x}")
    ips = _unique(rng, size, lambda: f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(2, 254)}")
    items = []
    for i in range(size):
        bad = i in planted
        phase = "CrashLoopBackOff" if bad and not quiet else "Running"
        items.append(
            {
                "name": names[i],
                "namespace": "default",
                "node": f"node-{rng.choice('abcdefgh')}",
                "ip": ips[i],
                "image": "registry.local/web:1.4.2",
                "restarts": 97 if bad and quiet else rng.randint(0, 3),
                "ready": not (bad and not quiet),
                "phase": phase,
                "status": {"phase": phase, "qos": "Burstable"},
                "labels": {"app": "web", "tier": rng.choice("abc")},
            }
        )
    planted_names = tuple(names[i] for i in sorted(planted))
    return Payload(
        json.dumps({"items": items}), tuple(names), planted_names, tuple(zip(names, ips, strict=True))
    )


def logs(size: int, planted: frozenset[int], seed: str, quiet: bool = False) -> Payload:
    """Request logs. The planted line names its request; a rule-kind line is a failed payment (its
    order id is what count and enumerate tasks name), a quiet one an exhausted connection pool."""
    rng = random.Random(seed)
    reqs = _unique(rng, size, lambda: f"req-{rng.getrandbits(32):08x}")
    users = _unique(rng, size, lambda: f"u-{rng.getrandbits(24):06x}")
    lines, hits = [], []
    for i in range(size):
        t = f"2026-11-03T{i // 3600 % 24:02d}:{i // 60 % 60:02d}:{i % 60:02d}Z"
        if i in planted and quiet:
            lines.append(f"{t} INFO  pool connections available=0 of 50 req={reqs[i]} user={users[i]}")
            hits.append(reqs[i])
        elif i in planted:
            order = f"ORD-{rng.getrandbits(24):06x}"
            lines.append(f"{t} ERROR payment failed for order {order} req={reqs[i]} user={users[i]}")
            hits.append(order)
        else:
            path = rng.choice(["/api/items", "/api/users", "/api/orders", "/health"])
            lines.append(f"{t} INFO  GET {path} req={reqs[i]} user={users[i]} 200 {rng.randint(1, 900)}ms")
    return Payload("\n".join(lines), tuple(reqs), tuple(hits), tuple(zip(reqs, users, strict=True)))


def snapshot(size: int, planted: frozenset[int], seed: str, quiet: bool = False) -> Payload:
    """A Playwright-style accessibility snapshot of an invoices page; a rule-kind anomaly is a
    disabled Pay button, a quiet one an invoice of $0.00."""
    rng = random.Random(seed)
    invoices = _unique(
        rng, size, lambda: f"INV-{rng.randint(10, 99)}{rng.getrandbits(20):05x}"
    )  # with a digit
    refs = [f"e{r}" for r in rng.sample(range(10, 100_000), 2 * size + 8)]
    lines = [
        "- Page URL: https://billing.local/invoices",
        "- Page Title: Invoices",
        f"- generic [ref={refs[-1]}]:",
        f"  - banner [ref={refs[-2]}]:",
        f'    - link "Billing home" [ref={refs[-3]}]',
        f"  - main [ref={refs[-4]}]:",
        f'    - heading "Invoices" [level=1] [ref={refs[-5]}]',
        f"    - list [ref={refs[-6]}]:",
    ]
    for i in range(size):
        bad = i in planted
        flag = " [disabled]" if bad and not quiet else ""
        amount = "0.00" if bad and quiet else f"{rng.randint(20, 900)}.{rng.randint(0, 99):02d}"
        lines += [
            f"      - listitem [ref={refs[2 * i]}]:",
            f"        - text: Invoice {invoices[i]}",
            f"        - text: ${amount} due {rng.randint(1, 28):02d} Nov",
            f'        - button "Pay {invoices[i]}" [ref={refs[2 * i + 1]}]{flag}',
        ]
    lines += [f"  - contentinfo [ref={refs[-7]}]:", "    - text: (c) Billing"]
    lookups = tuple((invoices[i], refs[2 * i + 1]) for i in range(size))
    return Payload("\n".join(lines), tuple(invoices), tuple(invoices[i] for i in sorted(planted)), lookups)


def figma(size: int, planted: frozenset[int], seed: str, quiet: bool = False) -> Payload:
    """Figma-style node metadata, packed on one line, for a grid of product cards; a rule-kind
    anomaly is a hidden layer, a quiet one a card half the width of the others."""
    rng = random.Random(seed)
    names = _unique(
        rng, size, lambda: f"Card {rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{rng.randint(1000, 9999)}"
    )
    ids = _unique(rng, 5 * size + 2, lambda: f"{rng.randint(1, 99999)}:{rng.randint(1, 99999)}")
    parts = [f'<canvas id="{ids[-1]}" name="Checkout">', f'<frame id="{ids[-2]}" name="Product grid">']
    for i in range(size):
        bad = i in planted
        hidden = ' hidden="true"' if bad and not quiet else ""
        width = 160 if bad and quiet else 320
        parts += [
            f'<frame id="{ids[5 * i]}" name="{names[i]}" x="{(i % 4) * 340}" y="{(i // 4) * 420}" '
            f'width="{width}" height="400"{hidden}>',
            f'<rectangle id="{ids[5 * i + 1]}" name="Image" width="{width}" height="240"/>',
            f'<text id="{ids[5 * i + 2]}" name="Title" width="{width - 32}" height="24"/>',
            f'<instance id="{ids[5 * i + 3]}" name="Button/Primary" width="{width - 32}" height="48"/>',
            "</frame>",
        ]
    parts += ["</frame>", "</canvas>"]
    lookups = tuple((names[i], ids[5 * i]) for i in range(size))
    return Payload("".join(parts), tuple(names), tuple(names[i] for i in sorted(planted)), lookups)

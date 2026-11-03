"""Synthetic payloads with a chosen set of planted items, for the eval tasks.

One generator per format. `planted` is the set of item indices that carry the anomaly (empty for
the absent control, one for spot, several for count and enumerate). Every item also has a unique
value, for lookups. The same seed always gives the same payload.
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


def pods(size: int, planted: frozenset[int], seed: str) -> Payload:
    rng = random.Random(seed)
    items, lookups = [], []
    for i in range(size):
        name = f"web-{rng.getrandbits(32):08x}-{i:04d}"
        ip = f"10.{i // 250}.{i % 250}.{rng.randint(2, 254)}"
        phase = "CrashLoopBackOff" if i in planted else "Running"
        items.append(
            {
                "name": name,
                "namespace": "default",
                "node": f"node-{rng.choice('abcdefgh')}",
                "ip": ip,
                "image": "registry.local/web:1.4.2",
                "restarts": rng.randint(0, 3),
                "ready": i not in planted,
                "phase": phase,
                "status": {"phase": phase, "qos": "Burstable"},
                "labels": {"app": "web", "tier": rng.choice("abc")},
            }
        )
        lookups.append((name, ip))
    names = tuple(p["name"] for p in items)
    return Payload(
        json.dumps({"items": items}), names, tuple(names[i] for i in sorted(planted)), tuple(lookups)
    )


def logs(size: int, planted: frozenset[int], seed: str) -> Payload:
    rng = random.Random(seed)
    lines, names, lookups, hits = [], [], [], []
    for i in range(size):
        t = f"2026-11-03T{i // 3600 % 24:02d}:{i // 60 % 60:02d}:{i % 60:02d}Z"
        req, user = f"req-{rng.getrandbits(32):08x}", f"u-{rng.getrandbits(24):06x}"
        if i in planted:
            order = f"ORD-{rng.randint(10000, 99999)}-{i:04d}"
            lines.append(f"{t} ERROR payment failed for order {order} req={req} user={user}")
            hits.append(order)
        else:
            path = rng.choice(["/api/items", "/api/users", "/api/orders", "/health"])
            lines.append(f"{t} INFO  GET {path} req={req} user={user} 200 {rng.randint(1, 900)}ms")
        names.append(req)
        lookups.append((req, user))
    return Payload("\n".join(lines), tuple(names), tuple(hits), tuple(lookups))


def snapshot(size: int, planted: frozenset[int], seed: str) -> Payload:
    """A Playwright-style accessibility snapshot of an invoices page."""
    rng = random.Random(seed)
    lines = [
        "- Page URL: https://billing.local/invoices",
        "- Page Title: Invoices",
        "- generic [ref=e1]:",
        "  - banner [ref=e2]:",
        '    - link "Billing home" [ref=e3]',
        "  - main [ref=e4]:",
        '    - heading "Invoices" [level=1] [ref=e5]',
        "    - list [ref=e6]:",
    ]
    names, lookups = [], []
    ref = 7
    for i in range(size):
        inv = f"INV-{rng.randint(1000, 9999)}-{i:04d}"
        button = f"e{ref + 1}"
        flag = " [disabled]" if i in planted else ""
        lines += [
            f"      - listitem [ref=e{ref}]:",
            f"        - text: Invoice {inv}",
            f"        - text: ${rng.randint(20, 900)}.00 due {rng.randint(1, 28):02d} Nov",
            f'        - button "Pay {inv}" [ref={button}]{flag}',
        ]
        ref += 2
        names.append(inv)
        lookups.append((inv, button))
    lines += [f"  - contentinfo [ref=e{ref}]:", "    - text: (c) Billing"]
    return Payload("\n".join(lines), tuple(names), tuple(names[i] for i in sorted(planted)), tuple(lookups))


def figma(size: int, planted: frozenset[int], seed: str) -> Payload:
    """Figma-style node metadata, packed on one line, for a grid of product cards."""
    rng = random.Random(seed)
    parts = ['<canvas id="0:1" name="Checkout">', '<frame id="1:10" name="Product grid">']
    names, lookups = [], []
    for i in range(size):
        node, name = f"{10 + i}:{1000 + i}", f"Card {rng.randint(100, 999)}-{i:04d}"
        hidden = ' hidden="true"' if i in planted else ""
        parts += [
            f'<frame id="{node}" name="{name}" x="{(i % 4) * 340}" y="{(i // 4) * 420}" width="320" '
            f'height="400"{hidden}>',
            f'<rectangle id="{10 + i}:5001" name="Image" width="320" height="240"/>',
            f'<text id="{10 + i}:5002" name="Title" width="288" height="24"/>',
            f'<instance id="{10 + i}:5003" name="Button/Primary" width="288" height="48"/>',
            "</frame>",
        ]
        names.append(name)
        lookups.append((name, node))
    parts += ["</frame>", "</canvas>"]
    return Payload("".join(parts), tuple(names), tuple(names[i] for i in sorted(planted)), tuple(lookups))

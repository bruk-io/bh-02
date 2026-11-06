"""The example envelopes the findings page shows, made by the hook's own code.

`invoices` is a list of 100 invoices (two overdue) whose tool call names INV-1024, folded under the
schema recipe with the exact-counts banner; `calm` is the same list with every invoice paid; `log`
and `snapshot` are two eval tasks' outputs. The functional test compares them with the code blocks
in results/FINDINGS.md, so the page cannot show an envelope the code no longer makes.
"""

import json
import random

from claude_code.hook import render
from compressors.cli import fold_text
from compressors.common import query_terms
from compressors.config import FoldConfig
from compressors.route import Folded, fold
from evals.tasks import task

SAVED = "/tmp/tool-results/invoices.json"  # where the example says the full output is saved
_CUSTOMERS = ("Acme", "Birch", "Cobalt", "Dune", "Ember")
_EXACT = FoldConfig(banner="exact")


def _invoices(overdue: tuple[int, ...]) -> str:
    rng = random.Random(7)
    rows = [
        {
            "id": f"INV-{1001 + i}",
            "customer": _CUSTOMERS[i % 5],
            "amount": round(rng.uniform(20, 900), 2),
            "status": "overdue" if i in overdue else "paid",
        }
        for i in range(100)
    ]
    return json.dumps({"invoices": rows}, indent=2)


def _folded(raw: str, terms: frozenset[str]) -> Folded:
    """The hook's fold of `raw`.

    Raises:
        ValueError: `raw` is small enough to pass through, so it has no envelope.
    """
    folded = fold(raw, terms=terms, view="schema", config=_EXACT)
    if folded is None:
        raise ValueError("the example passed through unfolded: make it larger than the 2,000-token budget")
    return folded


def invoices() -> str:
    """The banner and envelope of the invoice list, as the model reads them."""
    folded = _folded(_invoices((16, 71)), query_terms({"invoice": "INV-1024"}))
    return render(folded, SAVED, banner="exact")


def calm() -> str:
    """The envelope of the same list with every invoice paid, without its banner."""
    return _folded(_invoices(()), frozenset()).body


def _body(task_id: str) -> str:
    """An eval task's envelope under the schema recipe, without the CLI's header line."""
    text = fold_text(task(task_id).payload(), budget=2000, view="schema").text
    return text.split("\n", 1)[1]


def log() -> str:
    return _body("log-M-count-k3")


def snapshot() -> str:
    return _body("a11y-M-count-k3")

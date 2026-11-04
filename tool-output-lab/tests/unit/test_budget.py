"""The budget is kept: the cases review 1 found over it (R4), folded through the fold interface."""

import json
import random

import pytest

from compressors.cli import fold_text
from compressors.common import estimate_tokens
from compressors.route import LINE_BRANCHES, lines_envelope
from evals.envelope_check import text_problems


def _cases():
    rng = random.Random(0)
    vocab = [f"word{k}x" for k in range(500)]
    wide = "\n".join(
        ("2026-11-03 INFO " + " ".join(rng.choice(vocab) for _ in range(100)))[:428] for _ in range(2000)
    )
    fns = "".join(f"def f{i}(a):\n    x = a\n    y = x\n    return y\n\n" for i in range(20))
    gap = "\n".join(f"V{i} = '" + "v" * 200 + "'" for i in range(60))
    return [
        ("log of 428-char lines", wide, "", 2000),
        (
            "3,000 assignments",
            "\n".join(f'SETTING_{i} = "value number {i}"' for i in range(3000)),
            "s.py",
            500,
        ),
        (
            "unparsable code",
            "import os\nCONFIG = dict(\n" + "\n".join(f"    k{i}=1," for i in range(800)),
            "u.py",
            300,
        ),
        (
            "a traceback under error",
            json.dumps({"status": 500, "error": "Traceback\n" + "  File x.py\n" * 3500}),
            "",
            500,
        ),
        ("50 long messages", json.dumps([{"id": i, "message": "m" * 6600} for i in range(50)]), "", 2000),
        (
            "a gap after hidden siblings",
            fns + gap + "\n\ndef last(a):\n    x = a\n    return x\n",
            "g.py",
            1500,
        ),
        (
            "a parent and child on the same lines",
            "F = [{\n" + "\n".join(f'    "f{i}": "v{i}",' for i in range(400)) + "\n}]\n",
            "f.py",
            300,
        ),
        ("3,000 distinct keys", json.dumps([{f"host-{i:05d}": {"up": True}} for i in range(3000)]), "", 2000),
    ]


@pytest.mark.parametrize(("name", "text", "path", "budget"), _cases(), ids=[c[0] for c in _cases()])
def test_the_fold_fits_the_budget_and_every_claim_holds(name, text, path, budget):
    result = fold_text(text, budget=budget, path=path, quiet=True)
    assert estimate_tokens(result.text) <= budget * 1.1, name
    if result.branch in LINE_BRANCHES:  # an envelope of lines: every claim holds against its source
        env, source = lines_envelope(text, result.branch, frozenset(), budget, language=result.language or "")
        assert env.text() == result.text and text_problems(source, env, run_tools=False) == []


def test_a_traceback_under_error_is_cut_but_its_start_kept():
    raw = json.dumps({"status": 500, "error": "Traceback (most recent call last)\n" + "  File x.py\n" * 3500})
    out = fold_text(raw, budget=500, quiet=True).text
    assert "Traceback (most recent call last)" in out and "chars]" in out


def test_identifier_keys_are_whole_words_and_digests_stay_whole():
    digest = "a" * 64
    raw = json.dumps([{"sha256": digest, "shape": "s" * 900, "hashtags": "h" * 900} for _ in range(40)])
    out = fold_text(raw, budget=800, quiet=True).text
    assert digest in out
    assert "s" * 900 not in out and "h" * 900 not in out

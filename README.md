# tool-output-lab

A scratch lab for one question: does compressing large tool outputs before they reach the model
help, and which compressors earn their place. Not part of bh-02 (no `pyproject.toml`, so it is not a
uv workspace member and no gate sees it). Move it to its own repo when it has results worth keeping.

Source idea: `Filtering_Large_Tool_Outputs.pdf` (a Gemini chat export). Take the ideas, not the code.

## Target: Claude Code

The lab now tests the idea inside Claude Code, through two hooks and a headless A/B:

- `claude_code/hook.py`, a `PostToolUse` hook on `mcp__.*`: folds large MCP results (JSON, XML,
  accessibility outlines, logs), including the ones Claude Code itself spilled to a file, and
  points Claude at the saved raw output. `TOOL_OUTPUT_LAB_MODE=spilled-only` folds only what Claude
  Code spilled, which is what the A/Bs recommend.
- `claude_code/read_gate.py`, a `PreToolUse` hook on `Read`: answers the first whole-file read of a
  large source file with its ast-grep outline. The probes show current models rarely need it.
- `claude_code/ab.py` with `claude_code/fixture_mcp.py`: headless `claude -p` runs on synthetic
  needle payloads, native against the hook, scored on the answer, tokens, cost and tool calls.

Results and what they mean: `results/FINDINGS.md`.

## Design under test

Deterministic folding by format, with the raw output kept and named, so nothing is lost:

- JSON: long arrays keep head, tail and the items that stand out, in place; wide objects keep
  their first keys and the ones the query names.
- Trees (`compressors/tree.py`): code through ast-grep, XML, indentation outlines. Outline first,
  stand-outs and containers before bodies, each hidden range one line-numbered marker.
- Logs: runs of repeated lines collapse; head, tail and windows around error words stay.

The query signal is the tool call's own arguments, ignoring terms most items share.

## Kill criteria (set before measuring)

A branch, or a mode of the hook, is cut if either holds against native Claude Code:

- answers drop more than 3 points;
- input tokens, recovery reads included, are not lower.

Change these numbers only before a run, never after seeing one. So far: folding results Claude Code
spilled passes both; folding inline results fails the second (A/B 1 and 2).

## Running

```
./lab check                                   # format, lint, tests (Python 3.15 through uv)
./lab extract ~/.claude/projects              # transcripts -> corpus/results.jsonl
./lab stats [--budget 2000] [-o results/x.md] # corpus sizes, formats, deterministic compression
./lab needle [--seeds 5] [-o results/x.md]    # synthetic needle survival grid
./lab ab [--model M] [--seeds N] [--only json log a11y figma] [--name x]  # headless Claude Code A/B (costs money)
```

## Layout

```
lab            the one entry point
corpus/        private transcripts and extracted results (gitignored)
compressors/   route.fold/compress (the router), json_fold, tree, code, lines, html, recovery
claude_code/   hook (PostToolUse), read_gate (PreToolUse), fixture_mcp, ab
harness/       extract, stats, needle
tests/unit/    pure-function tests
results/       one file per run, never edited after; FINDINGS.md is the running summary
```

## Status

See PLAN.md for the stages and results/FINDINGS.md for what has been learned.

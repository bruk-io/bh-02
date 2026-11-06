# tool-output-lab

A scratch lab for one question: when a tool returns a large output, which composition of the
envelope gives Claude Code what it needs at the least context and cost. Not part of bh-02 (no
`pyproject.toml`, so it is not a uv workspace member and no gate sees it). Move it to its own repo
when it has results worth keeping.

## The envelope

A large output reaches the model as four parts, each made by a producer that a composition names:
its **shape** in exact numbers, the **anomalies** that break it with their addresses, **samples**
verbatim, and how to **get more** (a ready command, or how to read any part). JSON is addressed by
jq path; a log, an outline, XML, a page, plain text and code by line number. The raw output stays
saved and the envelope names the file. Every claim an envelope makes is checked against the data
in layer 1. PLAN.md has the protocol, each format's producers and the compositions.

## The tool

```
./lab fold FILE [--budget 2000] [--query WORDS] [--view sample|schema] [--set KNOB=VALUE] [--save PATH]
COMMAND | ./lab fold [--budget 2000] ...
```

Text that fits the budget comes back unchanged. Everything else folds as an envelope: `--view` names
a recipe (sample or schema) and `--set FORMAT_envelope.PART=PRODUCER` swaps one part (`json_envelope`,
`log_envelope`, `tree_envelope`). Code folds by its extension, or `--lang`, through ast-grep.

## Target: Claude Code

- `claude_code/hook.py`, a `PostToolUse` hook on `mcp__.*|Bash`: folds large MCP results and Bash
  output, including what Claude Code itself saved to a file, and points Claude at the saved raw. It
  acts after a command has run, so permission rules are checked on the real command. Read is never
  folded. By default (`inline`) it folds only results under Claude Code's spill threshold;
  `TOOL_OUTPUT_LAB_MODE=spilled` folds only spills, `all` both. `TOOL_OUTPUT_LAB_VIEW` and
  `TOOL_OUTPUT_LAB_SET` choose the composition.
- `evals/l2.py`, with `claude_code/fixture_mcp.py` (serves a synthetic task) and
  `claude_code/replay_mcp.py` (replays an MCP-Atlas task's recorded calls): headless `claude -p`
  runs, native against the hook, scored from the answer, with tokens per request, the final
  context, cost, calls and time.

Results: `results/FINDINGS.md`, which `./lab page` turns into one self-contained page,
`pages/findings.html` (charts, the annotated envelope and folds come from markers in its comments).

## Kill criteria (set before measuring)

A composition, or a mode of the hook, is cut if either holds against native Claude Code:

- answers drop more than 3 points;
- input tokens, recovery reads included, are not lower: measured as the final context, the input
  of the session's last request, which holds every recovery read (the owner's reading, 2026-11-03;
  summed input is reported, not judged).

Change these numbers only before a run, never after seeing one. Layer 2 applies the criteria to 95%
intervals.

## Running

```
./lab check                                       # green: format and lint checked, strict mypy, tests (Python 3.15 through uv)
./lab fix                                         # apply the formatter and ruff's safe fixes
./lab fetch mcp-atlas                             # the MCP-Atlas tasks into corpus/real/ (untracked)
./lab fetch hdfs                                  # the HDFS log and its labels into corpus/real/ (untracked)
curl -sSo corpus/real/pypi-click.json https://pypi.org/pypi/click/json   # the PyPI release JSON (untracked)
./lab evals l1 --only json pypi atlas [--view schema] [--set KNOB=VALUE]   # layer 1: fold and check (free)
./lab evals sweep sweeps/envelopes.toml           # layer 1 over a grid of compositions (free; logs.toml, trees.toml)
./lab evals dials dials/haiku-atlas.toml --dry-run   # layer 2: native against each composition (paid)
./lab evals sessions sessions/haiku.toml --dry-run   # layer 2: follow-up questions in one session (paid)
```

## Layout

```
lab            the one entry point
corpus/        fetched real data (gitignored)
compressors/   route (the router); envelope (the protocol); envelope_json, schema, json_items (JSON); envelope_text, envelope_log, envelope_tree (lines); tree, code, html (parsers)
claude_code/   hook (PostToolUse); fixture_mcp and replay_mcp (serve a task to Claude Code); fold_mcp
evals/         truth, synthetic, real, atlas, tasks; envelope_check, schema_check; l1, sweep, l2, dials, sessions, stats
harness/       fetch (real corpora); extract, stats (Claude Code transcripts)
pages/         findings (FINDINGS.md as one HTML page), examples (its envelopes, made by the hook); assets/
scenarios/     seal (the sealed test set's key, commitment and ledger); SCENARIOS.md has the v2 design
tests/         unit (pure functions) and functional (files and processes)
dials/ sessions/ sweeps/   run specs
results/       one file per run, never edited after; FINDINGS.md is what we found, kept current
```

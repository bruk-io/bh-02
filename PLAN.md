# Plan

Goal: find which composition of the envelope gives Claude Code what it needs from a large tool
output at the least context and cost, measured against native Claude Code on the same tasks. The
kill criteria are in README.md.

## The envelope

A large output reaches the model as an envelope of four parts: **shape** (what the data is, in
exact numbers), **anomalies** (what breaks the shape, each with its address), **samples** (what
items look like, verbatim) and **get more** (how to fetch the rest: addresses and a ready command).
The raw output stays saved, and the envelope names the file.

A producer makes each part. Producers run in a fixed order, shape first, and each is given the
parts before it, which it reads through what they claim (a count, the values a field holds, a row
that breaks the shape, a command and what it prints). Each part offers levels, fullest first, and
each level states the claims it makes. `compose` starts every part at its tersest level and raises
them in priority order while the text fits the budget.

Layer 1 checks every claim against the data, apart from the producers' code: a jq-path walker
recomputes counts, values and rows, and each command is run with `jq` itself. It also checks that
each claim is said on a line of its level's text, since a claim the text does not show is one the
model never reads.

Code: `compressors/envelope.py` (the protocol and `compose`), `compressors/envelope_json.py` (JSON's
producers and recipes), `evals/envelope_check.py` (layer 1's check). JSON is the one format with an
envelope so far.

## Compositions

A composition names a producer for each part, a priority and a budget.

| Part | Producers |
|---|---|
| shape | `fields` (every field's types, values and counts, ranges), `summary` (each field's type, and counts for fields with six values or fewer) |
| anomalies | `exceptions` (every row that breaks its collection's shape, and what breaks it), `standouts` (items the stand-out rules pick: rare values, error keys, failing statuses), `none` |
| samples | `matches` (rows holding a query term at most a fifth of the rows hold), `typical` (those, and a row that breaks nothing), `head-tail` (those, and each collection's first two rows and its last), `none` |
| get more | `jq` (a ready query for the rows that break the shape, and how to read any path), `rows` (how to read any row or range), `none` |

Two compositions are named recipes, chosen with `--view` (the hook's `TOOL_OUTPUT_LAB_VIEW`):
`sample`, the default, is summary, standouts, head-tail and rows; `schema` is fields, exceptions,
matches and jq. Any other composition is a recipe with parts swapped by knobs, such as `--set
json_envelope.samples=none` or `json_envelope.priority=shape,anomalies,samples,nav`. Every entry
point takes the same knobs: `./lab fold`, layer 1, layer 2, the hook, and the specs in `dials/`,
`sessions/` and `sweeps/`.

## How compositions are compared

- **Layer 1, free.** Every task's payload is folded under each composition: claims checked, then
  sufficiency (the task's own scorer run on the envelope's text, an upper bound on what a model can
  answer without fetching) and size. `./lab evals sweep sweeps/envelopes.toml` runs a grid.
- **Layer 2, paid.** Headless Claude Code on the same tasks, native against each composition,
  paired by task and repetition (`./lab evals dials SPEC`, a setting per composition). `./lab evals
  sessions SPEC` asks follow-up questions about one result in one session.
- **Tasks.** JSON only: synthetic pod lists with planted answers (`json`), the PyPI release file
  (`pypi`), and MCP-Atlas tasks replayed from their recorded tool calls and scored by the facts in
  each task's answer claims (`atlas`). EVALS.md has the task kinds and the statistics.

## Stages

| # | Stage | Needs a model | Status |
|---|---|---|---|
| M1 | Log each fold with its session, so every layer-2 row says whether the envelope acted on the task's large output, and the report splits on it | no | |
| M2 | MCP-Atlas tasks limited to those whose large output is JSON (50 of 59), so every fold under test is an envelope | no | |
| M3 | Layer-1 baseline: every composition in `sweeps/envelopes.toml` on the synthetic, PyPI and MCP-Atlas tasks | no | |
| M4 | Layer 2 on Haiku: native against the sample and schema recipes on MCP-Atlas (about $3) and on the synthetic JSON tasks at M and L (about $1) | yes | |
| M5 | Layer 2 on compositions layer 1 cannot tell apart: a typical sample or none, no get more | yes | |
| M6 | Sonnet on the compositions Haiku leaves standing | yes | |
| M7 | Sessions: follow-up questions on one JSON result, native against the two recipes (`sessions/haiku.toml`, about $4) | yes | |

Later, other formats on the same protocol: trees (accessibility snapshots, Figma) with a nested
envelope for each run of repeated siblings, and logs as templates (the templates and their counts
as the shape, the rare ones as the anomalies).

## Decisions

- Python 3.15 through `uv run --no-project`, standard library only for the envelope; own
  `pytest.ini` and `ruff.toml`, so the bh-02 root config never applies here.
- Producers are pure functions and an envelope is a value. Layer 1's checks share no code with the
  producers.
- Every count, range and row an envelope states is computed over all rows, never sampled. A model
  will trust "Failed 3".
- Budgets count tokens as `ceil(chars / 4)`; layer 2 reports the API's own counts.
- Query terms come from the tool call's own arguments, ignoring terms most rows share.

## Known caveat

The MCP-Atlas replay answers a call with the closest recorded call of the same tool, so a model
that asks differently from the recorded run can get a smaller output and never see the large one.
M1 measures how often, and the report keeps those sessions apart.

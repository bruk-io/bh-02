# Plan

Goal: find which composition of the envelope gives Claude Code what it needs from a large tool
output at the least context and cost, measured against native Claude Code on the same tasks. The
kill criteria are in README.md.

## The envelope

A large output reaches the model as an envelope of four parts: **shape** (what the output is, in
exact numbers), **anomalies** (what breaks the shape, each with its address), **samples** (what
items look like, verbatim) and **get more** (how to fetch the rest: addresses and a ready command).
The raw output stays saved, and the envelope names the file.

A producer makes each part. Producers run in a fixed order, shape first, and each is given the
parts before it, which it reads through what they claim. Each part offers levels, fullest first,
and each level states the claims it makes. `compose` starts every part at its tersest level and
raises them in priority order while the text fits the budget.

Every format folds as an envelope, addressed in its own terms:

- **JSON** by jq path (`compressors/envelope_json.py`). Its claims are counts, the values a field
  holds, a row's note, that a list of rows is complete, a sample's text, and what a jq command
  prints.
- **Logs**, and any output read line by line, by line number (`compressors/envelope_log.py`). A
  line's template is the line with every token that holds a digit or a hex id as `<*>`; the shape
  is each template said more than once and its count, with the values of its few-valued holes.
- **Trees** by line number (`compressors/envelope_tree.py`): indented outlines such as
  accessibility snapshots, XML (pretty-printed when it comes packed), a page once it is text (by
  its headings), plain text (a node a line) and source code (by its definitions, through
  ast-grep). A run is a node's children most of whose first lines share a template; the shape is
  the outline of headers, each run counted, and a run's items are read as a log is, counted by item.

Line-addressed claims (`Shows`, `Total`, `Alike`, `Prints` in `compressors/envelope.py`) say what
lines read, how many lines have a template or hold a value in one of its holes, and what a grep
prints. Layer 1 checks every claim against the data apart from the producers' code: for JSON a
jq-path walker and `jq` itself, for lines its own line split, template rule and reading of the
clip marker, and `grep` itself. It also checks that each claim is said on a line of its level's
text, since a claim the text does not show is one the model never reads.
`compressors/route.lines_envelope` makes any line-read envelope and the source its numbers refer to.

## Compositions

A composition names a producer for each part, a priority and a budget. Each format has its own
knob section: `json_envelope`, `log_envelope`, `tree_envelope`.

| Part | JSON | Logs | Trees |
|---|---|---|---|
| shape | `fields` (every field's types, values and counts, ranges), `summary` (types, counts for fields with six values or fewer) | `templates` (each template and its count, few-valued holes too), `count` (the totals) | `outline` (headers, each run counted by its kinds of item) |
| anomalies | `exceptions` (every row that breaks its collection's shape), `standouts` (the stand-out rules), `none` | `rare` (rare templates, error words few lines say, rare values in a hole), `errors` (error words), `none` | `rare` (items holding a line or a value few items hold, error words), `errors`, `none` |
| samples | `matches` (rows holding a query term), `typical` (and a row that breaks nothing), `head-tail` (and each collection's ends), `none` | `matches` (lines holding a query term), `typical` (and the commonest templates' first lines), `head-tail`, `none` | `matches` (the query's items), `typical` (and each run's first), `head-tail`, `none` |
| get more | `jq` (a query for the rows that break the shape), `rows` (how to read any row), `none` | `grep` (a command per anomaly printing exactly its lines), `sed` (any lines), `none` | `grep`, `sed`, `none` |

Two compositions are named recipes for every format, chosen with `--view` (the hook's
`TOOL_OUTPUT_LAB_VIEW`): `sample`, the default, shows samples from the ends and how to read any
part; `schema` shows JSON's every field and the rows or lines the query names, with a ready command
for the anomalies. Any other composition is a recipe with parts swapped by knobs, such as `--set
log_envelope.samples=typical` or `tree_envelope.anomalies=none`. Every entry point takes the same
knobs: `./lab fold`, layer 1, layer 2, the hook, and the specs in `dials/`, `sessions/` and
`sweeps/`.

## How compositions are compared

- **Layer 1, free.** Every task's payload is folded under each composition: claims checked, then
  sufficiency (the task's own scorer run on the envelope's text, an upper bound on what a model can
  answer without fetching) and size. `./lab evals sweep SPEC` runs a grid: `sweeps/envelopes.toml`
  (JSON), `sweeps/logs.toml`, `sweeps/trees.toml`.
- **Layer 2, paid.** Headless Claude Code on the same tasks, native against each composition,
  paired by task and repetition (`./lab evals dials SPEC`, a setting per composition). `./lab evals
  sessions SPEC` asks follow-up questions about one result in one session.
- **Tasks.** Synthetic payloads with planted answers (pod lists as JSON, request logs, accessibility
  snapshots, Figma XML), real files with computed answers (Python and Rust sources, an ISO 3166
  XML file, the PyPI release JSON), a real log with labelled anomalies (HDFS), and MCP-Atlas tasks
  replayed from their recorded tool calls. EVALS.md has the task kinds and the statistics.

## Stages

| # | Stage | Needs a model | Status |
|---|---|---|---|
| E1 | Every format folds as an envelope: logs by line templates, trees (outlines, XML, pages, text, code) by runs of like items | no | done: no claim fails on any task (FINDINGS 1) |
| M1 | Log each fold with its session, so every layer-2 row says whether the envelope acted on the task's large output, and the report splits on it | no | done: rows carry `large_seen` and `large_folded`; a Haiku smoke matched inline, spilled and replayed outputs by digest (`results/dials-haiku-m1-smoke.md`) |
| M2 | Layer-1 baseline: both recipes on every task | no | done (FINDINGS 1) |
| M3 | Layer-1 sweeps over compositions: `sweeps/envelopes.toml`, `logs.toml`, `trees.toml` | no | done: anomalies decide the most; samples past the query's matches add nothing in layer 1 (FINDINGS 2) |
| M4 | Layer 2 on Haiku: native against the two recipes on MCP-Atlas (about $3) and on the synthetic tasks of every format at M and L | yes | done: synthetic, both recipes pass (FINDINGS 4); MCP-Atlas where it acted, context passes, accuracy undecided (FINDINGS 3) |
| M5 | Layer 2 on compositions layer 1 cannot tell apart: a typical sample or none, no get more | yes | done as the patterns below: a typical sample (full) and no samples (lean) change nothing a model does but lean's extra reads (FINDINGS 6) |
| P1 | Three envelope patterns as recipes in every format: full (every part filled), lean (a terse shape, the anomalies, a command; no samples), index (a command for every group, a new get-more producer) | no | done: no claim fails (FINDINGS 5) |
| P2 | Haiku: native, schema, full, lean and index on the synthetic tasks at M and L (`dials/haiku-patterns.toml`); predictions set in the spec | yes, about $3.60 | done: all keep the answers; no pattern changes how often the model reads the raw; schema stays (FINDINGS 6) |
| M6 | Sonnet on the compositions Haiku leaves standing | yes | in part: the schema recipe on the synthetic tasks (FINDINGS 7): context passes, accuracy undecided at one loss, the $0.00 invoice |
| M7 | Sessions: follow-up questions on one result, native against the two recipes (`sessions/haiku.toml`, about $2) | yes | |

Later: a run nested in a run's items as an envelope of its own (a country's subdivisions inside the
list of countries); a numeric outlier in a hole, which no rule finds yet (the $0.00 invoice).

## Decisions

- Python 3.15 through `uv run --no-project`, standard library only for the envelope (ast-grep for
  code's tree); own `pytest.ini` and `ruff.toml`, so the bh-02 root config never applies here.
- Producers are pure functions and an envelope is a value. Layer 1's checks share no code with the
  producers.
- Every count, range and row an envelope states is computed over all rows or lines, never sampled.
  A model will trust "Failed 3".
- Budgets count tokens as `ceil(chars / 4)`; layer 2 reports the API's own counts.
- Query terms come from the tool call's own arguments, ignoring terms most rows share (over lines,
  more than 5% of them).

## Known caveat

The MCP-Atlas replay answers a call with the closest recorded call of the same tool, so a model
that asks differently from the recorded run can get a smaller output and never see the large one.
M1 measures how often, and the report keeps those sessions apart.

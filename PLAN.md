# Plan

Goal: find out which tool-output compressors keep what the model needs while cutting tokens, with
numbers, before anything is built into a harness. See README.md for the design under test and the
kill criteria.

## Stages

Each stage leaves a script and a file in `results/`. A later stage never edits an earlier result.

| # | Stage | Needs a model | Status |
|---|---|---|---|
| 1 | Extraction: Claude Code transcripts -> `corpus/results.jsonl` (one row per tool result, with the next assistant step as replay ground truth) | no | done; corpus 1 is six sub-agents' transcripts |
| 2 | Corpus stats: size distribution, per-tool totals, format mix of the large ones | no | done |
| 3 | Compressors: `lines` (dedupe + head/tail + error windows), `json` (array folding + anomaly promotion), `html` (strip to text, then `lines`), `text` (head/tail by chars), router, recovery | no | done (html not yet in the needle grid) |
| 4 | Deterministic ratio: run every compressor over the corpus; tokens in/out per branch | no | done; `results/stats-agents-1.md` |
| 5 | Needle survival: synthetic JSON and logs with one planted anomaly; does it survive compression? This is the upper bound on what a model can find | no | done; see results/FINDINGS.md |
| 6 | Replay: re-run the step after each large result with the compressed result; judge equivalence; count recovery calls | yes | blocked: API key and a real corpus |
| 7 | Needle with a model: same synthetic set, ask the model to find the anomaly, raw vs compressed | yes | blocked: API key |
| 8 | Verdict per branch against the kill criteria | - | after 6 and 7 |

## Decisions taken while working alone

- Python 3.15 via `uv run --no-project --python 3.15`, standard library only for the code; pytest for tests. Own
  `pytest.ini` and `ruff.toml` so the bh-02 root config (workspace globs, member paths) never applies here.
- Compressors are pure functions `(tool_name, args, raw) -> Compressed`. The raw-output cache is the
  caller's dict keyed by call id; `recover(raw, query)` is pure too.
- Token counts are `ceil(chars / 4)`. Good enough for ratios between branches; the model stages
  use the API's own counts.
- Anomaly promotion in JSON is statistical (a low-cardinality field where one value dominates, and
  an item holds a rare value) plus explicit error keys. No substring match on the whole item, which
  flags every `"deleted": false`.
- Promoted JSON items stay in place in the array, between fold markers, so the array stays an
  array and the item looks like what it is.
- Query terms come from the tool-call arguments only, and are a knob the needle stage measures with
  and without.

## Known caveat for the corpus

Claude Code already caps what reaches the model (Bash output is cut, Read pages long files), so a
Claude Code corpus understates how large raw tool outputs get. Stats report that the sizes are
post-harness.

## Claude Code stages (from 2026-11-03)

| # | Stage | Status |
|---|---|---|
| C1 | Map what Claude Code already does with large outputs, from its docs | done |
| C2 | Probe the hook points (PostToolUse output shapes, spills, Read numbering, PreToolUse deny) | done |
| C3 | PostToolUse fold hook for MCP results, inline and spilled | done |
| C4 | Fixture MCP server and headless A/B harness | done |
| C5 | A/B 1: JSON and logs, Haiku | done: fold wins on spilled, loses inline |
| C6 | Tree folding: code (ast-grep), XML, outlines | done |
| C7 | A/B 2: accessibility snapshots and Figma XML, Haiku | done: same split |
| C8 | Read gate (PreToolUse) with ast-grep outlines | removed (review 1, R2): it showed file content before Claude Code's permission check, and models page on their own |
| C9 | A/B with Sonnet, spilled-only mode, large cases | done (A/B 3); superseded by P2 and P3 (EVALS.md) |
| C10 | The outline as a tool Claude calls, against its own grep outlines | done: P2 and P3 offered it as `lab-fold` and as an MCP tool; used once in 76 runs (FINDINGS 36, 42) |
| C11 | Fold Bash output from the hook (after the command runs) | done: FINDINGS 46-48; the second-look regress is open |

## Schema views for data (from 2026-11-03)

What the evals showed about the current fold: after a fold, models query the raw (grep, `jq` or a
script in 89% of first moves, FINDINGS 46-48 and the transcripts), they use the commands the output
names, and they almost never open a marker's range. The fold shows samples (head, tail, stand-outs)
and leaves the model to infer the data's shape from them; quiet anomalies, which no rule names, are
lost at M and L in every format (R7), and counts past the stand-out cap survive only in JSON,
because its summary states them.

So for data, show its schema instead: what fields there are, what values they take and how many of
each, where the rows that break the pattern are, and the query that fetches instances. A schema's
size depends on the structure, not on the number of rows.

    .items: array[500], every item has the same 10 keys
      name      str, unique, like web-<hex>
      phase     Running 488, CrashLoopBackOff 12
      restarts  int 0..97, median 1; 97 at .items[312] (next highest 3)
    exceptions: .items[312] (web-a9da82d697) restarts=97; ...
    query:      jq '.items[] | select(.phase != "Running") | .name' FILE

Rules:

- **Exact.** Every count, range and exception is computed over all rows, never sampled, and layer
  1 checks each claim against the data. A model will trust "Failed 3".
- **Exceptions with addresses.** A row breaks the pattern when it holds a value few rows hold, a
  number far outside the rest, or a key most rows lack (or lacks one most have). Each is listed with
  its path and its identifying field (a unique name or id), so it can be named and fetched.
- **Native addresses and a query.** Paths are `jq` paths (`yq` for YAML, XPath or ids for XML), and
  the view names one ready query, since models use the commands the output names.
- **Mixed trees.** Show unique nodes as an outline, and replace each run of same-shaped siblings by
  its schema and exceptions (Figma and accessibility trees are document-like at the top and data
  where siblings repeat).
- **Documents are not data.** Code and Markdown keep the outline (their signatures and headings are
  their schema), with open, find and read verbs later. Logs (line templates) are paused.

| # | Stage | Needs a model | Status |
|---|---|---|---|
| S1 | JSON schema view (`compressors/schema.py`): structure, field statistics, exceptions, a query; `--view schema`, the sample fold staying for comparison | no | done |
| S2 | Layer 1 on both views: the claims checked against the data; sufficiency on spot (rule and quiet), count (past the cap), enumerate, absent, and lookup (expected to need the raw) | no | done: schema 41/47, sample 38/47, half the size, 0 false claims (FINDINGS 49-50) |
| S3 | Repeated siblings in XML and accessibility trees as schemas | no | |
| S4 | YAML through the same schema (multi-document manifests) | no | |
| S5 | Layer 2 on Haiku: the schema view against the sample fold and native, M and L | yes, about $2 | in part: as a dial at M, L to XXL and in sessions, never an answer lost, 8 to 39 pairs a cell (FINDINGS 54-66); a deciding run is open |
| S6 | The second-look regress in forced Bash folding (FINDINGS 48), before any Bash run of S5 | yes, about $0.70 | |

## The envelope (from 2026-11-04)

Every view of a large output answers four questions, and the envelope is that structure: **shape**
(what the data is, in exact numbers), **anomalies** (what breaks the shape, each with its address),
**samples** (what items look like, verbatim) and **nav** (how to fetch the rest: addresses and a
ready command). A recipe names a producer for each part; producers run in that order, each given
the parts before it, and read one another through what each part claims. Each part offers levels,
fullest first, with the claims each makes; `compose` starts every part at its tersest and raises
them in priority order within the budget. Layer 1 checks every claim against the data and that
the text says it. Code: `compressors/envelope.py` (the core), `compressors/envelope_json.py` (JSON's
producers), `evals/envelope_check.py`; `--view envelope` with the `json_envelope` knobs.

| # | Stage | Needs a model | Status |
|---|---|---|---|
| E1 | The protocols and `compose` | no | done |
| E2 | JSON's two views split into producers; the schema and sample recipes reproduce them in layer 1 | no | done: schema recipe on exactly the schema view's 41 of 47, sample recipe on 37 of the fold's 38 (FINDINGS 67) |
| E3 | A layer-1 sweep over mixed recipes | no | done: `sweep-envelopes.md` (FINDINGS 68) |
| E4 | Trees (S3) as producers on the same protocol, with nested envelopes for repeated siblings | no | |
| E5 | Logs as templates: shape the templates and counts, anomalies the rare ones | no | |
| E6 | Layer 2 on recipes that layer 1 cannot tell apart (a typical sample or none) | yes | |

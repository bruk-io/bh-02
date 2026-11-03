# Plan

Goal: find out which tool-output compressors keep what the model needs while cutting tokens, with
numbers, before anything is built into a harness. See README.md for the design under test and the
kill criteria.

## Stages

Each stage leaves a script and a file in `results/`. A later stage never edits an earlier result.

| # | Stage | Needs a model | Status |
|---|---|---|---|
| 1 | Extraction: Claude Code transcripts -> `corpus/results.jsonl` (one row per tool result, with the next assistant step as replay ground truth) | no || done; run on this session's own transcript only |
| 2 | Corpus stats: size distribution, per-tool totals, format mix of the large ones | no || done |
| 3 | Compressors: `lines` (dedupe + head/tail + error windows), `json` (array folding + anomaly promotion), `html` (strip to text, then `lines`), `text` (head/tail by chars), router, recovery | no || done (html not yet in the needle grid) |
| 4 | Deterministic ratio: run every compressor over the corpus; tokens in/out per branch | no || done; nothing to measure until a real corpus |
| 5 | Needle survival: synthetic JSON and logs with one planted anomaly; does it survive compression? This is the upper bound on what a model can find | no || done; see results/FINDINGS.md |
| 6 | Replay: re-run the step after each large result with the compressed result; judge equivalence; count recovery calls | yes | blocked: API key and a real corpus |
| 7 | Needle with a model: same synthetic set, ask the model to find the anomaly, raw vs compressed | yes | blocked: API key |
| 8 | Verdict per branch against the kill criteria | - || after 6 and 7 |

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

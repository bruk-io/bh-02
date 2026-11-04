# Findings

What the lab has measured about the envelope and its compositions, oldest first. Each entry names
the run it comes from (`results/<name>.md` and `.jsonl`); a run's files are never edited after it
ends, and a later entry that changes an earlier one says so.

Everything measured before 2026-11-04 was dropped. It tested the folds the envelope replaced, or it
tested the envelope on MCP-Atlas through a replay that never served the large output in about a
third of the folded sessions. Git keeps all of it, up to commit `ea8c2e5`.

The next runs are in PLAN.md.

## 1. Every format folds as an envelope, and no claim it makes fails (layer 1, both recipes)

Runs: `results/l1-1-sample.md` and `results/l1-1-schema.md`, budget 2,000 tokens, sizes S to L, 284
folds of 251 tasks each (a task with a query is folded with it and without it).

- **Claims.** No fold under either recipe makes a claim the data does not bear out, or one its text
  does not say. Every count, value, line and row is recomputed from the source apart from the
  producers' code, and every jq and grep command is run. Layer 1 found one bug on the way, on a
  real MCP-Atlas output: a grep pattern that starts with `-` was read by grep as an option, so it
  now goes after `-e`.
- **Sufficiency**, over the folds that folded (the rest fit the budget and pass through whole):

  | Format | sample | schema |
  |---|---|---|
  | JSON pods | 23/30 | 25/30 |
  | logs | 26/30 | 26/30 |
  | accessibility snapshots | 24/30 | 24/30 |
  | Figma XML | 26/30 | 26/30 |
  | Python | 12/15 | 12/15 |
  | Rust | 6/6 | 6/6 |
  | ISO 3166 XML | 3/6 | 3/6 |
  | PyPI JSON | 3/5 | 4/5 |
  | HDFS log | 12/24 | 12/24 |
  | MCP-Atlas | 21/59 | 17/59 |

  On the synthetic tasks at M and L, the schema recipe makes every spot, count, enumerate and
  absent task sufficient, quiet anomalies included, except two: the $0.00 invoice in an
  accessibility snapshot, since no rule reads a numeric outlier in a hole, and listing 12 failing
  pods of 100 in JSON. The sample recipe also misses JSON's quiet anomaly (one pod with 97
  restarts), which the schema recipe's exceptions find and its stand-out rules do not. A lookup
  needs its query, as expected, since the answer is one row among hundreds; with the query every
  synthetic lookup is sufficient.
- **Where it falls short.** HDFS's anomalies are what its operators labelled, and half of them
  leave no rare line; at M a healthy log is flagged for one rare thread id. On MCP-Atlas the
  answers sit in free text, which the sample recipe's head and tail reach more often than the
  schema recipe's query matches. The ISO 3166 file without its query shows the list of countries
  counted but not the subdivisions inside each, since a run inside a run's items is not yet an
  envelope of its own.
- **Size.** Under the schema recipe the median envelope of a synthetic M or L payload is 187 to 228
  tokens, 0 to 4% of the input; HDFS 537 to 629; MCP-Atlas 279 to 350; code 1.3k to 1.9k, since
  an outline of definitions grows with the file. The sample recipe's head and tail make them
  larger: 281 to 454 tokens for the synthetic payloads, 596 to 781 for MCP-Atlas.

This bounds what a model can answer from the envelope alone. Whether a model answers as well as
native Claude Code, at less context, is layer 2's question (PLAN.md M4).

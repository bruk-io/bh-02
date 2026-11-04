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

## 2. Which parts matter: each format's compositions swept in layer 1

Runs: `results/sweep-envelopes.md` (JSON and the PyPI file, 32 compositions, 47 folds each),
`results/sweep-logs.md` (the synthetic logs and HDFS, 16 compositions, 66 folds each) and
`results/sweep-trees.md` (accessibility snapshots, Figma XML, the ISO 3166 file, Python and Rust,
24 compositions, 112 folds each). Each grid crosses the kinds of anomaly with the kinds of sample
at budgets of 500 and 2,000 tokens, the rest of the schema recipe held. No claim fails at any of
the 72 compositions.

- **The anomalies part decides the most, in every format.** JSON's `exceptions` find all 12
  planted anomalies and all 3 quiet ones at every point; its `standouts` find 9 or 10 and at most
  1. In logs, `rare` finds every quiet anomaly (3 of 3, against at most 1 for `errors`) and more
  spots (16 of 20 against 13 or 14 at 2,000 tokens), but flags one healthy log, HDFS's rare thread
  id (absent 4 of 5 against 5 of 5). In trees, `rare` finds 22 of 24 spots and 25 of 27 counts at
  2,000 tokens; `errors` adds nothing over `none` there, since the synthetic trees name no errors,
  and both find 8 spots and 8 or 9 counts. No tree composition flags a healthy tree.
- **Matching the query adds the lookups, and nothing else does.** Matches add 5 to 13 lookups
  depending on the format and budget (JSON 4 to 9 of 14 at 2,000 tokens, logs 4 to 10 of 20, trees
  8 to 17 of 26). A typical sample, or the head and tail, answers no task that matches did not,
  except where the anomalies part missed rows: with JSON's `standouts` and logs' `errors`, the head
  and tail happen to show 1 to 3 answers the rule did not. They cost tokens: at 2,000 tokens the median envelope grows from 245 to 310 or 438 in
  JSON, from 444 to 536 or 594 in logs, and from 310 to 398 or 510 in trees. Whether a model
  uses a sample to write its query right is what layer 1 cannot see (PLAN.md M5).
- **The shape: fields or a summary.** JSON's `fields` list a keyed collection's keys and answer
  one more enumerate task (6 of 7 against 5) at 2,000 tokens; `summary` is about 65 tokens
  smaller, and at 500 tokens summary, exceptions and matches is the best JSON composition (36 of
  47 at 168 tokens).
- **The budget.** At 500 tokens logs answer 7 of 14 count tasks against 13 at 2,000, since the
  anomalies' lines are cut; code outlines need room too (trees locate 2 of 6 and edit 1 of 5 at
  500, against 6 of 6 and 4 of 5).

For layer 2 this leaves two questions layer 1 cannot answer: whether the schema recipe's
composition (exceptions or rare, matches, a ready command) keeps answers against native at less
context (M4), and whether samples the query did not ask for earn their tokens (M5).

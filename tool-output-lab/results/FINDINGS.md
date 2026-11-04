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

## 3. MCP-Atlas on Haiku: where the envelope acted, answers held within noise and the final context fell by 3.8k

Run: `results/dials-haiku-atlas.md`, 354 sessions, $3.10, none failed: the 59 MCP-Atlas tasks (42
at M, 17 at L), twice each, native against the hook folding every result (mode `all`) as the
sample recipe and as the schema recipe. Native answers 53% right.

- **The envelope acted in half the folded sessions.** The hook folded the task's large output in
  63 of 118 sample sessions and 59 of 118 schema ones, and in every session that received it. The
  rest never received it, since the replay answers a call with the closest recorded call and the
  model asked otherwise; those sessions folded nothing, so they ran as native does.
- **The sessions where it did not act are noise, and they made the pooled result look worse.**
  Over all pairs the sample recipe lost answers at M (-10% [-17%, -2%], 2 pairs won and 10 lost).
  Seven of its eight disagreements in sessions that folded nothing went against it, although
  those sessions ran under native's conditions and disagreed with native 15% of the time, less
  than native's 19% with itself.
- **Where it acted**, paired against native:

  | Recipe | pairs | accuracy | won/lost | final context | cost | time |
  |---|---|---|---|---|---|---|
  | sample | 63 | -2% [-12%, +9%] | 5/6 | -3,928 [-5,628, -2,229] | -5% | +1.5 s [-1.6, +3.9] |
  | schema | 59 | +0% [-12%, +12%] | 7/7 | -3,788 [-5,527, -2,097] | -3% | +4.8 s [+1.2, +10.6] |

  The two recipes disagree with native 17% and 24% of the time, about as often as native
  disagrees with itself (19%). At M the final context falls by 4.5k and 3.7k (46 and 44 pairs);
  at L by 0.8k and 1.1k (17 and 15 pairs), since over the spill threshold native's context holds
  only Claude Code's preview of the output.
- **Against the kill criteria**, the final context shrinks under both recipes, its interval below
  zero, which passes the input criterion. Accuracy is undecided: about 60 pairs bound the change
  to about 12 points either way, not the 3 the criterion asks.
- **More requests, smaller context.** The folded sessions carry more summed input (+25k and +37k
  on average: the requests that fetch from the saved output, each reading the prefix from the
  cache) and still cost 3 to 5% less, since cache reads are cheap and the context they re-read is
  smaller. The schema recipe's sessions take longer (+4.8 s), the sample recipe's about as long.

## 4. The synthetic tasks on Haiku: both recipes keep every answer, and cut the final context by 7k and the cost by 23%

Run: `results/dials-haiku-synthetic.md`, 312 sessions, $2.04, none failed: the synthetic MCP tasks
of every format (JSON pods, request logs, accessibility snapshots, Figma XML; 13 of each at M and
13 at L), once each, native against the hook folding every result (mode `all`) as the sample and
the schema recipe. The envelope acted in every folded session.

- **Answers.** Native answers 103 of 104; each recipe 104 of 104, one pair won and none lost.
  Over the 104 pairs the change is +1% [-2.7%, +5.2%]; per band, 52 pairs bound it only to 7
  points either way. These tasks are easy for Haiku, so they can show a loss but hardly a gain,
  and they showed no loss.
- **Context, cost and time**, paired against native (means, with 95% intervals for the context):

  | Band | Recipe | final context | cost | time |
  |---|---|---|---|---|
  | M | sample | -9,522 [-10,552, -8,298] | -18% | +2.1 s |
  | M | schema | -8,488 [-9,946, -6,717] | -17% | +1.5 s |
  | L | sample | -5,258 [-8,383, -2,538] | -27% | -5.0 s |
  | L | schema | -4,888 [-7,693, -2,535] | -28% | -4.8 s |
  | both | sample | -7,390 [-9,043, -5,797] | -23% | -1.4 s |
  | both | schema | -6,688 [-8,375, -5,111] | -23% | -1.7 s |

- **Against the kill criteria**, pooled over the 104 pairs, both recipes pass both: the accuracy
  change's lower bound is above -3 points and the final context's interval is below zero. Per
  band the accuracy criterion is undecided.
- **How the sessions read.** At M, where native holds the raw result, the folded sessions still
  read the saved raw in 87% (sample) and 73% (schema) of sessions, about one call more than native,
  and take 1.5 to 2 s longer. At L, where native always reads the file Claude Code saved, the
  folded sessions read it less often (81% and 65%), make two calls fewer and finish 5 s sooner;
  the context falls less, since native holds only a preview, but the cost falls most.
- **The exception: Figma XML at M.** The folded sessions read the saved XML whole (25 of 26), so
  their final context stayed about native's (the schema recipe's median +1.1k). At about 7k
  tokens the raw is small enough to read in one go.

With FINDINGS 3, M4 is done: on the synthetic tasks both recipes pass; on MCP-Atlas, where they
acted, the context criterion passes and accuracy is undecided at about 60 pairs. Sonnet (M6) and
the sample question (M5) are next; neither recipe is cut.

## 5. Three envelope patterns in layer 1: full, lean and index

Runs: `results/l1-2-full.md`, `l1-2-lean.md`, `l1-2-index.md`, beside FINDINGS 1's schema run;
budget 2,000 tokens, sizes S to L, all 251 tasks. Each pattern is a recipe in every format:

| Pattern | JSON | Logs | Trees |
|---|---|---|---|
| full: every part filled | fields, exceptions, typical, jq | templates, rare, typical, grep | outline, rare, typical, grep |
| lean: the least that keeps the anomalies | summary, exceptions, none, jq | count, rare, none, grep | outline, rare, none, grep |
| index: a command for every group | fields, exceptions, matches, index | templates, rare, matches, index | outline, rare, matches, index |

`index` is a new get-more producer. For JSON it gives each collection's row commands, the query
for the rows that break a dominant value, a `jq select` for every value but the commonest of each
few-valued field (a new claim, `Selects`: the command prints exactly the rows holding that value,
this many of them), and a command per listed row. For logs it gives a grep for every template
said more than once, the anomalies' first, each printing exactly its lines. For trees it gives
each run's line range with its items counted, each anomalous item's lines, and a grep per
anomaly's template.

- **Claims.** No fold under any pattern makes a claim the data does not bear out, with every jq
  and grep command run.
- **Sufficiency and size** on the synthetic tasks at M and L (104 folds without the query; 16
  lookups with it) and every folded task:

  | Pattern | synthetic, no query | lookups with the query | every folded task | median tokens (JSON, logs, snapshots, Figma) |
  |---|---|---|---|---|
  | schema | 85/104 | 16/16 | 155/235 | 225, 187, 212, 197 |
  | full | 85/104 | 16/16 | 156/235 | 292, 256, 258, 285 |
  | lean | 85/104 | 0/16 | 125/235 | 168, 112, 212, 197 |
  | index | 85/104 | 16/16 | 155/235 | 378, 255, 251, 330 |

- Full and index answer in layer 1 what schema does, at 45 to 150 tokens more. Lean is the
  smallest, but with the samples go the rows and lines the query matches, so it answers none of
  the lookups a tool call's query would name, and its model must fetch them. That is the bet the
  pattern makes, and its prediction stands as set before the run: lean keeps schema's answers at
  a smaller final context.

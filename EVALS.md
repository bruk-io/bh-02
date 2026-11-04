# Evals

How envelope compositions are tested, and how each test is scored. The rule throughout: the right
answer is computed by a program from the payload (the generator that planted it, `jq` over a real
file, or the facts in a recorded answer), never written by hand.

## The four questions

1. **Fidelity:** does the envelope keep what the task needs?
2. **Efficiency:** does it save calls, tokens, time and context in practice?
3. **Harm:** does it mislead? Confident wrong answers, invented anomalies, counts taken from the
   visible part only.
4. **Recovery:** when the envelope does not show what is needed, does Claude fetch it, and cheaply?

## Two layers

| Layer | What runs | Cost | When |
|---|---|---|---|
| L1, deterministic | the envelope alone, no model | free | every change (`./lab check` runs a fast subset) |
| L2, in the loop | headless Claude Code, native against each composition | money | per question below, paired |

L1 answers question 1 as an upper bound: if the answer cannot be read off the envelope, a model can
only find it by fetching more. L2 answers all four.

### L1 checks, for every payload

- **Claims hold.** Every claim a part makes is recomputed from the input (`evals/envelope_check.py`).
  For JSON (a count, the values a field holds and how many of each, a row's note, that a list of
  rows is complete, a sample's text, what a command prints) by `evals/schema_check.py`'s jq-path
  walker, each command run with `jq` itself, and the shape's field lines read back for what they
  say beyond the claims: ranges, medians, uniqueness. For an envelope of lines (what lines read,
  how many lines have a template or hold a value in a hole, what a grep prints) against the source
  its numbers refer to, with the checker's own line split, template rule and reading of the clip
  marker, each grep run with `grep` itself.
- **Claims are said.** Each claim appears on one line of its level's text.
- **Determinism and size.** The same input folds to the same text, and the envelope is never
  larger than the input.
- **Sufficiency, per task.** The task's own scorer (below) is run on the envelope's text instead of
  a model's answer.

## Task kinds and their scorers

| Kind | Example | Scorer | What it catches |
|---|---|---|---|
| Spot | "Does any pod look wrong or unusual? Name it." (and quiet anomalies no stand-out rule names) | the planted item on the ANSWER line | lost anomalies |
| Absent (control) | the same question, no anomaly planted | no candidate named; says none | invented anomalies |
| Look up | "What is the IP address of pod web-0417a1b2c3?" | exact value | recovery |
| Enumerate | "List every pod that is not Running." | recall and precision against the computed set | partial views read as complete |
| Count | "How many pods are not Running?" | exact number | counting only the visible rows |
| Locate | "On which line is close defined in Server?" | the line shown with its number | line numbers that lie |
| Edit | "Add a timeout parameter to create_server, defaulting to None." | where to start: the definition shown with its number (layer 1); the edit checked with `ast` (layer 2) | edits made blind into folded code |
| Claims | an MCP-Atlas task's own prompt | every claim of the recorded answer holds in the answer: its numbers and quoted titles, and two thirds of its names | real questions over real outputs |

Each run also records whether the model answered "cannot tell" or answered wrongly. Wrong and
confident is the harm, so it is reported separately from wrong and hedged.

## Sources

| Format | Source | Truth |
|---|---|---|
| `json` | synthetic pod lists (`evals/synthetic.py`) at every size band | planted by the generator |
| `log` | synthetic request logs: a failed payment is a rule-kind anomaly, an exhausted pool a quiet one | planted |
| `a11y` | synthetic accessibility snapshots of an invoices page: a disabled Pay button, a $0.00 invoice | planted |
| `figma` | synthetic Figma node XML of a product grid: a hidden card, a half-width card | planted |
| `hdfs` | Loghub's HDFS_v1, whole block lifecycles, anomalies labelled by the people who ran it (`./lab fetch hdfs`) | the labels |
| `python`, `rust` | stdlib and cargo registry sources | computed with `ast` or ast-grep patterns kept apart from the fold |
| `xml` | `/usr/share/xml/iso-codes/iso_3166-2.xml` | computed from the file |
| `pypi` | the PyPI release JSON for click, saved once | computed with `jq` paths |
| `atlas` | MCP-Atlas (ScaleAI, CC-BY-4.0): the tasks with one large tool output that a replay can answer and a program can score (`evals/atlas.py`, `./lab fetch mcp-atlas`) | the facts in each recorded answer claim; a fold is sufficient when it keeps the facts the large output holds |

An MCP-Atlas task reaches Claude through `claude_code/replay_mcp.py`, an MCP server offering the
task's recorded tools; each call is answered with the closest recorded call of the same tool.

## Conditions, sizes, models

- **Conditions:** native, and the hook folding as each composition. A dials spec's setting is one
  composition (`view`, `set`) in one hook mode (`inline`, the default, `spilled` or `all`), paired
  against native by task and repetition.
- **Sizes:**
  - S: under the budget;
  - M: between the budget and Claude Code's spill threshold (MCP 50k characters, Bash 30k);
  - L: over the threshold;
  - XL and XXL: 4 and 16 times L, synthetic only, built when asked for (`--bands XL XXL`, a
    sweep's or spec's `bands`).
  Every L2 cell reports the band, since under the threshold a native session holds the raw result
  and over it Claude Code saves the result and shows a preview. Sizes are estimated tokens
  (characters / 4); the API counts the synthetic payloads higher.
- **Models:** Haiku first (sensitive and cheap), then Sonnet on what Haiku leaves standing.

## Metrics per run

- **Outcome:** correct by the task's scorer; confidently wrong.
- **Tokens:** the final context's size (the input of the last request: what the input criterion
  judges); input tokens summed over requests, by cache class; output tokens.
- **Effort:** cost, tool calls, time.
- **Recovery:** reads of the saved raw file, and how much of it was read.

## Sessions

One-question tasks measure what an envelope costs and saves once. A real session uses a result
again, and every later request re-reads whatever the result left in the context. `./lab evals
sessions` asks six questions about one tool result in one Claude Code process (`--input-format
stream-json`, each question sent once the last has its result): the count task's own prompt, which
names the tool, then every planted item, then four items looked up across the payload
(`evals.tasks.conversations`). Every turn is scored and costed on its own (a result event's
`total_cost_usd` and `modelUsage` add up over the session; `usage` and `duration_ms` are the
turn's), and the report follows the context turn by turn: whether the envelope's saving survives the
follow-ups, and what the fetches cost.

## The prompt cache

Claude Code caches each request's prefix (system prompt, tools, the conversation so far) and writes
it with a one-hour lifetime (`modelUsage.cacheCreationEphemeral1hInputTokens`), priced at 2x the
input price; a cache read is 0.1x, output 5x. Under that structure a run's cost implies one input
price, and the report checks that runs agree on it before pricing anything with it.

The hook rewrites a tool result before it enters the conversation and never touches an earlier
message, so it cannot invalidate what is cached. What it changes is what comes after:

- An envelope is written once and re-read by every later request. A context N tokens smaller saves
  N cache-read tokens on each request after it: the report's "each later request" column.
- Every extra request (a fetch from the saved raw) re-reads the whole prefix: the "requests" and
  "cache reads" columns.
- The same input must fold to the same text, or repeated calls cannot share cache entries; layer 1
  checks this.
- Parallel runs with the same prefix read each other's cached system prompt: "warm starts" counts
  runs whose first request read 10,000 tokens or more from the cache. Interleaving conditions in
  the job list keeps this even across conditions.

## Statistics

- **Paired design:** the same task and seed in every condition, so differences are per task.
- **Accuracy:** with a Wilson 95% interval; paired accuracy with Newcombe's interval and McNemar's
  exact p, since a bootstrap is too sure with few discordant pairs.
- **Tokens, cost and time:** as the paired median difference with a bootstrap interval.
- **Noise floor:** native's first repetition against its second, so a composition's disagreement
  with native is read against native's disagreement with itself.
- **Kill criteria:** set in README.md before measuring, unchanged.

## Running

```
./lab evals l1 --only json pypi atlas [--view schema] [--set KNOB=VALUE] [--name l1-x]   # layer 1, free
./lab evals l1 --bands XL XXL --only json log a11y figma            # the larger bands
./lab evals sweep sweeps/envelopes.toml                             # layer 1 over a grid of compositions (logs.toml, trees.toml)
./lab evals dials dials/haiku-atlas.toml --dry-run                  # layer 2: the plan and its cost
./lab evals dials dials/haiku-atlas.toml                            # run it (headless Claude Code)
./lab evals sessions sessions/haiku.toml --dry-run                  # follow-up questions in one session
./lab evals l2 --merge l2-x l2-y --name l2-xy                       # report runs together, rescored
```

Every entry point takes the same knobs (`compressors/config.py`): `--config FILE.toml` and `--set
NAME=VALUE` for `./lab fold` and `./lab evals l1`, `set` in a spec; the hook reads
`TOOL_OUTPUT_LAB_CONFIG`, `TOOL_OUTPUT_LAB_SET` and `TOOL_OUTPUT_LAB_VIEW`. Layer 1 and layer 2
record the knobs and view with every row, and layer 2 will not merge runs folded differently.

The code: `evals/truth.py` (answer kinds and scorers), `evals/synthetic.py` (planted payloads),
`evals/real.py` and `evals/atlas.py` (real data and its computed answers), `evals/tasks.py` (the
registry), `evals/l1.py` (checks, sufficiency, the report), `evals/l2.py` (headless runs and their
report), `evals/dials.py`, `evals/sessions.py` and `evals/sweep.py` (specs).

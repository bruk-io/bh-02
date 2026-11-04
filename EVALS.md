# Evals

How we test `fold` across tasks and file types, and how each test is scored. The rule throughout:
the right answer is computed by a program from the payload (the generator that planted it, or
`ast`, `jq`, XPath or a regex over a real file), never written by hand.

## The four questions

1. **Fidelity:** does the fold keep what the task needs?
2. **Efficiency:** does it save calls, tokens, time and context in practice?
3. **Harm:** does it mislead? Confident wrong answers, invented anomalies, counts taken from the
   visible part only.
4. **Recovery:** when the fold hides what is needed, does Claude fetch it, and cheaply?

## Two layers

| Layer | What runs | Cost | When |
|---|---|---|---|
| L1, deterministic | the fold alone, no model | free | every change (`./lab check` runs a fast subset) |
| L2, in the loop | headless Claude Code, native against fold | money | per question below, paired |

L1 answers question 1 as an upper bound: if the answer cannot be read off the fold, a model can only
find it by recovering. L2 answers all four.

### L1 checks, for every payload

- **Invariants:** every line of the input is shown or inside exactly one marker; each marker's range,
  read back with `sed -n` (or `jq` for JSON paths), is exactly what it hid; the output fits the
  budget (or is the outline floor) and is never larger than the input; folding is deterministic.
- **Sufficiency, per task:** can the answer be read off the fold text alone? The task's own scorer
  (below) is run on the fold text instead of a model's answer.

## Task kinds and their scorers

| Kind | Example | Scorer | What it catches |
|---|---|---|---|
| Spot | "Does any pod look wrong or unusual? Name it." (and quiet anomalies the fold has no rule for) | the planted item on the ANSWER line | lost anomalies |
| Absent (control) | the same question, no anomaly planted | no candidate named; says none | invented anomalies from promotion noise |
| Look up | "What is the ref of the Pay button for INV-0417?" | exact value | recovery |
| Enumerate | "List every async method of BaseEventLoop." | recall and precision against the computed set (precision against the set of all candidate names) | partial views read as complete |
| Count | "How many pods are not Running?" | exact number | counting only the visible items |
| Locate | "On which line is close defined in Server?" | exact line number, or JSON path | line numbers that lie |
| Compare | "How do pods A and B differ?" | the set of differing fields | context lost between two folded items |
| Edit | "Add a timeout parameter to create_server, defaulting to None." | apply the change, then check it with `ast`, `jq` or the file's tests | edits made blind into folded code |
| Explain | "Give an overview of this module." | a rubric of facts computed from the source (classes, their methods, what calls what), scored by a separate judge model for coverage and for claims the source does not support; the judge is checked against hand labels on 10 answers first | the open-ended reading the other kinds cannot score |

Each run also records whether the model answered "cannot tell" or answered wrongly. Wrong and
confident is the harm, so it is reported separately from wrong and hedged.

## Formats and sources

| Format | Synthetic (generator plants the answer) | Real (answer computed from the file) |
|---|---|---|
| JSON lists | pods (`evals/synthetic.py`) | PyPI release JSON (3 MB, saved once); `uv pip list --format json` |
| JSON Lines | logs as records | |
| Logs | app logs with planted lines | `python -m test -v` output for a stdlib module; a real CI log |
| Test output | | pytest and unittest runs with a planted failing test |
| XML | Figma node metadata, Android UI dumps | `/usr/share/xml/iso-codes/iso_3166-2.xml` (lookups and counts by country) |
| HTML | | documentation pages saved once |
| Accessibility trees | Playwright-style snapshots | snapshots taken with the installed Chromium from the saved HTML pages |
| YAML | Kubernetes manifests | workflow files |
| Code | | Python (stdlib, truth by `ast`), Rust (cargo registry), JavaScript (npm `dist`), truth by ast-grep patterns kept separate from the fold's own code path |
| Markdown | | large changelogs; needs a heading-tree adapter (not built) |
| CSV, diffs | | not built: column statistics for CSV, per-file hunks for diffs |

## How the payload reaches Claude

| Channel | Fold through | Status |
|---|---|---|
| MCP tool result | `PostToolUse` hook: `inline` (the default), `spilled` or `all` | built; P2 |
| Bash output | the same hook on `Bash` (`stdout` in the tool's output shape) | not built |
| File read | `lab-fold FILE` as a command Claude may run (named in CLAUDE.md) | built; `evals/l2.py` condition `fold-tool` |
| No shell | the `fold` MCP tool (`claude_code/fold_mcp.py`), Bash disallowed; `evals/l2.py` conditions `noshell`, `noshell-fold` | built; P3 |

## Conditions, sizes, models

- **Conditions:** native; the hook in each mode (`fold` spilled, `fold-inline`, `fold-all`); `lab-fold`
  named in CLAUDE.md; no shell.
- **Sizes:**
  - S: under the budget;
  - M: between the budget and Claude Code's spill threshold (MCP 50k characters, Bash 30k);
  - L: over the threshold;
  - XL and XXL: 4 and 16 times L (to ~660k tokens), synthetic only, for how the fold scales; built
    only when asked for (`--bands XL XXL`, a sweep's or dials spec's `bands`).
  A/B 1 and 2 showed the answer turns on this, so every L2 cell reports it. Sizes are in estimated
  tokens (characters / 4), which undercount the synthetic payloads by 1.5 to 2 times (FINDINGS 57).
- **Models:** Haiku (sensitive and cheap), Sonnet (the default), Opus as a spot check.

## Metrics per run

- **Outcome:** correct by the task's scorer; confidently wrong.
- **Tokens:** the final context's size (the input of the last request: what the input criterion
  judges); input tokens summed over requests, by cache class; output tokens.
- **Effort:** cost, tool calls, time.
- **Recovery:** reads of the saved raw file, and how much of it was read.
- **Tool use:** whether `fold` was run, and how.

## Sessions

One-question tasks measure what a fold costs and saves once. A real session uses a result again,
and every later request re-reads whatever the result left in the context. `./lab evals sessions`
asks six questions about one tool result in one Claude Code process (`--input-format stream-json`,
each question sent once the last has its result): the count task's own prompt, which names the tool,
then every planted item, then four items looked up across the payload (`evals.tasks.conversations`).
A native session under the spill threshold holds the raw result and can answer a follow-up from it;
a folded one holds the fold and fetches from the saved raw when the fold does not show the answer.
Every turn is scored and costed on its own (a result event's `total_cost_usd` and `modelUsage` add up
over the session; `usage` and `duration_ms` are the turn's), and the report follows the context
turn by turn: whether the fold's saving survives the follow-ups, and what the fetches cost.

## The prompt cache

Claude Code caches each request's prefix (system prompt, tools, the conversation so far) and writes
it with a one-hour lifetime (`modelUsage.cacheCreationEphemeral1hInputTokens`), priced at 2x the
input price; a cache read is 0.1x, output 5x. Under that structure a run's cost implies one input
price, and the report checks that runs agree on it (Haiku 5.5: $0.10 per million; Sonnet 5.5:
about $1.84) before pricing anything with it.

The hook rewrites a tool result before it enters the conversation and never touches an earlier
message, so it cannot invalidate what is cached. What it changes is what comes after:

- A folded result is written once and re-read by every later request. A context N tokens smaller
  saves N cache-read tokens on each request after it: the report's "each later request" column.
  A one-question eval has few later requests; a long session has many, so this is where a fold's
  saving or cost compounds.
- Every extra request (a recovery read, a second look) re-reads the whole prefix: the "requests"
  and "cache reads" columns.
- A change to the prefix itself (a CLAUDE.md line, an MCP tool's description, a different set of
  allowed tools) makes every later request write a new prefix: offered tools pay this, the hook
  does not.
- The same input must fold to the same text, or repeated calls cannot share cache entries; layer
  1 checks this. A fold that depends on session state (folding a command's output only once) is a
  knob, not a default.
- Parallel eval runs with the same prefix read each other's cached system prompt: "warm starts"
  counts runs whose first request read 10,000 tokens or more from the cache. Conditions with a
  different prefix warm separately, which can tilt a cost comparison; interleaving conditions in
  the job list keeps it even.

## Statistics

- **Paired design:** the same case and seed in every condition, so differences are per case.
- **Accuracy:** with a Wilson 95% interval; paired accuracy with Newcombe's interval and McNemar's
  exact p (a bootstrap is too sure with few discordant pairs; FINDINGS 33).
- **Tokens, cost and time:** as the paired median difference with a bootstrap interval.
- **Sample size:** about 80 paired cases per format and kind detect a 10-point accuracy drop (McNemar,
  80% power, in the best case where every discordant pair goes the same way). Smaller runs are
  labelled indicative, as A/B 1 to 3 are.
- **Kill criteria:** set in README.md before measuring, unchanged.

## Running

```
./lab evals l1 [--budget 2000] [--only json log ...] [--name l1-x]   # layer 1, free, ~15 s (S to L)
./lab evals l1 --bands XL XXL --only json log a11y figma            # the larger bands, ~80 s
./lab check                                                         # includes a layer-1 sample
./lab evals l2 --dry-run [--bands M L] [--reps N]                   # layer 2: the plan and its cost
./lab evals l2 --bands M L --name l2-x [--first-rep N]              # run it (headless Claude Code)
./lab evals l2 --merge l2-x l2-y --name l2-xy                       # report runs together, rescored
./lab evals sweep sweeps/schema-rare.toml                           # layer 1 over a grid of knobs (free)
./lab evals dials dials/haiku-m.toml --dry-run                      # layer 2 over dial settings, one model
./lab evals sessions sessions/haiku.toml --dry-run                  # follow-up questions in one session
```

Every entry point takes the same knobs (`compressors/config.py`): `--config FILE.toml` and
`--set NAME=VALUE` for `./lab fold`, `./lab evals l1` and `./lab evals l2`; the hook reads
`TOOL_OUTPUT_LAB_CONFIG`, `TOOL_OUTPUT_LAB_SET` and `TOOL_OUTPUT_LAB_VIEW`. Layer 1 and layer 2
record the knobs and view with every row, and layer 2 will not merge runs folded differently.

The code: `evals/truth.py` (answer kinds and scorers), `evals/synthetic.py` (planted payloads),
`evals/real.py` (real files and their computed answers), `evals/tasks.py` (the registry),
`evals/l1.py` (invariants, sufficiency, the report).

## Build order

| Phase | Builds | Model cost |
|---|---|---|
| P1 | A task registry (format, kind, source, prompt, ground truth, scorer); L1 invariants and sufficiency over every synthetic and real source; the absent, count, enumerate and locate kinds for JSON, logs, XML, accessibility trees and code. **Done**: `evals/`, `./lab evals l1`, results in FINDINGS.md 28-32 | none |
| P2 | L2 on P1's tasks, sizes M and L: native against fold spilled-only and fold all, Haiku, 3 seeds, paired. **Done** with 2 repetitions: `./lab evals l2`, results in FINDINGS.md 33-39, `results/l2-p2.md` | $4.93 |
| P3 | The same on Sonnet; the no-shell channel; edit tasks with executable checks. As run, one repetition on Sonnet under a $25 ceiling (`--max-cost`): (a) M, native against `fold-inline`, the default, all 52 MCP tasks; (b) L, native against `fold`, spot and absent; (c) the 22 file tasks under native, `noshell` and `noshell-fold` (the `fold` MCP tool, `claude_code/fold_mcp.py`); (d) 5 edit tasks, checked by `ast`, under native, `fold-tool`, `noshell` and `noshell-fold`. **Done**: results in FINDINGS.md 40-45, `results/l2-p3.md` | $24.69 |
| P4 | Explain tasks with the validated judge; context growth; Opus spot checks; Markdown, CSV and diffs | about $10 |

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
| Spot | "Is any pod unhealthy? Name it." | the needle as a whole token in the answer | lost anomalies |
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
| JSON lists | pods, users, commits (`harness/needle.py`) | PyPI release JSON (3 MB, saved once); `uv pip list --format json` |
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
| MCP tool result | `PostToolUse` hook, spilled-only or all | built, A/B 1 to 3 |
| Bash output | the same hook on `Bash` (`stdout` in the tool's output shape) | not built |
| File read | `fold FILE` as a command Claude may run | built, comprehension A/B |
| No shell | an MCP tool that returns `fold`'s output, with Bash disabled | not built; where `fold` should matter most |

## Conditions, sizes, models

- **Conditions:** native; fold, spilled-only; fold, all results; `fold` named in CLAUDE.md; no shell.
- **Sizes:**
  - S: under the budget;
  - M: between the budget and Claude Code's spill threshold (MCP 50k characters, Bash 30k);
  - L: over the threshold.
  A/B 1 and 2 showed the answer turns on this, so every L2 cell reports it.
- **Models:** Haiku (sensitive and cheap), Sonnet (the default), Opus as a spot check.

## Metrics per run

- **Outcome:** correct by the task's scorer; confidently wrong.
- **Tokens:** input tokens summed over requests; output tokens; the final context's size (context
  growth, not yet measured).
- **Effort:** cost, tool calls, time.
- **Recovery:** reads of the saved raw file, and how much of it was read.
- **Tool use:** whether `fold` was run, and how.

## Statistics

- **Paired design:** the same case and seed in every condition, so differences are per case.
- **Accuracy:** with a Wilson 95% interval.
- **Tokens, cost and time:** as the paired median difference with a bootstrap interval.
- **Sample size:** about 80 paired cases per format and kind detect a 10-point accuracy drop (McNemar,
  80% power, in the best case where every discordant pair goes the same way). Smaller runs are
  labelled indicative, as A/B 1 to 3 are.
- **Kill criteria:** set in README.md before measuring, unchanged.

## Running

```
./lab evals l1 [--budget 2000] [--only json log ...] [--name l1-x]   # layer 1, free, ~15 s
./lab check                                                         # includes a layer-1 sample
```

The code: `evals/truth.py` (answer kinds and scorers), `evals/synthetic.py` (planted payloads),
`evals/real.py` (real files and their computed answers), `evals/tasks.py` (the registry),
`evals/l1.py` (invariants, sufficiency, the report).

## Build order

| Phase | Builds | Model cost |
|---|---|---|
| P1 | A task registry (format, kind, source, prompt, ground truth, scorer); L1 invariants and sufficiency over every synthetic and real source; the absent, count, enumerate and locate kinds for JSON, logs, XML, accessibility trees and code. **Done**: `evals/`, `./lab evals l1`, results in FINDINGS.md 28-32 | none |
| P2 | L2 on P1's tasks, sizes M and L: native against fold spilled-only and fold all, Haiku, 3 seeds, paired | about $5 |
| P3 | The same on Sonnet; the no-shell channel; edit tasks with executable checks | about $15 to $25 |
| P4 | Explain tasks with the validated judge; context growth; Opus spot checks; Markdown, CSV and diffs | about $10 |

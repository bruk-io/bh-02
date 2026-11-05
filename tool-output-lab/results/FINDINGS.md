# Findings

What we have learned about envelopes, oldest first. Each entry starts with the result in one line,
then the numbers, then what it means. Each names the run it comes from (`results/<name>.md`).

Everything measured before 2026-11-04 was dropped: it tested older designs. Git keeps it, up to
commit `ea8c2e5`.

**Words used here**

- **Native**: Claude Code as it is, with no envelope.
- **Envelope**: our short summary of a large tool output. Claude Code shows the model the envelope
  instead of the output, and the full output is saved to a file the model can read.
- **Recipe**: one way to build an envelope. `schema` and `sample` are the first two; `full`, `lean`
  and `index` came later (entry 5).
- **Medium and large outputs**: medium ones (about 4k to 12k tokens) fit within Claude Code's limit,
  so native shows them in full. Large ones are over it (here about 19k to 70k tokens), so native
  Claude Code saves them to a file and shows only a preview.
- **Layer 1**: a check with no model. It folds every test output and asks whether the answer can be
  read off the envelope, and whether everything the envelope states is true.
- **Layer 2**: real Claude Code runs. Each task runs once natively and once with the envelope, and
  the two are compared.
- **The pass rules**, set before any run: the envelope must not lose more than 3 points of
  answers, and it must make the model's final context smaller. "Not settled" means the runs were
  too few to tell.

## 1. Envelopes never state anything false (layer 1)

Runs: `results/l1-1-sample.md`, `results/l1-1-schema.md`.

- We folded all 251 test outputs with both recipes. Every number, line and row an envelope states
  was recomputed from the output, and every command it suggests was run. None was wrong.
- How often the answer could be read off the envelope, out of the outputs that were folded:

  | Kind of output | sample | schema |
  |---|---|---|
  | JSON (list of pods) | 23/30 | 25/30 |
  | Logs | 26/30 | 26/30 |
  | Accessibility snapshots | 24/30 | 24/30 |
  | Figma XML | 26/30 | 26/30 |
  | Python files | 12/15 | 12/15 |
  | Rust files | 6/6 | 6/6 |
  | XML file (ISO 3166) | 3/6 | 3/6 |
  | PyPI JSON | 3/5 | 4/5 |
  | HDFS log (real) | 12/24 | 12/24 |
  | MCP-Atlas (real) | 21/59 | 17/59 |

- Most misses on the test outputs are lookups of one row ("what is the IP of pod X?") when the
  tool call doesn't name the row. With the name, every lookup is answerable.
- `schema` also missed two cases: a $0.00 invoice (fixed in entry 8) and listing 12 failing pods
  out of 100. `sample` also missed a pod with 97 restarts.
- The envelope is small: about 190 to 230 tokens for a test output under `schema` (0 to 4% of the
  output), about 280 to 450 under `sample`.

## 2. What part of the envelope matters most (layer 1)

Runs: `results/sweep-envelopes.md` (JSON), `results/sweep-logs.md`, `results/sweep-trees.md`.

We tried 72 combinations of the envelope's parts. None stated anything false.

- **The anomalies part matters most.** It is what finds the odd rows. JSON's full exception list
  found all 12 planted problems and all 3 subtle ones; the simpler rules found 9 or 10 and at most
  1. The same held for logs and trees.
- **Showing the rows that match the question answers the lookups.** Extra sample rows answered
  almost nothing more and cost 65 to 200 tokens.
- **500 tokens is too small** for some tasks: it halved the log counting tasks.

## 3. Haiku on real tasks (MCP-Atlas): answers held where the envelope was used, and the context shrank by about 3,800 tokens

Run: `results/dials-haiku-atlas.md` (354 runs, $3.10).

- The envelope was used in only about half the runs. In the rest, the replayed tool gave the
  model a different, smaller output, so there was nothing to fold.
- Where it was used:

  | Recipe | runs compared | answers | final context | cost |
  |---|---|---|---|---|
  | sample | 63 | 2 points lower (5 better, 6 worse) | 3,928 tokens smaller | 5% less |
  | schema | 59 | the same (7 better, 7 worse) | 3,788 tokens smaller | 3% less |

- Both changed answers about as often as native changes its own answers between two runs (19%).
- The context rule passes. The answers rule is not settled: with about 60 runs, the true change
  could be anywhere within about 12 points either way.
- Counting all runs, `sample` looked 10 points worse at medium size. But those losses came from
  runs where the envelope was never used, which are native runs in all but name, so they were
  chance.

## 4. Haiku on test tasks: same answers, 7,000 tokens less context, 23% cheaper

Run: `results/dials-haiku-synthetic.md` (312 runs, $2.04).

- Native got 103 of 104 tasks right; both recipes got 104.
- Both pass both rules.

  | Output size | recipe | final context | cost | time |
  |---|---|---|---|---|
  | medium | sample | 9,522 smaller | 18% less | 2.1 s slower |
  | medium | schema | 8,488 smaller | 17% less | 1.5 s slower |
  | large | sample | 5,258 smaller | 27% less | 5.0 s faster |
  | large | schema | 4,888 smaller | 28% less | 4.8 s faster |

- The model still read the full output in 73 to 87% of runs at medium size, one more step than
  native, which is why those runs are slower. Entry 9 looks at what it read.
- These tasks are easy for Haiku (native gets 99%), so they can show a loss but not much of a
  gain.

## 5. Three more recipes (layer 1)

Runs: `results/l1-2-full.md`, `results/l1-2-lean.md`, `results/l1-2-index.md`.

- **full**: everything in `schema`, plus one ordinary row as an example.
- **lean**: a shorter summary, the anomalies and one command; no example rows.
- **index**: everything in `schema`, plus a ready command for every group in the output (for
  example, one `jq` command per value of each field, one `grep` per kind of log line).

Layer 1: none stated anything false. `full` and `index` answer what `schema` answers, at 45 to 150
tokens more. `lean` is the smallest, but without example rows it shows none of the rows a
question names, so it answers no lookups unless the model fetches them.

## 6. The three recipes on Haiku: none beats schema, and none changes how often the model re-reads

Run: `results/dials-haiku-patterns.md` (520 runs, $3.29).

| Recipe | answers right (of 104) | final context | cost | runs that read the full output, medium / large (of 52) |
|---|---|---|---|---|
| native | 101 | | | 0 / 52 |
| schema | 104 | 6,693 smaller | 23% less | 36 / 39 |
| full | 104 | 6,656 smaller | 23% less | 35 / 40 |
| lean | 103 | 5,937 smaller | 19% less | 43 / 44 |
| index | 104 | 5,973 smaller | 20% less | 37 / 40 |

- All four pass both rules.
- We predicted before the run what each would change. None of it happened:
  - `full` was meant to make the model re-read less. It didn't (35 against 36).
  - `lean` was meant to give the smallest context. The model re-read more with it (43 against 36),
    so its context ended larger.
  - `index` was meant to make re-reads smaller. They weren't.
- What decides the final context is whether the model reads the full output. The recipes differ
  by 50 to 150 tokens; one read adds thousands.
- Figma XML at medium size is a coin flip: the model either reads the whole 7k-token file or
  doesn't. `schema` and `lean` gave the exact same envelope for those tasks, and the context still
  differed by 10,000 tokens. Entry 4's odd Figma numbers were this, not the recipe.

## 7. Sonnet: it trusts the envelope more than Haiku, and lost one answer

Run: `results/dials-sonnet-synthetic.md` (208 runs, $22.25), `schema` against native.

- Native got 104 of 104 right; `schema` got 103.
- The one miss was the $0.00 invoice that layer 1 had already flagged. The envelope said
  "anomalies: none". Sonnet read the file and still answered "none". Native, reading everything,
  found it.
- The context rule passes. The answers rule is not settled: one miss in 104 runs leaves room for
  a drop of up to 5 points.
- The final context was 6,365 tokens smaller (10,401 at medium size, 2,329 at large). Cost was 23%
  less, about 3 cents a run.
- Sonnet read the full output in half its runs; Haiku did in 72%. At medium size it read it for 3
  of 13 JSON tasks and 4 of 13 logs (Haiku: 6 and 6), but for 12 of 13 Figma files, like Haiku.

## 8. Fixing the "none" mistake, and a rule for odd numbers (layer 1)

Runs: `results/l1-3-schema.md`, `results/l1-3-sample.md`.

- When the envelope finds no anomalies, it no longer says just "none". It lists what it checked
  and says there may be others: "none found by its rules (a line or a value few items hold, an
  error word few items hold, a number far from the rest), which is not proof there are none".
- A new rule for logs and snapshots flags a number far from the others: either far outside the
  usual range, or a zero where every other value is 10 or more. That catches a $0.00 amount among
  amounts of 20 to 900, but not the :00 in a timestamp, since minutes run from 0 to 59.
- Layer 1: both $0.00 invoice tasks are now answerable, nothing else got worse, and nothing false
  was stated. The envelope grew by about 25 tokens.
- Not yet done: JSON doesn't have the zero rule. No model has seen the fix yet.

## 9. When the model goes back to the full output, it mostly runs its own checks, not our commands

From the transcripts of the runs in entries 6 and 7.

| | Sonnet | Haiku |
|---|---|---|
| Runs that went back to the full output | 51% | 72% |
| …when the answer was already in the envelope | 40% | 66% |
| Calls that ran a command the envelope suggested | 0% | 4% |
| Calls that used the envelope's line numbers or paths, with the model's own command | 25% | 12% |
| Calls that were the model's own search | 69% | 81% |
| Calls that read the whole file | 1% | 3% |

- Even when we offered a command for every group (`index`), Haiku ran one in only 8% of its calls.
- Most of the model's own searches re-check what the envelope already said. For example, it
  recounts the hidden Figma cards with `grep -c 'hidden="true"'` after the envelope counted them.
- The line numbers do get used. For example, the model prints the lines around an anomaly the
  envelope pointed to.

What it means: the "get more" commands, as written, are mostly ignored. The model re-reads the
full output to check the envelope, even when the answer is already there. To save more context,
the next thing to try is getting the model to trust what the envelope says, not adding more to it.

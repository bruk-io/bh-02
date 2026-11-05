# Findings

**The question.** When a tool returns a large output, can Claude Code show the model a short
summary of it (an *envelope*) instead, and still get the same answers with less context?

**So far: yes.** On both Haiku and Sonnet, the envelope keeps the answers and shrinks the final
context by about 6,500 tokens, which makes each run about 23% cheaper. The model often goes back to
the full output anyway, mostly to double-check; telling it the counts are exact cuts that by a
quarter. We found one wrong answer (a $0.00 invoice) and fixed its cause.

Each entry below has the same parts: the result in one sentence, what we tried, what happened (a
table with the same columns every time), what it means, caveats, and the run it comes from
(`results/<name>.md`). Results measured before 2026-11-04 tested older designs and were dropped;
git keeps them, up to commit `ea8c2e5`.

## Words used

- **Native**: Claude Code as it is, with no envelope. Every model run compares against it, on the
  same tasks.
- **Envelope**: the short summary the model gets instead of a large tool output. The full output
  is saved to a file the model can still read.
- **Recipe**: one way of building the envelope. `schema` is the one we carry forward; the others
  are `sample`, `full`, `lean` and `index`.
- **Medium and large outputs**: a medium output (about 4k to 12k tokens) fits within Claude Code's
  limit, so native shows it to the model in full. A large one (here about 19k to 70k tokens) is
  over the limit, so native saves it to a file and shows only a preview; native then has to read
  the file.
- **Re-read**: the model opened the saved full output. For native this happens with every large
  output, because it only has a preview.
- **No-model check**: we fold every test output and check, with no model, whether the answer can
  be read off the envelope and whether everything the envelope states is true.
- **Model run**: real Claude Code sessions, each task once natively and once with the envelope.
- **The pass rules**, set before any run: answers may not fall by more than 3 points against
  native, and the final context must be smaller. *Not settled* means the runs were too few to
  rule out a fall of more than 3 points.

How to read the model-run tables: **answers right** counts tasks answered correctly, with native's
count on the same tasks beside it. **Context** and **cost** are the average change against native
on the same tasks. **Re-read** counts runs that opened the saved full output.

---

## 1. Envelopes never state anything false

**What we tried.** We folded all 251 test outputs with the `sample` and `schema` recipes, and
checked everything each envelope states against the output, with no model.

**What happened.**

| Kind of output | answerable from the envelope: sample | schema |
|---|---|---|
| JSON (list of pods) | 23 of 30 | 25 of 30 |
| Logs | 26 of 30 | 26 of 30 |
| Accessibility snapshots | 24 of 30 | 24 of 30 |
| Figma XML | 26 of 30 | 26 of 30 |
| Python files | 12 of 15 | 12 of 15 |
| Rust files | 6 of 6 | 6 of 6 |
| XML file (ISO 3166) | 3 of 6 | 3 of 6 |
| PyPI JSON | 3 of 5 | 4 of 5 |
| HDFS log (real) | 12 of 24 | 12 of 24 |
| MCP-Atlas (real) | 21 of 59 | 17 of 59 |

No envelope stated anything false: every number, line and row was recomputed, and every suggested
command was run.

**What it means.** The envelope is safe to read: what it says is true. Most tasks can be answered
from it alone.

**Caveats.**
- Most misses on the test outputs are lookups of one row ("what is the IP of pod X?") when the
  tool call doesn't name the row. With the name, every lookup is answerable.
- `schema` missed a $0.00 invoice (fixed in entry 8) and a list of 12 failing pods out of 100.
- The envelope is small: about 190 to 230 tokens for a test output under `schema`, 280 to 450
  under `sample`.

**Run.** `results/l1-1-sample.md`, `results/l1-1-schema.md`.

## 2. The anomalies part matters most

**What we tried.** We swapped the envelope's parts one at a time (72 combinations) and ran the
no-model check on each.

**What happened.**

| Part changed | effect on the tasks answerable from the envelope |
|---|---|
| Anomalies: full exception list instead of simpler rules (JSON) | finds 12 of 12 planted problems instead of 9 or 10, and 3 of 3 subtle ones instead of at most 1 |
| Samples: the rows that match the question | answers 5 to 13 more lookups |
| Samples: extra example rows | answer almost nothing more, cost 65 to 200 tokens |
| Budget: 500 tokens instead of 2,000 | halves the log counting tasks |

No combination stated anything false.

**What it means.** The anomalies part is what finds the odd rows, so it is the part to keep at
its fullest. Extra example rows are not worth their tokens, as far as a no-model check can tell.

**Run.** `results/sweep-envelopes.md`, `results/sweep-logs.md`, `results/sweep-trees.md`.

## 3. On real tasks, Haiku keeps its answers where the envelope is used

**What we tried.** Haiku on 59 real tasks from MCP-Atlas, replayed from recorded tool calls, each
twice: native, `sample` and `schema`.

**What happened.** The envelope was used in only about half the runs: in the rest, the replayed
tool gave the model a different, smaller output, so there was nothing to fold. On the runs where
it was used:

| Recipe | answers right | context | cost | re-read |
|---|---|---|---|---|
| sample | 37 of 63 (native 38) | 3,928 tokens smaller | 5% cheaper | 47 of 63 (native 14) |
| schema | 39 of 59 (native 39) | 3,788 tokens smaller | 3% cheaper | 47 of 59 (native 12) |

**What it means.** On real tasks the envelope keeps the answers and shrinks the context, as on
the test tasks. The context rule passes; the answers rule is not settled.

**Caveats.**
- With about 60 runs, the true change in answers could be anywhere within about 12 points either
  way.
- Counting every run, not just those where the envelope was used, made `sample` look 10 points
  worse at medium size. Those losses came from runs with no envelope, which are native runs in
  all but name, so they were chance.

**Run.** `results/dials-haiku-atlas.md` (354 runs, $3.10).

## 4. On test tasks, Haiku keeps its answers, with 7,000 tokens less context

**What we tried.** Haiku on 104 test tasks (JSON, logs, accessibility snapshots and Figma XML, at
medium and large sizes): native, `sample` and `schema`.

**What happened.**

| Recipe | answers right | context | cost | re-read |
|---|---|---|---|---|
| sample | 104 of 104 (native 103) | 7,390 tokens smaller | 23% cheaper | 87 of 104 (native 52) |
| schema | 104 of 104 (native 103) | 6,688 tokens smaller | 23% cheaper | 72 of 104 (native 52) |

By size, under `schema`: medium outputs 8,488 tokens smaller and 1.5 seconds slower; large
outputs 4,888 tokens smaller and 4.8 seconds faster.

**What it means.** Both recipes pass both rules. The envelope saves most at medium size, where
native holds the whole output, and saves time at large size, where native must read the file.

**Caveats.**
- Native gets 99% of these tasks right, so they can show a loss but hardly a gain.
- The runs are slower at medium size because the model often re-reads the full output (entry 9).

**Run.** `results/dials-haiku-synthetic.md` (312 runs, $2.04).

## 5. Three more recipes

**What we tried.** Three more ways of building the envelope, checked with no model:

- **full**: everything in `schema`, plus one ordinary row as an example.
- **lean**: a shorter summary, the anomalies and one command; no example rows.
- **index**: everything in `schema`, plus a ready command for every group in the output (one `jq`
  command per value of each field, one `grep` per kind of log line, a line range per run of
  items).

**What happened.**

| Recipe | test tasks answerable | lookups answerable, when the tool call names the row | size against schema |
|---|---|---|---|
| schema | 85 of 104 | 16 of 16 | |
| full | 85 of 104 | 16 of 16 | 45 to 90 tokens more |
| lean | 85 of 104 | 0 of 16 | up to 75 tokens less |
| index | 85 of 104 | 16 of 16 | 40 to 150 tokens more |

None stated anything false.

**What it means.** `full` and `index` answer what `schema` answers, for a few more tokens. `lean`
is smallest, but without example rows it shows none of the rows a question names, so the model
has to fetch them.

**Run.** `results/l1-2-full.md`, `results/l1-2-lean.md`, `results/l1-2-index.md`.

## 6. On Haiku, no other recipe beats schema

**What we tried.** Haiku on the 104 test tasks: native, `schema` and the three recipes of entry 5.

**What happened.**

| Recipe | answers right | context | cost | re-read |
|---|---|---|---|---|
| schema | 104 of 104 (native 101) | 6,693 tokens smaller | 23% cheaper | 75 of 104 (native 52) |
| full | 104 of 104 (native 101) | 6,656 tokens smaller | 23% cheaper | 75 of 104 (native 52) |
| lean | 103 of 104 (native 101) | 5,937 tokens smaller | 19% cheaper | 87 of 104 (native 52) |
| index | 104 of 104 (native 101) | 5,973 tokens smaller | 20% cheaper | 77 of 104 (native 52) |

**What it means.** All four pass both rules, and none does better than `schema`. Before the run
we predicted that `full` would make the model re-read less, that `lean` would give the smallest
context, and that `index` would make re-reads smaller. None of these happened: `lean` made the
model re-read more, so its context ended larger.

**Caveats.**
- Figma XML at medium size is a coin flip: the model either reads the whole 7k-token file or
  doesn't. `schema` and `lean` gave the exact same envelope for those tasks, yet their contexts
  differed by 10,000 tokens.
- An earlier version of this entry said one re-read adds thousands of tokens. Entry 10 corrects
  it: a re-read adds about 1,000 at the median, and thousands only when the model reads a whole
  file.

**Run.** `results/dials-haiku-patterns.md` (520 runs, $3.29).

## 7. Sonnet re-reads less than Haiku, and lost one answer

**What we tried.** Sonnet on the 104 test tasks: native and `schema`.

**What happened.**

| Recipe | answers right | context | cost | re-read |
|---|---|---|---|---|
| schema | 103 of 104 (native 104) | 6,365 tokens smaller | 23% cheaper (about 3 cents a run) | 53 of 104 (native 52) |

The one miss was a $0.00 invoice among normal ones. The envelope said "anomalies: none". Sonnet
read the file and still answered "none". Native, reading everything, found it.

**What it means.** The context rule passes; the answers rule is not settled (one miss in 104 runs
leaves room for a fall of up to 5 points). The miss was the envelope's fault: the gap the no-model
check had already flagged in entry 1, fixed in entry 8.

**Caveats.**
- At medium size, Sonnet re-read the full output for 3 of 13 JSON tasks and 4 of 13 logs (Haiku: 6
  and 6), but for 12 of 13 Figma files, like Haiku.

**Run.** `results/dials-sonnet-synthetic.md` (208 runs, $22.25).

## 8. The $0.00 invoice is now found

**What we tried.** Two changes, checked with no model on every test output:

- When the envelope finds no anomalies, it no longer says just "none". It lists what it checked
  and says there may be others: "none found by its rules (a line or a value few items hold, an
  error word few items hold, a number far from the rest), which is not proof there are none".
- A new rule for logs and snapshots flags a number far from the others: far outside the usual
  range, or a zero where every other value is 10 or more. That catches a $0.00 amount among
  amounts of 20 to 900, but not the :00 in a timestamp, since minutes run from 0 to 59.

**What happened.**

| | before | after |
|---|---|---|
| $0.00 invoice tasks answerable from the envelope | 0 of 2 | 2 of 2 |
| Other tasks that got worse | | none |
| False statements | none | none |
| Envelope size | | about 25 tokens larger |

**What it means.** The envelope now shows the $0.00 invoice, and says plainly when it found
nothing. Entry 11 checks whether models act on it.

**Caveats.**
- JSON does not have the zero rule yet.
- A first draft flagged times of day in a log and hid some hidden Figma cards; both were fixed
  before these checks.

**Run.** `results/l1-3-schema.md`, `results/l1-3-sample.md`.

## 9. When the model re-reads, it runs its own checks, not our commands

**What we tried.** We read the transcripts of the runs in entries 6 and 7, and sorted every call
the model made to the saved full output after it got the envelope.

**What happened.**

| | Sonnet | Haiku |
|---|---|---|
| Runs that re-read the full output | 53 of 104 | 75 of 104 |
| …when the answer was already in the envelope | 34 of 85 | 56 of 85 |
| Calls that ran a command the envelope suggested | 0% | 4% |
| Calls that used the envelope's line numbers or paths, with the model's own command | 25% | 12% |
| Calls that were the model's own search | 69% | 81% |
| Calls that read the whole file | 1% | 3% |

**What it means.** The model mostly re-reads to double-check what the envelope said. For example,
after the envelope counted the hidden Figma cards, it counted them again with
`grep -c 'hidden="true"'`. It uses the envelope's line numbers, but hardly ever the commands we
suggest: even when we offered one for every group (`index`), Haiku used one in only 8% of calls.

**Run.** The transcripts of `results/dials-sonnet-synthetic.md` and `results/dials-haiku-patterns.md`.

## 10. Saying the counts are exact makes Haiku re-read less, but saves little context

**What we tried.** Haiku on the 104 test tasks: native, `schema` with the usual banner, and
`schema` with one more sentence in the banner: "Every count and value in the envelope is exact,
worked out over the whole output, not a sample: read the file only for what the envelope does not
show."

**What happened.**

| Banner | answers right | context | cost | re-read |
|---|---|---|---|---|
| usual | 104 of 104 (native 100) | 6,458 tokens smaller | 25% cheaper | 70 of 104 (native 52) |
| exact counts | 104 of 104 (native 100) | 6,158 tokens smaller | 25% cheaper | 51 of 104 (native 52) |

When the answer was already in the envelope, 55 of 85 runs re-read under the usual banner, and 33
under the new one.

**What it means.** The model can be talked into trusting the envelope, at no cost in answers. But
the re-reads it drops are cheap ones, so the context barely changes: on these tasks the envelope
already saves most of what can be saved.

**Caveats.**
- The drop in re-reading is not chance: 23 tasks were re-read only under the usual banner, and 4
  only under the new one (p = 0.0003). It fell for every kind of output except Figma XML.
- Most re-reads are small checks: runs that re-read ended only about 1,000 tokens larger at the
  median.
- A model that trusts the envelope more is hurt more when the envelope misses something, so the
  wording of entry 8 matters alongside this banner.

**Run.** `results/dials-haiku-banner.md` (312 runs, $2.00).

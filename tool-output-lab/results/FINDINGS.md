# Findings

When a tool returns a large output, Claude Code either puts all of it in the model's context or,
when it is over Claude Code's size limit, saves it to a file and shows the model a preview. We
tested a third way. A hook replaces the large output with a short summary of it, which we call the
envelope, and saves the full output to a file that the model can still open. We wanted to know
whether the model still answers correctly, and whether its context ends up smaller.

## Result

On every set of tasks we tested, the model answered at least as well with the envelope as without
it, and its context ended up smaller.

The 104 test tasks ask questions about four kinds of output: lists of pods as JSON, request logs,
accessibility snapshots and Figma files. The 40 "what is wrong" tasks are the ones among them that
ask what is wrong in the output. They include two where one invoice in a list has an amount of
$0.00, and eight where nothing is wrong and the right answer is "nothing".

We ran the final version of the envelope three times, each time against Claude Code without the
envelope on the same tasks.

| Answers right | With the envelope | Without |
|---|---|---|
| Haiku, 104 test tasks | 104 of 104 | 100 of 104 |
| Haiku, 40 "what is wrong" tasks, each run twice | 80 of 80 | 72 of 80 |
| Sonnet, 40 "what is wrong" tasks | 40 of 40 | 39 of 40 |

| What the envelope saved per run | Context | Cost |
|---|---|---|
| Haiku, 104 test tasks | 6,158 tokens | 25% |
| Haiku, 40 "what is wrong" tasks, each run twice | 7,267 tokens | 29% |
| Sonnet, 40 "what is wrong" tasks | 8,164 tokens | 26% |

Context is the size of the model's input on its last request. Cost is what the API charged.

Before any run, we set two bars. Answers with the envelope may not fall more than 3 percentage
points below answers without it, and the final context must be smaller. Haiku meets both bars.
Sonnet's context is smaller, and Sonnet got all 40 answers right, but 40 runs are too few to rule
out a fall of more than 3 points. On an earlier version of the envelope, over all 104 test tasks,
Sonnet got 103 right against 104 without the envelope.

Haiku did better with the envelope than without it on the "what is wrong" tasks, by 10 points, and
the gain is larger than chance would give (the 95% range is 3 to 19 points). Without the envelope,
Haiku missed problems in large snapshots and Figma files, where it sees only a preview and has to
search the file itself.

The saving depends on the size of the output. A medium output (about 4,000 to 12,000 tokens) fits
within Claude Code's limit, so without the envelope the model holds all of it. A large output
(about 19,000 to 70,000 tokens) is over the limit, so without the envelope the model has to search
the saved file. These are Haiku's 104 test tasks again, split by size:

| Output size | Tokens saved per run | Cost saved | Time per run |
|---|---|---|---|
| Medium | 9,185 | 18% | 3.0 s slower |
| Large | 3,131 | 31% | 8.9 s faster |

Medium runs are slower because the model often opens the full output as well as reading the
envelope.

## What an envelope looks like

Here a tool returned a list of 100 invoices as JSON, about 2,800 tokens, and the tool call asked
about invoice INV-1024. Two of the invoices are overdue. The hook replaced the list with an
envelope of about 140 tokens. Everything shown below is the hook's real output for this list.

### The banner

The envelope starts with a banner that tells the model what it is reading and where the full
output is:

```
[Folded: ~2772 tokens -> ~143. Full output: /tmp/tool-results/invoices.json. This is the data's envelope: its shape (fields, values and counts), the rows that break it, samples, and how to get more, by jq path (jq). FILE in a command is /tmp/tool-results/invoices.json. Every count and value in the envelope is exact, worked out over the whole output, not a sample: read the file only for what the envelope does not show.]
```

### Part 1: what the output is

```
shape:
  .invoices: array[100] of object
    .id        str, unique like INV-<n>
    .customer  "Acme" 20, "Birch" 20, "Cobalt" 20, "Dune" 20, "Ember" 20
    .amount    float, unique
    .status    "paid" 98, "overdue" 2
```

The list holds 100 invoices, and each invoice has four fields. Every customer has 20 invoices, and
98 invoices are paid while 2 are overdue. The hook counted these over all 100 rows.

### Part 2: the rows that do not fit

```
anomalies: 2 rows, all listed
  .invoices[16] INV-1017: .status "overdue"
  .invoices[71] INV-1072: .status "overdue"
```

Two invoices are overdue when the other 98 are paid, so the envelope lists both, with their place
in the list, and says that these are all of them. When nothing stands out, this part lists the
checks it ran instead. This is what it says for the same list with every invoice paid:

```
anomalies: none found by its rules (a value few rows hold where one dominates, a number far outside the rest, a key few rows have or lack, a value of another type), which is not proof there are none
```

### Part 3: rows copied from the output

```
samples:
  .invoices[23]: {"id":"INV-1024","customer":"Dune","amount":274.86,"status":"paid"}  (matches the query)
```

The tool call asked about INV-1024, so the envelope copies that row exactly as it is in the output.

### Part 4: how to read the rest

```
get more:
  jq '.invoices[] | select(.status != "paid") | .id' FILE
  jq '.invoices[16]' FILE  (reads any path above)
```

The first command prints the id of every invoice that is not paid. The second reads one row by its
place in the list, and works for any place the envelope shows. FILE stands for the saved file.

### The same parts for a log

For a log, the envelope works line by line. It groups lines that follow the same pattern, which is
the line with every word that holds a digit or a hex id replaced by `<*>`. This is the envelope of
a request log of 300 lines:

```
shape: 300 lines, 5 line templates (<*> is a token holding a digit, or a hex id)
      85  <*>:<*>:<*> INFO  GET /api/orders req=<*> user=<*> <*> <*>
      75  <*>:<*>:<*> INFO  GET /health req=<*> user=<*> <*> <*>
      69  <*>:<*>:<*> INFO  GET /api/items req=<*> user=<*> <*> <*>
      68  <*>:<*>:<*> INFO  GET /api/users req=<*> user=<*> <*> <*>
       3  <*>:<*>:<*> ERROR payment failed for order <*> req=<*> user=<*>
anomalies: 3 lines in 1 group, all listed
  3 lines like: <*>:<*>:<*> ERROR payment failed for order <*> req=<*> user=<*>
    188: 2026-11-03T00:03:07Z ERROR payment failed for order ORD-4e4b61 req=req-525f51ac user=u-a7cedc
    196: 2026-11-03T00:03:15Z ERROR payment failed for order ORD-1da976 req=req-25704aed user=u-1bd3e9
    289: 2026-11-03T00:04:48Z ERROR payment failed for order ORD-3044f5 req=req-5773740c user=u-e5070c
get more:
  grep -nF 'ERROR payment failed for order' FILE  (the 3 lines like it)
  sed -n 'A,Bp' FILE  (any lines above, by number)
```

The 300 lines follow 5 patterns, and the count beside each pattern is how many lines follow it.
Three lines are payment errors, so the envelope lists them with their line numbers and gives a
`grep` command that prints exactly those three lines.

The hook also builds envelopes for accessibility snapshots, XML, web pages and source code. [The
envelope](https://claude.ai/artifact/BZNhBgeCmSDnquEMcnvBkj) page shows one of each.

## What we learned along the way

**Everything the envelope says is true.** We wrote a checker that shares no code with the code that
builds the envelope. It counts every number again against the full output, compares every quoted
line with the original, and runs every command the envelope suggests. Across 251 test outputs and
every version of the envelope we tried, the checker found no false statement. It also counts how
many tasks the envelope answers on its own, without the model opening the file. For the final
version on the medium and large test outputs, these are the counts:

| Kind of question | Answered by the envelope alone |
|---|---|
| How many rows or lines have something | 32 of 32 |
| What is wrong in the output | 32 of 32 |
| What is wrong, when nothing is | 8 of 8 |
| List every row that has something | 15 of 16 |
| Look up one row the tool call does not name | 0 of 16 |
| Look up one row the tool call names | 16 of 16 |

On real outputs, fewer tasks can be answered from the envelope alone:

| Real output | Answered by the envelope alone |
|---|---|
| HDFS server log | 10 of 20 |
| MCP-Atlas tool results | 17 of 59 |
| Python source files | 12 of 15 |
| Rust source files | 6 of 6 |
| ISO 3166 country list (XML) | 0 of 3 |
| PyPI release data (JSON) | 2 of 3 |

For the country list, all 3 can be answered when the tool call names the country.

**The list of rows that do not fit matters most.** We changed one part of the envelope at a time and
used the checker to count the tasks the envelope answers on its own.

| Change to the envelope | What it changed |
|---|---|
| List every JSON row that breaks the pattern, instead of applying simpler rules | Finds 12 of 12 planted problems instead of 9 or 10 |
| Copy the rows that contain words from the tool call | Answers 5 to 13 more lookups |
| Add more example rows | Answers almost nothing more, and costs 65 to 200 tokens |
| Allow 500 tokens instead of 2,000 | Answers half as many of the log counting tasks |

**One wrong answer led to two changes.** In an early run, Sonnet missed the invoice with an amount
of $0.00. The envelope had said "anomalies: none", and Sonnet answered "none" even after opening the
file. We changed the envelope in two ways. It now flags a number far from the rest, such as a zero
among amounts of 20 to 900. When it finds nothing, it now lists the checks it ran and says there may
be problems they do not catch.

| The invoice with an amount of $0.00 | Before the changes | After |
|---|---|---|
| The envelope shows it | 0 of 2 tasks | 2 of 2 tasks |
| Haiku found it | 2 of 2 runs | 4 of 4 runs |
| Sonnet found it | 1 of 2 runs | 2 of 2 runs |

After the changes, neither model reported a problem in the 24 runs where nothing was wrong.

**The model often opens the full output anyway.** It opened the saved file in about half to two
thirds of the runs, often when the answer was already in the envelope. A sentence in the banner
that says every count is exact cut how often Haiku did this, and it lost no answers.

| Runs that opened the full output | With the envelope | Without |
|---|---|---|
| Haiku, without the sentence that counts are exact | 70 of 104 | 52 of 104 |
| Haiku, with that sentence | 51 of 104 | 52 of 104 |
| Sonnet, without that sentence | 53 of 104 | 52 of 104 |

Without the envelope, the model opens the file for every large output, because it sees only a
preview, and 52 of the 104 tasks are large. Opening the file less did not make Haiku's context much
smaller, because most of these reads are small searches that add about 1,000 tokens.

When the model opened the file, it mostly ran its own search to check what the envelope said. For
example, after the envelope had counted the hidden cards in a Figma file, the model counted them
again with `grep`. It almost never ran the commands the envelope suggested.

| What the model's call to the file did | Sonnet | Haiku |
|---|---|---|
| Ran a command the envelope suggested | 0% | 4% |
| Used the envelope's line numbers in its own command | 25% | 12% |
| Ran its own search | 69% | 81% |
| Read the whole file | 1% | 3% |

**How the envelope is built barely changes the result.** We tried five versions of the envelope,
all made by the same code:

- `schema` has the four parts shown above. The final version is `schema` with the two changes for
  the $0.00 invoice and the sentence that counts are exact.
- `full` is `schema` plus one ordinary row as an example.
- `lean` has a shorter description, the rows that do not fit and one command, with no example rows.
- `index` is `schema` plus a ready command for every group of rows.
- `sample` shows the first and last rows of the output instead of the rows the tool call names.

The first four ran on Haiku in one run, on the 104 test tasks:

| Version | Right, of 104 | Tokens saved per run | Opened the file, of 104 |
|---|---|---|---|
| `schema` | 104 | 6,693 | 75 |
| `full` | 104 | 6,656 | 75 |
| `lean` | 103 | 5,937 | 87 |
| `index` | 104 | 5,973 | 77 |
| Without the envelope | 101 | | 52 |

In an earlier run, `sample` got 104 right against 103 without the envelope, saved 7,390 tokens per
run, and opened the full output in 87 of 104 runs. None of the versions did clearly better than
`schema`. `lean` made Haiku open the file more often, so it saved less.

## What is not settled

- Sonnet has had only 40 runs of the final version, which is too few to rule out a fall in answers
  of more than 3 points.
- Without the envelope, Claude Code gets 96 to 99% of the test tasks right, so these tasks show a
  loss more easily than a gain.
- We ran Haiku on 59 real tasks from the MCP-Atlas benchmark, which we replay from recorded tool
  calls. In about half the runs, the replay returned a smaller output than the recorded one, so the
  envelope had nothing to replace. The table below counts only the runs where the envelope was
  used, with `schema` before the changes. In those runs the context was 3,788 tokens smaller and
  the cost 3% lower.

| Haiku on MCP-Atlas | With the envelope | Without |
|---|---|---|
| Answers right | 39 of 59 | 39 of 59 |
| Opened the full output | 47 of 59 | 12 of 59 |

- For JSON, the envelope does not yet flag a zero among numbers that are all 10 or more. For logs
  and outlines, it does.
- We have not yet tested the envelope in long sessions, where the model answers several questions
  about one output.

## Next

1. Make the sentence that says every count is exact part of the hook's default banner. Today it is
   a setting (`banner=exact`).
2. Run Sonnet on the MCP-Atlas tasks, and test long sessions with follow-up questions.

## How we measured

Each task runs in headless Claude Code twice, once as it is and once with the hook, and the two
runs are compared task by task. The test tasks have answers we planted in the output. Each kind of
output comes at a medium size, which fits within Claude Code's limit, and a large size, which is
over it. Context and cost come from the API's own counts. The model runs cost about $43 in all.

Before any model run, the checker described above checks every envelope, without a model.

The numbers come from these reports in `results/`:

- The final version on Haiku over the 104 test tasks: `dials-haiku-banner.md` (the `exact` setting).
- The final version on the 40 "what is wrong" tasks: `dials-haiku-fixes.md` and
  `dials-sonnet-fixes.md`.
- Sonnet on an earlier version: `dials-sonnet-synthetic.md`.
- The other versions of the envelope: `dials-haiku-synthetic.md` and `dials-haiku-patterns.md`.
- The MCP-Atlas tasks: `dials-haiku-atlas.md`.
- The checker: `l1-3-schema.md` for the final version, and `sweep-*.md` for the changes one part
  at a time.
- How the model opens the full output: the transcripts of `dials-haiku-patterns.md` and
  `dials-sonnet-synthetic.md`.
- The $0.00 invoice before the changes: `dials-haiku-synthetic.md` and `dials-sonnet-synthetic.md`.

The example envelopes come from the hook's own code. The notes we wrote after each run, in order,
are in git history up to commit `0ab11f7`.

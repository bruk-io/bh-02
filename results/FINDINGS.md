# Summarising large tool outputs for Claude Code

When a tool returns a large output, such as a long log or a big JSON response, Claude Code either
puts all of it into the model's context or, if it is larger than Claude Code's limit, saves it to a
file and shows the model a short preview. We tested a third option. A Claude Code hook, a script
that runs after every tool call, replaces each large output with a short summary, which we call an
envelope, and saves the full output to a file that the model can still open. We wanted to know
whether the model still answers correctly with the envelope, and how much context it saves.

## Summary

<!-- stats: 104 of 104=questions answered correctly with the envelope, against 100 without it; 6,158=fewer tokens of context per run; 25%=lower cost per run | Haiku on all 104 test tasks, with the final version of the envelope -->

- With the envelope, Haiku and Sonnet answered at least as many questions correctly as without it,
  and every run used less context and cost less. [Results](#results)
- The envelope is a short summary in four labelled sections: exact counts, the items that differ
  from the rest, items copied from the output, and commands for reading the rest.
  [How the envelope works](#how-the-envelope-works)
- A separate program checks every envelope against the full output before a model sees it, and it
  has found no mistakes. [How we check the envelope](#how-we-check-the-envelope)
- Fixed rules decide what goes into the envelope, so it can miss a problem that no rule describes.
  [Heuristics](#heuristics)
- The model still opens the full output in about half the runs, mostly to check what the envelope
  said. [How often the model opens the full output](#how-often-the-model-opens-the-full-output)

## Results

The model answered at least as well with the envelope as without it in every test, and it used
less context each time.

We tested on 104 tasks that we built. Each task is a tool output with a question about it, and we
planted the answer in the output, so we know what the right answer is. The outputs are lists of
Kubernetes pods in JSON, web server logs, accessibility snapshots of web pages, and Figma design
files. Each comes in a medium size, which fits within Claude Code's limit, and a large size, which
does not. Forty of the tasks ask the model to find a problem in the output, which is where a
summary is most likely to hide something.

Each task ran twice in Claude Code, once with the hook and once without it, and we compared the two
runs task by task. We ran the final version of the envelope three times.

<!-- chart: paired | Questions answered correctly -->

| Answers right | With the envelope | Without |
|---|---|---|
| Haiku, all 104 tasks | 104 of 104 | 100 of 104 |
| Haiku, 40 find-the-problem tasks, each run twice | 80 of 80 | 72 of 80 |
| Sonnet, 40 find-the-problem tasks | 40 of 40 | 39 of 40 |

<!-- chart: bars 1 | Tokens of context the envelope saved per run -->

| What the envelope saved per run | Context | Cost |
|---|---|---|
| Haiku, all 104 tasks | 6,158 tokens | 25% |
| Haiku, 40 find-the-problem tasks, each run twice | 7,267 tokens | 29% |
| Sonnet, 40 find-the-problem tasks | 8,164 tokens | 26% |

Context here is the number of tokens the model read on its last request. Each run also cost 25 to
29% less, as charged by the API.

Before the runs, we decided that the envelope would pass if correct answers fell by no more than 3
percentage points and the context got smaller. Haiku passed on both counts. Sonnet used less
context and answered all 40 tasks correctly, but 40 runs are too few to rule out a drop of more
than 3 points. With an earlier version of the envelope, Sonnet answered 103 of the 104 tasks
correctly, against 104 without the envelope.

On the 40 find-the-problem tasks, Haiku did 10 points better with the envelope than without it,
which is more than chance would explain (the 95% range is 3 to 19 points). Without the envelope,
Haiku missed problems in the large snapshots and Figma files, where it only gets a preview and has
to search the saved file.

How much the envelope saves depends on the size of the output. Without the envelope, the model holds
a medium output in full, so replacing it saves more. A large output is already replaced by a
preview, and the model searches the file for what it needs. These are Haiku's 104 tasks split by
size.

<!-- chart: bars 1 | Tokens saved per run, by output size -->

| Output size | Tokens saved per run | Cost saved | Time per run |
|---|---|---|---|
| Medium | 9,185 | 18% | 3.0 s slower |
| Large | 3,131 | 31% | 8.9 s faster |

Medium runs cost 18% less but took about 3 seconds longer, because the model often opened the full
output after reading the envelope. Large runs cost 31% less and were about 9 seconds faster.

## How the envelope works

<!-- figure: envelope-flow -->

When a tool's output is larger than 2,000 tokens, the hook saves the output to a file and gives the
model an envelope in its place. The envelope has four sections, each labelled in the text:

- `shape:` describes the output and gives exact counts, worked out over the whole output.
- `anomalies:` lists the items that differ from the rest, with the position of each in the output.
- `samples:` copies a few items exactly, chosen because they contain words from the tool call.
- `get more:` gives line numbers and ready-made commands for reading the rest of the saved file.

A banner above the four sections says where the full output is saved. It also tells the model that
every count is exact and that it should open the file only for what the envelope does not show.

Here is a real envelope. A tool returned a list of 100 invoices as JSON, and the tool call asked
about invoice INV-1024. The hook's own code turned the list into this banner and envelope.

<!-- chart: scale The list of invoices=2772; The banner and envelope=143 | Size in tokens -->

```
[Folded: ~2772 tokens -> ~143. Full output: /tmp/tool-results/invoices.json. This is the data's envelope: its shape (fields, values and counts), the rows that break it, samples, and how to get more, by jq path (jq). FILE in a command is /tmp/tool-results/invoices.json. Every count and value in the envelope is exact, worked out over the whole output, not a sample: read the file only for what the envelope does not show.]
```

<!-- annotated -->

```
shape:
  .invoices: array[100] of object
    .id        str, unique like INV-<n>
    .customer  "Acme" 20, "Birch" 20, "Cobalt" 20, "Dune" 20, "Ember" 20
    .amount    float, unique
    .status    "paid" 98, "overdue" 2
anomalies: 2 rows, all listed
  .invoices[16] INV-1017: .status "overdue"
  .invoices[71] INV-1072: .status "overdue"
samples:
  .invoices[23]: {"id":"INV-1024","customer":"Dune","amount":274.86,"status":"paid"}  (matches the query)
get more:
  jq '.invoices[] | select(.status != "paid") | .id' FILE
  jq '.invoices[16]' FILE  (reads any path above)
```

- `shape:` The list holds 100 invoices with four fields each. Every customer has 20 invoices, and
  98 invoices are paid while 2 are overdue.
- `anomalies:` The two overdue invoices, with their positions in the list. "All listed" means
  there are no others.
- `samples:` Invoice INV-1024, copied exactly as it appears, because the tool call named it.
- `get more:` A command that prints the id of every unpaid invoice, and one that reads any single
  invoice. `FILE` stands for the saved file.

When nothing in the output stands out, the `anomalies:` section says which checks it ran, and that
passing them does not prove there is no problem. This is what it says for the same list with every
invoice paid:

```
anomalies: none found by its rules (a value few rows hold where one dominates, a number far outside the rest, a key few rows have or lack, a value of another type), which is not proof there are none
```

### Logs, page snapshots and other outputs

The hook builds envelopes with the same four sections for logs, page snapshots, XML, web pages,
plain text and source code.

<!-- more: Show the envelopes of a web server log and a page snapshot -->

A log is read line by line. The envelope groups lines that follow the same pattern, where a pattern
is a line with every word that contains a digit or an id replaced by `<*>`. This is the envelope of
a web server log of 300 lines.

<!-- pair -->

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

All 300 lines follow 5 patterns, and the number beside each pattern is how many lines follow it.
Three lines record failed payments, so the envelope lists them by line number and gives a `grep`
command that prints exactly those three.

For an output with an indented structure, such as an accessibility snapshot of a web page, the
envelope shows the outline and counts groups of similar items. This is the envelope of a snapshot
of a page that lists 150 invoices.

<!-- pair -->

```
shape: 610 lines, 15 line templates (<*> is a token holding a digit, a hex id or a quoted string)
  1: - Page URL: https://billing.local/invoices
  2: - Page Title: Invoices
  3: - generic [ref=e53187]:
  4:   - banner [ref=e40337]:
  6:   - main [ref=e27900]:
  7:     - heading "Invoices" [level=1] [ref=e44330]
  8:     - list [ref=e47831]:
            150 items, lines 9-608
            150 items like: - listitem [ref=<*>]:
  609:   - contentinfo [ref=e13672]:
  [+ 2 more nodes, deeper or further on]
anomalies: 3 of 150 items in 1 run, all listed
  3 lines like: - button <*> [ref=<*>] [disabled]  (in 3 of 150 items)
    89:       - listitem [ref=e28671]:
    90:         - text: Invoice INV-87af257
    91:         - text: $595.82 due 12 Nov
    92:         - button "Pay INV-87af257" [ref=e1179] [disabled]
    177:       - listitem [ref=e65742]:
    178:         - text: Invoice INV-668b725
    179:         - text: $121.67 due 27 Nov
    180:         - button "Pay INV-668b725" [ref=e33208] [disabled]
    553:       - listitem [ref=e59312]:
    554:         - text: Invoice INV-193349e
    555:         - text: $281.66 due 22 Nov
    556:         - button "Pay INV-193349e" [ref=e92037] [disabled]
get more:
  grep -nF '] [disabled]' FILE  (the 3 lines like it)
  sed -n 'A,Bp' FILE  (any lines above, by number)
```

The outline shows the top of the page, then says that lines 9 to 608 hold a list of 150 similar
items. Three of the items have a disabled Pay button, so the envelope shows those three items in
full.

For source code, the outline is the code's classes and functions.

<!-- /more -->

### How the envelope fits its budget

Each section can be written at a few levels of detail. The hook starts every section at its
shortest, then adds detail in order of importance (shape, then anomalies, then get more, then
samples) for as long as the envelope stays under 2,000 tokens. Most envelopes come out much smaller
than that, and for our test outputs they were a few hundred tokens.

### How we check the envelope

Before a model sees any envelope, a separate program checks it against the full output. We wrote
this program apart from the code that builds envelopes, so that a mistake in one is unlikely to be
repeated in the other. It counts every number again, compares every copied line with the original,
and runs every command the envelope suggests to see that it prints what the envelope says. We
tested 251 outputs, which include real logs, source files and recorded tool results as well as our
test outputs, and the program found no mistake in any of their envelopes.

The program also tells us which questions can be answered from the envelope alone, without opening
the saved file. These are the counts for the medium and large test outputs:

| Question | Answerable from the envelope alone |
|---|---|
| How many items have some property? | 32 of 32 |
| What is wrong in the output? | 32 of 32 |
| What is wrong, when nothing is? | 8 of 8 |
| Which items have some property? | 15 of 16 |
| A question about one item the tool call does not name | 0 of 16 |
| A question about one item the tool call names | 16 of 16 |

The envelope cannot answer a question about a particular item unless that item stands out or the
tool call names it, because those are the only items it copies.

<!-- more: Show how many questions about real outputs the envelope answers alone -->

Real outputs are less regular than our test outputs, so fewer questions about them can be answered
from the envelope alone:

| Real output | Answerable from the envelope alone |
|---|---|
| Hadoop (HDFS) server log | 10 of 20 |
| Results of tool calls recorded in MCP-Atlas | 17 of 59 |
| Python source files | 12 of 15 |
| Rust source files | 6 of 6 |
| A list of countries in XML (ISO 3166) | 0 of 3 |
| Package release data from PyPI (JSON) | 2 of 3 |

For the list of countries, all 3 questions can be answered when the tool call names the country.

<!-- /more -->

## Heuristics

The hook decides everything in an envelope with fixed rules, and no model is involved. We set the
thresholds by hand and checked them on our test outputs, but we have not tuned them
systematically.

<!-- grid -->

### Every output

- **When to build an envelope.** When the output is over 2,000 tokens, and only if the envelope is
  at most 90% of the output's size.
- **Measurements.** Numbers of six or more digits, such as sizes and timestamps, are never treated
  as categories or as outliers.
- **Unusual numbers.** A number more than three interquartile ranges outside the middle half.
- **Error words.** A fixed list that includes error, failed, fatal, exception, traceback, panic,
  crash, timeout, denied and invalid.
- **Copied items.** Items that contain a word from the tool call, skipping words that more than 5%
  of the lines, or 20% of JSON rows, contain.

### Logs and other line-by-line output

- **Patterns.** Two lines follow the same pattern when they match after every word that contains a
  digit, or an id of six or more hex characters, is replaced by `<*>`.
- **Unusual lines.** A pattern on 1% of the lines or fewer, or a pattern with an error word on 10%
  of the lines or fewer.
- **Unusual values.** In a `<*>` that holds six values or fewer, where one value is on 80% or more
  of the pattern's lines, a value on 2% of its lines or fewer.
- **Zeros.** A zero or a negative where every other value is 10 or more.
- **Long lines.** Cut at 300 characters, and the envelope says how many characters it cut.

### JSON

- **Unusual rows.** When 75% or more of the rows share a value, the rows whose own value is on 10%
  of the rows or fewer.
- **Unusual keys.** Rows that have a key only 10% of rows have, or lack a key 90% have.
- **Unusual types.** A value of another type than the rest of its field.
- **How many are listed.** Up to 25 unusual rows per list, and fewer when the budget is tight. The
  envelope gives the total and says how many it lists.
- **Long values.** Cut at 60 characters.

### Page snapshots and other outlines

- **Groups.** A node with five or more children, 60% or more of whose first lines follow one
  pattern, is a group of similar items. Quoted text also counts as `<*>`.
- **Unusual items.** Items that hold a line or a value found in 20% of the items or fewer.
- **Error lines.** A line with an error word, when 10% of the items or fewer have one.
- **Zeros.** A zero or a negative where every other value is 10 or more.

<!-- /grid -->

Because the rules are fixed, the envelope finds the kinds of problem they describe and can miss
others. The checking program shows that what an envelope says is true, but it cannot show that the
envelope found everything. We planted the problems in our test outputs ourselves, knowing the
rules, so the test tasks are likely kinder to the envelope than real outputs are.

The $0.00 invoice described below was a problem that no rule covered until we added the rule for
zeros, and on a real Hadoop server log, whose problems were labelled by the people who published
it, only 10 of 20 questions could be answered from the envelope alone. This is why, when the
envelope finds nothing unusual, it lists the checks it ran and says that they do not prove there is
no problem.

## Other measurements

### Changing one section at a time

We changed one section of the envelope at a time and counted how many questions could still be
answered from the envelope alone. The `anomalies:` section made the biggest difference.

| Change to the envelope | Effect |
|---|---|
| For JSON, list every item that differs from the rest, where simpler rules pick out only some | 12 of 12 planted problems found, up from 9 or 10 |
| Copy the items that contain words from the tool call | 5 to 13 more questions about one item answered |
| Copy more example items | Almost no more questions answered, for 65 to 200 more tokens |
| Allow 500 tokens where the default is 2,000 | Half as many counting questions about logs answered |

### A missed answer and what we changed

In one task, an accessibility snapshot listed invoices, and one of them had an amount of $0.00. In
an early run, the envelope's `anomalies:` section said "none", and Sonnet answered that nothing was
wrong, even though it opened the file. We made two changes. The envelope now flags a number far
from the rest, such as a zero among amounts between 20 and 900, and when it finds nothing, it lists
the checks it ran. The task came in both sizes, so there were two such tasks.

| The invoice with an amount of $0.00 | Before the changes | After |
|---|---|---|
| Shown in the envelope | 0 of 2 tasks | 2 of 2 tasks |
| Found by Haiku | 2 of 2 runs | 4 of 4 runs |
| Found by Sonnet | 1 of 2 runs | 2 of 2 runs |

Before the changes, Haiku found the invoice by searching the saved file. After the changes, neither
model reported a problem in any of the 24 runs where the output had none.

### How often the model opens the full output

With the envelope, the model does not need the saved file to answer these questions, but it often
opens it anyway. Without the envelope, it opens the file for each of the 52 large outputs, because
it only has a preview. Adding a sentence to the banner that says every count is exact made Haiku
open the file less often, and it lost no answers.

<!-- chart: paired | Runs that opened the full output -->

| Runs that opened the full output | With the envelope | Without |
|---|---|---|
| Haiku, banner without the sentence | 70 of 104 | 52 of 104 |
| Haiku, banner with the sentence | 51 of 104 | 52 of 104 |
| Sonnet, banner without the sentence | 53 of 104 | 52 of 104 |

Opening the file less often hardly changed Haiku's context, because most of these reads are small
searches that add about 1,000 tokens.

When the model opened the file, it mostly ran its own searches to check what the envelope had said.
For example, after the envelope had counted the hidden cards in a Figma file, the model counted
them again with `grep`. It used line numbers from the envelope in 12 to 27% of its reads, and it
seldom ran the commands in `get more:`.

<!-- chart: stacked | What the model's reads of the saved file did -->

| What the read did | Sonnet, 88 reads | Haiku, 113 reads |
|---|---|---|
| Ran a command from `get more:` | 0% | 4% |
| Used line numbers from the envelope | 27% | 12% |
| Ran its own search | 72% | 81% |
| Read the whole file | 1% | 3% |

### Other versions of the envelope

We compared the final version's base with four other versions on Haiku, and none did clearly
better.

<!-- more: Show the five versions and how each did -->

All five versions are built by the same code. The base version is the final version before the two
changes for the $0.00 invoice and the banner sentence. The others change it in one way each:

- The version with an example item also copies one ordinary item.
- The shorter version has a shorter `shape:` section and copies no items.
- The version with a command per group also gives a ready-made command for every group of similar
  items.

| Version | Right, of 104 | Tokens saved per run | Opened the file, of 104 |
|---|---|---|---|
| Base version | 104 | 6,693 | 75 |
| With an example item | 104 | 6,656 | 75 |
| Shorter | 103 | 5,937 | 87 |
| With a command per group | 104 | 5,973 | 77 |
| Without the envelope | 101 | | 52 |

In an earlier run, we also tried a fifth version, which copies the first and last items of the
output where the base version copies the items the tool call names. In that run, it answered all 104
tasks correctly and saved 7,390 tokens per run, against 6,688 for the base version, but it opened
the file in 87 runs against 72. The shorter version made Haiku open the file more often, so it saved
less than the base version. The differences were small, so we kept the base version.

<!-- /more -->

## What is not settled

- Sonnet ran the final version on only 40 tasks, which is too few to rule out a drop in correct
  answers of more than 3 points.
- Without the envelope, Claude Code answers 96 to 99% of our test tasks correctly, so these tasks
  show a loss more easily than a gain.
- We ran Haiku on 59 real tasks from MCP-Atlas, a benchmark of tasks that use MCP tools, by
  replaying the tool outputs recorded in it. In about half the runs, the model's tool call differed
  from the recorded one and the replay returned a smaller output, so the hook had nothing to
  replace. The table below counts only the runs where the hook did replace an output with the base
  version. In those runs, the context was 3,788 tokens smaller and the cost 3% lower.

| Haiku on MCP-Atlas | With the envelope | Without |
|---|---|---|
| Answers right | 39 of 59 | 39 of 59 |
| Opened the full output | 47 of 59 | 12 of 59 |

- For JSON, the envelope does not yet flag a zero among numbers that are all 10 or more, as it does
  for logs and page snapshots.
- We have not yet tested long sessions, where the model asks several questions about one output.

## Next

1. Make the banner sentence that says every count is exact part of the default banner. Today it has
   to be turned on.
2. Run Sonnet on the MCP-Atlas tasks, and test long sessions.

## How we tested

<!-- more: Headless Claude Code with Haiku and Sonnet, about $43 of model runs in all -->

The model runs used headless Claude Code (`claude -p`) with Haiku and with Sonnet, and cost about
$43 in all. Token counts and costs come from the API's own figures. The 95% ranges for correct
answers use Newcombe's method for paired results, and those for tokens and cost use the bootstrap.
The checking program runs without a model, so it costs nothing, and it ran on every version of the
envelope before any model saw it. The example envelopes on this page were made by the hook's own
code.

<!-- /more -->

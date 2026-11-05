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
envelope on the same tasks:

- Haiku on all 104 test tasks got 104 right with the envelope and 100 without it. With the
  envelope, the context was 6,158 tokens smaller per run, and each run cost 25% less.
- Haiku on the 40 "what is wrong" tasks, each run twice, got 80 of 80 right with the envelope and
  72 without it. With the envelope, the context was 7,267 tokens smaller per run, and each run cost
  29% less.
- Sonnet on the 40 "what is wrong" tasks got 40 right with the envelope and 39 without it. With the
  envelope, the context was 8,164 tokens smaller per run, and each run cost 26% less.

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
within Claude Code's limit, so without the envelope the model holds all of it. There the envelope
saves about 9,000 tokens per run, but the run takes about 3 seconds longer, because the model often
opens the full output as well. A large output (about 19,000 to 70,000 tokens) is over the limit, so
without the envelope the model has to search the saved file. There the envelope saves about 3,000
tokens per run, and the run is about 9 seconds faster.

## What the envelope contains

The envelope has four parts:

1. A description of the output with exact counts, such as how many pods are in each state, or how
   many log lines follow each pattern.
2. The rows or lines that do not fit the pattern, each with its line number or path. Examples are a
   failed pod among running ones, an error that appears in only a few lines of a long log, and an
   amount of $0.00 among amounts of 20 to 900. When the envelope finds none, it lists the checks it
   ran and says there may be problems those checks do not catch.
3. A few rows copied exactly from the output, chosen because they contain words from the tool call.
4. Line numbers and ready commands for reading the rest of the saved file.

A banner above the envelope says where the full output is saved. It also says that every count and
value in the envelope is exact and was worked out over the whole output, and that the model should
open the file only for what the envelope does not show.

The hook builds envelopes for JSON, logs, indented outlines such as accessibility snapshots, XML,
web pages and source code. [The envelope](https://claude.ai/artifact/BZNhBgeCmSDnquEMcnvBkj) page
shows an example of each.

## What we learned along the way

**Everything the envelope says is true.** We wrote a checker that shares no code with the code that
builds the envelope. It counts every number again against the full output, compares every quoted
line with the original, and runs every command the envelope suggests. Across 251 test outputs and
every version of the envelope we tried, the checker found no false statement.

**The list of rows that do not fit matters most.** We changed one part of the envelope at a time and
used the checker to count how many tasks the envelope answers on its own. The list of rows that do
not fit the pattern made the biggest difference. Showing the rows that contain words from the tool
call made 5 to 13 more lookups answerable. Adding more example rows answered almost nothing more,
and cost 65 to 200 tokens.

**One wrong answer led to two changes.** In an early run, Sonnet missed the invoice with an amount
of $0.00. The envelope had said "anomalies: none", and Sonnet answered "none" even after opening the
file. We changed the envelope in two ways. It now flags a number far from the rest, such as a zero
among amounts of 20 to 900. When it finds nothing, it now lists the checks it ran and says there may
be problems they do not catch. After these changes, Haiku and Sonnet found the $0.00 invoice in all
six runs where it appeared. In the 24 runs where nothing was wrong, neither model reported a problem.

**The model often opens the full output anyway.** With the envelope and the earlier banner, Haiku
opened the saved file in 70 of 104 runs and Sonnet in 53 of 104, often when the answer was already
in the envelope. Most of the time it ran its own search to check what the envelope said. For
example, after the envelope had counted the hidden cards in a Figma file, the model counted them
again with `grep`. It used the envelope's line numbers in 12 to 25% of its calls, but it almost
never ran the commands the envelope suggested (Sonnet never did, and Haiku did in 4% of its calls).
When we added the sentence that says every count is exact, Haiku opened the file in 51 of 104 runs
instead of 70, and lost no answers. Its context hardly changed, because most of these checks are
small searches that add about 1,000 tokens.

**How the envelope is built barely changes the result.** Besides the final version, we tried four
others on Haiku: one with an extra example row, a shorter one with no example rows, one with a ready
command for every group of rows, and one that shows the first and last rows of the output. All of
them kept Haiku's answers, and they saved between 5,900 and 7,400 tokens per run. None did clearly
better than the final version. The shorter one made Haiku open the file more often, so it saved
less.

## What is not settled

- Sonnet has had only 40 runs of the final version, which is too few to rule out a fall in answers
  of more than 3 points.
- Without the envelope, Claude Code gets 96 to 99% of the test tasks right, so these tasks show a
  loss more easily than a gain.
- We also ran Haiku on 59 real tasks from the MCP-Atlas benchmark, which we replay from recorded
  tool calls. In about half the runs, the replay returned a smaller output than the recorded one,
  so the envelope had nothing to replace. In the runs where the envelope was used, Haiku answered 39
  of 59 with an earlier version of the envelope, the same number as without it, and its context was
  3,788 tokens smaller.
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
over it. Context is the size of the model's input on its last request, and cost is what the API
charged; both come from the API's own counts. The model runs cost about $43 in all.

Before any model run, the checker described above checks every envelope, without a model.

The numbers come from these reports in `results/`:

- The final version on Haiku over the 104 test tasks: `dials-haiku-banner.md` (the `exact` setting).
- The final version on the 40 "what is wrong" tasks: `dials-haiku-fixes.md` and
  `dials-sonnet-fixes.md`.
- Sonnet on an earlier version: `dials-sonnet-synthetic.md`.
- The other versions of the envelope: `dials-haiku-synthetic.md` and `dials-haiku-patterns.md`.
- The MCP-Atlas tasks: `dials-haiku-atlas.md`.
- The checker: `l1-*.md` and `sweep-*.md`.
- How the model opens the full output: the transcripts of `dials-haiku-patterns.md` and
  `dials-sonnet-synthetic.md`.

The notes we wrote after each run, in order, are in git history up to commit `0ab11f7`.

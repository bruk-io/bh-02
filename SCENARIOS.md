# Scenarios (v2)

The test material for v2. In v1, each task had one tool that returned the same payload whatever the
model asked, one question, and a problem planted as one odd row or line by people who knew the
heuristics. Claude Code without the hook got 96 to 99% of those tasks right, so they could show a
loss but hardly a gain, and the problems were the kind the rules look for. v2 replaces them with
scenarios.

## A scenario

- **A world.** A seeded, consistent state built by a family's generator from a seed and a
  difficulty setting: frozen dataclasses (services, deploys, pods, requests) or files on disk (a
  repository with its history). The same seed always builds the same world.
- **Tools that query it.** Each tool is a function of the world and the call's arguments. A broad
  call returns a lot and a filtered call returns less, the same arguments always return the same
  output, and every tool agrees with every other. Tools are served as MCP tools (FastMCP) or are
  real commands (`pytest`, `git`, `grep`) run on the files the world wrote. Any call gets a true
  answer, so no session sees an output that does not fit the world, which was the MCP-Atlas replay's
  problem.
- **A task.** What a developer would ask, such as "Why have checkout requests been failing since
  14:00?", with follow-up questions for session runs.
- **A truth.** Worked out from the world, never written by hand, and scored claim by claim with the
  scorers in `evals/truth.py` (`Claims`, `Items`, `Number`, `Exact`, `Absent`).

## Families

| Family | World | Tools | Example tasks |
|---|---|---|---|
| Code and tests (first) | A generated Python package with tests and a git history, one commit of which brings in a seeded regression | real `pytest`, `git log`, `git show`, `grep`, file reads, through Bash | Which tests fail, and why. Which commit broke them. Every caller of a changed function |
| Incident triage | Services with deploys, pods, request logs, metrics and traces, one deploy of which breaks something | MCP: `list_pods`, `get_logs`, `get_metrics`, `list_deploys`, `get_trace` | Which deploy broke checkout, and when. How many requests failed. Which pods restarted |
| Browser QA (later) | A generated web app's pages and requests | MCP: an accessibility snapshot, network and console logs | Why the Pay button is disabled for some invoices |
| Data and APIs (later) | Accounts, invoices and payments | MCP: paginated JSON endpoints, a CSV export | Which accounts were billed twice last month |

Code and tests comes first because it is what Claude Code users meet most, and its outputs are real:
the generator writes the repository, and the tools are the real commands. Its truth is known by
construction (which commit broke which tests) and confirmed by running the tests when the world is
built.

## The code-and-tests family, as built

`scenarios/code.py` builds a world from a seed and a size (M or L): rule modules (one or two of
them big, so reading a whole file makes a large output), totals modules that call the rules, tests
with cases below, at and above each threshold, and a git history with one regression commit. Its
five tasks, each with the commands its answer usually needs:

| Task | What it asks | Commands | Truth |
|---|---|---|---|
| failing | every failing test, by pytest id | `./run-tests`, `./run-tests -v` | the tests the regression breaks, worked out from the rules and confirmed by running them |
| commit | the commit that broke them | `git log`, `git log -p`, `git log --stat` | the regression's hash (any 7 or more characters of it) |
| callers | the functions that call the broken rule | `grep -rn` | from the totals modules' calls; a control, since its outputs are small |
| lookup | a rule's threshold, read from the code | `cat` or `sed -n '1,400p'` of the big module | the constant |
| edit | add a keyword-only parameter to a rule | `cat` of the big module | checked with `ast`: the parameter is there, and nothing else changed |

`./lab scenarios --size M` (or L) builds five open seeds and runs layer 1 on every command's real
output (`results/scenarios-l1-code-M.md` and `-L.md`). No fold stated anything false. The
envelopes name every failing test; they never point to the breaking commit in `git log -p`, where
the regression is a changed operator in a diff that no rule sees; and before the fix below, a whole
file read with `cat` folded as a log, with no definitions in it.

The fix, found on open seeds: the hook now folds a Bash command that prints a whole file from its
first line (`cat F`, `head F`, `sed -n '1,Np' F`) as code when the file's extension names a
language, so the envelope lists the definitions with their line numbers. Edits then always find
their start in the envelope. A view that starts further in is left as it was, since its line
numbers are not the file's. Lookups mostly still need a fetch: the thresholds are module constants,
which the code envelope does not list.

## The pilot on Haiku, without the hook

`./lab scenarios-l2 --size M L --seeds 5 --conditions native --reps 3`
(`results/scenarios-pilot-haiku.md`): 150 runs, $0.49. Claude Code alone got all 150 right, every
task kind at both sizes, so none of the five templates is in the 20 to 80% band, and none can show
a difference the hook makes.

The reason is how the model works with a shell. It keeps outputs small itself: it runs the tests
with `-q -rfE` or through `tail`, reads history with `git log --oneline | head -30`, finds a
function with Grep and reads a file whole only to edit it. The median run carried 764 tokens of
tool output; only 18 of 150 runs saw an output over 2,000 tokens, and 15 of those were file reads
for an edit (Read, or `cat -n`, which the hook's whole-file rule does not take, since its line
numbers are part of each line). The median final context, 36,500 tokens, is almost all Claude
Code's own instructions and tools.

So in this family the hook has little to act on. Large outputs come where the model cannot narrow
the call: an MCP tool that returns everything it has, a file read whole to edit it, a question
over a whole output. The next templates go there:

- the incident-triage family, whose MCP tools return whole pod lists, logs and traces, as many real
  MCP servers do;
- code questions that need a whole output: counts and lists over a big module, or two files that
  must agree (a constant and its docstring), which a grep cannot narrow;
- problems no rule sees (a test shadowed by another of the same name, which pytest silently skips).

## The mix, from real sessions

One real session so far (`results/v1-survey.md`, this research's own): 84 of its 2,364 tool results
were over the hook's threshold, and 64 of those were file views (Bash `sed -n`, `cat` and `head`,
and the Read tool), at 2,000 to 9,000 tokens. Claude Code cuts long Bash output and pages long
files, so outputs past 12,500 tokens come from MCP tools, which it saves to a file.

So the code-and-tests family leans on reading files (source, docs, generated reports) and acting on
what was read: a question about a file, then an edit to it, which needs the exact text and is where
folding a file view could cost more than it saves. Test runs, searches and git history come next,
at the sizes the survey found. Incident triage covers the larger MCP outputs. One session by one
agent is not a mix to settle on: other people's sessions come next.

## Difficulty

Every task template states each of these, so tasks can be chosen where Claude Code without the hook
often fails:

| Setting | Values |
|---|---|
| Where the answer is | one item; several items; spread over two outputs; a count over a whole output |
| Who can see it | a rule sees it; no rule sees it (below) |
| Decoys | none; a few; a flood of harmless lines that look like problems, as in the HDFS log |
| Size | under the hook's 2,000-token threshold; within Claude Code's limit; over it; far over it |
| Mess | clean; messy (multi-line stack traces, JSON inside log lines, colour codes, partial records) |

## Kinds of problem

The kinds are listed here before any heuristic changes for v2, and generators are written without
reading `compressors/`, so the problems are not shaped by the rules.

- **Seen by a rule:** a rare value; a line or a value with an error word; a number far from the
  rest; a line pattern few lines follow; a key few rows have or lack.
- **Seen by no rule:**
  - a duplicate id;
  - timestamps out of order;
  - a gap in a sequence (a minute with no log lines, a missing invoice number);
  - totals that do not add up;
  - two outputs that disagree (a pod listed as Running whose logs show it crashing);
  - a value that is plausible alone and wrong in its context (a price in the wrong currency);
  - stale data (one record far older than the rest).

The second list is the failure-mode set: it measures what the model does when the envelope cannot
show the problem, and whether the banner that says counts are exact makes it worse.

## What each run records

Whether the answer is right, claim by claim; final context; every input token over the run, cached
or not; cost; time; every tool call with its arguments and the size of its output; whether the
model opened the saved file, and whether the answer was already in the envelope at the time (the
checker knows); and for a session, the same summed over its questions.

## Choosing tasks

A pilot runs Claude Code without the hook on the open seeds. A template stays when Claude Code
alone gets it right between 20% and 80% of the time, so a change in either direction can show.
Choosing happens on the open seeds only.

## Sealing

The numbers we report come from tasks nobody tuned against, chosen before the tuning, and run once
per version of the envelope.

1. **Two sets of seeds.** A family's open seeds are the integers 0, 1, 2 and so on, for
   building, tuning and piloting. Its sealed seeds are derived from a key with HMAC-SHA256, per
   family and per numbered set. Without the key, nobody reading the repository can build the sealed
   worlds.
2. **A key outside the repository.** `./lab seal init` makes a random key in
   `~/.config/tool-output-lab/seal.key` (readable by its owner only), or it is given in
   `TOOL_OUTPUT_LAB_SEAL_KEY`. The repository holds only the key's SHA-256, in `scenarios/seal.json`,
   committed before any sealed world is built. `./lab seal verify` checks that the key on this
   machine is the committed one.
3. **A ledger.** Building a sealed set, and every sealed run, adds a line to
   `results/sealed-ledger.jsonl`: the date, the family, the set, and for a run the version of the
   envelope code (a hash of the committed git trees of `compressors/` and the hook). A sealed run is
   refused while that code has uncommitted changes, since the version would name code that did not
   run.
4. **Each set is run once.** A sealed run takes the lowest set no run has used. Every setting to
   compare (Claude Code without the hook, and each version of the envelope) goes into that one run,
   so they are paired on the same tasks. Its results may then be read in full, and the next version
   is scored on the next set.
5. **Revealing.** When the work is published, the key can be published too. Anyone can then check
   its SHA-256 against the commitment and rebuild every sealed task.

The seal guards against tuning on the test set by accident, and against choosing the test set after
seeing results. It does not stop someone who has the key from looking on purpose; the ledger makes
that visible, since every build of a sealed set leaves a line.

The key must outlive this machine: a cloud session's container is discarded, and its key with it.
A key lost before any sealed run costs nothing, since a new key is committed in its place and the
ledger records the change. A key lost after a run keeps that run's results but cannot rebuild its
tasks.

## Libraries, on Python 3.15

FastMCP 4.1 serves the tools (its in-memory client also tests them). Faker 40 or Mimesis 22, seeded
from the world's seed, make the surface values (names, ids, addresses, timestamps). Hypothesis
works up to 6.149; its newer releases have no 3.15 build. jsf fails to generate on 3.15, so
schema-shaped records come from polyfactory or the generators themselves.

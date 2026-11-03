# Findings

The running summary. Each entry names the result file or sample it rests on. Numbers come from
files in this folder, not from memory. Since 2026-11-03 the target is Claude Code: the hooks in
`claude_code/` and headless `claude -p` runs against native Claude Code.

## Corrections after review 1 (`REVIEW-1.md`)

Four reviewers checked these findings against the result files. What they corrected:

- **K1. Every A/B result here is indicative, not a verdict.** Cells had 13 or 14 runs (one run is
  7 points; 13/14 has a 95% interval of 68% to 99%), seeds at a fixed position are near-replicates,
  and no interval was computed. The kill criteria could not be judged at these sizes. Layer 2
  (`evals/l2.py`) now reports Wilson and paired bootstrap intervals and applies the criteria to them.
- **K2. "Input tokens summed over requests" mostly counted turns** (about 29k + 39k per turn, R2 of
  0.90 to 0.94): "a third fewer input tokens" (1, 13, 19) means fewer round trips, not a smaller
  context. The cache breakdown behind 19 was not recorded. Layer 2 records usage per request by
  cache class and the final context's size.
- **K3. The A/B JSON and log needles gave themselves away:** the planted pod was named `needle-...`
  among `web-...` pods (29 of 32 Haiku and 7 of 8 Sonnet JSON answers cite the name), and the log
  needle held the word `needle-`. JSON accuracy in A/B 1 and 3 is inflated in both conditions.
- **K4. The tree prompts named the planted kinds** ("an invoice that cannot be paid or an error",
  "a hidden layer or a different component") while the JSON and log prompts were generic: A/B 2
  and the tree cells of A/B 3 tell the native condition what to look for. Prompts are now generic.
- **K5. Entry 15:** Claude recovered lookups from the saved file only in the 500-item runs; at 50
  items the target was in the fold.
- **K6. Entry 18:** the fold used more tokens than native in 4 of 6 Sonnet tree cells (5 of 13
  overall), not two, and folded trees cost more ($0.635 against $0.600): by the second kill
  criterion, folding spilled trees fails with Sonnet (indicatively).
- **K7. Entry 24:** 18 of 20 comprehension runs were right, not 20: both fold-condition answers to
  the Action question missed `_ChoicesPseudoAction` (a nested class) and passed only because the
  scorer took recall 0.9 as correct. The scorer read recall only, so listing every name would also
  have passed; and with native at ceiling, "adds nothing" could not have shown a gain.
- **K8. Entries 28 to 31 (layer 1):** the budget was not an enforced invariant then (PyPI folds ran
  3.0k to 3.4k tokens against 2,000; logs, code and long strings ignored it, R4); counts passed on
  any token equal to the number, line numbers included (code at 2,000 was 4/17, not 7/17); and
  every planted anomaly was a kind the fold has a rule for, with k under its cap, so "spot and
  absent are sufficient everywhere" held by construction. Restated: for the anomaly kinds the fold
  has rules for, the planted item is in view; quiet anomalies (no rule) are lost at M and L in
  every format; past the cap, trees now say how many more stand out. Current numbers: `l1-15-*.md`.

Entries below keep their original wording; a tag such as (K3) marks one these corrections qualify.

## What Claude Code already does (docs for v2.1.317, read 2026-11-03)

Most of the source document's ideas are already in Claude Code, in their simplest form:

| Idea | Claude Code |
|---|---|
| Spill to a file and recover by pointer | Bash output over ~30k chars: saved to the session folder, Claude gets the path and the first 2,000 chars. MCP text over 50k chars, or over `MAX_MCP_OUTPUT_TOKENS` (25k): saved to a file, Claude gets a notice with the path and how to read it. Read: pages of 25k tokens with a `PARTIAL view` notice |
| HTML to markdown and a small-model extractor | WebFetch does both, lossy by design |
| Head and tail on failure | A failing Bash command gets a head-and-tail excerpt up to 10k chars |
| Structure-aware folding (JSON, logs, trees, code) | Nothing: below the thresholds output arrives whole; above, the preview is the head only |

## Where a hook can act (probes in the scratchpad, 2026-11-03)

- A `PostToolUse` hook may replace any tool's output with `updatedToolOutput`; for MCP tools a
  plain string is accepted. Claude Code spills first: for an MCP result over its limits the hook
  sees Claude Code's notice (with the file path), not the result. The hook reads that file and
  folds it; for a result under the limits it saves the raw itself. Either way Claude gets the fold
  and a path, and reads the rest with jq, sed, grep or python, as it already does with spills.
- `Read` reaches `PostToolUse` as `{type, file: {content, startLine, numLines, totalLines}}`, and
  Claude Code numbers the lines from `startLine` itself, so a folded body there would carry wrong
  line numbers. Code folding therefore lives in `PreToolUse`: the gate turns away the first
  whole-file Read of a large source file with the outline as the reason (it reaches Claude as a
  hook error), and Claude reads exact ranges with offset and limit, numbered right by Read.
- Headless `claude -p` runs from this container with no API key, and its stream gives cost,
  tokens, turns and every tool call: the model stages run on Claude Code itself.

## A/B 1: JSON and logs, Haiku (`ab-1-haiku.md`, 56 runs, $0.36)

Native Claude Code against the fold hook (budget 2,000 tokens, folding inline and spilled results).
Small = 50 pods or 200 log lines (~3k tokens, inline natively); large = 500 pods or 2,000 lines
(~30k tokens, spilled natively).

| | runs | correct | cost | median input tokens | median calls | median time |
|---|---|---|---|---|---|---|
| large, native | 14 | 13 | $0.103 | 280k | 4 | 20.9s |
| large, fold | 14 | 13 | $0.089 | 187k | 2 | 13.7s |
| small, native | 14 | 14 | $0.084 | 142k | 1 | 9.7s |
| small, fold | 14 | 12 | $0.085 | 186k | 2 | 14.3s |

1. (K1, K2, K3) **Where Claude Code spills, the fold wins:** a third fewer input tokens, a third less time,
   half the tool calls, equal accuracy. It replaces a head-only preview that sent Claude exploring.
2. **Below the spill threshold it loses:** Claude opened the saved raw file in every folded run,
   apparently to check the fold, which costs a round trip the inline result did not need.
3. **The native baseline is strong.** On the large payloads Claude counted values in the spilled
   file with python and found the anomaly itself (4 calls instead of 2).
4. **The fold lost the quiet log line** (no error word) on the small log, 0/2 against 2/2 native,
   even though Claude opened the file. The heuristic's known blind spot costs answers.
5. So for Claude Code: fold only what Claude Code spills (`TOOL_OUTPUT_LAB_MODE=spilled-only`), or
   use a budget near its thresholds, not 2,000 tokens.

## Code: the Read gate (probe, `scratchpad/cc-probe`)

6. Haiku, asked a question about a 2,086-line file, paged it itself (50 lines, a Grep, 10 lines;
   $0.006): the gate never fires. It only acts on whole-file reads, which corpus 1's Opus agent
   made and Haiku does not.
7. Asked to read the whole file, Haiku got the outline (4.6k tokens for a 20k-token file, every
   method signature with its real line number) and then did what the prompt said: read it whole.
   The gate added cost there.
8. **Sonnet does not read whole files either, even for an overview.** Asked a targeted question it
   grepped and read 45 lines ($0.10). Asked for an overview of the whole file, it built its own
   outline with `grep -nE '^(class |def |async def |    def ...)'`, then read three ranges ($0.15).
   Current models already do "outline first, then exact ranges" with the shell, so the gate would
   rarely fire, and when it did it would duplicate what the model was about to do. Corpus 1's
   whole-file reads came from a prompt that told the agent to read the files.
9. The ast-grep outline is still better than a grep outline (multi-line signatures, docstrings,
   nesting, every language). That makes it a tool to offer (`outline FILE`), not a gate to impose.

## Tree folding: code, XML, accessibility outlines (`compressors/tree.py`, `compressors/code.py`)

One fold for anything that is a tree of line ranges. Outline first (every top-level header), then
open nodes while the budget allows: stand-out siblings first, then containers (a class, an
element: opening them shows their children's headers), then bodies; shallower and cheaper first.
A node with many children opens partly (as many as fit in half the room, and the last), with each
hidden run as one marker naming its lines. Siblings that stand out are kept in view and opened: a
small subtree whose shape (numbers blanked) is rare among siblings that mostly share one, or that
holds a query term few siblings share. Code comes from ast-grep (any node with a body, plus large
literals), XML from expat (pretty-printed first when packed), outlines from indentation.

10. Ordering matters for code: opening by depth alone spent the budget on module-level function
   bodies, and 52 of `BaseEventLoop`'s 76 methods ended up behind one marker. Containers before
   bodies fixed it; at a quarter of the file's tokens every method signature shows.
11. A stand-out must open, not just show: the disabled invoice in a 500-item accessibility list was
   promoted but shown folded, hiding the `[disabled]` line it was promoted for.
12. Synthetic survival at budget 2,000 (no model), one seed, middle position: in a 500-card Figma
    page (~50k tokens folded to ~1.9k) a hidden layer and a different button variant survive; in a
    500-invoice accessibility snapshot (~21k -> ~1.8k) a disabled button and a failure alert
    survive. A plain lookup by name survives only when the tool call's arguments name it; otherwise
    Claude has to read the saved file. Full grid: `needle-4-trees.md`.

## A/B 2: accessibility snapshots and Figma metadata, Haiku (`ab-2-trees-haiku.md`, 48 runs, $0.33)

Same set-up as A/B 1, through the tree folds (the hook routed every snapshot to `outline` and every
Figma result to `xml`). Small = 50 invoices or cards (~2k and ~5k tokens, inline natively); large =
500 (~21k and ~50k tokens, spilled natively). Kinds: a disabled button, a failure alert and a lookup
by invoice; a hidden layer, a different button variant and a lookup by card name.

| | runs | correct | cost | median input tokens | median calls | median time |
|---|---|---|---|---|---|---|
| large, native | 12 | 12 | $0.097 | 302k | 4.5 | 16.1s |
| large, fold | 12 | 12 | $0.079 | 189k | 2 | 11.7s |
| small, native | 12 | 12 | $0.073 | 142k | 1 | 7.4s |
| small, fold | 12 | 12 | $0.078 | 190k | 2 | 14.9s |

13. (K1, K2, K4) **The same split as A/B 1:** on spilled results the fold saves 37% of input tokens, 19% of the
    cost and a quarter of the time, with no answer lost; on inline results it costs more and takes
    twice as long, because Claude opens the saved file anyway.
14. **Accessibility snapshots gain the most.** Natively, Claude explored a spilled 500-invoice
    snapshot in 6.5 calls and 27s; with the outline fold it answered in 2 calls and 9.5s.
15. (K5) **Lookups recover as designed.** The fold hid the asked-for invoice and card (the tool calls
    carry no query), and Claude grepped the saved file and answered correctly in every run.
16. **Claude opens the saved file in nearly every folded run**, even when the answer is in the fold.
    That one extra call is the fold's whole cost on small results. Whether a banner that says what
    the fold guarantees (for example, that every sibling that differs is shown) cuts it, without
    inviting misplaced trust, is untested.

## A/B 3: Sonnet, spilled-only mode, large cases (`ab-3-sonnet-spilled.md`, 26 runs, $2.66)

One seed per cell, so each cell is a single run: read the totals, not the cells.

| | runs | correct | cost | median input tokens | median time |
|---|---|---|---|---|---|
| native | 13 | 12 | $1.35 | 227k | 20.6s |
| fold | 13 | 12 | $1.31 | 183k | 18.3s |

17. **JSON and logs: the same clear win as with Haiku**, 4 calls down to 2 and about a third fewer
    input tokens in most cells.
18. (K6) **Trees: no win with Sonnet.** It explores a spilled snapshot or Figma file efficiently on its
    own (2 to 4 calls), and in two cells the fold used more tokens than native.
19. (K2) **20% fewer input tokens bought 3% of the cost.** Most input tokens are cache reads, which are
    cheap; Sonnet's cost is mostly cache writes and output. In Claude Code the fold's value is fewer
    calls, less time and slower context growth, more than money. Context growth itself is not yet
    measured (the harness sums tokens over requests; the size of the final context would show it).
20. Both conditions missed the quiet log line: with Sonnet that miss is not the fold's doing.

## The tool: `fold` (`compressors/cli.py`, `./lab fold`)

Since 2026-11-03 the deliverable is a general CLI; the Claude Code hooks are one consumer of it.
`fold FILE` or `COMMAND | fold` prints the shape of a text in a token budget, with markers that say
what they hide (a JSON path, or a line or character range) so `jq`, `sed -n` or Read with offset and
limit fetch exactly that. Code is detected by extension (or `--lang`) and folded through ast-grep;
everything else by content. `--query` keeps in view what holds the given words, `--as` overrides the
detection, `--save` writes the pretty-printed copy when the line numbers refer to one.

21. Examples from the stdlib and synthetic inputs: `json/decoder.py` ~3.2k -> ~0.7k tokens with every
    class and function header at its real line; 500 users ~6.9k -> ~150 tokens with the one
    suspended user in place and the status counts; a 5,000-line log ~40k -> ~60 tokens with its one
    error line; `subprocess.py` (3,300 lines) to ~5.4k tokens with every method signature.

## Needle survival for trees (`needle-4-trees.md`, 3 seeds, no model)

22. **Figma XML:** a hidden layer and a different button variant survive at every position and size
    (50 and 500 cards, ~20% of the tokens at 50 and ~4% at 500); a lookup by name survives with the
    query, and only partly without it, as designed.
23. **Accessibility outlines exposed a bug:** with 50 invoices (just over the budget) the disabled
    button and the alert were never kept (0%), while with 500 they always were. The list fit in
    full, so stand-outs were never computed (only partial openings did that), and the stand-out's
    longer line made it the last item "cheapest first" would open. Fixed: stand-outs are found
    whenever a node opens and open first (`test_a_stand_out_opens_first_even_when_its_list_opens_in_full`);
    21/21 cells now survive at both sizes. Rerun (`needle-5-standouts-open.md`): disabled button
    and alert 50% -> 100%, lookup with the query 79% -> 100% (43% without it, which needs the file);
    every JSON, log and Figma row unchanged.

## Comprehension A/B: `fold` named in CLAUDE.md, Sonnet (`comp-1-sonnet.md`, 20 runs, $1.61)

Five structural questions over large stdlib files (which methods of BaseEventLoop are async, which
Popen methods are defined in both platform branches, which classes subclass Action, which classes
define close and where, which top-level functions are cached), answers computed with `ast`. Both
conditions had `fold` on the PATH; only `fold` had a CLAUDE.md naming it.

24. (K7) **Every run was right in both conditions** (20/20, recall 1.00 and 0.98), in 1 or 2 tool calls.
25. **Claude computes structural answers rather than reading structure.** Of 25 tool calls, 10 were
    its own Python `ast` scripts, the same way the ground truth was computed, and most others were
    grep or awk one-liners. For a question with an exact answer that beats any outline.
26. **`fold` was used in 2 of 20 runs**, both told about it and both on the Popen question, as
    `fold subprocess.py --budget 6000 | grep ...`. Those were the most expensive cells (161k against
    89k input tokens, 2.5 calls against 1). It was never used when not named, and never on the other
    questions when named. (The report's "ran fold" column reads 0 for all rows: its detector looked
    for `"name": "Bash"` with a space, which the stream does not write. Counted from the sessions'
    transcripts instead; the detector is fixed and tested.)
27. So for code, with Sonnet: an outline tool adds nothing on questions that have exact answers.
    What is left untested is open-ended understanding (no exact answer, so a judge would be needed),
    and weaker models or harnesses with no shell, where Claude cannot write its own `ast` script.

## Layer 1 evals: 131 tasks, the fold alone (`l1-*.md`, see EVALS.md)

131 tasks over 8 formats (synthetic JSON, logs, accessibility snapshots and Figma XML at three
sizes; real Python and Rust source, the ISO 3166-2 XML and PyPI JSON) and 6 kinds (spot, absent,
look up, enumerate, count, locate), every answer computed by a program. Each is folded through the
`fold` interface with no query and, where the tool call would name it, with the query. Free: the
whole run takes about 15 seconds.

28. (K8) **No invariant has ever failed** (0 of 160 folds in every run): every fold accounts for every
    source line exactly once, and every JSON marker holds exactly the count it claims.
29. (K8) **Spot and absent are sufficient everywhere:** the planted anomaly is in view in every format,
    size and position, and no fold ever promoted something in a payload with nothing planted.
30. **Layer 1 found eleven problems in an afternoon**, each fixed with a test, which moved
    sufficiency from 109/160 to 128/160 at 2,000 tokens (139/160 at 6,000):
    - the count scorer itself demanded the number written out (`l1-2-count-scorer.md`);
    - only three stand-outs were ever promoted, so a fourth planted item was hidden (now ten);
    - a 7%-rare shape was not rare (5%); for trees, which have no summary counts, now 10%;
    - query terms under three characters were dropped (`NL`, `JP-13`); now matched as whole words;
    - the log fold kept a query term every line holds (`req`), drowning the asked-for line;
    - promotion took matches in order, not by how many query terms each matched;
    - real XML is sloppy: the ISO file has a bare `&`; parsed leniently, lines unchanged;
    - a 60-line XML comment and the DOCTYPE could not fold;
    - a query match deep in a subtree (entry 13 of 47) did not count, and a header match
      (`code="AD"`) weighed no more than `Ad` in other countries' place names;
    - the tightest JSON level still went over budget on PyPI JSON, and cut SHA-256 digests;
    - opening by cost, added for docstrings, left the biggest class last (`l1-9-ranks.md`).
31. (K8) **What remains insufficient is by design or by budget:** a lookup with no query has nothing to
    mark the asked-for item, so it needs the saved file (that is the recovery path layer 2
    measures); and a 20k-token source file's outline does not fit 2,000 tokens. At 6,000, code is
    13/17; a file that fits is passed through unchanged, so "on which line" cannot be read off it.
32. One budget-edge case: the fold's own cost estimate runs about 15% above what it renders, so the
    Netherlands' last group of 3 entries waits for 2,200 tokens instead of 2,000. To calibrate.

## P2: layer 2 on the eval tasks, Haiku (`l2-p2.md`, 712 runs, $4.93)

Every M and L task under every condition of its channel, twice: 52 MCP tasks a band (JSON, logs,
accessibility snapshots, Figma XML) under native, fold of spilled results (`fold`) and fold of all
results (`fold-all`); 22 file tasks (Python, Rust, the ISO XML, PyPI JSON) under native and
`lab-fold` named in CLAUDE.md (`fold-tool`). Haiku 5.5, headless Claude Code. Two repetitions, not
the planned three: stage 1 cost what was estimated ($2.47), and a third would have taken P2 to about
$7.40 against its $5. No run failed to answer and none ran out of turns. Accuracy intervals are
Newcombe's for paired proportions with McNemar's exact p; the others are a paired bootstrap.
Per-band and pooled tables: `l2-p2.md`; each repetition: `l2-p2-r1.md`, `l2-p2-r2.md`.

33. **The control holds, and it showed the first accuracy interval was too sure.** At M nothing
    spills, so `fold` is native plus a hook that never acts: final context, input and cost are
    unchanged (-1 token). Its accuracy differed in 4 pairs, all for `fold` and all on prompts that
    read two ways (38). The paired bootstrap put that at +4% [+1%, +8%], while McNemar's p is 0.125:
    with no losses to resample, a bootstrap cannot reach zero. The report now uses Newcombe's
    interval (+4% [-0%, +10%]); the thresholds are as set before the run. One consequence: 104
    pairs that all agree give about +-3.3 points, so this sample cannot show accuracy kept within
    3 points; a cell needs about 150 agreeing pairs for that.
34. **Folding spilled results (L) answers more, in fewer requests, and ends with a larger context.**
    `fold`: accuracy +7% [+1%, +14%] (8 pairs right only when folded, 1 only native, p = 0.04).
    Six of the eight are spot tasks on accessibility and Figma trees, where native answered "none"
    and the fold's stand-outs showed the anomaly. It saves 1.2 requests and 1.8 tool calls a run
    (5.9 to 4.8 requests), so summed input falls 44k a run, cost $0.0006 (about 9%) and time 1.8 s.
    But Haiku still reads the saved raw in 97 of 104 runs (native: 104 of 104), and the fold, about
    2k tokens, is larger than Claude Code's own preview, so the final context grows 800 tokens
    [+170, +1,280]. `fold-all` at L is the same: +6% [+0%, +12%], +750 tokens. By the final context
    it fails; by summed input it passes.
35. **Folding results under the spill threshold (M) shrinks the context and keeps answers, for an
    extra round trip.** `fold-all`: accuracy +1% [-2%, +5%], final context -7.1k [-9.5k, -6.8k]
    (JSON and logs -11k, trees -5k to -6k), cost -$0.0007. Haiku reads the raw in 96 of 104 runs,
    1.4 more requests, so summed input rises 42.5k and time 3.6 s. It passes by the final context
    and fails by summed input. A/B 1 had found more tokens and more time here, and two misses; the
    tokens and time agree, the misses do not recur.
36. **Haiku does not use a named fold tool.** With `lab-fold` described in CLAUDE.md, it ran it once
    in 44 runs and grepped instead. Accuracy is unchanged (no discordant pair), and the CLAUDE.md
    lines add 300 tokens to the final context: it fails. Sonnet did the same (24-27).
37. **Which reading of "input tokens" decides changes the verdict.** The kill criterion is "input
    tokens, recovery reads included, are not lower". The final context (what the context holds at
    the end, recovery reads included) and summed input (every token every request carried, mostly
    the cached ~45k base) disagree in both directions: at L folding cuts requests and so summed
    input while the final context grows; at M, the reverse. The verdict column uses the final
    context, chosen in R9 before any P2 run, and both are reported. Cost, which prices cached input,
    falls slightly in both. Which one matters (headroom in a long session, or spend and latency) is
    the owner's call, not the data's.
38. **The runs found task flaws.** Every enumerate prompt ends `ANSWER: <every name, separated by
    commas>`, even when it asks for codes or orders. For Andorra's subdivision codes Haiku listed
    the parishes' names under both conditions; for failed orders in logs it answered "none (the logs
    have no names)" in some runs and listed the orders in others. These tasks flip between runs
    whatever the condition: all four of the control's discordant pairs are among them. The quiet log
    anomaly asks to "name the order or request it concerns", and Haiku sometimes names the event.
    The prompts stay as they were for P2, so both repetitions saw the same ones; fixing them is for
    P3. The scorer refused `N7697` for `Card N7697`; fixed (an item may name the one candidate that
    holds it). Rescoring the saved answers changed 2 of 712, both Figma enumerate answers under
    `fold` that native also got right: before the fix they counted as two losses for folding.
39. **Caveats.** One model; two repetitions of the same tasks, which are not independent cases (52
    MCP tasks a band); synthetic payloads on the MCP channel; a file channel of 22 tasks. Per-format
    cells (26 pairs) are indicative.

## Where the design stands

| Piece | Evidence | Leaning |
|---|---|---|
| Fold MCP results Claude Code spilled | P2 (Haiku, 104 pairs): accuracy +7% [+1%, +14%], 1.2 fewer requests, -9% cost, -1.8 s, but the final context +800 tokens (34); A/B 1-3 indicative (K1) | keep; the default. Fails the final-context reading of the input criterion, passes the summed one |
| Fold MCP results under the spill threshold | P2: answers kept, final context -7.1k, but 1.4 more requests, +42k summed input, +3.6 s (35) | depends on which input reading the criterion means (37) |
| JSON folding with promotion | real MCP JSON to 13%; built anomaly kinds survive | keep |
| Line folding for logs | error words survive; quiet anomalies lost, and the loss costs answers | keep, with the gap stated |
| Tree folding for XML and accessibility trees | A/B 2 (Haiku): -37% tokens on spilled results; A/B 3 (Sonnet): no gain | keep for weaker models; Sonnet does as well alone |
| Read gate with ast-grep outlines | works, but Haiku and Sonnet page and grep on their own, even for overviews | drop |
| `fold` as a tool for code | comprehension A/B: Sonnet writes its own `ast` scripts; told about `fold`, it used it twice, at a cost. P2: Haiku ran it once in 44 runs (36) | no gain with Haiku or Sonnet on exact questions; untested on open-ended ones |

## Next

0. A decision for the owner: which reading of "input tokens" the kill criterion means, the final
   context, summed input or cost (37). It decides both fold modes.
1. P3 (Sonnet, the no-shell channel, edit tasks), with the enumerate instruction naming what is
   listed (38), and about 150 agreeing pairs a cell so a verdict can resolve 3 points (33).
2. At L the fold is larger than Claude Code's preview and Haiku reads the raw anyway (34): try a
   fold no larger than the preview, or a banner that says what the fold guarantees, to see whether
   it saves the read.
3. More than one task per cell: two repetitions of 52 tasks are not 104 independent cases.

## Earlier results (bh-02 corpus and synthetic grid, kept as recorded)

### How large outputs arise (agent corpus 1, `stats-agents-1.md`)

Corpus: six Claude Code sub-agents given real read-only tasks on this repo (test run, PyPI
dependency check, GitHub history via MCP, cordis source walk-through, git churn, ast-grep docs).
They were not told about the lab. 93 tool results, ~75k tokens. Sizes are what reached the model
after Claude Code's own limits; none of the results was large enough for Claude Code to spill it
to a file. The transcripts are in `corpus/transcripts-agents-1/` (gitignored).

E1. **An agent with a shell filters at the source on its own.** 37 of 52 Bash calls piped through
   head, tail, grep, sed or python, or redirected to a file. Asked to read raw HTML docs and PyPI
   JSON with curl, agents saved them to files (118 KB of HTML, 3.2 MB of JSON) and pulled out what
   they needed; neither payload entered context. The largest Bash result was 3.4k tokens.
E2. **What lands large is what the agent cannot filter or chose to read whole.** 10 results were
   over the 2,000-token budget and held about half the corpus's tokens: 5 whole-file `Read`s, 2 MCP
   JSON results (`list_commits`, `list_pull_requests`) and 3 Bash outputs.
E3. **`Read` must not be folded.** The 5 over-budget `Read`s were cordis source and its README,
   read by the agent whose task was to explain the code with file:line references. Folding
   `runtime.py` 8,610 -> 1,407 tokens would have removed the lines it cited. They are 20.7k of the
   33.3k over-budget tokens, so without them the saving falls from 31% to 14% of the corpus.
E4. **MCP JSON is the clear win:** 9,752 -> 1,270 tokens (13% kept) for the two results, with no
   filtering parameter the agent could have used instead (`list_commits` has `perPage` and
   `fields`, and the agent used both; the result was still 31k chars).
E5. **The `lines` branch barely helps on what agents run:** the 3 Bash results kept 81%, because
   the agents had already cut them to what they wanted.

### JSON folding on real MCP output

E6. `list_commits` (60 commits): ~7.7k -> ~1.1k tokens before fix E7, ~840 after.
E7. **Query terms from arguments add noise.** The call's `owner: "bruk-io"` gave the term `bruk`,
   which matched every commit by that author, so three arbitrary commits were promoted as
   "matches the query". The synthetic grid missed this because its arguments did not name the
   container. Fixed: a query term that matches more than 20% of an array's items is ignored
   (`_discriminating` in `json_fold.py`, test `test_a_query_term_most_items_share_promotes_nothing`);
   `list_commits` then folds to ~840 tokens instead of ~1,150.
E8. The banner's recovery example was generic (`$.items[10:20]`) when the root was an array. Fixed:
   the example is built from the first real fold marker.

### Needle survival (synthetic, no model)

Baseline: `needle-1-baseline.md` (3 seeds). After the CamelCase error fix:
`needle-2-camelcase-errors.md` (5 seeds).

E9. **JSON statistical promotion works for the kinds it was built for.** A rare value, a rare
   nested value, an error key only one item has, and a flipped boolean survive at every position
   and size (50 to 5,000 items), at about 2% of the raw tokens.
E10. **A numeric outlier is lost** (restarts 9999 among 0-3): high-cardinality numbers are not
   analysed. Survives only at the head or tail.
E11. **A query match survives only with the query on.** With the query off it is lost unless at the
   head or tail.
E12. **Logs: error words survive everywhere.** A quiet anomalous line (no error word) is lost unless
    at the head or tail; expected.
E13. **The last line of a stack trace was lost in the baseline** (33%): `\berror\b` does not match
    inside `ValueError`. Fixed by matching `...Error` and `...Exception` words: 100% in the second
    run, with no other cell changed.
E14. **The lines branch leaves most of the budget unused:** ~750 tokens out against a 2,000 budget,
    because head, tail and windows are fixed counts. Whether to spend the rest (and on what) is
    open; more head and tail would not help a needle in the middle.
E15. The second run predates fix E7, and shows the same noise: with the query on, the argument
    `namespace: "default"` matched every item and promoted the earliest ones, which is why the
    numeric outlier reads 33% (query on) against 29% (off). The third run
    (`needle-3-discriminating-terms.md`), after fix E7, reads 29% both ways, and JSON output falls
    from ~2% to ~1.4% of the raw tokens because the noise promotions are gone. Logs unchanged.


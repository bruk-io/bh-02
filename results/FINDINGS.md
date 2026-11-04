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
    falls slightly in both. **The owner's reading (2026-11-03): the final context.** So, with Haiku,
    folding spilled results is cut and folding results under the threshold is kept; the hook's
    default is now `inline`, which does the second only.
38. **The runs found task flaws.** Every enumerate prompt ends `ANSWER: <every name, separated by
    commas>`, even when it asks for codes or orders. For Andorra's subdivision codes Haiku listed
    the parishes' names under both conditions; for failed orders in logs it answered "none (the logs
    have no names)" in some runs and listed the orders in others. These tasks flip between runs
    whatever the condition: all four of the control's discordant pairs are among them. The quiet log
    anomaly asks to "name the order or request it concerns", and Haiku sometimes names the event.
    The prompts stay as they were for P2, so both repetitions saw the same ones. Fixed for P3: the
    instruction says "the item, as the question asks for it" (and "every item"), the log question
    asks for "the id of the order or request", and a planted log line counts as named by either id
    on it. Rescoring P2's answers with that truth changes none. The scorer refused `N7697` for `Card N7697`; fixed (an item may name the one candidate that
    holds it). Rescoring the saved answers changed 2 of 712, both Figma enumerate answers under
    `fold` that native also got right: before the fix they counted as two losses for folding.
39. **Caveats.** One model; two repetitions of the same tasks, which are not independent cases (52
    MCP tasks a band); synthetic payloads on the MCP channel; a file channel of 22 tasks. Per-format
    cells (26 pairs) are indicative.

## P3: Sonnet, the no-shell channel, edits (`l2-p3.md`, 230 runs, $24.69)

One repetition on Sonnet 5.5 under a $25 ceiling (`--max-cost`), with the fixed prompts (38), in four
stages: (a) M, native against `fold-inline`, the hook's default, all 52 MCP tasks; (b) L, native
against `fold`, spot and absent (20 tasks); (c) the 22 file tasks under native, `noshell` (Bash
disallowed) and `noshell-fold` (the same with the `fold` MCP tool, paired against `noshell`); (d)
five edit tasks, checked by `ast`, under native, `fold-tool`, `noshell` and `noshell-fold`. Sonnet
cost $0.08 to $0.13 a run, about 15 times Haiku, so cells are small and every verdict below is
indicative. No run failed to answer. Stage reports: `l2-p3-a.md` to `l2-p3-d.md`.

40. **Folding inline results (M) holds up on Sonnet, and saves more money than on Haiku.**
    `fold-inline`: 52 of 52 right under both conditions, final context -8.8k [-10.7k, -7.5k] (JSON
    and logs -11k, trees -7k to -7.5k), cost -20% ($0.129 to $0.103 a run), time +6 s. As with
    Haiku, Sonnet reads the saved raw in most runs (44 of 52) and needs 1.5 more tool calls. The
    verdict reads undecided only because 52 agreeing pairs leave the accuracy interval at +-7
    points (33); on the input criterion it passes clearly. With P2, the default holds on both models.
41. **Folding spills (L) does not grow Sonnet's context, and wins the same answers as Haiku's.**
    `fold`: 20 of 20 right against native's 18; both of native's misses are Figma spot tasks
    answered "none", as with Haiku (34). Final context -910 [-4.1k, +1.4k] (accessibility trees
    -11k, Figma +1.9k, JSON -1k, logs +0.9k), cost -21% ($0.127 to $0.100), 1.8 fewer tool calls,
    -3.8 s. 20 pairs: undecided, so the cut from P2 stands for Haiku and is open for Sonnet.
42. **Sonnet never used a fold tool.** Offered `lab-fold` through CLAUDE.md (5 edit runs) or the
    `fold` MCP tool with no shell (27 runs), it called neither once: 0 of 32. With nothing used,
    `noshell-fold` is `noshell` plus a tool description (+8 tokens of context), and `fold-tool` is
    native plus 280 tokens of CLAUDE.md. Both fail. Haiku did the same (36): as an offered tool,
    folding is not taken up by either model on these tasks; as a hook, it applies itself.
43. **Taking the shell away costs, and a fold tool does not buy it back.** File reads: 22 of 22 right
    natively, 21 of 22 with no shell (the one miss, the methods Popen defines in both platform
    branches, is missed with and without the fold tool), cost +26%. Edits: 20 of 20 right in every
    condition, but the two renames took 2 tool calls each with a shell against 6 to 14 without, and
    edits cost 16% to 21% more without a shell.
44. **The edit check needed one fix before it could be trusted.** In the Haiku smoke, all four renames
    were right and updated the docstring that names the method; the check counted that as a second
    change and failed them. Strings are now renamed back too, and edit rows keep their diff, so a
    fixed check rescored them (4 of 4). Haiku and Sonnet made every edit correctly: these five are
    too easy to show whether a fold helps or misleads an edit, only what each condition costs.
45. **The prompt fixes worked.** Andorra's subdivision codes, missed under every condition in P2
    because the instruction asked for names, were right in all three of P3's conditions.

## Forcing the fold on Bash (`l2-bash.md`, 312 Haiku runs, $2.01)

Offered as a tool, the fold went unused (36, 42); applied by the hook, it acted on every result.
So: apply it to the shell too. Eight headless runs (about 4 cents) tested the ways to do that in
Claude Code 2.1.317 before anything was built; the scripts are in this session's scratchpad.

46. **Only folding after the command runs works.** `CLAUDE_CODE_SHELL_PREFIX` receives each command
    as one string and also wraps every hook's command, so folding there would corrupt the JSON
    hooks return. A `PreToolUse` hook that rewrites the command (`cmd | lab-fold`) does change what
    Claude sees, but permission rules are checked against the rewritten command, and Claude Code's
    checker refuses its brace group: under an allowlist of `Bash(seq:*)` both attempts were denied,
    and a pipe runs the command in a subshell, so `cd` would no longer carry over. A `PostToolUse`
    hook that answers in Bash's own shape (`{stdout, stderr, interrupted, isImage, ...}`) replaces
    what Claude sees after the real command ran under the real checks; a plain string is ignored.
    Up to 30,000 characters the hook gets the whole stdout; above that, Claude Code saves the output
    and gives the first 30,000 characters and `persistedOutputPath`. The hook now folds Bash: its
    stdout in `inline` mode, the saved output too in `all`.
47. **On the bash channel** (the same 52 synthetic tasks a band, printed by `./<tool>`, paired against
    `bash-native`):
    - M, `fold-bash` (inline): final context -8.1k [-8.9k, -7.2k] (58.1k to 50.0k), cost -10%,
      but 1.5 more tool calls and +6 s (7.7 s to 13.6 s), as on the MCP channel (35). Accuracy
      49/52 against 52/52: -6% [-16%, +2%], 0 won and 3 lost (p = 0.25), undecided. The losses: two
      Figma spot tasks answered "none", and a JSON absent task where Haiku named "the 28 web pods
      with 3 restarts" as an anomaly. `fold-bash-all` at M: -7.8k, 51/52.
    - L, `fold-bash` is a control: the payload is saved and inline mode leaves it alone. The context
      is unchanged (+18 tokens), yet 5 pairs disagree (2 won, 3 lost), all spot tasks on trees:
      at L these flip from run to run by themselves (native 49/52). That is the noise floor the M
      losses have to be read against.
    - L, `fold-bash-all`: 51/52 against 49/52, but the final context grows 1.5k [+1.0k, +2.0k]:
      it fails, as folding spills did with Haiku on MCP (34).
48. **Forcing has a regress: it folds the model's own second look.** Besides the payloads, the hook
    folded 91 of the model's follow-up outputs, most within a few tokens of a payload's size: Haiku
    re-ran the command, with a pipe added, to see it whole, and got the fold again. The exemption
    covered only reads of the saved copy. This may be why the M losses happened, and this run cannot
    tell it from noise. Before a verdict on forcing: fold a command's output once per session (run
    it again and it comes whole), then re-run M (104 runs, about $0.70).

## Schema views of JSON, layer 1 (`l1-19-json-sample.md`, `l1-19-json-schema.md`, PLAN.md S1-S2)

After a fold, models query the raw (48 and the transcripts: grep, `jq` or a script in 89% of first
moves). So for data, the view now shows its schema rather than samples: each collection's fields
over every row (types, presence, value counts, ranges, string shapes), the rows that break the
pattern with their jq paths and names, keyed objects with their keys, collections inside rows, and
one ready `jq` query (`--view schema`; the sample fold is still the default). Layer 1 checks every
claim of a schema view against the data with its own path walker, and runs the query in `jq`.

49. **On the 47 JSON and PyPI folds, the schema view is sufficient for 41 against the sample fold's
    38, at half the size (median 219 tokens against 431), with 0 false claims.** It gains both
    quiet anomalies (the pod with 97 restarts, at M and L), which the sample fold loses, as one
    exception line in a view of about 170 tokens. Counts are stated outright (`"CrashLoopBackOff"
    20`) in 150 to 700 tokens where the sample fold took up to 1,500. One gain is spurious: for
    "which versions of click were first uploaded in 2023" the view lists all 65 versions as keys,
    and the scorer, which looks for the expected names, cannot tell that nothing says which are
    from 2023. Still insufficient in both views: lookups without the query (the answer is one row,
    which a schema does not show; the query line gets it), and 12 failures among 100 pods (12% is
    not rare under the 10% rule; the count is stated, the names are not).
50. **The claims check found a false statement before any model saw one.** PyPI's `core-metadata`
    is `false` in 65 files and an object in 63; the view opened the objects into their fields and
    said the key was "in 65 of 128". It now counts an opened object as the key being there, with
    the type `object`. The check's own blind spots, found by doctoring views in its tests: a query
    of the right shape that selects against the wrong value passed until the check also required
    the selected-against value to be the dominant one.

## Knobs and the cache (`sweep-*.md`, EVALS.md "The prompt cache")

51. **Sweeps over the same tasks, free.** The knobs (`compressors/config.py`) reach every entry point,
    with the defaults byte-identical to before (all 1,206 folds, both views). First sweeps, layer 1:
    the schema view at 500 tokens is sufficient for more JSON folds (35 of 47) than the sample fold
    at 1,000 (34), and keeps the quiet anomalies at every budget (3 of 3, against 0 or 1); raising
    `schema.rare` to 0.15 lists the 12 failures among 100 pods for 3 more tokens; raising the tree
    stand-out cap (`tree.max_promoted`) from 10 to 25, with `tree.rare_share` 0.2, takes trees from
    62 to 74 sufficient of 90 at the same median size, inventing nothing. The planted counts of 12
    and 20 exist to test that cap, so a cap of 25 passes them by construction: layer 1 shows what
    becomes visible, and only layer 2 says whether models do better with it.
52. **Layer 2 counted output tokens wrong, and the cache's price structure checks out.** A message's
    `usage` in stream-json is a snapshot from when it began streaming (8 and 5 output tokens where
    the result event's total was 139); every row before this fix undercounts output. No finding
    rested on output tokens. Input, cache writes and cache reads summed correctly. Claude Code writes
    the cache with a one-hour lifetime (2x input); with reads at 0.1x and output at 5x, one run's
    cost implies exactly $0.10 per million input tokens for Haiku 5.5, and P3's runs agree on about
    $1.84 for Sonnet 5.5.
53. **What the cache adds to the verdicts.** Folding a medium result inline costs 1.4 more requests
    and about 70k more cache reads now, writes 7k to 9k fewer tokens, and saves 7.1k (Haiku) to
    8.8k (Sonnet) cache-read tokens on every request after it: $0.0016 a later request on Sonnet,
    about $0.08 over 50 more turns for one folded result. Folding a spill is the other way round:
    1.2 to 1.5 fewer requests now, then 800 more tokens on every later request with Haiku (900 fewer
    with Sonnet, undecided). The hook never invalidates the cache, since it changes a result before
    it enters the conversation; offered tools do, once, by changing the prefix.

## Dials on one model (`dials-haiku-m.md`, `dials/haiku-m.toml`)

54. **At M on Haiku, the fold as shipped saves 12% of the final context and 5% of the cost, adds
    4.4 s, and keeps every answer.** The 52 MCP tasks twice, native and six settings: 598 runs,
    $4.17, none failed. Native answered 104 of 104, so accuracy sits at the ceiling and +0% [-4%,
    +4%] is all 104 agreeing pairs can show. The final context falls 6.8k from 58k and each later
    request carries 7.6k fewer tokens; summed input rises 69k, nearly all of it cache reads (+76k),
    because the fold adds one to two requests and each re-reads the prefix at a tenth of the price.
    Cache writes fall 6.9k: the folded result is written once instead of the raw.
55. **The model checks the fold against the raw nearly every time, so the dials barely move.** It
    read the saved output in 98 of 104 default runs (90 at budget 4000, 19 of 26 with the schema
    view), in no native run, and never answered from the fold without another call. Budget 500 to
    4000 moves the final context by 2.8k and the cost by 7 points; against the default, the schema
    view saves 928 more tokens, 4% of the cost and 1.1 s, budget 500 saves 1,060 and 3%, and
    `tree-cap-25` 437 and 2%. Three answers were lost in 416 pairs: twice at budgets 500 and 1000 on
    `json-M-absent-none` (normal restart counts called anomalous) and once at 4000 on
    `a11y-M-absent-none`.
56. **The format matters more than any dial.** Native makes one call in three requests; the fold
    makes 1.9 (JSON) to 3.3 (Figma) calls. JSON saves 9.8k of context and 20% of the cost (+2.8 s),
    logs 10.1k and 15% (+4.1 s), accessibility trees 4.9k and nothing (+4.3 s), Figma 2.6k at 15%
    more cost (+6.5 s): where the model has to fetch more to answer, the extra requests cost more
    than the smaller result saves.
57. **`estimate_tokens` (characters / 4) undercounts these payloads by 1.5 to 2 times.** A native
    run's final context at M, less the 47k a native XXL run carries (where the result spills to a
    short preview), puts the results at 9.5k (accessibility tree) to 13k (log) real tokens against
    5.7k to 7.4k estimated: hex ids and punctuation tokenize short. Bands and budgets are in
    estimated tokens; the savings in layer-2 reports are real tokens from the API.

## The size ladder (`dials-haiku-sizes.md`, `sweep-sizes.md`, `dials/haiku-sizes.toml`)

The 52 MCP tasks at L, XL (4x L) and XXL (16x L, up to 659k estimated tokens), once each on Haiku:
native against the hook folding the saved output (mode `all`) at budgets 2000 and 6000, and the
schema view on JSON. 507 runs, $3.66, none failed.

58. **Layer 1 does not care how large the output is.** From L to XXL the fold stays the same size
    (median 1,695 tokens at budget 2000, 3,750 at 6000), sufficiency moves by at most one task of
    60, no fold breaks an invariant, and the largest folds in under a second (Figma, 589k, 0.9 s).
59. **Past the spill threshold native's context does not grow either, so there is none to save.**
    Claude Code saves a spilled result to a file and shows a preview; native Haiku then greps and
    reads the file, in every run, and its final context stays at 48.6k to 49.1k from L to XXL.
    Folding the saved output at budget 2000 leaves it there: median +669 (L), +85 (XL), +404 (XXL)
    tokens, each interval spanning zero. Not lower, so by the input criterion still cut, as P2 found
    at L (34, 37).
60. **What the fold saves past the threshold is work, and that grows with the output.** At budget
    2000, 156 pairs: accuracy +6% [+3%, +11%], 10 won and none lost (McNemar p 0.002), every win a
    spot task in an accessibility tree or Figma file where native grepped, found nothing and said
    none (it missed 10 of those 18 tasks); 1.1 (L) to 1.6 (XXL) fewer requests and 66k fewer
    summed input tokens a run; cost -12% to -15% at every size; time -2.2 s at L, -6.2 s at XL,
    -9.7 s at XXL. Native's time grows with the output (mean 15.8, 19.4, 24.2 s; p90 26, 28, 38 s;
    its slowest Figma run 138 s at XXL) and the fold's does not (13.6, 13.2, 14.5 s; p90 18 to 21 s).
    The pairs pool three bands of the same task templates, generated from different seeds.
61. **Past the threshold the budget dial hurts and the schema view helps.** Budget 6000 changes the
    trees alone (the JSON and log folds come out the same at any budget, 435 and 1,957 tokens): their
    folds grow about 3.5k, the model still reads the raw, and the final context grows 2.9k to 4.2k,
    failing at every band, for the same answers (10 won, 1 lost) and a cost saving of 3%. The schema
    view on JSON answers 13 of 13 at every band, as native does, with the final context 1.2k to 1.4k
    lower in every pair, cost -21%, time -6.8 s, and the raw read in 26 of 39 runs against 39 of 39
    native: the one setting that passes the input criterion past the threshold, indicative at 13
    pairs a band (39 together leave accuracy at +0% [-9%, +9%]).
62. **The ladder, at budget 2000** (M is `dials-haiku-m.md`, two repetitions, the hook's default
    `inline`, which at M folds what `all` would):

    | band | median input (estimated) | native right | accuracy | final context | cost | time |
    |---|---|---|---|---|---|---|
    | M | 6.5k | 100% | +0% [-4%, +4%] | -6.8k | -5% | +4.4 s |
    | L | 35k | 94% | +6% [-2%, +16%] | -1.0k | -12% | -2.2 s |
    | XL | 141k | 92% | +8% [-1%, +18%] | -0.2k | -15% | -6.2 s |
    | XXL | 565k | 94% | +6% [-2%, +16%] | +0.1k | -14% | -9.7 s |

    Changes against native, means per run. Under the threshold the fold saves context and costs time;
    over it, Claude Code's spill already caps the context, and the fold saves answers, requests,
    cost and time instead, more as the output grows.

## Sessions: one result, six questions (`sessions-haiku.md`, `sessions/haiku.toml`, EVALS.md "Sessions")

Each conversation asks, in one Claude Code process, the count on a count task's payload (the prompt
names the tool), then every planted item, then four items looked up across the payload: 16
conversations a band at M and L, twice, native against the fold (`all`, budget 2000) and, on JSON,
the schema view. 144 sessions, 864 turns, $1.77, none failed; every turn right under every
condition (192 of 192 a band), so these kinds measure cost, not accuracy.

63. **Under the threshold the fold's saving lasts the session, and so does its fetching.** At M the
    folded session's context is 8.5k smaller after the first answer and still 8.0k smaller after
    the sixth. But native answers each follow-up from the raw it holds (1.0 request, $0.00076, 3.6 s)
    and the folded session fetches from the saved raw for most of them (1.8 requests, 0.8 calls,
    $0.00117, 5.0 s). Over six turns: cost +10% ($0.0012), time +9.3 s, 5.4 more requests, cache
    writes -7.7k, cache reads +235k.
64. **The break-even is about 15 later requests, on Haiku's prices.** Every later request that needs
    nothing from the result carries 8k fewer tokens, $0.00008 at the cache-read price; every
    follow-up that does need it costs $0.0004 more, about five such requests' saving. After these
    five follow-ups the folded session is $0.0012 behind, made up after 15 more requests. Cost scales
    with one price structure on every model here (FINDINGS 52), so the count should carry over; the
    time does not come back: 1.4 s more for each follow-up that fetches.
65. **The schema view breaks even after two.** On JSON at M its first answer is a third cheaper
    ($0.0050 against $0.0074) and its context 12.2k smaller, still 10.7k after the sixth turn; its
    follow-ups fetch as the fold's do. Session cost +1%, time +2.4 s; the context saving pays the rest
    back within two later requests.
66. **Past the threshold the session changes nothing for the fold, and the schema view keeps its
    edge.** At L every session fetches from the saved file on every follow-up, native or not (1.8 to
    2.0 requests a follow-up). The fold: cost -2%, time +0.3 s, final context +738 (the fold is larger
    than Claude Code's preview), each within noise. The schema view: cost -8%, time -3.3 s, context
    1.5k smaller, 0.5 fewer requests. With count, list and lookup questions native Haiku greps the
    saved file reliably; the spot tasks, where the fold won answers past the threshold (60), are not
    among them.

## The envelope, layer 1 (`l1-21-*.md`, `sweep-envelopes.md`, PLAN.md "The envelope")

67. **The two JSON views come apart into parts and go back together.** As envelopes, the schema
    view's parts (fields, exceptions, matches, jq) are sufficient on exactly the tasks the schema
    view is (41 of 47, task by task) at 29 more tokens median, for the part titles and a line on
    reading any path; the sample fold's (summary, standouts, head-tail, rows) on 37 of the fold's
    38, the one short being a PyPI enumeration the fold answers by keeping every key that matches
    the query, where the parts show three matching rows. Every claim of every envelope held against
    the data, `jq` run on each command; both views stayed byte-identical over 1,376 folds. Two
    scorer and claim gaps turned up and were fixed: PyPI's release count was accepted only in the
    sample fold's wording, and the stand-out rules said "none" of items they cannot read.
68. **Mixing the parts: the anomalies matter most, then the query's rows; a typical sample adds
    nothing layer 1 can see.** Over 16 recipes at budgets 500 and 2000 (no violations anywhere),
    exceptions beat stand-outs on spot tasks (12 of 12 against 9 or 10) and on the quiet anomalies
    (3 of 3 against 0 or 1) at every shape and sample; showing the rows that match the query adds 5
    or 6 tasks, all lookups with the query on. The fuller shape (fields) answers more enumerations
    than the summary (6 of 7 against 4 at 2000, by listing a keyed collection's keys), and the
    summary is about 70 tokens smaller: at 500 tokens summary, exceptions and matches is the most
    sufficient recipe (35 of 47 at 168 tokens). A typical sample or head and tail leave every count
    as it was and cost 65 and 190 tokens: what a sample is for (the row's literal form, so a query
    is written right, and trust) is not something layer 1 measures, so whether it earns its tokens
    is a layer-2 question (PLAN.md E6).

69. **The envelope replaces both JSON renderers, losing nothing layer 1 can see.** The sample
    fold's JSON-with-markers, the schema view's text, their markers, the checks that read the
    markers back and `recovery.py` are gone; `--view sample` and `--view schema` now name two
    recipes. Over the 47 JSON and PyPI tasks each view is sufficient on exactly the tasks its old
    renderer was (38 and 41, task by task), at 29 more tokens median; the other 154 folds are
    unchanged in sufficiency and size; no violations in 201. Two things had to change for that:
    rows matching the query are found by the old fold's rule (a term at most a fifth of the rows
    hold, every such row listed, where the schema view's took a twentieth and three rows), which
    brings back the PyPI 2023 releases; and a JSON value too small to hold a collection is outlined
    rather than summarised, since the summary of it was empty and would have hidden the whole
    output. Layer-2 results before this were measured on the old renderers' text.

## Real logs: HDFS (`l1-23-hdfs.md`, `dials-haiku-hdfs.md`, `dials/haiku-hdfs.toml`)

Loghub's HDFS_v1 from Hugging Face (`./lab fetch hdfs`): a Hadoop cluster's log over two days, each
block labelled anomalous or not by the people who ran it. The 7,940 blocks that start in the first
100,000 lines are kept whole (every line of each, from all 11.2M; 313 anomalous). A task's log is
the cluster's log filtered to chosen blocks in the original order: 10 blocks at M (about 8.5k
estimated tokens), 80 at L (about 69k). Kinds: spot, absent, count, enumerate (truths from the
labels) and lookup (the file a block was allocated for, read off its lines).

70. **Real data broke two assumptions before any model ran.** Cut at the first 400,000 lines, the
    anomalous blocks without an error word looked exactly like healthy ones: their labels rest on
    lines hours later, so the excerpt had to hold whole lives. And error words sort nothing:
    7,299 of the 7,627 healthy blocks have a line saying "exception" (routine "Got exception while
    serving" read warnings). Spot tasks are split instead into distinct anomalies (254 of 313: a
    kind of line under 1% of healthy blocks have) and subtle ones (what is wrong is the sequence).
    Layer 1: no violations; the log fold is sufficient on 11 of 24 folds, on no subtle anomaly,
    and on the absent tasks it shows windows around warnings in healthy blocks: it invents anomalies.
    The guarantee test now covers the synthetic formats alone, whose anomalies were planted for the
    rules.
71. **Haiku and the fold answer identically, and the labels measure something else.** 80 runs,
    $0.82, none failed: not one of 40 pairs disagrees. Lookups are right in all 16 runs. The
    label questions are near zero under both conditions: distinct anomalies 5 of 8 (4 of 4 at L, 1
    of 4 at M), subtle 0 of 8, absent 0 of 4, count 0 of 8, enumerate 0 of 4. Both read the routine
    read warnings as the problem; native even named a labelled block ("does not belong to any file",
    then deleted) and ranked the warning-heavy ones above it. The labels encode an operator's notion
    of an anomaly that the log does not state, so these kinds measure agreement with the labellers,
    which neither condition has; they cannot show a fold's effect on answers. The costs can: at M
    the fold cuts the final context 8.3k [-10.6k, -5.5k] and the cost 12%, for 1.7 s (synthetic logs:
    -10.1k, -15%); at L the median run saves 4.8k of context, 15% of the cost and 6.0 s, but one
    folded session's context reached 190k tokens, more than the whole log, and cost $0.16, which
    turns the mean cost change to +50% (-27% without it). Next for real data: tasks whose answers
    were written for the question (MCP-Atlas), not borrowed from another task.

## Where the design stands

| Piece | Evidence | Leaning |
|---|---|---|
| Fold MCP results Claude Code spilled | P2 (Haiku, 104 pairs): accuracy +7% [+1%, +14%], 1.2 fewer requests, -9% cost, but the final context +800 tokens (34). P3 (Sonnet, 20 pairs): 20/20 against 18/20, cost -21%, final context -910 [-4.1k, +1.4k] (41). The size ladder (Haiku, L to XXL, 156 pairs): accuracy +6% [+3%, +11%], cost -12% to -15%, time saved growing to 9.7 s, final context unchanged (58-62); the schema view on JSON lowers it 1.2k to 1.4k (61) | cut for Haiku by the input criterion (37), at a price in answers, cost and time the ladder shows; open for Sonnet (undecided at 20 pairs); the schema view is the candidate to pass; `TOOL_OUTPUT_LAB_MODE=spilled` |
| Fold MCP results under the spill threshold | P2 (Haiku): answers kept, final context -7.1k (35). P3 (Sonnet): 52/52 both, final context -8.8k, cost -20% (40) | keep; the hook's default (`inline`) |
| Force the fold on Bash (the hook on `Bash`) | 46-48: inline at M: final context -8.1k, cost -10%, +6 s, but 49/52 against 52/52 (undecided) and a regress (91 second looks folded); saved outputs at L: context +1.5k | inline: fix the regress, then decide; saved outputs: cut |
| Fold a result the session will use again (under the threshold) | Sessions (Haiku, M, 32 pairs of six-turn sessions): context -8k through the session, but each follow-up that needs the data costs a fetch; cost +10%, +9 s, break-even after ~15 more requests (63-64); the schema view on JSON breaks even after two (65) | keep for long sessions; the schema view for data |
| JSON folding with promotion | real MCP JSON to 13%; built anomaly kinds survive | keep |
| Line folding for logs | error words survive; quiet anomalies lost, and the loss costs answers | keep, with the gap stated |
| Tree folding for XML and accessibility trees | A/B 2 (Haiku): -37% tokens on spilled results; A/B 3 (Sonnet): no gain | keep for weaker models; Sonnet does as well alone |
| Read gate with ast-grep outlines | works, but Haiku and Sonnet page and grep on their own, even for overviews | drop |
| `fold` as a tool (CLI in CLAUDE.md, or an MCP tool with no shell) | P2: Haiku ran it once in 44 runs (36). P3: Sonnet 0 of 32, with a shell or without (42); the comprehension A/B: twice, at a cost | drop as an offered tool; folding works when it is applied (the hook), not when it is offered |

## Next

0. Fix the regress in forced Bash folding (48): a command's output folded once per session, a
   second run whole; then re-run M on the bash channel, `bash-native` against `fold-bash`.
1. Sample size before more conditions: one repetition of 52 tasks cannot resolve 3 points of
   accuracy (33). About 150 independent tasks a cell, not repetitions, is what a verdict needs:
   more generated tasks per format and band, on Haiku, where a run costs $0.007.
2. At L the fold is larger than Claude Code's preview and both models read the raw anyway (34, 41):
   try a fold no larger than the preview, or a banner that says what the fold guarantees. The
   ladder agrees: a larger fold (budget 6000) fails, and the smallest (the schema view, ~240 tokens)
   is the one that lowers the final context (61). Next: the schema view on spilled JSON with enough
   tasks to decide (about 150 pairs), and a smaller tree fold for spills.
3. Harder edits, where the outline matters: an edit in a method whose name recurs in several
   classes, or in a folded branch; these five were made right everywhere (44).
4. P4 of EVALS.md: explain tasks with a validated judge; Markdown, CSV and diffs.

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


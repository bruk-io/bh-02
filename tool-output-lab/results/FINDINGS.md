# Findings

The running summary. Each entry names the result file or sample it rests on. Numbers come from
files in this folder, not from memory. Since 2026-11-03 the target is Claude Code: the hooks in
`claude_code/` and headless `claude -p` runs against native Claude Code.

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

1. **Where Claude Code spills, the fold wins:** a third fewer input tokens, a third less time,
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

13. **The same split as A/B 1:** on spilled results the fold saves 37% of input tokens, 19% of the
    cost and a quarter of the time, with no answer lost; on inline results it costs more and takes
    twice as long, because Claude opens the saved file anyway.
14. **Accessibility snapshots gain the most.** Natively, Claude explored a spilled 500-invoice
    snapshot in 6.5 calls and 27s; with the outline fold it answered in 2 calls and 9.5s.
15. **Lookups recover as designed.** The fold hid the asked-for invoice and card (the tool calls
    carry no query), and Claude grepped the saved file and answered correctly in every run.
16. **Claude opens the saved file in nearly every folded run**, even when the answer is in the fold.
    That one extra call is the fold's whole cost on small results. Whether a banner that says what
    the fold guarantees (for example, that every sibling that differs is shown) cuts it, without
    inviting misplaced trust, is untested.

## Where the design stands

| Piece | Evidence | Leaning |
|---|---|---|
| Fold MCP results Claude Code spilled | A/B 1: -33% tokens, -34% time, same accuracy | keep; the default |
| Fold MCP results under the spill threshold | A/B 1: more tokens, more time, two misses | drop |
| JSON folding with promotion | real MCP JSON to 13%; built anomaly kinds survive | keep |
| Line folding for logs | error words survive; quiet anomalies lost, and the loss costs answers | keep, with the gap stated |
| Tree folding for XML and accessibility trees | A/B 2: on spilled results -37% tokens, same accuracy; lookups recovered from the file | keep, spilled-only |
| Read gate with ast-grep outlines | works, but Haiku and Sonnet page and grep on their own, even for overviews | drop the gate; offer the outline as a tool |

## Next

1. A/B 1 and 2 with Sonnet, spilled-only mode, on the large cases; and a banner variant that says
   what the fold guarantees, to see whether it saves the checking call.
2. The outline as a tool Claude can call (`outline FILE`, through Bash or MCP), and an A/B of it
   against Claude's own grep outlines on comprehension tasks.
3. A second corpus of real Claude Code sessions, to see how often results land in the spilled band.

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


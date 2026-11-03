# Findings

The running summary. Each entry names the result file or sample it rests on. Numbers come from
files in this folder, not from memory.

## How large outputs arise (agent corpus 1, `stats-agents-1.md`)

Corpus: six Claude Code sub-agents given real read-only tasks on this repo (test run, PyPI
dependency check, GitHub history via MCP, cordis source walk-through, git churn, ast-grep docs).
They were not told about the lab. 93 tool results, ~75k tokens. Sizes are what reached the model
after Claude Code's own limits; none of the results was large enough for Claude Code to spill it
to a file. The transcripts are in `corpus/transcripts-agents-1/` (gitignored).

1. **An agent with a shell filters at the source on its own.** 37 of 52 Bash calls piped through
   head, tail, grep, sed or python, or redirected to a file. Asked to read raw HTML docs and PyPI
   JSON with curl, agents saved them to files (118 KB of HTML, 3.2 MB of JSON) and pulled out what
   they needed; neither payload entered context. The largest Bash result was 3.4k tokens.
2. **What lands large is what the agent cannot filter or chose to read whole.** 10 results were
   over the 2,000-token budget and held about half the corpus's tokens: 5 whole-file `Read`s, 2 MCP
   JSON results (`list_commits`, `list_pull_requests`) and 3 Bash outputs.
3. **`Read` must not be folded.** The 5 over-budget `Read`s were cordis source and its README,
   read by the agent whose task was to explain the code with file:line references. Folding
   `runtime.py` 8,610 -> 1,407 tokens would have removed the lines it cited. They are 20.7k of the
   33.3k over-budget tokens, so without them the saving falls from 31% to 14% of the corpus.
4. **MCP JSON is the clear win:** 9,752 -> 1,270 tokens (13% kept) for the two results, with no
   filtering parameter the agent could have used instead (`list_commits` has `perPage` and
   `fields`, and the agent used both; the result was still 31k chars).
5. **The `lines` branch barely helps on what agents run:** the 3 Bash results kept 81%, because
   the agents had already cut them to what they wanted.

## JSON folding on real MCP output

6. `list_commits` (60 commits): ~7.7k -> ~1.1k tokens before fix 7, ~840 after.
7. **Query terms from arguments add noise.** The call's `owner: "bruk-io"` gave the term `bruk`,
   which matched every commit by that author, so three arbitrary commits were promoted as
   "matches the query". The synthetic grid missed this because its arguments did not name the
   container. Fixed: a query term that matches more than 20% of an array's items is ignored
   (`_discriminating` in `json_fold.py`, test `test_a_query_term_most_items_share_promotes_nothing`);
   `list_commits` then folds to ~840 tokens instead of ~1,150.
8. The banner's recovery example was generic (`$.items[10:20]`) when the root was an array. Fixed:
   the example is built from the first real fold marker.

## Needle survival (synthetic, no model)

Baseline: `needle-1-baseline.md` (3 seeds). After the CamelCase error fix:
`needle-2-camelcase-errors.md` (5 seeds).

9. **JSON statistical promotion works for the kinds it was built for.** A rare value, a rare
   nested value, an error key only one item has, and a flipped boolean survive at every position
   and size (50 to 5,000 items), at about 2% of the raw tokens.
10. **A numeric outlier is lost** (restarts 9999 among 0-3): high-cardinality numbers are not
   analysed. Survives only at the head or tail.
11. **A query match survives only with the query on.** With the query off it is lost unless at the
   head or tail.
12. **Logs: error words survive everywhere.** A quiet anomalous line (no error word) is lost unless
    at the head or tail; expected.
13. **The last line of a stack trace was lost in the baseline** (33%): `\berror\b` does not match
    inside `ValueError`. Fixed by matching `...Error` and `...Exception` words: 100% in the second
    run, with no other cell changed.
14. **The lines branch leaves most of the budget unused:** ~750 tokens out against a 2,000 budget,
    because head, tail and windows are fixed counts. Whether to spend the rest (and on what) is
    open; more head and tail would not help a needle in the middle.
15. The second run predates fix 7, and shows the same noise: with the query on, the argument
    `namespace: "default"` matched every item and promoted the earliest ones, which is why the
    numeric outlier reads 33% (query on) against 29% (off).

## Where the design stands (provisional: no model stage has run)

| Branch | Evidence so far | Leaning |
|---|---|---|
| JSON folding + promotion | 13% kept on real MCP JSON; needles of the built kinds survive at every position | keep |
| `lines` | needles with error words survive; 81% kept on agent Bash, which agents already filter | keep for tools that return logs whole (CI logs, MCP log tools); little gain on shell |
| `Read` of files | folding would have removed lines the agent cited | never fold |
| HTML | agents never put raw HTML in context; untested on real pages | unproven |
| Query terms from arguments | finds what the call named; noisy until terms that match most items were dropped | keep, with the filter |

Not yet known, and what the kill criteria need: whether a model answers as well from the folded
JSON as from the raw (replay), and how often it calls `recover`.

## Next

1. An API key in the environment, then stages 6 and 7 (replay and needle with a model).
2. A second agent corpus aimed at the cases corpus 1 did not reach: tools that return large output
   whole with no way to filter (CI job logs, MCP list endpoints with no field selection), and a
   harness with no shell, where the agent cannot filter at the source.
3. A per-tool never-fold list in the router, starting with file reads.
4. Real HTML pages through the HTML branch, if corpus 2 produces any.

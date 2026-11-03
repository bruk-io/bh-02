# Findings

The running summary. Each entry names the result file or sample it rests on. Numbers come from
files in this folder, not from memory.

## How large outputs arise (agent corpus, 2026-11-03)

Corpus: six Claude Code sub-agents given real read-only tasks on this repo (test run, PyPI
dependency check, GitHub history via MCP, cordis source walk-through, git churn, ast-grep docs).
They were not told about the lab. Sizes are what reached the model after Claude Code's own limits.

1. **An agent with a shell filters at the source on its own.** Asked to read raw HTML docs and
   PyPI JSON with curl, the agent saved them to files (`curl -o`; 118 KB of HTML, 3.2 MB of JSON)
   and pulled out what it needed with python, grep and sed. Neither payload entered its context.
   The middleware has nothing to do there.
2. **What does land large is what the agent cannot filter:** MCP tool results returned whole
   (`list_commits`: 31k chars of JSON) and whole-file reads (`Read` of `runtime.py`: 34k chars).
   That narrows where the middleware can help: tool results with no filtering parameters, not
   shell output.
3. **Whole-file `Read` of source would currently route to `lines`** (numbered lines, many of them)
   and be folded head/tail. That is likely harmful when the agent reads to understand. Open until
   the replay stage judges it; a candidate rule is to pass `Read` of source through.

## JSON folding on real MCP output

4. `list_commits` (60 commits): ~7.7k -> ~1.1k tokens.
5. **Query terms from arguments add noise.** The call's `owner: "bruk-io"` gave the term `bruk`,
   which matched every commit by that author, so three arbitrary commits were promoted as
   "matches the query". The synthetic grid missed this because its arguments did not name the
   container. Fixed: a query term that matches more than 20% of an array's items is ignored
   (`_discriminating` in `json_fold.py`, test `test_a_query_term_most_items_share_promotes_nothing`).
6. The banner's recovery example was generic (`$.items[10:20]`) when the root was an array. Fixed:
   the example is built from the first real fold marker.

## Needle survival (synthetic, no model)

Baseline: `needle-1-baseline.md` (3 seeds). After the CamelCase error fix:
`needle-2-camelcase-errors.md` (5 seeds).

7. **JSON statistical promotion works for the kinds it was built for.** A rare value, a rare
   nested value, an error key only one item has, and a flipped boolean survive at every position
   and size (50 to 5,000 items), at about 2% of the raw tokens.
8. **A numeric outlier is lost** (restarts 9999 among 0-3): high-cardinality numbers are not
   analysed. Survives only at the head or tail.
9. **A query match survives only with the query on.** With the query off it is lost unless at the
   head or tail.
10. **Logs: error words survive everywhere.** A quiet anomalous line (no error word) is lost unless
    at the head or tail; expected.
11. **The last line of a stack trace was lost in the baseline** (33%): `\berror\b` does not match
    inside `ValueError`. Fixed by matching `...Error` and `...Exception` words; see the second run.
12. **The lines branch leaves most of the budget unused:** ~750 tokens out against a 2,000 budget,
    because head, tail and windows are fixed counts. Whether to spend the rest (and on what) is
    open; more head and tail would not help a needle in the middle.

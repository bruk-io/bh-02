# Review 1 (four Opus reviewers, 2026-11-03)

Four independent reviewers, read-only, each with one lens: fold core (CORE), eval validity (EVAL),
Claude Code integration (HOOK), design and conventions (DESIGN). This file first holds their
findings, condensed; then the consolidated list (duplicates merged); then each finding's outcome,
validated one by one: fixed (with the test that pins it) or closed (with the reason).

## Raw findings, condensed

### DESIGN (design and code quality)

- DESIGN-1 (high) evals/truth.py score_fold: a Number is sufficient if the number appears as any
  token (json-M-count-k3 accepts 1, 2, 3; python-L-count-Server, true 15, accepts 13-17); Absent
  passes on every log, a11y and figma fold because only JSON writes `_next_item_shown_because`.
  Change: name where the count must be read (a summary entry, a marker's count) else all items
  seen; folds report what they promoted as data, Absent requires it empty; scorers reject value+-1.
- DESIGN-2 (high) route.py / lines.py: the lines and html branches ignore the budget (fixed head 15,
  tail 25, 60 windows, 400-char lines): a log of 428-char lines folds to ~10k tokens at budget
  2000; synthetic logs fold to ~1.2k at budgets 300, 1000 and 2000. l1 records over-budget only
  as a column. Change: a level ladder in fold_lines; over budget (not at the floor) is an l1
  violation; a small-budget run and a long-line log task.
- DESIGN-3 (high) harness/needle.py vs evals/synthetic.py: two generators of the same payloads
  have drifted; the A/B fixture and needle grid use one, l1 the other; the format-to-generator and
  format-to-tool maps are written four times; EVALS.md and fixture_mcp's docstring are stale.
  P2 cannot run L2 on P1's payloads. Change: one generator; fixture serves a task by id.
- DESIGN-4 (medium) three "whole word" rules (needle.contains, truth.mentions, common.matches);
  comprehension scores recall only and duplicates python enumerate tasks; parse_stream hack.
  Change: score every L2 answer with evals.truth.score_answer; comprehension questions as Tasks.
- DESIGN-5 (medium) two query-term rules: query_terms(args) keeps 4+ char identifiers (hook and
  compress), query_words(query) keeps 2+ char tokens (CLI and l1); the hook gets no terms from
  {"code":"JP-13"}. Change: one text-to-terms function; fold takes terms only.
- DESIGN-6 (medium) markers are a text protocol made by f-strings and parsed by regexes in route,
  hook and l1; drifted: hook._LINE_GAP matches only "omitted", so xml/outline banners always say
  sed -n '1,20p'. Change: one markers module (dataclasses, render/parse) or markers as data.
- DESIGN-7 (medium) the fold interface: Result has no branch (only in the header string, spelled
  two ways); fold_text mixes presentation and path sniffing; docstring omits two ValueErrors;
  "saved under 10%" prints the input with no header, indistinguishable from "fits"; JSON parsed
  three times. Change: detect returns a parse-carrying union; fold_text returns a Fold record;
  main renders the header; l1 reads fold.branch.
- DESIGN-8 (medium) route.py `fold.source != raw` compares against the input without its trailing
  newline: every well-formed XML file ending in a newline is reported as "pretty-printed copy";
  the hook writes a redundant copy. Change: xml_tree says whether it pretty-printed.
- DESIGN-9 (medium, safety) = HOOK-1. Plus the shared /tmp/tool-output-lab fallback.
- DESIGN-10 (medium) compress/recover are stage-3 leftovers: the banner names a recover tool that
  nothing provides; compress drops Folded.source; needle and stats measure compress, not what the
  hook or CLI emits; recover's in-band errors would crash l1 instead of recording a violation.
- DESIGN-11 (medium) fold_tree is one 200-line function, complexity 41, nine closures over shared
  state; standouts filled as a side effect, memoised by id(children). Change: pure phases.
- DESIGN-12 (low) tasks() reads host paths eagerly (stdlib 3.13, cargo registry, iso-codes); only
  pypi is guarded; the test module calls tasks() at import, so ./lab check fails elsewhere.
- DESIGN-13 (low) tests/unit holds I/O tests; both handle()s mix decisions with I/O; read_gate.plan
  and fixture_mcp.respond untested; test_needle pins a known weakness.
- DESIGN-14 (low) cli.py: BrokenPipeError is an OSError, so its branch is dead: `fold x | head`
  prints "fold: [Errno 32] Broken pipe" and exits 1.
- DESIGN-15 (low) ./lab check rewrites files (ruff format .) instead of checking; no type checker;
  rules that would flag fold_tree, an unused lambda, an unused variable are off.
- Sound: extract, stats, code.py, json_fold's ladder and in-place promotion, recovery._resolve,
  l1.coverage, hook.plan and read_gate.plan's decide split, fixture_mcp.respond, 3.15 usage.

### HOOK (Claude Code integration, against the current hooks and MCP docs)

- HOOK-1 (high) hook.py: any MCP result can fake Claude Code's spill notice and make the hook read
  and fold an arbitrary file (a 65 KB config in the home directory: 17 keys and 35 values shown).
  Fix: plain-string responses only; anchor the notice; realpath under session_dir, named
  mcp-<server>-<tool>-<digits>.txt; O_NOFOLLOW, regular file, size cap.
- HOOK-2 (high) the same path can be /dev/zero: read_text never returns (12 s to MemoryError
  under a cap; unbounded RSS otherwise); the default hook timeout is 600 s. Fix: regular file,
  bounded read, explicit hook timeout.
- HOOK-3 (high) read_gate.py: puts file content in permissionDecisionReason before Claude Code's
  permission check, so Read deny rules and outside-workspace prompts are bypassed (a secrets
  settings.py's password and key shown). Fix: gate only paths shown to be allowed (under cwd /
  project dir), or headers only.
- HOOK-4 (medium) JSON fold time grows as items x query terms (20k items x 40 terms: 22 s; 80k:
  80 s), synchronous before Claude sees the result. Fix: hook timeout, cap terms, precompute
  each item's text once, size cap.
- HOOK-5 (medium) for html and packed xml the hook saves folded.source instead of the raw: the
  raw is lost (an HTML result's hrefs and attributes gone from "Full output"). Fix: always save
  the raw; the source as a second file.
- HOOK-6 (medium) line numbers come from str.splitlines(), which also splits on \r, \f, \x1c-\x1e,
  \x85, U+2028/2029; Read, sed and grep count \n only: a CI log with \r progress lines drifts by
  80 lines; form feeds in a .py file shift the outline. Fix: split on \n everywhere numbers show.
- HOOK-7 (medium) the documented hook config has no cd, so it fails with ModuleNotFoundError
  outside the lab (ab.py prepends cd); allowedTools hides recovery permission prompts; -p never
  backgrounds MCP calls; the fixture returns one text block, real servers several.
- HOOK-8 (medium) the default mode folds inline results too, which the A/Bs cut. Fix: spilled-only
  by default.
- HOOK-9 (low-medium) without transcript_path both hooks use a fixed /tmp/tool-output-lab: shared
  across users, follows symlinks on write (a planted symlink overwrote a file), default modes,
  non-atomic writes. Fix: per-session private dir, O_EXCL|O_NOFOLLOW, 0600, atomic replace.
- HOOK-10 (low) read gate's once-per-session state is check-then-append with no lock (parallel
  Reads: both denied, or one each); keyed on the main transcript, shared with subagents.
- HOOK-11 (low) spill paths with spaces are not parsed; banner commands do not quote the path.
- HOOK-12 (low) jq examples for keys with `-` (`.pod-list[2:7]`) are wrong jq.
- HOOK-13 (low) a failing TOOL_OUTPUT_LAB_LOG write turns a fold run into native silently.
- HOOK-14 (low) the lab's `fold` shadows coreutils fold on PATH in both comprehension conditions;
  ran_fold counts `| fold -w` as using the tool; read_gate has no tests and no experiment.
- Sound: output fields and exit codes match the docs; matchers; tool_response shapes; session_dir
  matches where Claude Code spills; per-call file names; the spill regex is linear; the gate does
  not read FIFOs or devices; a timed-out hook delivers the native result.

### EVAL (eval validity)

- EVAL-1 (high) truth.score_fold Number: sufficient whenever the number appears anywhere, line
  numbers included: python-L-count-Server (15) passes on `15\t` with 7 of 15 names visible;
  rust counts pass on line 7 and line 19. Code at 2,000 is 4/17, not 7/17; at 6,000 11/17, not
  13/17. With 12 or 20 planted in 500, the fold shows exactly 10 with no note and still "passes"
  ("due 12 Nov", node id 12:1002). Change: a count only when stated as a count, or all counted items
  visible as item headers; tasks with k above the cap.
- EVAL-2 (high) truth.score_answer Items: precision counts every universe name mentioned in prose
  ("X is left out"), so right answers fail (9 of 12 comp-1 enumerate answers fail when rescored);
  the log universe is request ids while the expected items are order ids. Change: ask for a
  machine-readable list and score that; same-kind universe; validate on recorded answers.
- EVAL-3 (high) Absent: the fold scorer looks only for the JSON promotion key, so it always passes
  for logs and trees (it says "nothing promoted" on spot folds that do promote); the answer scorer
  accepts an invented order or pod, and a non-answer. (FINDINGS 29 holds today, checked by hand.)
  Change: detect promotion structurally; in L2 require an explicit "none" and reject anomaly-shaped
  claims.
- EVAL-4 (high) every planted L1 anomaly is one the fold has a rule for (CrashLoopBackOff is in
  _BAD_STATUS; ERROR failed in ANOMALY_RE; one-off sibling signatures), and k <= 7 is under the cap
  of 10: "spot is sufficient everywhere" holds by construction. At k=12 or 20, 10 of k shown with no
  note. Change: quiet, numeric and nested kinds; k above every cap; restate FINDINGS 29.
- EVAL-5 (high) harness/needle.py: the A/B JSON needle pod is named `needle-<hex>` among `web-<hex>`
  pods: 29 of 32 Haiku and 7 of 8 Sonnet JSON answers cite the name; the log needle is the word
  `needle-`. Both conditions' JSON accuracy is inflated. Change: one name shape; score the property.
- EVAL-6 (medium-high) FINDINGS 24 "20/20 right": two fold-condition action-subclasses answers
  miss _ChoicesPseudoAction (nested class) and pass at recall 0.9; recall-only scoring; native at
  ceiling, so "adds nothing" could not show a gain; `kill = terminate` makes both-platforms debatable.
- EVAL-7 (medium) the kill criteria cannot be judged at n=13-14 per cell (13/14 Wilson [68.5%,
  98.7%]); seeds at a fixed position are near-replicates; no intervals or paired differences are
  computed though EVALS.md promises them; inline folding also fails the first criterion (14/14 vs
  12/14). Change: report intervals; "passes" = lower bound above -3 points, or say indicative.
- EVAL-8 (medium) summed input tokens is almost a count of turns (29k + 39k x turns, R^2 0.90-0.94):
  "a third fewer tokens" means fewer round trips; the cache breakdown behind FINDINGS 19 is not
  recorded. Change: per-request usage by cache class, tool-result tokens, final context size.
- EVAL-9 (medium) FINDINGS 18 "in two cells the fold used more tokens": 4 of 6 tree cells (5 of 13
  overall); trees cost more folded ($0.635 vs $0.600), so by the second criterion spilled trees fail
  with Sonnet; the design table cites pooled numbers driven by JSON and logs.
- EVAL-10 (medium) tree prompts name the planted kinds ("an invoice that cannot be paid or an
  error", "a hidden layer or a different component"), JSON and log prompts are generic; no no-needle
  cases in L2; fold timings include a uv start per MCP call.
- EVAL-11 (medium) synthetic lookups are answerable by arithmetic: names carry the index, refs are
  e{8+2i}, node ids {10+i}:{1000+i}; A/B lookup answers identical across seeds.
- EVAL-12 (low-medium) "fits the budget" is listed as an invariant but only flagged above 1.25x and
  never a violation (PyPI folds 3,068-3,411 at 2,000 in l1-1..5; pypi-L-enumerate-2023 q 2,447 now);
  45 of 160 folds are passthroughs, so 128/160 is 83/115 on folds that folded.
- EVAL-13 (low) FINDINGS 15 "grepped the saved file in every run": only the 500-item runs; at 50 the
  target was in the fold.
- Sound: ISO, Rust and PyPI truths recomputed independently (regex); Python truths by ast;
  determinism across hash seeds; fixture and harness seeds match; hook fired once per folded run;
  every reported A/B and L1 number reproduces from the rows; mentions() rejects partial tokens.

### CORE (fold core correctness)

- CORE-1 (high) every module splits with str.splitlines() (also \f, \x0b, \x1c-\x1e, \x85, U+2028/9)
  and the CLI reads with universal newlines (bare \r -> \n), while sed, Read and ast-grep count \n:
  a form feed in a .py shifts every later number; a progress line with \r pushes log markers past
  the end of the file; l1's coverage check uses the same split, so it cannot see it.
- CORE-2 (high) log dedupe hides lines that differ only in numbers, the anomaly included: 2,000
  `... 200 <bytes>` lines with one `500` fold to the first line and "repeated 1999 more times".
- CORE-3 (high) fold_lines ignores the budget (= DESIGN-2): ~4.6k tokens at budgets 200 to 20,000.
- CORE-4 (high) code folds have no floor: 3,000 assignment lines as .py go 25.7k -> 29.2k tokens at
  budget 500 (23 tokens as .txt); unparsable code (one ERROR node) prints whole, larger.
- CORE-5 (high) exempt-key strings are never cut (error, message, path, url; and `sha`/`hash` match
  inside shape, shared_notes, hashtags): a 66 KB traceback under "error" prints whole at budget 500;
  when folding saves under 10% the CLI prints the raw with no header.
- CORE-6 (medium) RecursionError (a 260-branch else-if chain, a 600-deep outline, 100,000-deep
  JSON) crashes the CLI with a traceback.
- CORE-7 (medium) fold_tree's cost model differs from render: the gap after a hidden sibling run is
  not costed (2,174 tokens out of a 2,059-token input); `opened` keyed by (first, last), so a
  parent and its only child on the same lines share a key and the child renders open in full.
- CORE-8 (medium) --query is silently ignored for source code (fold_code takes no terms).
- CORE-9 (medium) tree query: share 0.05 gives cut 1 for 20-39 siblings (Kyoto in 2 of 30 offices:
  none shown); under 10 siblings, matches are stand-outs but can still be hidden in a run.
- CORE-10 (medium) JSON key names match the raw terms, not the discriminating ones (5,000 keys
  `node-i` with --query node: the whole input back, no header); set(kept) rebuilt per key:
  quadratic (40,000 keys: 242 s).
- CORE-11 (medium) the `_all_items` summary is unbounded (3,000 distinct keys: a 66 KB marker,
  16.6k tokens at budget 2,000), and every item promoted as "few items have".
- CORE-12 (medium) HTML detection fires on text that contains tags (a git diff of .jsx, markdown
  badges) and strips the code to text.
- CORE-13 (low-medium) parseString on bytes obeys the declared encoding (ISO-8859-1 -> mojibake,
  utf-16 -> error); a BOM defeats JSON and XML detection.
- CORE-14 (low) "pretty-printed copy" header on any XML ending in a newline (= DESIGN-8); the
  JSONL note's index-to-line mapping is wrong with blank lines; the dropped-errors count counts
  runs and already-shown lines.
- CORE-15 (low) BrokenPipeError caught as OSError (= DESIGN-14); `--lang cobol` panics with a
  pyo3 traceback.
- Sound: code-fold coverage over 150 random stdlib modules at four budgets; outline and XML
  coverage over 300 random trees; JSON slices, counts and quoting; determinism; linear scaling
  (except packed XML parsed twice); non-UTF-8 stdin does not crash.

## Consolidated (duplicates merged), in the order they are worked

| # | Finding | From | Severity |
|---|---|---|---|
| R1 | The hook trusts a spill notice inside the tool's output: arbitrary file read, device hang | HOOK-1, HOOK-2, DESIGN-9 | high |
| R2 | The read gate shows file content before Claude Code's permission check | HOOK-3 (+HOOK-10, HOOK-14) | high |
| R3 | Line numbers from splitlines() and universal newlines drift from what sed, Read and grep count | CORE-1, HOOK-6 | high |
| R4 | The budget is not kept: lines branch, code with no floor, exempt strings, unbounded summary, passthrough over budget, tree cost model and key collision; l1 does not enforce it | CORE-3, CORE-4, CORE-5, CORE-7, CORE-11, DESIGN-2, EVAL-12 | high |
| R5 | Log dedupe hides lines that differ only in numbers | CORE-2 | high |
| R6 | Scorers: Number accepts any token, Items precision counts prose, Absent blind outside JSON and accepts invented claims; three whole-word rules; L2 harnesses score differently | DESIGN-1, EVAL-1, EVAL-2, EVAL-3, DESIGN-4 | high |
| R7 | Eval tasks hold only anomalies the fold has rules for, and k under every cap | EVAL-4 | high |
| R8 | Fixtures give the answer away: `needle-` names, arithmetic ids and refs | EVAL-5, EVAL-11 | high |
| R9 | Two drifted generators; the fixture cannot serve the eval tasks; mappings written four times | DESIGN-3 | high |
| R10 | Findings overstated or unmeasured: comprehension 20/20, Sonnet tree cells, FINDINGS 15, no intervals, tokens are turns, prompts name the kinds, no no-needle cases in L2 | EVAL-6..10, EVAL-13 | medium |
| R11 | Query handling: two term rules, ignored for code, tree share and small lists, JSON key names and quadratic time, items x terms cost | DESIGN-5, CORE-8, CORE-9, CORE-10, HOOK-4 | medium |
| R12 | Markers are an unshared text protocol: hook banner examples wrong for xml/outline, jq for keys with `-`, unquoted paths and paths with spaces | DESIGN-6, HOOK-11, HOOK-12 | medium |
| R13 | The fold interface carries no branch, re-parses, and "saved under 10%" looks like "fits" | DESIGN-7 | medium |
| R14 | Source copies: wrong "pretty-printed" header, the hook saves the text copy instead of the raw, the JSONL mapping note | DESIGN-8, HOOK-5, CORE-14 | medium |
| R15 | compress/recover leftovers; needle and stats measure them, not the CLI or hook | DESIGN-10 | medium |
| R16 | fold_tree is one 200-line function over shared closure state | DESIGN-11 | medium |
| R17 | Hook defaults and wiring: no cd in the documented config, inline folding on by default, shared /tmp fallback, log failure silent, no timeout, `fold` shadows coreutils | HOOK-7, HOOK-8, HOOK-9, HOOK-13, HOOK-14 | medium |
| R18 | RecursionError on deep nesting | CORE-6 | medium |
| R19 | HTML detection fires on text that contains tags | CORE-12 | medium |
| R20 | Encoding declarations and BOMs | CORE-13 | low-medium |
| R21 | The log fold's dropped-errors count | CORE-14 | low |
| R22 | CLI errors: broken pipe, unknown language | CORE-15, DESIGN-14 | low |
| R23 | Eval tasks read host paths eagerly | DESIGN-12 | low |
| R24 | Test layering; read gate and fixture untested; a test pins a weakness | DESIGN-13 | low |
| R25 | `./lab check` rewrites instead of checking; no type checker | DESIGN-15 | low |

## Outcomes

Each finding is reproduced first, then fixed with a test that fails before and passes after, or
closed with the reason.

| # | Outcome |
|---|---|
| R1 | **Fixed.** Reproduced: a crafted notice naming `subprocess.py` came back folded. A spill is now only a plain-string response that starts with Claude Code's notice, and its path must resolve, links followed, inside this session's tool-results folder under `mcp-<...>-<digits>.txt`. The file is opened with no link following and non-blocking, read only when regular and under 32 MB, and bounded. Tests: `test_cc_hook_plan.py` (notice inside content blocks or mid-text is not a spill; paths with spaces; trusted_spill) and `tests/functional/test_cc_hook_files.py` (outside file, link out, FIFO). The FIFO test hung the first run: the open itself blocked, fixed with O_NONBLOCK. |
| R2 | **Closed: the read gate is removed.** It showed file content before Claude Code's permission check. Its value was already refuted (Haiku and Sonnet page and grep on their own, FINDINGS 6-9, 24-27), and a safe version would have to re-implement Claude Code's permission rules. Removal also closes HOOK-10 (its race) and its missing tests. Code folding stays available as `./lab fold`. |
| R17 | **Fixed:** the documented config has the absolute `cd` and a 30 s timeout; the default mode is spilled-only (`TOOL_OUTPUT_LAB_MODE=all` opts in), and `./lab ab` defaults to it too; there is no shared /tmp fallback (no transcript, no action); writes are 0600, atomic, never through a link; a failing log no longer aborts the fold (test); the comprehension shim is `lab-fold`, so it cannot shadow coreutils `fold` (test). **Closed as limits of headless runs, noted for P2:** `--allowedTools` hides permission prompts that recovery reads might raise in a default-mode session, and `-p` never backgrounds MCP calls. The multi-block fixture goes with R9. |
| R3 | **Fixed.** Reproduced: after a form feed, `fold` labelled line 5 `def func_0`, which `sed -n 5p` shows is the line after it. One `split_lines` (newline only, a trailing CR dropped for display) replaces `str.splitlines()` wherever a line number is shown or checked (code, tree, lines, route, recovery, html, and l1's coverage check, which shared the bug and so could not see it); the CLI and the eval tasks read bytes, with no newline translation. Tests: form feed (every numbered line equals `sed`'s), a CR progress line (no marker past the end), CRLF folds as LF. l1 unchanged (`l1-10-split-lines.md`). |
| R4 | **Fixed.** Reproduced 8 of the reviewers' cases over budget (up to 18,385 tokens at a budget of 500). Tree fold: runs of 6+ plain lines no node covers become foldable leaves (a floor for code: 3,000 assignments 25.7k -> 18 tokens; unparsable code folds), the gap after a hidden sibling run is costed, state is keyed by node identity (a parent and its only child shared a key). Logs: the budget is passed and a ladder of tighter limits tried (428-char lines: 4,268 -> 1,703 at 2,000). JSON: identifier keys matched as whole words (`shape` and `hashtags` were exempt), identifiers whole only up to 256 chars, `error`/`message` strings cut at tighter levels, the all-items summary capped, "few items have" skipped when most keys are rare (3,000 distinct keys: 16,561 -> 213). CLI: never prints raw over budget; a fold that saves too little falls back to a character cut with a header. l1: over budget (beyond 10%) and not the floor is a violation, and the report gives sufficiency over folds that folded. Tests: `test_budget.py`. l1: 0 violations; 130/160 at 2,000 (was 128), 141/160 at 6,000. |
| R21 | **Fixed with R4:** when a signal's window does not fit, its own line is kept if it fits; the "N more lines matching" note counts hidden lines, not runs, and not lines already shown. |

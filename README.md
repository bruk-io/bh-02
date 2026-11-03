# tool-output-lab

A scratch lab for one question: does compressing large tool outputs before they reach the model
help, and which compressors earn their place. Not part of bh-02 (no `pyproject.toml`, so it is not a
uv workspace member and no gate sees it). Move it to its own repo when it has results worth keeping.

Source idea: `Filtering_Large_Tool_Outputs.pdf` (a Gemini chat export). Take the ideas, not the code.

## The tool

```
./lab fold FILE [--budget 2000] [--query WORDS] [--as FORMAT] [--lang LANG] [--save PATH]
COMMAND | ./lab fold [--budget 2000] ...
```

Prints the shape of a large text in a token budget, with markers that say what they hide (a JSON
path, or a line or character range), so `jq`, `sed -n 'A,Bp'` or a paged read fetches exactly that.
Code (by extension, or `--lang`) folds through ast-grep: every class, function and block header at
its real line number. Other text folds by what it is: JSON, XML, accessibility outlines, HTML, logs,
plain text. Text that fits the budget comes back unchanged.

## Target: Claude Code

The lab tests the idea inside Claude Code, through a hook and headless runs:

- `claude_code/hook.py`, a `PostToolUse` hook on `mcp__.*|Bash`: folds large MCP results and Bash
  output (JSON, XML, accessibility outlines, logs), including what Claude Code itself saved to a
  file, and points Claude at the saved raw output. It acts after a command has run, so permission
  rules are checked on the real command; rewriting the command first, or wrapping the shell with
  `CLAUDE_CODE_SHELL_PREFIX`, breaks permission checks or hooks (FINDINGS 46). Read is never folded. By default (`inline`) it folds only results under Claude
  Code's spill threshold and leaves spills to Claude Code, the one mode P2 kept (FINDINGS 34-35);
  `TOOL_OUTPUT_LAB_MODE=spilled` folds only spills, `all` both.
- `evals/l2.py` with `claude_code/fixture_mcp.py`: headless `claude -p` runs on the eval tasks,
  native against the hook (or against `lab-fold` named in CLAUDE.md, for files), scored from the
  answer's ANSWER line, with tokens per request, the final context, cost, calls and intervals.

Results and what they mean: `results/FINDINGS.md`.

## Design under test

Deterministic folding by format, with the raw output kept and named, so nothing is lost:

- JSON: long arrays keep head, tail and the items that stand out, in place; wide objects keep
  their first keys and the ones the query names.
- Trees (`compressors/tree.py`): code through ast-grep, XML, indentation outlines. Outline first,
  stand-outs and containers before bodies, each hidden range one line-numbered marker.
- Logs: runs of repeated lines collapse; head, tail and windows around error words stay.

The query signal is the tool call's own arguments, ignoring terms most items share.

## Kill criteria (set before measuring)

A branch, or a mode of the hook, is cut if either holds against native Claude Code:

- answers drop more than 3 points;
- input tokens, recovery reads included, are not lower: measured as the final context, the input
  of the session's last request, which holds every recovery read (the owner's reading, 2026-11-03,
  FINDINGS 37; summed input is reported, not judged).

Change these numbers only before a run, never after seeing one. Layer 2 applies the criteria to
95% intervals. Folding results under the spill threshold passes with Haiku (P2) and holds on Sonnet
(P3: same answers, final context -8.8k, cost -20%). Folding spilled results fails the input
criterion with Haiku (the final context grows 800 tokens) and is cut; with Sonnet it is undecided
at 20 pairs. Fold tools offered to the model, by CLAUDE.md or as an MCP tool, were never used by
Sonnet and once in 44 runs by Haiku (FINDINGS 33-45).

## Running

```
./lab check                                   # green: format and lint checked, strict mypy, tests (Python 3.15 through uv)
./lab fix                                     # apply the formatter and ruff's safe fixes
./lab extract ~/.claude/projects              # transcripts -> corpus/results.jsonl
./lab stats [--budget 2000] [-o results/x.md] # corpus sizes, formats, deterministic compression
./lab evals l1 [--budget 2000]                # layer 1: every eval task folded and checked (free)
./lab evals l2 --dry-run [filters]            # layer 2: the runs it would make and their rough cost
./lab evals l2 --model M [filters] --name x   # layer 2: headless Claude Code on the eval tasks
```

## Layout

```
lab            the one entry point
corpus/        private transcripts and extracted results (gitignored)
compressors/   route.fold/compress (the router), json_fold, tree, code, lines, html, recovery
claude_code/   hook (PostToolUse), fixture_mcp (serves an eval task to Claude Code)
evals/         truth, synthetic, real, tasks, l1, l2, stats
harness/       extract, stats (corpus tools)
tests/unit/    pure-function tests
results/       one file per run, never edited after; FINDINGS.md is the running summary
```

## Status

See PLAN.md for the stages and results/FINDINGS.md for what has been learned.

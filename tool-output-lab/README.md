# tool-output-lab

A scratch lab for one question: does compressing large tool outputs before they reach the model
help, and which compressors earn their place. Not part of bh-02 (no `pyproject.toml`, so it is not a
uv workspace member and no gate sees it). Move it to its own repo when it has results worth keeping.

Source idea: `Filtering_Large_Tool_Outputs.pdf` (a Gemini chat export). Take the ideas, not the code.

## Design under test

Tool-result middleware between any tool and any model:

1. Under a size threshold: pass through untouched.
2. Otherwise route by format and compress deterministically.
3. Cache the raw output under a call id; the compressed text names the id and says how to recover.
4. A recovery tool returns a slice of the cached raw output.

Compression happens once, at insertion. Never rewrite an older result (it breaks prompt caching).
The query signal is the tool-call arguments only.

## Branches, in build order

| Order | Branch | Expected value |
|---|---|---|
| 1 | log dedupe + error windows | high |
| 2 | JSON array folding + anomaly promotion | high |
| 3 | HTML to markdown strip | high for web tools |
| 4 | recovery tool | required by 1-3 |
| later | markdown section skeleton, BM25 unfolding, code skeleton, small-LLM extractor | experiments, expected to lose |

## Validation

- **Corpus.** Real tool results over ~2,000 tokens from Claude Code transcripts
  (`~/.claude/projects/*.jsonl`) and bh-02 sessions, bucketed by format. Lives in `corpus/`
  (gitignored: transcripts are private). First output is the size and format distribution, with no
  compression at all. This tests the "70-80% structured" claim.
- **Replay test.** For each large result, the assistant's next step is the ground truth. Re-run that
  step with the compressed result and judge whether the next action or answer is equivalent. A judge
  model scores it; spot-check a sample by hand.
- **Needle test.** Generate JSON arrays and logs with one anomaly at a random index. Measure how often
  the model finds it with and without promotion.
- **Metrics per branch.** Token ratio, replay equivalence, recovery-call rate, net tokens including
  the recovery calls.

## Kill criteria (set before measuring)

A branch is cut if either holds:

- replay equivalence drops more than 3 points against the raw result;
- net tokens, recovery calls included, are not lower than raw.

Change these numbers only before a run, never after seeing one.

## Running

```
./lab check                                   # format, lint, tests (Python 3.15 through uv)
./lab extract ~/.claude/projects              # transcripts -> corpus/results.jsonl
./lab stats [--budget 2000] [-o results/x.md] # corpus sizes, formats, deterministic compression
./lab needle [--seeds 5] [-o results/x.md]    # synthetic needle survival grid
```

## Layout

```
lab            the one entry point
corpus/        private transcripts and extracted results (gitignored)
compressors/   route.compress (the middleware), json_fold, lines, html, recovery.recover
harness/       extract, stats, needle
tests/unit/    pure-function tests
results/       one file per run, never edited after; FINDINGS.md is the running summary
```

## Status

See PLAN.md for the stages and results/FINDINGS.md for what has been learned.

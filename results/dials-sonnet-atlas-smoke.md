# Dials sonnet-atlas-smoke: claude-sonnet-5-5, the same tasks native and under each setting

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 1 | 100% | 55,376 | 198,654 | 28,125 | 170,519 | - | $0.1383 | 24.5s |
| fold | 1 | +0% [-79%, +79%], 0/0 | -4,471 [-4,471, -4,471] | +39,860 [+39,860, +39,860] | -4,471 [-4,471, -4,471] | +44,329 [+44,329, +44,329] | -4,471 ($-0.00079) | -7% ($-0.0096) | -4.2 [-4.2, -4.2]s |
| schema | 1 | +0% [-79%, +79%], 0/0 | -4,429 [-4,429, -4,429] | -10,541 [-10,541, -10,541] | -4,429 [-4,429, -4,429] | -6,112 [-6,112, -6,112] | -4,429 ($-0.00078) | -12% ($-0.0168) | -8.2 [-8.2, -8.2]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.176 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-sonnet-5-5)

3 runs, $0.39; 3 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| atlas | claims | M | fold | 1/1 [21%, 100%] | $0.1287 | 50905 | 5 | 1/1 | 0/1 |
| atlas | claims | M | native | 1/1 [21%, 100%] | $0.1383 | 55376 | 3 | 0/1 | 0/1 |
| atlas | claims | M | schema | 1/1 [21%, 100%] | $0.1215 | 50947 | 4 | 1/1 | 0/1 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| atlas | M | fold | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0096 [-0.0096, -0.0096] | -4471 [-4471, -4471] | +39860 [+39860, +39860] | -4.2s [-4.2, -4.2] | undecided (indicative: under 30 pairs) |
| atlas | M | schema | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0168 [-0.0168, -0.0168] | -4429 [-4429, -4429] | -10541 [-10541, -10541] | -8.2s [-8.2, -8.2] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | fold | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0096 [-0.0096, -0.0096] | -4471 [-4471, -4471] | +39860 [+39860, +39860] | -4.2s [-4.2, -4.2] | undecided (indicative: under 30 pairs) |
| M | schema | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0168 [-0.0168, -0.0168] | -4429 [-4429, -4429] | -10541 [-10541, -10541] | -8.2s [-8.2, -8.2] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $1.762 per million tokens (80% of runs between $1.714 and $1.780); so a cache read costs $0.176 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | fold | 1 | +1.0 [+1.0, +1.0] | -4,471 [-4,471, -4,471] | +44,329 [+44,329, +44,329] | +2.0 [+2.0, +2.0] | 1/1, 1/1 | -4,471 tokens, $-0.00079 |
| M | schema | 1 | +0.0 [+0.0, +0.0] | -4,429 [-4,429, -4,429] | -6,112 [-6,112, -6,112] | +0.0 [+0.0, +0.0] | 1/1, 1/1 | -4,429 tokens, $-0.00078 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

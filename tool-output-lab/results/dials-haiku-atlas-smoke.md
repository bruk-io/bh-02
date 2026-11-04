# Dials haiku-atlas-smoke: claude-haiku-5-5, the same tasks native and under each setting

## Band M (median input 3,138 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 2 | 100% | 57,094 | 280,362 | 28,062 | 252,290 | - | $0.0094 | 19.7s |
| fold | 2 | -50% [-91%, +27%], 0/1 | -4,292 [-4,458, -4,125] | -35,233 [-115,794, +45,328] | -4,292 [-4,458, -4,125] | -30,940 [-111,332, +49,451] | -4,292 ($-0.00004) | -12% ($-0.0012) | -1.3 [-2.6, +0.1]s |
| schema | 2 | +0% [-66%, +66%], 0/0 | -5,106 [-5,999, -4,212] | -63,424 [-68,716, -58,132] | -5,754 [-6,644, -4,865] | -57,668 [-63,849, -51,486] | -5,106 ($-0.00005) | -20% ($-0.0019) | -2.4 [-6.4, +1.5]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band L (median input 13,654 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 1 | 0% | 55,261 | 299,652 | 26,228 | 273,412 | - | $0.0097 | 22.8s |
| fold | 1 | +0% [-79%, +79%], 0/0 | +3,891 [+3,891, +3,891] | -30,059 [-30,059, -30,059] | +3,891 [+3,891, +3,891] | -33,948 [-33,948, -33,948] | +3,891 ($+0.00004) | +5% ($+0.0005) | +2.6 [+2.6, +2.6]s |
| schema | 1 | +0% [-79%, +79%], 0/0 | +1,649 [+1,649, +1,649] | +10,046 [+10,046, +10,046] | +1,649 [+1,649, +1,649] | +8,397 [+8,397, +8,397] | +1,649 ($+0.00002) | +5% ($+0.0005) | +7.6 [+7.6, +7.6]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 3 | 67% | 56,877 | 286,792 | 27,450 | 259,331 | - | $0.0095 | 20.7s |
| fold | 3 | -33% [-61%, +13%], 0/1 | -1,564 [-4,458, +3,891] | -33,508 [-115,794, +45,328] | -1,564 [-4,458, +3,891] | -31,943 [-111,332, +49,451] | -4,125 ($-0.00004) | -6% ($-0.0006) | +0.0 [-2.6, +2.6]s |
| schema | 3 | +0% [-19%, +19%], 0/0 | -2,854 [-5,999, +1,649] | -38,934 [-68,716, +10,046] | -3,287 [-6,644, +1,649] | -35,646 [-63,849, +8,397] | -4,212 ($-0.00004) | -12% ($-0.0011) | +0.9 [-6.4, +7.6]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

9 runs, $0.08; 9 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| atlas | claims | M | fold | 1/2 [9%, 91%] | $0.0082 | 52803 | 5.0 | 2/2 | 0/2 |
| atlas | claims | M | native | 2/2 [34%, 100%] | $0.0094 | 57094 | 4.5 | 0/2 | 0/2 |
| atlas | claims | M | schema | 2/2 [34%, 100%] | $0.0074 | 51989 | 5.0 | 1/2 | 0/2 |
| atlas | claims | L | fold | 0/1 [0%, 79%] | $0.0102 | 59152 | 7 | 0/1 | 0/1 |
| atlas | claims | L | native | 0/1 [0%, 79%] | $0.0097 | 55261 | 6 | 0/1 | 0/1 |
| atlas | claims | L | schema | 0/1 [0%, 79%] | $0.0102 | 56910 | 6 | 0/1 | 0/1 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| atlas | M | fold | 2 | -50% [-91%, +27%] | 0/1, p 1.00 | $-0.0012 [-0.0018, -0.0006] | -4292 [-4458, -4125] | -35233 [-115794, +45328] | -1.3s [-2.6, +0.1] | undecided (indicative: under 30 pairs) |
| atlas | M | schema | 2 | +0% [-66%, +66%] | 0/0, p 1.00 | $-0.0019 [-0.0024, -0.0014] | -5106 [-5999, -4212] | -63424 [-68716, -58132] | -2.4s [-6.4, +1.5] | undecided (indicative: under 30 pairs) |
| atlas | L | fold | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0005 [+0.0005, +0.0005] | +3891 [+3891, +3891] | -30059 [-30059, -30059] | +2.6s [+2.6, +2.6] | fails (indicative: under 30 pairs) |
| atlas | L | schema | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0005 [+0.0005, +0.0005] | +1649 [+1649, +1649] | +10046 [+10046, +10046] | +7.6s [+7.6, +7.6] | fails (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | fold | 2 | -50% [-91%, +27%] | 0/1, p 1.00 | $-0.0012 [-0.0018, -0.0006] | -4292 [-4458, -4125] | -35233 [-115794, +45328] | -1.3s [-2.6, +0.1] | undecided (indicative: under 30 pairs) |
| M | schema | 2 | +0% [-66%, +66%] | 0/0, p 1.00 | $-0.0019 [-0.0024, -0.0014] | -5106 [-5999, -4212] | -63424 [-68716, -58132] | -2.4s [-6.4, +1.5] | undecided (indicative: under 30 pairs) |
| L | fold | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0005 [+0.0005, +0.0005] | +3891 [+3891, +3891] | -30059 [-30059, -30059] | +2.6s [+2.6, +2.6] | fails (indicative: under 30 pairs) |
| L | schema | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0005 [+0.0005, +0.0005] | +1649 [+1649, +1649] | +10046 [+10046, +10046] | +7.6s [+7.6, +7.6] | fails (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | fold | 2 | -0.5 [-2.0, +1.0] | -4,292 [-4,458, -4,125] | -30,940 [-111,332, +49,451] | -1.0 [-4.0, +2.0] | 2/2, 2/2 | -4,292 tokens, $-0.00004 |
| M | schema | 2 | -1.0 [-1.0, -1.0] | -5,754 [-6,644, -4,865] | -57,668 [-63,849, -51,486] | -2.0 [-2.0, -2.0] | 2/2, 2/2 | -5,106 tokens, $-0.00005 |
| L | fold | 1 | -1.0 [-1.0, -1.0] | +3,891 [+3,891, +3,891] | -33,948 [-33,948, -33,948] | -2.0 [-2.0, -2.0] | 1/1, 1/1 | +3,891 tokens, $+0.00004 |
| L | schema | 1 | +0.0 [+0.0, +0.0] | +1,649 [+1,649, +1,649] | +8,397 [+8,397, +8,397] | +0.0 [+0.0, +0.0] | 1/1, 1/1 | +1,649 tokens, $+0.00002 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

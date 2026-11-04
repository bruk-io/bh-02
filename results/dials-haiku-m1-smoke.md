# Dials haiku-m1-smoke: claude-haiku-5-5, the same tasks native and under each setting

## Band M (median input 4,406 tokens)

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 2 | - | 50% | 54,584 | 194,149 | 40,066 | 154,074 | - | $0.0102 | 14.1s |
| sample | 2 | 1/2 | +0% [+0%, +0%], 0/0 | -2,150 [-10,914, +6,613] | +24,936 [-10,924, +60,797] | -2,150 [-10,914, +6,613] | +27,086 [-10, +54,182] | -2,150 ($-0.00002) | -2% ($-0.0002) | -3.4 [-6.5, -0.2]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band L (median input 27,422 tokens)

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 2 | - | 50% | 51,793 | 290,174 | 37,276 | 252,887 | - | $0.0111 | 25.8s |
| sample | 2 | 2/2 | +0% [+0%, +0%], 0/0 | -586 [-1,842, +670] | -95,400 [-143,338, -47,463] | -586 [-1,842, +670] | -94,810 [-141,490, -48,131] | -586 ($-0.00001) | -11% ($-0.0013) | -7.4 [-13.1, -1.6]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 4 | - | 50% | 52,962 | 242,162 | 38,671 | 203,481 | - | $0.0107 | 19.9s |
| sample | 4 | 3/4 | +0% [+0%, +0%], 0/0 | -1,368 [-8,018, +4,499] | -35,232 [-110,234, +33,732] | -1,368 [-8,018, +4,499] | -33,862 [-106,120, +28,604] | -586 ($-0.00001) | -7% ($-0.0007) | -5.4 [-10.3, -0.9]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Only the pairs where the envelope acted

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 4 | - | 50% | 52,962 | 242,162 | 38,671 | 203,481 | - | $0.0107 | 19.9s |
| sample | 3 | 3/4 | +0% [-19%, +19%], 0/0 | -4,029 [-10,914, +670] | -67,242 [-143,338, -10,924] | -4,029 [-10,914, +670] | -63,210 [-141,490, -10] | -1,842 ($-0.00002) | -14% ($-0.0016) | -5.0 [-13.1, -0.2]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

8 runs, $0.08; 8 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| atlas | claims | M | native | 0/1 [0%, 79%] | $0.0075 | 50742 | 3 | 0/1 | 0/1 |
| atlas | claims | M | sample | 0/1 [0%, 79%] | $0.0093 | 57355 | 7 | 0/1 | 0/1 |
| atlas | claims | L | native | 0/1 [0%, 79%] | $0.0096 | 55182 | 7 | 0/1 | 0/1 |
| atlas | claims | L | sample | 0/1 [0%, 79%] | $0.0093 | 55852 | 5 | 0/1 | 0/1 |
| json | count | M | native | 1/1 [21%, 100%] | $0.0130 | 58426 | 1 | 0/1 | 0/1 |
| json | count | M | sample | 1/1 [21%, 100%] | $0.0107 | 47512 | 1 | 0/1 | 0/1 |
| log | count | L | native | 1/1 [21%, 100%] | $0.0127 | 48404 | 5 | 1/1 | 0/1 |
| log | count | L | sample | 1/1 [21%, 100%] | $0.0104 | 46562 | 1 | 0/1 | 0/1 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| atlas | M | sample | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0019 [+0.0019, +0.0019] | +6613 [+6613, +6613] | +60797 [+60797, +60797] | -6.5s [-6.5, -6.5] | fails (indicative: under 30 pairs) |
| atlas | L | sample | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0003 [-0.0003, -0.0003] | +670 [+670, +670] | -47463 [-47463, -47463] | -1.6s [-1.6, -1.6] | fails (indicative: under 30 pairs) |
| json | M | sample | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0023 [-0.0023, -0.0023] | -10914 [-10914, -10914] | -10924 [-10924, -10924] | -0.2s [-0.2, -0.2] | undecided (indicative: under 30 pairs) |
| log | L | sample | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0022 [-0.0022, -0.0022] | -1842 [-1842, -1842] | -143338 [-143338, -143338] | -13.1s [-13.1, -13.1] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | sample | 2 | +0% [+0%, +0%] | 0/0, p 1.00 | $-0.0002 [-0.0023, +0.0019] | -2150 [-10914, +6613] | +24936 [-10924, +60797] | -3.4s [-6.5, -0.2] | undecided (indicative: under 30 pairs) |
| L | sample | 2 | +0% [+0%, +0%] | 0/0, p 1.00 | $-0.0013 [-0.0022, -0.0003] | -586 [-1842, +670] | -95400 [-143338, -47463] | -7.4s [-13.1, -1.6] | undecided (indicative: under 30 pairs) |

## When the envelope acted: the pairs whose folded session folded the task's large output

| band | condition | acted | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| M | sample | 1/2 (saw it 1) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0023 [-0.0023, -0.0023] | -10914 [-10914, -10914] | -10924 [-10924, -10924] | -0.2s [-0.2, -0.2] | undecided (indicative: under 30 pairs) |
| L | sample | 2/2 (saw it 2) | 2 | +0% [+0%, +0%] | 0/0, p 1.00 | $-0.0013 [-0.0022, -0.0003] | -586 [-1842, +670] | -95400 [-143338, -47463] | -7.4s [-13.1, -1.6] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, 2026-11-03); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | sample | 2 | +0.5 [+0.0, +1.0] | -2,150 [-10,914, +6,613] | +27,086 [-10, +54,182] | +1.0 [+0.0, +2.0] | 1/2, 1/2 | -2,150 tokens, $-0.00002 |
| L | sample | 2 | -2.0 [-3.0, -1.0] | -586 [-1,842, +670] | -94,810 [-141,490, -48,131] | -4.0 [-6.0, -2.0] | 1/2, 1/2 | -586 tokens, $-0.00001 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

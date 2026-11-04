# Dials sonnet-atlas: claude-sonnet-5-5, the same tasks native and under each setting

## Band M (median input 4,674 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 84 | 51% | 51,264 | 242,241 | 23,904 | 218,325 | - | $0.1304 | 24.2s |
| fold | 84 | +0% [-8%, +8%], 6/6 | -4,097 [-5,582, -2,687] | -6,768 [-48,031, +24,801] | -4,332 [-5,819, -2,919] | -2,436 [-42,751, +28,528] | -2,498 ($-0.00042) | -14% ($-0.0179) | -0.5 [-6.2, +4.0]s |
| schema | 84 | +1% [-7%, +9%], 7/6 | -4,041 [-5,567, -2,625] | -2,684 [-34,947, +22,871] | -4,314 [-5,843, -2,921] | +1,630 [-29,479, +26,756] | -2,117 ($-0.00036) | -13% ($-0.0170) | -0.7 [-5.3, +3.1]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.170 per million, as these runs' costs imply).

## Band L (median input 37,541 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 34 | 47% | 48,480 | 304,176 | 21,664 | 282,497 | - | $0.1337 | 28.1s |
| fold | 34 | +0% [-15%, +15%], 4/4 | -550 [-1,807, +619] | -8,357 [-36,244, +18,987] | -806 [-2,069, +354] | -7,551 [-35,011, +19,526] | +40 ($+0.00001) | -4% ($-0.0049) | -0.5 [-3.6, +2.7]s |
| schema | 34 | +0% [-11%, +11%], 2/2 | +971 [-287, +2,100] | +5,402 [-14,560, +28,106] | +675 [-569, +1,814] | +4,727 [-14,787, +27,052] | +476 ($+0.00008) | +2% ($+0.0033) | +2.4 [-1.8, +7.9]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.165 per million, as these runs' costs imply).

## Every band together

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 118 | 50% | 50,338 | 260,087 | 23,259 | 236,815 | - | $0.1313 | 25.3s |
| fold | 118 | +0% [-7%, +7%], 10/10 | -3,075 [-4,329, -2,017] | -7,226 [-35,999, +16,475] | -3,316 [-4,579, -2,250] | -3,910 [-31,831, +19,212] | -408 ($-0.00007) | -11% ($-0.0141) | -0.5 [-4.6, +2.8]s |
| schema | 118 | +1% [-6%, +8%], 9/8 | -2,596 [-3,897, -1,471] | -354 [-23,678, +19,546] | -2,877 [-4,176, -1,745] | +2,523 [-20,033, +21,974] | -23 ($-0.00000) | -9% ($-0.0112) | +0.2 [-3.1, +3.3]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.169 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-sonnet-5-5)

354 runs, $43.50; 354 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 1 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| atlas | claims | M | fold | 43/84 [41%, 62%] | $0.1123 | 47814 | 4.0 | 38/84 | 0/84 |
| atlas | claims | M | native | 43/84 [41%, 62%] | $0.1268 | 51264 | 3.0 | 0/84 | 0/84 |
| atlas | claims | M | schema | 44/84 [42%, 63%] | $0.1137 | 47844 | 4.0 | 42/84 | 0/84 |
| atlas | claims | L | fold | 16/34 [31%, 63%] | $0.1265 | 49317 | 6.0 | 8/34 | 0/34 |
| atlas | claims | L | native | 16/34 [31%, 63%] | $0.1321 | 48479 | 6.5 | 11/34 | 0/34 |
| atlas | claims | L | schema | 16/34 [31%, 63%] | $0.1337 | 51284 | 7.0 | 13/34 | 0/34 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| atlas | M | fold | 84 | +0% [-8%, +8%] | 6/6, p 1.00 | $-0.0042 [-0.0157, -0.0016] | -2498 [-4745, -195] | +949 [+1, +18871] | +1.5s [+0.5, +3.9] | undecided |
| atlas | M | schema | 84 | +1% [-7%, +9%] | 7/6, p 1.00 | $-0.0079 [-0.0141, -0.0022] | -2117 [-3597, -5] | +438 [+4, +17380] | +1.4s [+0.4, +2.1] | undecided |
| atlas | L | fold | 34 | +0% [-15%, +15%] | 4/4, p 1.00 | $-0.0023 [-0.0093, +0.0004] | +40 [-322, +565] | -2 [-1594, +1018] | -0.3s [-2.0, +2.2] | undecided |
| atlas | L | schema | 34 | +0% [-11%, +11%] | 2/2, p 1.00 | $+0.0001 [-0.0030, +0.0066] | +476 [-9, +1160] | +12 [-948, +10561] | +2.2s [-3.5, +4.5] | undecided |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | fold | 84 | +0% [-8%, +8%] | 6/6, p 1.00 | $-0.0042 [-0.0157, -0.0016] | -2498 [-4745, -195] | +949 [+1, +18871] | +1.5s [+0.5, +3.9] | undecided |
| M | schema | 84 | +1% [-7%, +9%] | 7/6, p 1.00 | $-0.0079 [-0.0141, -0.0022] | -2117 [-3597, -5] | +438 [+4, +17380] | +1.4s [+0.4, +2.1] | undecided |
| L | fold | 34 | +0% [-15%, +15%] | 4/4, p 1.00 | $-0.0023 [-0.0093, +0.0004] | +40 [-322, +565] | -2 [-1594, +1018] | -0.3s [-2.0, +2.2] | undecided |
| L | schema | 34 | +0% [-11%, +11%] | 2/2, p 1.00 | $+0.0001 [-0.0030, +0.0066] | +476 [-9, +1160] | +12 [-948, +10561] | +2.2s [-3.5, +4.5] | undecided |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $1.693 per million tokens (80% of runs between $1.594 and $1.790); too spread to price a read.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | fold | 84 | +0.2 [-0.6, +0.7] | -4,332 [-5,819, -2,919] | -2,436 [-42,751, +28,528] | +0.3 [-1.2, +1.5] | 84/84, 84/84 | -2,498 tokens |
| M | schema | 84 | +0.2 [-0.3, +0.7] | -4,314 [-5,843, -2,921] | +1,630 [-29,479, +26,756] | +0.5 [-0.7, +1.4] | 84/84, 84/84 | -2,117 tokens |
| L | fold | 34 | -0.2 [-0.7, +0.4] | -806 [-2,069, +354] | -7,551 [-35,011, +19,526] | -0.5 [-1.6, +0.6] | 34/34, 34/34 | +40 tokens |
| L | schema | 34 | +0.1 [-0.4, +0.5] | +675 [-569, +1,814] | +4,727 [-14,787, +27,052] | +0.1 [-0.8, +1.1] | 34/34, 34/34 | +476 tokens |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

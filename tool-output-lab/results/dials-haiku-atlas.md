# Dials haiku-atlas: claude-haiku-5-5, the same tasks native and under each setting

## Band M (median input 4,674 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 84 | 46% | 53,534 | 295,177 | 25,304 | 269,861 | - | $0.0088 | 19.4s |
| fold | 84 | +0% [-10%, +10%], 10/10 | -3,478 [-4,970, -2,023] | -6,079 [-35,618, +25,646] | -3,697 [-5,194, -2,266] | -2,383 [-31,319, +28,683] | -1,112 ($-0.00001) | -8% ($-0.0007) | +1.2 [-1.9, +4.4]s |
| schema | 84 | +1% [-7%, +9%], 7/6 | -2,895 [-4,380, -1,518] | +17,540 [-7,711, +44,666] | -3,192 [-4,687, -1,806] | +20,731 [-4,239, +47,554] | -584 ($-0.00001) | -3% ($-0.0003) | +2.2 [+0.2, +4.1]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band L (median input 37,541 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 34 | 53% | 52,918 | 364,629 | 24,115 | 340,500 | - | $0.0099 | 29.4s |
| fold | 34 | +0% [-11%, +11%], 2/2 | -287 [-1,196, +566] | -45,177 [-104,464, -501] | -1,348 [-3,760, +199] | -43,828 [-100,799, -249] | +14 ($+0.00000) | -7% ($-0.0007) | -4.7 [-14.3, +2.6]s |
| schema | 34 | +0% [-11%, +11%], 2/2 | -17 [-1,312, +1,193] | -50,188 [-102,694, -12,971] | -1,348 [-4,008, +518] | -48,838 [-98,547, -12,431] | -116 ($-0.00000) | -5% ($-0.0005) | -5.7 [-14.8, +0.9]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 118 | 48% | 53,507 | 315,189 | 24,962 | 290,215 | - | $0.0091 | 22.3s |
| fold | 118 | +0% [-8%, +8%], 12/12 | -2,559 [-3,692, -1,509] | -17,345 [-44,600, +8,943] | -3,020 [-4,287, -1,878] | -14,324 [-40,862, +11,161] | -682 ($-0.00001) | -8% ($-0.0007) | -0.5 [-4.0, +2.8]s |
| schema | 118 | +1% [-6%, +8%], 9/8 | -2,066 [-3,209, -1,051] | -1,974 [-25,355, +20,211] | -2,660 [-3,931, -1,460] | +686 [-22,369, +22,385] | -352 ($-0.00000) | -3% ($-0.0003) | -0.1 [-3.2, +2.6]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

354 runs, $3.12; 354 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| atlas | claims | M | fold | 39/84 [36%, 57%] | $0.0082 | 50658 | 6.0 | 31/84 | 0/84 |
| atlas | claims | M | native | 39/84 [36%, 57%] | $0.0085 | 53534 | 5.0 | 1/84 | 0/84 |
| atlas | claims | M | schema | 40/84 [37%, 58%] | $0.0081 | 50495 | 6.0 | 36/84 | 0/84 |
| atlas | claims | L | fold | 18/34 [37%, 69%] | $0.0093 | 52140 | 7.0 | 14/34 | 0/34 |
| atlas | claims | L | native | 18/34 [37%, 69%] | $0.0097 | 52918 | 8.0 | 16/34 | 0/34 |
| atlas | claims | L | schema | 18/34 [37%, 69%] | $0.0091 | 52396 | 6.5 | 15/34 | 0/34 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| atlas | M | fold | 84 | +0% [-10%, +10%] | 10/10, p 1.00 | $-0.0004 [-0.0010, -0.0001] | -1112 [-3275, -642] | -846 [-16829, +6] | +0.8s [-0.3, +2.1] | undecided |
| atlas | M | schema | 84 | +1% [-7%, +9%] | 7/6, p 1.00 | $-0.0001 [-0.0005, +0.0001] | -584 [-1576, -6] | +306 [-4, +10646] | +1.6s [+0.0, +3.1] | undecided |
| atlas | L | fold | 34 | +0% [-11%, +11%] | 2/2, p 1.00 | $-0.0000 [-0.0013, +0.0003] | +14 [-385, +638] | +365 [-59614, +9418] | +0.1s [-4.2, +4.2] | undecided |
| atlas | L | schema | 34 | +0% [-11%, +11%] | 2/2, p 1.00 | $-0.0003 [-0.0007, -0.0000] | -116 [-618, +411] | -1321 [-73622, +1065] | -1.4s [-3.9, +0.3] | undecided |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | fold | 84 | +0% [-10%, +10%] | 10/10, p 1.00 | $-0.0004 [-0.0010, -0.0001] | -1112 [-3275, -642] | -846 [-16829, +6] | +0.8s [-0.3, +2.1] | undecided |
| M | schema | 84 | +1% [-7%, +9%] | 7/6, p 1.00 | $-0.0001 [-0.0005, +0.0001] | -584 [-1576, -6] | +306 [-4, +10646] | +1.6s [+0.0, +3.1] | undecided |
| L | fold | 34 | +0% [-11%, +11%] | 2/2, p 1.00 | $-0.0000 [-0.0013, +0.0003] | +14 [-385, +638] | +365 [-59614, +9418] | +0.1s [-4.2, +4.2] | undecided |
| L | schema | 34 | +0% [-11%, +11%] | 2/2, p 1.00 | $-0.0003 [-0.0007, -0.0000] | -116 [-618, +411] | -1321 [-73622, +1065] | -1.4s [-3.9, +0.3] | undecided |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | fold | 84 | +0.1 [-0.4, +0.7] | -3,697 [-5,194, -2,266] | -2,383 [-31,319, +28,683] | +0.3 [-0.8, +1.4] | 84/84, 84/84 | -1,112 tokens, $-0.00001 |
| M | schema | 84 | +0.6 [+0.1, +1.1] | -3,192 [-4,687, -1,806] | +20,731 [-4,239, +47,554] | +1.1 [+0.2, +2.2] | 84/84, 84/84 | -584 tokens, $-0.00001 |
| L | fold | 34 | -0.6 [-1.3, +0.0] | -1,348 [-3,760, +199] | -43,828 [-100,799, -249] | -1.8 [-3.8, -0.2] | 34/34, 34/34 | +14 tokens, $+0.00000 |
| L | schema | 34 | -0.4 [-1.0, +0.3] | -1,348 [-4,008, +518] | -48,838 [-98,547, -12,431] | -1.9 [-3.6, -0.5] | 34/34, 34/34 | -116 tokens, $-0.00000 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

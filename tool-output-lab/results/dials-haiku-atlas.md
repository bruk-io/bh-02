# Dials haiku-atlas: claude-haiku-5-5, the same tasks native and under each setting

## Band M (median input 4,674 tokens)

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 84 | - | 54% | 53,078 | 269,790 | 25,083 | 244,696 | - | $0.0086 | 14.9s |
| sample | 84 | 46/84 | -10% [-17%, -2%], 2/10 | -3,017 [-4,555, -1,550] | +28,692 [+3,354, +54,929] | -3,305 [-4,842, -1,834] | +31,996 [+7,192, +57,567] | -858 ($-0.00001) | -2% ($-0.0002) | +2.8 [+1.2, +4.8]s |
| schema | 84 | 44/84 | -1% [-11%, +8%], 8/9 | -2,623 [-4,072, -1,252] | +37,151 [+13,262, +61,427] | -2,942 [-4,417, -1,557] | +40,091 [+16,368, +64,142] | -1,008 ($-0.00001) | -0% ($-0.0000) | +5.6 [+2.4, +10.2]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band L (median input 37,541 tokens)

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 34 | - | 53% | 53,867 | 362,949 | 25,026 | 337,908 | - | $0.0101 | 24.5s |
| sample | 34 | 17/34 | +3% [-12%, +17%], 4/3 | -1,590 [-3,136, -49] | -33,208 [-77,274, +11,574] | -1,904 [-3,443, -382] | -31,303 [-74,130, +12,486] | -242 ($-0.00000) | -10% ($-0.0010) | +0.6 [-7.7, +11.2]s |
| schema | 34 | 15/34 | +0% [-11%, +11%], 2/2 | -1,405 [-2,927, -91] | -32,932 [-75,410, +4,733] | -1,719 [-3,273, -403] | -31,211 [-72,533, +4,949] | -544 ($-0.00001) | -9% ($-0.0009) | -3.2 [-8.1, +0.2]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 118 | - | 53% | 53,116 | 296,632 | 25,067 | 271,554 | - | $0.0090 | 17.6s |
| sample | 118 | 63/118 | -6% [-13%, +1%], 6/13 | -2,606 [-3,782, -1,524] | +10,857 [-11,585, +33,391] | -2,901 [-4,082, -1,813] | +13,757 [-8,098, +36,118] | -649 ($-0.00001) | -5% ($-0.0004) | +2.2 [-0.5, +5.5]s |
| schema | 118 | 59/118 | -1% [-8%, +7%], 10/11 | -2,272 [-3,358, -1,239] | +16,958 [-4,095, +39,410] | -2,590 [-3,673, -1,550] | +19,546 [-1,280, +41,495] | -814 ($-0.00001) | -3% ($-0.0003) | +3.1 [+0.1, +6.6]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Only the pairs where the envelope acted

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 118 | - | 53% | 53,116 | 296,632 | 25,067 | 271,554 | - | $0.0090 | 17.6s |
| sample | 63 | 63/118 | -2% [-12%, +9%], 5/6 | -3,928 [-5,628, -2,229] | +24,770 [-7,522, +56,507] | -4,212 [-5,934, -2,502] | +28,981 [-2,806, +59,524] | -3,652 ($-0.00004) | -5% ($-0.0005) | +1.5 [-1.6, +3.9]s |
| schema | 59 | 59/118 | +0% [-12%, +12%], 7/7 | -3,788 [-5,527, -2,097] | +37,283 [+5,504, +67,426] | -4,102 [-5,811, -2,392] | +41,383 [+9,889, +70,868] | -2,964 ($-0.00003) | -3% ($-0.0003) | +4.8 [+1.2, +10.6]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

354 runs, $3.10; 354 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| atlas | claims | M | native | 45/84 [43%, 64%] | $0.0088 | 53078 | 5.0 | 0/84 | 0/84 |
| atlas | claims | M | sample | 37/84 [34%, 55%] | $0.0085 | 50455 | 6.0 | 33/84 | 0/84 |
| atlas | claims | M | schema | 44/84 [42%, 63%] | $0.0081 | 50720 | 5.0 | 36/84 | 0/84 |
| atlas | claims | L | native | 18/34 [37%, 69%] | $0.0097 | 53867 | 8.0 | 16/34 | 0/34 |
| atlas | claims | L | sample | 19/34 [39%, 71%] | $0.0091 | 51976 | 7.0 | 14/34 | 0/34 |
| atlas | claims | L | schema | 18/34 [37%, 69%] | $0.0090 | 51674 | 7.0 | 11/34 | 0/34 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| atlas | M | sample | 84 | -10% [-17%, -2%] | 2/10, p 0.04 | $-0.0001 [-0.0005, +0.0001] | -858 [-2123, +1] | +2010 [-0, +46514] | +1.3s [+0.6, +2.2] | undecided |
| atlas | M | schema | 84 | -1% [-11%, +8%] | 8/9, p 1.00 | $-0.0000 [-0.0004, +0.0002] | -1008 [-2468, -52] | +28928 [+87, +47724] | +2.3s [+1.4, +4.1] | undecided |
| atlas | L | sample | 34 | +3% [-12%, +17%] | 4/3, p 1.00 | $-0.0007 [-0.0012, +0.0000] | -242 [-1406, +66] | -46268 [-53776, -140] | -0.9s [-2.8, +0.5] | undecided |
| atlas | L | schema | 34 | +0% [-11%, +11%] | 2/2, p 1.00 | $-0.0001 [-0.0009, -0.0000] | -544 [-1556, -166] | -844 [-44506, +80] | -0.1s [-1.7, +0.8] | undecided |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | sample | 84 | -10% [-17%, -2%] | 2/10, p 0.04 | $-0.0001 [-0.0005, +0.0001] | -858 [-2123, +1] | +2010 [-0, +46514] | +1.3s [+0.6, +2.2] | undecided |
| M | schema | 84 | -1% [-11%, +8%] | 8/9, p 1.00 | $-0.0000 [-0.0004, +0.0002] | -1008 [-2468, -52] | +28928 [+87, +47724] | +2.3s [+1.4, +4.1] | undecided |
| L | sample | 34 | +3% [-12%, +17%] | 4/3, p 1.00 | $-0.0007 [-0.0012, +0.0000] | -242 [-1406, +66] | -46268 [-53776, -140] | -0.9s [-2.8, +0.5] | undecided |
| L | schema | 34 | +0% [-11%, +11%] | 2/2, p 1.00 | $-0.0001 [-0.0009, -0.0000] | -544 [-1556, -166] | -844 [-44506, +80] | -0.1s [-1.7, +0.8] | undecided |

## When the envelope acted: the pairs whose folded session folded the task's large output

| band | condition | acted | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| M | sample | 46/84 (saw it 46) | 46 | -7% [-17%, +4%] | 2/5, p 0.45 | $-0.0004 [-0.0008, +0.0002] | -4452 [-8080, -1800] | +52954 [+7358, +75091] | +3.3s [+1.4, +4.7] | undecided |
| M | schema | 44/84 (saw it 44) | 44 | +0% [-15%, +15%] | 6/6, p 1.00 | $-0.0003 [-0.0010, +0.0005] | -3729 [-6928, -2308] | +46730 [+10202, +83806] | +4.4s [+2.4, +5.2] | undecided |
| L | sample | 17/34 (saw it 17) | 17 | +12% [-10%, +31%] | 3/1, p 0.62 | $-0.0011 [-0.0030, +0.0008] | -806 [-8061, +331] | -51511 [-87175, +58677] | -2.0s [-7.9, +4.5] | undecided (indicative: under 30 pairs) |
| L | schema | 15/34 (saw it 15) | 15 | +0% [-17%, +17%] | 1/1, p 1.00 | $-0.0009 [-0.0032, -0.0000] | -1078 [-2120, -345] | -12920 [-134692, -1256] | -0.9s [-6.0, +0.7] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, 2026-11-03); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | sample | 84 | +0.8 [+0.3, +1.2] | -3,305 [-4,842, -1,834] | +31,996 [+7,192, +57,567] | +1.5 [+0.5, +2.5] | 84/84, 84/84 | -858 tokens, $-0.00001 |
| M | schema | 84 | +0.9 [+0.4, +1.3] | -2,942 [-4,417, -1,557] | +40,091 [+16,368, +64,142] | +1.8 [+0.8, +2.7] | 84/84, 84/84 | -1,008 tokens, $-0.00001 |
| L | sample | 34 | -0.6 [-1.3, +0.2] | -1,904 [-3,443, -382] | -31,303 [-74,130, +12,486] | -1.1 [-2.6, +0.4] | 34/34, 34/34 | -242 tokens, $-0.00000 |
| L | schema | 34 | -0.6 [-1.3, +0.1] | -1,719 [-3,273, -403] | -31,211 [-72,533, +4,949] | -1.1 [-2.5, +0.2] | 34/34, 34/34 | -544 tokens, $-0.00001 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

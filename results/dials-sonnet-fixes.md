# Dials sonnet-fixes: claude-sonnet-5-5, the same tasks native and under each setting

## Band M (median input 6,480 tokens)

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 20 | - | 0/20 | 100% | 56,934 | 137,317 | 32,807 | 104,503 | - | $0.1444 | 10.0s |
| fixed | 20 | 20/20 | 8/20 | +0% [-16%, +16%], 0/0 | -10,290 [-12,025, -7,705] | +27,987 [+2,186, +56,697] | -10,323 [-12,054, -7,716] | +38,307 [+13,809, +64,598] | -11,609 ($-0.00212) | -24% ($-0.0350) | +2.5 [+1.0, +4.3]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.183 per million, as these runs' costs imply).

## Band L (median input 35,289 tokens)

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 20 | - | 20/20 | 95% | 47,342 | 252,075 | 23,342 | 228,721 | - | $0.1267 | 17.0s |
| fixed | 20 | 20/20 | 11/20 | +5% [-12%, +24%], 1/0 | -6,038 [-10,546, -2,669] | -82,303 [-109,424, -54,205] | -6,038 [-10,546, -2,669] | -76,263 [-103,364, -46,638] | -1,708 ($-0.00029) | -29% ($-0.0366) | -5.7 [-7.6, -3.8]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.170 per million, as these runs' costs imply).

## Every band together

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 40 | - | 20/40 | 98% | 56,141 | 194,696 | 28,075 | 166,612 | - | $0.1356 | 13.5s |
| fixed | 40 | 40/40 | 19/40 | +2% [-7%, +13%], 1/0 | -8,164 [-10,713, -5,802] | -27,158 [-51,843, -1,275] | -8,180 [-10,713, -5,805] | -18,978 [-43,933, +7,155] | -10,256 ($-0.00179) | -26% ($-0.0358) | -1.6 [-3.3, +0.2]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.175 per million, as these runs' costs imply).

## Only the pairs where the envelope acted

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 40 | - | 20/40 | 98% | 56,141 | 194,696 | 28,075 | 166,612 | - | $0.1356 | 13.5s |
| fixed | 40 | 40/40 | 19/40 | +2% [-7%, +13%], 1/0 | -8,164 [-10,713, -5,802] | -27,158 [-51,843, -1,275] | -8,180 [-10,713, -5,805] | -18,978 [-43,933, +7,155] | -10,256 ($-0.00179) | -26% ($-0.0358) | -1.6 [-3.3, +0.2]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.175 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-sonnet-5-5)

80 runs, $9.41; 80 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | M | fixed | 1/1 [21%, 100%] | $0.1239 | 49230 | 5 | 1/1 | 0/1 |
| a11y | absent | M | native | 1/1 [21%, 100%] | $0.1165 | 55460 | 1 | 0/1 | 0/1 |
| a11y | absent | L | fixed | 1/1 [21%, 100%] | $0.1286 | 48447 | 7 | 1/1 | 0/1 |
| a11y | absent | L | native | 1/1 [21%, 100%] | $0.1630 | 60701 | 4 | 1/1 | 0/1 |
| a11y | spot | M | fixed | 4/4 [51%, 100%] | $0.0816 | 45380 | 1.0 | 1/4 | 0/4 |
| a11y | spot | M | native | 4/4 [51%, 100%] | $0.1212 | 55616 | 1.0 | 0/4 | 0/4 |
| a11y | spot | L | fixed | 4/4 [51%, 100%] | $0.0823 | 45581 | 1.5 | 2/4 | 0/4 |
| a11y | spot | L | native | 4/4 [51%, 100%] | $0.1753 | 63255 | 4.0 | 4/4 | 0/4 |
| figma | absent | M | fixed | 1/1 [21%, 100%] | $0.1956 | 67465 | 4 | 1/1 | 0/1 |
| figma | absent | M | native | 1/1 [21%, 100%] | $0.1266 | 56633 | 1 | 0/1 | 0/1 |
| figma | absent | L | fixed | 1/1 [21%, 100%] | $0.1137 | 47271 | 4 | 1/1 | 0/1 |
| figma | absent | L | native | 1/1 [21%, 100%] | $0.1110 | 46997 | 4 | 1/1 | 0/1 |
| figma | spot | M | fixed | 4/4 [51%, 100%] | $0.0943 | 45931 | 2.5 | 3/4 | 0/4 |
| figma | spot | M | native | 4/4 [51%, 100%] | $0.1267 | 56645 | 1.0 | 0/4 | 0/4 |
| figma | spot | L | fixed | 4/4 [51%, 100%] | $0.0926 | 46581 | 2.5 | 4/4 | 0/4 |
| figma | spot | L | native | 3/4 [30%, 95%] | $0.1085 | 47274 | 4.0 | 4/4 | 0/4 |
| json | absent | M | fixed | 1/1 [21%, 100%] | $0.0808 | 45311 | 1 | 0/1 | 0/1 |
| json | absent | M | native | 1/1 [21%, 100%] | $0.1222 | 57222 | 1 | 0/1 | 0/1 |
| json | absent | L | fixed | 1/1 [21%, 100%] | $0.0955 | 46843 | 2 | 1/1 | 0/1 |
| json | absent | L | native | 1/1 [21%, 100%] | $0.1114 | 47132 | 4 | 1/1 | 0/1 |
| json | spot | M | fixed | 4/4 [51%, 100%] | $0.1865 | 45227 | 1.0 | 0/4 | 0/4 |
| json | spot | M | native | 4/4 [51%, 100%] | $0.2377 | 57421 | 1.0 | 0/4 | 0/4 |
| json | spot | L | fixed | 4/4 [51%, 100%] | $0.0767 | 45242 | 1.0 | 0/4 | 0/4 |
| json | spot | L | native | 4/4 [51%, 100%] | $0.1014 | 46950 | 3.0 | 4/4 | 0/4 |
| log | absent | M | fixed | 1/1 [21%, 100%] | $0.0997 | 46443 | 3 | 1/1 | 0/1 |
| log | absent | M | native | 1/1 [21%, 100%] | $0.1377 | 59362 | 1 | 0/1 | 0/1 |
| log | absent | L | fixed | 1/1 [21%, 100%] | $0.0896 | 45746 | 2 | 1/1 | 0/1 |
| log | absent | L | native | 1/1 [21%, 100%] | $0.1115 | 47052 | 4 | 1/1 | 0/1 |
| log | spot | M | fixed | 4/4 [51%, 100%] | $0.0828 | 45372 | 1.0 | 1/4 | 0/4 |
| log | spot | M | native | 4/4 [51%, 100%] | $0.1376 | 59364 | 1.0 | 0/4 | 0/4 |
| log | spot | L | fixed | 4/4 [51%, 100%] | $0.0814 | 45335 | 1.0 | 1/4 | 0/4 |
| log | spot | L | native | 4/4 [51%, 100%] | $0.1075 | 47500 | 3.5 | 4/4 | 0/4 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | M | fixed | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0394 [-0.0412, +0.0073] | -10245 [-10283, -6230] | -10245 [-10283, +179335] | +1.2s [-0.6, +13.2] | undecided (indicative: under 30 pairs) |
| a11y | L | fixed | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0882 [-0.1428, -0.0344] | -15072 [-36448, -12254] | -133782 [-194286, +54293] | -6.9s [-11.3, +3.9] | undecided (indicative: under 30 pairs) |
| figma | M | fixed | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0305 [-0.0444, +0.0690] | -10449 [-11307, +10832] | +80579 [-11303, +180272] | +3.4s [+0.0, +10.3] | undecided (indicative: under 30 pairs) |
| figma | L | fixed | 5 | +20% [-26%, +62%] | 1/0, p 1.00 | $-0.0034 [-0.0222, +0.0027] | -447 [-1877, +274] | -1204 [-95853, +535] | -1.4s [-6.0, +2.7] | undecided (indicative: under 30 pairs) |
| json | M | fixed | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0484 [-0.0542, -0.0414] | -12059 [-12256, -11911] | -12057 [-56851, +32686] | +1.1s [-2.8, +2.1] | undecided (indicative: under 30 pairs) |
| json | L | fixed | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0227 [-0.0266, -0.0159] | -1624 [-2369, -289] | -93267 [-137407, -92454] | -7.2s [-7.8, -5.9] | undecided (indicative: under 30 pairs) |
| log | M | fixed | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0543 [-0.0560, -0.0380] | -13964 [-14063, -12919] | -13960 [-14081, +78500] | +0.6s [-0.1, +3.9] | undecided (indicative: under 30 pairs) |
| log | L | fixed | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0219 [-0.0465, -0.0147] | -1401 [-4277, -601] | -93464 [-151975, -91296] | -9.1s [-13.9, -6.3] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | fixed | 20 | +0% [-16%, +16%] | 0/0, p 1.00 | $-0.0413 [-0.0483, -0.0386] | -11609 [-12196, -10276] | -10252 [-12054, +35160] | +1.5s [+0.5, +3.0] | undecided (indicative: under 30 pairs) |
| L | fixed | 20 | +5% [-12%, +24%] | 1/0, p 1.00 | $-0.0224 [-0.0338, -0.0195] | -1708 [-4277, -1354] | -93070 [-114868, -50480] | -6.8s [-7.6, -5.9] | undecided (indicative: under 30 pairs) |

## When the envelope acted: the pairs whose folded session folded the task's large output

| band | condition | acted | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| M | fixed | 20/20 (saw it 20) | 20 | +0% [-16%, +16%] | 0/0, p 1.00 | $-0.0413 [-0.0483, -0.0386] | -11609 [-12196, -10276] | -10252 [-12054, +35160] | +1.5s [+0.5, +3.0] | undecided (indicative: under 30 pairs) |
| L | fixed | 20/20 (saw it 20) | 20 | +5% [-12%, +24%] | 1/0, p 1.00 | $-0.0224 [-0.0338, -0.0195] | -1708 [-4277, -1354] | -93070 [-114868, -50480] | -6.8s [-7.6, -5.9] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, 2026-11-03); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $1.745 per million tokens (80% of runs between $1.633 and $1.882); too spread to price a read.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | fixed | 20 | +0.8 [+0.3, +1.4] | -10,323 [-12,054, -7,716] | +38,307 [+13,809, +64,598] | +1.7 [+0.5, +3.0] | 17/20, 17/20 | -11,609 tokens |
| L | fixed | 20 | -1.5 [-2.0, -0.8] | -6,038 [-10,546, -2,669] | -76,263 [-103,364, -46,638] | -2.4 [-3.7, -0.9] | 20/20, 20/20 | -1,708 tokens |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

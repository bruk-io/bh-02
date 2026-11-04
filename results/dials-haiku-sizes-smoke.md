# Dials haiku-sizes-smoke: claude-haiku-5-5, the same tasks native and under each setting

## Band XL (median input 74,928 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 1 | 100% | 48,945 | 280,546 | 19,263 | 261,271 | - | $0.0074 | 11.0s |
| all-2000 | 1 | +0% [-79%, +79%], 0/0 | +681 [+681, +681] | -91,123 [-91,123, -91,123] | +681 [+681, +681] | -91,800 [-91,800, -91,800] | +681 ($+0.00001) | -18% ($-0.0013) | -0.0 [-0.0, -0.0]s |
| all-6000 | 1 | +0% [-79%, +79%], 0/0 | +7,548 [+7,548, +7,548] | -77,386 [-77,386, -77,386] | +7,548 [+7,548, +7,548] | -84,930 [-84,930, -84,930] | +7,548 ($+0.00008) | +2% ($+0.0002) | -1.6 [-1.6, -1.6]s |
| all-schema | 0 | - | - | - | - | - | - | - | - |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band XXL (median input 589,457 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 3 | 100% | 47,458 | 247,502 | 18,371 | 229,120 | - | $0.0066 | 11.1s |
| all-2000 | 3 | +0% [-56%, +56%], 0/0 | +1,781 [-1,703, +3,808] | -41,765 [-96,188, +8,145] | +1,572 [-1,703, +3,808] | -43,334 [-94,481, +4,337] | +3,237 ($+0.00003) | -4% ($-0.0003) | +0.8 [-1.8, +4.8]s |
| all-6000 | 3 | +0% [-56%, +56%], 0/0 | +4,045 [-1,241, +9,449] | -35,291 [-95,737, +8,360] | +3,836 [-1,241, +8,822] | -39,125 [-94,492, +4,433] | +3,927 ($+0.00004) | +4% ($+0.0002) | +2.0 [-1.1, +5.3]s |
| all-schema | 1 | +0% [-79%, +79%], 0/0 | -903 [-903, -903] | -48,098 [-48,098, -48,098] | -903 [-903, -903] | -47,193 [-47,193, -47,193] | -903 ($-0.00001) | -13% ($-0.0009) | +1.3 [+1.3, +1.3]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 4 | 100% | 48,202 | 255,763 | 18,594 | 237,158 | - | $0.0068 | 11.1s |
| all-2000 | 4 | +0% [-49%, +49%], 0/0 | +1,506 [-511, +3,522] | -54,104 [-93,656, -14,553] | +1,349 [-625, +3,209] | -55,451 [-93,140, -17,761] | +1,959 ($+0.00002) | -8% ($-0.0005) | +0.6 [-1.4, +3.5]s |
| all-6000 | 4 | +0% [-49%, +49%], 0/0 | +4,921 [+956, +8,498] | -45,814 [-86,562, -5,068] | +4,764 [+956, +8,185] | -50,576 [-89,711, -11,441] | +5,738 ($+0.00006) | +3% ($+0.0002) | +1.1 [-1.3, +3.7]s |
| all-schema | 1 | +0% [-79%, +79%], 0/0 | -903 [-903, -903] | -48,098 [-48,098, -48,098] | -903 [-903, -903] | -47,193 [-47,193, -47,193] | -903 ($-0.00001) | -13% ($-0.0009) | +1.3 [+1.3, +1.3]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

13 runs, $0.09; 13 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | enumerate | XL | all-2000 | 1/1 [21%, 100%] | $0.0061 | 49626 | 2 | 1/1 | 0/1 |
| a11y | enumerate | XL | all-6000 | 1/1 [21%, 100%] | $0.0075 | 56493 | 2 | 1/1 | 0/1 |
| a11y | enumerate | XL | native | 1/1 [21%, 100%] | $0.0074 | 48945 | 7 | 1/1 | 0/1 |
| figma | lookup | XXL | all-2000 | 1/1 [21%, 100%] | $0.0069 | 50695 | 3 | 1/1 | 0/1 |
| figma | lookup | XXL | all-6000 | 1/1 [21%, 100%] | $0.0083 | 56907 | 3 | 1/1 | 0/1 |
| figma | lookup | XXL | native | 1/1 [21%, 100%] | $0.0069 | 47458 | 4 | 1/1 | 0/1 |
| json | spot | XXL | all-2000 | 1/1 [21%, 100%] | $0.0057 | 47310 | 2 | 1/1 | 0/1 |
| json | spot | XXL | all-6000 | 1/1 [21%, 100%] | $0.0058 | 47772 | 2 | 1/1 | 0/1 |
| json | spot | XXL | all-schema | 1/1 [21%, 100%] | $0.0064 | 48110 | 3 | 1/1 | 0/1 |
| json | spot | XXL | native | 1/1 [21%, 100%] | $0.0073 | 49013 | 4 | 1/1 | 0/1 |
| log | count | XXL | all-2000 | 1/1 [21%, 100%] | $0.0064 | 50809 | 2 | 1/1 | 0/1 |
| log | count | XXL | all-6000 | 1/1 [21%, 100%] | $0.0064 | 50928 | 2 | 1/1 | 0/1 |
| log | count | XXL | native | 1/1 [21%, 100%] | $0.0056 | 47001 | 3 | 1/1 | 0/1 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | XL | all-2000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0013 [-0.0013, -0.0013] | +681 [+681, +681] | -91123 [-91123, -91123] | -0.0s [-0.0, -0.0] | fails (indicative: under 30 pairs) |
| a11y | XL | all-6000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0002 [+0.0002, +0.0002] | +7548 [+7548, +7548] | -77386 [-77386, -77386] | -1.6s [-1.6, -1.6] | fails (indicative: under 30 pairs) |
| figma | XXL | all-2000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0000 [+0.0000, +0.0000] | +3237 [+3237, +3237] | -37251 [-37251, -37251] | -0.5s [-0.5, -0.5] | fails (indicative: under 30 pairs) |
| figma | XXL | all-6000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0014 [+0.0014, +0.0014] | +9449 [+9449, +9449] | -18495 [-18495, -18495] | -1.1s [-1.1, -1.1] | fails (indicative: under 30 pairs) |
| json | XXL | all-2000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0017 [-0.0017, -0.0017] | -1703 [-1703, -1703] | -96188 [-96188, -96188] | -1.8s [-1.8, -1.8] | undecided (indicative: under 30 pairs) |
| json | XXL | all-6000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0015 [-0.0015, -0.0015] | -1241 [-1241, -1241] | -95737 [-95737, -95737] | +1.7s [+1.7, +1.7] | undecided (indicative: under 30 pairs) |
| json | XXL | all-schema | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0009 [-0.0009, -0.0009] | -903 [-903, -903] | -48098 [-48098, -48098] | +1.3s [+1.3, +1.3] | undecided (indicative: under 30 pairs) |
| log | XXL | all-2000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0008 [+0.0008, +0.0008] | +3808 [+3808, +3808] | +8145 [+8145, +8145] | +4.8s [+4.8, +4.8] | fails (indicative: under 30 pairs) |
| log | XXL | all-6000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0008 [+0.0008, +0.0008] | +3927 [+3927, +3927] | +8360 [+8360, +8360] | +5.3s [+5.3, +5.3] | fails (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| XL | all-2000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0013 [-0.0013, -0.0013] | +681 [+681, +681] | -91123 [-91123, -91123] | -0.0s [-0.0, -0.0] | fails (indicative: under 30 pairs) |
| XL | all-6000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0002 [+0.0002, +0.0002] | +7548 [+7548, +7548] | -77386 [-77386, -77386] | -1.6s [-1.6, -1.6] | fails (indicative: under 30 pairs) |
| XXL | all-2000 | 3 | +0% [-56%, +56%] | 0/0, p 1.00 | $+0.0000 [-0.0017, +0.0008] | +3237 [-1703, +3808] | -37251 [-96188, +8145] | -0.5s [-1.8, +4.8] | undecided (indicative: under 30 pairs) |
| XXL | all-6000 | 3 | +0% [-56%, +56%] | 0/0, p 1.00 | $+0.0008 [-0.0015, +0.0014] | +3927 [-1241, +9449] | -18495 [-95737, +8360] | +1.7s [-1.1, +5.3] | undecided (indicative: under 30 pairs) |
| XXL | all-schema | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0009 [-0.0009, -0.0009] | -903 [-903, -903] | -48098 [-48098, -48098] | +1.3s [+1.3, +1.3] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| XL | all-2000 | 1 | -2.0 [-2.0, -2.0] | +681 [+681, +681] | -91,800 [-91,800, -91,800] | -4.0 [-4.0, -4.0] | 1/1, 1/1 | +681 tokens, $+0.00001 |
| XL | all-6000 | 1 | -2.0 [-2.0, -2.0] | +7,548 [+7,548, +7,548] | -84,930 [-84,930, -84,930] | -4.0 [-4.0, -4.0] | 1/1, 1/1 | +7,548 tokens, $+0.00008 |
| XXL | all-2000 | 3 | -1.0 [-2.0, +0.0] | +1,572 [-1,703, +3,808] | -43,334 [-94,481, +4,337] | -2.0 [-4.0, +0.0] | 3/3, 3/3 | +3,237 tokens, $+0.00003 |
| XXL | all-6000 | 3 | -1.0 [-2.0, +0.0] | +3,836 [-1,241, +8,822] | -39,125 [-94,492, +4,433] | -2.0 [-4.0, +0.0] | 3/3, 3/3 | +3,927 tokens, $+0.00004 |
| XXL | all-schema | 1 | -1.0 [-1.0, -1.0] | -903 [-903, -903] | -47,193 [-47,193, -47,193] | -2.0 [-2.0, -2.0] | 1/1, 3/3 | -903 tokens, $-0.00001 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

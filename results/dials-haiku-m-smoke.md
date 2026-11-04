# Dials haiku-m-smoke: claude-haiku-5-5, the same tasks native and under each setting

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 2 | 100% | 58,048 | 148,750 | 43,530 | 105,214 | - | $0.0101 | 9.8s |
| default | 2 | +0% [-66%, +66%], 0/0 | -8,221 [-10,102, -6,340] | +90,477 [+37,784, +143,170] | -8,546 [-10,102, -6,990] | +99,019 [+47,884, +150,154] | -8,221 ($-0.00008) | -3% ($-0.0003) | +6.0 [+3.2, +8.7]s |
| budget-500 | 2 | +0% [-66%, +66%], 0/0 | -9,349 [-11,266, -7,432] | +109,724 [+35,422, +184,025] | -9,674 [-11,266, -8,082] | +119,392 [+46,686, +192,099] | -9,349 ($-0.00009) | -2% ($-0.0002) | +5.8 [+2.0, +9.5]s |
| budget-1000 | 2 | +0% [-66%, +66%], 0/0 | -4,002 [-10,543, +2,539] | +43,506 [+36,890, +50,122] | -4,327 [-10,543, +1,889] | +47,831 [+47,431, +48,231] | -4,002 ($-0.00004) | -0% ($-0.0000) | +5.2 [+2.5, +7.8]s |
| budget-4000 | 2 | +0% [-66%, +66%], 0/0 | -6,376 [-10,056, -2,697] | +97,210 [+37,828, +156,593] | -6,702 [-10,056, -3,347] | +103,908 [+47,882, +159,934] | -6,376 ($-0.00006) | +1% ($+0.0001) | +5.5 [+4.4, +6.5]s |
| schema-view | 1 | +0% [-79%, +79%], 0/0 | -11,536 [-11,536, -11,536] | +34,980 [+34,980, +34,980] | -11,536 [-11,536, -11,536] | +46,514 [+46,514, +46,514] | -11,536 ($-0.00012) | -14% ($-0.0018) | +1.9 [+1.9, +1.9]s |
| tree-cap-25 | 1 | +0% [-79%, +79%], 0/0 | +4,581 [+4,581, +4,581] | +115,359 [+115,359, +115,359] | +3,931 [+3,931, +3,931] | +111,424 [+111,424, +111,424] | +4,581 ($+0.00005) | +32% ($+0.0023) | +4.4 [+4.4, +4.4]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

12 runs, $0.12; 12 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| figma | spot | M | budget-1000 | 1/1 [21%, 100%] | $0.0088 | 60207 | 2 | 1/1 | 0/1 |
| figma | spot | M | budget-4000 | 1/1 [21%, 100%] | $0.0090 | 54971 | 4 | 1/1 | 0/1 |
| figma | spot | M | budget-500 | 1/1 [21%, 100%] | $0.0086 | 50236 | 5 | 1/1 | 0/1 |
| figma | spot | M | default | 1/1 [21%, 100%] | $0.0081 | 51328 | 4 | 1/1 | 0/1 |
| figma | spot | M | native | 1/1 [21%, 100%] | $0.0073 | 57668 | 1 | 0/1 | 0/1 |
| figma | spot | M | tree-cap-25 | 1/1 [21%, 100%] | $0.0096 | 62249 | 3 | 1/1 | 0/1 |
| json | count | M | budget-1000 | 1/1 [21%, 100%] | $0.0113 | 47884 | 2 | 1/1 | 0/1 |
| json | count | M | budget-4000 | 1/1 [21%, 100%] | $0.0114 | 48371 | 2 | 1/1 | 0/1 |
| json | count | M | budget-500 | 1/1 [21%, 100%] | $0.0112 | 47161 | 2 | 1/1 | 0/1 |
| json | count | M | default | 1/1 [21%, 100%] | $0.0114 | 48325 | 2 | 1/1 | 0/1 |
| json | count | M | native | 1/1 [21%, 100%] | $0.0129 | 58427 | 1 | 0/1 | 0/1 |
| json | count | M | schema-view | 1/1 [21%, 100%] | $0.0111 | 46891 | 2 | 1/1 | 0/1 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| figma | M | budget-1000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0016 [+0.0016, +0.0016] | +2539 [+2539, +2539] | +50122 [+50122, +50122] | +7.8s [+7.8, +7.8] | fails (indicative: under 30 pairs) |
| figma | M | budget-4000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0017 [+0.0017, +0.0017] | -2697 [-2697, -2697] | +156593 [+156593, +156593] | +6.5s [+6.5, +6.5] | undecided (indicative: under 30 pairs) |
| figma | M | budget-500 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0014 [+0.0014, +0.0014] | -7432 [-7432, -7432] | +184025 [+184025, +184025] | +9.5s [+9.5, +9.5] | undecided (indicative: under 30 pairs) |
| figma | M | default | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0009 [+0.0009, +0.0009] | -6340 [-6340, -6340] | +143170 [+143170, +143170] | +8.7s [+8.7, +8.7] | undecided (indicative: under 30 pairs) |
| figma | M | tree-cap-25 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0023 [+0.0023, +0.0023] | +4581 [+4581, +4581] | +115359 [+115359, +115359] | +4.4s [+4.4, +4.4] | fails (indicative: under 30 pairs) |
| json | M | budget-1000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0016 [-0.0016, -0.0016] | -10543 [-10543, -10543] | +36890 [+36890, +36890] | +2.5s [+2.5, +2.5] | undecided (indicative: under 30 pairs) |
| json | M | budget-4000 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0015 [-0.0015, -0.0015] | -10056 [-10056, -10056] | +37828 [+37828, +37828] | +4.4s [+4.4, +4.4] | undecided (indicative: under 30 pairs) |
| json | M | budget-500 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0017 [-0.0017, -0.0017] | -11266 [-11266, -11266] | +35422 [+35422, +35422] | +2.0s [+2.0, +2.0] | undecided (indicative: under 30 pairs) |
| json | M | default | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0014 [-0.0014, -0.0014] | -10102 [-10102, -10102] | +37784 [+37784, +37784] | +3.2s [+3.2, +3.2] | undecided (indicative: under 30 pairs) |
| json | M | schema-view | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0018 [-0.0018, -0.0018] | -11536 [-11536, -11536] | +34980 [+34980, +34980] | +1.9s [+1.9, +1.9] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | budget-1000 | 2 | +0% [-66%, +66%] | 0/0, p 1.00 | $-0.0000 [-0.0016, +0.0016] | -4002 [-10543, +2539] | +43506 [+36890, +50122] | +5.2s [+2.5, +7.8] | undecided (indicative: under 30 pairs) |
| M | budget-4000 | 2 | +0% [-66%, +66%] | 0/0, p 1.00 | $+0.0001 [-0.0015, +0.0017] | -6376 [-10056, -2697] | +97210 [+37828, +156593] | +5.5s [+4.4, +6.5] | undecided (indicative: under 30 pairs) |
| M | budget-500 | 2 | +0% [-66%, +66%] | 0/0, p 1.00 | $-0.0002 [-0.0017, +0.0014] | -9349 [-11266, -7432] | +109724 [+35422, +184025] | +5.8s [+2.0, +9.5] | undecided (indicative: under 30 pairs) |
| M | default | 2 | +0% [-66%, +66%] | 0/0, p 1.00 | $-0.0003 [-0.0014, +0.0009] | -8221 [-10102, -6340] | +90477 [+37784, +143170] | +6.0s [+3.2, +8.7] | undecided (indicative: under 30 pairs) |
| M | schema-view | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0018 [-0.0018, -0.0018] | -11536 [-11536, -11536] | +34980 [+34980, +34980] | +1.9s [+1.9, +1.9] | undecided (indicative: under 30 pairs) |
| M | tree-cap-25 | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0023 [+0.0023, +0.0023] | +4581 [+4581, +4581] | +115359 [+115359, +115359] | +4.4s [+4.4, +4.4] | fails (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | budget-1000 | 2 | +1.0 [+1.0, +1.0] | -4,327 [-10,543, +1,889] | +47,831 [+47,431, +48,231] | +2.0 [+2.0, +2.0] | 1/2, 1/2 | -4,002 tokens, $-0.00004 |
| M | budget-4000 | 2 | +2.0 [+1.0, +3.0] | -6,702 [-10,056, -3,347] | +103,908 [+47,882, +159,934] | +4.0 [+2.0, +6.0] | 1/2, 1/2 | -6,376 tokens, $-0.00006 |
| M | budget-500 | 2 | +2.5 [+1.0, +4.0] | -9,674 [-11,266, -8,082] | +119,392 [+46,686, +192,099] | +5.0 [+2.0, +8.0] | 1/2, 1/2 | -9,349 tokens, $-0.00009 |
| M | default | 2 | +2.0 [+1.0, +3.0] | -8,546 [-10,102, -6,990] | +99,019 [+47,884, +150,154] | +4.0 [+2.0, +6.0] | 1/2, 1/2 | -8,221 tokens, $-0.00008 |
| M | schema-view | 1 | +1.0 [+1.0, +1.0] | -11,536 [-11,536, -11,536] | +46,514 [+46,514, +46,514] | +2.0 [+2.0, +2.0] | 0/1, 1/2 | -11,536 tokens, $-0.00012 |
| M | tree-cap-25 | 1 | +2.0 [+2.0, +2.0] | +3,931 [+3,931, +3,931] | +111,424 [+111,424, +111,424] | +4.0 [+4.0, +4.0] | 1/1, 1/2 | +4,581 tokens, $+0.00005 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

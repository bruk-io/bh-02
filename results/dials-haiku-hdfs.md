# Dials haiku-hdfs: claude-haiku-5-5, the same tasks native and under each setting

## Band M (median input 8,441 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 20 | 25% | 62,174 | 152,952 | 32,689 | 120,258 | - | $0.0084 | 11.9s |
| fold | 20 | +0% [-8%, +8%], 0/0 | -8,287 [-10,633, -5,547] | +51,213 [+35,888, +70,998] | -8,351 [-10,722, -5,580] | +59,562 [+46,553, +77,625] | -10,830 ($-0.00011) | -12% ($-0.0010) | +1.7 [-0.2, +3.7]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band L (median input 69,336 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 20 | 40% | 55,267 | 350,049 | 26,886 | 323,150 | - | $0.0100 | 23.1s |
| fold | 20 | +0% [-3%, +3%], 0/0 | +1,467 [-7,249, +15,841] | -92,420 [-164,757, -19,222] | +1,404 [-7,316, +15,770] | -93,820 [-158,716, -30,229] | -4,814 ($-0.00005) | +50% ($+0.0050) | -6.0 [-11.1, -1.6]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 40 | 32% | 61,544 | 251,501 | 29,787 | 221,704 | - | $0.0092 | 17.5s |
| fold | 40 | +0% [-3%, +3%], 0/0 | -3,410 [-8,103, +4,834] | -20,603 [-67,311, +22,687] | -3,474 [-8,150, +4,769] | -17,129 [-61,466, +21,917] | -7,366 ($-0.00007) | +22% ($+0.0020) | -2.2 [-5.3, +0.3]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

80 runs, $0.82; 80 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| hdfs | absent | M | fold | 0/2 [0%, 66%] | $0.0068 | 52302 | 2.0 | 2/2 | 0/2 |
| hdfs | absent | M | native | 0/2 [0%, 66%] | $0.0082 | 62795 | 1.0 | 0/2 | 0/2 |
| hdfs | absent | L | fold | 0/2 [0%, 66%] | $0.0080 | 51179 | 4.0 | 2/2 | 0/2 |
| hdfs | absent | L | native | 0/2 [0%, 66%] | $0.0131 | 60739 | 9.5 | 2/2 | 0/2 |
| hdfs | count | M | fold | 0/4 [0%, 49%] | $0.0084 | 58932 | 2.0 | 4/4 | 0/4 |
| hdfs | count | M | native | 0/4 [0%, 49%] | $0.0087 | 62606 | 1.0 | 0/4 | 0/4 |
| hdfs | count | L | fold | 0/4 [0%, 49%] | $0.0066 | 49726 | 2.5 | 4/4 | 0/4 |
| hdfs | count | L | native | 0/4 [0%, 49%] | $0.0087 | 52795 | 5.0 | 4/4 | 0/4 |
| hdfs | enumerate | M | fold | 0/2 [0%, 66%] | $0.0093 | 56043 | 4.0 | 2/2 | 0/2 |
| hdfs | enumerate | M | native | 0/2 [0%, 66%] | $0.0090 | 61543 | 1.0 | 0/2 | 0/2 |
| hdfs | enumerate | L | fold | 0/2 [0%, 66%] | $0.0872 | 125064 | 5.0 | 2/2 | 0/2 |
| hdfs | enumerate | L | native | 0/2 [0%, 66%] | $0.0133 | 65514 | 5.0 | 2/2 | 0/2 |
| hdfs | lookup | M | fold | 4/4 [51%, 100%] | $0.0061 | 49573 | 2.0 | 3/4 | 0/4 |
| hdfs | lookup | M | native | 4/4 [51%, 100%] | $0.0080 | 61981 | 1.0 | 0/4 | 0/4 |
| hdfs | lookup | L | fold | 4/4 [51%, 100%] | $0.0063 | 50501 | 2.0 | 4/4 | 0/4 |
| hdfs | lookup | L | native | 4/4 [51%, 100%] | $0.0058 | 48047 | 2.0 | 4/4 | 0/4 |
| hdfs | spot | M | fold | 1/8 [2%, 47%] | $0.0069 | 52166 | 2.0 | 8/8 | 0/8 |
| hdfs | spot | M | native | 1/8 [2%, 47%] | $0.0081 | 62057 | 1.0 | 0/8 | 0/8 |
| hdfs | spot | L | fold | 4/8 [22%, 78%] | $0.0072 | 50618 | 3.0 | 8/8 | 0/8 |
| hdfs | spot | L | native | 4/8 [22%, 78%] | $0.0097 | 56928 | 6.0 | 8/8 | 0/8 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| hdfs | M | fold | 20 | +0% [-8%, +8%] | 0/0, p 1.00 | $-0.0014 [-0.0019, -0.0012] | -10830 [-11774, -9256] | +38145 [+37376, +40141] | +1.0s [-0.2, +3.2] | undecided (indicative: under 30 pairs) |
| hdfs | L | fold | 20 | +0% [-3%, +3%] | 0/0, p 1.00 | $-0.0015 [-0.0034, -0.0009] | -4814 [-6558, -732] | -53064 [-155572, -11637] | -3.5s [-9.9, +0.6] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | fold | 20 | +0% [-8%, +8%] | 0/0, p 1.00 | $-0.0014 [-0.0019, -0.0012] | -10830 [-11774, -9256] | +38145 [+37376, +40141] | +1.0s [-0.2, +3.2] | undecided (indicative: under 30 pairs) |
| L | fold | 20 | +0% [-3%, +3%] | 0/0, p 1.00 | $-0.0015 [-0.0034, -0.0009] | -4814 [-6558, -732] | -53064 [-155572, -11637] | -3.5s [-9.9, +0.6] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | fold | 20 | +1.2 [+0.9, +1.6] | -8,351 [-10,722, -5,580] | +59,562 [+46,553, +77,625] | +2.4 [+1.9, +3.1] | 20/20, 20/20 | -10,830 tokens, $-0.00011 |
| L | fold | 20 | -1.8 [-2.8, -0.8] | +1,404 [-7,316, +15,770] | -93,820 [-158,716, -30,229] | -3.6 [-5.6, -1.6] | 20/20, 20/20 | -4,814 tokens, $-0.00005 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

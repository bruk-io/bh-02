# Dials haiku-hdfs-smoke: claude-haiku-5-5, the same tasks native and under each setting

## Band M (median input 9,205 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 1 | 0% | 63,642 | 154,352 | 63,640 | 90,706 | - | $0.0147 | 15.7s |
| fold | 1 | +0% [-79%, +79%], 0/0 | -11,201 [-11,201, -11,201] | +37,436 [+37,436, +37,436] | -11,201 [-11,201, -11,201] | +48,635 [+48,635, +48,635] | -11,201 ($-0.00011) | -14% ($-0.0021) | +0.1 [+0.1, +0.1]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band L (median input 68,608 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 1 | 0% | 54,400 | 348,679 | 54,398 | 294,267 | - | $0.0149 | 23.4s |
| fold | 1 | +0% [-79%, +79%], 0/0 | -4,580 [-4,580, -4,580] | -110,075 [-110,075, -110,075] | -4,580 [-4,580, -4,580] | -105,491 [-105,491, -105,491] | -4,580 ($-0.00005) | -15% ($-0.0022) | -8.0 [-8.0, -8.0]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 2 | 0% | 59,021 | 251,516 | 59,019 | 192,486 | - | $0.0148 | 19.6s |
| fold | 2 | +0% [-66%, +66%], 0/0 | -7,890 [-11,201, -4,580] | -36,320 [-110,075, +37,436] | -7,890 [-11,201, -4,580] | -28,428 [-105,491, +48,635] | -7,890 ($-0.00008) | -14% ($-0.0021) | -3.9 [-8.0, +0.1]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

4 runs, $0.05; 4 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| hdfs | count | L | fold | 0/1 [0%, 79%] | $0.0127 | 49820 | 3 | 1/1 | 0/1 |
| hdfs | count | L | native | 0/1 [0%, 79%] | $0.0149 | 54400 | 5 | 1/1 | 0/1 |
| hdfs | spot | M | fold | 0/1 [0%, 79%] | $0.0126 | 52441 | 2 | 1/1 | 0/1 |
| hdfs | spot | M | native | 0/1 [0%, 79%] | $0.0147 | 63642 | 1 | 0/1 | 0/1 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| hdfs | M | fold | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0021 [-0.0021, -0.0021] | -11201 [-11201, -11201] | +37436 [+37436, +37436] | +0.1s [+0.1, +0.1] | undecided (indicative: under 30 pairs) |
| hdfs | L | fold | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0022 [-0.0022, -0.0022] | -4580 [-4580, -4580] | -110075 [-110075, -110075] | -8.0s [-8.0, -8.0] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | fold | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0021 [-0.0021, -0.0021] | -11201 [-11201, -11201] | +37436 [+37436, +37436] | +0.1s [+0.1, +0.1] | undecided (indicative: under 30 pairs) |
| L | fold | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0022 [-0.0022, -0.0022] | -4580 [-4580, -4580] | -110075 [-110075, -110075] | -8.0s [-8.0, -8.0] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | fold | 1 | +1.0 [+1.0, +1.0] | -11,201 [-11,201, -11,201] | +48,635 [+48,635, +48,635] | +2.0 [+2.0, +2.0] | 0/1, 0/1 | -11,201 tokens, $-0.00011 |
| L | fold | 1 | -2.0 [-2.0, -2.0] | -4,580 [-4,580, -4,580] | -105,491 [-105,491, -105,491] | -4.0 [-4.0, -4.0] | 0/1, 0/1 | -4,580 tokens, $-0.00005 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

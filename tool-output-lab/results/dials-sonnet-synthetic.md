# Dials sonnet-synthetic: claude-sonnet-5-5, the same tasks native and under each setting

## Band M (median input 6,502 tokens)

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | - | 100% | 56,964 | 133,342 | 30,285 | 103,051 | - | $0.1345 | 6.1s |
| schema | 52 | 52/52 | +0% [-7%, +7%], 0/0 | -10,401 [-11,379, -9,195] | +27,535 [+16,410, +39,205] | -10,559 [-11,548, -9,354] | +38,092 [+27,494, +49,254] | -11,435 ($-0.00209) | -28% ($-0.0372) | +2.1 [+1.3, +2.8]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.183 per million, as these runs' costs imply).

## Band L (median input 35,333 tokens)

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | - | 100% | 46,732 | 225,258 | 19,668 | 205,579 | - | $0.1070 | 11.4s |
| schema | 52 | 52/52 | -2% [-10%, +5%], 0/1 | -2,329 [-4,203, -1,022] | -56,940 [-70,427, -41,548] | -2,402 [-4,277, -1,114] | -54,536 [-68,055, -38,950] | -994 ($-0.00017) | -17% ($-0.0178) | -2.9 [-3.8, -1.7]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.169 per million, as these runs' costs imply).

## Every band together

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 104 | - | 100% | 55,465 | 179,300 | 24,976 | 154,315 | - | $0.1207 | 8.8s |
| schema | 104 | 104/104 | -1% [-5%, +3%], 0/1 | -6,365 [-7,683, -5,188] | -14,703 [-26,926, -1,775] | -6,480 [-7,810, -5,299] | -8,222 [-20,905, +4,976] | -2,608 ($-0.00045) | -23% ($-0.0275) | -0.4 [-1.2, +0.4]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.174 per million, as these runs' costs imply).

## Only the pairs where the envelope acted

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 104 | - | 100% | 55,465 | 179,300 | 24,976 | 154,315 | - | $0.1207 | 8.8s |
| schema | 104 | 104/104 | -1% [-5%, +3%], 0/1 | -6,365 [-7,683, -5,188] | -14,703 [-26,926, -1,775] | -6,480 [-7,810, -5,299] | -8,222 [-20,905, +4,976] | -2,608 ($-0.00045) | -23% ($-0.0275) | -0.4 [-1.2, +0.4]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.174 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-sonnet-5-5)

208 runs, $22.25; 208 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | M | native | 1/1 [21%, 100%] | $0.1164 | 55459 | 1 | 0/1 | 0/1 |
| a11y | absent | M | schema | 1/1 [21%, 100%] | $0.1074 | 46726 | 4 | 1/1 | 0/1 |
| a11y | absent | L | native | 1/1 [21%, 100%] | $0.1617 | 60391 | 4 | 1/1 | 0/1 |
| a11y | absent | L | schema | 1/1 [21%, 100%] | $0.1474 | 50096 | 9 | 1/1 | 0/1 |
| a11y | count | M | native | 4/4 [51%, 100%] | $0.1201 | 55544 | 1.0 | 0/4 | 0/4 |
| a11y | count | M | schema | 4/4 [51%, 100%] | $0.0805 | 45701 | 1.0 | 0/4 | 0/4 |
| a11y | count | L | native | 4/4 [51%, 100%] | $0.0953 | 46349 | 4.0 | 4/4 | 0/4 |
| a11y | count | L | schema | 4/4 [51%, 100%] | $0.0815 | 45698 | 1.0 | 1/4 | 0/4 |
| a11y | enumerate | M | native | 2/2 [34%, 100%] | $0.1185 | 55483 | 1.0 | 0/2 | 0/2 |
| a11y | enumerate | M | schema | 2/2 [34%, 100%] | $0.0772 | 45454 | 1.0 | 0/2 | 0/2 |
| a11y | enumerate | L | native | 2/2 [34%, 100%] | $0.0980 | 47365 | 3.5 | 2/2 | 0/2 |
| a11y | enumerate | L | schema | 2/2 [34%, 100%] | $0.0761 | 45465 | 1.0 | 0/2 | 0/2 |
| a11y | lookup | M | native | 2/2 [34%, 100%] | $0.1205 | 55548 | 1.0 | 0/2 | 0/2 |
| a11y | lookup | M | schema | 2/2 [34%, 100%] | $0.0887 | 45634 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | native | 2/2 [34%, 100%] | $0.0903 | 45738 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | schema | 2/2 [34%, 100%] | $0.0878 | 45669 | 2.0 | 2/2 | 0/2 |
| a11y | spot | M | native | 4/4 [51%, 100%] | $0.1177 | 55462 | 1.0 | 0/4 | 0/4 |
| a11y | spot | M | schema | 4/4 [51%, 100%] | $0.0872 | 45893 | 2.0 | 4/4 | 0/4 |
| a11y | spot | L | native | 4/4 [51%, 100%] | $0.1657 | 60239 | 4.0 | 4/4 | 0/4 |
| a11y | spot | L | schema | 3/4 [30%, 95%] | $0.0973 | 46414 | 3.0 | 4/4 | 0/4 |
| figma | absent | M | native | 1/1 [21%, 100%] | $0.1271 | 56638 | 1 | 0/1 | 0/1 |
| figma | absent | M | schema | 1/1 [21%, 100%] | $0.1395 | 57608 | 3 | 1/1 | 0/1 |
| figma | absent | L | native | 1/1 [21%, 100%] | $0.1134 | 47679 | 4 | 1/1 | 0/1 |
| figma | absent | L | schema | 1/1 [21%, 100%] | $0.1122 | 47181 | 4 | 1/1 | 0/1 |
| figma | count | M | native | 4/4 [51%, 100%] | $0.1276 | 56663 | 1.0 | 0/4 | 0/4 |
| figma | count | M | schema | 4/4 [51%, 100%] | $0.0986 | 46417 | 3.0 | 3/4 | 0/4 |
| figma | count | L | native | 4/4 [51%, 100%] | $0.0999 | 46770 | 3.0 | 4/4 | 0/4 |
| figma | count | L | schema | 4/4 [51%, 100%] | $0.0912 | 46165 | 2.5 | 3/4 | 0/4 |
| figma | enumerate | M | native | 2/2 [34%, 100%] | $0.1276 | 56672 | 1.0 | 0/2 | 0/2 |
| figma | enumerate | M | schema | 2/2 [34%, 100%] | $0.0960 | 46161 | 2.5 | 2/2 | 0/2 |
| figma | enumerate | L | native | 2/2 [34%, 100%] | $0.0991 | 46672 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | L | schema | 2/2 [34%, 100%] | $0.0875 | 45832 | 1.5 | 1/2 | 0/2 |
| figma | lookup | M | native | 2/2 [34%, 100%] | $0.1272 | 56610 | 1.0 | 0/2 | 0/2 |
| figma | lookup | M | schema | 2/2 [34%, 100%] | $0.0940 | 45521 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | native | 2/2 [34%, 100%] | $0.0892 | 45453 | 2.0 | 2/2 | 0/2 |
| figma | lookup | L | schema | 2/2 [34%, 100%] | $0.0937 | 45494 | 3.0 | 2/2 | 0/2 |
| figma | spot | M | native | 4/4 [51%, 100%] | $0.1254 | 56643 | 1.0 | 0/4 | 0/4 |
| figma | spot | M | schema | 4/4 [51%, 100%] | $0.1167 | 52297 | 2.5 | 4/4 | 0/4 |
| figma | spot | L | native | 4/4 [51%, 100%] | $0.1054 | 47334 | 3.5 | 4/4 | 0/4 |
| figma | spot | L | schema | 4/4 [51%, 100%] | $0.0977 | 46613 | 3.0 | 4/4 | 0/4 |
| json | absent | M | native | 1/1 [21%, 100%] | $0.1230 | 57225 | 1 | 0/1 | 0/1 |
| json | absent | M | schema | 1/1 [21%, 100%] | $0.0808 | 45220 | 1 | 0/1 | 0/1 |
| json | absent | L | native | 1/1 [21%, 100%] | $0.1047 | 46967 | 4 | 1/1 | 0/1 |
| json | absent | L | schema | 1/1 [21%, 100%] | $0.0884 | 45532 | 2 | 1/1 | 0/1 |
| json | count | M | native | 4/4 [51%, 100%] | $0.1311 | 57535 | 1.0 | 0/4 | 0/4 |
| json | count | M | schema | 4/4 [51%, 100%] | $0.0804 | 45314 | 1.0 | 0/4 | 0/4 |
| json | count | L | native | 4/4 [51%, 100%] | $0.0969 | 46172 | 3.0 | 4/4 | 0/4 |
| json | count | L | schema | 4/4 [51%, 100%] | $0.0815 | 45728 | 1.0 | 0/4 | 0/4 |
| json | enumerate | M | native | 2/2 [34%, 100%] | $0.1277 | 57327 | 1.0 | 0/2 | 0/2 |
| json | enumerate | M | schema | 2/2 [34%, 100%] | $0.0852 | 45497 | 1.5 | 1/2 | 0/2 |
| json | enumerate | L | native | 2/2 [34%, 100%] | $0.0993 | 46734 | 3.0 | 2/2 | 0/2 |
| json | enumerate | L | schema | 2/2 [34%, 100%] | $0.0824 | 45701 | 1.5 | 1/2 | 0/2 |
| json | lookup | M | native | 2/2 [34%, 100%] | $0.1303 | 57404 | 1.0 | 0/2 | 0/2 |
| json | lookup | M | schema | 2/2 [34%, 100%] | $0.0858 | 45392 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | native | 2/2 [34%, 100%] | $0.0964 | 45795 | 3.0 | 2/2 | 0/2 |
| json | lookup | L | schema | 2/2 [34%, 100%] | $0.0855 | 45345 | 2.0 | 2/2 | 0/2 |
| json | spot | M | native | 4/4 [51%, 100%] | $0.2407 | 57422 | 1.0 | 0/4 | 0/4 |
| json | spot | M | schema | 4/4 [51%, 100%] | $0.1895 | 45292 | 1.0 | 0/4 | 0/4 |
| json | spot | L | native | 4/4 [51%, 100%] | $0.0953 | 46687 | 3.0 | 4/4 | 0/4 |
| json | spot | L | schema | 4/4 [51%, 100%] | $0.0767 | 45212 | 1.0 | 0/4 | 0/4 |
| log | absent | M | native | 1/1 [21%, 100%] | $0.1373 | 59351 | 1 | 0/1 | 0/1 |
| log | absent | M | schema | 1/1 [21%, 100%] | $0.0968 | 46057 | 3 | 1/1 | 0/1 |
| log | absent | L | native | 1/1 [21%, 100%] | $0.1138 | 47878 | 4 | 1/1 | 0/1 |
| log | absent | L | schema | 1/1 [21%, 100%] | $0.0968 | 45987 | 3 | 1/1 | 0/1 |
| log | count | M | native | 4/4 [51%, 100%] | $0.1390 | 59369 | 1.0 | 0/4 | 0/4 |
| log | count | M | schema | 4/4 [51%, 100%] | $0.0830 | 45778 | 1.0 | 0/4 | 0/4 |
| log | count | L | native | 4/4 [51%, 100%] | $0.0985 | 46531 | 3.0 | 4/4 | 0/4 |
| log | count | L | schema | 4/4 [51%, 100%] | $0.0824 | 45774 | 1.0 | 0/4 | 0/4 |
| log | enumerate | M | native | 2/2 [34%, 100%] | $0.1399 | 59417 | 1.0 | 0/2 | 0/2 |
| log | enumerate | M | schema | 2/2 [34%, 100%] | $0.0845 | 45739 | 1.0 | 0/2 | 0/2 |
| log | enumerate | L | native | 2/2 [34%, 100%] | $0.0992 | 46606 | 3.0 | 2/2 | 0/2 |
| log | enumerate | L | schema | 2/2 [34%, 100%] | $0.0827 | 45730 | 1.0 | 0/2 | 0/2 |
| log | lookup | M | native | 2/2 [34%, 100%] | $0.1389 | 59325 | 1.0 | 0/2 | 0/2 |
| log | lookup | M | schema | 2/2 [34%, 100%] | $0.0871 | 45370 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | native | 2/2 [34%, 100%] | $0.0893 | 45367 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | schema | 2/2 [34%, 100%] | $0.0878 | 45331 | 2.0 | 2/2 | 0/2 |
| log | spot | M | native | 4/4 [51%, 100%] | $0.1369 | 59359 | 1.0 | 0/4 | 0/4 |
| log | spot | M | schema | 4/4 [51%, 100%] | $0.0808 | 45312 | 1.0 | 1/4 | 0/4 |
| log | spot | L | native | 4/4 [51%, 100%] | $0.1065 | 47416 | 3.5 | 4/4 | 0/4 |
| log | spot | L | schema | 4/4 [51%, 100%] | $0.0805 | 45297 | 1.0 | 1/4 | 0/4 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0350 [-0.0403, -0.0313] | -9712 [-9900, -9633] | +35110 [-9857, +35656] | +1.9s [+1.1, +2.2] | undecided (indicative: under 30 pairs) |
| a11y | L | schema | 13 | -8% [-33%, +16%] | 0/1, p 1.00 | $-0.0156 [-0.0248, -0.0088] | -1598 [-10295, -451] | -46713 [-91829, -16717] | -2.8s [-4.1, +0.9] | undecided (indicative: under 30 pairs) |
| figma | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0296 [-0.0320, +0.0110] | -10487 [-10703, +924] | +79384 [+46214, +80960] | +4.3s [+3.8, +5.7] | undecided (indicative: under 30 pairs) |
| figma | L | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0059 [-0.0155, -0.0000] | -677 [-1029, -498] | -1918 [-91894, +44106] | -1.2s [-3.4, +1.4] | undecided (indicative: under 30 pairs) |
| json | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0482 [-0.0488, -0.0426] | -12027 [-12100, -11964] | -11885 [-12104, +32818] | +0.6s [-0.4, +2.1] | undecided (indicative: under 30 pairs) |
| json | L | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0157 [-0.0177, -0.0141] | -1061 [-1338, -491] | -91201 [-92276, -47624] | -5.0s [-5.2, -3.9] | undecided (indicative: under 30 pairs) |
| log | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0545 [-0.0563, -0.0515] | -13814 [-13916, -13491] | -13501 [-13841, +31124] | +1.0s [-1.0, +2.9] | undecided (indicative: under 30 pairs) |
| log | L | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0171 [-0.0186, -0.0143] | -1123 [-1523, -414] | -91816 [-92779, -91183] | -3.4s [-5.0, -3.0] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | schema | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0425 [-0.0474, -0.0350] | -11435 [-12027, -10371] | +32720 [-9857, +35328] | +2.0s [+1.2, +2.9] | undecided |
| L | schema | 52 | -2% [-10%, +5%] | 0/1, p 1.00 | $-0.0153 [-0.0166, -0.0137] | -994 [-1136, -622] | -90402 [-91628, -46714] | -3.4s [-4.0, -2.9] | undecided |

## When the envelope acted: the pairs whose folded session folded the task's large output

| band | condition | acted | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| M | schema | 52/52 (saw it 52) | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0425 [-0.0474, -0.0350] | -11435 [-12027, -10371] | +32720 [-9857, +35328] | +2.0s [+1.2, +2.9] | undecided |
| L | schema | 52/52 (saw it 52) | 52 | -2% [-10%, +5%] | 0/1, p 1.00 | $-0.0153 [-0.0166, -0.0137] | -994 [-1136, -622] | -90402 [-91628, -46714] | -3.4s [-4.0, -2.9] | undecided |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, 2026-11-03); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $1.744 per million tokens (80% of runs between $1.645 and $1.880); too spread to price a read.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | schema | 52 | +0.8 [+0.6, +1.1] | -10,559 [-11,548, -9,354] | +38,092 [+27,494, +49,254] | +1.8 [+1.2, +2.5] | 49/52, 49/52 | -11,435 tokens |
| L | schema | 52 | -1.2 [-1.4, -0.8] | -2,402 [-4,277, -1,114] | -54,536 [-68,055, -38,950] | -2.2 [-3.0, -1.4] | 52/52, 52/52 | -994 tokens |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

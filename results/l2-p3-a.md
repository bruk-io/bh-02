# Layer 2: Claude Code on the eval tasks (claude-sonnet-5-5)

104 runs, $12.06; 104 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | M | fold-inline | 1/1 [21%, 100%] | $0.1208 | 49324 | 4 | 1/1 | 0/1 |
| a11y | absent | M | native | 1/1 [21%, 100%] | $0.1231 | 55648 | 1 | 0/1 | 0/1 |
| a11y | count | M | fold-inline | 4/4 [51%, 100%] | $0.0989 | 48368 | 2.0 | 4/4 | 0/4 |
| a11y | count | M | native | 4/4 [51%, 100%] | $0.1227 | 55639 | 1.0 | 0/4 | 0/4 |
| a11y | enumerate | M | fold-inline | 2/2 [34%, 100%] | $0.1010 | 48564 | 2.0 | 2/2 | 0/2 |
| a11y | enumerate | M | native | 2/2 [34%, 100%] | $0.1233 | 55672 | 1.0 | 0/2 | 0/2 |
| a11y | lookup | M | fold-inline | 2/2 [34%, 100%] | $0.1009 | 48578 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | M | native | 2/2 [34%, 100%] | $0.1234 | 55641 | 1.0 | 0/2 | 0/2 |
| a11y | spot | M | fold-inline | 4/4 [51%, 100%] | $0.1078 | 49000 | 3.0 | 4/4 | 0/4 |
| a11y | spot | M | native | 4/4 [51%, 100%] | $0.1166 | 55447 | 1.0 | 0/4 | 0/4 |
| figma | absent | M | fold-inline | 1/1 [21%, 100%] | $0.1175 | 49389 | 4 | 1/1 | 0/1 |
| figma | absent | M | native | 1/1 [21%, 100%] | $0.1270 | 56635 | 1 | 0/1 | 0/1 |
| figma | count | M | fold-inline | 4/4 [51%, 100%] | $0.1163 | 48945 | 4.0 | 4/4 | 0/4 |
| figma | count | M | native | 4/4 [51%, 100%] | $0.1277 | 56666 | 1.0 | 0/4 | 0/4 |
| figma | enumerate | M | fold-inline | 2/2 [34%, 100%] | $0.1160 | 49198 | 3.5 | 2/2 | 0/2 |
| figma | enumerate | M | native | 2/2 [34%, 100%] | $0.1277 | 56673 | 1.0 | 0/2 | 0/2 |
| figma | lookup | M | fold-inline | 2/2 [34%, 100%] | $0.1050 | 48440 | 3.0 | 2/2 | 0/2 |
| figma | lookup | M | native | 2/2 [34%, 100%] | $0.1271 | 56605 | 1.0 | 0/2 | 0/2 |
| figma | spot | M | fold-inline | 4/4 [51%, 100%] | $0.1219 | 50168 | 3.0 | 4/4 | 0/4 |
| figma | spot | M | native | 4/4 [51%, 100%] | $0.1265 | 56646 | 1.0 | 0/4 | 0/4 |
| json | absent | M | fold-inline | 1/1 [21%, 100%] | $0.1001 | 46185 | 3 | 1/1 | 0/1 |
| json | absent | M | native | 1/1 [21%, 100%] | $0.1285 | 57423 | 1 | 0/1 | 0/1 |
| json | count | M | fold-inline | 4/4 [51%, 100%] | $0.0859 | 47156 | 1.0 | 0/4 | 0/4 |
| json | count | M | native | 4/4 [51%, 100%] | $0.1313 | 57538 | 1.0 | 0/4 | 0/4 |
| json | enumerate | M | fold-inline | 2/2 [34%, 100%] | $0.0925 | 47128 | 1.5 | 1/2 | 0/2 |
| json | enumerate | M | native | 2/2 [34%, 100%] | $0.1333 | 57521 | 1.0 | 0/2 | 0/2 |
| json | lookup | M | fold-inline | 2/2 [34%, 100%] | $0.0881 | 45600 | 2.0 | 2/2 | 0/2 |
| json | lookup | M | native | 2/2 [34%, 100%] | $0.1302 | 57398 | 1.0 | 0/2 | 0/2 |
| json | spot | M | fold-inline | 4/4 [51%, 100%] | $0.0822 | 45730 | 1.0 | 1/4 | 0/4 |
| json | spot | M | native | 4/4 [51%, 100%] | $0.1284 | 57419 | 1.0 | 0/4 | 0/4 |
| log | absent | M | fold-inline | 1/1 [21%, 100%] | $0.1022 | 47457 | 3 | 1/1 | 0/1 |
| log | absent | M | native | 1/1 [21%, 100%] | $0.1368 | 59369 | 1 | 0/1 | 0/1 |
| log | count | M | fold-inline | 4/4 [51%, 100%] | $0.1085 | 49169 | 2.5 | 4/4 | 0/4 |
| log | count | M | native | 4/4 [51%, 100%] | $0.1385 | 59368 | 1.0 | 0/4 | 0/4 |
| log | enumerate | M | fold-inline | 2/2 [34%, 100%] | $0.1071 | 48672 | 2.5 | 2/2 | 0/2 |
| log | enumerate | M | native | 2/2 [34%, 100%] | $0.1402 | 59415 | 1.0 | 0/2 | 0/2 |
| log | lookup | M | fold-inline | 2/2 [34%, 100%] | $0.0953 | 47109 | 2.0 | 2/2 | 0/2 |
| log | lookup | M | native | 2/2 [34%, 100%] | $0.1391 | 59343 | 1.0 | 0/2 | 0/2 |
| log | spot | M | fold-inline | 4/4 [51%, 100%] | $0.0963 | 47506 | 2.0 | 4/4 | 0/4 |
| log | spot | M | native | 4/4 [51%, 100%] | $0.1337 | 59267 | 1.0 | 0/4 | 0/4 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | M | fold-inline | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0208 [-0.0242, -0.0109] | -6981 [-7146, -6499] | +41258 [+41007, +134200] | +6.4s [+2.5, +8.4] | undecided (indicative: under 30 pairs) |
| figma | M | fold-inline | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0117 [-0.0168, -0.0096] | -7547 [-7727, -6811] | +93211 [+88656, +137365] | +10.8s [+6.6, +17.1] | undecided (indicative: under 30 pairs) |
| json | M | fold-inline | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0434 [-0.0471, -0.0401] | -11307 [-11698, -10732] | -10038 [-11690, +33675] | +2.0s [-4.9, +7.7] | undecided (indicative: under 30 pairs) |
| log | M | fold-inline | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0338 [-0.0356, -0.0307] | -11208 [-11877, -10674] | +80178 [+37658, +83021] | +4.0s [+1.0, +6.1] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | fold-inline | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0280 [-0.0324, -0.0214] | -8830 [-10703, -7490] | +43474 [+39184, +85006] | +6.0s [+3.0, +8.3] | undecided |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

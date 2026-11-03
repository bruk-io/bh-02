# Layer 2: Claude Code on the eval tasks (claude-sonnet-5-5)

40 runs, $4.55; 40 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | L | fold | 1/1 [21%, 100%] | $0.1155 | 49515 | 3 | 1/1 | 0/1 |
| a11y | absent | L | native | 1/1 [21%, 100%] | $0.1776 | 60877 | 5 | 1/1 | 0/1 |
| a11y | spot | L | fold | 4/4 [51%, 100%] | $0.1027 | 48853 | 2.0 | 4/4 | 0/4 |
| a11y | spot | L | native | 4/4 [51%, 100%] | $0.1748 | 60741 | 4.5 | 4/4 | 0/4 |
| figma | absent | L | fold | 1/1 [21%, 100%] | $0.1095 | 49244 | 3 | 1/1 | 0/1 |
| figma | absent | L | native | 1/1 [21%, 100%] | $0.1137 | 47372 | 4 | 1/1 | 0/1 |
| figma | spot | L | fold | 4/4 [51%, 100%] | $0.1103 | 49114 | 2.5 | 4/4 | 0/4 |
| figma | spot | L | native | 2/4 [15%, 85%] | $0.1119 | 47216 | 4.0 | 4/4 | 0/4 |
| json | absent | L | fold | 1/1 [21%, 100%] | $0.0895 | 45876 | 2 | 1/1 | 0/1 |
| json | absent | L | native | 1/1 [21%, 100%] | $0.1039 | 46847 | 4 | 1/1 | 0/1 |
| json | spot | L | fold | 4/4 [51%, 100%] | $0.0816 | 45697 | 1.0 | 1/4 | 0/4 |
| json | spot | L | native | 4/4 [51%, 100%] | $0.0979 | 46734 | 3.0 | 4/4 | 0/4 |
| log | absent | L | fold | 1/1 [21%, 100%] | $0.1056 | 47588 | 3 | 1/1 | 0/1 |
| log | absent | L | native | 1/1 [21%, 100%] | $0.1411 | 48640 | 9 | 1/1 | 0/1 |
| log | spot | L | fold | 4/4 [51%, 100%] | $0.0973 | 47603 | 2.0 | 4/4 | 0/4 |
| log | spot | L | native | 4/4 [51%, 100%] | $0.0995 | 46568 | 3.0 | 4/4 | 0/4 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | L | fold | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0622 [-0.1567, -0.0529] | -11362 [-38263, -11076] | -89520 [-188098, -79925] | -4.6s [-18.2, +36.0] | undecided (indicative: under 30 pairs) |
| figma | L | fold | 5 | +40% [-12%, +77%] | 2/0, p 0.50 | $+0.0002 [-0.0079, +0.0047] | +1872 [+1401, +2773] | -41244 [-89422, -37961] | -6.9s [-14.6, -2.7] | fails (indicative: under 30 pairs) |
| json | L | fold | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0180 [-0.0428, -0.0056] | -996 [-7123, -849] | -91834 [-98284, -1725] | -1.9s [-2.8, +11.9] | undecided (indicative: under 30 pairs) |
| log | L | fold | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0020 [-0.0355, +0.0012] | +921 [-1052, +1662] | -43321 [-186737, -41205] | -4.5s [-17.8, +4.1] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| L | fold | 20 | +10% [-8%, +30%] | 2/0, p 0.50 | $-0.0112 [-0.0392, -0.0026] | -910 [-4097, +1378] | -80956 [-90677, -42604] | -3.8s [-8.8, -1.9] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

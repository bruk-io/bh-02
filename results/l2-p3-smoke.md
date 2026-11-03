# Layer 2: Claude Code on the eval tasks (claude-sonnet-5-5)

2 runs, $0.22; 2 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| json | spot | M | fold-inline | 1/1 [21%, 100%] | $0.0883 | 45733 | 1 | 0/1 | 0/1 |
| json | spot | M | native | 1/1 [21%, 100%] | $0.1355 | 57418 | 1 | 0/1 | 0/1 |

## Each condition against native, paired by task and repetition, per size band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| json | M | fold-inline | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0472 [-0.0472, -0.0472] | -11685 [-11685, -11685] | -11687 [-11687, -11687] | +4.0s [+4.0, +4.0] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | fold-inline | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0472 [-0.0472, -0.0472] | -11685 [-11685, -11685] | -11687 [-11687, -11687] | +4.0s [+4.0, +4.0] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

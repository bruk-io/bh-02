# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

6 runs, $0.07; 6 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| log | spot | L | bash-native | 1/1 [21%, 100%] | $0.0118 | 48000 | 3 | 1/1 | 0/1 |
| log | spot | L | fold-bash | 1/1 [21%, 100%] | $0.0123 | 48777 | 4 | 0/1 | 0/1 |
| log | spot | L | fold-bash-all | 1/1 [21%, 100%] | $0.0120 | 49272 | 3 | 1/1 | 0/1 |
| log | spot | M | bash-native | 1/1 [21%, 100%] | $0.0127 | 60214 | 1 | 0/1 | 0/1 |
| log | spot | M | fold-bash | 1/1 [21%, 100%] | $0.0111 | 48293 | 2 | 0/1 | 0/1 |
| log | spot | M | fold-bash-all | 1/1 [21%, 100%] | $0.0116 | 48680 | 3 | 0/1 | 0/1 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| log | L | fold-bash (against bash-native) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0006 [+0.0006, +0.0006] | +777 [+777, +777] | +49361 [+49361, +49361] | -2.3s [-2.3, -2.3] | fails (indicative: under 30 pairs) |
| log | L | fold-bash-all (against bash-native) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0002 [+0.0002, +0.0002] | +1272 [+1272, +1272] | +3642 [+3642, +3642] | +1.4s [+1.4, +1.4] | fails (indicative: under 30 pairs) |
| log | M | fold-bash (against bash-native) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0016 [-0.0016, -0.0016] | -11921 [-11921, -11921] | +35892 [+35892, +35892] | +3.9s [+3.9, +3.9] | undecided (indicative: under 30 pairs) |
| log | M | fold-bash-all (against bash-native) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0011 [-0.0011, -0.0011] | -11534 [-11534, -11534] | +84835 [+84835, +84835] | +3.5s [+3.5, +3.5] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| L | fold-bash (against bash-native) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0006 [+0.0006, +0.0006] | +777 [+777, +777] | +49361 [+49361, +49361] | -2.3s [-2.3, -2.3] | fails (indicative: under 30 pairs) |
| L | fold-bash-all (against bash-native) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0002 [+0.0002, +0.0002] | +1272 [+1272, +1272] | +3642 [+3642, +3642] | +1.4s [+1.4, +1.4] | fails (indicative: under 30 pairs) |
| M | fold-bash (against bash-native) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0016 [-0.0016, -0.0016] | -11921 [-11921, -11921] | +35892 [+35892, +35892] | +3.9s [+3.9, +3.9] | undecided (indicative: under 30 pairs) |
| M | fold-bash-all (against bash-native) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $-0.0011 [-0.0011, -0.0011] | -11534 [-11534, -11534] | +84835 [+84835, +84835] | +3.5s [+3.5, +3.5] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

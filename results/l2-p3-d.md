# Layer 2: Claude Code on the eval tasks (claude-sonnet-5-5)

20 runs, $2.02; 20 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| python | edit | L | fold-tool | 5/5 [57%, 100%] | $0.0970 | 48205 | 3 | 0/5 | 0/5 |
| python | edit | L | native | 5/5 [57%, 100%] | $0.0949 | 47925 | 2 | 0/5 | 0/5 |
| python | edit | L | noshell | 5/5 [57%, 100%] | $0.1009 | 46917 | 3 | 0/5 | 0/5 |
| python | edit | L | noshell-fold | 5/5 [57%, 100%] | $0.0946 | 46740 | 2 | 0/5 | 0/5 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| python | L | fold-tool | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $+0.0015 [+0.0007, +0.0078] | +280 [+188, +493] | +831 [+744, +49010] | +2.2s [-3.3, +4.5] | fails (indicative: under 30 pairs) |
| python | L | noshell | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $+0.0060 [-0.0057, +0.0538] | -1099 [-1342, +4289] | +42683 [-51644, +139737] | +7.5s [+1.6, +11.3] | undecided (indicative: under 30 pairs) |
| python | L | noshell-fold (against noshell) | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0060 [-0.0203, +0.0162] | -177 [-2002, +1195] | -2713 [-46606, +95123] | -3.7s [-10.0, -1.8] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| L | fold-tool | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $+0.0015 [+0.0007, +0.0078] | +280 [+188, +493] | +831 [+744, +49010] | +2.2s [-3.3, +4.5] | fails (indicative: under 30 pairs) |
| L | noshell | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $+0.0060 [-0.0057, +0.0538] | -1099 [-1342, +4289] | +42683 [-51644, +139737] | +7.5s [+1.6, +11.3] | undecided (indicative: under 30 pairs) |
| L | noshell-fold (against noshell) | 5 | +0% [-43%, +43%] | 0/0, p 1.00 | $-0.0060 [-0.0203, +0.0162] | -177 [-2002, +1195] | -2713 [-46606, +95123] | -3.7s [-10.0, -1.8] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

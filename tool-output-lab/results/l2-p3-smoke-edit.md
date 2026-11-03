# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

4 runs, $0.04; 4 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| python | edit | L | fold-tool | 1/1 [21%, 100%] | $0.0059 | 47584 | 2 | 0/1 | 0/1 |
| python | edit | L | native | 1/1 [21%, 100%] | $0.0055 | 46821 | 2 | 0/1 | 0/1 |
| python | edit | L | noshell | 1/1 [21%, 100%] | $0.0138 | 50943 | 12 | 0/1 | 0/1 |
| python | edit | L | noshell-fold | 1/1 [21%, 100%] | $0.0143 | 51020 | 12 | 0/1 | 0/1 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| python | L | fold-tool | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0003 [+0.0003, +0.0003] | +763 [+763, +763] | +1430 [+1430, +1430] | +5.2s [+5.2, +5.2] | fails (indicative: under 30 pairs) |
| python | L | noshell | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0083 [+0.0083, +0.0083] | +4122 [+4122, +4122] | +101325 [+101325, +101325] | +6.1s [+6.1, +6.1] | fails (indicative: under 30 pairs) |
| python | L | noshell-fold (against noshell) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0005 [+0.0005, +0.0005] | +77 [+77, +77] | +45839 [+45839, +45839] | +5.4s [+5.4, +5.4] | fails (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| L | fold-tool | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0003 [+0.0003, +0.0003] | +763 [+763, +763] | +1430 [+1430, +1430] | +5.2s [+5.2, +5.2] | fails (indicative: under 30 pairs) |
| L | noshell | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0083 [+0.0083, +0.0083] | +4122 [+4122, +4122] | +101325 [+101325, +101325] | +6.1s [+6.1, +6.1] | fails (indicative: under 30 pairs) |
| L | noshell-fold (against noshell) | 1 | +0% [-79%, +79%] | 0/0, p 1.00 | $+0.0005 [+0.0005, +0.0005] | +77 [+77, +77] | +45839 [+45839, +45839] | +5.4s [+5.4, +5.4] | fails (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

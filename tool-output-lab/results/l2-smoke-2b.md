# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

2 runs, $0.01; 2 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls |
|---|---|---|---|---|---|---|---|
| python | locate | L | fold-tool | 1/1 [21%, 100%] | $0.0049 | 46019 | 2 |
| python | locate | L | native | 1/1 [21%, 100%] | $0.0048 | 45734 | 2 |

## Each condition against native, paired by task and repetition

| format | condition | pairs | accuracy change | cost change | final context change | time change | verdict |
|---|---|---|---|---|---|---|---|
| python | fold-tool | 1 | +0% [+0%, +0%] | $+0.0001 [+0.0001, +0.0001] | +285 [+285, +285] | -3.2s [-3.2, -3.2] | fails (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise.

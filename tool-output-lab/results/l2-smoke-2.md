# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

3 runs, $0.02; 3 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls |
|---|---|---|---|---|---|---|---|
| figma | lookup | L | fold | 1/1 [21%, 100%] | $0.0069 | 50566 | 3 |
| figma | lookup | L | fold-all | 1/1 [21%, 100%] | $0.0072 | 50809 | 3 |
| figma | lookup | L | native | 1/1 [21%, 100%] | $0.0068 | 47260 | 4 |

## Each condition against native, paired by task and repetition

| format | condition | pairs | accuracy change | cost change | final context change | time change | verdict |
|---|---|---|---|---|---|---|---|
| figma | fold | 1 | +0% [+0%, +0%] | $+0.0001 [+0.0001, +0.0001] | +3306 [+3306, +3306] | -0.8s [-0.8, -0.8] | fails (indicative: under 30 pairs) |
| figma | fold-all | 1 | +0% [+0%, +0%] | $+0.0003 [+0.0003, +0.0003] | +3549 [+3549, +3549] | +11.2s [+11.2, +11.2] | fails (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise.

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

3 runs, $0.02. Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls |
|---|---|---|---|---|---|---|---|
| json | spot | L | fold | 1/1 [21%, 100%] | $0.0048 | 46632 | 1 |
| json | spot | L | fold-all | 1/1 [21%, 100%] | $0.0053 | 46621 | 1 |
| json | spot | L | native | 1/1 [21%, 100%] | $0.0077 | 48578 | 4 |

## Each condition against native, paired by task and repetition

| format | condition | pairs | accuracy change | cost change | final context change | time change | verdict |
|---|---|---|---|---|---|---|---|
| json | fold | 1 | +0% [+0%, +0%] | $-0.0029 [-0.0029, -0.0029] | -1946 [-1946, -1946] | -1.3s [-1.3, -1.3] | passes (indicative: under 30 pairs) |
| json | fold-all | 1 | +0% [+0%, +0%] | $-0.0024 [-0.0024, -0.0024] | -1957 [-1957, -1957] | -6.8s [-6.8, -6.8] | passes (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise.

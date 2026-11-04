# Layer 1: the fold alone, budget 2000 tokens

View: sample. Knobs: defaults.

59 folds of 59 tasks. Sufficient = the task's scorer finds
the answer in the fold text (an upper bound on what a model can answer without fetching more).

Sufficient overall: 23/59; over the folds that folded (not passed through): 22/58.

## Invariants: 0 folds with violations

None.

## Sufficiency, query off

| format | kind | M | L |
|---|---|---|---|
| atlas | claims | 19/42 | 4/17 |

## Size, query off

| format | band | tasks | median tokens in | median out | median kept | over budget |
|---|---|---|---|---|---|---|
| atlas | M | 42 | 4673 | 630 | 9% | 0 |
| atlas | L | 17 | 37541 | 866 | 3% | 0 |

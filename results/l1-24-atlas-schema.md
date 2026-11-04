# Layer 1: the fold alone, budget 2000 tokens

View: sample. Knobs: defaults.

59 folds of 59 tasks. Sufficient = the task's scorer finds
the answer in the fold text (an upper bound on what a model can answer without fetching more).

Sufficient overall: 18/59; over the folds that folded (not passed through): 17/58.

## Invariants: 0 folds with violations

None.

## Sufficiency, query off

| format | kind | M | L |
|---|---|---|---|
| atlas | claims | 16/42 | 2/17 |

## Size, query off

| format | band | tasks | median tokens in | median out | median kept | over budget |
|---|---|---|---|---|---|---|
| atlas | M | 42 | 4673 | 321 | 6% | 0 |
| atlas | L | 17 | 37541 | 351 | 2% | 0 |

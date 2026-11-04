# Layer 1: the fold alone, budget 2000 tokens

View: sample. Knobs: defaults.

47 folds of 39 tasks. Sufficient = the task's scorer finds
the answer in the fold text (an upper bound on what a model can answer without fetching more).

Sufficient overall: 41/47; over the folds that folded (not passed through): 29/35.

## Invariants: 0 folds with violations

None.

## Sufficiency, query off

| format | kind | S | M | L |
|---|---|---|---|---|
| json | absent | 1/1 | 1/1 | 1/1 |
| json | count | 2/2 | 4/4 | 4/4 |
| json | enumerate | 1/1 | 1/2 | 2/2 |
| json | lookup | 2/2 | 0/2 | 0/2 |
| json | spot | 4/4 | 4/4 | 4/4 |
| pypi | count |  |  | 1/1 |
| pypi | enumerate |  |  | 1/1 |
| pypi | lookup |  |  | 0/1 |

## Sufficiency, query on (tasks whose tool call would name what is asked)

| format | kind | S | M | L |
|---|---|---|---|---|
| json | lookup | 2/2 | 2/2 | 2/2 |
| pypi | enumerate |  |  | 1/1 |
| pypi | lookup |  |  | 1/1 |

## Size, query off

| format | band | tasks | median tokens in | median out | median kept | over budget |
|---|---|---|---|---|---|---|
| json | S | 10 | 1360 | 1360 | 100% | 0 |
| json | M | 13 | 6780 | 192 | 3% | 0 |
| json | L | 13 | 33852 | 228 | 1% | 0 |
| pypi | L | 3 | 25628 | 1018 | 4% | 0 |

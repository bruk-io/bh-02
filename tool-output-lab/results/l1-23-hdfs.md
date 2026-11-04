# Layer 1: the fold alone, budget 2000 tokens

View: sample. Knobs: defaults.

24 folds of 20 tasks. Sufficient = the task's scorer finds
the answer in the fold text (an upper bound on what a model can answer without fetching more).

Sufficient overall: 12/24; over the folds that folded (not passed through): 12/24.

## Invariants: 0 folds with violations

None.

## Sufficiency, query off

| format | kind | M | L |
|---|---|---|---|
| hdfs | absent | 0/1 | 0/1 |
| hdfs | count | 2/2 | 0/2 |
| hdfs | enumerate | 1/1 | 1/1 |
| hdfs | lookup | 1/2 | 0/2 |
| hdfs | spot | 2/4 | 1/4 |

## Sufficiency, query on (tasks whose tool call would name what is asked)

| format | kind | M | L |
|---|---|---|---|
| hdfs | lookup | 2/2 | 2/2 |

## Size, query off

| format | band | tasks | median tokens in | median out | median kept | over budget |
|---|---|---|---|---|---|---|
| hdfs | M | 10 | 8441 | 1649 | 20% | 0 |
| hdfs | L | 10 | 69335 | 1538 | 2% | 0 |

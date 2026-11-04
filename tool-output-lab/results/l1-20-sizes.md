# Layer 1: the fold alone, budget 2000 tokens

View: sample. Knobs: defaults.

120 folds of 104 tasks. Sufficient = the task's scorer finds
the answer in the fold text (an upper bound on what a model can answer without fetching more).

Sufficient overall: 76/120; over the folds that folded (not passed through): 76/120.

## Invariants: 0 folds with violations

None.

## Sufficiency, query off

| format | kind | XL | XXL |
|---|---|---|---|
| json | absent | 1/1 | 1/1 |
| json | count | 4/4 | 4/4 |
| json | enumerate | 1/2 | 1/2 |
| json | lookup | 0/2 | 0/2 |
| json | spot | 3/4 | 3/4 |
| log | absent | 1/1 | 1/1 |
| log | count | 2/4 | 2/4 |
| log | enumerate | 1/2 | 1/2 |
| log | lookup | 0/2 | 0/2 |
| log | spot | 3/4 | 3/4 |
| a11y | absent | 1/1 | 1/1 |
| a11y | count | 2/4 | 2/4 |
| a11y | enumerate | 1/2 | 1/2 |
| a11y | lookup | 0/2 | 0/2 |
| a11y | spot | 3/4 | 3/4 |
| figma | absent | 1/1 | 1/1 |
| figma | count | 2/4 | 2/4 |
| figma | enumerate | 1/2 | 1/2 |
| figma | lookup | 0/2 | 0/2 |
| figma | spot | 3/4 | 3/4 |

## Sufficiency, query on (tasks whose tool call would name what is asked)

| format | kind | XL | XXL |
|---|---|---|---|
| json | lookup | 2/2 | 2/2 |
| log | lookup | 2/2 | 2/2 |
| a11y | lookup | 2/2 | 2/2 |
| figma | lookup | 2/2 | 2/2 |

## Size, query off

| format | band | tasks | median tokens in | median out | median kept | over budget |
|---|---|---|---|---|---|---|
| json | XL | 13 | 135377 | 433 | 0% | 0 |
| json | XXL | 13 | 541458 | 435 | 0% | 0 |
| log | XL | 13 | 164764 | 998 | 1% | 0 |
| log | XXL | 13 | 659061 | 993 | 0% | 0 |
| a11y | XL | 13 | 74924 | 1734 | 2% | 0 |
| a11y | XXL | 13 | 299463 | 1735 | 1% | 0 |
| figma | XL | 13 | 147189 | 1846 | 1% | 0 |
| figma | XXL | 13 | 589502 | 1852 | 0% | 0 |

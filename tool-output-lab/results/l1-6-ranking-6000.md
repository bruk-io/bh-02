# Layer 1: the fold alone, budget 6000 tokens

160 folds of 131 tasks. Sufficient = the task's scorer finds
the answer in the fold text (an upper bound on what a model can answer without fetching more).

## Invariants: 0 folds with violations

None.

## Sufficiency, query off

| format | kind | S | M | L |
|---|---|---|---|---|
| json | absent | 1/1 | 1/1 | 1/1 |
| json | count | 2/2 | 2/2 | 2/2 |
| json | enumerate | 1/1 | 1/1 | 1/1 |
| json | lookup | 2/2 | 0/2 | 0/2 |
| json | spot | 3/3 | 3/3 | 3/3 |
| log | absent | 1/1 | 1/1 | 1/1 |
| log | count | 2/2 | 2/2 | 2/2 |
| log | enumerate | 1/1 | 1/1 | 1/1 |
| log | lookup | 2/2 | 0/2 | 0/2 |
| log | spot | 3/3 | 3/3 | 3/3 |
| a11y | absent | 1/1 | 1/1 | 1/1 |
| a11y | count | 2/2 | 2/2 | 2/2 |
| a11y | enumerate | 1/1 | 1/1 | 1/1 |
| a11y | lookup | 2/2 | 2/2 | 0/2 |
| a11y | spot | 3/3 | 3/3 | 3/3 |
| figma | absent | 1/1 | 1/1 | 1/1 |
| figma | count | 2/2 | 2/2 | 2/2 |
| figma | enumerate | 1/1 | 1/1 | 1/1 |
| figma | lookup | 2/2 | 2/2 | 0/2 |
| figma | spot | 3/3 | 3/3 | 3/3 |
| python | count |  | 1/1 | 2/2 |
| python | enumerate | 1/1 |  | 2/3 |
| python | locate |  | 0/1 | 1/3 |
| rust | count |  |  | 2/2 |
| rust | enumerate |  |  | 0/2 |
| rust | locate |  |  | 0/2 |
| xml | count |  |  | 0/1 |
| xml | enumerate |  |  | 0/1 |
| xml | lookup |  |  | 0/1 |
| pypi | count |  |  | 1/1 |
| pypi | enumerate |  |  | 0/1 |
| pypi | lookup |  |  | 0/1 |

## Sufficiency, query on (tasks whose tool call would name what is asked)

| format | kind | S | M | L |
|---|---|---|---|---|
| json | lookup | 2/2 | 2/2 | 2/2 |
| log | lookup | 2/2 | 2/2 | 2/2 |
| a11y | lookup | 2/2 | 2/2 | 2/2 |
| figma | lookup | 2/2 | 2/2 | 2/2 |
| xml | count |  |  | 1/1 |
| xml | enumerate |  |  | 1/1 |
| xml | lookup |  |  | 1/1 |
| pypi | enumerate |  |  | 1/1 |
| pypi | lookup |  |  | 1/1 |

## Size, query off

| format | band | tasks | median tokens in | median out | median kept | over budget |
|---|---|---|---|---|---|---|
| json | S | 9 | 1364 | 1364 | 100% | 0 |
| json | M | 9 | 6794 | 427 | 6% | 0 |
| json | L | 9 | 34028 | 430 | 1% | 0 |
| log | S | 9 | 1239 | 1239 | 100% | 0 |
| log | M | 9 | 6180 | 1001 | 16% | 0 |
| log | L | 9 | 41209 | 996 | 2% | 0 |
| a11y | S | 9 | 1181 | 1181 | 100% | 0 |
| a11y | M | 9 | 5670 | 5670 | 100% | 0 |
| a11y | L | 9 | 18790 | 5309 | 28% | 0 |
| figma | S | 9 | 1424 | 1424 | 100% | 0 |
| figma | M | 9 | 7050 | 5547 | 79% | 0 |
| figma | L | 9 | 35625 | 5565 | 16% | 0 |
| python | S | 1 | 856 | 856 | 100% | 0 |
| python | M | 2 | 3220 | 3220 | 100% | 0 |
| python | L | 8 | 22699 | 5355 | 24% | 0 |
| rust | L | 6 | 34705 | 5414 | 18% | 0 |
| xml | L | 3 | 83067 | 5201 | 6% | 0 |
| pypi | L | 3 | 25628 | 4708 | 18% | 0 |

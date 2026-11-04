# Layer 1: the fold alone, budget 2000 tokens

View: sample. Knobs: defaults.

201 folds of 172 tasks. Sufficient = the task's scorer finds
the answer in the fold text (an upper bound on what a model can answer without fetching more).

Sufficient overall: 140/201; over the folds that folded (not passed through): 91/152.

## Invariants: 0 folds with violations

None.

## Sufficiency, query off

| format | kind | S | M | L |
|---|---|---|---|---|
| json | absent | 1/1 | 1/1 | 1/1 |
| json | count | 2/2 | 4/4 | 4/4 |
| json | enumerate | 1/1 | 1/2 | 2/2 |
| json | lookup | 2/2 | 0/2 | 0/2 |
| json | spot | 4/4 | 3/4 | 3/4 |
| log | absent | 1/1 | 1/1 | 1/1 |
| log | count | 2/2 | 3/4 | 2/4 |
| log | enumerate | 1/1 | 1/2 | 1/2 |
| log | lookup | 2/2 | 0/2 | 0/2 |
| log | spot | 4/4 | 3/4 | 3/4 |
| a11y | absent | 1/1 | 1/1 | 1/1 |
| a11y | count | 2/2 | 2/4 | 2/4 |
| a11y | enumerate | 1/1 | 1/2 | 1/2 |
| a11y | lookup | 2/2 | 0/2 | 0/2 |
| a11y | spot | 4/4 | 3/4 | 3/4 |
| figma | absent | 1/1 | 1/1 | 1/1 |
| figma | count | 2/2 | 2/4 | 2/4 |
| figma | enumerate | 1/1 | 1/2 | 1/2 |
| figma | lookup | 2/2 | 0/2 | 0/2 |
| figma | spot | 4/4 | 3/4 | 3/4 |
| python | count |  | 1/1 | 1/2 |
| python | edit |  |  | 1/5 |
| python | enumerate | 1/1 |  | 1/3 |
| python | locate |  | 1/1 | 0/3 |
| rust | count |  |  | 1/2 |
| rust | enumerate |  |  | 1/2 |
| rust | locate |  |  | 1/2 |
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
| xml | count |  |  | 0/1 |
| xml | enumerate |  |  | 1/1 |
| xml | lookup |  |  | 1/1 |
| pypi | enumerate |  |  | 1/1 |
| pypi | lookup |  |  | 1/1 |

## Size, query off

| format | band | tasks | median tokens in | median out | median kept | over budget |
|---|---|---|---|---|---|---|
| json | S | 10 | 1360 | 1360 | 100% | 0 |
| json | M | 13 | 6780 | 425 | 6% | 0 |
| json | L | 13 | 33852 | 428 | 1% | 0 |
| log | S | 10 | 1237 | 1237 | 100% | 0 |
| log | M | 13 | 6185 | 993 | 16% | 0 |
| log | L | 13 | 41210 | 996 | 2% | 0 |
| a11y | S | 10 | 1201 | 1201 | 100% | 0 |
| a11y | M | 13 | 5693 | 1735 | 30% | 0 |
| a11y | L | 13 | 18793 | 1735 | 9% | 0 |
| figma | S | 10 | 1488 | 1488 | 100% | 0 |
| figma | M | 13 | 7350 | 1835 | 25% | 0 |
| figma | L | 13 | 36734 | 1848 | 5% | 0 |
| python | S | 1 | 856 | 856 | 100% | 0 |
| python | M | 2 | 3220 | 1744 | 54% | 0 |
| python | L | 13 | 22699 | 1756 | 8% | 0 |
| rust | L | 6 | 34705 | 1726 | 6% | 0 |
| xml | L | 3 | 83067 | 1709 | 2% | 0 |
| pypi | L | 3 | 25628 | 886 | 3% | 0 |

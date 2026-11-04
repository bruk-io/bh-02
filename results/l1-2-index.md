# Layer 1: the fold alone, budget 2000 tokens

View: sample. Knobs: defaults.

284 folds of 251 tasks. Sufficient = the task's scorer finds
the answer in the fold text (an upper bound on what a model can answer without fetching more).

Sufficient overall: 204/284; over the folds that folded (not passed through): 155/235.

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
| log | absent | 1/1 | 1/1 | 1/1 |
| log | count | 2/2 | 4/4 | 4/4 |
| log | enumerate | 1/1 | 2/2 | 2/2 |
| log | lookup | 2/2 | 0/2 | 0/2 |
| log | spot | 4/4 | 4/4 | 4/4 |
| a11y | absent | 1/1 | 1/1 | 1/1 |
| a11y | count | 2/2 | 4/4 | 4/4 |
| a11y | enumerate | 1/1 | 2/2 | 2/2 |
| a11y | lookup | 2/2 | 0/2 | 0/2 |
| a11y | spot | 4/4 | 3/4 | 3/4 |
| figma | absent | 1/1 | 1/1 | 1/1 |
| figma | count | 2/2 | 4/4 | 4/4 |
| figma | enumerate | 1/1 | 2/2 | 2/2 |
| figma | lookup | 2/2 | 0/2 | 0/2 |
| figma | spot | 4/4 | 4/4 | 4/4 |
| hdfs | absent |  | 0/1 | 1/1 |
| hdfs | count |  | 2/2 | 1/2 |
| hdfs | enumerate |  | 1/1 | 1/1 |
| hdfs | lookup |  | 0/2 | 0/2 |
| hdfs | spot |  | 2/4 | 2/4 |
| atlas | claims |  | 15/42 | 2/17 |
| python | count |  | 1/1 | 1/2 |
| python | edit |  |  | 4/5 |
| python | enumerate | 1/1 |  | 2/3 |
| python | locate |  | 1/1 | 3/3 |
| rust | count |  |  | 2/2 |
| rust | enumerate |  |  | 2/2 |
| rust | locate |  |  | 2/2 |
| xml | count |  |  | 0/1 |
| xml | enumerate |  |  | 0/1 |
| xml | lookup |  |  | 0/1 |
| pypi | count |  |  | 1/1 |
| pypi | enumerate |  |  | 1/1 |
| pypi | lookup |  |  | 0/1 |

## Sufficiency, query on (tasks whose tool call would name what is asked)

| format | kind | S | M | L |
|---|---|---|---|---|
| json | lookup | 2/2 | 2/2 | 2/2 |
| log | lookup | 2/2 | 2/2 | 2/2 |
| a11y | lookup | 2/2 | 2/2 | 2/2 |
| figma | lookup | 2/2 | 2/2 | 2/2 |
| hdfs | lookup |  | 0/2 | 2/2 |
| xml | count |  |  | 1/1 |
| xml | enumerate |  |  | 1/1 |
| xml | lookup |  |  | 1/1 |
| pypi | enumerate |  |  | 1/1 |
| pypi | lookup |  |  | 1/1 |

## Size, query off

| format | band | tasks | median tokens in | median out | median kept | over budget |
|---|---|---|---|---|---|---|
| json | S | 10 | 1360 | 1360 | 100% | 0 |
| json | M | 13 | 6780 | 331 | 5% | 0 |
| json | L | 13 | 33852 | 383 | 1% | 0 |
| log | S | 10 | 1237 | 1237 | 100% | 0 |
| log | M | 13 | 6185 | 255 | 4% | 0 |
| log | L | 13 | 41210 | 256 | 1% | 0 |
| a11y | S | 10 | 1201 | 1201 | 100% | 0 |
| a11y | M | 13 | 5693 | 249 | 4% | 0 |
| a11y | L | 13 | 18793 | 251 | 1% | 0 |
| figma | S | 10 | 1488 | 1488 | 100% | 0 |
| figma | M | 13 | 7350 | 327 | 4% | 0 |
| figma | L | 13 | 36734 | 333 | 1% | 0 |
| hdfs | M | 10 | 8441 | 837 | 10% | 0 |
| hdfs | L | 10 | 69335 | 747 | 1% | 0 |
| atlas | M | 42 | 4673 | 457 | 7% | 0 |
| atlas | L | 17 | 37541 | 428 | 2% | 0 |
| python | S | 1 | 856 | 856 | 100% | 0 |
| python | M | 2 | 3220 | 626 | 19% | 0 |
| python | L | 13 | 22699 | 1286 | 5% | 0 |
| rust | L | 6 | 34705 | 1877 | 6% | 0 |
| xml | L | 3 | 83067 | 1353 | 2% | 0 |
| pypi | L | 3 | 25628 | 1069 | 4% | 0 |

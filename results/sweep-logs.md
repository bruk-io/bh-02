# Sweep logs: layer 1 over 16 points

Each row folds the same tasks under one point of the grid. Sufficient = the task's scorer finds the answer in the fold text; the kind columns count every fold of that kind; quiet = the quiet anomalies (no rule names them); median out = tokens shown; violations = folds that broke an invariant or made a false claim.

| log_envelope.anomalies | log_envelope.samples | budget | sufficient | of folded | spot | absent | lookup | enumerate | count | quiet | median out | violations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rare | none | 500 | 30/66 | 30/66 | 14/20 | 4/5 | 0/20 | 5/7 | 7/14 | 3/3 | 273 | 0 |
| rare | none | 2000 | 44/66 | 32/54 | 16/20 | 4/5 | 4/20 | 7/7 | 13/14 | 3/3 | 444 | 0 |
| rare | matches | 500 | 37/66 | 37/66 | 14/20 | 4/5 | 7/20 | 5/7 | 7/14 | 3/3 | 273 | 0 |
| rare | matches | 2000 | 50/66 | 38/54 | 16/20 | 4/5 | 10/20 | 7/7 | 13/14 | 3/3 | 444 | 0 |
| rare | typical | 500 | 37/66 | 37/66 | 14/20 | 4/5 | 7/20 | 5/7 | 7/14 | 3/3 | 341 | 0 |
| rare | typical | 2000 | 50/66 | 38/54 | 16/20 | 4/5 | 10/20 | 7/7 | 13/14 | 3/3 | 536 | 0 |
| rare | head-tail | 500 | 37/66 | 37/66 | 14/20 | 4/5 | 7/20 | 5/7 | 7/14 | 3/3 | 374 | 0 |
| rare | head-tail | 2000 | 50/66 | 38/54 | 16/20 | 4/5 | 10/20 | 7/7 | 13/14 | 3/3 | 594 | 0 |
| errors | none | 500 | 29/66 | 29/66 | 12/20 | 5/5 | 0/20 | 5/7 | 7/14 | 0/3 | 273 | 0 |
| errors | none | 2000 | 40/66 | 28/54 | 13/20 | 5/5 | 4/20 | 6/7 | 12/14 | 1/3 | 410 | 0 |
| errors | matches | 500 | 36/66 | 36/66 | 12/20 | 5/5 | 7/20 | 5/7 | 7/14 | 0/3 | 273 | 0 |
| errors | matches | 2000 | 46/66 | 34/54 | 13/20 | 5/5 | 10/20 | 6/7 | 12/14 | 1/3 | 410 | 0 |
| errors | typical | 500 | 36/66 | 36/66 | 12/20 | 5/5 | 7/20 | 5/7 | 7/14 | 0/3 | 341 | 0 |
| errors | typical | 2000 | 46/66 | 34/54 | 13/20 | 5/5 | 10/20 | 6/7 | 12/14 | 1/3 | 521 | 0 |
| errors | head-tail | 500 | 36/66 | 36/66 | 12/20 | 5/5 | 7/20 | 5/7 | 7/14 | 0/3 | 374 | 0 |
| errors | head-tail | 2000 | 49/66 | 37/54 | 14/20 | 5/5 | 10/20 | 7/7 | 13/14 | 1/3 | 593 | 0 |

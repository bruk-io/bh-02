# Sweep envelopes: layer 1 over 32 points

Each row folds the same tasks under one point of the grid. Sufficient = the task's scorer finds the answer in the fold text; the kind columns count every fold of that kind; quiet = the quiet anomalies (no rule names them); median out = tokens shown; violations = folds that broke an invariant or made a false claim.

| json_envelope.shape | json_envelope.anomalies | json_envelope.samples | budget | sufficient | of folded | spot | absent | lookup | enumerate | count | quiet | median out | violations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fields | exceptions | none | 500 | 28/47 | 28/47 | 12/12 | 3/3 | 0/14 | 2/7 | 11/11 | 3/3 | 195 | 0 |
| fields | exceptions | none | 2000 | 36/47 | 24/35 | 12/12 | 3/3 | 4/14 | 6/7 | 11/11 | 3/3 | 225 | 0 |
| fields | exceptions | matches | 500 | 34/47 | 34/47 | 12/12 | 3/3 | 6/14 | 2/7 | 11/11 | 3/3 | 225 | 0 |
| fields | exceptions | matches | 2000 | 41/47 | 29/35 | 12/12 | 3/3 | 9/14 | 6/7 | 11/11 | 3/3 | 245 | 0 |
| fields | exceptions | typical | 500 | 34/47 | 34/47 | 12/12 | 3/3 | 6/14 | 2/7 | 11/11 | 3/3 | 292 | 0 |
| fields | exceptions | typical | 2000 | 41/47 | 29/35 | 12/12 | 3/3 | 9/14 | 6/7 | 11/11 | 3/3 | 310 | 0 |
| fields | exceptions | head-tail | 500 | 34/47 | 34/47 | 12/12 | 3/3 | 6/14 | 2/7 | 11/11 | 3/3 | 412 | 0 |
| fields | exceptions | head-tail | 2000 | 41/47 | 29/35 | 12/12 | 3/3 | 9/14 | 6/7 | 11/11 | 3/3 | 438 | 0 |
| fields | standouts | none | 500 | 29/47 | 29/47 | 9/12 | 3/3 | 6/14 | 0/7 | 11/11 | 0/3 | 292 | 0 |
| fields | standouts | none | 2000 | 37/47 | 25/35 | 10/12 | 3/3 | 8/14 | 5/7 | 11/11 | 1/3 | 295 | 0 |
| fields | standouts | matches | 500 | 29/47 | 29/47 | 9/12 | 3/3 | 6/14 | 0/7 | 11/11 | 0/3 | 315 | 0 |
| fields | standouts | matches | 2000 | 38/47 | 26/35 | 10/12 | 3/3 | 9/14 | 5/7 | 11/11 | 1/3 | 327 | 0 |
| fields | standouts | typical | 500 | 29/47 | 29/47 | 9/12 | 3/3 | 6/14 | 0/7 | 11/11 | 0/3 | 380 | 0 |
| fields | standouts | typical | 2000 | 38/47 | 26/35 | 10/12 | 3/3 | 9/14 | 5/7 | 11/11 | 1/3 | 391 | 0 |
| fields | standouts | head-tail | 500 | 29/47 | 29/47 | 9/12 | 3/3 | 6/14 | 0/7 | 11/11 | 0/3 | 457 | 0 |
| fields | standouts | head-tail | 2000 | 39/47 | 27/35 | 10/12 | 3/3 | 9/14 | 6/7 | 11/11 | 1/3 | 521 | 0 |
| summary | exceptions | none | 500 | 29/47 | 29/47 | 12/12 | 3/3 | 0/14 | 3/7 | 11/11 | 3/3 | 140 | 0 |
| summary | exceptions | none | 2000 | 34/47 | 22/35 | 12/12 | 3/3 | 4/14 | 4/7 | 11/11 | 3/3 | 168 | 0 |
| summary | exceptions | matches | 500 | 35/47 | 35/47 | 12/12 | 3/3 | 6/14 | 3/7 | 11/11 | 3/3 | 168 | 0 |
| summary | exceptions | matches | 2000 | 39/47 | 27/35 | 12/12 | 3/3 | 9/14 | 4/7 | 11/11 | 3/3 | 178 | 0 |
| summary | exceptions | typical | 500 | 35/47 | 35/47 | 12/12 | 3/3 | 6/14 | 3/7 | 11/11 | 3/3 | 234 | 0 |
| summary | exceptions | typical | 2000 | 39/47 | 27/35 | 12/12 | 3/3 | 9/14 | 4/7 | 11/11 | 3/3 | 242 | 0 |
| summary | exceptions | head-tail | 500 | 35/47 | 35/47 | 12/12 | 3/3 | 6/14 | 3/7 | 11/11 | 3/3 | 364 | 0 |
| summary | exceptions | head-tail | 2000 | 39/47 | 27/35 | 12/12 | 3/3 | 9/14 | 4/7 | 11/11 | 3/3 | 371 | 0 |
| summary | standouts | none | 500 | 32/47 | 32/47 | 9/12 | 3/3 | 6/14 | 3/7 | 11/11 | 0/3 | 235 | 0 |
| summary | standouts | none | 2000 | 35/47 | 23/35 | 10/12 | 3/3 | 8/14 | 3/7 | 11/11 | 1/3 | 238 | 0 |
| summary | standouts | matches | 500 | 32/47 | 32/47 | 9/12 | 3/3 | 6/14 | 3/7 | 11/11 | 0/3 | 255 | 0 |
| summary | standouts | matches | 2000 | 36/47 | 24/35 | 10/12 | 3/3 | 9/14 | 3/7 | 11/11 | 1/3 | 259 | 0 |
| summary | standouts | typical | 500 | 32/47 | 32/47 | 9/12 | 3/3 | 6/14 | 3/7 | 11/11 | 0/3 | 319 | 0 |
| summary | standouts | typical | 2000 | 36/47 | 24/35 | 10/12 | 3/3 | 9/14 | 3/7 | 11/11 | 1/3 | 323 | 0 |
| summary | standouts | head-tail | 500 | 32/47 | 32/47 | 9/12 | 3/3 | 6/14 | 3/7 | 11/11 | 0/3 | 431 | 0 |
| summary | standouts | head-tail | 2000 | 37/47 | 25/35 | 10/12 | 3/3 | 9/14 | 4/7 | 11/11 | 1/3 | 453 | 0 |

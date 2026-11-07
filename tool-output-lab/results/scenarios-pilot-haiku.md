# Scenarios, layer 2: code and tests on claude-haiku-5-5

150 runs, 0 failed to produce an answer (not scored).
Spent $0.49.

| task | size | condition | right | median turns | median final context | median cost | runs with a large output |
|---|---|---|---|---|---|---|---|
| failing | L | native | 15 of 15 (100%) | 3 | 36,950 | $0.0024 | 0 of 15 |
| failing | M | native | 15 of 15 (100%) | 3 | 36,223 | $0.0023 | 0 of 15 |
| commit | L | native | 15 of 15 (100%) | 5 | 40,026 | $0.0048 | 1 of 15 |
| commit | M | native | 15 of 15 (100%) | 4 | 38,795 | $0.0041 | 0 of 15 |
| callers | L | native | 15 of 15 (100%) | 3 | 36,390 | $0.0027 | 0 of 15 |
| callers | M | native | 15 of 15 (100%) | 3 | 35,893 | $0.0025 | 0 of 15 |
| lookup | L | native | 15 of 15 (100%) | 4 | 36,401 | $0.0029 | 2 of 15 |
| lookup | M | native | 15 of 15 (100%) | 4 | 36,255 | $0.0029 | 0 of 15 |
| edit | L | native | 15 of 15 (100%) | 4 | 36,425 | $0.0031 | 6 of 15 |
| edit | M | native | 15 of 15 (100%) | 4 | 43,129 | $0.0040 | 9 of 15 |

## Calls whose output was over 2,000 tokens

| call | times | median tokens |
|---|---|---|
| `Bash: cat -n shop/tax.py` | 3 | 4,447 |
| `Grep: regional_rebate_for_quantity` | 2 | 3,047 |
| `Bash: cat -n /tmp/scenario-jvf71oij/repo/shop/tax.py` | 1 | 4,427 |
| `Bash: cat -n shop/shipping.py` | 1 | 6,565 |
| `Bash: grep -rn "def` | 1 | 6,572 |
| `Bash: cat -n shop/deposits.py` | 1 | 6,617 |
| `Bash: cat shop/coupons.py &&` | 1 | 3,656 |
| `Read: /tmp/scenario-cegy6sf6/repo/shop/tax.py` | 1 | 4,086 |
| `Bash: cat shop/tax.py &&` | 1 | 3,668 |
| `Read: /tmp/scenario-emzleanb/repo/shop/shipping.py` | 1 | 6,035 |
| `Bash: cat shop/deposits.py &&` | 1 | 5,462 |
| `Bash: cat shop/coupons.py` | 1 | 3,645 |
| `Bash: cat -n shop/returns.py` | 1 | 2,571 |
| `Bash: cat -n shop/coupons.py` | 1 | 6,570 |
| `Read: /tmp/scenario-24pjsjqp/repo/shop/shipping.py` | 1 | 6,035 |

## Some misses


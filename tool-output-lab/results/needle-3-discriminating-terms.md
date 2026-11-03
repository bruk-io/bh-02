# Needle survival

Budget 2000 tokens, 5 seeds per cell, positions 0%, 5%, 25%, 50%, 75%, 95%, 100%. Survival means the needle's unique string is in the compressed text.

## By kind (query from tool arguments on / off)

| format | kind | survived, query on | survived, query off | tokens kept (median) |
|---|---|---|---|---|
| json | rare_value | 100% | 100% | 1.5% |
| json | nested_rare_value | 100% | 100% | 1.4% |
| json | error_key | 100% | 100% | 1.4% |
| json | bool_flip | 100% | 100% | 1.4% |
| json | query_match | 100% | 29% | 1.4% |
| json | numeric_outlier | 29% | 29% | 1.1% |
| log | error_word | 100% | 100% | 2.7% |
| log | query_match | 100% | 38% | 2.6% |
| log | stack_trace_tail | 100% | 100% | 2.9% |
| log | quiet_line | 38% | 38% | 2.3% |

## By position, query off

| format | kind | 0% | 5% | 25% | 50% | 75% | 95% | 100% |
|---|---|---|---|---|---|---|---|---|
| json | rare_value | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| json | nested_rare_value | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| json | error_key | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| json | bool_flip | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| json | query_match | 100% | 0% | 0% | 0% | 0% | 0% | 100% |
| json | numeric_outlier | 100% | 0% | 0% | 0% | 0% | 0% | 100% |
| log | error_word | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| log | query_match | 100% | 33% | 0% | 0% | 0% | 33% | 100% |
| log | stack_trace_tail | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| log | quiet_line | 100% | 33% | 0% | 0% | 0% | 33% | 100% |

## By size, query off

| format | kind | size | survived | tokens in (median) | out (median) |
|---|---|---|---|---|---|
| json | rare_value | 50 | 100% | 3106 | 451 |
| json | rare_value | 500 | 100% | 31006 | 454 |
| json | rare_value | 5000 | 100% | 310006 | 458 |
| json | nested_rare_value | 50 | 100% | 3103 | 427 |
| json | nested_rare_value | 500 | 100% | 31003 | 430 |
| json | nested_rare_value | 5000 | 100% | 310003 | 434 |
| json | error_key | 50 | 100% | 3113 | 439 |
| json | error_key | 500 | 100% | 31013 | 442 |
| json | error_key | 5000 | 100% | 310013 | 445 |
| json | bool_flip | 50 | 100% | 3104 | 437 |
| json | bool_flip | 500 | 100% | 31004 | 441 |
| json | bool_flip | 5000 | 100% | 310004 | 444 |
| json | query_match | 50 | 29% | 3103 | 328 |
| json | query_match | 500 | 29% | 31003 | 330 |
| json | query_match | 5000 | 29% | 310003 | 332 |
| json | numeric_outlier | 50 | 29% | 3104 | 331 |
| json | numeric_outlier | 500 | 29% | 31004 | 333 |
| json | numeric_outlier | 5000 | 29% | 310004 | 335 |
| log | error_word | 200 | 100% | 3006 | 731 |
| log | error_word | 2000 | 100% | 29994 | 807 |
| log | error_word | 20000 | 100% | 300345 | 810 |
| log | query_match | 200 | 57% | 2999 | 711 |
| log | query_match | 2000 | 29% | 30042 | 699 |
| log | query_match | 20000 | 29% | 300260 | 703 |
| log | stack_trace_tail | 200 | 100% | 3074 | 723 |
| log | stack_trace_tail | 2000 | 100% | 30111 | 875 |
| log | stack_trace_tail | 20000 | 100% | 300416 | 885 |
| log | quiet_line | 200 | 57% | 3012 | 708 |
| log | quiet_line | 2000 | 29% | 30053 | 701 |
| log | quiet_line | 20000 | 29% | 300312 | 714 |

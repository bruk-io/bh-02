# Needle survival

Budget 2000 tokens, 3 seeds per cell, positions 0%, 5%, 25%, 50%, 75%, 95%, 100%. Survival means the needle's unique string is in the compressed text.

## By kind (query from tool arguments on / off)

| format | kind | survived, query on | survived, query off | tokens kept (median) |
|---|---|---|---|---|
| json | rare_value | 100% | 100% | 1.4% |
| json | nested_rare_value | 100% | 100% | 1.4% |
| json | error_key | 100% | 100% | 1.4% |
| json | bool_flip | 100% | 100% | 1.4% |
| json | query_match | 100% | 29% | 1.4% |
| json | numeric_outlier | 29% | 29% | 1.1% |
| log | error_word | 100% | 100% | 2.6% |
| log | query_match | 100% | 38% | 2.6% |
| log | stack_trace_tail | 100% | 100% | 2.9% |
| log | quiet_line | 38% | 38% | 2.3% |
| a11y | disabled_button | 50% | 50% | 44.9% |
| a11y | error_alert | 50% | 50% | 44.6% |
| a11y | lookup | 79% | 43% | 45.0% |
| figma | hidden_layer | 100% | 100% | 20.4% |
| figma | variant_mismatch | 100% | 100% | 20.3% |
| figma | lookup | 100% | 64% | 20.4% |

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
| a11y | disabled_button | 50% | 50% | 50% | 50% | 50% | 50% | 50% |
| a11y | error_alert | 50% | 50% | 50% | 50% | 50% | 50% | 50% |
| a11y | lookup | 100% | 100% | 50% | 50% | 0% | 0% | 0% |
| figma | hidden_layer | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| figma | variant_mismatch | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| figma | lookup | 100% | 50% | 50% | 50% | 50% | 50% | 100% |

## By size, query off

| format | kind | size | survived | tokens in (median) | out (median) |
|---|---|---|---|---|---|
| json | rare_value | 50 | 100% | 3106 | 444 |
| json | rare_value | 500 | 100% | 31006 | 448 |
| json | rare_value | 5000 | 100% | 310006 | 451 |
| json | nested_rare_value | 50 | 100% | 3103 | 427 |
| json | nested_rare_value | 500 | 100% | 31003 | 430 |
| json | nested_rare_value | 5000 | 100% | 310003 | 434 |
| json | error_key | 50 | 100% | 3113 | 439 |
| json | error_key | 500 | 100% | 31013 | 442 |
| json | error_key | 5000 | 100% | 310013 | 445 |
| json | bool_flip | 50 | 100% | 3104 | 433 |
| json | bool_flip | 500 | 100% | 31004 | 437 |
| json | bool_flip | 5000 | 100% | 310004 | 440 |
| json | query_match | 50 | 29% | 3103 | 328 |
| json | query_match | 500 | 29% | 31003 | 330 |
| json | query_match | 5000 | 29% | 310003 | 332 |
| json | numeric_outlier | 50 | 29% | 3104 | 331 |
| json | numeric_outlier | 500 | 29% | 31004 | 333 |
| json | numeric_outlier | 5000 | 29% | 310004 | 335 |
| log | error_word | 200 | 100% | 3007 | 733 |
| log | error_word | 2000 | 100% | 29994 | 797 |
| log | error_word | 20000 | 100% | 300368 | 800 |
| log | query_match | 200 | 57% | 2999 | 714 |
| log | query_match | 2000 | 29% | 30048 | 699 |
| log | query_match | 20000 | 29% | 300415 | 710 |
| log | stack_trace_tail | 200 | 100% | 3077 | 740 |
| log | stack_trace_tail | 2000 | 100% | 30103 | 878 |
| log | stack_trace_tail | 20000 | 100% | 300429 | 889 |
| log | quiet_line | 200 | 57% | 3010 | 703 |
| log | quiet_line | 2000 | 29% | 30054 | 697 |
| log | quiet_line | 20000 | 29% | 300331 | 713 |
| a11y | disabled_button | 50 | 0% | 2234 | 1813 |
| a11y | disabled_button | 500 | 100% | 21015 | 1824 |
| a11y | error_alert | 50 | 0% | 2250 | 1813 |
| a11y | error_alert | 500 | 100% | 21031 | 1815 |
| a11y | lookup | 50 | 57% | 2231 | 1813 |
| a11y | lookup | 500 | 29% | 21012 | 1809 |
| figma | hidden_layer | 50 | 100% | 5001 | 1849 |
| figma | hidden_layer | 500 | 100% | 50024 | 1893 |
| figma | variant_mismatch | 50 | 100% | 4998 | 1845 |
| figma | variant_mismatch | 500 | 100% | 50021 | 1890 |
| figma | lookup | 50 | 100% | 4997 | 1845 |
| figma | lookup | 500 | 29% | 50021 | 1877 |

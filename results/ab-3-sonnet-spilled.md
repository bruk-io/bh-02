# A/B: native Claude Code against the fold hook (claude-sonnet-5-5)

26 runs, $2.66 in all. Correct = the final answer names the planted needle.
Tokens are all input tokens (cached or not) summed over the session's requests, so they include
Claude Code's own system prompt; the difference between conditions is what matters.

| format | kind | size | condition | correct | median input tokens | median cost | median calls | read file |
|---|---|---|---|---|---|---|---|---|
| a11y | disabled_button | 500 | fold | 1/1 | 235187 | $0.1101 | 3 | 1/1 |
| a11y | disabled_button | 500 | native | 1/1 | 184105 | $0.1044 | 4 | 1/1 |
| a11y | error_alert | 500 | fold | 1/1 | 141115 | $0.0970 | 2 | 1/1 |
| a11y | error_alert | 500 | native | 1/1 | 226083 | $0.0994 | 3 | 1/1 |
| a11y | lookup | 500 | fold | 1/1 | 185779 | $0.0991 | 2 | 1/1 |
| a11y | lookup | 500 | native | 1/1 | 134875 | $0.0844 | 2 | 1/1 |
| figma | hidden_layer | 500 | fold | 1/1 | 235093 | $0.1143 | 3 | 1/1 |
| figma | hidden_layer | 500 | native | 1/1 | 277402 | $0.1185 | 4 | 1/1 |
| figma | lookup | 500 | fold | 1/1 | 185555 | $0.0994 | 2 | 1/1 |
| figma | lookup | 500 | native | 1/1 | 179711 | $0.0899 | 2 | 1/1 |
| figma | variant_mismatch | 500 | fold | 1/1 | 235371 | $0.1151 | 3 | 1/1 |
| figma | variant_mismatch | 500 | native | 1/1 | 227234 | $0.1030 | 3 | 1/1 |
| json | bool_flip | 500 | fold | 1/1 | 180511 | $0.0927 | 2 | 1/1 |
| json | bool_flip | 500 | native | 1/1 | 273946 | $0.1096 | 4 | 1/1 |
| json | error_key | 500 | fold | 1/1 | 180558 | $0.0952 | 2 | 1/1 |
| json | error_key | 500 | native | 1/1 | 274668 | $0.1162 | 4 | 1/1 |
| json | numeric_outlier | 500 | fold | 1/1 | 180315 | $0.0916 | 2 | 1/1 |
| json | numeric_outlier | 500 | native | 1/1 | 273808 | $0.1091 | 4 | 1/1 |
| json | rare_value | 500 | fold | 1/1 | 180660 | $0.0952 | 2 | 1/1 |
| json | rare_value | 500 | native | 1/1 | 227794 | $0.1073 | 3 | 1/1 |
| log | error_word | 2000 | fold | 1/1 | 182403 | $0.0941 | 2 | 1/1 |
| log | error_word | 2000 | native | 1/1 | 275500 | $0.1128 | 4 | 1/1 |
| log | quiet_line | 2000 | fold | 0/1 | 230700 | $0.1094 | 3 | 1/1 |
| log | quiet_line | 2000 | native | 0/1 | 225617 | $0.1002 | 4 | 1/1 |
| log | stack_trace_tail | 2000 | fold | 1/1 | 182564 | $0.0955 | 2 | 1/1 |
| log | stack_trace_tail | 2000 | native | 1/1 | 225668 | $0.0988 | 3 | 1/1 |

## By condition

| condition | correct | total cost | median input tokens | median duration |
|---|---|---|---|---|
| native | 12/13 | $1.35 | 227234 | 20.6s |
| fold | 12/13 | $1.31 | 182564 | 18.3s |

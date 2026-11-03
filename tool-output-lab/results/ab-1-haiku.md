# A/B: native Claude Code against the fold hook (claude-haiku-5-5)

56 runs, $0.36 in all. Correct = the final answer names the planted needle.
Tokens are all input tokens (cached or not) summed over the session's requests, so they include
Claude Code's own system prompt; the difference between conditions is what matters.

| format | kind | size | condition | correct | median input tokens | median cost | median calls | read file |
|---|---|---|---|---|---|---|---|---|
| json | bool_flip | 50 | fold | 2/2 | 185209 | $0.0059 | 2.0 | 2/2 |
| json | bool_flip | 50 | native | 2/2 | 141920 | $0.0059 | 1.0 | 0/2 |
| json | bool_flip | 500 | fold | 2/2 | 191133 | $0.0072 | 2.0 | 2/2 |
| json | bool_flip | 500 | native | 2/2 | 304946 | $0.0077 | 4.5 | 2/2 |
| json | error_key | 50 | fold | 2/2 | 186977 | $0.0063 | 2.0 | 2/2 |
| json | error_key | 50 | native | 2/2 | 141909 | $0.0059 | 1.0 | 0/2 |
| json | error_key | 500 | fold | 2/2 | 184236 | $0.0057 | 2.0 | 2/2 |
| json | error_key | 500 | native | 2/2 | 281465 | $0.0074 | 4.0 | 2/2 |
| json | numeric_outlier | 50 | fold | 2/2 | 185833 | $0.0060 | 2.0 | 2/2 |
| json | numeric_outlier | 50 | native | 2/2 | 141903 | $0.0059 | 1.0 | 0/2 |
| json | numeric_outlier | 500 | fold | 2/2 | 208844 | $0.0063 | 2.5 | 2/2 |
| json | numeric_outlier | 500 | native | 2/2 | 280054 | $0.0073 | 4.0 | 2/2 |
| json | rare_value | 50 | fold | 2/2 | 185418 | $0.0061 | 2.0 | 2/2 |
| json | rare_value | 50 | native | 2/2 | 141861 | $0.0060 | 1.0 | 0/2 |
| json | rare_value | 500 | fold | 2/2 | 185541 | $0.0061 | 2.0 | 2/2 |
| json | rare_value | 500 | native | 2/2 | 280513 | $0.0075 | 4.0 | 2/2 |
| log | error_word | 200 | fold | 2/2 | 186076 | $0.0059 | 2.0 | 2/2 |
| log | error_word | 200 | native | 2/2 | 142640 | $0.0060 | 1.0 | 0/2 |
| log | error_word | 2000 | fold | 2/2 | 186743 | $0.0060 | 2.0 | 2/2 |
| log | error_word | 2000 | native | 2/2 | 254423 | $0.0066 | 4.5 | 2/2 |
| log | quiet_line | 200 | fold | 0/2 | 210349 | $0.0064 | 2.5 | 2/2 |
| log | quiet_line | 200 | native | 2/2 | 142639 | $0.0061 | 1.0 | 0/2 |
| log | quiet_line | 2000 | fold | 1/2 | 233932 | $0.0066 | 3.5 | 2/2 |
| log | quiet_line | 2000 | native | 1/2 | 357258 | $0.0087 | 7.0 | 2/2 |
| log | stack_trace_tail | 200 | fold | 2/2 | 186178 | $0.0059 | 2.0 | 2/2 |
| log | stack_trace_tail | 200 | native | 2/2 | 142745 | $0.0060 | 1.0 | 0/2 |
| log | stack_trace_tail | 2000 | fold | 2/2 | 212274 | $0.0065 | 2.5 | 2/2 |
| log | stack_trace_tail | 2000 | native | 2/2 | 230876 | $0.0064 | 3.5 | 2/2 |

## By condition

| condition | correct | total cost | median input tokens | median duration |
|---|---|---|---|---|
| native | 27/28 | $0.19 | 186611 | 12.8s |
| fold | 25/28 | $0.17 | 186219 | 14.3s |

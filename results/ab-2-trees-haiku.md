# A/B: native Claude Code against the fold hook (claude-haiku-5-5)

48 runs, $0.33 in all. Correct = the final answer names the planted needle.
Tokens are all input tokens (cached or not) summed over the session's requests, so they include
Claude Code's own system prompt; the difference between conditions is what matters.

| format | kind | size | condition | correct | median input tokens | median cost | median calls | read file |
|---|---|---|---|---|---|---|---|---|
| a11y | disabled_button | 50 | fold | 2/2 | 217236 | $0.0071 | 2.5 | 2/2 |
| a11y | disabled_button | 50 | native | 2/2 | 140650 | $0.0058 | 1.0 | 0/2 |
| a11y | disabled_button | 500 | fold | 2/2 | 189639 | $0.0061 | 2.0 | 2/2 |
| a11y | disabled_button | 500 | native | 2/2 | 375664 | $0.0099 | 7.5 | 2/2 |
| a11y | error_alert | 50 | fold | 2/2 | 191002 | $0.0065 | 2.0 | 2/2 |
| a11y | error_alert | 50 | native | 2/2 | 140659 | $0.0056 | 1.0 | 0/2 |
| a11y | error_alert | 500 | fold | 2/2 | 189767 | $0.0061 | 2.0 | 2/2 |
| a11y | error_alert | 500 | native | 2/2 | 353763 | $0.0085 | 7.0 | 2/2 |
| a11y | lookup | 50 | fold | 2/2 | 139881 | $0.0053 | 1.0 | 0/2 |
| a11y | lookup | 50 | native | 2/2 | 140559 | $0.0055 | 1.0 | 0/2 |
| a11y | lookup | 500 | fold | 2/2 | 189639 | $0.0060 | 2.0 | 2/2 |
| a11y | lookup | 500 | native | 2/2 | 183713 | $0.0056 | 2.0 | 2/2 |
| figma | hidden_layer | 50 | fold | 2/2 | 215219 | $0.0067 | 2.5 | 2/2 |
| figma | hidden_layer | 50 | native | 2/2 | 145086 | $0.0065 | 1.0 | 0/2 |
| figma | hidden_layer | 500 | fold | 2/2 | 293668 | $0.0082 | 4.0 | 2/2 |
| figma | hidden_layer | 500 | native | 2/2 | 294315 | $0.0087 | 4.0 | 2/2 |
| figma | lookup | 50 | fold | 2/2 | 139880 | $0.0053 | 1.0 | 0/2 |
| figma | lookup | 50 | native | 2/2 | 145064 | $0.0064 | 1.0 | 0/2 |
| figma | lookup | 500 | fold | 2/2 | 189341 | $0.0060 | 2.0 | 2/2 |
| figma | lookup | 500 | native | 2/2 | 277817 | $0.0069 | 4.0 | 2/2 |
| figma | variant_mismatch | 50 | fold | 2/2 | 249615 | $0.0081 | 3.0 | 2/2 |
| figma | variant_mismatch | 50 | native | 2/2 | 145100 | $0.0065 | 1.0 | 0/2 |
| figma | variant_mismatch | 500 | fold | 2/2 | 215344 | $0.0067 | 2.5 | 2/2 |
| figma | variant_mismatch | 500 | native | 2/2 | 319964 | $0.0088 | 5.5 | 2/2 |

## By condition

| condition | correct | total cost | median input tokens | median duration |
|---|---|---|---|---|
| native | 24/24 | $0.17 | 164401 | 10.1s |
| fold | 24/24 | $0.16 | 189914 | 12.3s |

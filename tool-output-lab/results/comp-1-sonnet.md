# Comprehension A/B: Claude's own approach against `fold` named in CLAUDE.md (claude-sonnet-5-5)

20 runs, $1.62. Correct = the answer names at least 90%
of the expected items (computed with `ast`).

| question | condition | correct | mean recall | median input tokens | median cost | median calls | median time | ran fold |
|---|---|---|---|---|---|---|---|---|
| async-methods | native | 2/2 | 1.00 | 89116 | $0.0779 | 1.0 | 15.1s | 0/2 |
| async-methods | fold | 2/2 | 1.00 | 89701 | $0.0814 | 1.0 | 13.3s | 0/2 |
| both-platforms | native | 2/2 | 1.00 | 89209 | $0.0794 | 1.0 | 10.7s | 0/2 |
| both-platforms | fold | 2/2 | 1.00 | 160979 | $0.0977 | 2.5 | 15.4s | 0/2 |
| action-subclasses | native | 2/2 | 1.00 | 88955 | $0.0761 | 1.0 | 10.9s | 0/2 |
| action-subclasses | fold | 2/2 | 0.90 | 89431 | $0.0788 | 1.0 | 11.0s | 0/2 |
| close-methods | native | 2/2 | 1.00 | 88886 | $0.0746 | 1.0 | 10.0s | 0/2 |
| close-methods | fold | 2/2 | 1.00 | 89374 | $0.0763 | 1.0 | 10.5s | 0/2 |
| tp-cache | native | 2/2 | 1.00 | 136207 | $0.0887 | 2.0 | 11.9s | 0/2 |
| tp-cache | fold | 2/2 | 1.00 | 89513 | $0.0781 | 1.0 | 10.6s | 0/2 |

| condition | correct | mean recall | total cost | median input tokens | median time |
|---|---|---|---|---|---|
| native | 10/10 | 1.00 | $0.79 | 89116 | 11.6s |
| fold | 10/10 | 0.98 | $0.82 | 89513 | 10.6s |

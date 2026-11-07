# Layer 1 on the incident scenarios, size M, open seeds 0 to 4

Each task's probes (commands, or tool calls) run in its world; their real outputs are folded as
the hook folds them (the command, or the call's arguments, is the query), under the final recipe,
and checked.

## Invariants: 0 folds of 45 with violations

None.

## By task kind and command

| task | command | median output | folded | median envelope | answered by the envelope |
|---|---|---|---|---|---|
| cause | `list_deploys()` | 725 | 0 of 5 |  |  |
| cause | `get_logs(service=<service>)` | 9,560 | 5 of 5 | 1,437 | 0 of 5 |
| cause | `get_metrics(service=<service>)` | 1,967 | 0 of 5 |  |  |
| count | `get_logs(service=<service>, since=14:00)` | 4,866 | 5 of 5 | 1,386 | 0 of 5 |
| count | `get_logs(service=<service>)` | 9,560 | 5 of 5 | 1,437 | 0 of 5 |
| stale | `list_pods()` | 5,074 | 5 of 5 | 341 | 0 of 5 |
| gap | `get_logs(service=<service>)` | 9,443 | 5 of 5 | 246 | 0 of 5 |
| healthy | `get_logs(service=<service>)` | 14,545 | 5 of 5 | 1,052 | 0 of 5 |
| healthy | `get_metrics(service=<service>)` | 1,967 | 0 of 5 |  |  |

Answered by the envelope counts only the outputs it replaced: an output under the threshold
reaches the model whole. An edit is answered when the envelope shows the definition with its
line number, where the edit starts.

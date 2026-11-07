# Layer 1 on the incident scenarios, size L, open seeds 0 to 4

Each task's probes (commands, or tool calls) run in its world; their real outputs are folded as
the hook folds them (the command, or the call's arguments, is the query), under the final recipe,
and checked.

## Invariants: 0 folds of 45 with violations

None.

## By task kind and command

| task | command | median output | folded | median envelope | answered by the envelope |
|---|---|---|---|---|---|
| cause | `list_deploys()` | 961 | 0 of 5 |  |  |
| cause | `get_logs(service=<service>)` | 46,153 | 5 of 5 | 1,791 | 0 of 5 |
| cause | `get_metrics(service=<service>)` | 1,967 | 0 of 5 |  |  |
| count | `get_logs(service=<service>, since=14:00)` | 23,624 | 5 of 5 | 507 | 0 of 5 |
| count | `get_logs(service=<service>)` | 46,153 | 5 of 5 | 1,791 | 0 of 5 |
| stale | `list_pods()` | 22,730 | 5 of 5 | 377 | 0 of 5 |
| gap | `get_logs(service=<service>)` | 42,909 | 5 of 5 | 485 | 0 of 5 |
| healthy | `get_logs(service=<service>)` | 48,035 | 5 of 5 | 1,210 | 0 of 5 |
| healthy | `get_metrics(service=<service>)` | 1,967 | 0 of 5 |  |  |

Answered by the envelope counts only the outputs it replaced: an output under the threshold
reaches the model whole. An edit is answered when the envelope shows the definition with its
line number, where the edit starts.

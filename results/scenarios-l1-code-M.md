# Layer 1 on the code-and-tests scenarios, size M, open seeds 0 to 4

Each task's probe commands run in its built world; their real outputs are folded as the hook
folds a Bash result (the command is the query), under the final recipe, and checked.

## Invariants: 0 folds of 50 with violations

None.

## By task kind and command

| task | command | median output | folded | median envelope | answered by the envelope |
|---|---|---|---|---|---|
| failing | `./run-tests` | 549 | 0 of 5 |  |  |
| failing | `./run-tests -v` | 6,965 | 5 of 5 | 1,263 | 5 of 5 |
| commit | `git log` | 630 | 0 of 5 |  |  |
| commit | `git log -p` | 14,287 | 5 of 5 | 1,462 | 0 of 5 |
| commit | `git log --stat` | 1,090 | 0 of 5 |  |  |
| callers | `grep -rn <function> shop` | 61 | 0 of 5 |  |  |
| callers | `grep -rn <function> .` | 426 | 0 of 5 |  |  |
| lookup | `cat shop/<module>.py` | 3,646 | 5 of 5 | 1,824 | 1 of 5 |
| lookup | `sed -n '1,400p' shop/<module>.py` | 3,312 | 5 of 5 | 1,837 | 1 of 5 |
| edit | `cat shop/<module>.py` | 3,646 | 5 of 5 | 1,824 | 5 of 5 |

Answered by the envelope counts only the outputs it replaced: an output under the threshold
reaches the model whole. An edit is answered when the envelope shows the definition with its
line number, where the edit starts.

# Layer 1 on the code-and-tests scenarios, size L, open seeds 0 to 4

Each task's probe commands run in its built world; their real outputs are folded as the hook
folds a Bash result (the command is the query), under the final recipe, and checked.

## Invariants: 0 folds of 50 with violations

None.

## By task kind and command

| task | command | median output | folded | median envelope | answered by the envelope |
|---|---|---|---|---|---|
| failing | `./run-tests` | 1,212 | 0 of 5 |  |  |
| failing | `./run-tests -v` | 26,954 | 5 of 5 | 1,422 | 5 of 5 |
| commit | `git log` | 912 | 0 of 5 |  |  |
| commit | `git log -p` | 35,859 | 5 of 5 | 1,736 | 0 of 5 |
| commit | `git log --stat` | 1,606 | 0 of 5 |  |  |
| callers | `grep -rn <function> shop` | 62 | 0 of 5 |  |  |
| callers | `grep -rn <function> .` | 806 | 0 of 5 |  |  |
| lookup | `cat shop/<module>.py` | 5,403 | 5 of 5 | 1,691 | 0 of 5 |
| lookup | `sed -n '1,400p' shop/<module>.py` | 3,377 | 5 of 5 | 1,859 | 0 of 5 |
| edit | `cat shop/<module>.py` | 5,403 | 5 of 5 | 1,691 | 5 of 5 |

Answered by the envelope counts only the outputs it replaced: an output under the threshold
reaches the model whole. An edit is answered when the envelope shows the definition with its
line number, where the edit starts.

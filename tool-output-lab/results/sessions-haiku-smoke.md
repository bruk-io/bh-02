# Sessions haiku-smoke: claude-haiku-5-5, follow-up questions on one tool result

5 sessions, $0.09; 0 with a failed turn, left out whole. Each session asks its turns in one Claude Code process; each setting is paired against native by conversation and repetition.

## Band M

### Session totals

| setting | sessions | turns right | accuracy (turn pairs) | cost | time | requests | summed input | cache writes | cache reads | context after the last turn |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 1 | 6/6 | - | $0.0164 | 33.8s | 8.0 | 446,046 | 59,756 | 386,274 | 59,758 |
| fold | 1 | 6/6 (native 6/6) | +0% [-39%, +39%], 0/0, p 1.00 | -3% ($-0.0006) | -2.5 [-2.5, -2.5]s | +3.0 [+3.0, +3.0] | +88,108 [+88,108, +88,108] | -9,493 [-9,493, -9,493] | +97,595 [+97,595, +97,595] | -9,493 |
| schema | 1 | 6/6 (native 6/6) | +0% [-39%, +39%], 0/0, p 1.00 | +4% ($+0.0006) | +2.7 [+2.7, +2.7]s | +6.0 [+6.0, +6.0] | +218,760 [+218,760, +218,760] | -10,774 [-10,774, -10,774] | +229,522 [+229,522, +229,522] | -10,774 |

### Turn by turn

| setting | turn 1 (count) | turn 2 (enumerate) | turn 3 (lookup) | turn 4 (lookup) | turn 5 (lookup) | turn 6 (lookup) |
|---|---|---|---|---|---|---|
| native: context, right | 58,434, 1/1 | 58,915, 1/1 | 59,236, 1/1 | 59,440, 1/1 | 59,596, 1/1 | 59,758, 1/1 |
| fold: context, cost, right | -10,538, -16%, 1/1 | -10,498, -8%, 1/1 | -10,051, +79%, 1/1 | -9,771, +79%, 1/1 | -9,459, +81%, 1/1 | -9,493, -9%, 1/1 |
| schema: context, cost, right | -11,624, -14%, 1/1 | -11,522, +60%, 1/1 | -11,347, +64%, 1/1 | -11,186, +72%, 1/1 | -10,975, +74%, 1/1 | -10,774, +75%, 1/1 |

### By format

| format | setting | sessions | turns right (native) | cost | time | requests | context after the last turn (native, change) | read the raw (native) |
|---|---|---|---|---|---|---|---|---|
| json | fold | 1 | 6/6 (6/6) | -3% | -2.5s | +3.0 | 59,758, -9,493 | 1/1 (0/1) |
| json | schema | 1 | 6/6 (6/6) | +4% | +2.7s | +6.0 | 59,758, -10,774 | 1/1 (0/1) |

## Band L

### Session totals

| setting | sessions | turns right | accuracy (turn pairs) | cost | time | requests | summed input | cache writes | cache reads | context after the last turn |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 1 | 6/6 | - | $0.0191 | 40.4s | 15.0 | 738,569 | 51,940 | 686,599 | 51,942 |
| fold | 1 | 6/6 (native 6/6) | +0% [-39%, +39%], 0/0, p 1.00 | -1% ($-0.0001) | -2.2 [-2.2, -2.2]s | +0.0 [+0.0, +0.0] | +15,000 [+15,000, +15,000] | +600 [+600, +600] | +14,400 [+14,400, +14,400] | +600 |

### Turn by turn

| setting | turn 1 (count) | turn 2 (enumerate) | turn 3 (lookup) | turn 4 (lookup) | turn 5 (lookup) | turn 6 (lookup) |
|---|---|---|---|---|---|---|
| native: context, right | 49,064, 1/1 | 49,745, 1/1 | 50,436, 1/1 | 50,940, 1/1 | 51,441, 1/1 | 51,942, 1/1 |
| fold: context, cost, right | +838, -5%, 1/1 | +884, +73%, 1/1 | +697, -2%, 1/1 | +666, +0%, 1/1 | +633, +0%, 1/1 | +600, +0%, 1/1 |

### By format

| format | setting | sessions | turns right (native) | cost | time | requests | context after the last turn (native, change) | read the raw (native) |
|---|---|---|---|---|---|---|---|---|
| figma | fold | 1 | 6/6 (6/6) | -1% | -2.2s | +0.0 | 51,942, +600 | 1/1 (1/1) |

Session totals: turns right, and the accuracy change over turn pairs with its 95% interval (Newcombe) and the pairs won and lost (turns of one session are not independent: read it as indicative); cost as the mean change per session against native's mean; time, requests, summed input (every input token every request carried, cached or not), cache writes and reads as mean changes per session with bootstrap intervals; the context after the last turn as the median change, which every later request in the session would carry. Turn by turn: native's median context after each turn and its turns right; each setting's median change in that context, its change in that turn's cost (summed over sessions), and its turns right.

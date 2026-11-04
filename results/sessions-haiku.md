# Sessions haiku: claude-haiku-5-5, follow-up questions on one tool result

144 sessions, $1.77; 0 with a failed turn, left out whole. Each session asks its turns in one Claude Code process; each setting is paired against native by conversation and repetition.

## Band M

### Session totals

| setting | sessions | turns right | accuracy (turn pairs) | cost | time | requests | summed input | cache writes | cache reads | context after the last turn |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 32 | 192/192 | - | $0.0113 | 27.5s | 8.0 | 447,870 | 30,594 | 417,259 | 60,078 |
| fold | 32 | 192/192 (native 192/192) | +0% [-2%, +2%], 0/0, p 1.00 | +10% ($+0.0012) | +9.3 [+7.3, +11.3]s | +5.4 [+5.1, +5.8] | +227,236 [+210,594, +244,588] | -7,667 [-8,470, -6,618] | +234,892 [+218,111, +252,185] | -7,977 |
| schema | 8 | 48/48 (native 48/48) | +0% [-7%, +7%], 0/0, p 1.00 | +1% ($+0.0002) | +2.4 [-5.1, +10.4]s | +4.5 [+2.9, +5.8] | +160,414 [+102,349, +206,203] | -8,273 [-11,180, -4,201] | +168,677 [+106,657, +217,327] | -10,746 |

### Turn by turn

| setting | turn 1 (count) | turn 2 (enumerate) | turn 3 (lookup) | turn 4 (lookup) | turn 5 (lookup) | turn 6 (lookup) |
|---|---|---|---|---|---|---|
| native: context, right | 58,074, 32/32 | 58,923, 32/32 | 59,594, 32/32 | 59,758, 32/32 | 59,916, 32/32 | 60,078, 32/32 |
| fold: context, cost, right | -8,492, -12%, 32/32 | -8,714, +26%, 32/32 | -8,784, +35%, 32/32 | -8,458, +69%, 32/32 | -8,216, +77%, 32/32 | -7,977, +75%, 32/32 |
| schema: context, cost, right | -12,184, -34%, 8/8 | -11,594, +118%, 8/8 | -11,356, +50%, 8/8 | -11,152, +55%, 8/8 | -10,956, +56%, 8/8 | -10,746, +59%, 8/8 |

### By format

| format | setting | sessions | turns right (native) | cost | time | requests | context after the last turn (native, change) | read the raw (native) |
|---|---|---|---|---|---|---|---|---|
| a11y | fold | 8 | 48/48 (48/48) | +13% | +12.3s | +5.2 | 58,208, -5,691 | 8/8 (0/8) |
| figma | fold | 8 | 48/48 (48/48) | +18% | +6.6s | +5.8 | 59,875, -6,438 | 8/8 (0/8) |
| json | fold | 8 | 48/48 (48/48) | +4% | +9.9s | +5.4 | 60,051, -9,624 | 8/8 (0/8) |
| json | schema | 8 | 48/48 (48/48) | +1% | +2.4s | +4.5 | 60,051, -10,746 | 8/8 (0/8) |
| log | fold | 8 | 48/48 (48/48) | +6% | +8.3s | +5.4 | 61,818, -9,620 | 8/8 (0/8) |

## Band L

### Session totals

| setting | sessions | turns right | accuracy (turn pairs) | cost | time | requests | summed input | cache writes | cache reads | context after the last turn |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 32 | 192/192 | - | $0.0131 | 39.3s | 14.8 | 730,304 | 22,252 | 708,023 | 50,874 |
| fold | 32 | 192/192 (native 192/192) | +0% [-2%, +2%], 0/0, p 1.00 | -2% ($-0.0002) | +0.3 [-3.4, +4.0]s | -0.4 [-0.8, +0.0] | -11,616 [-33,978, +11,695] | +536 [-353, +1,391] | -12,152 [-34,273, +10,829] | +738 |
| schema | 8 | 48/48 (native 48/48) | +0% [-7%, +7%], 0/0, p 1.00 | -8% ($-0.0009) | -3.3 [-8.0, +1.2]s | -0.5 [-0.9, -0.1] | -34,358 [-52,140, -16,864] | -1,370 [-1,665, -1,020] | -32,988 [-50,966, -15,365] | -1,529 |

### Turn by turn

| setting | turn 1 (count) | turn 2 (enumerate) | turn 3 (lookup) | turn 4 (lookup) | turn 5 (lookup) | turn 6 (lookup) |
|---|---|---|---|---|---|---|
| native: context, right | 48,575, 32/32 | 48,936, 32/32 | 49,627, 32/32 | 50,042, 32/32 | 50,458, 32/32 | 50,874, 32/32 |
| fold: context, cost, right | +770, -8%, 32/32 | +1,094, +36%, 32/32 | +978, -4%, 32/32 | +894, +3%, 32/32 | +826, -0%, 32/32 | +738, -0%, 32/32 |
| schema: context, cost, right | -1,284, -20%, 8/8 | -1,024, +75%, 8/8 | -1,193, +0%, 8/8 | -1,311, -5%, 8/8 | -1,422, -5%, 8/8 | -1,529, -6%, 8/8 |

### By format

| format | setting | sessions | turns right (native) | cost | time | requests | context after the last turn (native, change) | read the raw (native) |
|---|---|---|---|---|---|---|---|---|
| a11y | fold | 8 | 48/48 (48/48) | +2% | +4.4s | -0.4 | 51,040, +1,596 | 8/8 (8/8) |
| figma | fold | 8 | 48/48 (48/48) | -6% | -2.0s | -0.2 | 53,948, -955 | 8/8 (8/8) |
| json | fold | 8 | 48/48 (48/48) | -2% | -0.9s | -0.2 | 50,642, +97 | 8/8 (8/8) |
| json | schema | 8 | 48/48 (48/48) | -8% | -3.3s | -0.5 | 50,642, -1,529 | 7/8 (8/8) |
| log | fold | 8 | 48/48 (48/48) | -0% | -0.2s | -0.9 | 50,688, +1,417 | 8/8 (8/8) |

Session totals: turns right, and the accuracy change over turn pairs with its 95% interval (Newcombe) and the pairs won and lost (turns of one session are not independent: read it as indicative); cost as the mean change per session against native's mean; time, requests, summed input (every input token every request carried, cached or not), cache writes and reads as mean changes per session with bootstrap intervals; the context after the last turn as the median change, which every later request in the session would carry. Turn by turn: native's median context after each turn and its turns right; each setting's median change in that context, its change in that turn's cost (summed over sessions), and its turns right.

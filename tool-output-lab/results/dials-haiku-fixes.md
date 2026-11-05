# Dials haiku-fixes: claude-haiku-5-5, the same tasks native and under each setting

## Band M (median input 6,480 tokens)

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 40 | - | 0/40 | 100% | 57,988 | 148,940 | 28,758 | 120,176 | - | $0.0073 | 10.3s |
| fixed | 40 | 40/40 | 23/40 | +0% [-9%, +9%], 0/0 | -8,367 [-9,986, -6,637] | +32,593 [+19,262, +48,223] | -8,400 [-10,005, -6,685] | +40,992 [+28,002, +55,412] | -10,282 ($-0.00010) | -15% ($-0.0011) | +2.6 [+1.6, +3.8]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band L (median input 35,289 tokens)

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 40 | - | 40/40 | 80% | 52,377 | 363,415 | 25,842 | 337,559 | - | $0.0099 | 26.0s |
| fixed | 40 | 40/40 | 19/40 | +20% [+7%, +35%], 8/0 | -6,168 [-9,471, -2,993] | -175,463 [-202,756, -147,271] | -6,168 [-9,471, -2,993] | -169,289 [-196,500, -141,859] | -3,836 ($-0.00004) | -38% ($-0.0038) | -12.4 [-14.4, -10.5]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 80 | - | 40/80 | 90% | 57,102 | 256,177 | 27,300 | 228,867 | - | $0.0086 | 18.2s |
| fixed | 80 | 80/80 | 42/80 | +10% [+3%, +19%], 8/0 | -7,267 [-9,149, -5,367] | -71,435 [-100,955, -43,318] | -7,284 [-9,165, -5,378] | -64,149 [-93,783, -36,313] | -7,770 ($-0.00008) | -29% ($-0.0025) | -4.9 [-7.0, -2.9]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Only the pairs where the envelope acted

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 80 | - | 40/80 | 90% | 57,102 | 256,177 | 27,300 | 228,867 | - | $0.0086 | 18.2s |
| fixed | 80 | 80/80 | 42/80 | +10% [+3%, +19%], 8/0 | -7,267 [-9,149, -5,367] | -71,435 [-100,955, -43,318] | -7,284 [-9,165, -5,378] | -64,149 [-93,783, -36,313] | -7,770 ($-0.00008) | -29% ($-0.0025) | -4.9 [-7.0, -2.9]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

160 runs, $1.18; 160 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | M | fixed | 2/2 [34%, 100%] | $0.0080 | 57501 | 2.0 | 2/2 | 0/2 |
| a11y | absent | M | native | 2/2 [34%, 100%] | $0.0076 | 56573 | 1.0 | 0/2 | 0/2 |
| a11y | absent | L | fixed | 2/2 [34%, 100%] | $0.0143 | 88148 | 2.5 | 2/2 | 0/2 |
| a11y | absent | L | native | 2/2 [34%, 100%] | $0.0142 | 73962 | 7.0 | 2/2 | 0/2 |
| a11y | spot | M | fixed | 8/8 [68%, 100%] | $0.0048 | 46305 | 1.0 | 2/8 | 0/8 |
| a11y | spot | M | native | 8/8 [68%, 100%] | $0.0068 | 56567 | 1.0 | 0/8 | 0/8 |
| a11y | spot | L | fixed | 8/8 [68%, 100%] | $0.0048 | 46291 | 1.0 | 2/8 | 0/8 |
| a11y | spot | L | native | 4/8 [22%, 78%] | $0.0117 | 58294 | 7.0 | 8/8 | 0/8 |
| figma | absent | M | fixed | 2/2 [34%, 100%] | $0.0093 | 57708 | 4.0 | 2/2 | 0/2 |
| figma | absent | M | native | 2/2 [34%, 100%] | $0.0073 | 57635 | 1.0 | 0/2 | 0/2 |
| figma | absent | L | fixed | 2/2 [34%, 100%] | $0.0092 | 52256 | 5.0 | 2/2 | 0/2 |
| figma | absent | L | native | 2/2 [34%, 100%] | $0.0111 | 54391 | 7.0 | 2/2 | 0/2 |
| figma | spot | M | fixed | 8/8 [68%, 100%] | $0.0079 | 58664 | 2.0 | 7/8 | 0/8 |
| figma | spot | M | native | 8/8 [68%, 100%] | $0.0071 | 57632 | 1.0 | 0/8 | 0/8 |
| figma | spot | L | fixed | 8/8 [68%, 100%] | $0.0067 | 48362 | 3.0 | 7/8 | 0/8 |
| figma | spot | L | native | 4/8 [22%, 78%] | $0.0101 | 52159 | 6.5 | 8/8 | 0/8 |
| json | absent | M | fixed | 2/2 [34%, 100%] | $0.0048 | 46229 | 1.0 | 0/2 | 0/2 |
| json | absent | M | native | 2/2 [34%, 100%] | $0.0072 | 58337 | 1.0 | 0/2 | 0/2 |
| json | absent | L | fixed | 2/2 [34%, 100%] | $0.0048 | 46204 | 1.0 | 0/2 | 0/2 |
| json | absent | L | native | 2/2 [34%, 100%] | $0.0073 | 48590 | 4.0 | 2/2 | 0/2 |
| json | spot | M | fixed | 8/8 [68%, 100%] | $0.0050 | 46296 | 1.0 | 1/8 | 0/8 |
| json | spot | M | native | 8/8 [68%, 100%] | $0.0072 | 58344 | 1.0 | 0/8 | 0/8 |
| json | spot | L | fixed | 8/8 [68%, 100%] | $0.0047 | 46264 | 1.0 | 0/8 | 0/8 |
| json | spot | L | native | 8/8 [68%, 100%] | $0.0071 | 48395 | 4.0 | 8/8 | 0/8 |
| log | absent | M | fixed | 2/2 [34%, 100%] | $0.0078 | 54634 | 3.0 | 2/2 | 0/2 |
| log | absent | M | native | 2/2 [34%, 100%] | $0.0076 | 60289 | 1.0 | 0/2 | 0/2 |
| log | absent | L | fixed | 2/2 [34%, 100%] | $0.0071 | 48582 | 4.5 | 2/2 | 0/2 |
| log | absent | L | native | 2/2 [34%, 100%] | $0.0097 | 52859 | 8.0 | 2/2 | 0/2 |
| log | spot | M | fixed | 8/8 [68%, 100%] | $0.0056 | 47255 | 2.0 | 7/8 | 0/8 |
| log | spot | M | native | 8/8 [68%, 100%] | $0.0076 | 60309 | 1.0 | 0/8 | 0/8 |
| log | spot | L | fixed | 8/8 [68%, 100%] | $0.0052 | 46499 | 1.5 | 4/8 | 0/8 |
| log | spot | L | native | 8/8 [68%, 100%] | $0.0093 | 52683 | 7.5 | 8/8 | 0/8 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | M | fixed | 10 | +0% [-28%, +28%] | 0/0, p 1.00 | $-0.0016 [-0.0020, -0.0004] | -9801 [-10275, -4234] | +13345 [-10274, +41988] | +0.8s [-0.1, +3.0] | undecided (indicative: under 30 pairs) |
| a11y | L | fixed | 10 | +40% [+4%, +69%] | 4/0, p 0.12 | $-0.0063 [-0.0081, -0.0041] | -11014 [-26773, -6420] | -222924 [-306516, -143716] | -15.6s [-23.6, -12.1] | passes (indicative: under 30 pairs) |
| figma | M | fixed | 10 | +0% [-28%, +28%] | 0/0, p 1.00 | $+0.0008 [+0.0001, +0.0015] | +992 [-8473, +1192] | +66267 [+47361, +113254] | +4.3s [+2.7, +7.8] | undecided (indicative: under 30 pairs) |
| figma | L | fixed | 10 | +40% [+4%, +69%] | 4/0, p 0.12 | $-0.0035 [-0.0043, -0.0014] | -3984 [-5799, -988] | -164630 [-210644, -73878] | -11.8s [-16.2, -4.7] | passes (indicative: under 30 pairs) |
| json | M | fixed | 10 | +0% [-28%, +28%] | 0/0, p 1.00 | $-0.0024 [-0.0024, -0.0024] | -12060 [-12107, -12024] | -12067 [-12102, -12003] | +0.3s [-1.0, +1.3] | undecided (indicative: under 30 pairs) |
| json | L | fixed | 10 | +0% [-28%, +28%] | 0/0, p 1.00 | $-0.0024 [-0.0025, -0.0021] | -2226 [-2504, -2065] | -143174 [-143480, -119870] | -8.6s [-10.0, -8.2] | undecided (indicative: under 30 pairs) |
| log | M | fixed | 10 | +0% [-28%, +28%] | 0/0, p 1.00 | $-0.0020 [-0.0021, -0.0012] | -13000 [-13364, -12590] | +33296 [+32910, +40326] | +2.3s [+0.8, +4.0] | undecided (indicative: under 30 pairs) |
| log | L | fixed | 10 | +0% [-28%, +28%] | 0/0, p 1.00 | $-0.0036 [-0.0065, -0.0025] | -5508 [-10235, -3579] | -183446 [-283543, -102996] | -14.1s [-18.0, -7.5] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | fixed | 40 | +0% [-9%, +9%] | 0/0, p 1.00 | $-0.0020 [-0.0020, -0.0010] | -10282 [-12060, -9304] | +33373 [-10238, +37595] | +2.0s [+1.0, +3.1] | undecided |
| L | fixed | 40 | +20% [+7%, +35%] | 8/0, p 0.01 | $-0.0030 [-0.0045, -0.0025] | -3836 [-5891, -2556] | -149764 [-209548, -143216] | -11.3s [-14.9, -9.1] | passes |

## When the envelope acted: the pairs whose folded session folded the task's large output

| band | condition | acted | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| M | fixed | 40/40 (saw it 40) | 40 | +0% [-9%, +9%] | 0/0, p 1.00 | $-0.0020 [-0.0020, -0.0010] | -10282 [-12060, -9304] | +33373 [-10238, +37595] | +2.0s [+1.0, +3.1] | undecided |
| L | fixed | 40/40 (saw it 40) | 40 | +20% [+7%, +35%] | 8/0, p 0.01 | $-0.0030 [-0.0045, -0.0025] | -3836 [-5891, -2556] | -149764 [-209548, -143216] | -11.3s [-14.9, -9.1] | passes |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, 2026-11-03); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | fixed | 40 | +0.9 [+0.6, +1.2] | -8,400 [-10,005, -6,685] | +40,992 [+28,002, +55,412] | +1.8 [+1.2, +2.4] | 40/40, 40/40 | -10,282 tokens, $-0.00010 |
| L | fixed | 40 | -3.3 [-3.8, -2.8] | -6,168 [-9,471, -2,993] | -169,289 [-196,500, -141,859] | -6.6 [-7.7, -5.5] | 40/40, 40/40 | -3,836 tokens, $-0.00004 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

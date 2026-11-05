# Dials haiku-banner: claude-haiku-5-5, the same tasks native and under each setting

## Band M (median input 6,502 tokens)

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | - | 0/52 | 98% | 58,038 | 148,933 | 28,891 | 120,036 | - | $0.0073 | 9.5s |
| schema | 52 | 52/52 | 34/52 | +2% [-5%, +10%], 1/0 | -9,212 [-10,478, -7,764] | +27,724 [+18,608, +37,834] | -9,321 [-10,583, -7,861] | +37,044 [+28,631, +46,907] | -10,776 ($-0.00011) | -20% ($-0.0015) | +1.8 [+1.1, +2.5]s |
| exact | 52 | 52/52 | 28/52 | +2% [-5%, +10%], 1/0 | -9,185 [-10,474, -7,671] | +35,142 [+17,313, +60,081] | -9,381 [-10,662, -7,836] | +44,521 [+27,183, +68,624] | -10,853 ($-0.00011) | -18% ($-0.0013) | +3.0 [+1.6, +4.9]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band L (median input 35,333 tokens)

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | - | 52/52 | 94% | 48,738 | 299,277 | 21,411 | 277,854 | - | $0.0080 | 20.2s |
| schema | 52 | 52/52 | 36/52 | +6% [-2%, +16%], 3/0 | -3,703 [-5,578, -2,271] | -112,642 [-143,307, -86,116] | -3,764 [-5,642, -2,351] | -108,874 [-138,861, -82,627] | -1,578 ($-0.00002) | -30% ($-0.0024) | -7.8 [-11.6, -4.6]s |
| exact | 52 | 52/52 | 23/52 | +6% [-2%, +16%], 3/0 | -3,131 [-5,297, -1,060] | -128,351 [-161,346, -98,410] | -3,228 [-5,390, -1,149] | -125,118 [-158,178, -95,014] | -1,812 ($-0.00002) | -31% ($-0.0025) | -8.9 [-12.6, -5.9]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 104 | - | 52/104 | 96% | 56,578 | 224,105 | 25,151 | 198,945 | - | $0.0077 | 14.9s |
| schema | 104 | 104/104 | 70/104 | +4% [-0%, +9%], 4/0 | -6,458 [-7,729, -5,277] | -42,459 [-63,549, -22,224] | -6,542 [-7,813, -5,349] | -35,915 [-56,911, -15,566] | -6,525 ($-0.00007) | -25% ($-0.0019) | -3.0 [-5.1, -1.1]s |
| exact | 104 | 104/104 | 51/104 | +4% [-0%, +9%], 4/0 | -6,158 [-7,520, -4,779] | -46,604 [-72,265, -21,120] | -6,304 [-7,672, -4,934] | -40,298 [-66,084, -14,776] | -5,715 ($-0.00006) | -25% ($-0.0019) | -2.9 [-5.2, -0.8]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Only the pairs where the envelope acted

| setting | pairs | acted | re-read | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 104 | - | 52/104 | 96% | 56,578 | 224,105 | 25,151 | 198,945 | - | $0.0077 | 14.9s |
| schema | 104 | 104/104 | 70/104 | +4% [-0%, +9%], 4/0 | -6,458 [-7,729, -5,277] | -42,459 [-63,549, -22,224] | -6,542 [-7,813, -5,349] | -35,915 [-56,911, -15,566] | -6,525 ($-0.00007) | -25% ($-0.0019) | -3.0 [-5.1, -1.1]s |
| exact | 104 | 104/104 | 51/104 | +4% [-0%, +9%], 4/0 | -6,158 [-7,520, -4,779] | -46,604 [-72,265, -21,120] | -6,304 [-7,672, -4,934] | -40,298 [-66,084, -14,776] | -5,715 ($-0.00006) | -25% ($-0.0019) | -2.9 [-5.2, -0.8]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Re-read: the runs that opened the saved full output. Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

312 runs, $2.00; 312 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | M | exact | 1/1 [21%, 100%] | $0.0085 | 58709 | 2 | 1/1 | 0/1 |
| a11y | absent | M | native | 1/1 [21%, 100%] | $0.0069 | 56584 | 1 | 0/1 | 0/1 |
| a11y | absent | M | schema | 1/1 [21%, 100%] | $0.0085 | 58648 | 2 | 1/1 | 0/1 |
| a11y | absent | L | exact | 1/1 [21%, 100%] | $0.0140 | 87943 | 2 | 1/1 | 0/1 |
| a11y | absent | L | native | 1/1 [21%, 100%] | $0.0154 | 60784 | 18 | 1/1 | 0/1 |
| a11y | absent | L | schema | 1/1 [21%, 100%] | $0.0074 | 48976 | 4 | 1/1 | 0/1 |
| a11y | count | M | exact | 4/4 [51%, 100%] | $0.0049 | 47045 | 1.0 | 0/4 | 0/4 |
| a11y | count | M | native | 4/4 [51%, 100%] | $0.0070 | 56598 | 1.0 | 0/4 | 0/4 |
| a11y | count | M | schema | 4/4 [51%, 100%] | $0.0056 | 47325 | 2.0 | 3/4 | 0/4 |
| a11y | count | L | exact | 4/4 [51%, 100%] | $0.0049 | 47037 | 1.0 | 0/4 | 0/4 |
| a11y | count | L | native | 4/4 [51%, 100%] | $0.0065 | 48443 | 4.0 | 4/4 | 0/4 |
| a11y | count | L | schema | 4/4 [51%, 100%] | $0.0057 | 47464 | 2.0 | 4/4 | 0/4 |
| a11y | enumerate | M | exact | 2/2 [34%, 100%] | $0.0055 | 47367 | 1.5 | 1/2 | 0/2 |
| a11y | enumerate | M | native | 2/2 [34%, 100%] | $0.0069 | 56627 | 1.0 | 0/2 | 0/2 |
| a11y | enumerate | M | schema | 2/2 [34%, 100%] | $0.0054 | 47202 | 1.5 | 1/2 | 0/2 |
| a11y | enumerate | L | exact | 2/2 [34%, 100%] | $0.0050 | 46932 | 1.0 | 0/2 | 0/2 |
| a11y | enumerate | L | native | 2/2 [34%, 100%] | $0.0076 | 50746 | 4.5 | 2/2 | 0/2 |
| a11y | enumerate | L | schema | 2/2 [34%, 100%] | $0.0050 | 46900 | 1.0 | 0/2 | 0/2 |
| a11y | lookup | M | exact | 2/2 [34%, 100%] | $0.0054 | 46985 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | M | native | 2/2 [34%, 100%] | $0.0069 | 56570 | 1.0 | 0/2 | 0/2 |
| a11y | lookup | M | schema | 2/2 [34%, 100%] | $0.0054 | 46756 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | exact | 2/2 [34%, 100%] | $0.0054 | 46988 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | native | 2/2 [34%, 100%] | $0.0067 | 51844 | 3.0 | 2/2 | 0/2 |
| a11y | lookup | L | schema | 2/2 [34%, 100%] | $0.0055 | 47018 | 2.0 | 2/2 | 0/2 |
| a11y | spot | M | exact | 4/4 [51%, 100%] | $0.0053 | 46869 | 1.5 | 2/4 | 0/4 |
| a11y | spot | M | native | 4/4 [51%, 100%] | $0.0069 | 56557 | 1.0 | 0/4 | 0/4 |
| a11y | spot | M | schema | 4/4 [51%, 100%] | $0.0053 | 47073 | 1.5 | 2/4 | 0/4 |
| a11y | spot | L | exact | 4/4 [51%, 100%] | $0.0048 | 46292 | 1.0 | 1/4 | 0/4 |
| a11y | spot | L | native | 3/4 [30%, 95%] | $0.0112 | 55874 | 7.0 | 4/4 | 0/4 |
| a11y | spot | L | schema | 4/4 [51%, 100%] | $0.0052 | 46603 | 1.5 | 2/4 | 0/4 |
| figma | absent | M | exact | 1/1 [21%, 100%] | $0.0159 | 64537 | 10 | 1/1 | 0/1 |
| figma | absent | M | native | 0/1 [0%, 79%] | $0.0078 | 57621 | 1 | 0/1 | 0/1 |
| figma | absent | M | schema | 1/1 [21%, 100%] | $0.0081 | 58346 | 2 | 1/1 | 0/1 |
| figma | absent | L | exact | 1/1 [21%, 100%] | $0.0078 | 50118 | 4 | 1/1 | 0/1 |
| figma | absent | L | native | 1/1 [21%, 100%] | $0.0082 | 50716 | 4 | 1/1 | 0/1 |
| figma | absent | L | schema | 1/1 [21%, 100%] | $0.0077 | 49487 | 4 | 1/1 | 0/1 |
| figma | count | M | exact | 4/4 [51%, 100%] | $0.0066 | 48104 | 2.5 | 3/4 | 0/4 |
| figma | count | M | native | 4/4 [51%, 100%] | $0.0075 | 57690 | 1.0 | 0/4 | 0/4 |
| figma | count | M | schema | 4/4 [51%, 100%] | $0.0065 | 47999 | 3.0 | 4/4 | 0/4 |
| figma | count | L | exact | 4/4 [51%, 100%] | $0.0066 | 48228 | 3.0 | 3/4 | 0/4 |
| figma | count | L | native | 4/4 [51%, 100%] | $0.0071 | 48736 | 3.5 | 4/4 | 0/4 |
| figma | count | L | schema | 4/4 [51%, 100%] | $0.0066 | 48499 | 3.0 | 4/4 | 0/4 |
| figma | enumerate | M | exact | 2/2 [34%, 100%] | $0.0074 | 53569 | 2.5 | 2/2 | 0/2 |
| figma | enumerate | M | native | 2/2 [34%, 100%] | $0.0073 | 57709 | 1.0 | 0/2 | 0/2 |
| figma | enumerate | M | schema | 2/2 [34%, 100%] | $0.0071 | 53183 | 2.0 | 1/2 | 0/2 |
| figma | enumerate | L | exact | 2/2 [34%, 100%] | $0.0067 | 48484 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | L | native | 2/2 [34%, 100%] | $0.0067 | 49533 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | L | schema | 2/2 [34%, 100%] | $0.0062 | 47934 | 2.5 | 2/2 | 0/2 |
| figma | lookup | M | exact | 2/2 [34%, 100%] | $0.0063 | 46867 | 3.5 | 2/2 | 0/2 |
| figma | lookup | M | native | 2/2 [34%, 100%] | $0.0071 | 57606 | 1.0 | 0/2 | 0/2 |
| figma | lookup | M | schema | 2/2 [34%, 100%] | $0.0070 | 52669 | 2.5 | 2/2 | 0/2 |
| figma | lookup | L | exact | 2/2 [34%, 100%] | $0.0063 | 46921 | 3.5 | 2/2 | 0/2 |
| figma | lookup | L | native | 2/2 [34%, 100%] | $0.0062 | 46996 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | schema | 2/2 [34%, 100%] | $0.0061 | 46854 | 3.0 | 2/2 | 0/2 |
| figma | spot | M | exact | 4/4 [51%, 100%] | $0.0080 | 58771 | 2.0 | 4/4 | 0/4 |
| figma | spot | M | native | 4/4 [51%, 100%] | $0.0071 | 57629 | 1.0 | 0/4 | 0/4 |
| figma | spot | M | schema | 4/4 [51%, 100%] | $0.0080 | 58706 | 2.0 | 4/4 | 0/4 |
| figma | spot | L | exact | 4/4 [51%, 100%] | $0.0059 | 47965 | 2.0 | 4/4 | 0/4 |
| figma | spot | L | native | 2/4 [15%, 85%] | $0.0117 | 55260 | 8.5 | 4/4 | 0/4 |
| figma | spot | L | schema | 4/4 [51%, 100%] | $0.0067 | 48620 | 3.0 | 4/4 | 0/4 |
| json | absent | M | exact | 1/1 [21%, 100%] | $0.0048 | 46229 | 1 | 0/1 | 0/1 |
| json | absent | M | native | 1/1 [21%, 100%] | $0.0072 | 58332 | 1 | 0/1 | 0/1 |
| json | absent | M | schema | 1/1 [21%, 100%] | $0.0048 | 46196 | 1 | 0/1 | 0/1 |
| json | absent | L | exact | 1/1 [21%, 100%] | $0.0048 | 46194 | 1 | 0/1 | 0/1 |
| json | absent | L | native | 1/1 [21%, 100%] | $0.0074 | 48857 | 4 | 1/1 | 0/1 |
| json | absent | L | schema | 1/1 [21%, 100%] | $0.0055 | 46796 | 2 | 1/1 | 0/1 |
| json | count | M | exact | 4/4 [51%, 100%] | $0.0047 | 46294 | 1.0 | 0/4 | 0/4 |
| json | count | M | native | 4/4 [51%, 100%] | $0.0076 | 58452 | 1.0 | 0/4 | 0/4 |
| json | count | M | schema | 4/4 [51%, 100%] | $0.0049 | 46442 | 1.0 | 1/4 | 0/4 |
| json | count | L | exact | 4/4 [51%, 100%] | $0.0048 | 46687 | 1.0 | 0/4 | 0/4 |
| json | count | L | native | 4/4 [51%, 100%] | $0.0065 | 48267 | 3.0 | 4/4 | 0/4 |
| json | count | L | schema | 4/4 [51%, 100%] | $0.0052 | 46942 | 1.5 | 2/4 | 0/4 |
| json | enumerate | M | exact | 2/2 [34%, 100%] | $0.0051 | 46548 | 1.5 | 1/2 | 0/2 |
| json | enumerate | M | native | 2/2 [34%, 100%] | $0.0074 | 58452 | 1.0 | 0/2 | 0/2 |
| json | enumerate | M | schema | 2/2 [34%, 100%] | $0.0051 | 46522 | 1.5 | 1/2 | 0/2 |
| json | enumerate | L | exact | 2/2 [34%, 100%] | $0.0049 | 46633 | 1.0 | 0/2 | 0/2 |
| json | enumerate | L | native | 2/2 [34%, 100%] | $0.0065 | 48210 | 3.0 | 2/2 | 0/2 |
| json | enumerate | L | schema | 2/2 [34%, 100%] | $0.0049 | 46608 | 1.0 | 0/2 | 0/2 |
| json | lookup | M | exact | 2/2 [34%, 100%] | $0.0054 | 46529 | 2.0 | 2/2 | 0/2 |
| json | lookup | M | native | 2/2 [34%, 100%] | $0.0072 | 58318 | 1.0 | 0/2 | 0/2 |
| json | lookup | M | schema | 2/2 [34%, 100%] | $0.0053 | 46482 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | exact | 2/2 [34%, 100%] | $0.0053 | 46499 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | native | 2/2 [34%, 100%] | $0.0061 | 46903 | 3.0 | 2/2 | 0/2 |
| json | lookup | L | schema | 2/2 [34%, 100%] | $0.0053 | 46450 | 2.0 | 2/2 | 0/2 |
| json | spot | M | exact | 4/4 [51%, 100%] | $0.0052 | 46302 | 1.0 | 1/4 | 0/4 |
| json | spot | M | native | 4/4 [51%, 100%] | $0.0074 | 58344 | 1.0 | 0/4 | 0/4 |
| json | spot | M | schema | 4/4 [51%, 100%] | $0.0052 | 46235 | 1.0 | 1/4 | 0/4 |
| json | spot | L | exact | 4/4 [51%, 100%] | $0.0047 | 46259 | 1.0 | 0/4 | 0/4 |
| json | spot | L | native | 4/4 [51%, 100%] | $0.0072 | 48573 | 4.0 | 4/4 | 0/4 |
| json | spot | L | schema | 4/4 [51%, 100%] | $0.0048 | 46229 | 1.0 | 1/4 | 0/4 |
| log | absent | M | exact | 1/1 [21%, 100%] | $0.0085 | 61786 | 2 | 1/1 | 0/1 |
| log | absent | M | native | 1/1 [21%, 100%] | $0.0076 | 60273 | 1 | 0/1 | 0/1 |
| log | absent | M | schema | 1/1 [21%, 100%] | $0.0084 | 61666 | 2 | 1/1 | 0/1 |
| log | absent | L | exact | 1/1 [21%, 100%] | $0.0066 | 47937 | 3 | 1/1 | 0/1 |
| log | absent | L | native | 1/1 [21%, 100%] | $0.0103 | 52473 | 7 | 1/1 | 0/1 |
| log | absent | L | schema | 1/1 [21%, 100%] | $0.0072 | 48242 | 4 | 1/1 | 0/1 |
| log | count | M | exact | 4/4 [51%, 100%] | $0.0049 | 46771 | 1.0 | 0/4 | 0/4 |
| log | count | M | native | 4/4 [51%, 100%] | $0.0077 | 60300 | 1.0 | 0/4 | 0/4 |
| log | count | M | schema | 4/4 [51%, 100%] | $0.0049 | 46732 | 1.0 | 1/4 | 0/4 |
| log | count | L | exact | 4/4 [51%, 100%] | $0.0049 | 46793 | 1.0 | 0/4 | 0/4 |
| log | count | L | native | 4/4 [51%, 100%] | $0.0063 | 47602 | 4.0 | 4/4 | 0/4 |
| log | count | L | schema | 4/4 [51%, 100%] | $0.0055 | 46937 | 2.0 | 3/4 | 0/4 |
| log | enumerate | M | exact | 2/2 [34%, 100%] | $0.0049 | 46649 | 1.0 | 0/2 | 0/2 |
| log | enumerate | M | native | 2/2 [34%, 100%] | $0.0078 | 60343 | 1.0 | 0/2 | 0/2 |
| log | enumerate | M | schema | 2/2 [34%, 100%] | $0.0050 | 46674 | 1.0 | 0/2 | 0/2 |
| log | enumerate | L | exact | 2/2 [34%, 100%] | $0.0049 | 46682 | 1.0 | 0/2 | 0/2 |
| log | enumerate | L | native | 2/2 [34%, 100%] | $0.0064 | 47462 | 3.0 | 2/2 | 0/2 |
| log | enumerate | L | schema | 2/2 [34%, 100%] | $0.0049 | 46638 | 1.0 | 0/2 | 0/2 |
| log | lookup | M | exact | 2/2 [34%, 100%] | $0.0054 | 46494 | 2.0 | 2/2 | 0/2 |
| log | lookup | M | native | 2/2 [34%, 100%] | $0.0077 | 60270 | 1.0 | 0/2 | 0/2 |
| log | lookup | M | schema | 2/2 [34%, 100%] | $0.0055 | 46471 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | exact | 2/2 [34%, 100%] | $0.0053 | 46460 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | native | 2/2 [34%, 100%] | $0.0055 | 46416 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | schema | 2/2 [34%, 100%] | $0.0048 | 46250 | 1.0 | 0/2 | 0/2 |
| log | spot | M | exact | 4/4 [51%, 100%] | $0.0056 | 47259 | 2.0 | 3/4 | 0/4 |
| log | spot | M | native | 4/4 [51%, 100%] | $0.0077 | 60307 | 1.0 | 0/4 | 0/4 |
| log | spot | M | schema | 4/4 [51%, 100%] | $0.0056 | 46988 | 2.0 | 4/4 | 0/4 |
| log | spot | L | exact | 4/4 [51%, 100%] | $0.0052 | 46703 | 1.5 | 2/4 | 0/4 |
| log | spot | L | native | 4/4 [51%, 100%] | $0.0114 | 55199 | 11.0 | 4/4 | 0/4 |
| log | spot | L | schema | 4/4 [51%, 100%] | $0.0056 | 47260 | 2.0 | 4/4 | 0/4 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | M | exact | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0017 [-0.0020, -0.0012] | -9367 [-9769, -9152] | -8685 [-9758, +37172] | +1.7s [+0.6, +3.8] | undecided (indicative: under 30 pairs) |
| a11y | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0015 [-0.0020, -0.0013] | -9465 [-9822, -8679] | +36892 [-9376, +37603] | +1.9s [+1.2, +3.6] | undecided (indicative: under 30 pairs) |
| a11y | L | exact | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0020 [-0.0057, -0.0014] | -4849 [-8227, -1426] | -143230 [-225369, -88081] | -5.7s [-19.5, -3.5] | undecided (indicative: under 30 pairs) |
| a11y | L | schema | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0023 [-0.0061, -0.0012] | -4912 [-8458, -1599] | -94827 [-225318, -41167] | -5.0s [-16.9, -0.6] | undecided (indicative: under 30 pairs) |
| figma | M | exact | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $+0.0005 [-0.0008, +0.0009] | -7639 [-10050, +1249] | +81683 [+47669, +85785] | +5.0s [+3.8, +6.3] | undecided (indicative: under 30 pairs) |
| figma | M | schema | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $+0.0002 [-0.0010, +0.0009] | +725 [-10047, +1036] | +48566 [+47227, +83903] | +2.4s [+1.8, +4.8] | undecided (indicative: under 30 pairs) |
| figma | L | exact | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $-0.0007 [-0.0022, -0.0003] | -655 [-3309, -179] | -47445 [-144591, -286] | -2.3s [-11.5, -0.4] | undecided (indicative: under 30 pairs) |
| figma | L | schema | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $-0.0005 [-0.0014, -0.0001] | -691 [-2439, -251] | -4776 [-95605, -413] | -3.9s [-12.1, +0.2] | undecided (indicative: under 30 pairs) |
| json | M | exact | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0024 [-0.0024, -0.0020] | -11996 [-12095, -11851] | -11992 [-12086, +34422] | +1.0s [-0.1, +1.5] | undecided (indicative: under 30 pairs) |
| json | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0024 [-0.0024, -0.0021] | -12005 [-12120, -11856] | -11996 [-12124, +34334] | +0.4s [-0.7, +1.3] | undecided (indicative: under 30 pairs) |
| json | L | exact | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0017 [-0.0024, -0.0016] | -1743 [-2288, -1535] | -94994 [-143498, -94611] | -7.0s [-8.9, -5.6] | undecided (indicative: under 30 pairs) |
| json | L | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0016 [-0.0019, -0.0016] | -1587 [-2061, -1452] | -94998 [-97081, -94610] | -5.2s [-8.4, -4.3] | undecided (indicative: under 30 pairs) |
| log | M | exact | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0028 [-0.0029, -0.0021] | -13529 [-13806, -13041] | -12944 [-13596, +33228] | +0.5s [-0.8, +2.2] | undecided (indicative: under 30 pairs) |
| log | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0022 [-0.0028, -0.0021] | -13571 [-13753, -13086] | +32409 [-13530, +33116] | +1.0s [-0.1, +2.1] | undecided (indicative: under 30 pairs) |
| log | L | exact | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0021 [-0.0037, -0.0008] | -1784 [-4562, -378] | -143197 [-202051, -46445] | -8.7s [-12.4, -3.3] | undecided (indicative: under 30 pairs) |
| log | L | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0015 [-0.0031, -0.0008] | -1543 [-4142, -458] | -96547 [-154322, -46549] | -6.5s [-10.4, -3.2] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | exact | 52 | +2% [-5%, +10%] | 1/0, p 1.00 | $-0.0020 [-0.0022, -0.0016] | -10853 [-11958, -9691] | +32832 [-10084, +35688] | +1.6s [+1.0, +2.6] | undecided |
| M | schema | 52 | +2% [-5%, +10%] | 1/0, p 1.00 | $-0.0020 [-0.0021, -0.0014] | -10776 [-12003, -9714] | +34335 [+32409, +36928] | +1.7s [+0.9, +2.0] | undecided |
| L | exact | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0017 [-0.0022, -0.0013] | -1812 [-2306, -1418] | -94830 [-143630, -93061] | -6.4s [-8.4, -4.8] | passes |
| L | schema | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0016 [-0.0019, -0.0012] | -1578 [-2268, -1162] | -94684 [-96830, -47566] | -5.1s [-7.4, -3.9] | passes |

## When the envelope acted: the pairs whose folded session folded the task's large output

| band | condition | acted | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| M | exact | 52/52 (saw it 52) | 52 | +2% [-5%, +10%] | 1/0, p 1.00 | $-0.0020 [-0.0022, -0.0016] | -10853 [-11958, -9691] | +32832 [-10084, +35688] | +1.6s [+1.0, +2.6] | undecided |
| M | schema | 52/52 (saw it 52) | 52 | +2% [-5%, +10%] | 1/0, p 1.00 | $-0.0020 [-0.0021, -0.0014] | -10776 [-12003, -9714] | +34335 [+32409, +36928] | +1.7s [+0.9, +2.0] | undecided |
| L | exact | 52/52 (saw it 52) | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0017 [-0.0022, -0.0013] | -1812 [-2306, -1418] | -94830 [-143630, -93061] | -6.4s [-8.4, -4.8] | passes |
| L | schema | 52/52 (saw it 52) | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0016 [-0.0019, -0.0012] | -1578 [-2268, -1162] | -94684 [-96830, -47566] | -5.1s [-7.4, -3.9] | passes |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, 2026-11-03); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | exact | 52 | +0.9 [+0.6, +1.3] | -9,381 [-10,662, -7,836] | +44,521 [+27,183, +68,624] | +1.8 [+1.2, +2.7] | 52/52, 52/52 | -10,853 tokens, $-0.00011 |
| M | schema | 52 | +0.8 [+0.6, +1.0] | -9,321 [-10,583, -7,861] | +37,044 [+28,631, +46,907] | +1.6 [+1.2, +2.0] | 52/52, 52/52 | -10,776 tokens, $-0.00011 |
| L | exact | 52 | -2.5 [-3.1, -2.0] | -3,228 [-5,390, -1,149] | -125,118 [-158,178, -95,014] | -5.0 [-6.3, -3.9] | 52/52, 52/52 | -1,812 tokens, $-0.00002 |
| L | schema | 52 | -2.2 [-2.7, -1.7] | -3,764 [-5,642, -2,351] | -108,874 [-138,861, -82,627] | -4.3 [-5.5, -3.3] | 52/52, 52/52 | -1,578 tokens, $-0.00002 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

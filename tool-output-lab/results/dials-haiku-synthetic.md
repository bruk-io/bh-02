# Dials haiku-synthetic: claude-haiku-5-5, the same tasks native and under each setting

## Band M (median input 6,502 tokens)

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | - | 100% | 58,064 | 148,944 | 28,830 | 120,108 | - | $0.0073 | 5.8s |
| sample | 52 | 52/52 | +0% [-7%, +7%], 0/0 | -9,522 [-10,552, -8,298] | +43,904 [+34,681, +54,679] | -9,729 [-10,774, -8,504] | +53,631 [+44,551, +63,848] | -9,899 ($-0.00010) | -18% ($-0.0013) | +2.1 [+1.6, +2.8]s |
| schema | 52 | 52/52 | +0% [-7%, +7%], 0/0 | -8,488 [-9,946, -6,717] | +34,500 [+24,936, +45,708] | -8,732 [-10,212, -6,944] | +43,230 [+34,599, +53,045] | -10,892 ($-0.00011) | -17% ($-0.0013) | +1.5 [+1.0, +2.0]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band L (median input 35,333 tokens)

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | - | 98% | 48,692 | 278,920 | 23,373 | 255,535 | - | $0.0081 | 13.2s |
| sample | 52 | 52/52 | +2% [-5%, +10%], 1/0 | -5,258 [-8,383, -2,538] | -83,338 [-109,718, -60,719] | -5,330 [-8,462, -2,628] | -78,005 [-103,534, -55,397] | -1,174 ($-0.00001) | -27% ($-0.0022) | -5.0 [-8.4, -2.8]s |
| schema | 52 | 52/52 | +2% [-5%, +10%], 1/0 | -4,888 [-7,693, -2,535] | -90,518 [-117,045, -66,272] | -4,984 [-7,785, -2,666] | -85,530 [-111,650, -62,228] | -1,615 ($-0.00002) | -28% ($-0.0022) | -4.8 [-8.3, -2.3]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 104 | - | 99% | 56,580 | 213,932 | 26,101 | 187,821 | - | $0.0077 | 9.5s |
| sample | 104 | 104/104 | +1% [-3%, +5%], 1/0 | -7,390 [-9,043, -5,797] | -19,717 [-37,857, -1,162] | -7,529 [-9,185, -5,934] | -12,187 [-29,942, +6,345] | -8,002 ($-0.00008) | -23% ($-0.0018) | -1.4 [-3.3, -0.0]s |
| schema | 104 | 104/104 | +1% [-3%, +5%], 1/0 | -6,688 [-8,375, -5,111] | -28,009 [-45,373, -10,294] | -6,858 [-8,542, -5,263] | -21,150 [-38,337, -3,760] | -3,638 ($-0.00004) | -23% ($-0.0017) | -1.7 [-3.6, -0.2]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Only the pairs where the envelope acted

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 104 | - | 99% | 56,580 | 213,932 | 26,101 | 187,821 | - | $0.0077 | 9.5s |
| sample | 104 | 104/104 | +1% [-3%, +5%], 1/0 | -7,390 [-9,043, -5,797] | -19,717 [-37,857, -1,162] | -7,529 [-9,185, -5,934] | -12,187 [-29,942, +6,345] | -8,002 ($-0.00008) | -23% ($-0.0018) | -1.4 [-3.3, -0.0]s |
| schema | 104 | 104/104 | +1% [-3%, +5%], 1/0 | -6,688 [-8,375, -5,111] | -28,009 [-45,373, -10,294] | -6,858 [-8,542, -5,263] | -21,150 [-38,337, -3,760] | -3,638 ($-0.00004) | -23% ($-0.0017) | -1.7 [-3.6, -0.2]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

312 runs, $2.04; 312 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | M | native | 1/1 [21%, 100%] | $0.0073 | 56571 | 1 | 0/1 | 0/1 |
| a11y | absent | M | sample | 1/1 [21%, 100%] | $0.0080 | 57823 | 2 | 1/1 | 0/1 |
| a11y | absent | M | schema | 1/1 [21%, 100%] | $0.0108 | 63358 | 4 | 1/1 | 0/1 |
| a11y | absent | L | native | 1/1 [21%, 100%] | $0.0179 | 90445 | 6 | 1/1 | 0/1 |
| a11y | absent | L | sample | 1/1 [21%, 100%] | $0.0068 | 48333 | 3 | 1/1 | 0/1 |
| a11y | absent | L | schema | 1/1 [21%, 100%] | $0.0077 | 49431 | 4 | 1/1 | 0/1 |
| a11y | count | M | native | 4/4 [51%, 100%] | $0.0070 | 56597 | 1.0 | 0/4 | 0/4 |
| a11y | count | M | sample | 4/4 [51%, 100%] | $0.0056 | 47228 | 2.0 | 3/4 | 0/4 |
| a11y | count | M | schema | 4/4 [51%, 100%] | $0.0056 | 47227 | 2.0 | 4/4 | 0/4 |
| a11y | count | L | native | 4/4 [51%, 100%] | $0.0069 | 48683 | 5.0 | 4/4 | 0/4 |
| a11y | count | L | sample | 4/4 [51%, 100%] | $0.0057 | 47491 | 2.0 | 4/4 | 0/4 |
| a11y | count | L | schema | 4/4 [51%, 100%] | $0.0056 | 47148 | 2.0 | 4/4 | 0/4 |
| a11y | enumerate | M | native | 2/2 [34%, 100%] | $0.0070 | 56599 | 1.0 | 0/2 | 0/2 |
| a11y | enumerate | M | sample | 2/2 [34%, 100%] | $0.0058 | 47478 | 2.0 | 2/2 | 0/2 |
| a11y | enumerate | M | schema | 2/2 [34%, 100%] | $0.0053 | 47105 | 1.5 | 1/2 | 0/2 |
| a11y | enumerate | L | native | 2/2 [34%, 100%] | $0.0076 | 52072 | 4.5 | 2/2 | 0/2 |
| a11y | enumerate | L | sample | 2/2 [34%, 100%] | $0.0053 | 47247 | 1.5 | 1/2 | 0/2 |
| a11y | enumerate | L | schema | 2/2 [34%, 100%] | $0.0049 | 46568 | 1.0 | 0/2 | 0/2 |
| a11y | lookup | M | native | 2/2 [34%, 100%] | $0.0069 | 56569 | 1.0 | 0/2 | 0/2 |
| a11y | lookup | M | sample | 2/2 [34%, 100%] | $0.0055 | 46811 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | M | schema | 2/2 [34%, 100%] | $0.0054 | 46922 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | native | 2/2 [34%, 100%] | $0.0055 | 46995 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | sample | 2/2 [34%, 100%] | $0.0054 | 46721 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | schema | 2/2 [34%, 100%] | $0.0057 | 47013 | 2.5 | 2/2 | 0/2 |
| a11y | spot | M | native | 4/4 [51%, 100%] | $0.0068 | 56565 | 1.0 | 0/4 | 0/4 |
| a11y | spot | M | sample | 4/4 [51%, 100%] | $0.0056 | 47006 | 2.0 | 4/4 | 0/4 |
| a11y | spot | M | schema | 4/4 [51%, 100%] | $0.0062 | 47872 | 2.0 | 4/4 | 0/4 |
| a11y | spot | L | native | 4/4 [51%, 100%] | $0.0141 | 88303 | 5.0 | 4/4 | 0/4 |
| a11y | spot | L | sample | 4/4 [51%, 100%] | $0.0056 | 47008 | 2.0 | 4/4 | 0/4 |
| a11y | spot | L | schema | 4/4 [51%, 100%] | $0.0056 | 47099 | 2.0 | 4/4 | 0/4 |
| figma | absent | M | native | 1/1 [21%, 100%] | $0.0073 | 57621 | 1 | 0/1 | 0/1 |
| figma | absent | M | sample | 1/1 [21%, 100%] | $0.0089 | 51234 | 5 | 1/1 | 0/1 |
| figma | absent | M | schema | 1/1 [21%, 100%] | $0.0093 | 59718 | 3 | 1/1 | 0/1 |
| figma | absent | L | native | 1/1 [21%, 100%] | $0.0103 | 53888 | 6 | 1/1 | 0/1 |
| figma | absent | L | sample | 1/1 [21%, 100%] | $0.0110 | 58151 | 6 | 1/1 | 0/1 |
| figma | absent | L | schema | 1/1 [21%, 100%] | $0.0091 | 51358 | 5 | 1/1 | 0/1 |
| figma | count | M | native | 4/4 [51%, 100%] | $0.0074 | 57726 | 1.0 | 0/4 | 0/4 |
| figma | count | M | sample | 4/4 [51%, 100%] | $0.0066 | 48296 | 3.0 | 4/4 | 0/4 |
| figma | count | M | schema | 4/4 [51%, 100%] | $0.0085 | 59226 | 3.0 | 4/4 | 0/4 |
| figma | count | L | native | 4/4 [51%, 100%] | $0.0065 | 48246 | 3.0 | 4/4 | 0/4 |
| figma | count | L | sample | 4/4 [51%, 100%] | $0.0065 | 48316 | 3.0 | 3/4 | 0/4 |
| figma | count | L | schema | 4/4 [51%, 100%] | $0.0064 | 47532 | 3.0 | 3/4 | 0/4 |
| figma | enumerate | M | native | 2/2 [34%, 100%] | $0.0075 | 57704 | 1.0 | 0/2 | 0/2 |
| figma | enumerate | M | sample | 2/2 [34%, 100%] | $0.0071 | 53692 | 2.0 | 2/2 | 0/2 |
| figma | enumerate | M | schema | 2/2 [34%, 100%] | $0.0066 | 52840 | 1.5 | 1/2 | 0/2 |
| figma | enumerate | L | native | 2/2 [34%, 100%] | $0.0064 | 48804 | 2.5 | 2/2 | 0/2 |
| figma | enumerate | L | sample | 2/2 [34%, 100%] | $0.0069 | 49241 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | L | schema | 2/2 [34%, 100%] | $0.0062 | 47983 | 2.5 | 2/2 | 0/2 |
| figma | lookup | M | native | 2/2 [34%, 100%] | $0.0071 | 57616 | 1.0 | 0/2 | 0/2 |
| figma | lookup | M | sample | 2/2 [34%, 100%] | $0.0064 | 47292 | 3.5 | 2/2 | 0/2 |
| figma | lookup | M | schema | 2/2 [34%, 100%] | $0.0060 | 46849 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | native | 2/2 [34%, 100%] | $0.0069 | 47392 | 4.0 | 2/2 | 0/2 |
| figma | lookup | L | sample | 2/2 [34%, 100%] | $0.0061 | 47140 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | schema | 2/2 [34%, 100%] | $0.0060 | 46825 | 3.0 | 2/2 | 0/2 |
| figma | spot | M | native | 4/4 [51%, 100%] | $0.0072 | 57652 | 1.0 | 0/4 | 0/4 |
| figma | spot | M | sample | 4/4 [51%, 100%] | $0.0075 | 53913 | 3.0 | 4/4 | 0/4 |
| figma | spot | M | schema | 4/4 [51%, 100%] | $0.0079 | 58695 | 2.0 | 4/4 | 0/4 |
| figma | spot | L | native | 3/4 [30%, 95%] | $0.0108 | 54377 | 6.5 | 4/4 | 0/4 |
| figma | spot | L | sample | 4/4 [51%, 100%] | $0.0065 | 47966 | 3.0 | 3/4 | 0/4 |
| figma | spot | L | schema | 4/4 [51%, 100%] | $0.0075 | 49028 | 4.0 | 4/4 | 0/4 |
| json | absent | M | native | 1/1 [21%, 100%] | $0.0073 | 58341 | 1 | 0/1 | 0/1 |
| json | absent | M | sample | 1/1 [21%, 100%] | $0.0079 | 53768 | 3 | 1/1 | 0/1 |
| json | absent | M | schema | 1/1 [21%, 100%] | $0.0047 | 46140 | 1 | 0/1 | 0/1 |
| json | absent | L | native | 1/1 [21%, 100%] | $0.0073 | 48663 | 4 | 1/1 | 0/1 |
| json | absent | L | sample | 1/1 [21%, 100%] | $0.0055 | 46825 | 2 | 1/1 | 0/1 |
| json | absent | L | schema | 1/1 [21%, 100%] | $0.0048 | 46127 | 1 | 0/1 | 0/1 |
| json | count | M | native | 4/4 [51%, 100%] | $0.0073 | 58466 | 1.0 | 0/4 | 0/4 |
| json | count | M | sample | 4/4 [51%, 100%] | $0.0057 | 48171 | 2.0 | 4/4 | 0/4 |
| json | count | M | schema | 4/4 [51%, 100%] | $0.0047 | 46221 | 1.0 | 1/4 | 0/4 |
| json | count | L | native | 4/4 [51%, 100%] | $0.0065 | 48207 | 3.0 | 4/4 | 0/4 |
| json | count | L | sample | 4/4 [51%, 100%] | $0.0057 | 48274 | 2.0 | 4/4 | 0/4 |
| json | count | L | schema | 4/4 [51%, 100%] | $0.0052 | 47047 | 1.5 | 2/4 | 0/4 |
| json | enumerate | M | native | 2/2 [34%, 100%] | $0.0076 | 58443 | 1.0 | 0/2 | 0/2 |
| json | enumerate | M | sample | 2/2 [34%, 100%] | $0.0059 | 48377 | 2.0 | 2/2 | 0/2 |
| json | enumerate | M | schema | 2/2 [34%, 100%] | $0.0055 | 46731 | 2.0 | 2/2 | 0/2 |
| json | enumerate | L | native | 2/2 [34%, 100%] | $0.0070 | 48594 | 3.5 | 2/2 | 0/2 |
| json | enumerate | L | sample | 2/2 [34%, 100%] | $0.0059 | 48353 | 2.0 | 2/2 | 0/2 |
| json | enumerate | L | schema | 2/2 [34%, 100%] | $0.0049 | 46593 | 1.0 | 0/2 | 0/2 |
| json | lookup | M | native | 2/2 [34%, 100%] | $0.0072 | 58327 | 1.0 | 0/2 | 0/2 |
| json | lookup | M | sample | 2/2 [34%, 100%] | $0.0054 | 46794 | 2.0 | 2/2 | 0/2 |
| json | lookup | M | schema | 2/2 [34%, 100%] | $0.0052 | 46390 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | native | 2/2 [34%, 100%] | $0.0064 | 47085 | 3.5 | 2/2 | 0/2 |
| json | lookup | L | sample | 2/2 [34%, 100%] | $0.0053 | 46630 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | schema | 2/2 [34%, 100%] | $0.0053 | 46374 | 2.0 | 2/2 | 0/2 |
| json | spot | M | native | 4/4 [51%, 100%] | $0.0072 | 58341 | 1.0 | 0/4 | 0/4 |
| json | spot | M | sample | 4/4 [51%, 100%] | $0.0049 | 46615 | 1.0 | 1/4 | 0/4 |
| json | spot | M | schema | 4/4 [51%, 100%] | $0.0047 | 46224 | 1.0 | 0/4 | 0/4 |
| json | spot | L | native | 4/4 [51%, 100%] | $0.0073 | 48893 | 4.0 | 4/4 | 0/4 |
| json | spot | L | sample | 4/4 [51%, 100%] | $0.0048 | 46584 | 1.0 | 1/4 | 0/4 |
| json | spot | L | schema | 4/4 [51%, 100%] | $0.0048 | 46217 | 1.0 | 1/4 | 0/4 |
| log | absent | M | native | 1/1 [21%, 100%] | $0.0076 | 60286 | 1 | 0/1 | 0/1 |
| log | absent | M | sample | 1/1 [21%, 100%] | $0.0056 | 46893 | 2 | 1/1 | 0/1 |
| log | absent | M | schema | 1/1 [21%, 100%] | $0.0086 | 61701 | 2 | 1/1 | 0/1 |
| log | absent | L | native | 1/1 [21%, 100%] | $0.0079 | 50113 | 5 | 1/1 | 0/1 |
| log | absent | L | sample | 1/1 [21%, 100%] | $0.0063 | 47136 | 3 | 1/1 | 0/1 |
| log | absent | L | schema | 1/1 [21%, 100%] | $0.0088 | 51942 | 5 | 1/1 | 0/1 |
| log | count | M | native | 4/4 [51%, 100%] | $0.0077 | 60316 | 1.0 | 0/4 | 0/4 |
| log | count | M | sample | 4/4 [51%, 100%] | $0.0055 | 47275 | 2.0 | 3/4 | 0/4 |
| log | count | M | schema | 4/4 [51%, 100%] | $0.0052 | 46874 | 1.5 | 2/4 | 0/4 |
| log | count | L | native | 4/4 [51%, 100%] | $0.0064 | 48517 | 4.0 | 4/4 | 0/4 |
| log | count | L | sample | 4/4 [51%, 100%] | $0.0049 | 47129 | 1.0 | 1/4 | 0/4 |
| log | count | L | schema | 4/4 [51%, 100%] | $0.0048 | 46688 | 1.0 | 0/4 | 0/4 |
| log | enumerate | M | native | 2/2 [34%, 100%] | $0.0077 | 60363 | 1.0 | 0/2 | 0/2 |
| log | enumerate | M | sample | 2/2 [34%, 100%] | $0.0050 | 46866 | 1.0 | 0/2 | 0/2 |
| log | enumerate | M | schema | 2/2 [34%, 100%] | $0.0049 | 46675 | 1.0 | 0/2 | 0/2 |
| log | enumerate | L | native | 2/2 [34%, 100%] | $0.0063 | 47394 | 3.5 | 2/2 | 0/2 |
| log | enumerate | L | sample | 2/2 [34%, 100%] | $0.0055 | 47241 | 1.5 | 1/2 | 0/2 |
| log | enumerate | L | schema | 2/2 [34%, 100%] | $0.0050 | 46687 | 1.0 | 0/2 | 0/2 |
| log | lookup | M | native | 2/2 [34%, 100%] | $0.0077 | 60293 | 1.0 | 0/2 | 0/2 |
| log | lookup | M | sample | 2/2 [34%, 100%] | $0.0054 | 46710 | 2.0 | 2/2 | 0/2 |
| log | lookup | M | schema | 2/2 [34%, 100%] | $0.0053 | 46420 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | native | 2/2 [34%, 100%] | $0.0054 | 46352 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | sample | 2/2 [34%, 100%] | $0.0054 | 46653 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | schema | 2/2 [34%, 100%] | $0.0053 | 46379 | 2.0 | 2/2 | 0/2 |
| log | spot | M | native | 4/4 [51%, 100%] | $0.0076 | 60306 | 1.0 | 0/4 | 0/4 |
| log | spot | M | sample | 4/4 [51%, 100%] | $0.0056 | 47268 | 2.0 | 4/4 | 0/4 |
| log | spot | M | schema | 4/4 [51%, 100%] | $0.0055 | 46710 | 2.0 | 4/4 | 0/4 |
| log | spot | L | native | 4/4 [51%, 100%] | $0.0092 | 52403 | 9.0 | 4/4 | 0/4 |
| log | spot | L | sample | 4/4 [51%, 100%] | $0.0057 | 47186 | 2.0 | 4/4 | 0/4 |
| log | spot | L | schema | 4/4 [51%, 100%] | $0.0056 | 47119 | 2.0 | 3/4 | 0/4 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | M | sample | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0013 [-0.0014, -0.0012] | -9444 [-9658, -8899] | +37076 [+36792, +38111] | +1.8s [+1.1, +2.6] | undecided (indicative: under 30 pairs) |
| a11y | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0013 [-0.0014, -0.0010] | -9289 [-9634, -8979] | +37018 [+36630, +38186] | +1.4s [+1.3, +2.9] | undecided (indicative: under 30 pairs) |
| a11y | L | sample | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0023 [-0.0068, -0.0011] | -2106 [-39884, -1227] | -47335 [-96421, -40822] | -2.3s [-3.4, -0.7] | undecided (indicative: under 30 pairs) |
| a11y | L | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0016 [-0.0045, -0.0008] | -1710 [-10811, -947] | -47766 [-109125, -41028] | -2.6s [-3.2, -1.5] | undecided (indicative: under 30 pairs) |
| figma | M | sample | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0004 [-0.0008, +0.0009] | -9387 [-9687, -6387] | +85044 [+48553, +87561] | +3.5s [+2.6, +4.2] | undecided (indicative: under 30 pairs) |
| figma | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $+0.0008 [-0.0009, +0.0009] | +1135 [-9583, +1514] | +48119 [+47452, +85352] | +2.6s [+1.0, +3.3] | undecided (indicative: under 30 pairs) |
| figma | L | sample | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0006 [-0.0026, +0.0001] | -201 [-3695, +176] | -46265 [-94556, +1124] | -2.0s [-6.9, -0.9] | undecided (indicative: under 30 pairs) |
| figma | L | schema | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0012 [-0.0016, -0.0001] | -1113 [-2530, -362] | -50328 [-95035, -926] | -2.5s [-4.3, -0.7] | undecided (indicative: under 30 pairs) |
| json | M | sample | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0016 [-0.0021, -0.0016] | -10947 [-11543, -10160] | +35983 [+34822, +37881] | +1.6s [+0.5, +2.3] | undecided (indicative: under 30 pairs) |
| json | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0024 [-0.0025, -0.0020] | -12085 [-12157, -11920] | -12083 [-12203, +34182] | +0.4s [-0.2, +1.1] | undecided (indicative: under 30 pairs) |
| json | L | sample | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0015 [-0.0018, -0.0008] | -663 [-1838, -234] | -93366 [-96547, -45610] | -3.7s [-5.3, -2.1] | undecided (indicative: under 30 pairs) |
| json | L | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0017 [-0.0025, -0.0015] | -1631 [-2505, -1224] | -94737 [-143588, -93886] | -4.2s [-5.7, -3.3] | undecided (indicative: under 30 pairs) |
| log | M | sample | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0022 [-0.0023, -0.0021] | -13213 [-13393, -13052] | +33272 [+32692, +33431] | +1.3s [+0.7, +1.6] | undecided (indicative: under 30 pairs) |
| log | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0023 [-0.0027, -0.0021] | -13567 [-13848, -13354] | +32555 [-13495, +33180] | +1.3s [+0.1, +1.8] | undecided (indicative: under 30 pairs) |
| log | L | sample | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0014 [-0.0022, -0.0007] | -1120 [-2984, -248] | -93329 [-110922, -47173] | -3.7s [-5.4, -1.9] | undecided (indicative: under 30 pairs) |
| log | L | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0015 [-0.0022, -0.0013] | -1294 [-3028, -487] | -94698 [-143777, -93515] | -3.1s [-4.9, -2.3] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | sample | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0016 [-0.0019, -0.0013] | -9899 [-11110, -9540] | +36904 [+34956, +37996] | +1.9s [+1.6, +2.4] | undecided |
| M | schema | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0019 [-0.0022, -0.0013] | -10892 [-12048, -9567] | +34976 [+33180, +37160] | +1.3s [+0.9, +2.0] | undecided |
| L | sample | 52 | +2% [-5%, +10%] | 1/0, p 1.00 | $-0.0015 [-0.0019, -0.0008] | -1174 [-2011, -440] | -57230 [-94634, -46419] | -3.0s [-4.0, -2.0] | undecided |
| L | schema | 52 | +2% [-5%, +10%] | 1/0, p 1.00 | $-0.0015 [-0.0020, -0.0013] | -1615 [-2336, -1113] | -94200 [-95837, -49072] | -3.2s [-3.8, -2.6] | undecided |

## When the envelope acted: the pairs whose folded session folded the task's large output

| band | condition | acted | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| M | sample | 52/52 (saw it 52) | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0016 [-0.0019, -0.0013] | -9899 [-11110, -9540] | +36904 [+34956, +37996] | +1.9s [+1.6, +2.4] | undecided |
| M | schema | 52/52 (saw it 52) | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0019 [-0.0022, -0.0013] | -10892 [-12048, -9567] | +34976 [+33180, +37160] | +1.3s [+0.9, +2.0] | undecided |
| L | sample | 52/52 (saw it 52) | 52 | +2% [-5%, +10%] | 1/0, p 1.00 | $-0.0015 [-0.0019, -0.0008] | -1174 [-2011, -440] | -57230 [-94634, -46419] | -3.0s [-4.0, -2.0] | undecided |
| L | schema | 52/52 (saw it 52) | 52 | +2% [-5%, +10%] | 1/0, p 1.00 | $-0.0015 [-0.0020, -0.0013] | -1615 [-2336, -1113] | -94200 [-95837, -49072] | -3.2s [-3.8, -2.6] | undecided |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, 2026-11-03); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | sample | 52 | +1.1 [+0.9, +1.3] | -9,729 [-10,774, -8,504] | +53,631 [+44,551, +63,848] | +2.3 [+1.9, +2.7] | 52/52, 52/52 | -9,899 tokens, $-0.00010 |
| M | schema | 52 | +0.9 [+0.7, +1.1] | -8,732 [-10,212, -6,944] | +43,230 [+34,599, +53,045] | +1.8 [+1.5, +2.2] | 52/52, 52/52 | -10,892 tokens, $-0.00011 |
| L | sample | 52 | -1.5 [-2.0, -1.1] | -5,330 [-8,462, -2,628] | -78,005 [-103,534, -55,397] | -3.0 [-3.9, -2.2] | 52/52, 52/52 | -1,174 tokens, $-0.00001 |
| L | schema | 52 | -1.7 [-2.1, -1.2] | -4,984 [-7,785, -2,666] | -85,530 [-111,650, -62,228] | -3.3 [-4.3, -2.5] | 52/52, 52/52 | -1,615 tokens, $-0.00002 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

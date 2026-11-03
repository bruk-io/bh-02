# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

312 runs, $2.01; 312 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | L | bash-native | 1/1 [21%, 100%] | $0.0066 | 48714 | 3 | 0/1 | 0/1 |
| a11y | absent | L | fold-bash | 1/1 [21%, 100%] | $0.0080 | 50259 | 4 | 1/1 | 0/1 |
| a11y | absent | L | fold-bash-all | 1/1 [21%, 100%] | $0.0101 | 53763 | 6 | 0/1 | 0/1 |
| a11y | absent | M | bash-native | 1/1 [21%, 100%] | $0.0071 | 56371 | 1 | 0/1 | 0/1 |
| a11y | absent | M | fold-bash | 1/1 [21%, 100%] | $0.0074 | 53378 | 3 | 1/1 | 0/1 |
| a11y | absent | M | fold-bash-all | 1/1 [21%, 100%] | $0.0072 | 51807 | 3 | 0/1 | 0/1 |
| a11y | count | L | bash-native | 4/4 [51%, 100%] | $0.0059 | 47915 | 3.5 | 3/4 | 0/4 |
| a11y | count | L | fold-bash | 4/4 [51%, 100%] | $0.0058 | 47989 | 3.5 | 3/4 | 0/4 |
| a11y | count | L | fold-bash-all | 4/4 [51%, 100%] | $0.0062 | 49795 | 3.0 | 3/4 | 0/4 |
| a11y | count | M | bash-native | 4/4 [51%, 100%] | $0.0065 | 56408 | 1.0 | 0/4 | 0/4 |
| a11y | count | M | fold-bash | 4/4 [51%, 100%] | $0.0058 | 49696 | 2.0 | 3/4 | 0/4 |
| a11y | count | M | fold-bash-all | 4/4 [51%, 100%] | $0.0061 | 50141 | 2.5 | 4/4 | 0/4 |
| a11y | enumerate | L | bash-native | 2/2 [34%, 100%] | $0.0063 | 48150 | 4.0 | 2/2 | 0/2 |
| a11y | enumerate | L | fold-bash | 2/2 [34%, 100%] | $0.0060 | 48101 | 4.5 | 2/2 | 0/2 |
| a11y | enumerate | L | fold-bash-all | 2/2 [34%, 100%] | $0.0057 | 49574 | 2.0 | 2/2 | 0/2 |
| a11y | enumerate | M | bash-native | 2/2 [34%, 100%] | $0.0065 | 56380 | 1.0 | 0/2 | 0/2 |
| a11y | enumerate | M | fold-bash | 2/2 [34%, 100%] | $0.0057 | 49714 | 2.0 | 0/2 | 0/2 |
| a11y | enumerate | M | fold-bash-all | 2/2 [34%, 100%] | $0.0070 | 50645 | 3.5 | 2/2 | 0/2 |
| a11y | lookup | L | bash-native | 2/2 [34%, 100%] | $0.0050 | 46788 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | fold-bash | 2/2 [34%, 100%] | $0.0050 | 46908 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | fold-bash-all | 2/2 [34%, 100%] | $0.0061 | 49627 | 3.0 | 2/2 | 0/2 |
| a11y | lookup | M | bash-native | 2/2 [34%, 100%] | $0.0064 | 56428 | 1.0 | 0/2 | 0/2 |
| a11y | lookup | M | fold-bash | 2/2 [34%, 100%] | $0.0055 | 49396 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | M | fold-bash-all | 2/2 [34%, 100%] | $0.0059 | 49948 | 2.5 | 2/2 | 0/2 |
| a11y | spot | L | bash-native | 3/4 [30%, 95%] | $0.0077 | 49381 | 5.0 | 1/4 | 0/4 |
| a11y | spot | L | fold-bash | 2/4 [15%, 85%] | $0.0079 | 49363 | 5.0 | 3/4 | 0/4 |
| a11y | spot | L | fold-bash-all | 4/4 [51%, 100%] | $0.0063 | 50220 | 2.5 | 2/4 | 0/4 |
| a11y | spot | M | bash-native | 4/4 [51%, 100%] | $0.0064 | 56425 | 1.0 | 0/4 | 0/4 |
| a11y | spot | M | fold-bash | 4/4 [51%, 100%] | $0.0070 | 50717 | 3.5 | 2/4 | 0/4 |
| a11y | spot | M | fold-bash-all | 4/4 [51%, 100%] | $0.0069 | 51163 | 3.0 | 4/4 | 0/4 |
| figma | absent | L | bash-native | 1/1 [21%, 100%] | $0.0084 | 50622 | 5 | 0/1 | 0/1 |
| figma | absent | L | fold-bash | 1/1 [21%, 100%] | $0.0078 | 49964 | 4 | 1/1 | 0/1 |
| figma | absent | L | fold-bash-all | 1/1 [21%, 100%] | $0.0070 | 50730 | 3 | 1/1 | 0/1 |
| figma | absent | M | bash-native | 1/1 [21%, 100%] | $0.0082 | 59032 | 2 | 0/1 | 0/1 |
| figma | absent | M | fold-bash | 1/1 [21%, 100%] | $0.0083 | 53555 | 4 | 0/1 | 0/1 |
| figma | absent | M | fold-bash-all | 1/1 [21%, 100%] | $0.0061 | 49880 | 2 | 1/1 | 0/1 |
| figma | count | L | bash-native | 4/4 [51%, 100%] | $0.0062 | 47840 | 3.5 | 3/4 | 0/4 |
| figma | count | L | fold-bash | 4/4 [51%, 100%] | $0.0060 | 48323 | 3.0 | 2/4 | 0/4 |
| figma | count | L | fold-bash-all | 4/4 [51%, 100%] | $0.0061 | 50240 | 2.5 | 4/4 | 0/4 |
| figma | count | M | bash-native | 4/4 [51%, 100%] | $0.0071 | 57512 | 1.0 | 0/4 | 0/4 |
| figma | count | M | fold-bash | 4/4 [51%, 100%] | $0.0064 | 49880 | 3.0 | 4/4 | 0/4 |
| figma | count | M | fold-bash-all | 4/4 [51%, 100%] | $0.0062 | 50037 | 2.5 | 2/4 | 0/4 |
| figma | enumerate | L | bash-native | 2/2 [34%, 100%] | $0.0060 | 47676 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | L | fold-bash | 2/2 [34%, 100%] | $0.0057 | 47508 | 2.5 | 0/2 | 0/2 |
| figma | enumerate | L | fold-bash-all | 2/2 [34%, 100%] | $0.0068 | 50459 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | M | bash-native | 2/2 [34%, 100%] | $0.0070 | 57507 | 1.0 | 0/2 | 0/2 |
| figma | enumerate | M | fold-bash | 2/2 [34%, 100%] | $0.0066 | 49983 | 3.0 | 0/2 | 0/2 |
| figma | enumerate | M | fold-bash-all | 2/2 [34%, 100%] | $0.0070 | 50603 | 3.5 | 1/2 | 0/2 |
| figma | lookup | L | bash-native | 2/2 [34%, 100%] | $0.0054 | 47021 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | fold-bash | 2/2 [34%, 100%] | $0.0052 | 46891 | 2.5 | 2/2 | 0/2 |
| figma | lookup | L | fold-bash-all | 2/2 [34%, 100%] | $0.0055 | 49242 | 2.0 | 2/2 | 0/2 |
| figma | lookup | M | bash-native | 2/2 [34%, 100%] | $0.0066 | 57429 | 1.0 | 0/2 | 0/2 |
| figma | lookup | M | fold-bash | 2/2 [34%, 100%] | $0.0057 | 49159 | 2.5 | 1/2 | 0/2 |
| figma | lookup | M | fold-bash-all | 2/2 [34%, 100%] | $0.0054 | 49077 | 2.0 | 0/2 | 0/2 |
| figma | spot | L | bash-native | 2/4 [15%, 85%] | $0.0082 | 50567 | 4.0 | 1/4 | 0/4 |
| figma | spot | L | fold-bash | 2/4 [15%, 85%] | $0.0098 | 51918 | 5.5 | 4/4 | 0/4 |
| figma | spot | L | fold-bash-all | 3/4 [30%, 95%] | $0.0079 | 51442 | 4.0 | 3/4 | 0/4 |
| figma | spot | M | bash-native | 4/4 [51%, 100%] | $0.0065 | 57475 | 1.0 | 0/4 | 0/4 |
| figma | spot | M | fold-bash | 2/4 [15%, 85%] | $0.0068 | 50245 | 2.5 | 3/4 | 0/4 |
| figma | spot | M | fold-bash-all | 3/4 [30%, 95%] | $0.0076 | 53405 | 3.0 | 3/4 | 0/4 |
| json | absent | L | bash-native | 1/1 [21%, 100%] | $0.0074 | 49547 | 4 | 1/1 | 0/1 |
| json | absent | L | fold-bash | 1/1 [21%, 100%] | $0.0063 | 48309 | 3 | 0/1 | 0/1 |
| json | absent | L | fold-bash-all | 1/1 [21%, 100%] | $0.0063 | 48554 | 3 | 1/1 | 0/1 |
| json | absent | M | bash-native | 1/1 [21%, 100%] | $0.0067 | 58138 | 1 | 0/1 | 0/1 |
| json | absent | M | fold-bash | 0/1 [0%, 79%] | $0.0060 | 50007 | 2 | 1/1 | 0/1 |
| json | absent | M | fold-bash-all | 1/1 [21%, 100%] | $0.0061 | 50506 | 2 | 1/1 | 0/1 |
| json | count | L | bash-native | 4/4 [51%, 100%] | $0.0053 | 47866 | 2.0 | 1/4 | 0/4 |
| json | count | L | fold-bash | 4/4 [51%, 100%] | $0.0070 | 49284 | 4.0 | 3/4 | 0/4 |
| json | count | L | fold-bash-all | 4/4 [51%, 100%] | $0.0058 | 50105 | 2.0 | 3/4 | 0/4 |
| json | count | M | bash-native | 4/4 [51%, 100%] | $0.0075 | 58839 | 2.0 | 0/4 | 0/4 |
| json | count | M | fold-bash | 4/4 [51%, 100%] | $0.0056 | 49833 | 2.0 | 1/4 | 0/4 |
| json | count | M | fold-bash-all | 4/4 [51%, 100%] | $0.0056 | 49872 | 2.0 | 1/4 | 0/4 |
| json | enumerate | L | bash-native | 2/2 [34%, 100%] | $0.0063 | 48620 | 3.0 | 1/2 | 0/2 |
| json | enumerate | L | fold-bash | 2/2 [34%, 100%] | $0.0054 | 48027 | 2.0 | 0/2 | 0/2 |
| json | enumerate | L | fold-bash-all | 2/2 [34%, 100%] | $0.0058 | 50024 | 2.0 | 0/2 | 0/2 |
| json | enumerate | M | bash-native | 2/2 [34%, 100%] | $0.0070 | 58224 | 1.0 | 0/2 | 0/2 |
| json | enumerate | M | fold-bash | 2/2 [34%, 100%] | $0.0059 | 49155 | 2.5 | 1/2 | 0/2 |
| json | enumerate | M | fold-bash-all | 2/2 [34%, 100%] | $0.0057 | 49196 | 2.0 | 1/2 | 0/2 |
| json | lookup | L | bash-native | 2/2 [34%, 100%] | $0.0054 | 47138 | 2.5 | 2/2 | 0/2 |
| json | lookup | L | fold-bash | 2/2 [34%, 100%] | $0.0050 | 46796 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | fold-bash-all | 2/2 [34%, 100%] | $0.0052 | 48144 | 2.0 | 2/2 | 0/2 |
| json | lookup | M | bash-native | 2/2 [34%, 100%] | $0.0067 | 58230 | 1.0 | 0/2 | 0/2 |
| json | lookup | M | fold-bash | 2/2 [34%, 100%] | $0.0055 | 49655 | 2.0 | 0/2 | 0/2 |
| json | lookup | M | fold-bash-all | 2/2 [34%, 100%] | $0.0056 | 48458 | 2.5 | 1/2 | 0/2 |
| json | spot | L | bash-native | 4/4 [51%, 100%] | $0.0061 | 48366 | 3.0 | 4/4 | 0/4 |
| json | spot | L | fold-bash | 4/4 [51%, 100%] | $0.0064 | 48380 | 3.5 | 2/4 | 0/4 |
| json | spot | L | fold-bash-all | 4/4 [51%, 100%] | $0.0058 | 48798 | 2.5 | 4/4 | 0/4 |
| json | spot | M | bash-native | 4/4 [51%, 100%] | $0.0067 | 58212 | 1.0 | 0/4 | 0/4 |
| json | spot | M | fold-bash | 4/4 [51%, 100%] | $0.0059 | 48956 | 2.0 | 2/4 | 0/4 |
| json | spot | M | fold-bash-all | 4/4 [51%, 100%] | $0.0066 | 51495 | 2.5 | 0/4 | 0/4 |
| log | absent | L | bash-native | 1/1 [21%, 100%] | $0.0109 | 60723 | 6 | 0/1 | 0/1 |
| log | absent | L | fold-bash | 1/1 [21%, 100%] | $0.0062 | 48273 | 3 | 0/1 | 0/1 |
| log | absent | L | fold-bash-all | 1/1 [21%, 100%] | $0.0064 | 48588 | 3 | 1/1 | 0/1 |
| log | absent | M | bash-native | 1/1 [21%, 100%] | $0.0071 | 60161 | 1 | 0/1 | 0/1 |
| log | absent | M | fold-bash | 1/1 [21%, 100%] | $0.0064 | 49210 | 3 | 1/1 | 0/1 |
| log | absent | M | fold-bash-all | 1/1 [21%, 100%] | $0.0062 | 48915 | 3 | 1/1 | 0/1 |
| log | count | L | bash-native | 4/4 [51%, 100%] | $0.0059 | 48066 | 3.0 | 3/4 | 0/4 |
| log | count | L | fold-bash | 4/4 [51%, 100%] | $0.0060 | 48299 | 3.0 | 1/4 | 0/4 |
| log | count | L | fold-bash-all | 4/4 [51%, 100%] | $0.0060 | 50012 | 2.5 | 3/4 | 0/4 |
| log | count | M | bash-native | 4/4 [51%, 100%] | $0.0072 | 60096 | 1.0 | 0/4 | 0/4 |
| log | count | M | fold-bash | 4/4 [51%, 100%] | $0.0058 | 49815 | 2.0 | 2/4 | 0/4 |
| log | count | M | fold-bash-all | 4/4 [51%, 100%] | $0.0064 | 50321 | 3.0 | 3/4 | 0/4 |
| log | enumerate | L | bash-native | 2/2 [34%, 100%] | $0.0061 | 48136 | 3.0 | 1/2 | 0/2 |
| log | enumerate | L | fold-bash | 2/2 [34%, 100%] | $0.0060 | 48431 | 3.0 | 2/2 | 0/2 |
| log | enumerate | L | fold-bash-all | 2/2 [34%, 100%] | $0.0062 | 49879 | 2.5 | 2/2 | 0/2 |
| log | enumerate | M | bash-native | 2/2 [34%, 100%] | $0.0072 | 60132 | 1.0 | 0/2 | 0/2 |
| log | enumerate | M | fold-bash | 2/2 [34%, 100%] | $0.0077 | 50888 | 4.5 | 1/2 | 0/2 |
| log | enumerate | M | fold-bash-all | 2/2 [34%, 100%] | $0.0057 | 49490 | 2.0 | 0/2 | 0/2 |
| log | lookup | L | bash-native | 2/2 [34%, 100%] | $0.0050 | 46831 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | fold-bash | 2/2 [34%, 100%] | $0.0048 | 46802 | 2.0 | 1/2 | 0/2 |
| log | lookup | L | fold-bash-all | 2/2 [34%, 100%] | $0.0052 | 47911 | 2.5 | 2/2 | 0/2 |
| log | lookup | M | bash-native | 2/2 [34%, 100%] | $0.0071 | 59957 | 1.0 | 0/2 | 0/2 |
| log | lookup | M | fold-bash | 2/2 [34%, 100%] | $0.0052 | 47897 | 2.0 | 2/2 | 0/2 |
| log | lookup | M | fold-bash-all | 2/2 [34%, 100%] | $0.0051 | 47942 | 2.0 | 2/2 | 0/2 |
| log | spot | L | bash-native | 4/4 [51%, 100%] | $0.0065 | 48887 | 3.5 | 1/4 | 0/4 |
| log | spot | L | fold-bash | 4/4 [51%, 100%] | $0.0065 | 48683 | 3.5 | 3/4 | 0/4 |
| log | spot | L | fold-bash-all | 4/4 [51%, 100%] | $0.0057 | 48476 | 2.5 | 2/4 | 0/4 |
| log | spot | M | bash-native | 4/4 [51%, 100%] | $0.0071 | 60065 | 1.0 | 0/4 | 0/4 |
| log | spot | M | fold-bash | 4/4 [51%, 100%] | $0.0060 | 48781 | 3.0 | 2/4 | 0/4 |
| log | spot | M | fold-bash-all | 4/4 [51%, 100%] | $0.0058 | 48634 | 2.5 | 1/4 | 0/4 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | L | fold-bash (against bash-native) | 13 | -8% [-36%, +21%] | 1/2, p 1.00 | $+0.0000 [-0.0003, +0.0006] | +198 [-442, +407] | +3 [-1697, +47221] | +0.3s [-3.2, +6.8] | undecided (indicative: under 30 pairs) |
| a11y | L | fold-bash-all (against bash-native) | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0001 [-0.0009, +0.0010] | +1924 [+955, +2671] | -39792 [-90957, +54217] | +1.1s [-4.8, +2.9] | fails (indicative: under 30 pairs) |
| a11y | M | fold-bash (against bash-native) | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0007 [-0.0008, +0.0003] | -6486 [-6953, -6098] | +42413 [+42028, +92604] | +6.3s [+4.3, +7.7] | undecided (indicative: under 30 pairs) |
| a11y | M | fold-bash-all (against bash-native) | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $+0.0001 [-0.0006, +0.0003] | -5959 [-6266, -5664] | +92573 [+42817, +95102] | +5.9s [+4.0, +9.3] | undecided (indicative: under 30 pairs) |
| figma | L | fold-bash (against bash-native) | 13 | +0% [-25%, +25%] | 1/1, p 1.00 | $+0.0000 [-0.0003, +0.0006] | +28 [-140, +397] | +245 [-302, +47880] | +1.3s [-2.6, +3.4] | undecided (indicative: under 30 pairs) |
| figma | L | fold-bash-all (against bash-native) | 13 | +8% [-12%, +31%] | 1/0, p 1.00 | $+0.0003 [-0.0005, +0.0007] | +2110 [+1264, +2481] | +4851 [-42509, +7989] | -2.1s [-4.2, +1.7] | fails (indicative: under 30 pairs) |
| figma | M | fold-bash (against bash-native) | 13 | -15% [-42%, +10%] | 0/2, p 0.50 | $-0.0006 [-0.0008, +0.0004] | -7545 [-8050, -6853] | +89580 [+40920, +90912] | +7.0s [+4.1, +11.2] | undecided (indicative: under 30 pairs) |
| figma | M | fold-bash-all (against bash-native) | 13 | -8% [-33%, +16%] | 0/1, p 1.00 | $-0.0005 [-0.0012, +0.0005] | -7357 [-8041, -6676] | +41045 [+40347, +99102] | +4.4s [+1.9, +12.6] | undecided (indicative: under 30 pairs) |
| json | L | fold-bash (against bash-native) | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0001 [-0.0010, +0.0000] | -31 [-980, +840] | -39 [-50482, +793] | -0.8s [-3.9, +3.6] | undecided (indicative: under 30 pairs) |
| json | L | fold-bash-all (against bash-native) | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0001 [-0.0011, +0.0005] | +746 [-150, +2387] | -374 [-50103, +5736] | -1.8s [-4.4, +4.8] | undecided (indicative: under 30 pairs) |
| json | M | fold-bash (against bash-native) | 13 | -8% [-33%, +16%] | 0/1, p 1.00 | $-0.0016 [-0.0018, -0.0006] | -8964 [-10056, -8131] | +36680 [-18084, +40597] | +4.0s [+0.6, +7.2] | undecided (indicative: under 30 pairs) |
| json | M | fold-bash-all (against bash-native) | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0011 [-0.0018, -0.0004] | -8137 [-9026, -7632] | +41311 [-17740, +43686] | +3.7s [+1.8, +6.3] | undecided (indicative: under 30 pairs) |
| log | L | fold-bash (against bash-native) | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $+0.0000 [-0.0001, +0.0001] | -24 [-177, +444] | -6 [-159, +543] | +0.9s [-0.5, +2.5] | undecided (indicative: under 30 pairs) |
| log | L | fold-bash-all (against bash-native) | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0002 [-0.0006, +0.0002] | +1188 [-138, +1534] | -43579 [-46204, +2106] | -1.5s [-4.3, +2.2] | undecided (indicative: under 30 pairs) |
| log | M | fold-bash (against bash-native) | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0012 [-0.0016, -0.0007] | -11008 [-11376, -9912] | +84742 [+36393, +85267] | +4.8s [+1.7, +7.6] | undecided (indicative: under 30 pairs) |
| log | M | fold-bash-all (against bash-native) | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0013 [-0.0017, -0.0009] | -11002 [-11608, -10343] | +38521 [+35955, +85781] | +5.0s [+4.1, +6.7] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| L | fold-bash (against bash-native) | 52 | -2% [-12%, +8%] | 2/3, p 1.00 | $-0.0000 [-0.0002, +0.0001] | +18 [-120, +304] | +8 [-219, +423] | +0.5s [-2.0, +1.6] | undecided |
| L | fold-bash-all (against bash-native) | 52 | +4% [-3%, +13%] | 2/0, p 0.50 | $-0.0001 [-0.0004, +0.0003] | +1498 [+972, +1980] | -20083 [-43518, +5424] | -1.6s [-3.8, +1.4] | fails |
| M | fold-bash (against bash-native) | 52 | -6% [-16%, +2%] | 0/3, p 0.25 | $-0.0008 [-0.0011, -0.0006] | -8090 [-8860, -7232] | +42332 [+40920, +85322] | +6.0s [+4.2, +7.2] | undecided |
| M | fold-bash-all (against bash-native) | 52 | -2% [-10%, +5%] | 0/1, p 1.00 | $-0.0007 [-0.0010, -0.0005] | -7826 [-8634, -6870] | +42724 [+41045, +90968] | +4.7s [+4.0, +6.0] | undecided |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

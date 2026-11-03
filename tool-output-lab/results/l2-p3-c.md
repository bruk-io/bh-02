# Layer 2: Claude Code on the eval tasks (claude-sonnet-5-5)

66 runs, $6.05; 66 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| pypi | count | L | native | 1/1 [21%, 100%] | $0.0722 | 44456 | 1 | 0/1 | 0/1 |
| pypi | count | L | noshell | 1/1 [21%, 100%] | $0.1128 | 45288 | 6 | 0/1 | 0/1 |
| pypi | count | L | noshell-fold | 1/1 [21%, 100%] | $0.1043 | 44809 | 5 | 0/1 | 0/1 |
| pypi | enumerate | L | native | 1/1 [21%, 100%] | $0.0744 | 44634 | 1 | 0/1 | 0/1 |
| pypi | enumerate | L | noshell | 1/1 [21%, 100%] | $0.1115 | 45561 | 6 | 0/1 | 0/1 |
| pypi | enumerate | L | noshell-fold | 1/1 [21%, 100%] | $0.1390 | 50864 | 6 | 0/1 | 0/1 |
| pypi | lookup | L | native | 1/1 [21%, 100%] | $0.0744 | 44627 | 1 | 0/1 | 0/1 |
| pypi | lookup | L | noshell | 1/1 [21%, 100%] | $0.1923 | 65749 | 6 | 0/1 | 0/1 |
| pypi | lookup | L | noshell-fold | 1/1 [21%, 100%] | $0.1043 | 44289 | 5 | 0/1 | 0/1 |
| python | count | L | native | 2/2 [34%, 100%] | $0.0769 | 44708 | 1.0 | 0/2 | 0/2 |
| python | count | L | noshell | 2/2 [34%, 100%] | $0.0924 | 45775 | 1.5 | 0/2 | 0/2 |
| python | count | L | noshell-fold | 2/2 [34%, 100%] | $0.0901 | 45790 | 1.5 | 0/2 | 0/2 |
| python | count | M | native | 1/1 [21%, 100%] | $0.0752 | 44542 | 1 | 0/1 | 0/1 |
| python | count | M | noshell | 1/1 [21%, 100%] | $0.0747 | 43247 | 1 | 0/1 | 0/1 |
| python | count | M | noshell-fold | 1/1 [21%, 100%] | $0.0718 | 43255 | 1 | 0/1 | 0/1 |
| python | enumerate | L | native | 3/3 [44%, 100%] | $0.0827 | 45249 | 1 | 0/3 | 0/3 |
| python | enumerate | L | noshell | 2/3 [21%, 94%] | $0.1933 | 45166 | 2 | 0/3 | 0/3 |
| python | enumerate | L | noshell-fold | 2/3 [21%, 94%] | $0.1876 | 43912 | 1 | 0/3 | 0/3 |
| python | locate | L | native | 3/3 [44%, 100%] | $0.0743 | 44480 | 1 | 0/3 | 0/3 |
| python | locate | L | noshell | 3/3 [44%, 100%] | $0.0740 | 43131 | 1 | 0/3 | 0/3 |
| python | locate | L | noshell-fold | 3/3 [44%, 100%] | $0.0739 | 43140 | 1 | 0/3 | 0/3 |
| python | locate | M | native | 1/1 [21%, 100%] | $0.0740 | 44472 | 1 | 0/1 | 0/1 |
| python | locate | M | noshell | 1/1 [21%, 100%] | $0.0737 | 43125 | 1 | 0/1 | 0/1 |
| python | locate | M | noshell-fold | 1/1 [21%, 100%] | $0.0738 | 43140 | 1 | 0/1 | 0/1 |
| rust | count | L | native | 2/2 [34%, 100%] | $0.0923 | 47691 | 1.5 | 0/2 | 0/2 |
| rust | count | L | noshell | 2/2 [34%, 100%] | $0.0971 | 47180 | 1.5 | 0/2 | 0/2 |
| rust | count | L | noshell-fold | 2/2 [34%, 100%] | $0.0919 | 46189 | 1.5 | 0/2 | 0/2 |
| rust | enumerate | L | native | 2/2 [34%, 100%] | $0.0892 | 47433 | 1.0 | 0/2 | 0/2 |
| rust | enumerate | L | noshell | 2/2 [34%, 100%] | $0.0893 | 46039 | 1.0 | 0/2 | 0/2 |
| rust | enumerate | L | noshell-fold | 2/2 [34%, 100%] | $0.0865 | 46045 | 1.0 | 0/2 | 0/2 |
| rust | locate | L | native | 2/2 [34%, 100%] | $0.0753 | 44633 | 1.0 | 0/2 | 0/2 |
| rust | locate | L | noshell | 2/2 [34%, 100%] | $0.0751 | 43282 | 1.0 | 0/2 | 0/2 |
| rust | locate | L | noshell-fold | 2/2 [34%, 100%] | $0.0738 | 43293 | 1.0 | 0/2 | 0/2 |
| xml | count | L | native | 1/1 [21%, 100%] | $0.0866 | 45511 | 2 | 0/1 | 0/1 |
| xml | count | L | noshell | 1/1 [21%, 100%] | $0.0829 | 43362 | 2 | 0/1 | 0/1 |
| xml | count | L | noshell-fold | 1/1 [21%, 100%] | $0.0870 | 44115 | 3 | 0/1 | 0/1 |
| xml | enumerate | L | native | 1/1 [21%, 100%] | $0.0747 | 44509 | 1 | 0/1 | 0/1 |
| xml | enumerate | L | noshell | 1/1 [21%, 100%] | $0.0750 | 43295 | 1 | 0/1 | 0/1 |
| xml | enumerate | L | noshell-fold | 1/1 [21%, 100%] | $0.0724 | 43307 | 1 | 0/1 | 0/1 |
| xml | lookup | L | native | 1/1 [21%, 100%] | $0.0745 | 44502 | 1 | 0/1 | 0/1 |
| xml | lookup | L | noshell | 1/1 [21%, 100%] | $0.0745 | 43232 | 1 | 0/1 | 0/1 |
| xml | lookup | L | noshell-fold | 1/1 [21%, 100%] | $0.0743 | 43160 | 1 | 0/1 | 0/1 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| pypi | L | noshell | 3 | +0% [-56%, +56%] | 0/0, p 1.00 | $+0.0406 [+0.0371, +0.1179] | +927 [+832, +21122] | +174468 [+174188, +214941] | +19.9s [+9.2, +27.4] | fails (indicative: under 30 pairs) |
| pypi | L | noshell-fold (against noshell) | 3 | +0% [-56%, +56%] | 0/0, p 1.00 | $-0.0086 [-0.0880, +0.0275] | -479 [-21460, +5303] | -42526 [-44823, +55099] | -13.6s [-21.8, +17.6] | undecided (indicative: under 30 pairs) |
| python | L | noshell | 8 | -12% [-47%, +22%] | 0/1, p 1.00 | $+0.0065 [+0.0010, +0.0670] | -526 [-1344, +544] | -2038 [-2692, +40975] | -0.8s [-5.1, +5.6] | undecided (indicative: under 30 pairs) |
| python | L | noshell-fold (against noshell) | 8 | +0% [-24%, +24%] | 0/0, p 1.00 | $-0.0018 [-0.0057, +0.0000] | +10 [-330, +20] | +20 [-1287, +31] | +2.5s [-2.7, +6.1] | undecided (indicative: under 30 pairs) |
| python | M | noshell | 2 | +0% [-66%, +66%] | 0/0, p 1.00 | $-0.0004 [-0.0004, -0.0003] | -1321 [-1347, -1295] | -2668 [-2694, -2641] | +1.6s [-0.8, +3.9] | undecided (indicative: under 30 pairs) |
| python | M | noshell-fold (against noshell) | 2 | +0% [-66%, +66%] | 0/0, p 1.00 | $-0.0015 [-0.0030, +0.0001] | +12 [+8, +15] | +23 [+16, +30] | -0.9s [-3.4, +1.6] | fails (indicative: under 30 pairs) |
| rust | L | noshell | 6 | +0% [-39%, +39%] | 0/0, p 1.00 | $-0.0001 [-0.0009, +0.0058] | -1350 [-1454, -452] | -2701 [-2796, -2530] | +3.4s [-4.2, +7.7] | undecided (indicative: under 30 pairs) |
| rust | L | noshell-fold (against noshell) | 6 | +0% [-39%, +39%] | 0/0, p 1.00 | $-0.0025 [-0.0070, +0.0002] | +9 [-998, +16] | +16 [-2426, +30] | -2.2s [-5.0, +9.3] | undecided (indicative: under 30 pairs) |
| xml | L | noshell | 3 | +0% [-56%, +56%] | 0/0, p 1.00 | $-0.0000 [-0.0037, +0.0003] | -1270 [-2149, -1214] | -2616 [-5203, -2562] | -5.9s [-8.4, -0.1] | undecided (indicative: under 30 pairs) |
| xml | L | noshell-fold (against noshell) | 3 | +0% [-56%, +56%] | 0/0, p 1.00 | $-0.0003 [-0.0026, +0.0041] | +12 [-72, +753] | +24 [-68, +922] | -1.1s [-2.4, +0.0] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| L | noshell | 20 | -5% [-24%, +12%] | 0/1, p 1.00 | $+0.0020 [-0.0001, +0.0166] | -1242 [-1346, +196] | -2644 [-2696, -1094] | +1.1s [-2.3, +5.1] | undecided (indicative: under 30 pairs) |
| L | noshell-fold (against noshell) | 20 | +0% [-15%, +15%] | 0/0, p 1.00 | $-0.0024 [-0.0036, -0.0000] | +10 [-36, +12] | +18 [-33, +28] | -0.5s [-2.8, +3.9] | undecided (indicative: under 30 pairs) |
| M | noshell | 2 | +0% [-66%, +66%] | 0/0, p 1.00 | $-0.0004 [-0.0004, -0.0003] | -1321 [-1347, -1295] | -2668 [-2694, -2641] | +1.6s [-0.8, +3.9] | undecided (indicative: under 30 pairs) |
| M | noshell-fold (against noshell) | 2 | +0% [-66%, +66%] | 0/0, p 1.00 | $-0.0015 [-0.0030, +0.0001] | +12 [+8, +15] | +23 [+16, +30] | -0.9s [-3.4, +1.6] | fails (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

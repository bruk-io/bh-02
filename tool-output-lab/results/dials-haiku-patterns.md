# Dials haiku-patterns: claude-haiku-5-5, the same tasks native and under each setting

## Band M (median input 6,502 tokens)

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | - | 100% | 58,042 | 148,933 | 28,892 | 120,034 | - | $0.0074 | 9.1s |
| schema | 52 | 52/52 | +0% [-7%, +7%], 0/0 | -9,115 [-10,439, -7,575] | +37,228 [+26,087, +49,304] | -9,320 [-10,672, -7,765] | +46,546 [+36,243, +57,910] | -11,073 ($-0.00011) | -18% ($-0.0014) | +2.2 [+1.5, +3.0]s |
| full | 52 | 52/52 | +0% [-7%, +7%], 0/0 | -9,852 [-10,953, -8,536] | +29,123 [+20,094, +39,750] | -10,118 [-11,247, -8,796] | +39,239 [+30,826, +49,197] | -10,742 ($-0.00011) | -22% ($-0.0016) | +1.9 [+1.2, +2.6]s |
| lean | 52 | 52/52 | -2% [-10%, +5%], 0/1 | -9,150 [-10,377, -7,735] | +42,288 [+31,929, +54,003] | -9,427 [-10,676, -7,981] | +51,714 [+41,691, +62,867] | -10,578 ($-0.00011) | -17% ($-0.0013) | +2.8 [+1.9, +3.8]s |
| index | 52 | 52/52 | +0% [-7%, +7%], 0/0 | -8,771 [-10,071, -7,267] | +40,413 [+27,500, +57,121] | -9,049 [-10,381, -7,545] | +49,460 [+37,129, +65,159] | -10,851 ($-0.00011) | -17% ($-0.0012) | +2.7 [+1.7, +4.0]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band L (median input 35,333 tokens)

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | - | 94% | 48,716 | 280,686 | 22,097 | 258,578 | - | $0.0079 | 17.9s |
| schema | 52 | 52/52 | +6% [-2%, +16%], 3/0 | -4,272 [-6,570, -2,483] | -84,785 [-105,814, -65,211] | -4,368 [-6,667, -2,590] | -80,414 [-100,828, -60,264] | -1,842 ($-0.00002) | -26% ($-0.0021) | -5.4 [-7.0, -3.8]s |
| full | 52 | 52/52 | +6% [-2%, +16%], 3/0 | -3,459 [-6,144, -1,159] | -86,610 [-107,485, -67,781] | -3,555 [-6,216, -1,247] | -83,051 [-104,107, -63,696] | -1,668 ($-0.00002) | -25% ($-0.0020) | -5.7 [-7.3, -4.3]s |
| lean | 52 | 52/52 | +6% [-2%, +16%], 3/0 | -2,724 [-4,583, -1,408] | -75,467 [-92,486, -58,512] | -2,821 [-4,666, -1,508] | -72,643 [-89,440, -55,844] | -1,592 ($-0.00002) | -21% ($-0.0017) | -4.6 [-6.1, -3.2]s |
| index | 52 | 52/52 | +6% [-2%, +16%], 3/0 | -3,176 [-5,008, -1,766] | -80,637 [-101,782, -57,046] | -3,272 [-5,117, -1,879] | -77,362 [-98,122, -53,924] | -1,422 ($-0.00001) | -23% ($-0.0018) | -5.2 [-6.9, -3.5]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 104 | - | 97% | 56,570 | 214,810 | 25,495 | 189,306 | - | $0.0076 | 13.5s |
| schema | 104 | 104/104 | +3% [-1%, +8%], 3/0 | -6,693 [-8,040, -5,404] | -23,779 [-39,880, -7,116] | -6,844 [-8,196, -5,560] | -16,934 [-33,146, -181] | -6,758 ($-0.00007) | -23% ($-0.0017) | -1.6 [-2.7, -0.4]s |
| full | 104 | 104/104 | +3% [-1%, +8%], 3/0 | -6,656 [-8,151, -5,206] | -28,743 [-44,230, -12,972] | -6,836 [-8,349, -5,374] | -21,906 [-38,149, -5,932] | -8,540 ($-0.00009) | -23% ($-0.0018) | -1.9 [-3.1, -0.8]s |
| lean | 104 | 104/104 | +2% [-3%, +7%], 3/1 | -5,937 [-7,286, -4,770] | -16,589 [-32,344, -1,086] | -6,124 [-7,472, -4,944] | -10,465 [-26,476, +5,332] | -3,582 ($-0.00004) | -19% ($-0.0015) | -0.9 [-2.1, +0.2]s |
| index | 104 | 104/104 | +3% [-1%, +8%], 3/0 | -5,973 [-7,262, -4,748] | -20,112 [-37,490, -2,705] | -6,161 [-7,433, -4,928] | -13,951 [-31,557, +3,991] | -5,008 ($-0.00005) | -20% ($-0.0015) | -1.3 [-2.5, +0.0]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Only the pairs where the envelope acted

| setting | pairs | acted | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 104 | - | 97% | 56,570 | 214,810 | 25,495 | 189,306 | - | $0.0076 | 13.5s |
| schema | 104 | 104/104 | +3% [-1%, +8%], 3/0 | -6,693 [-8,040, -5,404] | -23,779 [-39,880, -7,116] | -6,844 [-8,196, -5,560] | -16,934 [-33,146, -181] | -6,758 ($-0.00007) | -23% ($-0.0017) | -1.6 [-2.7, -0.4]s |
| full | 104 | 104/104 | +3% [-1%, +8%], 3/0 | -6,656 [-8,151, -5,206] | -28,743 [-44,230, -12,972] | -6,836 [-8,349, -5,374] | -21,906 [-38,149, -5,932] | -8,540 ($-0.00009) | -23% ($-0.0018) | -1.9 [-3.1, -0.8]s |
| lean | 104 | 104/104 | +2% [-3%, +7%], 3/1 | -5,937 [-7,286, -4,770] | -16,589 [-32,344, -1,086] | -6,124 [-7,472, -4,944] | -10,465 [-26,476, +5,332] | -3,582 ($-0.00004) | -19% ($-0.0015) | -0.9 [-2.1, +0.2]s |
| index | 104 | 104/104 | +3% [-1%, +8%], 3/0 | -5,973 [-7,262, -4,748] | -20,112 [-37,490, -2,705] | -6,161 [-7,433, -4,928] | -13,951 [-31,557, +3,991] | -5,008 ($-0.00005) | -20% ($-0.0015) | -1.3 [-2.5, +0.0]s |

Acted: the setting's runs whose hook folded the task's large output (matched by digest). Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

520 runs, $3.29; 520 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | M | full | 1/1 [21%, 100%] | $0.0081 | 58724 | 2 | 1/1 | 0/1 |
| a11y | absent | M | index | 1/1 [21%, 100%] | $0.0094 | 58945 | 3 | 1/1 | 0/1 |
| a11y | absent | M | lean | 1/1 [21%, 100%] | $0.0081 | 58602 | 2 | 1/1 | 0/1 |
| a11y | absent | M | native | 1/1 [21%, 100%] | $0.0073 | 56570 | 1 | 0/1 | 0/1 |
| a11y | absent | M | schema | 1/1 [21%, 100%] | $0.0077 | 57378 | 2 | 1/1 | 0/1 |
| a11y | absent | L | full | 1/1 [21%, 100%] | $0.0138 | 87832 | 2 | 1/1 | 0/1 |
| a11y | absent | L | index | 1/1 [21%, 100%] | $0.0085 | 52756 | 4 | 1/1 | 0/1 |
| a11y | absent | L | lean | 1/1 [21%, 100%] | $0.0097 | 56975 | 4 | 1/1 | 0/1 |
| a11y | absent | L | native | 1/1 [21%, 100%] | $0.0111 | 59653 | 6 | 1/1 | 0/1 |
| a11y | absent | L | schema | 1/1 [21%, 100%] | $0.0069 | 48608 | 3 | 1/1 | 0/1 |
| a11y | count | M | full | 4/4 [51%, 100%] | $0.0056 | 47255 | 2.0 | 4/4 | 0/4 |
| a11y | count | M | index | 4/4 [51%, 100%] | $0.0056 | 47440 | 2.0 | 4/4 | 0/4 |
| a11y | count | M | lean | 4/4 [51%, 100%] | $0.0056 | 47231 | 2.0 | 3/4 | 0/4 |
| a11y | count | M | native | 4/4 [51%, 100%] | $0.0071 | 56599 | 1.0 | 0/4 | 0/4 |
| a11y | count | M | schema | 4/4 [51%, 100%] | $0.0055 | 47068 | 2.0 | 4/4 | 0/4 |
| a11y | count | L | full | 4/4 [51%, 100%] | $0.0056 | 47252 | 2.0 | 4/4 | 0/4 |
| a11y | count | L | index | 4/4 [51%, 100%] | $0.0056 | 47453 | 2.0 | 4/4 | 0/4 |
| a11y | count | L | lean | 4/4 [51%, 100%] | $0.0055 | 47134 | 2.0 | 4/4 | 0/4 |
| a11y | count | L | native | 4/4 [51%, 100%] | $0.0084 | 55803 | 5.0 | 4/4 | 0/4 |
| a11y | count | L | schema | 4/4 [51%, 100%] | $0.0056 | 47132 | 2.0 | 4/4 | 0/4 |
| a11y | enumerate | M | full | 2/2 [34%, 100%] | $0.0049 | 46674 | 1.0 | 0/2 | 0/2 |
| a11y | enumerate | M | index | 2/2 [34%, 100%] | $0.0057 | 47634 | 2.0 | 2/2 | 0/2 |
| a11y | enumerate | M | lean | 2/2 [34%, 100%] | $0.0052 | 46896 | 1.5 | 1/2 | 0/2 |
| a11y | enumerate | M | native | 2/2 [34%, 100%] | $0.0070 | 56589 | 1.0 | 0/2 | 0/2 |
| a11y | enumerate | M | schema | 2/2 [34%, 100%] | $0.0052 | 46865 | 1.5 | 1/2 | 0/2 |
| a11y | enumerate | L | full | 2/2 [34%, 100%] | $0.0056 | 47341 | 2.0 | 2/2 | 0/2 |
| a11y | enumerate | L | index | 2/2 [34%, 100%] | $0.0053 | 47145 | 1.5 | 1/2 | 0/2 |
| a11y | enumerate | L | lean | 2/2 [34%, 100%] | $0.0049 | 46569 | 1.0 | 0/2 | 0/2 |
| a11y | enumerate | L | native | 2/2 [34%, 100%] | $0.0073 | 49008 | 5.0 | 2/2 | 0/2 |
| a11y | enumerate | L | schema | 2/2 [34%, 100%] | $0.0052 | 46877 | 1.5 | 1/2 | 0/2 |
| a11y | lookup | M | full | 2/2 [34%, 100%] | $0.0053 | 46600 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | M | index | 2/2 [34%, 100%] | $0.0060 | 49561 | 2.5 | 2/2 | 0/2 |
| a11y | lookup | M | lean | 2/2 [34%, 100%] | $0.0065 | 51711 | 3.0 | 2/2 | 0/2 |
| a11y | lookup | M | native | 2/2 [34%, 100%] | $0.0069 | 56564 | 1.0 | 0/2 | 0/2 |
| a11y | lookup | M | schema | 2/2 [34%, 100%] | $0.0064 | 48865 | 3.0 | 2/2 | 0/2 |
| a11y | lookup | L | full | 2/2 [34%, 100%] | $0.0054 | 46695 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | index | 2/2 [34%, 100%] | $0.0057 | 46982 | 2.5 | 2/2 | 0/2 |
| a11y | lookup | L | lean | 2/2 [34%, 100%] | $0.0057 | 46873 | 2.5 | 2/2 | 0/2 |
| a11y | lookup | L | native | 2/2 [34%, 100%] | $0.0059 | 48147 | 2.5 | 2/2 | 0/2 |
| a11y | lookup | L | schema | 2/2 [34%, 100%] | $0.0057 | 46995 | 2.5 | 2/2 | 0/2 |
| a11y | spot | M | full | 4/4 [51%, 100%] | $0.0056 | 46995 | 2.0 | 4/4 | 0/4 |
| a11y | spot | M | index | 4/4 [51%, 100%] | $0.0066 | 52657 | 2.0 | 4/4 | 0/4 |
| a11y | spot | M | lean | 4/4 [51%, 100%] | $0.0068 | 49090 | 2.0 | 4/4 | 0/4 |
| a11y | spot | M | native | 4/4 [51%, 100%] | $0.0068 | 56564 | 1.0 | 0/4 | 0/4 |
| a11y | spot | M | schema | 4/4 [51%, 100%] | $0.0058 | 47348 | 2.0 | 4/4 | 0/4 |
| a11y | spot | L | full | 4/4 [51%, 100%] | $0.0055 | 46826 | 2.0 | 4/4 | 0/4 |
| a11y | spot | L | index | 4/4 [51%, 100%] | $0.0057 | 47262 | 2.0 | 4/4 | 0/4 |
| a11y | spot | L | lean | 4/4 [51%, 100%] | $0.0056 | 47167 | 2.0 | 4/4 | 0/4 |
| a11y | spot | L | native | 2/4 [15%, 85%] | $0.0134 | 72966 | 7.5 | 4/4 | 0/4 |
| a11y | spot | L | schema | 4/4 [51%, 100%] | $0.0056 | 47013 | 2.0 | 4/4 | 0/4 |
| figma | absent | M | full | 1/1 [21%, 100%] | $0.0090 | 59412 | 3 | 1/1 | 0/1 |
| figma | absent | M | index | 1/1 [21%, 100%] | $0.0120 | 53972 | 8 | 1/1 | 0/1 |
| figma | absent | M | lean | 1/1 [21%, 100%] | $0.0090 | 59360 | 3 | 1/1 | 0/1 |
| figma | absent | M | native | 1/1 [21%, 100%] | $0.0073 | 57612 | 1 | 0/1 | 0/1 |
| figma | absent | M | schema | 1/1 [21%, 100%] | $0.0091 | 59466 | 3 | 1/1 | 0/1 |
| figma | absent | L | full | 1/1 [21%, 100%] | $0.0100 | 53192 | 7 | 1/1 | 0/1 |
| figma | absent | L | index | 1/1 [21%, 100%] | $0.0100 | 52829 | 6 | 1/1 | 0/1 |
| figma | absent | L | lean | 1/1 [21%, 100%] | $0.0106 | 63618 | 4 | 1/1 | 0/1 |
| figma | absent | L | native | 1/1 [21%, 100%] | $0.0109 | 60388 | 5 | 1/1 | 0/1 |
| figma | absent | L | schema | 1/1 [21%, 100%] | $0.0088 | 51183 | 5 | 1/1 | 0/1 |
| figma | count | M | full | 4/4 [51%, 100%] | $0.0065 | 48070 | 2.5 | 4/4 | 0/4 |
| figma | count | M | index | 4/4 [51%, 100%] | $0.0068 | 49029 | 3.0 | 2/4 | 0/4 |
| figma | count | M | lean | 4/4 [51%, 100%] | $0.0064 | 47782 | 3.0 | 4/4 | 0/4 |
| figma | count | M | native | 4/4 [51%, 100%] | $0.0076 | 57724 | 1.0 | 0/4 | 0/4 |
| figma | count | M | schema | 4/4 [51%, 100%] | $0.0073 | 53534 | 2.5 | 3/4 | 0/4 |
| figma | count | L | full | 4/4 [51%, 100%] | $0.0066 | 48583 | 3.0 | 3/4 | 0/4 |
| figma | count | L | index | 4/4 [51%, 100%] | $0.0066 | 48807 | 3.0 | 4/4 | 0/4 |
| figma | count | L | lean | 4/4 [51%, 100%] | $0.0066 | 48563 | 3.0 | 4/4 | 0/4 |
| figma | count | L | native | 4/4 [51%, 100%] | $0.0079 | 49585 | 5.5 | 4/4 | 0/4 |
| figma | count | L | schema | 4/4 [51%, 100%] | $0.0065 | 48092 | 3.0 | 4/4 | 0/4 |
| figma | enumerate | M | full | 2/2 [34%, 100%] | $0.0071 | 53321 | 2.0 | 1/2 | 0/2 |
| figma | enumerate | M | index | 2/2 [34%, 100%] | $0.0076 | 54193 | 2.5 | 2/2 | 0/2 |
| figma | enumerate | M | lean | 2/2 [34%, 100%] | $0.0066 | 52835 | 1.5 | 1/2 | 0/2 |
| figma | enumerate | M | native | 2/2 [34%, 100%] | $0.0074 | 57735 | 1.0 | 0/2 | 0/2 |
| figma | enumerate | M | schema | 2/2 [34%, 100%] | $0.0082 | 55441 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | L | full | 2/2 [34%, 100%] | $0.0068 | 48533 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | L | index | 2/2 [34%, 100%] | $0.0067 | 48653 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | L | lean | 2/2 [34%, 100%] | $0.0063 | 48401 | 2.5 | 2/2 | 0/2 |
| figma | enumerate | L | native | 2/2 [34%, 100%] | $0.0079 | 49615 | 5.5 | 2/2 | 0/2 |
| figma | enumerate | L | schema | 2/2 [34%, 100%] | $0.0067 | 48688 | 3.0 | 2/2 | 0/2 |
| figma | lookup | M | full | 2/2 [34%, 100%] | $0.0061 | 47005 | 3.5 | 2/2 | 0/2 |
| figma | lookup | M | index | 2/2 [34%, 100%] | $0.0072 | 52735 | 3.0 | 2/2 | 0/2 |
| figma | lookup | M | lean | 2/2 [34%, 100%] | $0.0066 | 47024 | 4.0 | 2/2 | 0/2 |
| figma | lookup | M | native | 2/2 [34%, 100%] | $0.0071 | 57602 | 1.0 | 0/2 | 0/2 |
| figma | lookup | M | schema | 2/2 [34%, 100%] | $0.0067 | 47073 | 4.0 | 2/2 | 0/2 |
| figma | lookup | L | full | 2/2 [34%, 100%] | $0.0060 | 46900 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | index | 2/2 [34%, 100%] | $0.0060 | 46858 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | lean | 2/2 [34%, 100%] | $0.0061 | 46898 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | native | 2/2 [34%, 100%] | $0.0061 | 46958 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | schema | 2/2 [34%, 100%] | $0.0064 | 47005 | 3.5 | 2/2 | 0/2 |
| figma | spot | M | full | 4/4 [51%, 100%] | $0.0067 | 48419 | 2.5 | 4/4 | 0/4 |
| figma | spot | M | index | 4/4 [51%, 100%] | $0.0080 | 58884 | 2.0 | 4/4 | 0/4 |
| figma | spot | M | lean | 4/4 [51%, 100%] | $0.0080 | 58541 | 2.0 | 4/4 | 0/4 |
| figma | spot | M | native | 4/4 [51%, 100%] | $0.0071 | 57634 | 1.0 | 0/4 | 0/4 |
| figma | spot | M | schema | 4/4 [51%, 100%] | $0.0079 | 58646 | 2.0 | 4/4 | 0/4 |
| figma | spot | L | full | 4/4 [51%, 100%] | $0.0070 | 48536 | 3.5 | 4/4 | 0/4 |
| figma | spot | L | index | 4/4 [51%, 100%] | $0.0067 | 48798 | 3.0 | 3/4 | 0/4 |
| figma | spot | L | lean | 4/4 [51%, 100%] | $0.0082 | 50632 | 3.5 | 4/4 | 0/4 |
| figma | spot | L | native | 3/4 [30%, 95%] | $0.0106 | 54094 | 6.0 | 4/4 | 0/4 |
| figma | spot | L | schema | 4/4 [51%, 100%] | $0.0068 | 48634 | 3.0 | 4/4 | 0/4 |
| json | absent | M | full | 1/1 [21%, 100%] | $0.0059 | 47877 | 2 | 1/1 | 0/1 |
| json | absent | M | index | 1/1 [21%, 100%] | $0.0057 | 47030 | 2 | 1/1 | 0/1 |
| json | absent | M | lean | 0/1 [0%, 79%] | $0.0063 | 49053 | 2 | 1/1 | 0/1 |
| json | absent | M | native | 1/1 [21%, 100%] | $0.0072 | 58334 | 1 | 0/1 | 0/1 |
| json | absent | M | schema | 1/1 [21%, 100%] | $0.0049 | 46133 | 1 | 0/1 | 0/1 |
| json | absent | L | full | 1/1 [21%, 100%] | $0.0048 | 46233 | 1 | 0/1 | 0/1 |
| json | absent | L | index | 1/1 [21%, 100%] | $0.0056 | 46977 | 2 | 1/1 | 0/1 |
| json | absent | L | lean | 1/1 [21%, 100%] | $0.0071 | 49722 | 3 | 1/1 | 0/1 |
| json | absent | L | native | 1/1 [21%, 100%] | $0.0073 | 48622 | 4 | 1/1 | 0/1 |
| json | absent | L | schema | 1/1 [21%, 100%] | $0.0055 | 46723 | 2 | 1/1 | 0/1 |
| json | count | M | full | 4/4 [51%, 100%] | $0.0048 | 46359 | 1.0 | 0/4 | 0/4 |
| json | count | M | index | 4/4 [51%, 100%] | $0.0048 | 46562 | 1.0 | 1/4 | 0/4 |
| json | count | M | lean | 4/4 [51%, 100%] | $0.0050 | 46273 | 1.5 | 2/4 | 0/4 |
| json | count | M | native | 4/4 [51%, 100%] | $0.0073 | 58458 | 1.0 | 0/4 | 0/4 |
| json | count | M | schema | 4/4 [51%, 100%] | $0.0048 | 46413 | 1.0 | 1/4 | 0/4 |
| json | count | L | full | 4/4 [51%, 100%] | $0.0056 | 47258 | 2.0 | 3/4 | 0/4 |
| json | count | L | index | 4/4 [51%, 100%] | $0.0050 | 47160 | 1.0 | 1/4 | 0/4 |
| json | count | L | lean | 4/4 [51%, 100%] | $0.0048 | 46519 | 1.0 | 0/4 | 0/4 |
| json | count | L | native | 4/4 [51%, 100%] | $0.0065 | 48330 | 3.0 | 4/4 | 0/4 |
| json | count | L | schema | 4/4 [51%, 100%] | $0.0054 | 47045 | 2.0 | 3/4 | 0/4 |
| json | enumerate | M | full | 2/2 [34%, 100%] | $0.0055 | 46915 | 2.0 | 2/2 | 0/2 |
| json | enumerate | M | index | 2/2 [34%, 100%] | $0.0052 | 46799 | 1.5 | 1/2 | 0/2 |
| json | enumerate | M | lean | 2/2 [34%, 100%] | $0.0055 | 46656 | 2.0 | 2/2 | 0/2 |
| json | enumerate | M | native | 2/2 [34%, 100%] | $0.0075 | 58442 | 1.0 | 0/2 | 0/2 |
| json | enumerate | M | schema | 2/2 [34%, 100%] | $0.0052 | 46471 | 1.5 | 1/2 | 0/2 |
| json | enumerate | L | full | 2/2 [34%, 100%] | $0.0053 | 46927 | 1.5 | 1/2 | 0/2 |
| json | enumerate | L | index | 2/2 [34%, 100%] | $0.0057 | 47647 | 2.0 | 2/2 | 0/2 |
| json | enumerate | L | lean | 2/2 [34%, 100%] | $0.0048 | 46468 | 1.0 | 0/2 | 0/2 |
| json | enumerate | L | native | 2/2 [34%, 100%] | $0.0069 | 48499 | 3.5 | 2/2 | 0/2 |
| json | enumerate | L | schema | 2/2 [34%, 100%] | $0.0053 | 46873 | 1.5 | 1/2 | 0/2 |
| json | lookup | M | full | 2/2 [34%, 100%] | $0.0053 | 46533 | 2.0 | 2/2 | 0/2 |
| json | lookup | M | index | 2/2 [34%, 100%] | $0.0053 | 46627 | 2.0 | 2/2 | 0/2 |
| json | lookup | M | lean | 2/2 [34%, 100%] | $0.0053 | 46332 | 2.0 | 2/2 | 0/2 |
| json | lookup | M | native | 2/2 [34%, 100%] | $0.0072 | 58332 | 1.0 | 0/2 | 0/2 |
| json | lookup | M | schema | 2/2 [34%, 100%] | $0.0053 | 46457 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | full | 2/2 [34%, 100%] | $0.0053 | 46505 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | index | 2/2 [34%, 100%] | $0.0053 | 46534 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | lean | 2/2 [34%, 100%] | $0.0053 | 46302 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | native | 2/2 [34%, 100%] | $0.0062 | 47013 | 3.0 | 2/2 | 0/2 |
| json | lookup | L | schema | 2/2 [34%, 100%] | $0.0053 | 46422 | 2.0 | 2/2 | 0/2 |
| json | spot | M | full | 4/4 [51%, 100%] | $0.0048 | 46369 | 1.0 | 0/4 | 0/4 |
| json | spot | M | index | 4/4 [51%, 100%] | $0.0051 | 46576 | 1.0 | 1/4 | 0/4 |
| json | spot | M | lean | 4/4 [51%, 100%] | $0.0050 | 46130 | 1.0 | 1/4 | 0/4 |
| json | spot | M | native | 4/4 [51%, 100%] | $0.0074 | 58342 | 1.0 | 0/4 | 0/4 |
| json | spot | M | schema | 4/4 [51%, 100%] | $0.0050 | 46483 | 1.5 | 2/4 | 0/4 |
| json | spot | L | full | 4/4 [51%, 100%] | $0.0048 | 46354 | 1.0 | 0/4 | 0/4 |
| json | spot | L | index | 4/4 [51%, 100%] | $0.0051 | 46776 | 1.5 | 2/4 | 0/4 |
| json | spot | L | lean | 4/4 [51%, 100%] | $0.0054 | 46692 | 2.0 | 4/4 | 0/4 |
| json | spot | L | native | 4/4 [51%, 100%] | $0.0071 | 48374 | 4.0 | 4/4 | 0/4 |
| json | spot | L | schema | 4/4 [51%, 100%] | $0.0047 | 46216 | 1.0 | 1/4 | 0/4 |
| log | absent | M | full | 1/1 [21%, 100%] | $0.0055 | 46703 | 2 | 1/1 | 0/1 |
| log | absent | M | index | 1/1 [21%, 100%] | $0.0065 | 48288 | 3 | 1/1 | 0/1 |
| log | absent | M | lean | 1/1 [21%, 100%] | $0.0087 | 58770 | 3 | 1/1 | 0/1 |
| log | absent | M | native | 1/1 [21%, 100%] | $0.0077 | 60297 | 1 | 0/1 | 0/1 |
| log | absent | M | schema | 1/1 [21%, 100%] | $0.0065 | 47753 | 3 | 1/1 | 0/1 |
| log | absent | L | full | 1/1 [21%, 100%] | $0.0063 | 47170 | 3 | 1/1 | 0/1 |
| log | absent | L | index | 1/1 [21%, 100%] | $0.0071 | 47867 | 4 | 1/1 | 0/1 |
| log | absent | L | lean | 1/1 [21%, 100%] | $0.0067 | 48519 | 3 | 1/1 | 0/1 |
| log | absent | L | native | 1/1 [21%, 100%] | $0.0076 | 48864 | 5 | 1/1 | 0/1 |
| log | absent | L | schema | 1/1 [21%, 100%] | $0.0065 | 47790 | 3 | 1/1 | 0/1 |
| log | count | M | full | 4/4 [51%, 100%] | $0.0049 | 46849 | 1.0 | 0/4 | 0/4 |
| log | count | M | index | 4/4 [51%, 100%] | $0.0052 | 46914 | 1.5 | 2/4 | 0/4 |
| log | count | M | lean | 4/4 [51%, 100%] | $0.0055 | 46930 | 2.0 | 4/4 | 0/4 |
| log | count | M | native | 4/4 [51%, 100%] | $0.0077 | 60284 | 1.0 | 0/4 | 0/4 |
| log | count | M | schema | 4/4 [51%, 100%] | $0.0049 | 46750 | 1.0 | 0/4 | 0/4 |
| log | count | L | full | 4/4 [51%, 100%] | $0.0049 | 47031 | 1.0 | 1/4 | 0/4 |
| log | count | L | index | 4/4 [51%, 100%] | $0.0049 | 47037 | 1.0 | 1/4 | 0/4 |
| log | count | L | lean | 4/4 [51%, 100%] | $0.0055 | 46926 | 2.0 | 4/4 | 0/4 |
| log | count | L | native | 4/4 [51%, 100%] | $0.0064 | 47885 | 4.0 | 4/4 | 0/4 |
| log | count | L | schema | 4/4 [51%, 100%] | $0.0048 | 46702 | 1.0 | 0/4 | 0/4 |
| log | enumerate | M | full | 2/2 [34%, 100%] | $0.0050 | 46802 | 1.0 | 0/2 | 0/2 |
| log | enumerate | M | index | 2/2 [34%, 100%] | $0.0050 | 46823 | 1.0 | 0/2 | 0/2 |
| log | enumerate | M | lean | 2/2 [34%, 100%] | $0.0053 | 46738 | 1.5 | 1/2 | 0/2 |
| log | enumerate | M | native | 2/2 [34%, 100%] | $0.0078 | 60371 | 1.0 | 0/2 | 0/2 |
| log | enumerate | M | schema | 2/2 [34%, 100%] | $0.0049 | 46657 | 1.0 | 0/2 | 0/2 |
| log | enumerate | L | full | 2/2 [34%, 100%] | $0.0053 | 47138 | 1.5 | 1/2 | 0/2 |
| log | enumerate | L | index | 2/2 [34%, 100%] | $0.0051 | 46777 | 1.0 | 0/2 | 0/2 |
| log | enumerate | L | lean | 2/2 [34%, 100%] | $0.0059 | 47166 | 2.5 | 2/2 | 0/2 |
| log | enumerate | L | native | 2/2 [34%, 100%] | $0.0062 | 47137 | 3.0 | 2/2 | 0/2 |
| log | enumerate | L | schema | 2/2 [34%, 100%] | $0.0050 | 46638 | 1.0 | 0/2 | 0/2 |
| log | lookup | M | full | 2/2 [34%, 100%] | $0.0053 | 46521 | 2.0 | 2/2 | 0/2 |
| log | lookup | M | index | 2/2 [34%, 100%] | $0.0053 | 46522 | 2.0 | 2/2 | 0/2 |
| log | lookup | M | lean | 2/2 [34%, 100%] | $0.0054 | 46413 | 2.0 | 2/2 | 0/2 |
| log | lookup | M | native | 2/2 [34%, 100%] | $0.0077 | 60281 | 1.0 | 0/2 | 0/2 |
| log | lookup | M | schema | 2/2 [34%, 100%] | $0.0054 | 46403 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | full | 2/2 [34%, 100%] | $0.0053 | 46510 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | index | 2/2 [34%, 100%] | $0.0053 | 46498 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | lean | 2/2 [34%, 100%] | $0.0053 | 46197 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | native | 2/2 [34%, 100%] | $0.0055 | 46419 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | schema | 2/2 [34%, 100%] | $0.0054 | 46440 | 2.0 | 2/2 | 0/2 |
| log | spot | M | full | 4/4 [51%, 100%] | $0.0057 | 47233 | 2.0 | 4/4 | 0/4 |
| log | spot | M | index | 4/4 [51%, 100%] | $0.0053 | 46928 | 1.5 | 2/4 | 0/4 |
| log | spot | M | lean | 4/4 [51%, 100%] | $0.0056 | 46950 | 2.0 | 4/4 | 0/4 |
| log | spot | M | native | 4/4 [51%, 100%] | $0.0077 | 60298 | 1.0 | 0/4 | 0/4 |
| log | spot | M | schema | 4/4 [51%, 100%] | $0.0056 | 47029 | 2.0 | 3/4 | 0/4 |
| log | spot | L | full | 4/4 [51%, 100%] | $0.0056 | 46985 | 2.0 | 4/4 | 0/4 |
| log | spot | L | index | 4/4 [51%, 100%] | $0.0057 | 47545 | 2.0 | 4/4 | 0/4 |
| log | spot | L | lean | 4/4 [51%, 100%] | $0.0059 | 46897 | 2.5 | 4/4 | 0/4 |
| log | spot | L | native | 4/4 [51%, 100%] | $0.0078 | 50382 | 5.5 | 4/4 | 0/4 |
| log | spot | L | schema | 4/4 [51%, 100%] | $0.0055 | 46903 | 2.0 | 3/4 | 0/4 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | M | full | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0014 [-0.0016, -0.0013] | -9660 [-9759, -9119] | +36707 [+36229, +37729] | +1.2s [+0.8, +3.5] | undecided (indicative: under 30 pairs) |
| a11y | M | index | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0013 [-0.0014, -0.0002] | -8637 [-9407, -4404] | +38156 [+37167, +41732] | +2.5s [+1.6, +3.5] | undecided (indicative: under 30 pairs) |
| a11y | M | lean | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0012 [-0.0014, -0.0002] | -9057 [-9519, -5446] | +38071 [+36749, +41842] | +2.3s [+1.4, +3.4] | undecided (indicative: under 30 pairs) |
| a11y | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0013 [-0.0014, -0.0009] | -9473 [-9662, -8960] | +37273 [+36760, +46908] | +3.3s [+0.8, +3.5] | undecided (indicative: under 30 pairs) |
| a11y | L | full | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $-0.0026 [-0.0050, -0.0008] | -6889 [-9714, -1649] | -96835 [-119040, -2418] | -5.1s [-7.5, -2.0] | undecided (indicative: under 30 pairs) |
| a11y | L | index | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $-0.0024 [-0.0035, -0.0002] | -6877 [-8137, -1586] | -77539 [-118735, +126] | -5.3s [-6.6, -1.8] | undecided (indicative: under 30 pairs) |
| a11y | L | lean | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $-0.0024 [-0.0036, -0.0012] | -2678 [-8442, -2323] | -71532 [-144109, -41174] | -4.7s [-7.6, -3.3] | undecided (indicative: under 30 pairs) |
| a11y | L | schema | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $-0.0032 [-0.0050, -0.0017] | -8149 [-10288, -2211] | -97140 [-136893, -69] | -4.0s [-7.1, -1.5] | undecided (indicative: under 30 pairs) |
| figma | M | full | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0006 [-0.0013, +0.0009] | -9483 [-10198, +1422] | +83867 [+36867, +86015] | +5.4s [+3.3, +5.9] | undecided (indicative: under 30 pairs) |
| figma | M | index | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $+0.0006 [-0.0007, +0.0010] | -3640 [-8811, +1380] | +86146 [+47849, +87575] | +5.5s [+3.4, +6.0] | undecided (indicative: under 30 pairs) |
| figma | M | lean | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0005 [-0.0012, +0.0007] | -9936 [-10079, +918] | +83156 [+47224, +85250] | +3.2s [+2.4, +5.6] | undecided (indicative: under 30 pairs) |
| figma | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $+0.0008 [-0.0004, +0.0009] | +979 [-9556, +1221] | +85412 [+47509, +107301] | +3.6s [+2.8, +6.5] | undecided (indicative: under 30 pairs) |
| figma | L | full | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0013 [-0.0018, -0.0005] | -1996 [-2585, -71] | -53876 [-102686, -71] | -2.8s [-7.5, -1.7] | undecided (indicative: under 30 pairs) |
| figma | L | index | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0018 [-0.0026, -0.0006] | -1840 [-3634, +54] | -97153 [-151252, -322] | -4.1s [-9.4, -2.2] | undecided (indicative: under 30 pairs) |
| figma | L | lean | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0010 [-0.0019, -0.0003] | -1184 [-2741, +312] | -51869 [-103219, -19021] | -4.4s [-7.0, +1.4] | undecided (indicative: under 30 pairs) |
| figma | L | schema | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0019 [-0.0021, -0.0006] | -1983 [-2975, -196] | -97354 [-103001, -28383] | -5.6s [-6.4, -0.7] | undecided (indicative: under 30 pairs) |
| json | M | full | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0024 [-0.0025, -0.0019] | -11931 [-11980, -11767] | -11926 [-11980, +34481] | +0.4s [+0.1, +2.7] | undecided (indicative: under 30 pairs) |
| json | M | index | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0024 [-0.0025, -0.0019] | -11704 [-11775, -11627] | -11640 [-11769, +34818] | +0.6s [+0.0, +2.3] | undecided (indicative: under 30 pairs) |
| json | M | lean | 13 | -8% [-33%, +16%] | 0/1, p 1.00 | $-0.0020 [-0.0026, -0.0019] | -12034 [-12231, -11812] | +33932 [-12195, +34223] | +2.0s [-0.8, +2.9] | undecided (indicative: under 30 pairs) |
| json | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0024 [-0.0024, -0.0020] | -11962 [-12103, -11893] | -11920 [-12105, +34219] | +0.5s [+0.2, +2.2] | undecided (indicative: under 30 pairs) |
| json | L | full | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0017 [-0.0023, -0.0009] | -1650 [-1904, -958] | -95451 [-142930, -47177] | -5.5s [-8.6, -4.0] | undecided (indicative: under 30 pairs) |
| json | L | index | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0016 [-0.0017, -0.0010] | -1199 [-1484, -1113] | -94704 [-96237, -48105] | -5.8s [-7.4, -4.1] | undecided (indicative: under 30 pairs) |
| json | L | lean | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0017 [-0.0017, -0.0016] | -1690 [-1921, -1567] | -95256 [-96518, -94722] | -4.9s [-7.4, -4.0] | undecided (indicative: under 30 pairs) |
| json | L | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0016 [-0.0023, -0.0010] | -1537 [-1993, -1212] | -94601 [-142931, -47490] | -5.2s [-8.7, -3.3] | undecided (indicative: under 30 pairs) |
| log | M | full | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0024 [-0.0028, -0.0022] | -13423 [-13715, -13116] | +32459 [-13438, +33025] | +0.5s [-0.8, +1.9] | undecided (indicative: under 30 pairs) |
| log | M | index | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0024 [-0.0028, -0.0021] | -13459 [-13723, -12802] | +32445 [-13511, +33602] | +1.0s [+0.1, +1.6] | undecided (indicative: under 30 pairs) |
| log | M | lean | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0022 [-0.0023, -0.0020] | -13480 [-13775, -12895] | +32783 [+32266, +33399] | +2.4s [+1.4, +4.0] | undecided (indicative: under 30 pairs) |
| log | M | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0027 [-0.0028, -0.0023] | -13616 [-13903, -13048] | -13039 [-13608, +32559] | +0.8s [-0.8, +2.0] | undecided (indicative: under 30 pairs) |
| log | L | full | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0013 [-0.0019, -0.0007] | -690 [-1694, +70] | -93510 [-98556, -46320] | -4.9s [-5.9, -2.8] | undecided (indicative: under 30 pairs) |
| log | L | index | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0012 [-0.0021, -0.0007] | -937 [-1826, -310] | -93535 [-99004, -46370] | -5.1s [-6.3, -1.3] | undecided (indicative: under 30 pairs) |
| log | L | lean | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0008 [-0.0015, -0.0002] | -345 [-1465, -263] | -47653 [-53765, -509] | -3.0s [-4.2, -1.1] | undecided (indicative: under 30 pairs) |
| log | L | schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0013 [-0.0020, -0.0010] | -1074 [-1785, -431] | -93686 [-98651, -49330] | -5.2s [-6.9, -2.8] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | full | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0019 [-0.0022, -0.0015] | -10742 [-11948, -10014] | +34482 [+32657, +36606] | +1.9s [+0.8, +2.6] | undecided |
| M | index | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0016 [-0.0020, -0.0012] | -10851 [-11706, -9148] | +36668 [+34600, +38401] | +2.3s [+1.4, +3.1] | undecided |
| M | lean | 52 | -2% [-10%, +5%] | 0/1, p 1.00 | $-0.0017 [-0.0020, -0.0012] | -10578 [-11966, -9732] | +35602 [+33818, +39360] | +2.4s [+2.0, +3.3] | undecided |
| M | schema | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0018 [-0.0022, -0.0013] | -11073 [-11970, -9618] | +36361 [+33797, +38022] | +2.2s [+1.1, +3.2] | undecided |
| L | full | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0016 [-0.0019, -0.0010] | -1668 [-2226, -958] | -94292 [-96999, -47525] | -4.9s [-6.0, -3.5] | passes |
| L | index | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0016 [-0.0019, -0.0011] | -1422 [-1983, -1067] | -94221 [-96844, -48105] | -5.3s [-6.4, -4.1] | passes |
| L | lean | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0016 [-0.0017, -0.0009] | -1592 [-2012, -1032] | -66474 [-95944, -47668] | -4.5s [-5.8, -3.0] | passes |
| L | schema | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0017 [-0.0021, -0.0012] | -1842 [-2226, -1374] | -94206 [-98956, -49162] | -5.2s [-6.5, -4.0] | passes |

## When the envelope acted: the pairs whose folded session folded the task's large output

| band | condition | acted | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| M | full | 52/52 (saw it 52) | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0019 [-0.0022, -0.0015] | -10742 [-11948, -10014] | +34482 [+32657, +36606] | +1.9s [+0.8, +2.6] | undecided |
| M | index | 52/52 (saw it 52) | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0016 [-0.0020, -0.0012] | -10851 [-11706, -9148] | +36668 [+34600, +38401] | +2.3s [+1.4, +3.1] | undecided |
| M | lean | 52/52 (saw it 52) | 52 | -2% [-10%, +5%] | 0/1, p 1.00 | $-0.0017 [-0.0020, -0.0012] | -10578 [-11966, -9732] | +35602 [+33818, +39360] | +2.4s [+2.0, +3.3] | undecided |
| M | schema | 52/52 (saw it 52) | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $-0.0018 [-0.0022, -0.0013] | -11073 [-11970, -9618] | +36361 [+33797, +38022] | +2.2s [+1.1, +3.2] | undecided |
| L | full | 52/52 (saw it 52) | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0016 [-0.0019, -0.0010] | -1668 [-2226, -958] | -94292 [-96999, -47525] | -4.9s [-6.0, -3.5] | passes |
| L | index | 52/52 (saw it 52) | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0016 [-0.0019, -0.0011] | -1422 [-1983, -1067] | -94221 [-96844, -48105] | -5.3s [-6.4, -4.1] | passes |
| L | lean | 52/52 (saw it 52) | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0016 [-0.0017, -0.0009] | -1592 [-2012, -1032] | -66474 [-95944, -47668] | -4.5s [-5.8, -3.0] | passes |
| L | schema | 52/52 (saw it 52) | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0017 [-0.0021, -0.0012] | -1842 [-2226, -1374] | -94206 [-98956, -49162] | -5.2s [-6.5, -4.0] | passes |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, 2026-11-03); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | full | 52 | +0.8 [+0.7, +1.0] | -10,118 [-11,247, -8,796] | +39,239 [+30,826, +49,197] | +1.7 [+1.3, +2.1] | 52/52, 52/52 | -10,742 tokens, $-0.00011 |
| M | index | 52 | +1.0 [+0.8, +1.3] | -9,049 [-10,381, -7,545] | +49,460 [+37,129, +65,159] | +2.1 [+1.6, +2.7] | 52/52, 52/52 | -10,851 tokens, $-0.00011 |
| M | lean | 52 | +1.1 [+0.9, +1.3] | -9,427 [-10,676, -7,981] | +51,714 [+41,691, +62,867] | +2.2 [+1.8, +2.7] | 52/52, 52/52 | -10,578 tokens, $-0.00011 |
| M | schema | 52 | +1.0 [+0.8, +1.2] | -9,320 [-10,672, -7,765] | +46,546 [+36,243, +57,910] | +2.0 [+1.5, +2.4] | 52/52, 52/52 | -11,073 tokens, $-0.00011 |
| L | full | 52 | -1.7 [-2.1, -1.3] | -3,555 [-6,216, -1,247] | -83,051 [-104,107, -63,696] | -3.3 [-4.2, -2.6] | 52/52, 52/52 | -1,668 tokens, $-0.00002 |
| L | index | 52 | -1.6 [-2.0, -1.1] | -3,272 [-5,117, -1,879] | -77,362 [-98,122, -53,924] | -3.2 [-4.0, -2.3] | 52/52, 52/52 | -1,422 tokens, $-0.00001 |
| L | lean | 52 | -1.5 [-1.8, -1.1] | -2,821 [-4,666, -1,508] | -72,643 [-89,440, -55,844] | -2.9 [-3.6, -2.2] | 52/52, 52/52 | -1,592 tokens, $-0.00002 |
| L | schema | 52 | -1.6 [-2.0, -1.2] | -4,368 [-6,667, -2,590] | -80,414 [-100,828, -60,264] | -3.2 [-4.0, -2.4] | 52/52, 52/52 | -1,842 tokens, $-0.00002 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

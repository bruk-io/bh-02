# Dials haiku-m: claude-haiku-5-5, the same tasks native and under each setting

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 104 | 100% | 58,066 | 148,937 | 28,681 | 120,250 | - | $0.0073 | 8.4s |
| default | 104 | +0% [-4%, +4%], 0/0 | -6,821 [-7,776, -5,776] | +69,036 [+60,436, +78,001] | -6,882 [-7,837, -5,817] | +75,915 [+67,653, +84,480] | -7,597 ($-0.00008) | -5% ($-0.0004) | +4.4 [+3.5, +5.5]s |
| budget-500 | 104 | -2% [-7%, +2%], 0/2 | -7,882 [-8,869, -6,861] | +68,359 [+59,520, +77,635] | -7,985 [-8,964, -6,980] | +76,341 [+67,482, +85,596] | -9,568 ($-0.00010) | -8% ($-0.0006) | +4.2 [+3.4, +5.2]s |
| budget-1000 | 104 | -1% [-5%, +3%], 0/1 | -7,257 [-8,222, -6,179] | +70,880 [+61,583, +81,166] | -7,360 [-8,354, -6,288] | +78,236 [+69,191, +88,266] | -8,732 ($-0.00009) | -6% ($-0.0004) | +4.7 [+3.7, +5.7]s |
| budget-4000 | 104 | -1% [-5%, +3%], 0/1 | -5,097 [-6,258, -3,836] | +67,882 [+56,563, +80,454] | -5,200 [-6,361, -3,945] | +73,079 [+62,050, +85,233] | -5,250 ($-0.00005) | -1% ($-0.0001) | +4.4 [+3.5, +5.3]s |
| schema-view | 26 | +0% [-13%, +13%], 0/0 | -10,722 [-11,764, -9,211] | +35,584 [+22,116, +49,595] | -10,795 [-11,853, -9,264] | +46,377 [+33,830, +60,676] | -11,598 ($-0.00012) | -23% ($-0.0017) | +1.8 [+0.3, +3.2]s |
| tree-cap-25 | 52 | +0% [-7%, +7%], 0/0 | -4,146 [-5,307, -2,934] | +90,403 [+78,019, +102,586] | -4,256 [-5,418, -3,032] | +94,655 [+81,937, +107,265] | -6,520 ($-0.00007) | +6% ($+0.0004) | +5.7 [+4.5, +7.0]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

598 runs, $4.17; 598 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | M | budget-1000 | 2/2 [34%, 100%] | $0.0082 | 58064 | 2.0 | 2/2 | 0/2 |
| a11y | absent | M | budget-4000 | 1/2 [9%, 91%] | $0.0084 | 59082 | 2.0 | 2/2 | 0/2 |
| a11y | absent | M | budget-500 | 2/2 [34%, 100%] | $0.0075 | 53826 | 2.5 | 2/2 | 0/2 |
| a11y | absent | M | default | 2/2 [34%, 100%] | $0.0082 | 51656 | 4.0 | 2/2 | 0/2 |
| a11y | absent | M | native | 2/2 [34%, 100%] | $0.0070 | 56574 | 1.0 | 0/2 | 0/2 |
| a11y | absent | M | tree-cap-25 | 2/2 [34%, 100%] | $0.0080 | 56492 | 2.5 | 2/2 | 0/2 |
| a11y | count | M | budget-1000 | 8/8 [68%, 100%] | $0.0064 | 48522 | 3.0 | 8/8 | 0/8 |
| a11y | count | M | budget-4000 | 8/8 [68%, 100%] | $0.0069 | 53198 | 2.0 | 8/8 | 0/8 |
| a11y | count | M | budget-500 | 8/8 [68%, 100%] | $0.0061 | 47685 | 2.5 | 8/8 | 0/8 |
| a11y | count | M | default | 8/8 [68%, 100%] | $0.0068 | 50124 | 2.5 | 8/8 | 0/8 |
| a11y | count | M | native | 8/8 [68%, 100%] | $0.0069 | 56599 | 1.0 | 0/8 | 0/8 |
| a11y | count | M | tree-cap-25 | 8/8 [68%, 100%] | $0.0069 | 50213 | 2.5 | 8/8 | 0/8 |
| a11y | enumerate | M | budget-1000 | 4/4 [51%, 100%] | $0.0064 | 48607 | 2.5 | 4/4 | 0/4 |
| a11y | enumerate | M | budget-4000 | 4/4 [51%, 100%] | $0.0069 | 53218 | 2.5 | 4/4 | 0/4 |
| a11y | enumerate | M | budget-500 | 4/4 [51%, 100%] | $0.0068 | 52295 | 2.0 | 4/4 | 0/4 |
| a11y | enumerate | M | default | 4/4 [51%, 100%] | $0.0061 | 49874 | 2.0 | 4/4 | 0/4 |
| a11y | enumerate | M | native | 4/4 [51%, 100%] | $0.0070 | 56616 | 1.0 | 0/4 | 0/4 |
| a11y | enumerate | M | tree-cap-25 | 4/4 [51%, 100%] | $0.0062 | 49966 | 2.0 | 4/4 | 0/4 |
| a11y | lookup | M | budget-1000 | 4/4 [51%, 100%] | $0.0056 | 47834 | 2.0 | 4/4 | 0/4 |
| a11y | lookup | M | budget-4000 | 4/4 [51%, 100%] | $0.0073 | 53122 | 3.0 | 4/4 | 0/4 |
| a11y | lookup | M | budget-500 | 4/4 [51%, 100%] | $0.0054 | 46934 | 2.0 | 4/4 | 0/4 |
| a11y | lookup | M | default | 4/4 [51%, 100%] | $0.0063 | 49734 | 2.0 | 4/4 | 0/4 |
| a11y | lookup | M | native | 4/4 [51%, 100%] | $0.0068 | 56569 | 1.0 | 0/4 | 0/4 |
| a11y | lookup | M | tree-cap-25 | 4/4 [51%, 100%] | $0.0060 | 49621 | 2.0 | 4/4 | 0/4 |
| a11y | spot | M | budget-1000 | 8/8 [68%, 100%] | $0.0081 | 59975 | 2.0 | 7/8 | 0/8 |
| a11y | spot | M | budget-4000 | 8/8 [68%, 100%] | $0.0084 | 56695 | 2.5 | 8/8 | 0/8 |
| a11y | spot | M | budget-500 | 8/8 [68%, 100%] | $0.0080 | 58031 | 2.0 | 8/8 | 0/8 |
| a11y | spot | M | default | 8/8 [68%, 100%] | $0.0071 | 50937 | 2.5 | 8/8 | 0/8 |
| a11y | spot | M | native | 8/8 [68%, 100%] | $0.0068 | 56559 | 1.0 | 0/8 | 0/8 |
| a11y | spot | M | tree-cap-25 | 8/8 [68%, 100%] | $0.0077 | 55117 | 2.0 | 7/8 | 0/8 |
| figma | absent | M | budget-1000 | 2/2 [34%, 100%] | $0.0087 | 50473 | 5.0 | 2/2 | 0/2 |
| figma | absent | M | budget-4000 | 2/2 [34%, 100%] | $0.0096 | 55939 | 4.5 | 2/2 | 0/2 |
| figma | absent | M | budget-500 | 2/2 [34%, 100%] | $0.0095 | 50770 | 6.0 | 2/2 | 0/2 |
| figma | absent | M | default | 2/2 [34%, 100%] | $0.0086 | 51894 | 4.0 | 2/2 | 0/2 |
| figma | absent | M | native | 2/2 [34%, 100%] | $0.0074 | 57651 | 1.0 | 0/2 | 0/2 |
| figma | absent | M | tree-cap-25 | 2/2 [34%, 100%] | $0.0089 | 52047 | 5.0 | 2/2 | 0/2 |
| figma | count | M | budget-1000 | 8/8 [68%, 100%] | $0.0074 | 49303 | 4.0 | 8/8 | 0/8 |
| figma | count | M | budget-4000 | 8/8 [68%, 100%] | $0.0081 | 53774 | 3.0 | 8/8 | 0/8 |
| figma | count | M | budget-500 | 8/8 [68%, 100%] | $0.0077 | 48951 | 3.0 | 7/8 | 0/8 |
| figma | count | M | default | 8/8 [68%, 100%] | $0.0086 | 56375 | 3.0 | 8/8 | 0/8 |
| figma | count | M | native | 8/8 [68%, 100%] | $0.0074 | 57720 | 1.0 | 0/8 | 0/8 |
| figma | count | M | tree-cap-25 | 8/8 [68%, 100%] | $0.0076 | 50631 | 4.0 | 8/8 | 0/8 |
| figma | enumerate | M | budget-1000 | 4/4 [51%, 100%] | $0.0075 | 54328 | 2.5 | 4/4 | 0/4 |
| figma | enumerate | M | budget-4000 | 4/4 [51%, 100%] | $0.0079 | 53227 | 2.0 | 2/4 | 0/4 |
| figma | enumerate | M | budget-500 | 4/4 [51%, 100%] | $0.0080 | 53861 | 3.0 | 4/4 | 0/4 |
| figma | enumerate | M | default | 4/4 [51%, 100%] | $0.0090 | 56382 | 3.0 | 4/4 | 0/4 |
| figma | enumerate | M | native | 4/4 [51%, 100%] | $0.0073 | 57690 | 1.0 | 0/4 | 0/4 |
| figma | enumerate | M | tree-cap-25 | 4/4 [51%, 100%] | $0.0076 | 50586 | 4.0 | 4/4 | 0/4 |
| figma | lookup | M | budget-1000 | 4/4 [51%, 100%] | $0.0073 | 54032 | 2.5 | 4/4 | 0/4 |
| figma | lookup | M | budget-4000 | 4/4 [51%, 100%] | $0.0076 | 58546 | 1.5 | 2/4 | 0/4 |
| figma | lookup | M | budget-500 | 4/4 [51%, 100%] | $0.0070 | 53144 | 2.5 | 4/4 | 0/4 |
| figma | lookup | M | default | 4/4 [51%, 100%] | $0.0068 | 49688 | 3.0 | 4/4 | 0/4 |
| figma | lookup | M | native | 4/4 [51%, 100%] | $0.0071 | 57624 | 1.0 | 0/4 | 0/4 |
| figma | lookup | M | tree-cap-25 | 4/4 [51%, 100%] | $0.0070 | 49783 | 3.0 | 4/4 | 0/4 |
| figma | spot | M | budget-1000 | 8/8 [68%, 100%] | $0.0085 | 50631 | 4.5 | 7/8 | 0/8 |
| figma | spot | M | budget-4000 | 8/8 [68%, 100%] | $0.0099 | 65159 | 3.0 | 5/8 | 0/8 |
| figma | spot | M | budget-500 | 8/8 [68%, 100%] | $0.0082 | 56618 | 3.5 | 8/8 | 0/8 |
| figma | spot | M | default | 8/8 [68%, 100%] | $0.0089 | 57980 | 3.0 | 8/8 | 0/8 |
| figma | spot | M | native | 8/8 [68%, 100%] | $0.0071 | 57668 | 1.0 | 0/8 | 0/8 |
| figma | spot | M | tree-cap-25 | 8/8 [68%, 100%] | $0.0089 | 61708 | 2.5 | 7/8 | 0/8 |
| json | absent | M | budget-1000 | 1/2 [9%, 91%] | $0.0071 | 52056 | 2.5 | 2/2 | 0/2 |
| json | absent | M | budget-4000 | 2/2 [34%, 100%] | $0.0070 | 51528 | 2.5 | 2/2 | 0/2 |
| json | absent | M | budget-500 | 0/2 [0%, 66%] | $0.0074 | 52364 | 2.5 | 2/2 | 0/2 |
| json | absent | M | default | 2/2 [34%, 100%] | $0.0083 | 56040 | 3.0 | 2/2 | 0/2 |
| json | absent | M | native | 2/2 [34%, 100%] | $0.0072 | 58338 | 1.0 | 0/2 | 0/2 |
| json | absent | M | schema-view | 2/2 [34%, 100%] | $0.0073 | 53739 | 2.5 | 2/2 | 0/2 |
| json | count | M | budget-1000 | 8/8 [68%, 100%] | $0.0057 | 47897 | 2.0 | 7/8 | 0/8 |
| json | count | M | budget-4000 | 8/8 [68%, 100%] | $0.0058 | 48420 | 2.0 | 7/8 | 0/8 |
| json | count | M | budget-500 | 8/8 [68%, 100%] | $0.0055 | 47174 | 2.0 | 7/8 | 0/8 |
| json | count | M | default | 8/8 [68%, 100%] | $0.0057 | 48400 | 2.0 | 6/8 | 0/8 |
| json | count | M | native | 8/8 [68%, 100%] | $0.0076 | 58430 | 1.0 | 0/8 | 0/8 |
| json | count | M | schema-view | 8/8 [68%, 100%] | $0.0054 | 46639 | 2.0 | 6/8 | 0/8 |
| json | enumerate | M | budget-1000 | 4/4 [51%, 100%] | $0.0058 | 48000 | 2.0 | 3/4 | 0/4 |
| json | enumerate | M | budget-4000 | 4/4 [51%, 100%] | $0.0057 | 48309 | 1.5 | 2/4 | 0/4 |
| json | enumerate | M | budget-500 | 4/4 [51%, 100%] | $0.0057 | 47351 | 2.0 | 4/4 | 0/4 |
| json | enumerate | M | default | 4/4 [51%, 100%] | $0.0061 | 48636 | 2.0 | 3/4 | 0/4 |
| json | enumerate | M | native | 4/4 [51%, 100%] | $0.0074 | 58449 | 1.0 | 0/4 | 0/4 |
| json | enumerate | M | schema-view | 4/4 [51%, 100%] | $0.0058 | 47067 | 2.0 | 4/4 | 0/4 |
| json | lookup | M | budget-1000 | 4/4 [51%, 100%] | $0.0054 | 46819 | 2.0 | 4/4 | 0/4 |
| json | lookup | M | budget-4000 | 4/4 [51%, 100%] | $0.0054 | 46790 | 2.0 | 4/4 | 0/4 |
| json | lookup | M | budget-500 | 4/4 [51%, 100%] | $0.0054 | 46773 | 2.0 | 4/4 | 0/4 |
| json | lookup | M | default | 4/4 [51%, 100%] | $0.0054 | 46822 | 2.0 | 4/4 | 0/4 |
| json | lookup | M | native | 4/4 [51%, 100%] | $0.0072 | 58337 | 1.0 | 0/4 | 0/4 |
| json | lookup | M | schema-view | 4/4 [51%, 100%] | $0.0060 | 47005 | 3.0 | 4/4 | 0/4 |
| json | spot | M | budget-1000 | 8/8 [68%, 100%] | $0.0057 | 47193 | 2.0 | 6/8 | 0/8 |
| json | spot | M | budget-4000 | 8/8 [68%, 100%] | $0.0053 | 46971 | 1.5 | 4/8 | 0/8 |
| json | spot | M | budget-500 | 8/8 [68%, 100%] | $0.0053 | 46775 | 1.5 | 4/8 | 0/8 |
| json | spot | M | default | 8/8 [68%, 100%] | $0.0055 | 46920 | 2.0 | 5/8 | 0/8 |
| json | spot | M | native | 8/8 [68%, 100%] | $0.0071 | 58339 | 1.0 | 0/8 | 0/8 |
| json | spot | M | schema-view | 8/8 [68%, 100%] | $0.0048 | 46205 | 1.0 | 3/8 | 0/8 |
| log | absent | M | budget-1000 | 2/2 [34%, 100%] | $0.0098 | 62263 | 3.5 | 2/2 | 0/2 |
| log | absent | M | budget-4000 | 2/2 [34%, 100%] | $0.0079 | 58240 | 2.5 | 2/2 | 0/2 |
| log | absent | M | budget-500 | 2/2 [34%, 100%] | $0.0065 | 47591 | 3.0 | 2/2 | 0/2 |
| log | absent | M | default | 2/2 [34%, 100%] | $0.0063 | 48568 | 2.5 | 2/2 | 0/2 |
| log | absent | M | native | 2/2 [34%, 100%] | $0.0076 | 60275 | 1.0 | 0/2 | 0/2 |
| log | count | M | budget-1000 | 8/8 [68%, 100%] | $0.0066 | 48865 | 3.0 | 8/8 | 0/8 |
| log | count | M | budget-4000 | 8/8 [68%, 100%] | $0.0063 | 50678 | 2.0 | 8/8 | 0/8 |
| log | count | M | budget-500 | 8/8 [68%, 100%] | $0.0063 | 47681 | 3.0 | 8/8 | 0/8 |
| log | count | M | default | 8/8 [68%, 100%] | $0.0063 | 50494 | 2.0 | 8/8 | 0/8 |
| log | count | M | native | 8/8 [68%, 100%] | $0.0077 | 60277 | 1.0 | 0/8 | 0/8 |
| log | enumerate | M | budget-1000 | 4/4 [51%, 100%] | $0.0061 | 48777 | 2.0 | 4/4 | 0/4 |
| log | enumerate | M | budget-4000 | 4/4 [51%, 100%] | $0.0064 | 50689 | 2.0 | 4/4 | 0/4 |
| log | enumerate | M | budget-500 | 4/4 [51%, 100%] | $0.0060 | 47612 | 2.5 | 4/4 | 0/4 |
| log | enumerate | M | default | 4/4 [51%, 100%] | $0.0063 | 50100 | 2.0 | 4/4 | 0/4 |
| log | enumerate | M | native | 4/4 [51%, 100%] | $0.0077 | 60323 | 1.0 | 0/4 | 0/4 |
| log | lookup | M | budget-1000 | 4/4 [51%, 100%] | $0.0057 | 48152 | 2.0 | 4/4 | 0/4 |
| log | lookup | M | budget-4000 | 4/4 [51%, 100%] | $0.0057 | 48161 | 2.0 | 4/4 | 0/4 |
| log | lookup | M | budget-500 | 4/4 [51%, 100%] | $0.0054 | 46886 | 2.0 | 4/4 | 0/4 |
| log | lookup | M | default | 4/4 [51%, 100%] | $0.0057 | 48137 | 2.0 | 4/4 | 0/4 |
| log | lookup | M | native | 4/4 [51%, 100%] | $0.0076 | 60288 | 1.0 | 0/4 | 0/4 |
| log | spot | M | budget-1000 | 8/8 [68%, 100%] | $0.0064 | 48972 | 2.5 | 8/8 | 0/8 |
| log | spot | M | budget-4000 | 8/8 [68%, 100%] | $0.0061 | 48723 | 2.0 | 8/8 | 0/8 |
| log | spot | M | budget-500 | 8/8 [68%, 100%] | $0.0068 | 50223 | 2.5 | 8/8 | 0/8 |
| log | spot | M | default | 8/8 [68%, 100%] | $0.0067 | 49191 | 3.0 | 8/8 | 0/8 |
| log | spot | M | native | 8/8 [68%, 100%] | $0.0077 | 60313 | 1.0 | 0/8 | 0/8 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | M | budget-1000 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0003 [-0.0007, +0.0010] | -7894 [-8214, +1378] | +50905 [+48212, +87022] | +3.3s [+2.3, +5.6] | undecided (indicative: under 30 pairs) |
| a11y | M | budget-4000 | 26 | -4% [-19%, +9%] | 0/1, p 1.00 | $+0.0004 [+0.0000, +0.0008] | -3268 [-3453, -3074] | +53154 [+48974, +101953] | +5.6s [+3.7, +7.6] | undecided (indicative: under 30 pairs) |
| a11y | M | budget-500 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0005 [-0.0012, +0.0009] | -8750 [-9158, -3386] | +48434 [+37493, +84840] | +4.3s [+2.9, +4.9] | undecided (indicative: under 30 pairs) |
| a11y | M | default | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0001 [-0.0007, +0.0002] | -6322 [-6727, -5862] | +51990 [+42372, +92270] | +4.1s [+2.6, +5.7] | undecided (indicative: under 30 pairs) |
| a11y | M | tree-cap-25 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0000 [-0.0007, +0.0007] | -6357 [-6665, -4609] | +49804 [+42460, +71624] | +5.1s [+2.7, +6.4] | undecided (indicative: under 30 pairs) |
| figma | M | budget-1000 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $+0.0010 [+0.0002, +0.0012] | -7267 [-8372, +2060] | +122658 [+86314, +136233] | +7.1s [+5.2, +10.4] | undecided (indicative: under 30 pairs) |
| figma | M | budget-4000 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $+0.0018 [+0.0008, +0.0026] | -1712 [-3956, +7232] | +103052 [+60080, +125064] | +3.8s [+1.5, +7.8] | undecided (indicative: under 30 pairs) |
| figma | M | budget-500 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $+0.0008 [+0.0003, +0.0014] | -6881 [-8899, +1333] | +106942 [+84446, +132547] | +5.1s [+1.1, +9.4] | undecided (indicative: under 30 pairs) |
| figma | M | default | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $+0.0011 [+0.0004, +0.0017] | -5949 [-7006, +4134] | +114760 [+91360, +115582] | +6.3s [+3.8, +8.2] | undecided (indicative: under 30 pairs) |
| figma | M | tree-cap-25 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $+0.0005 [+0.0001, +0.0013] | -6896 [-7150, -5604] | +127882 [+90970, +141807] | +5.7s [+3.9, +7.9] | undecided (indicative: under 30 pairs) |
| json | M | budget-1000 | 26 | -4% [-19%, +9%] | 0/1, p 1.00 | $-0.0015 [-0.0018, -0.0015] | -10822 [-11194, -10575] | +36020 [+34954, +36864] | +2.8s [+2.0, +4.8] | undecided (indicative: under 30 pairs) |
| json | M | budget-4000 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0017 [-0.0021, -0.0014] | -10910 [-11260, -9806] | +35902 [+34760, +38376] | +3.1s [+1.1, +4.7] | undecided (indicative: under 30 pairs) |
| json | M | budget-500 | 26 | -8% [-24%, +6%] | 0/2, p 0.50 | $-0.0017 [-0.0018, -0.0016] | -11197 [-11530, -11077] | +35498 [+34799, +35670] | +3.2s [+2.0, +4.7] | undecided (indicative: under 30 pairs) |
| json | M | default | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0016 [-0.0019, -0.0014] | -10408 [-11373, -9857] | +36244 [+34838, +38816] | +2.9s [+0.2, +5.0] | undecided (indicative: under 30 pairs) |
| json | M | schema-view | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0018 [-0.0023, -0.0015] | -11598 [-12014, -11484] | +34692 [+34074, +40895] | +2.0s [+0.8, +3.5] | undecided (indicative: under 30 pairs) |
| log | M | budget-1000 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0012 [-0.0017, -0.0009] | -11524 [-11716, -11100] | +51501 [+36500, +84346] | +4.3s [+3.5, +5.4] | undecided (indicative: under 30 pairs) |
| log | M | budget-4000 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0014 [-0.0017, -0.0010] | -10711 [-11575, -9389] | +39060 [+36590, +41760] | +4.2s [+2.0, +5.3] | undecided (indicative: under 30 pairs) |
| log | M | budget-500 | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0014 [-0.0019, -0.0013] | -12725 [-13134, -12266] | +47894 [+33691, +80968] | +3.9s [+2.5, +5.0] | undecided (indicative: under 30 pairs) |
| log | M | default | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0013 [-0.0016, -0.0011] | -11048 [-11321, -9806] | +39658 [+37401, +84694] | +4.4s [+2.5, +5.9] | undecided (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| M | budget-1000 | 104 | -1% [-5%, +3%] | 0/1, p 1.00 | $-0.0007 [-0.0011, -0.0004] | -8732 [-10146, -8280] | +49993 [+39254, +83772] | +4.3s [+3.6, +5.2] | undecided |
| M | budget-4000 | 104 | -1% [-5%, +3%] | 0/1, p 1.00 | $-0.0002 [-0.0009, +0.0000] | -5250 [-8796, -3757] | +48745 [+40666, +51251] | +4.0s [+3.2, +5.2] | undecided |
| M | budget-500 | 104 | -2% [-7%, +2%] | 0/2, p 0.50 | $-0.0011 [-0.0013, -0.0005] | -9568 [-10729, -9143] | +48097 [+39270, +80979] | +3.8s [+3.2, +4.5] | undecided |
| M | default | 104 | +0% [-4%, +4%] | 0/0, p 1.00 | $-0.0007 [-0.0009, -0.0003] | -7597 [-9500, -6949] | +51462 [+42101, +85751] | +4.2s [+3.4, +5.4] | undecided |
| M | schema-view | 26 | +0% [-13%, +13%] | 0/0, p 1.00 | $-0.0018 [-0.0023, -0.0015] | -11598 [-12014, -11484] | +34692 [+34074, +40895] | +2.0s [+0.8, +3.5] | undecided (indicative: under 30 pairs) |
| M | tree-cap-25 | 52 | +0% [-7%, +7%] | 0/0, p 1.00 | $+0.0004 [+0.0000, +0.0008] | -6520 [-6831, -5775] | +90933 [+53102, +93032] | +5.4s [+4.1, +6.6] | undecided |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| M | budget-1000 | 104 | +1.6 [+1.4, +1.8] | -7,360 [-8,354, -6,288] | +78,236 [+69,191, +88,266] | +3.2 [+2.9, +3.6] | 104/104, 104/104 | -8,732 tokens, $-0.00009 |
| M | budget-4000 | 104 | +1.4 [+1.2, +1.6] | -5,200 [-6,361, -3,945] | +73,079 [+62,050, +85,233] | +2.8 [+2.4, +3.3] | 104/104, 104/104 | -5,250 tokens, $-0.00005 |
| M | budget-500 | 104 | +1.6 [+1.4, +1.8] | -7,985 [-8,964, -6,980] | +76,341 [+67,482, +85,596] | +3.2 [+2.8, +3.6] | 104/104, 104/104 | -9,568 tokens, $-0.00010 |
| M | default | 104 | +1.5 [+1.4, +1.7] | -6,882 [-7,837, -5,817] | +75,915 [+67,653, +84,480] | +3.1 [+2.7, +3.4] | 104/104, 104/104 | -7,597 tokens, $-0.00008 |
| M | schema-view | 26 | +1.0 [+0.7, +1.3] | -10,795 [-11,853, -9,264] | +46,377 [+33,830, +60,676] | +2.0 [+1.5, +2.6] | 26/26, 104/104 | -11,598 tokens, $-0.00012 |
| M | tree-cap-25 | 52 | +1.9 [+1.7, +2.2] | -4,256 [-5,418, -3,032] | +94,655 [+81,937, +107,265] | +3.8 [+3.3, +4.3] | 52/52, 104/104 | -6,520 tokens, $-0.00007 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

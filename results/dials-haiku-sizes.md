# Dials haiku-sizes: claude-haiku-5-5, the same tasks native and under each setting

## Band L (median input 35,333 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | 94% | 48,570 | 278,777 | 21,590 | 257,176 | - | $0.0078 | 15.8s |
| all-2000 | 52 | +6% [-2%, +16%], 3/0 | -1,004 [-3,238, +800] | -51,441 [-70,731, -33,749] | -1,088 [-3,323, +731] | -50,350 [-69,666, -31,917] | +669 ($+0.00001) | -12% ($-0.0009) | -2.2 [-3.9, -0.7]s |
| all-6000 | 52 | +6% [-2%, +16%], 3/0 | +2,766 [+886, +4,303] | -43,085 [-64,560, -22,856] | +2,682 [+796, +4,225] | -45,764 [-66,876, -25,435] | +3,236 ($+0.00003) | -2% ($-0.0001) | -1.8 [-3.2, -0.3]s |
| all-schema | 13 | +0% [-23%, +23%], 0/0 | -1,504 [-1,951, -1,100] | -80,838 [-106,571, -55,254] | -1,601 [-1,998, -1,267] | -79,234 [-104,648, -53,908] | -1,356 ($-0.00001) | -22% ($-0.0015) | -3.2 [-4.9, -1.4]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band XL (median input 141,320 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | 92% | 48,895 | 292,754 | 20,318 | 272,423 | - | $0.0078 | 19.4s |
| all-2000 | 52 | +8% [-1%, +18%], 4/0 | -194 [-903, +427] | -71,949 [-95,779, -51,417] | -254 [-952, +351] | -71,692 [-95,032, -51,447] | +85 ($+0.00000) | -15% ($-0.0011) | -6.2 [-10.2, -3.4]s |
| all-6000 | 52 | +6% [-4%, +16%], 4/1 | +3,327 [+2,253, +4,399] | -61,199 [-86,388, -38,982] | +3,231 [+2,174, +4,311] | -64,427 [-89,320, -42,847] | +4,222 ($+0.00004) | -5% ($-0.0004) | -6.3 [-10.2, -3.5]s |
| all-schema | 13 | +0% [-23%, +23%], 0/0 | -1,611 [-2,035, -1,183] | -66,675 [-92,480, -44,461] | -1,708 [-2,055, -1,372] | -64,965 [-90,459, -43,054] | -1,392 ($-0.00001) | -20% ($-0.0013) | -4.2 [-5.9, -2.7]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Band XXL (median input 565,495 tokens)

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 52 | 94% | 49,066 | 300,394 | 20,102 | 280,279 | - | $0.0079 | 24.2s |
| all-2000 | 52 | +6% [-2%, +16%], 3/0 | +77 [-528, +657] | -75,688 [-102,298, -52,558] | +17 [-573, +578] | -75,702 [-102,004, -53,074] | +404 ($+0.00000) | -14% ($-0.0011) | -9.7 [-18.7, -2.9]s |
| all-6000 | 52 | +6% [-2%, +16%], 3/0 | +3,708 [+2,578, +4,880] | -57,506 [-85,969, -31,122] | +3,623 [+2,508, +4,798] | -61,127 [-89,405, -35,363] | +2,893 ($+0.00003) | -3% ($-0.0002) | -9.4 [-18.7, -2.7]s |
| all-schema | 13 | +0% [-23%, +23%], 0/0 | -1,613 [-2,039, -1,224] | -81,154 [-106,884, -56,021] | -1,710 [-2,087, -1,365] | -79,442 [-104,877, -54,447] | -1,193 ($-0.00001) | -22% ($-0.0015) | -13.0 [-31.4, -2.9]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

## Every band together

| setting | pairs | accuracy | final context | summed input | cache writes | cache reads | each later request | cost | time |
|---|---|---|---|---|---|---|---|---|---|
| native (absolute) | 156 | 94% | 48,834 | 290,641 | 20,670 | 269,959 | - | $0.0078 | 19.8s |
| all-2000 | 156 | +6% [+3%, +11%], 10/0 | -373 [-1,250, +286] | -66,359 [-80,059, -53,555] | -442 [-1,316, +214] | -65,915 [-79,423, -53,350] | +320 ($+0.00000) | -14% ($-0.0011) | -6.1 [-9.5, -3.4]s |
| all-6000 | 156 | +6% [+2%, +11%], 10/1 | +3,267 [+2,475, +3,989] | -53,930 [-68,431, -39,634] | +3,179 [+2,376, +3,903] | -57,106 [-71,479, -42,785] | +3,564 ($+0.00004) | -3% ($-0.0002) | -5.8 [-9.2, -3.3]s |
| all-schema | 39 | +0% [-9%, +9%], 0/0 | -1,576 [-1,818, -1,336] | -76,223 [-90,959, -61,610] | -1,673 [-1,883, -1,477] | -74,547 [-89,132, -60,055] | -1,373 ($-0.00001) | -21% ($-0.0014) | -6.8 [-13.5, -3.0]s |

Each setting against native on the same tasks and repetitions: accuracy as the change with its 95% interval (Newcombe) and the pairs won and lost; the rest as mean changes per run with bootstrap intervals. Final context: the input of the session's last request. Summed input: every input token every request carried, cached or not. Each later request: what one more request in the same session would save or pay, the median change in the final context (a cache read at $0.010 per million, as these runs' costs imply).

# Layer 2: Claude Code on the eval tasks (claude-haiku-5-5)

507 runs, $3.66; 507 scored, 0 failed to answer (listed at the end). Correct = the ANSWER line matches the computed truth; intervals are 95% (Wilson for accuracy, bootstrap for paired differences). 0 answers had no ANSWER line (scored on their prose); 0 ran out of turns (scored as wrong).

## By task group

| format | kind | band | condition | correct | median cost | median final context | median calls | read the saved file | ran lab-fold |
|---|---|---|---|---|---|---|---|---|---|
| a11y | absent | L | all-2000 | 1/1 [21%, 100%] | $0.0072 | 50691 | 3 | 1/1 | 0/1 |
| a11y | absent | L | all-6000 | 1/1 [21%, 100%] | $0.0092 | 58112 | 3 | 1/1 | 0/1 |
| a11y | absent | L | native | 1/1 [21%, 100%] | $0.0123 | 58413 | 9 | 1/1 | 0/1 |
| a11y | absent | XL | all-2000 | 1/1 [21%, 100%] | $0.0074 | 50716 | 3 | 1/1 | 0/1 |
| a11y | absent | XL | all-6000 | 1/1 [21%, 100%] | $0.0088 | 57672 | 3 | 1/1 | 0/1 |
| a11y | absent | XL | native | 1/1 [21%, 100%] | $0.0110 | 52484 | 9 | 1/1 | 0/1 |
| a11y | absent | XXL | all-2000 | 1/1 [21%, 100%] | $0.0075 | 50984 | 3 | 1/1 | 0/1 |
| a11y | absent | XXL | all-6000 | 1/1 [21%, 100%] | $0.0089 | 58237 | 3 | 1/1 | 0/1 |
| a11y | absent | XXL | native | 1/1 [21%, 100%] | $0.0107 | 52177 | 8 | 1/1 | 0/1 |
| a11y | count | L | all-2000 | 4/4 [51%, 100%] | $0.0062 | 49805 | 2.0 | 4/4 | 0/4 |
| a11y | count | L | all-6000 | 4/4 [51%, 100%] | $0.0080 | 56812 | 2.5 | 4/4 | 0/4 |
| a11y | count | L | native | 4/4 [51%, 100%] | $0.0071 | 48951 | 4.5 | 4/4 | 0/4 |
| a11y | count | XL | all-2000 | 4/4 [51%, 100%] | $0.0066 | 50147 | 3.0 | 4/4 | 0/4 |
| a11y | count | XL | all-6000 | 4/4 [51%, 100%] | $0.0077 | 56534 | 2.0 | 4/4 | 0/4 |
| a11y | count | XL | native | 4/4 [51%, 100%] | $0.0070 | 48415 | 6.0 | 4/4 | 0/4 |
| a11y | count | XXL | all-2000 | 4/4 [51%, 100%] | $0.0066 | 50090 | 2.5 | 4/4 | 0/4 |
| a11y | count | XXL | all-6000 | 4/4 [51%, 100%] | $0.0080 | 56808 | 2.5 | 4/4 | 0/4 |
| a11y | count | XXL | native | 4/4 [51%, 100%] | $0.0069 | 49431 | 5.5 | 4/4 | 0/4 |
| a11y | enumerate | L | all-2000 | 2/2 [34%, 100%] | $0.0062 | 49951 | 3.0 | 2/2 | 0/2 |
| a11y | enumerate | L | all-6000 | 2/2 [34%, 100%] | $0.0077 | 56820 | 2.0 | 2/2 | 0/2 |
| a11y | enumerate | L | native | 2/2 [34%, 100%] | $0.0077 | 50923 | 4.5 | 2/2 | 0/2 |
| a11y | enumerate | XL | all-2000 | 2/2 [34%, 100%] | $0.0066 | 50055 | 3.0 | 2/2 | 0/2 |
| a11y | enumerate | XL | all-6000 | 2/2 [34%, 100%] | $0.0076 | 56723 | 2.0 | 2/2 | 0/2 |
| a11y | enumerate | XL | native | 2/2 [34%, 100%] | $0.0068 | 49699 | 3.5 | 2/2 | 0/2 |
| a11y | enumerate | XXL | all-2000 | 2/2 [34%, 100%] | $0.0070 | 50276 | 3.5 | 2/2 | 0/2 |
| a11y | enumerate | XXL | all-6000 | 2/2 [34%, 100%] | $0.0085 | 57206 | 3.5 | 2/2 | 0/2 |
| a11y | enumerate | XXL | native | 2/2 [34%, 100%] | $0.0075 | 49122 | 5.5 | 2/2 | 0/2 |
| a11y | lookup | L | all-2000 | 2/2 [34%, 100%] | $0.0060 | 49592 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | all-6000 | 2/2 [34%, 100%] | $0.0075 | 56499 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | L | native | 2/2 [34%, 100%] | $0.0060 | 47681 | 2.5 | 2/2 | 0/2 |
| a11y | lookup | XL | all-2000 | 2/2 [34%, 100%] | $0.0060 | 49654 | 2.0 | 2/2 | 0/2 |
| a11y | lookup | XL | all-6000 | 2/2 [34%, 100%] | $0.0078 | 56630 | 2.5 | 2/2 | 0/2 |
| a11y | lookup | XL | native | 2/2 [34%, 100%] | $0.0062 | 48320 | 3.5 | 2/2 | 0/2 |
| a11y | lookup | XXL | all-2000 | 2/2 [34%, 100%] | $0.0064 | 49737 | 2.5 | 2/2 | 0/2 |
| a11y | lookup | XXL | all-6000 | 2/2 [34%, 100%] | $0.0078 | 56683 | 2.5 | 2/2 | 0/2 |
| a11y | lookup | XXL | native | 2/2 [34%, 100%] | $0.0060 | 47517 | 3.0 | 2/2 | 0/2 |
| a11y | spot | L | all-2000 | 4/4 [51%, 100%] | $0.0078 | 51471 | 3.5 | 2/4 | 0/4 |
| a11y | spot | L | all-6000 | 4/4 [51%, 100%] | $0.0103 | 59293 | 3.0 | 4/4 | 0/4 |
| a11y | spot | L | native | 2/4 [15%, 85%] | $0.0126 | 71691 | 6.5 | 4/4 | 0/4 |
| a11y | spot | XL | all-2000 | 4/4 [51%, 100%] | $0.0073 | 50847 | 3.0 | 4/4 | 0/4 |
| a11y | spot | XL | all-6000 | 3/4 [30%, 95%] | $0.0084 | 57407 | 2.5 | 4/4 | 0/4 |
| a11y | spot | XL | native | 2/4 [15%, 85%] | $0.0109 | 53209 | 9.0 | 4/4 | 0/4 |
| a11y | spot | XXL | all-2000 | 4/4 [51%, 100%] | $0.0071 | 50525 | 3.0 | 4/4 | 0/4 |
| a11y | spot | XXL | all-6000 | 4/4 [51%, 100%] | $0.0090 | 57857 | 3.5 | 4/4 | 0/4 |
| a11y | spot | XXL | native | 3/4 [30%, 95%] | $0.0123 | 55340 | 11.0 | 4/4 | 0/4 |
| figma | absent | L | all-2000 | 1/1 [21%, 100%] | $0.0085 | 51839 | 4 | 0/1 | 0/1 |
| figma | absent | L | all-6000 | 1/1 [21%, 100%] | $0.0110 | 59291 | 5 | 1/1 | 0/1 |
| figma | absent | L | native | 1/1 [21%, 100%] | $0.0088 | 50297 | 5 | 1/1 | 0/1 |
| figma | absent | XL | all-2000 | 1/1 [21%, 100%] | $0.0085 | 51853 | 4 | 1/1 | 0/1 |
| figma | absent | XL | all-6000 | 1/1 [21%, 100%] | $0.0109 | 58780 | 5 | 1/1 | 0/1 |
| figma | absent | XL | native | 1/1 [21%, 100%] | $0.0103 | 53771 | 6 | 1/1 | 0/1 |
| figma | absent | XXL | all-2000 | 1/1 [21%, 100%] | $0.0084 | 51735 | 4 | 1/1 | 0/1 |
| figma | absent | XXL | all-6000 | 1/1 [21%, 100%] | $0.0109 | 58771 | 5 | 1/1 | 0/1 |
| figma | absent | XXL | native | 1/1 [21%, 100%] | $0.0089 | 50093 | 6 | 1/1 | 0/1 |
| figma | count | L | all-2000 | 4/4 [51%, 100%] | $0.0078 | 50939 | 4.0 | 4/4 | 0/4 |
| figma | count | L | all-6000 | 4/4 [51%, 100%] | $0.0084 | 56429 | 3.0 | 4/4 | 0/4 |
| figma | count | L | native | 4/4 [51%, 100%] | $0.0072 | 48625 | 3.5 | 4/4 | 0/4 |
| figma | count | XL | all-2000 | 4/4 [51%, 100%] | $0.0074 | 50593 | 3.5 | 4/4 | 0/4 |
| figma | count | XL | all-6000 | 4/4 [51%, 100%] | $0.0088 | 56754 | 3.5 | 3/4 | 0/4 |
| figma | count | XL | native | 4/4 [51%, 100%] | $0.0073 | 49821 | 4.0 | 4/4 | 0/4 |
| figma | count | XXL | all-2000 | 4/4 [51%, 100%] | $0.0075 | 50581 | 3.5 | 4/4 | 0/4 |
| figma | count | XXL | all-6000 | 4/4 [51%, 100%] | $0.0088 | 56626 | 3.5 | 4/4 | 0/4 |
| figma | count | XXL | native | 4/4 [51%, 100%] | $0.0071 | 49235 | 3.5 | 4/4 | 0/4 |
| figma | enumerate | L | all-2000 | 2/2 [34%, 100%] | $0.0067 | 50040 | 2.5 | 2/2 | 0/2 |
| figma | enumerate | L | all-6000 | 2/2 [34%, 100%] | $0.0083 | 56253 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | L | native | 2/2 [34%, 100%] | $0.0066 | 47687 | 3.5 | 2/2 | 0/2 |
| figma | enumerate | XL | all-2000 | 2/2 [34%, 100%] | $0.0070 | 50312 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | XL | all-6000 | 2/2 [34%, 100%] | $0.0076 | 56031 | 2.0 | 2/2 | 0/2 |
| figma | enumerate | XL | native | 2/2 [34%, 100%] | $0.0063 | 47657 | 2.5 | 2/2 | 0/2 |
| figma | enumerate | XXL | all-2000 | 2/2 [34%, 100%] | $0.0070 | 50072 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | XXL | all-6000 | 2/2 [34%, 100%] | $0.0085 | 56493 | 3.0 | 2/2 | 0/2 |
| figma | enumerate | XXL | native | 2/2 [34%, 100%] | $0.0075 | 49207 | 4.0 | 2/2 | 0/2 |
| figma | lookup | L | all-2000 | 2/2 [34%, 100%] | $0.0066 | 49676 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | all-6000 | 2/2 [34%, 100%] | $0.0082 | 56833 | 3.0 | 2/2 | 0/2 |
| figma | lookup | L | native | 2/2 [34%, 100%] | $0.0065 | 47161 | 3.5 | 2/2 | 0/2 |
| figma | lookup | XL | all-2000 | 2/2 [34%, 100%] | $0.0067 | 50136 | 3.0 | 2/2 | 0/2 |
| figma | lookup | XL | all-6000 | 2/2 [34%, 100%] | $0.0080 | 55910 | 3.0 | 2/2 | 0/2 |
| figma | lookup | XL | native | 2/2 [34%, 100%] | $0.0069 | 47441 | 4.0 | 2/2 | 0/2 |
| figma | lookup | XXL | all-2000 | 2/2 [34%, 100%] | $0.0069 | 50722 | 3.0 | 2/2 | 0/2 |
| figma | lookup | XXL | all-6000 | 2/2 [34%, 100%] | $0.0083 | 56920 | 3.0 | 2/2 | 0/2 |
| figma | lookup | XXL | native | 2/2 [34%, 100%] | $0.0061 | 47076 | 3.0 | 2/2 | 0/2 |
| figma | spot | L | all-2000 | 4/4 [51%, 100%] | $0.0083 | 52011 | 4.0 | 4/4 | 0/4 |
| figma | spot | L | all-6000 | 4/4 [51%, 100%] | $0.0099 | 58476 | 4.0 | 3/4 | 0/4 |
| figma | spot | L | native | 3/4 [30%, 95%] | $0.0099 | 53602 | 5.5 | 4/4 | 0/4 |
| figma | spot | XL | all-2000 | 4/4 [51%, 100%] | $0.0086 | 52256 | 4.0 | 4/4 | 0/4 |
| figma | spot | XL | all-6000 | 4/4 [51%, 100%] | $0.0096 | 58840 | 3.5 | 4/4 | 0/4 |
| figma | spot | XL | native | 2/4 [15%, 85%] | $0.0100 | 53807 | 6.0 | 4/4 | 0/4 |
| figma | spot | XXL | all-2000 | 4/4 [51%, 100%] | $0.0084 | 52224 | 4.0 | 4/4 | 0/4 |
| figma | spot | XXL | all-6000 | 4/4 [51%, 100%] | $0.0099 | 58339 | 4.0 | 4/4 | 0/4 |
| figma | spot | XXL | native | 2/4 [15%, 85%] | $0.0103 | 52788 | 6.0 | 4/4 | 0/4 |
| json | absent | L | all-2000 | 1/1 [21%, 100%] | $0.0064 | 47709 | 3 | 1/1 | 0/1 |
| json | absent | L | all-6000 | 1/1 [21%, 100%] | $0.0064 | 47590 | 3 | 1/1 | 0/1 |
| json | absent | L | all-schema | 1/1 [21%, 100%] | $0.0049 | 46075 | 1 | 0/1 | 0/1 |
| json | absent | L | native | 1/1 [21%, 100%] | $0.0075 | 48902 | 4 | 1/1 | 0/1 |
| json | absent | XL | all-2000 | 1/1 [21%, 100%] | $0.0066 | 47799 | 3 | 1/1 | 0/1 |
| json | absent | XL | all-6000 | 1/1 [21%, 100%] | $0.0057 | 46906 | 2 | 1/1 | 0/1 |
| json | absent | XL | all-schema | 1/1 [21%, 100%] | $0.0050 | 46071 | 1 | 0/1 | 0/1 |
| json | absent | XL | native | 1/1 [21%, 100%] | $0.0074 | 48684 | 4 | 1/1 | 0/1 |
| json | absent | XXL | all-2000 | 1/1 [21%, 100%] | $0.0067 | 47609 | 3 | 1/1 | 0/1 |
| json | absent | XXL | all-6000 | 1/1 [21%, 100%] | $0.0073 | 48234 | 4 | 1/1 | 0/1 |
| json | absent | XXL | all-schema | 1/1 [21%, 100%] | $0.0050 | 46037 | 1 | 0/1 | 0/1 |
| json | absent | XXL | native | 1/1 [21%, 100%] | $0.0074 | 48495 | 4 | 1/1 | 0/1 |
| json | count | L | all-2000 | 4/4 [51%, 100%] | $0.0059 | 48810 | 2.0 | 4/4 | 0/4 |
| json | count | L | all-6000 | 4/4 [51%, 100%] | $0.0059 | 48778 | 2.0 | 4/4 | 0/4 |
| json | count | L | all-schema | 4/4 [51%, 100%] | $0.0051 | 46665 | 1.5 | 2/4 | 0/4 |
| json | count | L | native | 4/4 [51%, 100%] | $0.0065 | 48152 | 3.0 | 4/4 | 0/4 |
| json | count | XL | all-2000 | 4/4 [51%, 100%] | $0.0058 | 48533 | 2.0 | 3/4 | 0/4 |
| json | count | XL | all-6000 | 4/4 [51%, 100%] | $0.0058 | 48744 | 2.0 | 4/4 | 0/4 |
| json | count | XL | all-schema | 4/4 [51%, 100%] | $0.0054 | 46952 | 2.0 | 4/4 | 0/4 |
| json | count | XL | native | 4/4 [51%, 100%] | $0.0065 | 48250 | 3.0 | 4/4 | 0/4 |
| json | count | XXL | all-2000 | 4/4 [51%, 100%] | $0.0059 | 48824 | 2.0 | 4/4 | 0/4 |
| json | count | XXL | all-6000 | 4/4 [51%, 100%] | $0.0060 | 48900 | 2.0 | 4/4 | 0/4 |
| json | count | XXL | all-schema | 4/4 [51%, 100%] | $0.0055 | 47027 | 2.0 | 4/4 | 0/4 |
| json | count | XXL | native | 4/4 [51%, 100%] | $0.0066 | 48310 | 3.0 | 4/4 | 0/4 |
| json | enumerate | L | all-2000 | 2/2 [34%, 100%] | $0.0057 | 48484 | 1.5 | 1/2 | 0/2 |
| json | enumerate | L | all-6000 | 2/2 [34%, 100%] | $0.0061 | 48865 | 2.0 | 2/2 | 0/2 |
| json | enumerate | L | all-schema | 2/2 [34%, 100%] | $0.0055 | 47111 | 2.0 | 2/2 | 0/2 |
| json | enumerate | L | native | 2/2 [34%, 100%] | $0.0064 | 48030 | 3.0 | 2/2 | 0/2 |
| json | enumerate | XL | all-2000 | 2/2 [34%, 100%] | $0.0057 | 48511 | 1.5 | 1/2 | 0/2 |
| json | enumerate | XL | all-6000 | 2/2 [34%, 100%] | $0.0061 | 48791 | 2.0 | 2/2 | 0/2 |
| json | enumerate | XL | all-schema | 2/2 [34%, 100%] | $0.0052 | 46836 | 1.5 | 1/2 | 0/2 |
| json | enumerate | XL | native | 2/2 [34%, 100%] | $0.0066 | 48767 | 3.0 | 2/2 | 0/2 |
| json | enumerate | XXL | all-2000 | 2/2 [34%, 100%] | $0.0057 | 48570 | 1.5 | 1/2 | 0/2 |
| json | enumerate | XXL | all-6000 | 2/2 [34%, 100%] | $0.0058 | 48619 | 1.5 | 1/2 | 0/2 |
| json | enumerate | XXL | all-schema | 2/2 [34%, 100%] | $0.0056 | 47098 | 2.0 | 2/2 | 0/2 |
| json | enumerate | XXL | native | 2/2 [34%, 100%] | $0.0066 | 48231 | 3.0 | 2/2 | 0/2 |
| json | lookup | L | all-2000 | 2/2 [34%, 100%] | $0.0055 | 46778 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | all-6000 | 2/2 [34%, 100%] | $0.0055 | 46823 | 2.0 | 2/2 | 0/2 |
| json | lookup | L | all-schema | 2/2 [34%, 100%] | $0.0060 | 46878 | 3.0 | 2/2 | 0/2 |
| json | lookup | L | native | 2/2 [34%, 100%] | $0.0065 | 47228 | 3.5 | 2/2 | 0/2 |
| json | lookup | XL | all-2000 | 2/2 [34%, 100%] | $0.0056 | 46872 | 2.0 | 2/2 | 0/2 |
| json | lookup | XL | all-6000 | 2/2 [34%, 100%] | $0.0057 | 46981 | 2.5 | 2/2 | 0/2 |
| json | lookup | XL | all-schema | 2/2 [34%, 100%] | $0.0060 | 46841 | 3.0 | 2/2 | 0/2 |
| json | lookup | XL | native | 2/2 [34%, 100%] | $0.0062 | 47042 | 3.0 | 2/2 | 0/2 |
| json | lookup | XXL | all-2000 | 2/2 [34%, 100%] | $0.0056 | 46912 | 2.0 | 2/2 | 0/2 |
| json | lookup | XXL | all-6000 | 2/2 [34%, 100%] | $0.0055 | 46931 | 2.0 | 2/2 | 0/2 |
| json | lookup | XXL | all-schema | 2/2 [34%, 100%] | $0.0063 | 47013 | 3.5 | 2/2 | 0/2 |
| json | lookup | XXL | native | 2/2 [34%, 100%] | $0.0069 | 47722 | 4.5 | 2/2 | 0/2 |
| json | spot | L | all-2000 | 4/4 [51%, 100%] | $0.0052 | 46777 | 1.5 | 2/4 | 0/4 |
| json | spot | L | all-6000 | 4/4 [51%, 100%] | $0.0056 | 47019 | 2.0 | 3/4 | 0/4 |
| json | spot | L | all-schema | 4/4 [51%, 100%] | $0.0047 | 46175 | 1.0 | 1/4 | 0/4 |
| json | spot | L | native | 4/4 [51%, 100%] | $0.0069 | 48433 | 3.5 | 4/4 | 0/4 |
| json | spot | XL | all-2000 | 4/4 [51%, 100%] | $0.0052 | 46746 | 1.5 | 2/4 | 0/4 |
| json | spot | XL | all-6000 | 4/4 [51%, 100%] | $0.0056 | 47039 | 2.0 | 3/4 | 0/4 |
| json | spot | XL | all-schema | 4/4 [51%, 100%] | $0.0055 | 46709 | 2.0 | 3/4 | 0/4 |
| json | spot | XL | native | 4/4 [51%, 100%] | $0.0073 | 48818 | 4.0 | 4/4 | 0/4 |
| json | spot | XXL | all-2000 | 4/4 [51%, 100%] | $0.0053 | 46965 | 1.5 | 2/4 | 0/4 |
| json | spot | XXL | all-6000 | 4/4 [51%, 100%] | $0.0052 | 46777 | 1.5 | 1/4 | 0/4 |
| json | spot | XXL | all-schema | 4/4 [51%, 100%] | $0.0048 | 46217 | 1.0 | 1/4 | 0/4 |
| json | spot | XXL | native | 4/4 [51%, 100%] | $0.0074 | 48819 | 4.0 | 4/4 | 0/4 |
| log | absent | L | all-2000 | 1/1 [21%, 100%] | $0.0079 | 50818 | 4 | 1/1 | 0/1 |
| log | absent | L | all-6000 | 1/1 [21%, 100%] | $0.0069 | 49135 | 3 | 1/1 | 0/1 |
| log | absent | L | native | 1/1 [21%, 100%] | $0.0128 | 60491 | 9 | 1/1 | 0/1 |
| log | absent | XL | all-2000 | 1/1 [21%, 100%] | $0.0068 | 49351 | 3 | 1/1 | 0/1 |
| log | absent | XL | all-6000 | 1/1 [21%, 100%] | $0.0078 | 50642 | 4 | 1/1 | 0/1 |
| log | absent | XL | native | 1/1 [21%, 100%] | $0.0111 | 57697 | 7 | 1/1 | 0/1 |
| log | absent | XXL | all-2000 | 1/1 [21%, 100%] | $0.0079 | 50594 | 4 | 1/1 | 0/1 |
| log | absent | XXL | all-6000 | 1/1 [21%, 100%] | $0.0081 | 50608 | 4 | 1/1 | 0/1 |
| log | absent | XXL | native | 1/1 [21%, 100%] | $0.0122 | 54095 | 14 | 1/1 | 0/1 |
| log | count | L | all-2000 | 4/4 [51%, 100%] | $0.0067 | 50327 | 2.5 | 4/4 | 0/4 |
| log | count | L | all-6000 | 4/4 [51%, 100%] | $0.0064 | 51100 | 2.0 | 4/4 | 0/4 |
| log | count | L | native | 4/4 [51%, 100%] | $0.0060 | 47629 | 3.0 | 4/4 | 0/4 |
| log | count | XL | all-2000 | 4/4 [51%, 100%] | $0.0070 | 50691 | 3.0 | 4/4 | 0/4 |
| log | count | XL | all-6000 | 4/4 [51%, 100%] | $0.0066 | 51298 | 2.5 | 4/4 | 0/4 |
| log | count | XL | native | 4/4 [51%, 100%] | $0.0059 | 47072 | 3.0 | 4/4 | 0/4 |
| log | count | XXL | all-2000 | 4/4 [51%, 100%] | $0.0062 | 49770 | 2.0 | 4/4 | 0/4 |
| log | count | XXL | all-6000 | 4/4 [51%, 100%] | $0.0067 | 51207 | 2.5 | 4/4 | 0/4 |
| log | count | XXL | native | 4/4 [51%, 100%] | $0.0070 | 48445 | 5.0 | 4/4 | 0/4 |
| log | enumerate | L | all-2000 | 2/2 [34%, 100%] | $0.0066 | 50262 | 2.5 | 2/2 | 0/2 |
| log | enumerate | L | all-6000 | 2/2 [34%, 100%] | $0.0067 | 50756 | 2.5 | 2/2 | 0/2 |
| log | enumerate | L | native | 2/2 [34%, 100%] | $0.0063 | 47487 | 3.0 | 2/2 | 0/2 |
| log | enumerate | XL | all-2000 | 2/2 [34%, 100%] | $0.0064 | 50501 | 2.0 | 2/2 | 0/2 |
| log | enumerate | XL | all-6000 | 2/2 [34%, 100%] | $0.0071 | 51268 | 3.0 | 2/2 | 0/2 |
| log | enumerate | XL | native | 2/2 [34%, 100%] | $0.0067 | 47763 | 3.5 | 2/2 | 0/2 |
| log | enumerate | XXL | all-2000 | 2/2 [34%, 100%] | $0.0064 | 50411 | 2.0 | 2/2 | 0/2 |
| log | enumerate | XXL | all-6000 | 2/2 [34%, 100%] | $0.0068 | 51074 | 2.5 | 2/2 | 0/2 |
| log | enumerate | XXL | native | 2/2 [34%, 100%] | $0.0074 | 49470 | 5.0 | 2/2 | 0/2 |
| log | lookup | L | all-2000 | 2/2 [34%, 100%] | $0.0057 | 48141 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | all-6000 | 2/2 [34%, 100%] | $0.0056 | 48073 | 2.0 | 2/2 | 0/2 |
| log | lookup | L | native | 2/2 [34%, 100%] | $0.0055 | 46385 | 2.0 | 2/2 | 0/2 |
| log | lookup | XL | all-2000 | 2/2 [34%, 100%] | $0.0058 | 48140 | 2.0 | 2/2 | 0/2 |
| log | lookup | XL | all-6000 | 2/2 [34%, 100%] | $0.0057 | 48108 | 2.0 | 2/2 | 0/2 |
| log | lookup | XL | native | 2/2 [34%, 100%] | $0.0055 | 46402 | 2.0 | 2/2 | 0/2 |
| log | lookup | XXL | all-2000 | 2/2 [34%, 100%] | $0.0057 | 48141 | 2.0 | 2/2 | 0/2 |
| log | lookup | XXL | all-6000 | 2/2 [34%, 100%] | $0.0057 | 48114 | 2.0 | 2/2 | 0/2 |
| log | lookup | XXL | native | 2/2 [34%, 100%] | $0.0055 | 46391 | 2.0 | 2/2 | 0/2 |
| log | spot | L | all-2000 | 4/4 [51%, 100%] | $0.0088 | 56749 | 4.0 | 4/4 | 0/4 |
| log | spot | L | all-6000 | 4/4 [51%, 100%] | $0.0079 | 49847 | 4.5 | 4/4 | 0/4 |
| log | spot | L | native | 4/4 [51%, 100%] | $0.0086 | 51028 | 6.0 | 4/4 | 0/4 |
| log | spot | XL | all-2000 | 4/4 [51%, 100%] | $0.0068 | 49320 | 3.0 | 4/4 | 0/4 |
| log | spot | XL | all-6000 | 4/4 [51%, 100%] | $0.0073 | 50067 | 3.5 | 4/4 | 0/4 |
| log | spot | XL | native | 4/4 [51%, 100%] | $0.0094 | 51846 | 6.5 | 4/4 | 0/4 |
| log | spot | XXL | all-2000 | 4/4 [51%, 100%] | $0.0069 | 49424 | 3.0 | 4/4 | 0/4 |
| log | spot | XXL | all-6000 | 4/4 [51%, 100%] | $0.0080 | 50432 | 5.0 | 4/4 | 0/4 |
| log | spot | XXL | native | 4/4 [51%, 100%] | $0.0082 | 50242 | 5.0 | 4/4 | 0/4 |

## Each condition against native (or its baseline), paired by task and repetition, per band

| format | band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| a11y | L | all-2000 | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $-0.0011 [-0.0049, -0.0007] | -754 [-5388, +721] | -44608 [-92444, +3782] | +0.6s [-1.2, +3.6] | undecided (indicative: under 30 pairs) |
| a11y | L | all-6000 | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $+0.0004 [-0.0011, +0.0012] | +7422 [+4581, +8256] | -30089 [-89546, +19417] | -0.5s [-4.4, +3.8] | fails (indicative: under 30 pairs) |
| a11y | XL | all-2000 | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $-0.0011 [-0.0030, -0.0000] | +116 [-1768, +1496] | -89841 [-194007, +3935] | -3.9s [-10.7, -1.1] | undecided (indicative: under 30 pairs) |
| a11y | XL | all-6000 | 13 | +8% [-21%, +36%] | 2/1, p 1.00 | $+0.0004 [-0.0022, +0.0009] | +6952 [+5188, +8199] | -76074 [-190099, -30094] | -5.6s [-14.6, -3.1] | fails (indicative: under 30 pairs) |
| a11y | XXL | all-2000 | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0006 [-0.0032, -0.0001] | +408 [-1193, +910] | -44753 [-194050, -40766] | -3.8s [-13.4, -1.5] | undecided (indicative: under 30 pairs) |
| a11y | XXL | all-6000 | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $+0.0009 [-0.0017, +0.0015] | +7439 [+6060, +8302] | -30907 [-172593, +25816] | -2.8s [-14.3, +1.1] | fails (indicative: under 30 pairs) |
| figma | L | all-2000 | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $-0.0001 [-0.0007, +0.0004] | +2031 [-780, +2465] | -38778 [-50278, +8460] | -1.8s [-3.4, +1.8] | undecided (indicative: under 30 pairs) |
| figma | L | all-6000 | 13 | +8% [-16%, +33%] | 1/0, p 1.00 | $+0.0015 [+0.0004, +0.0018] | +8075 [+5604, +8847] | +19980 [-18453, +26373] | -0.1s [-1.3, +1.7] | fails (indicative: under 30 pairs) |
| figma | XL | all-2000 | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $-0.0003 [-0.0013, +0.0002] | +767 [-1217, +2006] | -39083 [-95212, +6265] | -1.6s [-8.5, -0.2] | undecided (indicative: under 30 pairs) |
| figma | XL | all-6000 | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $+0.0010 [+0.0002, +0.0012] | +6537 [+5042, +7823] | -20490 [-30265, +18102] | -4.4s [-5.9, -2.0] | fails (indicative: under 30 pairs) |
| figma | XXL | all-2000 | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $+0.0002 [-0.0006, +0.0005] | +1082 [+648, +1985] | -29991 [-41558, +7216] | -2.1s [-14.6, +4.8] | fails (indicative: under 30 pairs) |
| figma | XXL | all-6000 | 13 | +15% [-10%, +42%] | 2/0, p 0.50 | $+0.0019 [+0.0001, +0.0021] | +7508 [+6711, +8678] | +28900 [-73673, +34126] | -1.1s [-14.2, +4.8] | fails (indicative: under 30 pairs) |
| json | L | all-2000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0011 [-0.0014, -0.0007] | -410 [-1193, +128] | -48842 [-93857, -46487] | -3.4s [-5.8, -1.8] | undecided (indicative: under 30 pairs) |
| json | L | all-6000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0009 [-0.0013, -0.0006] | -454 [-1312, +284] | -48403 [-92797, -45434] | -4.0s [-4.9, -1.1] | undecided (indicative: under 30 pairs) |
| json | L | all-schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0011 [-0.0023, -0.0010] | -1356 [-2203, -1085] | -48855 [-142705, -47600] | -3.6s [-6.0, -1.5] | undecided (indicative: under 30 pairs) |
| json | XL | all-2000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0008 [-0.0014, -0.0006] | -256 [-1646, -95] | -48545 [-94098, -46228] | -3.5s [-5.7, -2.3] | undecided (indicative: under 30 pairs) |
| json | XL | all-6000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0008 [-0.0016, -0.0006] | -249 [-1493, +296] | -46285 [-96105, -44146] | -2.3s [-6.5, -0.9] | undecided (indicative: under 30 pairs) |
| json | XL | all-schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0011 [-0.0018, -0.0010] | -1392 [-2242, -1267] | -48207 [-96768, -47719] | -3.8s [-5.0, -3.7] | undecided (indicative: under 30 pairs) |
| json | XXL | all-2000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0013 [-0.0014, -0.0007] | -623 [-1383, +282] | -93067 [-95391, -44877] | -3.5s [-6.8, +0.5] | undecided (indicative: under 30 pairs) |
| json | XXL | all-6000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0013 [-0.0015, -0.0005] | -439 [-1143, +222] | -93268 [-95353, -43603] | -2.5s [-5.5, -0.5] | undecided (indicative: under 30 pairs) |
| json | XXL | all-schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0011 [-0.0024, -0.0010] | -1193 [-2458, -1063] | -48022 [-143257, -47474] | -3.6s [-5.7, -2.3] | undecided (indicative: under 30 pairs) |
| log | L | all-2000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $+0.0002 [-0.0004, +0.0006] | +2575 [+1768, +3069] | -38976 [-44867, +4981] | +0.1s [-5.0, +2.7] | fails (indicative: under 30 pairs) |
| log | L | all-6000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $+0.0002 [-0.0000, +0.0008] | +2395 [+674, +3267] | +3362 [-41175, +8562] | -0.1s [-3.7, +1.2] | fails (indicative: under 30 pairs) |
| log | XL | all-2000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0001 [-0.0025, +0.0003] | +1636 [-2099, +2581] | -42555 [-111053, +3681] | -3.8s [-7.6, +1.1] | undecided (indicative: under 30 pairs) |
| log | XL | all-6000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0000 [-0.0010, +0.0008] | +1750 [-397, +3136] | -38295 [-89995, +8448] | -1.3s [-4.3, +1.0] | undecided (indicative: under 30 pairs) |
| log | XXL | all-2000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0008 [-0.0012, -0.0005] | +399 [-508, +1734] | -88469 [-93344, -45361] | -2.9s [-6.4, +0.0] | undecided (indicative: under 30 pairs) |
| log | XXL | all-6000 | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0002 [-0.0010, +0.0002] | +1748 [+1454, +1917] | -40839 [-88988, +3495] | -0.8s [-2.0, +2.6] | fails (indicative: under 30 pairs) |

## Every format together, per size band

| band | condition | pairs | accuracy change | right only here / only native | cost change | final context change | input change | time change | verdict |
|---|---|---|---|---|---|---|---|---|---|
| L | all-2000 | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0007 [-0.0010, -0.0003] | +669 [-482, +1734] | -44118 [-49560, -39432] | -1.4s [-3.0, +0.2] | undecided |
| L | all-6000 | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $+0.0001 [-0.0005, +0.0006] | +3236 [+1560, +4614] | -40941 [-47312, -12840] | -1.1s [-2.7, +0.1] | fails |
| L | all-schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0011 [-0.0023, -0.0010] | -1356 [-2203, -1085] | -48855 [-142705, -47600] | -3.6s [-6.0, -1.5] | undecided (indicative: under 30 pairs) |
| XL | all-2000 | 52 | +8% [-1%, +18%] | 4/0, p 0.12 | $-0.0007 [-0.0012, -0.0004] | +85 [-868, +832] | -46258 [-89980, -43260] | -3.4s [-5.8, -1.4] | undecided |
| XL | all-6000 | 52 | +6% [-4%, +16%] | 4/1, p 0.38 | $-0.0002 [-0.0007, +0.0005] | +4222 [+1513, +5069] | -44112 [-48671, -27607] | -3.5s [-5.7, -1.9] | fails |
| XL | all-schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0011 [-0.0018, -0.0010] | -1392 [-2242, -1267] | -48207 [-96768, -47719] | -3.8s [-5.0, -3.7] | undecided (indicative: under 30 pairs) |
| XXL | all-2000 | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0007 [-0.0012, -0.0005] | +404 [-334, +910] | -46251 [-90936, -43074] | -3.4s [-4.5, -0.7] | undecided |
| XXL | all-6000 | 52 | +6% [-2%, +16%] | 3/0, p 0.25 | $-0.0001 [-0.0005, +0.0002] | +2893 [+1525, +6696] | -43528 [-79556, -25366] | -1.6s [-3.1, +0.1] | fails |
| XXL | all-schema | 13 | +0% [-23%, +23%] | 0/0, p 1.00 | $-0.0011 [-0.0024, -0.0010] | -1193 [-2458, -1063] | -48022 [-143257, -47474] | -3.6s [-5.7, -2.3] | undecided (indicative: under 30 pairs) |

Verdict: passes when the accuracy change's lower bound is above -3 points and the final context shrinks (its upper bound below zero); fails when accuracy surely drops more than 3 points or the context surely grows; undecided otherwise. The accuracy interval is Newcombe's for paired proportions, with McNemar's exact p; the cost, context, input and time intervals are a bootstrap of the pairs. The input criterion is the final context (the owner's reading, FINDINGS 37); summed input, every input token the requests carried (cached or not), is reported beside it.

## Cache and requests, every format together, per size band

Input price these runs' costs imply: $0.100 per million tokens (80% of runs between $0.100 and $0.100); so a cache read costs $0.010 per million.

| band | condition | pairs | requests | cache writes | cache reads | uncached input | warm starts (here, baseline) | each later request |
|---|---|---|---|---|---|---|---|---|
| L | all-2000 | 52 | -1.1 [-1.5, -0.7] | -1,088 [-3,323, +731] | -50,350 [-69,666, -31,917] | -2.2 [-2.9, -1.5] | 52/52, 52/52 | +669 tokens, $+0.00001 |
| L | all-6000 | 52 | -1.1 [-1.5, -0.8] | +2,682 [+796, +4,225] | -45,764 [-66,876, -25,435] | -2.3 [-3.1, -1.5] | 52/52, 52/52 | +3,236 tokens, $+0.00003 |
| L | all-schema | 13 | -1.7 [-2.2, -1.2] | -1,601 [-1,998, -1,267] | -79,234 [-104,648, -53,908] | -3.4 [-4.5, -2.3] | 13/13, 52/52 | -1,356 tokens, $-0.00001 |
| XL | all-2000 | 52 | -1.5 [-2.0, -1.1] | -254 [-952, +351] | -71,692 [-95,032, -51,447] | -3.0 [-4.0, -2.2] | 52/52, 52/52 | +85 tokens, $+0.00000 |
| XL | all-6000 | 52 | -1.5 [-2.0, -1.1] | +3,231 [+2,174, +4,311] | -64,427 [-89,320, -42,847] | -3.0 [-4.0, -2.2] | 52/52, 52/52 | +4,222 tokens, $+0.00004 |
| XL | all-schema | 13 | -1.4 [-1.9, -0.9] | -1,708 [-2,055, -1,372] | -64,965 [-90,459, -43,054] | -2.8 [-3.8, -1.8] | 13/13, 52/52 | -1,392 tokens, $-0.00001 |
| XXL | all-2000 | 52 | -1.6 [-2.1, -1.2] | +17.2 [-573.0, +578.3] | -75,702 [-102,004, -53,074] | -3.2 [-4.3, -2.3] | 52/52, 52/52 | +404 tokens, $+0.00000 |
| XXL | all-6000 | 52 | -1.5 [-2.0, -1.0] | +3,623 [+2,508, +4,798] | -61,127 [-89,405, -35,363] | -3.0 [-4.1, -2.0] | 52/52, 52/52 | +2,893 tokens, $+0.00003 |
| XXL | all-schema | 13 | -1.7 [-2.2, -1.2] | -1,710 [-2,087, -1,365] | -79,442 [-104,877, -54,447] | -3.4 [-4.5, -2.3] | 13/13, 52/52 | -1,193 tokens, $-0.00001 |

A folded result is written to the cache once and re-read by every later request, so a context N tokens smaller saves N cache-read tokens on each request after it: the last column, by the median change in the final context, priced at the implied cache-read price when the runs agree on it. Requests, writes, reads and uncached input are mean changes per run against the baseline, with bootstrap intervals. A warm start is a run whose first request read 10,000 tokens or more from the cache: a prefix another session had written, which lowers that run's cost.

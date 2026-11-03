# Corpus stats (budget 2000 tokens)

93 tool results from 6 transcripts, ~75023 tokens in all. 0 image blocks were not counted.

## Size distribution

| size (tokens) | results | share of tokens |
|---|---|---|
| <500 | 51 | 10% |
| 500-2k | 32 | 38% |
| 2k-8k | 9 | 41% |
| 8k-32k | 1 | 11% |
| >=32k | 0 | 0% |

## Per tool

| tool | results | tokens | share | median | max | over 2000 |
|---|---|---|---|---|---|---|
| Bash | 52 | 31245 | 42% | 377 | 3411 | 3 |
| Read | 13 | 26916 | 36% | 1358 | 8610 | 5 |
| mcp__github__list_commits | 1 | 7729 | 10% | 7729 | 7729 | 1 |
| mcp__github__pull_request_read | 7 | 5326 | 7% | 699 | 1227 | 0 |
| mcp__github__list_pull_requests | 2 | 2024 | 3% | 1012 | 2023 | 1 |
| mcp__github__get_commit | 2 | 919 | 1% | 459 | 472 | 0 |
| Grep | 3 | 524 | 1% | 175 | 209 | 0 |
| SubagentHandback | 6 | 96 | 0% | 16 | 16 | 0 |
| Write | 2 | 95 | 0% | 47 | 49 | 0 |
| Monitor | 1 | 76 | 0% | 76 | 76 | 0 |
| Edit | 1 | 51 | 0% | 51 | 51 | 0 |
| mcp__github__list_issues | 1 | 22 | 0% | 22 | 22 | 0 |
| ToolSearch | 2 | 0 | 0% | 0 | 0 | 0 |

## Results over the budget (10)

| format | results |
|---|---|
| lines | 8 |
| json | 2 |

Compression by branch (passthrough means folding saved under 10%):

| branch | results | tokens in | tokens out | kept |
|---|---|---|---|---|
| json | 2 | 9752 | 1270 | 13% |
| lines | 8 | 29519 | 14441 | 49% |

Compression by tool (to see a tool that should never be folded):

| tool | results | tokens in | tokens out | kept |
|---|---|---|---|---|
| Bash | 3 | 8780 | 7077 | 81% |
| Read | 5 | 20739 | 7364 | 36% |
| mcp__github__list_commits | 1 | 7729 | 839 | 11% |
| mcp__github__list_pull_requests | 1 | 2023 | 431 | 21% |

Tokens saved over the whole corpus: ~23560 of ~75023 (31%).
Without folding Bash: ~21857 (29%).
Without folding Read: ~10185 (14%).
Without folding mcp__github__list_commits: ~16670 (22%).
Without folding mcp__github__list_pull_requests: ~21968 (29%).

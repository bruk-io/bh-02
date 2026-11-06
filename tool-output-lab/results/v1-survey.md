# V1: the large outputs of one real session

Source: this research's own Claude Code session (one main transcript and ten sub-agent transcripts,
5-6 November 2026), extracted with `./lab extract` and reported with `./lab stats --budget 2000`.
The lab's own test runs (the `-tmp-l2-*` and `-tmp-ab-*` transcripts) are left out, since their
tasks are synthetic.

## What it shows

- Large outputs are few but heavy: 84 of 2,364 tool results (4%) are over the hook's 2,000-token
  threshold, and they hold about 37% of all tool-result tokens.
- Nothing reaches 32,000 tokens. Claude Code cuts long Bash output and pages long files, so the
  large outputs a coding session meets are 2,000 to 9,000 tokens. v1's large band (19,000 to 70,000)
  applies to MCP tools, which Claude Code saves to a file past 50,000 characters.
- Most large outputs are file views. Grouped by the command behind them:

| What produced it | Results | Tokens | Median |
|---|---|---|---|
| Bash file views (`sed -n`, `cat`, `head`) | 48 | 175,685 | 3,660 |
| The Read tool | 16 | 59,794 | 3,737 |
| Reading published pages back (Artifact) | 4 | 28,146 | 7,036 |
| Shell loops over files (`for`) | 5 | 14,513 | 2,902 |
| GitHub through MCP (commits, pull requests) | 2 | 9,751 | 4,876 |
| Searches and listings (`grep`, `find`, `ls`) | 2 | 6,508 | 3,254 |
| Scripts (`python`, `node`) | 2 | 4,782 | 2,391 |
| Test runs (`./lab check`) | 1 | 4,184 | 4,184 |
| Other (`awk`, `timeout`, `sleep`, `sed`) | 4 | 9,378 | 2,345 |

- The hook folds Bash and MCP output, not Read, and a file view is often read so that it can be
  edited, which needs the exact text. File views are the largest share and the riskiest to fold.

## What it cannot show

It is one session, by one agent, on one kind of work (an evaluation lab), with this agent's habits:
it reads files in ranges with `sed -n` and cuts test output with `tail`, so test runs look smaller
here than they would for someone who reads them whole. Other people's sessions, on other work, are
needed before the scenario mix is settled.

---

# Corpus stats (budget 2000 tokens)

2364 tool results from 11 transcripts, ~847954 tokens in all. 94 image blocks were not counted.

## Size distribution

| size (tokens) | results | share of tokens |
|---|---|---|
| <500 | 1944 | 27% |
| 500-2k | 336 | 36% |
| 2k-8k | 81 | 34% |
| 8k-32k | 3 | 3% |
| >=32k | 0 | 0% |

## Per tool

| tool | results | tokens | share | median | max | over 2000 |
|---|---|---|---|---|---|---|
| Bash | 1939 | 697800 | 82% | 127 | 6184 | 62 |
| Read | 94 | 78900 | 9% | 0 | 8610 | 16 |
| Artifact | 33 | 38785 | 5% | 376 | 9514 | 4 |
| mcp__github__list_commits | 1 | 7729 | 1% | 7729 | 7729 | 1 |
| mcp__github__pull_request_read | 7 | 5326 | 1% | 699 | 1227 | 0 |
| Write | 113 | 4622 | 1% | 39 | 53 | 0 |
| Grep | 9 | 3107 | 0% | 175 | 1600 | 0 |
| Agent | 10 | 2600 | 0% | 260 | 260 | 0 |
| WebSearch | 3 | 2103 | 0% | 643 | 818 | 0 |
| mcp__github__list_pull_requests | 2 | 2024 | 0% | 1012 | 2023 | 1 |
| Monitor | 13 | 988 | 0% | 76 | 76 | 0 |
| TaskStop | 6 | 937 | 0% | 143 | 292 | 0 |
| mcp__github__get_commit | 2 | 919 | 0% | 459 | 472 | 0 |
| TaskCreate | 34 | 755 | 0% | 21 | 33 | 0 |
| mcp__claude-code-remote__read_documentation | 1 | 381 | 0% | 381 | 381 | 0 |
| Edit | 9 | 359 | 0% | 40 | 75 | 0 |
| TaskUpdate | 59 | 354 | 0% | 6 | 6 | 0 |
| SubagentHandback | 10 | 160 | 0% | 16 | 16 | 0 |
| Skill | 7 | 67 | 0% | 10 | 11 | 0 |
| mcp__github__list_issues | 1 | 22 | 0% | 22 | 22 | 0 |
| mcp__ccd_session__spawn_task | 1 | 16 | 0% | 16 | 16 | 0 |
| ToolSearch | 10 | 0 | 0% | 0 | 0 | 0 |

## Results over the budget (84)

| format | results |
|---|---|
| lines | 67 |
| outline | 12 |
| json | 2 |
| text | 2 |
| html | 1 |

Compression by branch (passthrough means folding saved under 10%):

| branch | results | tokens in | tokens out | kept |
|---|---|---|---|---|
| html | 1 | 3089 | 1654 | 54% |
| json | 2 | 9752 | 3000 | 31% |
| lines | 67 | 255815 | 58402 | 23% |
| outline | 12 | 38866 | 19635 | 51% |
| text | 2 | 5281 | 2013 | 38% |

Compression by tool (to see a tool that should never be folded):

| tool | results | tokens in | tokens out | kept |
|---|---|---|---|---|
| Artifact | 4 | 28149 | 3421 | 12% |
| Bash | 62 | 215096 | 61619 | 29% |
| Read | 16 | 59806 | 16664 | 28% |
| mcp__github__list_commits | 1 | 7729 | 1708 | 22% |
| mcp__github__list_pull_requests | 1 | 2023 | 1292 | 64% |

Tokens saved over the whole corpus: ~228099 of ~847954 (27%).
Without folding Artifact: ~203371 (24%).
Without folding Bash: ~74622 (9%).
Without folding Read: ~184957 (22%).
Without folding mcp__github__list_commits: ~222078 (26%).
Without folding mcp__github__list_pull_requests: ~227368 (27%).

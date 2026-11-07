# Scenarios, layer 2: the incident family on claude-haiku-5-5

150 runs, 0 failed to produce an answer (not scored).
Spent $1.01.

| task | size | condition | right | median turns | median final context | median cost | runs with a large output |
|---|---|---|---|---|---|---|---|
| cause | L | native | 15 of 15 (100%) | 7 | 50,951 | $0.0065 | 11 of 15 |
| cause | M | native | 14 of 15 (93%) | 7 | 46,916 | $0.0057 | 2 of 15 |
| count | L | native | 15 of 15 (100%) | 7 | 41,212 | $0.0057 | 6 of 15 |
| count | M | native | 15 of 15 (100%) | 5 | 47,610 | $0.0059 | 15 of 15 |
| stale | L | native | 15 of 15 (100%) | 6 | 40,805 | $0.0047 | 0 of 15 |
| stale | M | native | 15 of 15 (100%) | 5 | 46,431 | $0.0048 | 15 of 15 |
| gap | L | native | 15 of 15 (100%) | 8 | 39,323 | $0.0057 | 1 of 15 |
| gap | M | native | 15 of 15 (100%) | 5 | 60,088 | $0.0100 | 15 of 15 |
| healthy | L | native | 15 of 15 (100%) | 10 | 50,412 | $0.0078 | 8 of 15 |
| healthy | M | native | 15 of 15 (100%) | 11 | 52,080 | $0.0088 | 11 of 15 |

## Calls whose output was over 2,000 tokens

| call | times | median tokens |
|---|---|---|
| `mcp__incident__list_pods: {"namespace": "prod"}` | 12 | 5,074 |
| `mcp__incident__get_logs: {"service": "search", "since":` | 8 | 8,968 |
| `mcp__incident__get_logs: {"service": "inventory", "since":` | 8 | 3,953 |
| `mcp__incident__list_pods: {}` | 6 | 5,426 |
| `mcp__incident__get_logs: {"service": "pricing", "since":` | 6 | 4,866 |
| `mcp__incident__get_logs: {"service": "payments", "since":` | 6 | 9,869 |
| `Bash: ls -la /tmp` | 6 | 5,014 |
| `mcp__incident__get_metrics: {"service": "gateway", "metric":` | 4 | 2,020 |
| `mcp__incident__get_logs: {"service": "notifications", "since":` | 4 | 5,289 |
| `mcp__incident__get_logs: {"service": "reviews", "since":` | 3 | 9,876 |
| `mcp__incident__get_metrics: {"service": "cart", "metric":` | 3 | 2,021 |
| `mcp__incident__get_logs: {"service": "catalogue", "since":` | 3 | 9,443 |
| `mcp__incident__get_metrics: {"service": "auth", "metric":` | 3 | 2,026 |
| `mcp__incident__get_metrics: {"service": "shipping", "metric":` | 3 | 2,027 |
| `mcp__incident__get_logs: {"service": "checkout", "since":` | 3 | 4,074 |
| `mcp__incident__get_metrics: {"service": "pricing", "metric":` | 2 | 2,020 |
| `mcp__incident__get_logs: {"service": "search"}` | 2 | 10,174 |
| `mcp__incident__get_metrics: {"service": "payments", "metric":` | 2 | 2,027 |
| `mcp__incident__get_logs: {"service": "auth", "since":` | 2 | 3,426 |
| `mcp__incident__get_logs: {"service": "cart", "since":` | 2 | 9,113 |
| `Bash: ls -la /tmp/scenario-xk789w46/` | 1 | 2,177 |
| `Bash: ls -la /tmp/scenario-0rmerq0e/` | 1 | 5,483 |
| `mcp__incident__get_metrics: {"service": "checkout", "metric":` | 1 | 2,027 |
| `Bash: F=/root/.claude/projects/-tmp-scenario-qr5quey5-work/c6c09582-843f-492f-9cf4-a1551a622323/tool-results/mcp-incident-get_logs-1794057603687.txt; head -5` | 1 | 2,180 |
| `Bash: cd /root/.claude/projects/-tmp-scenario-2hh6rrnn-work/195df3f8-3401-445d-872d-9e3bd353a2a3/tool-results/ &&` | 1 | 6,933 |

## Some misses

- incident-M-0-cause (native): none

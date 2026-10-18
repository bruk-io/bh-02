---
id: TASK-0150
title: >-
  A reused jail_dir's stale proxy.port points a new jail's workload at a dead or
  foreign port
status: To Do
assignee: []
created_date: '2026-10-18 12:55'
labels:
  - brig
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing TASK-0140. connect_proxy's wrap (libs/brig/src/brig/mech/connect_proxy.py, _render_wait_script) waits with [ ! -s <jail_dir>/proxy.port ], reads the port and exports HTTP_PROXY/HTTPS_PROXY. The proxy publishes that file (os.replace after listen) only when its Python process has started, tens of milliseconds after the workload's shell may already be running. A jail_dir that still holds the proxy.port of an earlier jail (a supported flow: decision-181, make_channel_dir keeps an earlier jail's directory, clear_earlier_records clears only procs/) makes the wrap return at once with the OLD port. The workload is then pointed at a port nobody listens on (ConnectionRefusedError, measured: a planted stale file failed the 403 integration test 11 of 12 runs) or, worse, at whatever listens there now, which would receive its proxied requests. The cooperative grade does not excuse sending a jail's traffic to a foreign listener. TASK-0140 fixed the one test by giving it a fresh directory; the library is unchanged. A fix changes behaviour, so it starts as a SPEC.md decision (libs/brig/WORKFLOW.md). Options to rule on: the runtime removes a helper's declared ready file before it spawns the helper (Helper gains the path it publishes); or the runtime starts the proxy with its existing --ready-fd and waits for it, then passes the port on; or the wrap checks the file it reads came from this launch.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A SPEC.md decision paragraph rules how a new jail never reads an earlier jail's proxy.port, naming this task and ending (Ruled YYYY-MM-DD, decision-N.)
- [ ] #2 A test plants a proxy.port naming a closed port in the jail_dir before Jail.create and shows the workload still gets the proxy's own 403 for a host outside the allow list; it is seen failing before the change and passing after
- [ ] #3 scripts/check libs/brig passes
<!-- AC:END -->

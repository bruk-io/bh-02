---
id: TASK-0181
title: >-
  Plugins and inputs ask for what they need, and the person approves once or
  always
status: Done
assignee:
  - '@bruk'
created_date: '2026-11-03T18:22:00Z'
updated_date: '2026-11-04T23:42:00Z'
labels:
  - runner
  - approval
dependencies: []
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

In the owner's words: let other plugins request whatever they need and let the user approve once or always approve. The policy for brig can be shaped by this per project, and the runner (brig's plugin) manages it. For network, approve per hostname and/or IP address, plus the port.

Today approval is one rule (runner:approval) that asks about every call unless brig grades the whole jail confined, and keeps no memory of an answer. The jail's policy is fixed by spec_for plus a hand-edited allow setting. Once bh-02 runs on the brig that grades honestly (brig TASK-0042, TASK-0043), network reads best_effort for a typical project, and every input would be asked about. A plugin that needs a cache directory, a token or one host on the network has no way to say so; the person cannot say yes once and be done.

## Affected users and systems

- The person running bh-02, who answers the prompts.
- Plugins that need more than the default jail (python, extensions, subagents, future ones), and the model's inputs that run into a denial.
- The runner plugin: approval, spec_for and the policy handed to brig.
- brig: an enforced egress allowlist (host or IP plus port) does not exist yet; it is TASK-0001's egress criterion and open question on brig's board.

## Open questions

- [x] Where are always-grants kept so the jailed model can never write them (bh-02's own state outside every jail root, per project), and can the person list and revoke them (a command)?
- [x] A grant changes the jail's policy, which brig fixes at create: does an always-grant apply from the next start only, and does a once-grant mid-session restart the program (losing the Python process's namespace), run one call in a jail of its own, or wait?
- [x] What may a plugin request without the person ever being asked, if anything, and what is always asked?
- [x] Network: hostname matching through the proxy (CONNECT or TLS SNI) and IP plus port for raw TCP; does a granted hostname cover the addresses it resolves to, and are wildcards (*.github.com) allowed?
- [x] How does a grant show in the grades and the prompt (a granted socket path would rightly lower channel_exclusivity), and what does the person see before saying always?
- [x] How does this replace the jail row's allow setting and relate to the access broker (a per-file check before a tool opens a file)?
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A plugin can request a capability (read a path, write a path, pass an environment variable, reach a network destination as hostname or IP plus port) with a reason, and an input that hits a denial can raise the same request
- [x] #2 The person answers each request once, always for this project, or no; an always-grant is not asked again in that project, and a no is not re-asked within the session
- [x] #3 The runner plugin turns the grants into brig's policy at each jail start, and the report still grades the resulting jail honestly
- [x] #4 Network grants are per hostname and/or IP address plus port, enforced by brig: a program that ignores the proxy reaches nothing, and a destination not granted is refused or asked about
- [x] #5 Must not break: the jailed model cannot grant itself anything (always-grants live where no jail can write them), and what runs unasked is never wider than what the person granted
- [x] #6 Must not break: runner:confined still refuses where it cannot jail, and an unconfined run still asks about every call
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-03: the network question has a proposed answer in bruk-io/brig decision-0009 (TASK-0048): grants are host and port (exact hostname, *.suffix, or an IP literal; port always), names are resolved by the proxy, never the jail, and a resolved private address needs an IP grant; allow_egress adds a destination to a running jail without a restart; refusals come back as data (egress_decisions) so the runner can ask. Ticked once the owner accepts it.

Check `scripts/check` exited 0

(13 earlier lines omitted)
```text

........................................................................ [  2%]
........................................................................ [  5%]
............s........................................................... [  7%]
.............................x.......................................... [ 10%]
........................................................................ [ 12%]
........................................................................ [ 15%]
........................................................................ [ 18%]
.......................s................................................ [ 20%]
........................................................................ [ 23%]
........................................................................ [ 25%]
........................................................................ [ 28%]
........................................................................ [ 30%]
........................................................................ [ 33%]
...............................................ss....................... [ 36%]
........................................................................ [ 38%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 46%]
........................................................................ [ 48%]
........................................................................ [ 51%]
........................................................................ [ 54%]
........................................................................ [ 56%]
........................................................................ [ 59%]
........................................................................ [ 61%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 82%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 95%]
........................................................................ [ 97%]
...........................................................              [100%]
2790 passed, 6 skipped, 1 xfailed in 134.12s (0:02:14)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 2.37 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Closed by review against the intent's own six criteria. Full check (scripts/check) exit 0, 2790 passed, bwrap present so real-jail tests ran; tree clean after. AC1: Kind read/write/env/net with reason and Asker; inputs raise via grant() and egress refusals become prompts. AC2: test_runner_broker once/always/no tests, test_a_declined_destination_is_asked_once_and_stays_refused, test_a_grant_kept_as_always_..._with_nothing_asked. AC3: to_brig/spec_for at each start, test_what_the_broker_says_is_granted_is_what_the_next_start_applies; grades honest in test_a_real_start_grades_the_network_best_effort_and_proxied_... AC4: real-jail tests test_a_jailed_program_reaches_no_network_and_one_that_ignores_the_proxy_settings_reaches_nothing, test_a_program_that_ignores_the_proxy_reaches_nothing_though_the_destination_is_granted, test_a_destination_granted_is_reached_through_the_proxy_and_nothing_ungranted_is (seen failing with the egress policy emptied). AC5: test_a_linux_jail_keeps_the_grants_store_from_being_read_or_written_where_the_project_holds_it (real jail: list empty, read ENOENT, writes EROFS, file unchanged); floor refusals tested in test_runner_grants_policy and test_a_refused_grant_in_the_store_never_reaches_the_jail; every grant passes through the broker's prompt, none is applied unasked. AC6: test_a_confined_runner_that_cannot_jail_here_is_not_confined_before_any_start, test_a_host_with_no_bubblewrap_is_refused_..., test_an_unconfined_start_grades_every_part_unenforced_and_is_not_confined. Known limits (extension grants.ask not floor-checked up front, restart cost for a late grant-prompt mount, sub-agent has no grant tool DRAFT-0029) narrow convenience, not the criteria: nothing in them widens what runs unasked beyond what the person granted. No new findings filed.
<!-- SECTION:NOTES:END -->

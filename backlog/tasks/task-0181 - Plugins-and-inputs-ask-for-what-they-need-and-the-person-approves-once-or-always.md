---
id: TASK-0181
title: >-
  Plugins and inputs ask for what they need, and the person approves once or
  always
status: To Do
assignee:
  - '@bruk'
created_date: '2026-11-03T18:22:00Z'
updated_date: '2026-11-03T19:28:00Z'
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
- [ ] #1 A plugin can request a capability (read a path, write a path, pass an environment variable, reach a network destination as hostname or IP plus port) with a reason, and an input that hits a denial can raise the same request
- [ ] #2 The person answers each request once, always for this project, or no; an always-grant is not asked again in that project, and a no is not re-asked within the session
- [ ] #3 The runner plugin turns the grants into brig's policy at each jail start, and the report still grades the resulting jail honestly
- [ ] #4 Network grants are per hostname and/or IP address plus port, enforced by brig: a program that ignores the proxy reaches nothing, and a destination not granted is refused or asked about
- [ ] #5 Must not break: the jailed model cannot grant itself anything (always-grants live where no jail can write them), and what runs unasked is never wider than what the person granted
- [ ] #6 Must not break: runner:confined still refuses where it cannot jail, and an unconfined run still asks about every call
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-03: the network question has a proposed answer in bruk-io/brig decision-0009 (TASK-0048): grants are host and port (exact hostname, *.suffix, or an IP literal; port always), names are resolved by the proxy, never the jail, and a resolved private address needs an IP grant; allow_egress adds a destination to a running jail without a restart; refusals come back as data (egress_decisions) so the runner can ask. Ticked once the owner accepts it.
<!-- SECTION:NOTES:END -->

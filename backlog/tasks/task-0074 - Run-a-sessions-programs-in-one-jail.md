---
id: TASK-0074
title: Run a session's programs in one jail
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-10 18:42'
updated_date: '2026-11-09 01:37'
labels:
  - runner
  - finish-moved
  - size-5
milestone: m-5
dependencies:
  - TASK-0079.32
modified_files:
  - bh-02/CONTRACTS.md
  - bh-02/plugins/runner-cordis-plugin/README.md
  - bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/jail.py
  - bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/runner.py
  - bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/wiring.py
  - bh-02/plugins/runner-cordis-plugin/tests/conftest.py
  - bh-02/plugins/runner-cordis-plugin/tests/test_runner_allowlist.py
  - bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py
  - bh-02/plugins/extensions-cordis-plugin/src/extensions_cordis_plugin/host.py
  - '>-'
  - libs/brig/SPEC.md
  - libs/brig/src/brig/run/_supervisor_program.py
  - libs/brig/tests/e2e/test_process_namespaces.py
parent_task_id: TASK-0084
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`runner:confined` compiles a jail per start, so a session starts two jails from one policy (the Python process and the extensions process), and sub-agents would add one per REPL. With TASK-0073 a jail holds more than one process: the runner starts one jail per session and starts each program in it. The `runner` contract changes: `start` starts a program in the session's jail; the grades report is the jail's, not each start's; `/release` stops each program through its owner, then ends the jail; a stuck or dead Python process is started again inside the jail, not in a new one. `runner:unconfined` keeps plain processes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Where a jail's program holds namespaces of its own (`Process.namespaces`: bwrap as an unprivileged user, nested user namespaces allowed), a session starts one jail and the Python process and the extensions process both run in it (tested: one jail start for both). Where it does not (darwin, bwrap as uid 0, nested user namespaces blocked), each program keeps a jail of its own (tested: one jail start per program)
- [x] #2 Where a session shares a jail, starting the Python process again (a stuck input, a crash) starts no new jail; where it does not, the new start replaces only that program's own jail, as before
- [x] #3 `/release` stops each program through its owner, then ends every jail nothing runs in; the next start starts a new one
- [x] #4 `--no-jail` behaves as before
- [x] #5 CONTRACTS.md (`runner`), the runner plugin's README and the docs' jail-and-approval page describe one jail per session where the namespaces hold, and a jail per program where they do not
- [ ] #6 `scripts/linux-jail-check` and `scripts/check` pass
- [x] #7 The mount tripwire ends the session's jail with a kill that doesn't depend on the runtime, tells every owner `ended()`, and the next start creates a new jail
- [x] #8 Read allows derived from argv, and `git_author`, are decided at create, not per start
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Updated for the owner's ruling, 2026-11-08 (option A; see the note of that date).

### Order of work

1. `jail.py`: split `_Jailed` in two. `_Held` is one brig jail and what bh-02 holds for it: tether, lock, record, placeholders, tripwire, `jail_dir`, facts; it ends once, through `_Held.end`. `_Jailed` is one program in it. Its `stop` is `Process.stop` where the jail is shared (a stop that can't end the program ends the jail), and the whole jail where it is that program's own. `started.connect` and `start(argv_for, *, cwd)` stay as TASK-0079.31 left them: the task's text predates them.
2. `BrigJail.start`: one start at a time chooses a jail, so two owners starting at once share one. A start joins the shared jail for its resolved `cwd` while that jail is usable, else creates one. A jail is shared only if its first program reports `Process.namespaces`; otherwise the next start creates another, as on those hosts today. A jail found over, or that ends as a start asks, is ended and replaced without failing that owner's start.
3. #8: compile, `git_author` and facts happen once, at create. Read allows are the system tree, the interpreter's trees, `host.code` and what the creating start's argv names. A later start naming an absolute path outside them is refused (`_outside`) and never widened.
4. #7: the wire moves to `_Held`, so every `started.ended()` reads the jail's `tripped`. The end stays `Jail.destroy(grace=0)` with the plain `killpg` fallback. The extensions owner gains `ended()` in its protocol and says why in its status.
5. #3: `BrigJail.release` ends every jail nothing runs in, then sweeps; a jail something runs in stays and `released_for` says so. `BrigJail` is an async context manager entered by the `confined` row, so the jail ends with the row and what it made goes with it. Without that a shared jail's placeholders would outlive a clean exit.
6. #4: `unconfined.py` unchanged.
7. Tests, then #5's docs: `bh-02/CONTRACTS.md`, the runner README, the jail-and-approval page.

### Risks

- A shared jail outlives its programs, so tests that ended a jail by stopping its only program now need `close`. Each assertion stays; only when the jail ends moves.
- Sub-agents share `runner`, so where the bundle holds their REPLs join the session's jail with no change of theirs (decision-0002). The sub-agent's real-jail test had not been able to boot since TASK-0169.05; it is fixed here because it is what exercises this.
- `_Held.usable` uses the instance's process group, because `Jail.alive` reads gone with no program running. A shared jail is always supervised, so it has one.
- A tripwire or a supervisor failure ends every program in a shared jail. That is the point of #7, and every owner is told.
- `linux-jail-check --root` runs the per-program path, so the sharing tests skip there by name: the unprivileged run is what proves sharing.

### Proof

- Isolation: `test_a_program_in_the_session_s_jail_can_t_reach_its_sibling`, real jail, read from the target's own count and the host's dial. Seen failing with the isolation removed (supervisor's probe planted off, the jail forced shared).
- No namespaces: `test_a_host_without_namespaces_keeps_a_jail_per_program_and_they_stay_apart`, real on darwin and uid 0, and `test_a_program_with_no_namespaces_of_its_own_is_not_followed_into_its_jail` for the unprivileged run. Seen failing with the ruling's check removed.
- #1 real workers both orders; #2 stuck and crashed; #3 owners then jail; #7 two owners told, new jail; #8 asked once, refused, reads unchanged; a different `cwd` a jail of its own.
- Runs: `scripts/check`, `scripts/linux-jail-check`, and `scripts/linux-jail-check --root` on the four suites, all through `testlock`, every failure reported with its traceback.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-11: rewired onto decision-0001's split. It no longer depends on TASK-0073 (superseded): it needs a channel per start (TASK-0079.05) and per-process isolation (TASK-0079.07), so the Python process and the extensions process can't reach each other in one jail.

Owner's trim, 2026-10-12: moved out of TASK-0079's finish line to the deferred brig intent TASK-0084. Sub-agents run with a jail each from the same policy until this lands (decision-0002).

Finish moved (recorded 2026-11-06): commit b6b09860 ("Accept the brig and sub-agent intents and decision-0001, and split them") added criteria #7 and #8 when this task was rewired onto decision-0001's runtime/confinement split, requiring the mount tripwire to end the jail independent of the runtime and read allows to be decided at create rather than per start.

Owner stand-in (Opus), 2026-11-06: Approved for this run on the orchestrator's report that Bruk put 0048 and 0074 in it today; it starts only after TASK-0079.31 closes, in the brig lane's order. Its AC #6 needs scripts/linux-jail-check as well as scripts/check; if the lane runs out of room, stopping here is fine (stuck is information).

Stopped before implementing, 2026-11-08 (worker, at d1c60cf7): one design ruling is needed. No code changed; this branch holds the plan and these notes.

Measured: one program (B) attacks another (A) under the runner's own policy (`BrigJail.compile`, then `Jail.create`), each with its own reservation. A's accept count and the host's redial are read outside B. Script: a scratch file, not committed.

| | Linux, uid 1001, bundle held, one jail | Linux, uid 0, no bundle, one jail | Linux, uid 0, two jails (today) | darwin, one jail | darwin, two jails (today) |
|---|---|---|---|---|---|
| connect to A's socket | FileNotFoundError | CONNECTED (A accepted 1) | FileNotFoundError | PermissionError | PermissionError |
| list A's socket directory | empty | A's socket listed | FileNotFoundError | A's socket listed | A's socket listed |
| see A in /proc, signal A | only itself | pids 1, 3, 4; signal 0 DELIVERED | only itself | no /proc; PermissionError | no /proc; PermissionError |
| see A's scratch file | no | yes | no | yes | no (TMPDIR is another path) |
| unlink A's socket | FileNotFoundError | UNLINKED | FileNotFoundError | UNLINKED | PermissionError |
| host's dial of A afterwards | ok | FileNotFoundError | ok | FileNotFoundError | ok |

Runs: `scripts/linux-jail-check --shell` and `--root --shell` under testlock, and directly on this Mac, each exit 0. Corrected from a first run where a signal reading on the bundled jail was false: A and B are both pid 1 in their own namespaces, so B would have signalled itself; that case is now skipped and reported as such.

What it means:
- Linux with the bundle: closed. brig's tests/e2e/test_process_namespaces.py already proves ESRCH for a sibling's signal.
- Linux without the bundle: uid 0 measured here. Blocked nested user namespaces take the same fallback (decision-195), not run in this measurement. One jail opens all of it, where two jails open none. Also, each worker's first non-empty line makes that connection its host: read in python's worker.py (lines 445-455), not attacked here. So a sibling that dials a starting worker first could drive it, inside the same confinement.
- darwin: seatbelt refuses connect and signal, measured but promised by no grade (`channel_exclusivity` is `unenforced`). One jail adds a shared scratch directory and lets a sibling unlink another's socket, so the host can't dial it again until it restarts; a connection already dialled was not tested.
- decision-0001 accepts these as shared media that bh-02 must name. The brief says the two processes must not reach each other. Both can't stand on these hosts.

The question: where `Process.namespaces` is false, does a session still get one jail?
- A (proposed): no. Share only where the bundle holds, and keep a jail per program elsewhere: what those hosts do today, so nothing regresses. #1, #2 and #3 are reworded (`finish-moved`). Cost: one-jail behaviour on bwrap as an unprivileged user only, not on a Mac; a second path stays in the code.
- B: yes, as decision-0001 wrote: one jail everywhere, shared media named in the notice and grade detail. All criteria stay as they are, and the reach in the table is accepted. The `--root` isolation test could only assert the notice.
- C: A on Linux, and one jail on darwin once brig narrows each start's channel and scratch grants (seatbelt's profile is applied per start, so this looks possible but is unproven): a brig task first, then darwin joins.

Not blocking, my readings for the owner to confirm:
- #7: `Jail.destroy(grace=0)` with the existing plain `os.killpg` of the instance group as fallback is the kill that doesn't depend on the runtime (brig decision-193, later than the criterion). Only the wire's owner changes.
- #8: "at create" means from the argv of the start that creates the jail, plus `host.code` and the interpreter. Both workers sit in `host.code` directories (their paths are beside each package's `__file__`; not yet checked in a running jail). A later start outside those allows is refused, never widened.
- A start with another `cwd` gets a jail of its own, since one jail can't widen its write roots.

This is one change, not a split: size-5 fits once the ruling is in.

Owner's ruling, 2026-11-08: option A. Where `Process.namespaces` is false a session does not share a jail: it keeps a jail per program, so nothing regresses. Why: the measurement table above (Stopped before implementing, 2026-11-08) shows one jail lets a co-tenant connect to, signal and unlink a sibling's socket on Linux as uid 0, and unlink it and share its scratch on darwin, where two jails allow none of those. What changed: #1, #2 and #3 reworded to that, #5 to match them, `finish-moved` added. One jail per session now holds only on bwrap as an unprivileged user with nested user namespaces allowed; on darwin, as uid 0 and where nested user namespaces are blocked, a session keeps a jail per program. darwin's part of option C is TASK-0217, not this task. Also confirmed by the owner: #7 is `Jail.destroy(grace=0)` plus the existing plain `killpg` fallback; #8's 'at create' is the creating start's argv plus `host.code` and the interpreter, a later start outside those refused and never widened; a different `cwd` gets its own jail.

Worker, 2026-11-08, implemented to the owner's ruling, on main 4d432d2e.

What changed: `jail.py` splits `_Jailed` into `_Held` (one brig jail and what bh-02 holds for it) and `_Jailed` (one program in it). `BrigJail.start` chooses one start at a time: it joins the shared jail for the resolved `cwd`, or creates one, and shares it only if the first program reports `Process.namespaces`. `BrigJail` is an async context manager the `confined` row enters, so the jail ends with the row and its placeholders go with it. The extensions owner reads `ended()`. `unconfined.py` has no diff against main. Contract, README and docs page follow.

Evidence by criterion:
- #1: `test_on_linux_the_real_workers_share_one_jail_whichever_starts_first` (the installed Python and extensions workers, both orders: one record with namespaces, two without; passes as bh and root); `test_a_session_starts_one_jail_for_both_programs_even_starting_at_once` (bh). Without namespaces: `test_a_host_without_namespaces_keeps_a_jail_per_program_and_they_stay_apart` (darwin, root, real) and `test_a_program_with_no_namespaces_of_its_own_is_not_followed_into_its_jail` (bh, faked `_Plain`).
- #2: `test_starting_a_program_again_starts_no_new_jail_and_leaves_its_sibling_running`, `test_a_program_that_crashed_starts_again_in_the_same_jail`.
- #3: `test_release_stops_through_owners_then_ends_the_jail_and_the_next_start_makes_a_new_one`.
- #4: no diff in `unconfined.py`; its tests pass unchanged.
- #5: `bh-02/CONTRACTS.md`, runner README, `docs/bh-02/how-it-works/jail-and-approval.md`.
- #6: left unticked for the reviewer; runs below.
- #7: `test_the_tripwire_ends_the_session_s_jail_tells_every_owner_and_the_next_start_makes_a_new_one`; `test_a_worker_the_jail_ended_says_why_as_every_owner_of_that_jail_is_told`.
- #8: `test_what_a_shared_jail_reads_and_who_commits_is_decided_when_it_is_created`; `test_a_program_in_another_directory_gets_a_jail_of_its_own`.

Required tests, how each was seen failing:
- Isolation, `test_a_program_in_the_session_s_jail_can_t_reach_its_sibling`, with the jail forced shared and its skip guard bypassed. As bh with the supervisor's namespace probe planted off: `assert accepted == 0` failed, attacker report connect CONNECTED, socket listed, pids [1, 3, 4]. As root, the natural jail without the bundle: the same, before the harness fix. After the fix, repeated as bh: failed the same way. Plants restored by sha256.
- No namespaces, with the ruling's check removed: root, `assert len(set(made)) == 2` failed on one jail directory. bh (`_Plain`): `len(groups) == 2` failed, one group. darwin: failed, but on the shared jail's refusal of a later start (seatbelt's Spec names no read allows, so `_outside` refuses), not on that assertion.

The isolation test's one failure was a harness race, shown, not a reach between programs. It failed 1 in 16 full parallel runs as first written, with no traceback kept. Cause: the target counts a connection some time after the kernel takes it, so the host's own readiness dial could land between the test's two reads of the count. Forced with a 0.5 s delay in the target and a 1 s wait before the second read: `accepted` 1 with a clean report. Then caught unforced with the unfixed harness restored, run 4 of a loop: `assert 1 == 0` with report pid 1, connect FileNotFoundError, listed [], pids [1]. (That message truncates the report's other keys.) The attacker never found the socket. Fixed: the count starts once the readiness dial is in it, and ends after a host dial of its own. Fixed harness: passes with the target counting slowly, 0 failures in 20 full parallel runs (10 of them on the rebased code).

Other failures seen, none rerun away:
- `test_a_linux_jail_ends_when_the_host_renames_over_a_write_deny_and_a_new_one_holds_it` (TASK-0218): one line `# planted by the jail` written after Pat, so the first jail's write in the tripwire's known window, not the second jail's (it would write about five). Full parallel runs: branch 3 of 30 with the name kept (1 of 6, 1 of 10, 0 of 4, 1 of 10), plus 1 more failed run in 10 whose test name was not kept, and 2 failed single runs. Baseline 0 of 16. Serial: branch 2 of 30, baseline 1 of 30. So the failure predates this task; the kill path has no logic change (`Jail.destroy(grace=0)`), but this does not rule out that it became more frequent under load.
- `test_a_linux_jail_ends_when_the_host_replaces_or_removes_a_secret_it_holds` (TASK-0211): failed once on the branch, run 4 of the unfixed-harness loop, and on the baseline in 2 of 16.

Not run: a Linux host whose nested user namespaces are really blocked (brig's own tests plant that; here uid 0 and `_Plain` stand for it).

Final runs on the rebased code, each under testlock, each exit 0: `scripts/check` 3872 passed, 242 skipped, gates and docs ok, tokens skipped (no bh-01 build beside this worktree). `scripts/linux-jail-check` 341 passed, 5 skipped. `scripts/linux-jail-check --root` four suites 710 passed, 12 skipped, 8 of them the sharing tests, by name. Ten full parallel runs as bh on the rebased code, subagents included: 9 clean at 855 passed, 5 skipped, 1 failed as above.

More from the worker, 2026-11-08:

- TASK-0207's test is changed here, for the owner to see. `test_a_child_s_python_runs_in_a_jail_of_its_own_under_the_confined_runner` is now `test_a_child_s_python_shares_the_session_s_jail_only_where_they_are_kept_apart`, so TASK-0207's title names a test that no longer exists. It failed 16 of 16 on the baseline. Cause, seen in the loader's status: `ContractViolation('runner: host is bound to a _Host, which is missing key_envs, models_file')`. a1d94488 (TASK-0169.05) made `confined` require those fields and the test's fake was never given them, so it was the fake, not the container. Why it is touched here: decision-0002 puts a child's REPL in the session's jail, and this is the one test that runs that for real. It now passes as bh and as root. TASK-0207 itself is left open for the owner: its #1 looks answered and its #2 met.
- Renamed `test_each_start_keeps_what_it_is_whatever_the_jail_starts_after_it` to `test_a_jail_per_program_keeps_what_it_is_whatever_starts_after_it`: it runs only on the per-program path (`_plain_launch`, no namespaces), so its old name stated a contract that no longer holds in a shared jail. Its assertions are unchanged.
- One assertion was removed, for the reviewer to judge: in `test_on_linux_the_python_process_tells_the_model_its_own_worker_s_trees_when_another_starts`, `str(elsewhere) not in process.reads()`. The stand-in worker now has to be in `host.code` to start in a shared jail, so every jail reads it. What replaces it: `process.reads()` and `process.instructions()` are unchanged by the second start and its stop. The per-program form of the removed claim is still asserted by the renamed test above, as an unprivileged run with `_Plain`.
- Root `pyproject.toml`: one line, `_Held.*` added to the `no-impure-functions` budget. It is the split half of the already budgeted `_Jailed.*` (`_write`, `end`, `_teardown` moved there), not new impure surface.
- `_outside` assumes a read allowlist: on darwin `read_allows` is empty, so it would refuse every later start. Unreachable today, since darwin never shares, but TASK-0217 will hit it.
- TASK-0218 was filed on this branch, since the rename-over failure is outside this task's criteria. Rename-over's numbers carry one more caveat: the branch's parallel run has 855 tests against the baseline's 842, more of them real jails, and the window the test depends on is load-sensitive, so the two rates are not from equal load.

Final runs on the final code (the earlier runs noted above came before one test's rename and docstring), each under testlock. `scripts/check` exited 1: 1 failed, 3871 passed, 242 skipped; format, lint, types, gates and docs ok; tokens skipped (no bh-01 build beside this worktree). The failure: `test_extensions_host.py::test_an_extension_that_ends_the_worker_is_not_loaded_again_until_something_changes`, `PermissionError: [Errno 1] Operation not permitted` at `os.killpg` in `extensions_cordis_plugin/testing.py`'s fake `_Started.stop`, on darwin. That is TASK-0216's signature, with the same traceback recorded on TASK-0079.31 before this task; this task added only `ended()` and `why` to that fake, not to `stop`. Not rerun. The commit before the rename gave exit 0, 3872 passed. `scripts/linux-jail-check` exit 0, 341 passed, 5 skipped. `scripts/linux-jail-check --root` on the four suites exit 0, 710 passed, 12 skipped. #6 stays unticked: the reviewer's, and this run's `scripts/check` is not green.

Owner's ruling, 2026-11-08: "must not reach each other" includes a shared /dev/shm, fixed before this merges (found by a pre-merge review). No criterion's text changes; #1's isolation now rests on brig's decision-211. `finish-moved` is already set.

Measured from inside a shared jail with namespaces held, Linux container, uid 1001; B attacks what A made, under the runner's own policy. Two jails is the control.

| Medium | One jail, before | Two jails | One jail, after decision-211 |
|---|---|---|---|
| `/dev/shm` file | B reads and writes it | not found | not found |
| `/dev/pts/N` (a terminal A holds) | B lists, opens, writes; A receives it | not listed | not listed |
| `$TMPDIR` | not found | not found | not found |
| `/tmp`, `/dev`, `/home` | A can't write | same | same |
| `/var/tmp`, `/run`, `/run/lock`, `/var/lock`, `/dev/mqueue`, `/root`, `/mnt`, `/media`, `/opt`, `/srv`, `/sys/fs/cgroup` | absent | absent | absent (after: `/var/tmp` onward not printed by the filtered run; the fix adds no such path) |
| POSIX message queue | not found | not found | not found |
| System V shm, semaphore, message queue | not found | not found | not found |
| Abstract socket | refused | refused | refused |
| Loopback port | refused | refused | refused |
| IPC, pid, net, mount, user namespace | per process | per process | per process |
| UTS, cgroup namespace | shared; `sethostname` EPERM for both, cgroup reads `0::/` | per jail; the same values | shared, unchanged: nothing to change or read |
| User keyring | not found | not found | not found |
| **Session keyring** | **B finds A's key** | **B finds A's key, same id** | **unchanged: not closed, TASK-0219** |
| Project directory | shared by design, out of scope | shared | shared |

Every writable mount B has, by `/proc/self/mountinfo`, was `/dev/shm`, its own channel and scratch directories and the project.

Fix: brig decision-211, `isolate` mounts a fresh tmpfs on `/dev/shm` and a new devpts instance on `/dev/pts` in each process's mount namespace. `probe_namespaces` runs `isolate`, so a host refusing either falls back as graded. Not fixed: the session keyring, since two jails do not keep it apart, so it is outside the ruling's rule; decision-211 and the docs name it, and TASK-0219 is filed.

How each attack was seen failing:
- Without the fix, as bh: brig's `test_a_process_has_a_dev_shm_of_its_own[namespaces]` (`before: ['a.shm']`), `test_a_process_can_not_see_or_type_at_a_siblings_terminal[namespaces]` (`listed: ['0'], typed: ['0']`), the sub-agent test (`'planted' not in ['planted']`). `test_a_program_in_the_session_s_jail_can_t_reach_its_sibling` failed on dev_shm, dev_shm_changed, ptys, typed_at, typed_received; again with the attack in its final form and the two mounts planted off.
- With all isolation removed (supervisor's probe off, jail forced shared, media checked first), as bh, the same test failed on all 12: dev_shm, dev_shm_changed, ptys, typed_at, typed_received, mq, sysv_shm, sysv_sem, sysv_msg, abstract, loopback, same_ipc. Plants restored; tree clean.
- One attack bug found and fixed: `dev_shm_changed` opened with "a", which created a file in the attacker's own `/dev/shm` and read as a change. It opens with "r+" now.

Not verified: `/dev/shm` and devpts on a host other than this container; darwin is not touched (no namespaces, a jail per program).

Final runs with decision-211, each under testlock, on the final code. `scripts/check` exit 0: 3872 passed, 248 skipped; gates and docs ok; tokens skipped (no bh-01 build beside this worktree). `scripts/linux-jail-check` exit 0: 347 passed, 5 skipped. `scripts/linux-jail-check --root` on the four suites exit 1: 1 failed, 709 passed, 12 skipped. The failure: `test_a_linux_jail_ends_when_the_host_replaces_or_removes_a_secret_it_holds`, `assert not seen.exists()` at the third start, as root. That is TASK-0211's failure: `seen` is never removed between starts, and the second jail's program can write it in the tripwire's window. As root this path is a jail per program, which this change's mounts do not touch. Not rerun. The same run on the code one docstring earlier exited 0, 710 passed, 12 skipped. #6 stays unticked: the reviewer's, and this root run is not green.
<!-- SECTION:NOTES:END -->

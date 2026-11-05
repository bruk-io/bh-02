---
id: TASK-0194
title: Sub-agents get the grant tool, asking as the agent
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-04T22:39:00Z'
updated_date: '2026-11-05T04:19:00Z'
labels:
  - runner
  - subagents
  - size-2
dependencies: []
modified_files:
  - bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/wiring.py
  - bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/requesting.py
  - bh-02/plugins/subagents-cordis-plugin/src/subagents_cordis_plugin/agents.py
  - bh-02/plugins/subagents-cordis-plugin/src/subagents_cordis_plugin/child.py
  - bh-02/app/src/bh_02/bh-02.toml
  - bh-02/app/tests/conftest.py
  - bh-02/CONTRACTS.md
  - bh-02/GLOSSARY.md
  - docs/bh-02/using/jail.md
  - docs/bh-02/how-it-works/jail-and-approval.md
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A sub-agent's conversation is made of the agents row's rows (bh-02.toml: loop, tools, transcript, model, system, asides, access, memory, on-touch, executor, python), and grant-prompt is not among them, so the child's own tools row has no grant tool: a sub-agent's input that calls tools.grant(...) gets an unknown tool, and its system prompt has no grant section. Its standing needs (python config needs) and its refused connections are asked as the agent (TASK-0181.08). To decide: does a sub-agent get grant()? If yes, it must not use requesting.ASKER (Asker(Source.INPUT, 'python'), runner_cordis_plugin/requesting.py:21), which grant_prompt's grant() always uses; the request is asked as the agent, by its label. Found in review of TASK-0181.08 (first filed as the label alone).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A sub-agent has the grant tool and its system section; a call asks the person under the agent's label (agent NAME (TYPE)), never as input python
- [x] #2 The session's grant tool still asks as input python, and there is still one prompt and one /grants per session
- [x] #3 The docs and READMEs no longer say a sub-agent has no grant tool, and say a sub-agent's grant applies to the session
- [x] #4 scripts/check and scripts/linux-jail-check (both modes) pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Starts from bbf66ad's successor on bhabtu/quirky-ride-g68g31 (this task's promotion). The owner decided on 2026-11-05 that sub-agents get the `grant` tool.

### Order of work

1. runner plugin, split the tool from the prompt. `runner:grant_prompt` keeps what there is one of per session: `grants.serve(prompt)`, the asides that tell the model what was decided, and `/grants`. A new component, `runner:grant_tool` (wiring.py), registers the `grant` tool (`runs="harness"`) and the `system` section `grants`. It depends on `grants`, `tools`, `system`, `runner` and `approval`, with config `agent: str = ""`. Its asker is `Asker(Source.AGENT, agent)` when `agent` is set and `Asker(Source.INPUT, "python")` otherwise. This replaces the fixed `requesting.ASKER`: a pure `requesting.asker(agent)` returns the asker. A child can't mount `grant_prompt`, because that would serve a second prompt on the one broker the realm exposes. It can mount `grant_tool`, which only asks.
2. bh-02.toml: a `grant` row (`use = "runner:grant_tool"`) beside `grant-prompt`. Add `"grant"` to the agents row's `rows`, so every child has it. It isn't one of the type-grantable `tools`: its only effect is a question to the person, so it widens nothing a type limits.
3. subagents plugin: `AgentsConfig.python_row` becomes `agent_rows: Sequence[str] = ("python", "grant")`. Every row named there that the child has gets the child's label written into its config as `agent` (child.py, agents.py). Breaking the old config key is fine: there's no released format to keep.
4. Tests:
   - runner: `grant_tool` with `agent` set asks as `agent general-1 (general)`. Without it, the tool asks as `input python`. The existing `grant` tool tests move to the new row.
   - subagents: a child's `grant` row config carries its label.
   - app: test_child_boot.py (or the nearest real-composition test) shows a child's tool list includes `grant`, and that a child's `grant` call reaches the person's question labelled with the agent. The `NO_AGENTS` snippet in bh-02/app/tests/conftest.py disables the new `grant` row as well as `grant-prompt`.
5. Docs: CONTRACTS.md (the two components), the runner and subagents READMEs, GLOSSARY (`grant` tool), docs/bh-02/using/jail.md and how-it-works/jail-and-approval.md. Each currently says a sub-agent has no `grant` tool; that line goes, and each says a sub-agent's request shows its label.

### Risks

- A grant a sub-agent gets applies to the whole session (every jail), the same as a need or a refused connection. The question names the agent, so the person decides knowing that. The docs say it.
- The parent's asides still tell the parent model about an answer to a child's request. That's harmless (the grant reaches the parent's jail too) and stays.
- Splitting the row means a layer that mounts `grant-prompt` without `grant` has no tool. The shipped layer mounts both.

### Proof

scripts/check; scripts/linux-jail-check in both modes. Plant a failure: with the child's `agent` not written into the `grant` row, the label test fails (seen, then restored).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner's decision, 2026-11-05: yes, give sub-agents the grant tool.

Check `scripts/check` exited 1

(35 earlier lines omitted)
```text
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
........................................................................ [ 84%]
...............................................F........................ [ 87%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 95%]
........................................................................ [ 97%]
............................................................             [100%]
=================================== FAILURES ===================================
___ test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts ___
[gw1] linux -- Python 3.15.0 /home/user/bh-02/.claude/worktrees/agent-ae0759bc028fa5a40/.venv/bin/python

    async def test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts() -> None:
        """The defaults, undriven: about once a second, so nothing for the first moments, then
        the seconds."""
        app = BhApp()
        async with app.run_test(size=_SIZE) as pilot:
            app.post_message(ReplyStarted())
            await pilot.pause(0.4)
            assert _line(app) is None
            await _until(pilot, lambda: _line(app) is not None, within=3.0)
>           assert re.fullmatch(r"Working · [12]s", _line(app) or "")
E           AssertionError: assert None
E            +  where None = <function fullmatch at 0x7f725e3519b0>('Working · [12]s', ('Working · 0s'))
E            +    where <function fullmatch at 0x7f725e3519b0> = re.fullmatch
E            +    and   'Working · 0s' = _line(BhApp(title='bh-02', classes={'-dark-mode', '-theme-bh-01-dark'}, pseudo_classes={'focus', 'dark'}))

bh-02/plugins/tui-cordis-plugin/tests/test_tui_working.py:319: AssertionError
=========================== short test summary info ============================
FAILED bh-02/plugins/tui-cordis-plugin/tests/test_tui_working.py::test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts
1 failed, 2790 passed, 6 skipped, 1 xfailed in 130.76s (0:02:10)
   FAILED: tests
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
INFO    -  Building documentation to directory: /home/user/bh-02/.claude/worktrees/agent-ae0759bc028fa5a40/site
INFO    -  Documentation built in 2.76 seconds
   ok
== tokens
   skipped: no /home/user/bh-02/.claude/worktrees/bh-01/dist (bh-01, built, beside this repository)
```

Check `scripts/linux-jail-check --ca /root/.ccr/ca-bundle.crt` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
Installed 1 package in 1ms
Error: docker is not answering: this check needs a running Docker daemon
```

Check `scripts/linux-jail-check --ca /root/.ccr/ca-bundle.crt` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
Error: docker is not answering: this check needs a running Docker daemon
```

Check `scripts/linux-jail-check --ca /root/.ccr/ca-bundle.crt` exited 0

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== image bh-02-linux-jail (ubuntu 24.04, bubblewrap, uv, Python 3.15)
sha256:9a69e522a6048e53106ebe3e868f30c136ec18fd02411955fa2b7b4a24ad109b
== uv run --locked pytest -q -p no:cacheprovider bh-02/plugins/runner-cordis-plugin bh-02/plugins/python-cordis-plugin bh-02/plugins/extensions-cordis-plugin bh-02/app/tests/test_python_repl.py
bubblewrap 0.9.0
uv 0.13.7 (x86_64-unknown-linux-gnu)
Python 3.15.2 (main, Oct 26 2026, 14:06:56) [Clang 23.1.3 ]
........................................................................ [ 13%]
...............................x........................................ [ 26%]
........................................................................ [ 40%]
........................................................................ [ 53%]
........................................................................ [ 67%]
........................................................................ [ 80%]
........................................................................ [ 93%]
..............s..................                                        [100%]
535 passed, 1 skipped, 1 xfailed in 122.30s (0:02:02)
```

Check `scripts/linux-jail-check --as-root --ca /root/.ccr/ca-bundle.crt` exited 0

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== image bh-02-linux-jail (ubuntu 24.04, bubblewrap, uv, Python 3.15)
sha256:cf277ec11ca111723ceef38a55f3161d4ec7db6d65b60ca7a2a98593edc90e7c
== uv run --locked pytest -q -p no:cacheprovider bh-02/plugins/runner-cordis-plugin bh-02/plugins/python-cordis-plugin bh-02/plugins/extensions-cordis-plugin bh-02/app/tests/test_python_repl.py
bubblewrap 0.9.0
uv 0.13.7 (x86_64-unknown-linux-gnu)
Python 3.15.2 (main, Oct 26 2026, 14:06:56) [Clang 23.1.3 ]
........................................................................ [ 13%]
...............................x........................................ [ 26%]
........................................................................ [ 40%]
........................................................................ [ 53%]
........................................................................ [ 67%]
........................................................................ [ 80%]
........................................................................ [ 93%]
..............s..................                                        [100%]
535 passed, 1 skipped, 1 xfailed in 137.25s (0:02:17)
```

Implemented: runner:grant_tool (config agent) split from runner:grant_prompt; requesting.asker(agent) replaces ASKER (via egress.asked_as); bh-02.toml grant row, added to the agents row's rows; AgentsConfig.python_row replaced by agent_rows=(python, grant); docs updated. Planted failure seen: with the grant row skipped when writing the child's agent label, test_child_boot::test_the_agents_row_rewrites_those_fields_of_the_shipped_rows failed (KeyError 'agent'), restored and green. scripts/check: only the known flake DRAFT-0028 failed (2790 passed). scripts/linux-jail-check both modes: 535 passed each (the Docker daemon had to be started with dockerd). ACs left unticked for the reviewer.

Check `scripts/check` exited 0

(13 earlier lines omitted)
```text

........................................................................ [  2%]
........................................................................ [  5%]
................s....................................................... [  7%]
...................................x.................................... [ 10%]
........................................................................ [ 12%]
........................................................................ [ 15%]
........................................................................ [ 18%]
....s................................................................... [ 20%]
........................................................................ [ 23%]
........................................................................ [ 25%]
........................................................................ [ 28%]
........................................................................ [ 30%]
........................................................................ [ 33%]
.ss..................................................................... [ 36%]
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
........................................................................ [ 84%]
........................................................................ [ 87%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 95%]
........................................................................ [ 97%]
............................................................             [100%]
2791 passed, 6 skipped, 1 xfailed in 168.14s (0:02:48)
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
INFO    -  Building documentation to directory: /home/user/bh-02/.claude/worktrees/agent-ae0759bc028fa5a40/site
INFO    -  Documentation built in 2.58 seconds
   ok
== tokens
   skipped: no /home/user/bh-02/.claude/worktrees/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->

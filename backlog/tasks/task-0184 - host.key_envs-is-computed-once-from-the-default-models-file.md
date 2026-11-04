---
id: TASK-0184
title: host.key_envs is computed once from the default models file
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T13:26:00Z'
labels:
  - models
  - credentials
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: bh_02/cli.py computes key_envs at boot from the models file's default path only, with the app's own parser (bootstrap.py), separate from the models plugin's. A layer pointing the model row at another models file, or an endpoint added mid-session, gives a key variable runner:confined won't refuse and ! commands pass through. Proposed: models:catalog provides key_envs() read fresh, and the runner and shell_command ask it at each start (the catalog depends only on loader, so no new reloads). Related unguarded rules: runs='memory'/'harness' honoured from any row (a pypeeker rule could restrict the literals), and system/asides contributors must not need the event loop.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The runner refuses, and ! withholds, every key variable of every endpoint the model row can reach: the default models file, the row's models file and its extra endpoints; repro test: a layer pointing the model row at another file whose key is { env = 'OTHER_KEY' } with runner.toml listing OTHER_KEY is refused
- [x] #2 The set is read fresh at each start, so an endpoint added mid-session counts; tested
- [x] #3 The draft's related unguarded rules move to drafts of their own
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).

Repro at 7d921d4b237a, test files: bh-02/app/tests/test_host_values.py; command: `uv run pytest bh-02/app/tests/test_host_values.py -q -k another_layer` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
F                                                                        [100%]
=================================== FAILURES ===================================
_ test_the_runner_refuses_a_variable_a_key_reads_in_the_models_file_another_layer_names _

composition = <function composition.<locals>.layer at 0x7fb58cad8670>
tmp_path = PosixPath('/tmp/pytest-of-root/pytest-698/test_the_runner_refuses_a_vari0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7fb58cac8770>

    def test_the_runner_refuses_a_variable_a_key_reads_in_the_models_file_another_layer_names(
        composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TASK-0184: the variables a key reads are those of every endpoint the model row can reach,
        not only the default models file's. A layer pointing the row at another file, whose key reads
        OTHER_KEY, with OTHER_KEY in runner.toml, stops the runner row."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        config = tmp_path / "xdg"
        (config / "bh-02").mkdir(parents=True)
        (config / "bh-02" / "runner.toml").write_text('env = ["OTHER_KEY"]\n')
        other = tmp_path / "other.toml"
        other.write_text(
            '[elsewhere]\nprovider = "openai"\nbase_url = "http://localhost:1/v1"\nkey = { env = "OTHER_KEY" }\n'
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
        work = tmp_path / "work"
        work.mkdir()
        monkeypatch.chdir(work)
        patch = composition(
            '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
            '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
            f'[[plugin]]\nid = "model"\nconfig = {{ models = "{other}" }}\n'
            '[[plugin]]\nid = "runner"\nuse = "runner:confined"\n'
        )
        result = CliRunner().invoke(main, ["--patch", str(patch)])
>       assert result.exit_code == 1, result.output
E       AssertionError: session 20261104-131000-480d  (uv run bh-02 --resume to continue it)
E         
E       assert 0 == 1
E        +  where 0 = <Result okay>.exit_code

/home/user/bh-02-keys/bh-02/app/tests/test_host_values.py:233: AssertionError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_host_values.py::test_the_runner_refuses_a_variable_a_key_reads_in_the_models_file_another_layer_names
1 failed, 7 deselected in 2.70s
```

Fix: models:catalog.key_envs() (catalog.py) reads the model row's models file and extra fresh at each call; runner:confined depends on 'models' (not host.key_envs), refuses at row start and again at each program start (_Rechecked in runner wiring), commands:shell_command asks per command. host.key_envs/models_file, bootstrap.key_variables/models_keys and their cli computation removed (no duplicate parser). Catalog depends on loader only, so no new reloads. Tests: repro test_host_values (seen failing, exit 0 instead of 1, before the fix; recorded with record-check --repro; passes after); catalog key_envs tests; runner re-check test seen failing with the per-start check removed; shell_command mid-session test. A models file in the project adds nothing, its extra still counts; a bad row cwd makes key_envs raise ModelsError (fail closed). Checks: scripts/check for runner (with gates, docs) exit 0; --no-gates --no-docs for commands, models, app, subagents exit 0; arch-check --no-fix exit 0; mypy clean. AC1 and AC2 not ticked (reviewer). AC3: the two side rules (runs=memory/harness from any row; system/asides contributors needing the event loop) are not done here; no draft filed by me, see report.

Lead, 2026-11-04: criterion 3's two side rules filed as drafts (runs=memory/harness honoured from any row; system and asides contributors needing the event loop).

Check `scripts/check` exited 0

(11 earlier lines omitted)
```text
bringing up nodes...
bringing up nodes...

........................................................................ [  2%]
........................................................................ [  5%]
...s.................................................................... [  8%]
.........x.............................................................. [ 11%]
........................................................................ [ 13%]
........................................................................ [ 16%]
........................................................................ [ 19%]
...................................s.................................... [ 22%]
........................................................................ [ 24%]
........................................................................ [ 27%]
........................................................................ [ 30%]
........................................................................ [ 33%]
........................................................................ [ 36%]
......................ss................................................ [ 38%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 47%]
........................................................................ [ 49%]
........................................................................ [ 52%]
........................................................................ [ 55%]
........................................................................ [ 58%]
........................................................................ [ 60%]
........................................................................ [ 63%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 80%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 99%]
.......                                                                  [100%]
2594 passed, 6 skipped, 1 xfailed in 142.49s (0:02:22)
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
INFO    -  Building documentation to directory: /home/user/bh-02-keys/site
INFO    -  Documentation built in 2.85 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Reviewer, 2026-11-04: verdict closes on the criteria, but close-task refused: the repro file bh-02/app/tests/test_host_values.py changed since 7d921d4. The repro function itself is unchanged; the file lost the tests of the removed key_variables/models_keys/host.key_envs and one assertion that the refusal names the models file. Status left In Progress; the lead decides whether to record a new repro (record-check --repro) or accept. Full check (scripts/check) exit 0, first line a uv UV_NATIVE_TLS deprecation warning, nothing reformatted; 2594 passed. AC1, AC2 met and ticked (repro test; catalog per-call read; runner re-check per program start; ! per command). AC3 met: DRAFT-0024, DRAFT-0025. Fail closed: a bad cwd's ModelsError propagates out of runner start and the ! run, so neither starts. Empty sets come only from a row that is not models:model, a file not read, and an invalid key table (DRAFT-0027). A project models file adds nothing, as before: the model row refuses to read it, so none of its keys is used, and the variable is in runner.toml by the person's own choice; accepted, not filed. No test uses a real credential. Findings: CONTRACTS.md host row still lists key_envs and models_file -> DRAFT-0026. key_envs() skips an env key whose table has another problem (ttl_ms, unknown field), against its docstring and the old parser -> DRAFT-0027. Minor, not filed: the refusal no longer names which models file; key_envs reads the file synchronously on the event loop at each start and ! command.
<!-- SECTION:NOTES:END -->

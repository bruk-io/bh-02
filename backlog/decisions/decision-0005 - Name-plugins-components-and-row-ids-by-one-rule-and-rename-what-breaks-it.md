---
id: decision-0005
title: 'Name plugins, components and row ids by one rule, and rename what breaks it'
date: '2026-10-14 16:38'
status: accepted
---
## Context

The owner (2026-10-14): the naming is hurting my head. TASK-0099 swept the shipped composition,
CONTRACTS.md and GLOSSARY.md and found no written rule. Fable, standing in for the owner, answered
most of its questions (they are TASK-0099's, settled, not reopened here): the rule's wording; the
sub-agents plugin is `subagents` with the row id `agents` kept and `agents_status` becoming
`agents-status`; the startup files are `startup.py`, the python row's class `PythonProcess`; the
glossary's double meanings stay with labels; an old `kernel.py` keeps running for good.

What this record adds, as TASK-0099.01 asked: the rule worded to go into `bh-02/CLAUDE.md`; the
component name `agents:agents` takes; a sweep of every component and row id against the rule; and,
for each rename, the files it touches and how a person's layers and resumed sessions translate it.

How an old name is translated today (TASK-0064's precedent). `bh_02/outdated.py` holds two tables:
`_RENAMED` (a row id) and `_RENAMED_USES` (a `plugin:component`). `translated` rewrites a layer and
says one line per change; `bh-02 update-layer FILE` writes it back (keeping `FILE.bak`); a resumed
session's own layer is translated silently (`sessions.update`); a `--patch` file is the person's, so
the command line refuses it with those lines. A file name is not a layer: nothing in `outdated.py`
translates one.

## Decision

### 1. The rule

Worded to go into `bh-02/CLAUDE.md` as a "Naming" section after "Adding a plugin", which points to it.

> **Names say what they name.** A layer author reads `id` and `use` and should know what fills the
> role without opening the plugin.
>
> - A **plugin** is named for its subject, as a user would say it (`agent`, `runner`, `python`,
>   `subagents`). No two plugin names differ by a letter or a plural.
> - A **component** is named for what it is, read after its plugin's name (`commands:registry`,
>   `models:catalog`, `agent:tools`, `python:tool`), and never repeats its plugin's word, in the
>   singular or the plural, unless it is named for the key it binds, whose name its consumers fix
>   (`models:model` binds `model`). A broker whose key is its plugin's own name takes the kind for
>   its component (`registry`, `catalog`). The one kept stutter is `tui:ui`: TASK-0064 gave the
>   Textual app one name for its function, component and row, and `tui:app` would bring the third
>   back.
> - A **row id** is the key the row binds, when it binds one key and that key names what fills the
>   role (`loop`, `tools`, `commands`); else its role (`ui` binds three keys, `agents` two, `python`
>   none; `chat` binds `done`, a signal the shell waits on, not the thing that fills the role). Ids
>   are lowercase words joined by hyphens (`memory-auto`); components are Python names (`on_touch`).
> - **One word, one thing.** A thing seen from two places keeps its word with a label saying where
>   (`tools`: the broker row and key, and the namespace's view in an input; `python`: the tool, and
>   the row). GLOSSARY.md holds each label, and a new term goes there.
> - **A rename is translated, not abandoned.** A row id or component a person may have written goes
>   into `bh_02/outdated.py` (`_RENAMED`, `_RENAMED_USES`), so `bh-02 update-layer` and a resume say
>   what changed; a file the person owns is read under its old name for good, with a line saying the
>   new one. Rename symbols with `pypeeker rename` (`demote` only makes one private).

"Repeats" means the same word, plural or not, or the word a plugin's name is built on:
`agents:agents` and `extensions:extensions` repeat, and `subagents:agents` would. `models:model` is
the one place the key's-name exception applies. `tui:ui` reads as a stutter and is kept on purpose,
named in the rule (see the sweep).

### 2. The component of the `agents` row: `subagents:parent`

| Candidate | For | Against |
|---|---|---|
| **`parent`** (Fable's lean) | The plugin's own prose already calls this row's side "the parent": the parent's `output`, its rows, its loader, "your parent agent". It pairs with `child` (the row each child's realm gets) and `output` (the child's, over `asker`). cordis's own words for a mounted subtree are the same pair: the row is the parent of the realm it mounts (`use(child, ...)`). | It names a position, not a job; a layer author reads `use = "subagents:parent"` as "the parent's side of sub-agents", which is true and enough. |
| `spawner` / `starter` | Names what the `agent` tool does. | The row also tracks (`roster`), asks (`asker`), waits, sends, stops and answers `/agents`; and "spawn" is a word the plugin's prose, the docs and the glossary never use ("start", "mount"). |
| `supervisor` | Starts, watches, stops. | Implies restarts and trees (this repository's `warden` example is a supervisor); nothing here restarts a child. |
| `agents` (keep the function's name under the new plugin) | No component rename at all. | It is the plugin's whole subject again (`subagents:agents`, beside the row `agents` and the tool `agent`): the stutter the owner named, one prefix apart; true to the letter of the rule, not to its reason. And it binds no key `agents`, so the exception for a key's name does not cover it. |

Chosen: **`parent`**. The function `agents_cordis_plugin.wiring.agents` becomes
`subagents_cordis_plugin.wiring.parent`; `:status`, `:child` and `:output` keep their names (decided).

### 3. The sweep

Every row of the shipped layer (`bh-02.toml`), the shell's pinned rows, the child's realm rows, and
every plugin's components, against the rule.

**Breaks the rule:**

| What | Why | Verdict |
|---|---|---|
| plugins `agent` and `agents` | a letter apart, for the loop and its sub-agents | rename `agents` to `subagents` (decided) |
| `agents:agents` | component repeats its plugin | rename: `subagents:parent` (section 2) |
| `agents_status` (row id) | the one id with an underscore | rename: `agents-status` (decided) |
| `extensions:extensions` | component repeats its plugin | rename: `extensions:process` (section 4, row 6) |
| `kernel.py` (the startup files), `Kernel` and `KernelConfig` (the python row's class and config) | name what the file and the class are not: the docs already say startup file and Python process | rename: `startup.py`, `PythonProcess`, `PythonProcessConfig` (decided; TASK-0099.02) |

**Everything else checked and kept**, each with why a rename costs more than it clears:

- **`chat` binds one key, `done`**, so read literally the id would be `done`. Kept: `id = "chat"`
  tells a layer author what fills the role, which is the rule's reason; `id = "done"` would not.
  The rule's wording says so (a key that is a signal, not what fills the role).
- **`tui:ui`**: plugin `tui`, component `ui`. They are not the same word, and TASK-0064 settled on
  one name for the function, the component and the row (`ui`) after three (`tui`, `app`, `ui`);
  `tui:app` would bring the third back.
- **`models:model`, and the rows `model` and `models`** (one letter apart): the model, and the models
  there are. `models:model` is the singular under a plural plugin, which the rule's exception for a
  key's name covers (it binds `model`); the rows are a noun and its plural, each the key its row
  binds, and read as what they are. Renaming either costs 30 files naming `models:model` (and it is
  the target of two earlier translations in `outdated.py`) or every consumer of the `models` key,
  for a pair that does not mislead. The closest call in the sweep; the owner kept it.
- **`memory-auto`, `on-touch`, `shell-command`, `agents-status`** (and `status`, `grades`, `palette`
  in tui): each id is its role; `memory-auto`, `shell-command` and `agents-status` take their
  plugin's or kind's word where the bare role is another row's key or id (`memory`, `status`).
- **Every other component** binds the key it is named for (`agent:loop`, `agent:tools`,
  `agent:system`, `agent:asides`, `agent:access`, `agent:executor`, `agent:transcript`,
  `commands:jobs`, `runner:confined`, `runner:unconfined`, `runner:approval`), or its kind where the
  key is the plugin's own name (`commands:registry`, `models:catalog`, `memory:files`), or does what
  it is named for and binds none (`agent:conversation`, `commands:operator`,
  `commands:shell_command`, `memory:on_touch`, `memory:auto`, `models:switch`, `python:tool`,
  `runner:release`, `tui:status`, `tui:grades`, `tui:palette`, `chat:converse`).
- **The shell's pinned rows** `shell`, `host`, `session` (`bh_02.bootstrap:`), and the child
  realm's rows (`output` from `agents:output`, binding `output`; `agent` from `agents:child`): ids by
  the rule.
- **`runs="harness"`** (a tool registration's value, about a dozen files): not a row id, a
  component or a name a person writes; "harness" is a glossary word with its label (bh-02's own
  process). Kept.
- **Words the glossary uses for several things**, each already labelled, so the rule's second
  clause holds: `tools`, `python` (decided); `input` (the key, and one `python` call), `host` (the
  side outside the jail, and the row), `session` (what a run keeps, and the running one's row),
  `shell` (bh-02's app, and your shell for `!`), `harness` (five senses), `stack` (a session's,
  brig's, a fiber's), and, after the rename, `agent` (the plugin's loop; the tool and the glossary's
  child). One of these names something other than what it holds: a session's `stack` is the model
  it started on (in every session's `meta.json`, the `bh-02 sessions` column). Kept by the owner,
  out of scope (a `meta.json` field, not a plugin, component or row id): a rename needs a read-both-forever shim like `kernel.py`'s for one column and one
  glossary line.
- **Module names inside a plugin** (`prompt.py` next to `system.py`, `toolset.py` next to
  `tools.py`, `jail.py` beside `unconfined.py`): not named by any layer or person, each says what it
  holds in its first line; outside the rule's scope.
- **Test-only fakes** (`bh_02.testing:echo`, `slow_start`, `showcase`, `bomb`, `*_model`): named for
  what they do; not in the shipped layer.

### 4. The rename table

Counts are `grep -l` files outside `backlog/`, the generated `site/`, `.pypeeker/`, `.hypothesis/`
and `__pycache__/`; a file that
needs two renames is counted in each.

| # | Old | New | Touches | How a person's layer or session translates it |
|---|---|---|---|---|
| 1 | plugin `agents`: package `agents_cordis_plugin`, member `agents-cordis-plugin`, entry point `agents` | `subagents`: `subagents_cordis_plugin`, `subagents-cordis-plugin`, `subagents` | package name: 12 files; member name: 9; together with rows 2 to 5, 11 files outside the member (`bh-02/CONTRACTS.md`, `GLOSSARY.md`, `app/README.md`, `app/pyproject.toml`, `bh-02.toml`, `watching.py`, `app/tests/{conftest,test_python_repl,test_watching}.py`, `docs/bh-02/using/commands.md`, root `pyproject.toml`), `uv.lock`, and the word "agents plugin" in prose (`bh_02/testing.py`); the member's own 14 files move | the entry point is the first half of every `use`, so rows 2 to 4 carry it |
| 2 | `agents:agents` | `subagents:parent` | 10 files | `_RENAMED_USES["agents:agents"]` |
| 3 | `agents:status` | `subagents:status` | 8 | `_RENAMED_USES["agents:status"]` |
| 4 | `agents:child`, `agents:output` | `subagents:child`, `subagents:output` | 8 and 7 (`child.py` names both and `agents:agents` as strings) | `_RENAMED_USES`, both. The agents row writes these into each child's realm, so no layer or session names them; the entries cost two lines and make "every use the plugin had" true |
| 5 | row id `agents_status` | `agents-status` | 4 files | `_RENAMED["agents_status"]`. The likely hit is a patch that turns the field off (`id = "agents_status"`, `disabled = true`, no `use`); `_renamed_rows` carries a `clear` list too. A layer that has both ids gets `_clash`'s fold-them line |
| 6 | `extensions:extensions` | `extensions:process` | 10 (8 name the use; `__init__.py` and the test name the function): `README.md`, `bh-02/{CONTRACTS,GLOSSARY}.md`, `app/README.md`, `bh-02.toml`, the plugin's and the runner's READMEs, `wiring.py`, `__init__.py` (the re-export), `tests/test_extensions_host.py` | `_RENAMED_USES["extensions:extensions"]`. The row id `extensions` stays, so `/restart extensions` and a config override of it keep working |
| 7 | `kernel.py`: `$XDG_CONFIG_HOME/bh-02/kernel.py` and `.bh-02/kernel.py` | `startup.py`, same places | 12 files name `kernel.py`; with the class (row 8), 17 in all; `scripts/model-friction` among them (it reads old sessions, so it matches both names) | not `outdated.py`: it is not a layer. The python row reads the old name for good (below) |
| 8 | `Kernel`, `KernelConfig`, `_Kernel` (`worker.py`), `__kernel__` | `PythonProcess`, `PythonProcessConfig`; `_Kernel` and `__kernel__` are TASK-0099.02's call | the 17 above, among them root `pyproject.toml` (purity budget: `python_cordis_plugin.client:Kernel.*`, `worker:_Kernel._run`), `bh-02/CLAUDE.md` (`Kernel.run`) and `libs/host-paths/CLAUDE.md`; 46 files say "kernel" in prose or a test's name (some mean the Linux kernel: judge each hit) | nothing: no class name is in a layer or on disk. `KernelConfig`'s fields keep their names (`startup`...) |

Why `extensions:process` (row 6). The row binds nothing; it owns the extensions process the way
the python row owns the Python process: it watches the directory, loads what is
there into it, relays what an extension adds, asks the `approval` rule, and stops it on `/release`.
GLOSSARY.md already has the term and the sentence ("the process the model's extensions run in";
`python` is "bh-02's handle on the Python process"). Not `loader`: cordis's word, the thing that
reads layers. Not `host`: the shell's row and key. Not `watcher`: one of three jobs.

How the python row reads the startup files (row 7; TASK-0099.02 builds it, under today's reading
rules: the project's in the jail, the person's on the host through `host_paths`, no new path):

1. For each place (the person's, the project's): `startup.py` there runs. A `kernel.py` beside it
   is not read, and the line says so (below).
2. `startup.py` absent and `kernel.py` there: `kernel.py` runs, as the placed file in that entry's
   place: the person's goes through `host_paths.walked` as any startup file does (`_ready`), the
   project's is read by the worker in the jail. The fallback is by name, per configured entry: an
   entry named `startup.py`, default or written out, is looked for as `kernel.py` beside it when
   absent.
3. Neither: nothing, as today.
4. The line, once per Python process start, in the first input's output beside "ran first and
   defined": that the file ran under its old name, that it is called `startup.py` now, and (for
   the project's, which the model may write) to rename it; for the person's, which the model cannot
   write, only that the person's file is called `startup.py` now. When both exist: that `kernel.py`
   is no longer read because `startup.py` exists.
5. The both-exist line matters for one case: a resumed conversation began with the prompt that
   names `.bh-02/kernel.py` (a conversation's prompt is sent unchanged); its model may write
   helpers there again after a `startup.py` appeared, and would lose them silently.
6. A `startup` config naming `kernel.py` explicitly runs as named, with no line; `update-layer`
   does not rewrite it. The prompt (`instructions_for`, built from each entry's configured name)
   names only `startup.py`, whatever is on disk: the fallback changes what is opened, never the
   name the model is told, so the aside is the one place the old name is said.
7. `__kernel__` (the namespace's `__name__`) stays: a person's startup file may test `__name__`,
   a rename breaks that silently, and nothing the model or person sees changes. The one old word
   left; `worker.py` says why beside it. `_Kernel` is TASK-0099.02's call.

### 5. Review against the cordis design

- **What a layer names** is `id`, `use`, `config`, `disabled`. `use` is resolved by
  `cordis.loader.resolve`: the first half is a `cordis.plugins` entry point's name, the second a
  component found by name in that plugin's package. A plugin rename is an entry-point rename and a
  component rename is a function's name; `provides=` declarations do not change.
- **Keys**: none is renamed (`loop`, `tools`, `asker`, `roster`, `done`, ...). A row depends by key,
  so no row's dependencies change and no row reloads because another was renamed.
- **Brokers** stay commutative: `agents-status` still `acquire`s a field of `frame`, the parent row
  still `acquire`s into `tools`, `commands` and `system`; nothing here orders anything.
- **Row ids**: only `agents_status` changes. The ids a config names (`clear`'s `agents`, the agents
  row's `rows`, `/restart agents`, the realm's `agents/NAME/` prefix and the event logs under
  `<session>/agents/`) are `agents`, which stays, so nothing on disk moves.
- **cordis itself is unchanged**: no code in `libs/cordis`; its words (plugin, component, row,
  layer, key, broker) are used as its README defines them. The rule only says how bh-02 picks the
  names those words hold.

## Consequences

- **An installed bh-02 needs a reinstall after the pull that renames a plugin** (rows 1, 6): cordis
  reads entry points from installed metadata, so until `uv tool install --editable ./bh-02/app
  --reinstall` the shipped layer's `use = "subagents:parent"` finds no plugin (the loader's error
  names the plugins installed) and the row is unresolved, reported, never fatal; `uv sync
  --all-packages` does it in a checkout. TASK-0099.03 says it in the app README's install line.
- A person's `--patch` with an old name is refused with the lines until `bh-02 update-layer` rewrites
  it; a resumed session's own layer is translated silently. Both tested for each rename, as
  TASK-0064 did.
- Nothing the model sees changes: the tools `agent`, `agent_wait`, `agent_send`, `agent_stop` and
  `python`, `/agents`, `agents: N running` and the prompt's `agents` section stay. The Python
  process's startup line is the one new sentence (row 7).
- The renames share `outdated.py` and `test_outdated_layers.py`, so they land one at a time, each
  gate-green: TASK-0099.02, TASK-0099.03 and the extensions rename in any order, the rule's section
  in `bh-02/CLAUDE.md` after them (its examples are then true names).
- Kept on purpose, each cheap to reopen: `chat` binding `done`, `tui:ui`, `model`/`models`,
  `runs="harness"`, a session's `stack`, module names inside a plugin.
- Not decided here: nothing about brig, cordis or the warden example (their own names); a docs
  reference page for the sub-agents plugin does not exist (`docs/bh-02/reference/plugins/` has none,
  `mkdocs.yml` lists none) and is not made by the rename.

## Accepted

2026-10-14, by Fable standing in for the owner (he delegated these decisions), after the review
against the cordis design (TASK-0099.01's notes) found nothing blocking. Accepted with five changes,
applied above: `tui:ui` named in the rule as the one kept stutter; the startup-file fallback by name
per configured entry, through `host_paths.walked` for the person's, with the prompt naming only
`startup.py`; `__kernel__` stays; `pypeeker rename`, not `demote`; the counts' exclusions. Flags
ruled: `models:model`, `model` and `models` kept (the key's-name exception; thirty files for no
confusion removed); a session's `stack` kept and out of scope.

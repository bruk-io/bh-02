# The jail

The model's code runs in a jail. Inside it the model can change the project, but it can't reach
the network, read your credentials, or change what would run code outside the jail later. Because
the jail holds, bh-02 runs the model's code without asking you first.

## What the jail allows

In short; the policy itself, path by path and why, is the
[runner plugin's](../reference/plugins/runner.md).

| | Inside the jail |
|---|---|
| **Writes** | the project, a scratch directory of the jail's own, and the project's auto memory directory. Not, even in the project: bh-02's layer files, its own code, the Python it runs on (and the directories of the links that lead to it, uv's Python directory when your project is the home directory) and the paths it imports from, its config directory, `.git/hooks`, `.git/config`, `.claude`, shell rc files, editor settings, and other files that could run code later. `CLAUDE.md` and `AGENTS.md` may be edited. |
| **Reads** | everything but credentials: `~/.ssh`, `~/.aws` and the like, and the sessions' state. On Linux, only the system, the Python interpreter, the project and its auto memory directory are there at all; your home directory is not. |
| **Network** | none |
| **Environment** | scrubbed to a short list of variables: a provider key in your shell is not among them unless you list it |

One thing bh-02 does writes outside the jail: the `memory` tool, which saves the model's auto
memories, runs in bh-02's own process, not in the jail. It writes only in the auto memory
directory, through no link (a link or a second name the model left there is refused, never
followed), and the jailed model can already write that directory, so bh-02 runs the tool without
asking, jailed or under `--no-jail`. Every other tool declared to run in bh-02's own process
(`runs = "host"`) is still asked about. [Why](../how-it-works/jail-and-approval.md#the-memory-tool-runs-outside-the-jail).

Programs the model's code starts run inside the same jail. brig's host process, which starts the
Python process from outside the jail, keeps the environment bh-02 was launched with (brig's
launcher passes it on, so a key or token your shell exports is there, and bh-02 never adds one of its own); a jailed input can't read it.

The jail is brig's. On macOS it is Seatbelt; on Linux it is bubblewrap, which must be installed
(the `bubblewrap` package). Without it, bh-02 tells you to install it or run with `--no-jail`.

## The status bar

The `jail:` field (the `grades` row) says whether the model's code is confined and how well each
part of the jail holds:

```text
jail: jailed fs_write ✓ network ✓ fs_read ~ env ✓
```

Each part is graded as brig can enforce it: `✓` enforced, `~` best effort, `?` cooperative, `✗`
unenforced. On a narrow terminal the field shortens to initials (`w✓ n✓ r~ e✓`), then to the
marks alone. It is never cut. What a start says you should know (on Linux, the paths its jail
holds with a mount the host can undo) is shown once, as a note in the conversation.

The `agents:` field appears while sub-agents run (`agents: 2 running`) and is absent at none.

tmux's `TMUX` and `TMUX_PANE` are not in the environment of any program the runner starts: the
confined runner passes an allowlist that leaves them out, and under `--no-jail` they are taken out
of the rest of bh-02's environment. (Without the jail that is hygiene, not a boundary: an input
can find the tmux socket itself.)

## Without the jail: `--no-jail`

```sh
bh-02 --no-jail
```

Use this where the jail can't run. The model's code then runs with your own permissions, so bh-02
asks you about each input before it runs: the code is shown, `y` runs it, and `n` or `Esc`
doesn't. The question ignores keys for its first 0.4 seconds, its keys dimmed meanwhile, so a
message you were typing can't answer it; those keys are dropped. The model's own extensions are
put to you the same way before each loads. The `memory` tool is not asked about, as above.

!!! warning
    An input you approve can do anything you can. Its environment has no `CLAUDE*` or
    `ANTHROPIC_*` variables, but **every other variable of bh-02's environment reaches the model's
    code, your providers' keys among them**: an `OPENAI_API_KEY` or `OPENROUTER_API_KEY` that a
    model's `key = { env = ... }` reads, exported in the shell that started bh-02, is in the
    environment of the Python process, and the code can read it, print it or send it. Only the
    jail keeps a key out. An input could also rewrite bh-02's config directory or its own code, or
    read the environment of a process you own (the Claude Code process's, which holds the
    subscription token, among them). Read an input before you answer `y`, and don't use
    `--no-jail` with a key you can't afford to expose.

A session keeps the jail it started with: `--resume` refuses `--no-jail`.

## Letting the model write more

The `runner` row's config changes what the jail lets through. Put it in a layer of your own and
start bh-02 with `--patch` ([Layers](layers.md)). This lets inputs write `.git/config` too:

```toml
[[plugin]]
id = "runner"
config = { allow = ["CLAUDE.md", "AGENTS.md", ".git/config"] }
```

| Setting | What it does |
|---|---|
| `allow` | files taken off the list the jail protects. It replaces the default, `["CLAUDE.md", "AGENTS.md"]`, so name every file it should let through. |
| `write` | where inputs may write, `["."]` (the project) by default |
| `deny` | more paths inputs may not write |
| `hide` | files inside the project that inputs may not read, none by default |
| `env` | the environment variables that survive the scrub |

A `config` in a layer replaces the row's whole config, so give every setting you want.

## On Linux

bubblewrap holds a path the model may not create with an empty, read-only directory. So while
the Python process runs, empty directories such as `.envrc/`, `.vscode/`, `.idea/` and `.claude/`
appear in the project (and `.git/` in a project that is not a repository), and go when the jail
ends. Leave them alone: removing one ends the jail.

The jail also ends when something on the host replaces a file it holds, as an editor does when it
saves by renaming, or `git config` does to `.git/config`. The next input starts a new jail that
holds the new file, and says why the model's variables are gone. A program an input left running
can get a write in during the few milliseconds that takes, so stop the reply (or `/release`)
before you edit a layer file while one runs.

### Creating a path the jail holds: `/release`

While the Python process runs, the jail holds the empty directories above where nothing was, so you
can't create a file at one of those names (an `.envrc`, say) from outside. To create one:

1. Type `/release`. Each row stops what it runs in the jail (the Python process, and the
   extensions' process if one runs) until the next input, and the directories go.
2. Create the file.
3. Send your message. The next input starts a new jail, which holds what is still absent again and
   the file you made read-only.

Anything that starts in the jail before you create the file holds the path again (an input, or
an extension you edit): `/release` again. `/restart python` won't do here: it starts the Python
process and its jail again at once. `/release` says so when a program still runs because its row
did not stop it.

[The jail and approval](../how-it-works/jail-and-approval.md) explains how the jail and the
approval rule fit together, and the runner plugin's README has every detail:
[runner-cordis-plugin](../reference/plugins/runner.md).

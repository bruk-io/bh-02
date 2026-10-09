# The jail

The model's code runs in a jail. Inside it the model can change the project, but it can't reach
the network, read your credentials, or change what would run code outside the jail later. Because
the jail holds, bh-02 runs the model's code without asking you first.

## What the jail allows

| | Inside the jail |
|---|---|
| **Writes** | the project, a scratch directory of the jail's own, and the project's auto memory directory. Not, even in the project: bh-02's layer files, `.git/hooks`, `.git/config`, `.claude`, shell rc files, editor settings, and other files that could run code later. `CLAUDE.md` and `AGENTS.md` may be edited. |
| **Reads** | everything but credentials: `~/.ssh`, `~/.aws` and the like, bh-02's `local.env`, and the sessions' state. On Linux, only the system, the Python interpreter, the project and its auto memory directory are there at all; your home directory is not. |
| **Network** | none |
| **Environment** | scrubbed to a short list of variables |

Programs the model's code starts run inside the same jail.

The jail is brig's. On macOS it is Seatbelt; on Linux it is bubblewrap, which must be installed
(the `bubblewrap` package). Without it, bh-02 tells you to install it or run with `--no-jail`.

## The status bar

The `jail:` field says whether the model's code is confined and how well each part of the jail
holds:

```text
jail: jailed fs_write ✓ network ✓ fs_read ~ env ✓
```

Each part is graded as brig can enforce it: `✓` enforced, `~` best effort, `?` cooperative, `✗`
unenforced. On a narrow terminal the field shortens to initials (`w✓ n✓ r~ e✓`), then to the
marks alone. It is never cut.

## Without the jail: `--no-jail`

```sh
bh-02 --no-jail
```

Use this where the jail can't run. The model's code then runs with your own permissions, so bh-02
asks you about each input before it runs: the code is shown, `y` runs it, and `n` or `Esc`
doesn't. The question ignores keys for its first 0.4 seconds, so a message you were typing can't
answer it. The model's own extensions are put to you the same way before each loads.

!!! warning
    An input you approve can do anything you can. Its environment has no `CLAUDE*` or
    `ANTHROPIC_*` variables, but it could still open `local.env` itself, or read the environment
    of a process you own. Read an input before you answer `y`.

A session keeps the jail it started with: `--resume` refuses `--no-jail`.

## Letting the model write more

The `jail` row's config changes what the jail lets through. Put it in a layer of your own and
start bh-02 with `--patch` ([Layers](layers.md)). This lets inputs write `.git/config` too:

```toml
[[plugin]]
id = "jail"
config = { allow = ["CLAUDE.md", "AGENTS.md", ".git/config"] }
```

| Setting | What it does |
|---|---|
| `allow` | files taken off the list the jail protects. It replaces the default, `["CLAUDE.md", "AGENTS.md"]`, so name every file it should let through. |
| `write` | where inputs may write, `["."]` (the project) by default |
| `deny` | more paths inputs may not write |
| `hide` | files inputs may not read, `["local.env"]` by default |
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

### Adding your credential mid-session

Where bh-02 looks for `local.env` and finds none, the jail holds the path, so you can't create the
file while the Python process runs. To add it:

1. Type `/release`. It stops the Python process and its jail until the next input, and says
   which paths that freed.
2. Create `local.env` ([Get started](../get-started.md#the-credential)).
3. Send your message. The model row reads the file at its next step, and the next input starts a
   new jail that hides it again.

`/restart kernel` won't do here: it starts the jail again at once.

[The jail and approval](../how-it-works/jail-and-approval.md) explains how the jail and the
approval rule fit together, and the brig plugin's README has every detail:
[runner-cordis-plugin](../reference/plugins/runner.md).

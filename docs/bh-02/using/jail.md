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

The jail is brig's (bruk-io/brig). On Linux it is bubblewrap, which must be installed (the
`bubblewrap` package); without it, bh-02 tells you to install it or run with `--no-jail`. On macOS
brig has no jail yet, so `runner:confined` refuses and names `--no-jail`.

## The status bar

The `jail:` field (the `grades` row) says whether the model's code is confined and how well each
part of the jail holds:

```text
jail: jailed fs_write ~ network ~ fs_read ~ env ✓
```

Each part is graded as brig can enforce it: `✓` enforced, `~` best effort, `?` cooperative, `✗`
unenforced, `!` violated (brig finds the claim broken). `network` reads `~` on a normal start: the
jail reaches no network (every start enforces an egress proxy that grants nothing), and brig grades
it best effort while the jail sees any host root. It is `!` when a root of the jail (the project,
a write root, the scratch or memory directory) is under a place hosts keep sockets, so a start with
one is refused: keep the project and `XDG_STATE_HOME` out of `/tmp`, `/var/tmp`, `/run`, `/dev/shm`
and `$XDG_RUNTIME_DIR`. On a narrow terminal the field shortens to initials (`w~ n~ r~ e✓`), then to the
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
start bh-02 with `--patch` ([Layers](layers.md)). This lets inputs write `docs/generated` as well
as the project:

```toml
[[plugin]]
id = "runner"
config = { write = [".", "docs/generated"] }
```

| Setting | What it does |
|---|---|
| `write` | where inputs may write, `["."]` (the project) by default |
| `deny` | more paths inputs may not write |
| `hide` | files inside the project that inputs may not read, none by default |
| `env` | the environment variables that survive the scrub; it replaces the list below, baseline included |

There is no `allow`: CLAUDE.md and AGENTS.md are writable by default, and a layer that names `allow`
fails at boot with the loader's error (`invalid config for BrigConfig`). Any other path the jail
protects because it can run code outside the jail later (`.git/hooks`, `.git/config`, shell rc
files, `.envrc`, `.vscode`, `.idea`, `.claude`) is writable only by a write grant on that exact path
(below); a grant on its parent directory does not lift it.

A `config` in a layer replaces the row's whole config, so give every setting you want. The
exception is `env`: a layer that leaves it out takes the list from your `runner.toml` (below).

## Grants

A grant is one thing the jail is given beyond its policy: `read` or `write` an absolute path, let an
`env` variable through, or reach a `net` destination (a hostname, `*.suffix` or an IP address, with a
port). Every start applies the project's always-grants, kept in `grants.toml` in the project's grants
directory (`$XDG_STATE_HOME/bh-02/projects/<project>/grants/`; no jail reads or writes it) and the
session's. For now nothing asks the person: the session's are empty, and the always-grants are the
file as it stands (the request and the prompt are tasks of their own, in decision-0012).

A start applies a grant as follows:

- `read`: the path joins the trees the jail reads. `write`: it joins the roots the jail writes. A
  write grant on exactly a self-modifying path (above) lifts that path's protection and nothing else.
- `env`: the variable joins the allow-list, and reaches the jail if bh-02's own environment has it.
- `net`: the destination joins the start's egress policy; the proxy lets the program reach exactly
  that host and port. Nothing else is reachable. A `net` grant also reaches every program running
  now, at once, with no restart (a connection the program makes after it is let through), and a
  `/grants revoke` in the session is refused from the next connection on; a connection already open
  stays open until the program restarts (`/clear` restarts the Python process), since the proxy
  judges a connection once. `bh-02 grants revoke`, from outside a session, changes what later starts
  apply: a session running now keeps the destination until its next start of a program, and the
  command says so.

When a program's connection is refused, you are asked while the call runs: the destination, which
input asked (`python` or `extensions`), and once, always or no. On a yes the model is told it may
retry. A name that resolves to a private address (loopback, your network) is asked only as that
address, with a warning that it lets the program reach it on your network; a name that does not resolve
is not asked, and the model is told. A refusal never offers a wildcard.

Some grants are refused whoever asks: a path that is or lies under a secret, the grants store, your
credentials, the layer files, bh-02's configuration (a read as well as a write), and for a write bh-02's
own code, the interpreter and the directories of the links on the way to it; a variable a model's key
reads; the proxy variables. Paths are resolved first, so a link to one of those is refused as what it
leads to. A refused grant is left out of the start, and the start's notice (the line the jail reports
about itself) says which and why. A read grant for a path that is not there is left out the same way,
and so is a write grant for one outside the project that is not there (a worktree since removed) or one
under a path the layer hides.

## Which environment variables the model's code sees

The jail starts the model's code with an empty environment and adds back `PATH`, `HOME`, `LANG`,
`LC_ALL` and `TERM`, and nothing else. A provider key you exported for a model's
`key = { env = ... }` is in bh-02's own environment and **not** in the code's. To let more through
(a `GITHUB_TOKEN` for `gh`, an `AWS_PROFILE`), list the names, never values, in
`~/.config/bh-02/runner.toml` (`$XDG_CONFIG_HOME/bh-02/runner.toml`):

```toml
env = ["GITHUB_TOKEN", "AWS_PROFILE"]
```

- The names are added to the five above, for every session and with no `--patch`.
- A layer whose `runner` config sets `env` replaces this list (and the five: a layer's `env` is the
  whole list), and the jail says so when it starts. A layer that leaves `env` out takes the file's.
- The file is read like the models file: one in the project, or reached through a link into it, is
  not read, because the model's code could have written it. The jail then passes the five alone and
  tells you where to put it (outside the project; if you run bh-02 from your home directory, set
  `XDG_CONFIG_HOME` somewhere else). No file leaves the five.
- A file that is not TOML, has a key other than `env`, or lists something that is not a variable
  name is refused with a message saying what to fix, and bh-02 does not start the runner on it.
- `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` and `NO_PROXY`, in either case, are refused too: the jail
  sets them itself to reach its egress proxy.
- A name that a `key = { env = ... }` in your models file reads is refused at startup, naming the
  variable, the endpoint and both files: the jail would hand that key to the model's code. Remove
  it from `runner.toml` (or the layer), or change the key. (The models file checked is the default
  one; a model row `models` setting naming another is not.)
- `--no-jail` ignores the file: the unconfined runner passes bh-02's environment, as above.

The model's code cannot write the file: bh-02's config directory is not writable in the jail.

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

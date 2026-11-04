# The jail and approval

Two rows decide what the model's code may do. The `runner` row decides where it runs. The
`approval` row decides whether it runs without asking you. The rule between them is short: when
the runner confines the code, it runs; when it doesn't, you are asked.

## Approval: one rule, one row

`runner:approval` binds `approval`, the one place that decides whether the model's code runs
unasked. What it doesn't let run is put to you as a **question**. The loop asks the rule about
every input (`unasked(question)`), and the extensions row about every extension it loads. Neither
keeps a copy of the rule, and each puts the question to you itself when the rule says no.

- **Confined** (the runner enforces writes and network): yes, at once.
- **Unconfined** (`--no-jail`): the loop or the extensions row puts the question to you in the
  app's approval modal, with the code shown, and it runs only on a yes. With nobody to ask, the
  answer is no.

The python row tells the model whether it is confined by the same rule, so what the model is
told and what happens agree. `approval` runs in bh-02's own process and depends on the runner
alone, not on the Python process or the app, so `/clear` leaves it up. Only a layer replaces it;
an extension has no way to.

### The memory tool runs outside the jail

One call is never asked, whether the runner confines or not: the `memory` tool of the memory
plugin, which saves, reads and deletes the model's auto memories. It runs in bh-02's own process,
not in the jail, and it writes files there. That is on purpose.

- **It is bh-02's code, not the model's.** The model chooses a name and a text; bh-02 writes the
  file and its line in `MEMORY.md`.
- **It writes only the auto memory directory** (`host.auto_memory`), through no link: a link or a
  second name for another file that the model left there is refused, never followed, so nothing
  outside the directory is read, written or removed.
- **The jailed model can already write that directory** without being asked, so asking about this
  tool would protect nothing.
- **A jail per save would cost a whole process** for a small file write.

Every other tool declared to run in bh-02's own process (`runs = "host"`) is still asked about,
jailed or not; the sub-agent tools (`"harness"`) are asked about only under `--no-jail`. A tool
gets this treatment only from a layer's row (`runs = "memory"`); an extension's tool is always
the jail's. [The memory plugin](../reference/plugins/memory.md#auto-memory) says how the tool works.

## The runner row

The `runner` row starts the programs the model's code runs in: the Python process, and the
extensions' own process. Two components can fill it:

- **`runner:confined`** (the default) confines both, each in a jail of its own built from one
  policy.
- **`runner:unconfined`** (`--no-jail`) starts them as plain processes. Every part is graded
  unenforced, so approval asks.

The runner starts a program, and the row that started it is the one that stops it. On
`/release` (`runner:release`) the runner asks each such row to stop its own (the python row its
Python process, the extensions row its process), then says whether a program of its jails still runs, brig having removed the placeholders its jails held on the
host. It never stops a row's program itself: if one still runs, `/release` says so. The next
start ends the release, whoever starts: the next input, or an extension that changed.

The policy (`spec_for` in the runner plugin) is one pure function: writes only to the project and
a few places bh-02 names, never to what bh-02 itself reads and trusts (its layer files, its config
directory, the paths it imports from) or what could run code later; reads of everything but
credentials; no network; a scrubbed environment; and whatever the person has granted that the
floor allows (read and write paths, environment variables, network destinations). [The jail](../using/jail.md) lists it as you meet
it.

brig's bubblewrap jail enforces it on Linux (by allowlist: the system, the interpreter, the project;
nothing else exists). brig has no jail for macOS yet, so the confined runner refuses there.

brig grades every part of what it enforces (`enforced`, `best_effort`, `cooperative`,
`unenforced`) by what the stack can deliver, and the status bar's `jail` field (the `grades`
row) shows those grades. A jail that enforced less than asked would say so.

## Grants

The policy is not the last word: the person can give the jail more, one grant at a time
([Grants](../using/jail.md#grants) is how you meet it). Two rows do it.

- **`runner:grants`** is the broker: a plain value that holds the project's always-grants (read
  fresh from `grants.toml` at each start, so another process's change counts) and the session's
  answers (`once`, and `no`, which is not asked again). Rows ask it with `need` (held while the row is
  up) and anything else with `ask`. It depends on `host` alone, which never reloads, so a grant changes
  what the broker holds and reloads no row.
- **`runner:grant_prompt`** serves the broker its prompt (once, always, no, through `output.choose`),
  tells the model each answer in an aside, and registers `/grants` and the `grant` tool.

`approval` depends on `runner` alone, so a grant, an always, or a requester coming and going leaves the
rule up. A grant never changes whether the code is confined; it changes what the confined code can reach.

**The floor.** `spec_for` checks every path and variable a grant names against what bh-02 builds from its
own arguments: the secrets and the grants store, your credentials, the layer files, its configuration, its
own code and interpreters, and the variables a model's key reads and the proxy variables. A grant on the
floor, or on a path that leads there through a link, is refused before the person is asked and left out of
a start that holds it. That is why a jailed input can't widen the jail into bh-02's own trust: the person
is never asked for it. The floor is not applied to an extension's `grants.ask` before the question; the
start drops such a grant and says so.

**Generations and the restart.** A `read`, `write` or `env` grant is applied when a program starts. When
what a start would apply has changed (an answer, a revoke, a need held or released), the Python process
starts again before the next input, never during one, and the input's result says why; the extensions
process is replaced at once. A row's `needs` are awaited before its first start (`ready()`), so they cost
no restart, except that with no prompt served `ready()` does not wait.

**Live egress.** A `net` grant needs no restart. Each running jail has an egress watcher that follows the
broker: it allows a destination the jail lacks and revokes one it no longer holds, on the running proxy,
and about every 0.2 s it reads the proxy's refusals and asks about each one as the program that made it
(`python`, `extensions`, or a sub-agent's label). A name that resolved to a private address is asked as
that address alone, and a name that did not resolve is not asked. The proxy judges a connection once, so
a revoke refuses from the next connection and never cuts one already open. A sub-agent's realm reads the
one broker; it has no `grant` tool of its own.

**The honest grade.** A grant opens the proxy's door and nothing else: a program that ignores the proxy
settings and connects directly reaches nothing, because the jail has loopback only. Even so brig cannot
vouch for more than that, so `network` is graded `best_effort`, never `enforced`, and the egress is
`proxied`. `approval` counts a best-effort network as confined, because every start applies the egress
policy, which passes only what is granted. A start under `--no-jail` grades every part unenforced and
there is nothing to grant.

The runner plugin's README has the detail: [runner-cordis-plugin](../reference/plugins/runner.md).

## The credential never gets in

bh-02 reads no credential file: a model's key and the Claude token come from the environment
bh-02 was started with, through the endpoint's `key`, and the token goes only to the Claude Code CLI
it starts. The jail hides the sessions' state, where Claude Code keeps its own config. The Python
process's environment is scrubbed to an allow-list, so a provider key exported in your shell is not
in it. Without the jail, `runner:unconfined` drops only every `CLAUDE*` and `ANTHROPIC_*` variable
and tmux's, and passes the rest: a provider key then reaches the model's code
([the jail](../using/jail.md#without-the-jail-no-jail)). The models plugin's README has the credential's rules in
full: [models-cordis-plugin](../reference/plugins/models.md#the-credential).

## When the jail ends

On Linux every path the jail protects inside the project is a mount the host can undo: an editor
saving by rename, `git config` rewriting `.git/config`. The jail watches them, and when one is
undone it ends itself at once. The next input starts a new jail that holds the path again, and is
told why its variables are gone.

The jail is also tied to bh-02: when bh-02 exits, however it exits, the jail goes too, and with it
the programs an input left running. On Linux that is every one of them. On macOS a program that
left the jail's process group (one started in a session of its own) keeps running, still under
the jail's rules, until it ends or you end it.

The runner plugin's README has the policy, the platforms and their measured gaps in full:
[runner-cordis-plugin](../reference/plugins/runner.md).

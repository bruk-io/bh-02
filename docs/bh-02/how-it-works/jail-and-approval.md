# The jail and approval

Two rows decide what the model's code may do. The `runner` row decides where it runs. The
`approval` row decides whether it runs without asking you. The rule between them is short: when
the runner confines the code, it runs; when it doesn't, you are asked.

## Approval: one rule, one row

`runner:approval` binds `approval`, the one place that decides whether the model's code runs
unasked. The loop asks it about every input, and the extensions row about every extension it
loads. Neither keeps a copy of the rule, and each asks you itself when the rule says no.

- **Confined** (the runner enforces writes and network): yes, at once.
- **Unconfined** (`--no-jail`): the loop or the extensions row asks you through the app's
  approval question, with the code shown, and it runs only on a yes. With nobody to ask, the
  answer is no.

The python row tells the model whether it is confined by the same rule, so what the model is
told and what happens agree. `approval` runs in bh-02's own process and depends on the runner
alone, not on the Python process or the app, so `/clear` leaves it up. Only a layer replaces it;
an extension has no way to.

## The runner row

The `runner` row starts the programs the model's code runs in: the Python process, and the
extensions' own process. Two components can fill it:

- **`runner:confined`** (the default) confines both, each in a jail of its own built from one
  policy.
- **`runner:unconfined`** (`--no-jail`) starts them as plain processes. Every part is graded
  unenforced, so approval asks.

The runner starts a program, and the row that started it is the one that stops it. On
`/release` (`runner:release`) the runner asks each such row to stop its own (the python row its
Python process, the extensions row its process), then lets go of what its jails hold on the
host. It never stops a row's program itself: if one still runs, `/release` says so. The next
start ends the release, whoever starts: the next input, or an extension that changed.

The policy (`spec_for` in the runner plugin) is one pure function: writes only to the project and
a few places bh-02 names, never to what bh-02 itself reads and trusts (its layer files, its config
directory, the paths it imports from) or what could run code later; reads of everything but
credentials; no network; a scrubbed environment. [The jail](../using/jail.md) lists it as you meet
it.

Two stacks enforce it, from [brig](../../brig/index.md):

| Platform | Mechanism | Reads |
|---|---|---|
| macOS | Seatbelt | by denylist: everything but what the policy hides |
| Linux | bubblewrap | by allowlist: the system, the interpreter, the project; nothing else exists |

brig grades every part of what it enforces (`enforced`, `best_effort`, `cooperative`,
`unenforced`) by what the stack can deliver, and the status bar's `jail` field (the `grades`
row) shows those grades. A jail that enforced less than asked would say so.

## The credential never gets in

bh-02's `local.env` holds the Claude token. The jail denies reading it wherever bh-02 looks for
it, and denies creating one there, so an input can't plant a credential for the next launch to
read. It also hides the sessions' state, where Claude Code keeps its own config. The Python
process's environment is scrubbed: without the jail, `runner:unconfined` still drops every
`CLAUDE*` and `ANTHROPIC_*` variable. The models plugin's README has the credential's rules in
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

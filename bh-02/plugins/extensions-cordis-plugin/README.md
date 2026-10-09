# extensions-cordis-plugin

The model's own plugins: cordis components it writes, which bh-02 loads while it runs. The
model extends the harness it works in the way any plugin does, through keys, and without a
restart; what keeps that safe is where the code runs, not who reads it first.

| Row | Binds | Consumes |
|---|---|---|
| `extensions:extensions` | nothing: what extensions add goes into `commands`, `frame` and `system`; its own `system` section tells the model how; registers its worker's stop with the runner (`/release`) | `runner` (`start`, `released`, `on_release`), `commands`, `frame`, `system`, `approval` (`confined`, `unasked`), `output` (`confirm`) |

Config (`ExtensionsConfig`): `root` (the project, `.`), `path` (the extensions directory under
it, `.bh-02/plugins`), `watch` (how often it is looked at, 0.5 s).

## What the model does

It writes `.bh-02/plugins/NAME.py` (NAME: lowercase letters, digits, `_`), a module of cordis
components, from an input like any other file. bh-02 loads it within a `watch`, loads it afresh
when it changes, and unloads it when it is deleted. The directory is the project's, so the
extensions load again in every later session there.

```python
from cordis import Effects, acquire, component


@component
async def todo(*, commands, system) -> Effects:
    items: list[str] = []

    async def run(args: str) -> str:
        if args:
            items.append(args)
        return "\n".join(items) or "nothing to do"

    spec = {"name": "todo", "help": "Keep a to-do list", "usage": "/todo [ITEM]"}
    yield acquire(commands.register, spec, run)
    yield acquire(system.add, "The person keeps a to-do list with /todo.")
```

What an extension reaches of bh-02, each only to add to it, each returning its remover:
- `commands.register(spec, run)`: a slash command for the person (`spec`: `name`, `help`,
  `usage`; `run`: async, argument text in, text out). A name bh-02 already has is refused. Not
  `commands.claim`, a line prefix (`!`): a prefix takes every line the person starts with it
  (`!` runs it in their shell, unjailed), so only a row in a layer may claim one. The worker's
  `commands.claim` raises `PermissionError` saying so, and the host adds nothing an extension
  sends but a command, a status field and a prompt section (anything else is a `problem`).
- `frame.status(field, text, *shorter)`: a status-bar field, pushed as `NAME:field`, so it
  can't cover another row's.
- `system.add(text)`: text in the model's own prompt, told with the next message the model reads
  (the loop keeps the prompt a conversation began with and tells a change as a note).

A component may also `bind` keys of its own, which another extension's components can depend
on. It can't replace a row, rebind one of bh-02's keys or reach the loader: those don't exist
where it runs. Whatever it added leaves with it, through `acquire` or not: the worker takes back
any entry an extension never removed (a field pushed from background work) when it unloads.

What the model is told (`watch.instructions`, the row's `system` section) is enough cordis to
write one and no more, since it goes out with every request: the lifecycle rule (a component
runs while what it needs is bound, starts again when that is replaced, and is undone in reverse
when it leaves), the effects it uses (`acquire`, `bind`, `enter`, `background`), Protocol
contracts, the three keys, and how to try a component in an input before writing its file
(`asyncio.run(cordis.testing.drive(todo(commands=fake, system=fake)))`, cordis being importable
there). The rest it can read: cordis's README, whose path it is given when bh-02 runs from the
workspace (an editable install), and `help(cordis.background)` and the like.

The model's prompt (`watch.instructions`) says how to extend bh-02 and names the extensions
there are, nothing more: how each one is lives in `.bh-02/plugins/status.json`, so a load ending
or failing never changes the prompt (each change is a note the loop sends the model, so only an
extension appearing or going is one). The file is written as each load ends, so an input can read
it at once: per extension, `state` (`active`, `partly up`, `failed`, `loading`), each
component's state (`active`, `waiting on: KEY`, `failed:` and the traceback from the
extension's own frames), the module's `error`, its `commands`, and `problems` (a registration
bh-02 refused). The status bar's `extensions` field shows the same to the person
(`ext: todo ✓ notes ✗`).

## Where it runs, and who is asked

Not in bh-02's process. `host.py` starts `worker.py` through the runner, which jails it as it
does the Python process, where inputs run: with `runner:confined` an extension can write only
inside the project, can't reach the network, and can't read `local.env` or the sessions' state.
Each load is put to the `approval` rule (`runner:approval`), the rule the loop asks about
inputs too, so an extension loads without asking exactly when an input runs without asking; the
model's plugins are as contained as its inputs. With `--no-jail` (`runner:unconfined`) an
extension would run with the person's own permissions, so the rule says no (`unasked`) and the
row puts each load to the person itself (`output.confirm`), the source shown whole (`Load the
model's extension todo into bh-02, unjailed (12 lines)?`), and a no leaves it unloaded until
the file changes. What the model is told about it follows `approval.confined`.

Nothing of an extension crosses into bh-02 but data over the worker's socket: a command's spec
and, when the person runs it, its argument text out and its answer back; a field's text; a
section's text. `host.py` registers each into the real key and keeps the remover. A changed or
deleted extension, a failed one, the worker ending, and the row leaving each take back what was
added.

A project that ships a `.bh-02/plugins/` (a repository cloned from someone else) loads its
extensions when bh-02 starts there, jailed, as the model's would be. Unjailed, each is asked
about first.

## What the host reads, and writes, there

The model writes the extensions directory from the jail, and `host.py` reads it on the host,
with the person's permissions, so it follows no link there (the python row's rule for its startup
files: never read a file the model could write, or reach through a link it could make, and hand
its text to the model). A link to `local.env`, or a hard link to it, would otherwise send the
secret to the worker as an extension's source, where an extension already loaded could keep
it, and a SyntaxError on its first line would put that line in status.json and the prompt.
- The directory is opened from the project's root a name at a time (`.bh-02`, then `plugins`)
  with `O_NOFOLLOW` (`host_paths.directory_beneath`, the opener memory and the prompt's
  `.git/HEAD` use too), and listed and read through that descriptor (`_opened`). The root itself
  is the person's, and may be reached through a link of theirs.
- An extension is opened beneath it with `O_NOFOLLOW` (and `O_NONBLOCK`, so a FIFO swapped in
  never blocks; `host_paths.read_beneath`), and read only when `fstat` on that descriptor says it
  is a regular file with one name (`watch.refusal`), of at most 256 KiB (the source goes to the
  worker as one line). So a file swapped for a link after it was found, or as it is opened, is
  not read either.
- A file refused is not loaded (what an earlier version of it added goes), and status.json says
  why and what to write instead: `.bh-02/plugins/leak.py is a link, which bh-02 does not follow
  there (it could lead to a file the jail hides): write the extension itself at
  .bh-02/plugins/leak.py, not a link to it`; a hard link says how many names it has.
- A link on the way (`.bh-02`, or the directory itself) loads nothing: nothing in it is listed,
  read or written, status.json included, so the row's `system` section says it instead
  (`watch.linked`: make it a directory in the project, not a link).
- status.json is written through the same descriptor, as a new file renamed over the old, so a
  link the model left at `status.json` is replaced, not written through, and an input never
  reads half of one.

## The worker

`worker.py` runs by path (`python -I worker.py SOCKET`) and holds a cordis `Runtime`. An
extension is one fiber that binds its own `commands`, `frame` and `system` (isolated, so each
registration carries the extension's name), with the module's components mounted as its
children (`NAME.component`); a load waits up to 10 s for them to come up and reports each one's
state. Its module is run from the source the host sent (so what the person approved is what
runs), registered in `sys.modules` under a name of its own while it is loaded, since cordis's
scan finds a component by its module.

Wire, newline-delimited JSON. Host to worker: `hello` once, then `load` (`name`, `path`,
`source`), `unload` (`name`), `run` (`call`, `command`, `args`). Worker to host: `loaded`
(`name`, `rows`, `error`), `unloaded` (`name`), `ran` (`call`, `answer`), and, whenever an
extension adds or takes back an entry, `add` (`id`, `extension`, `kind`: `command` with
`spec`, `status` with `field` and `forms`, `context` with `text`) and `remove` (`id`). Texts
are capped at 20,000 characters.

The worker starts with the first extension there is to load. One that ends (an extension can
end it: `os._exit` at import) takes every extension down; nothing loads again, and no worker is
started, until the directory changes, so an extension that ends the worker as it loads isn't
loaded again every `watch`.

`/release` stops the worker too, and the row does it itself: it registers its worker's stop
with the runner (`Extensions.stopped`, `runner.on_release`), which asks each owner to stop its
own program and stops none itself, since the worker's jail holds the same placeholders as the
Python process's (where bh-02 looks for its credential, the person's to fill now). The stop
takes back what the extensions added and answers `The extensions' worker is stopped, and what
the extensions added with it: ...`. That is not an ending: while the runner is `released()` and
nothing in the directory changed, no worker starts (each extension's status says why), and once
the next input has started the Python process, every extension there is loads again in a new
worker, with nothing changed (`test_after_release_stops_the_worker_every_extension_loads_again_once_the_jail_runs`).
A change to one of them while released (the person, or the model, edited it) is asked for, so
its worker starts at once, and that start ends the release, as the next input's would
(`test_a_change_while_released_loads_at_once_and_ends_the_release`).
What a command of theirs kept in memory starts afresh, as after any new worker.

## Tests

- `test_extensions_watch.py` is pure: names, changes, which files may be read, what the model
  and the status bar are told.
- `test_extensions_host.py` runs `Extensions` against a real worker the runner plugin's
  `Runner` starts over `extensions_cordis_plugin.testing.PlainJail` (a mechanism that starts a
  plain subprocess; it confines nothing and says so) and fakes for the keys, `approval` among
  them (confined or not): an extension loaded and its command run, changed and deleted, the ways
  one fails to load, a command name bh-02 has, the unjailed question, a worker an extension
  ends, one `/release` stops (the row's own stop, as the runner asks it; `PlainJail`'s `release`
  holds nothing and stops nothing), one changed while released, and the links it does
  not follow: a link to a file outside, a hard link, `.bh-02` or `.bh-02/plugins` a link, a file
  swapped for a link between being found and read (by an extension loaded just before it), and a
  link at `status.json`.

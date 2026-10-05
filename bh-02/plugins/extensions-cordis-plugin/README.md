# extensions-cordis-plugin

The model's own plugins: cordis components it writes, which bh-02 loads while it runs. The
model extends the harness it works in the way any plugin does, through keys, and without a
restart; what keeps that safe is where the code runs, not who reads it first.

| Row | Binds | Consumes |
|---|---|---|
| `extensions:extensions` | nothing: what extensions add goes into `commands`, `frame` and `system`; its own `system` section tells the model how | `jail`, `commands`, `frame`, `system`, `output` (`confirm`, unjailed) |

Config (`ExtensionsConfig`): `root` (the project, `.`), `path` (the extensions directory under
it, `.bh-02/plugins`), `watch` (how often it is looked at, 0.5 s).

## What the model does

It writes `.bh-02/plugins/NAME.py` (NAME: lowercase letters, digits, `_`), a module of cordis
components, from a cell like any other file. bh-02 loads it within a `watch`, loads it afresh
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
  `usage`; `run`: async, argument text in, text out). A name bh-02 already has is refused.
- `frame.status(field, text, *shorter)`: a status-bar field, pushed as `NAME:field`, so it
  can't cover another row's.
- `system.add(text)`: text in the model's own prompt, from its next request (with Claude, a
  changed prompt takes effect at the next reply).

A component may also `bind` keys of its own, which another extension's components can depend
on. It can't replace a row, rebind one of bh-02's keys or reach the loader: those don't exist
where it runs. Whatever it added leaves with it, through `acquire` or not: the worker takes back
any entry an extension never removed (a field pushed from background work) when it unloads.

What the model is told (`watch.instructions`, the row's `system` section) is enough cordis to
write one and no more, since it goes out with every request: the lifecycle rule (a component
runs while what it needs is bound, starts again when that is replaced, and is undone in reverse
when it leaves), the effects it uses (`acquire`, `bind`, `enter`, `background`), Protocol
contracts, the three keys, and how to try a component in a cell before writing its file
(`asyncio.run(cordis.testing.drive(todo(commands=fake, system=fake)))`, cordis being importable
there). The rest it can read: cordis's README, whose path it is given when bh-02 runs from the
workspace (an editable install), and `help(cordis.background)` and the like.

The model hears how each one went in its prompt (`watch.instructions`: how to extend, then each
extension's state) and in `.bh-02/plugins/status.json`, written as each load ends, so a cell can
read it at once: per extension, `state` (`active`, `partly up`, `failed`, `loading`), each
component's state (`active`, `waiting on: KEY`, `failed:` and the traceback from the
extension's own frames), the module's `error`, its `commands`, and `problems` (a registration
bh-02 refused). The status bar's `extensions` field shows the same to the person
(`ext: todo ✓ notes ✗`).

## Where it runs, and who is asked

Not in bh-02's process. `host.py` starts `worker.py` through the `jail` row, the same jail the
kernel's cells run in: with `brig:jail` an extension can write only inside the project, can't
reach the network, and can't read `local.env` or the sessions' state. So an extension loads
without asking, exactly as a cell runs without asking; the model's plugins are as contained as
its cells. With `--no-jail` (`kernel:unjailed`) an extension would run with the person's own
permissions, so each load is put to the person through `output.confirm`, the source shown
whole (`Load the model's extension todo into bh-02, unjailed (12 lines)?`), and a no leaves it
unloaded until the file changes.

Nothing of an extension crosses into bh-02 but data over the worker's socket: a command's spec
and, when the person runs it, its argument text out and its answer back; a field's text; a
section's text. `host.py` registers each into the real key and keeps the remover. A changed or
deleted extension, a failed one, the worker ending, and the row leaving each take back what was
added.

A project that ships a `.bh-02/plugins/` (a repository cloned from someone else) loads its
extensions when bh-02 starts there, jailed, as the model's would be. Unjailed, each is asked
about first.

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

## Tests

- `test_extensions_watch.py` is pure: names, changes, confinement, what the model and the
  status bar are told.
- `test_extensions_host.py` runs `Extensions` against a real worker under
  `extensions_cordis_plugin.testing.PlainJail` (a plain subprocess reported as confined or not;
  it confines nothing) and fakes for the keys: an extension loaded and its command run, changed
  and deleted, the ways one fails to load, a command name bh-02 has, the unjailed question,
  a worker an extension ends.

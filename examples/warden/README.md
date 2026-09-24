# warden

A process supervisor, composed the same way `bh-02` is: a thin shell (`cli`, `bootstrap`, one
shipped layer file) over `*-cordis-plugin` workspace members that the layer names by string.
No LLM, no chat — cordis's reactivity and lifecycle applied to a domain that has nothing to
do with either. `warden` and its plugins are their own family, separate from `bh-02`'s: they
agree on names and shapes in [`CONTRACTS.md`](CONTRACTS.md), not the root one, and no plugin
here imports another or anything from `bh-02`'s plugins.

```
uv run warden                       # supervise the configured processes until Ctrl-C
uv run warden --patch mine.toml     # a layer of your own over the shipped composition
uv run warden --trace               # any of these, with every row's lifecycle event on stderr
uv run warden --tray                # a macOS menu bar app instead of running until Ctrl-C
```

## The composition (iteration 2, current)

| Row | Base composition | Binds / registers | Depends on |
|---|---|---|---|
| `processes` | `warden:registry` | `Processes`, the broker | nothing |
| `example` | `warden:supervised`, `config = { name = "example", command = [...] }` | registers one process under its `config.name` | `processes` |

`processes` is the paper's service broker (section 6.2), the same pattern `bh-02`'s `commands` row
uses: one row binds it, and every managed process is its own `warden:supervised` contributor
that `acquire`s a registration under `config.name`, undone (unregistered, then the process
terminated) when its row leaves. Nothing depends on a contributor, only on the registry, so
adding, removing or reconfiguring one managed process never reloads another. Add another
process by adding another `[[plugin]]` block to a layer file with a unique row id, `use =
"warden:supervised"` and its own `config.name`/`config.command` — see `supervisor.toml`.

Iteration 1 (a single hardcoded process, no registry) is superseded by this; nothing about
`enter`/undo as start/stop changed, only that it is now a contributor instead of the whole
composition.

## Running the tray (macOS)

`--tray` adds `tray.toml` (`tray` row, `warden-systray:tray`, from
`warden-systray-cordis-plugin`) on top of `supervisor.toml`: a read-only menu-bar listing of
`processes.names`, refreshed on a timer. AppKit needs the *main* thread for its own run loop,
which `warden` would otherwise be using for cordis's asyncio loop, so `--tray` inverts the
usual arrangement:

- The composition (`boot` + wait-until-cancelled + `shutdown`) runs on a **background
  thread**, in its own event loop.
- The main thread constructs the tray app from the factory bound under `tray`
  (`booted.runtime.root.get("tray")`) and blocks on its `.run()` — the AppKit run loop.
- Quitting the tray is what ends everything: the tray's `on_quit` hook (set by
  `warden.bootstrap.run_with_tray` before calling `.run()`) cancels the background thread's
  task and joins it, which unwinds the composition through the same `Runtime.shutdown()`
  every other exit path uses — so every supervised process still gets terminated, not
  orphaned by `rumps`'s own quit tearing the process down first.

`run` (no tray) and `run_with_tray` share `_boot`; only the "who owns the main thread, and
what ends the run" part differs. See `plugins/warden-systray-cordis-plugin/README.md` for the plugin
side, and `CONTRACTS.md` for the `tray` key.

## Where this goes next

- **Health checks** (`cordis-helpers`' `Hooks`): a `health` row runs checks against the
  registry without the registry depending on it.
- **A restart policy**: the interesting reactive case — a fiber that watches its own
  supervised process exit and remounts.
- **Tray actions**: the tray is read-only today; starting/stopping a process from the menu
  needs a small command surface on `processes`, not just `register`/`get`/`names`.

# Contracts

`warden`'s own plugin family, separate from `bh-02`'s (`bh-02/CONTRACTS.md`): no plugin here
imports another, or imports anything from `bh-02`'s. They agree on **names** (the keys a layer
wires) and **shapes** (what a value bound under a name looks like), written down here and
nowhere else. A consumer states the shape it needs as a `runtime_checkable` Protocol of its
own; cordis checks the value against it when the dependency is committed, before the
consumer's first effect. A provider imports nothing to satisfy a contract; it just has the
methods.

## Keys

| Key | Value | Bound by | Read by |
|---|---|---|---|
| `processes` | the registry, below | `warden:registry` | `warden:supervised` (`register`), `warden-systray:tray` (`names`) |
| `tray` | a zero-argument factory for a `_Tray` (`on_quit`, `run()`), unconstructed | `warden-systray:tray` | `warden.bootstrap:run_with_tray` |

Row ids in the shipped layer coincide with these keys where a row binds one (`processes`,
`tray`); a row that contributes to the registry (`example`, and any process added alongside
it) has an id of its own, unrelated to `config.name`.

`tray` is bound as a *factory*, not a constructed value: `warden-systray:tray`'s `TrayApp`
wraps AppKit state that must be built and run on the main thread, but the row that binds it
runs on whichever thread the runtime happens to be on (a background one, under `--tray` -
see `README.md`'s "Running the tray"). This is `bh-02`'s `done`/`harness` pattern
(`bh-02/CONTRACTS.md`) applied the other way: there the shell declares its own dependency on
a binding a mode must produce; here the shell (`run_with_tray`) reads a binding no row
depends on, through a `_Tray` Protocol of its own rather than importing
`warden_systray_cordis_plugin.TrayApp`.

## The registry (`processes`)

```
register(name, process) -> remover    process: warden_cordis_plugin.process.Process
get(name) -> Process | None
names -> list[str]
```

The generic half is `cordis_helpers`' `Registry`; a contributor registers with cordis's
`acquire` effect, so the remover is the undo: `yield acquire(processes.register, config.name,
process)`. Each registration is its own entry (the paper's Definition 44), so any subset can
be withdrawn in any order — retiring one `warden:supervised` row unregisters and terminates
only its own process, never another's.

## Shapes

```
Process    {"pid": int}    (warden_cordis_plugin.process.Process, a frozen dataclass)
```

## Errors

Spawning a process's configured command failing (a bad path, no permission) fails that
`warden:supervised` row at activation with cordis's own diagnosis
(`FileNotFoundError`/`PermissionError` propagating out of `managed_process`'s `__aenter__`);
it does not affect sibling rows. There is no recoverable-error contract yet (nothing in this
app shows a person a message the way `bh-02`'s `llm`/`completion` do).

## Where this grows

- `health`: hooked checks against the registry (`cordis-helpers`' `Hooks`), consuming
  `processes` without `processes` depending on it.
- A restart policy: a fiber that watches its own supervised process exit and remounts.
- Tray actions: today `tray` is read-only (`warden-systray-cordis-plugin`'s `TrayApp` lists
  `processes.names`); starting/stopping a process from the menu needs a small command
  surface on `processes` beyond `register`/`get`/`names`, not just read access.

This section is a plan, not yet true; move an entry above into a real one the same commit
that implements it, the way any change to a shape here should land with the code that makes
it so.

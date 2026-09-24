# warden-cordis-plugin

Two rows. `warden:registry` binds `Processes`, a broker (the paper's service broker, section
6.2, the same pattern bh-02's `commands` row, `commands_cordis_plugin`'s `Commands`, uses) under the `processes` key, depending
on nothing. `warden:supervised` spawns `config.command` as a subprocess when it activates,
registers the resulting `Process` (its `pid`) into `processes` under `config.name`, and — on
the way out — unregisters it and terminates it, in that order (an `acquire` effect over
`enter`, undone last-acquired-first). `config` is a `ProcessConfig` (`name: str`, `command:
tuple[str, ...]`, default `("sleep", "100")`).

One `warden:supervised` row per managed process; each depends only on `processes`, never on
another contributor, so adding, removing or reconfiguring one process never reloads another.
Imports nothing from any other plugin; the shapes are written down in
[`CONTRACTS.md`](../../CONTRACTS.md), `warden`'s own contracts doc.

No health checks and no restart policy yet — a registry of processes, proving the broker
pattern outside `bh-02`'s `tools`, before either is added.

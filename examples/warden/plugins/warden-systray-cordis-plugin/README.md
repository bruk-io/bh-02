# warden-systray-cordis-plugin

macOS only. One row, `warden-systray:tray`, that binds a **factory** for a menu-bar app under
the `tray` key — not a constructed app. `TrayApp` wraps AppKit state (`rumps.App`, an
`NSStatusItem`), which belongs to the main thread; the cordis row that binds it may be
running on any thread the runtime happens to be on, so it hands back `lambda: TrayApp(...)`
and lets whoever owns the main thread call it (`warden.bootstrap.run_with_tray`, which `warden.cli` calls under `--tray`).

`TrayApp` lists the names in `processes` (depends on `processes`, declared as its own
`Snapshot` Protocol — `names: list[str]` — not by importing `warden_cordis_plugin.Processes`),
refreshed on a `config.refresh_seconds` timer (`TrayConfig`, default 2s). Read-only: no
start/stop from the tray yet. `menu_labels` (names -> sorted labels, `"(no processes)"` when
empty) is the one pure, unit-tested piece; `TrayApp` itself is AppKit-backed and only
verifiable by running it.

`on_quit`, settable on the `TrayApp` after the shell constructs it and before `.run()`, is
the hook back into warden's own shutdown: `rumps`'s default quit tears the process down
(`NSApp terminate:`) without unwinding anything, which would orphan every process this
composition is supervising. The shell wires `on_quit` to cancel its own run and wait for
`Runtime.shutdown()` before letting `rumps.quit_application()` proceed — see
`../../README.md`'s "Running the tray" section for the actual bridge.

Imports nothing from any other plugin, including `warden-cordis-plugin`; the shape it needs
of `processes` is written down in [`CONTRACTS.md`](../../CONTRACTS.md).

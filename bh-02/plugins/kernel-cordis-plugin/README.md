# kernel-cordis-plugin

A persistent Python namespace in a process of its own, started by whatever jail the
composition names, and the model's one tool, `python(code)`, which runs a cell in it.

| Row | Binds | Consumes |
|---|---|---|
| `kernel:kernel` | `kernel`: `spec` (`python(code)`), `instructions()`, `run(code) -> str`, `confined`, `report()`, `notice()` and `reads()` (its jail's); config: `root` (default `.`), `grace` (seconds an interrupted cell gets) | `jail` |
| `kernel:release` | (nothing: registers `/release`) | `kernel`, `commands` |
| `kernel:unjailed` | `jail`: the worker as a plain subprocess, every axis reported `unenforced` | |

`python.py` is the tool, pure: its spec and `instructions_for(confined)` (what the model is
told: one tool, plain Python, and where it runs). `confined` is what the loop reads to decide
whether a cell is put to the person first (`agent:loop`): the kernel itself never asks, so it
depends on its jail alone and a new ui or model keeps the namespace.

`worker.py` is the process: standard library only (the gate's `worker-stdlib-only`), run by
path as `python -I worker.py SOCKET`, so nothing of the host crosses into a jail with it. Its
one channel is the Unix socket: newline-delimited JSON (`hello`, then `exec` in and `done` out
per cell; a `done`'s output and error are capped at 20,000 characters each, so a line stays
under the host's 1 MiB read limit). The namespace holds only what cells put there: a cell reads and writes files and
runs programs itself, with plain Python, and the jail decides what it may touch. Cells run on
the worker's main thread, so SIGINT lands as `KeyboardInterrupt` in the running cell and the
namespace survives; with no cell running, SIGINT is ignored. A cell's last expression is
shown, and `print` is the observation channel.

`client.py`'s `Kernel` is the host end: entering starts the worker through the jail (its
socket in a short `/tmp` directory, since a socket path must fit in ~100 bytes), leaving stops
it. Cancelling `run` interrupts the cell and waits `grace` seconds for it to end; a worker that
won't, or that died, is started again on the next cell, which is told its variables are gone.
Every failure it knows of comes back as the cell's text, never as an exception out of `run`: a
worker that died, an answer it can't read (the worker is replaced), a worker the jail won't
start again (the next cell tries again).

`release()` (`/release`, the `kernel:release` row) ends the worker now, and the jail it ran
in, then asks the jail what that freed on the host: on Linux, `brig:jail` holds where bh-02
looks for its credential with an empty directory while it runs, and this is how the person
adds one mid-session (the brig plugin's README). The next cell starts a new worker, told its
variables are gone. A cell that is running is left alone, and the answer says to stop the
reply first. `kernel:unjailed` holds nothing, so there it only stops the worker.

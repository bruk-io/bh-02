# kernel-cordis-plugin

A persistent Python namespace in a process of its own, started by whatever jail the
composition names, and the model's one tool, `python(code)`, which runs an input in it.

| Row | Binds | Consumes |
|---|---|---|
| `kernel:kernel` | `kernel`: `spec` (`python(code)`), `instructions()`, `run(code) -> str`, `confined`, `report()`; config: `root` (default `.`), `grace` (seconds an interrupted input gets), `startup` (the project's file a new kernel runs first, default `.bh-02/kernel.py`) | `jail` |
| `kernel:unjailed` | `jail`: the worker as a plain subprocess, every axis reported `unenforced` | |

`python.py` is the tool, pure: its spec and `instructions_for(confined, startup)`, what the
model is told: that `python` is the CodeAct tool bh-02 ships, a Python REPL of its own that lasts as
long as this run of bh-02 (a /model switch keeps it; a start, a resume, /clear or a dead worker
empties it), and that helpers worth keeping go in the startup file; how to use it (build up
state and re-read what changed, print what matters, capture a program's output with
`subprocess.run(..., capture_output=True, text=True, timeout=...)`, since one not captured never
reaches the input, no stdin, the person sees every input); and where its code runs. `confined` is what the loop reads to decide
whether an input is put to the person first (`agent:loop`): the kernel itself never asks, so it
depends on its jail alone and a new ui or model keeps the namespace.

`worker.py` is the process: standard library only (the gate's `worker-stdlib-only`), run by
path as `python -I worker.py SOCKET`, so nothing of the host crosses into a jail with it. Its
one channel is the Unix socket: newline-delimited JSON (`hello`, then `exec` in and `done` out
per input; a `done`'s output and error are capped at 20,000 characters each, so a line stays
under the host's 1 MiB read limit: a longer one keeps its first 6,000 and last 14,000, since a
test run's summary and an error's message come last, and is saved whole to a file in the
worker's temporary directory, which the cut names). Each input is compiled as `<input N>`, its
source registered with `linecache`, so a traceback shows each frame's line and the input it is
in, a function defined three inputs back included. A `NameError` for a name the namespace has
never held says the kernel is new and what empties one, since that is the usual cause after a
resume. The namespace holds only what inputs put there: an input reads and writes files and
runs programs itself, with plain Python, and the jail decides what it may touch. Inputs run on
the worker's main thread, so SIGINT lands as `KeyboardInterrupt` in the running input and the
namespace survives; with no input running, SIGINT is ignored. An input's last expression is
shown, and `print` is the observation channel.

`client.py`'s `Kernel` is the host end: entering starts the worker through the jail (its
socket in a short `/tmp` directory, since a socket path must fit in ~100 bytes), leaving stops
it. Cancelling `run` interrupts the input and waits `grace` seconds for it to end; a worker that
won't, or that died, is started again on the next input, which is told its variables are gone.
A new kernel's first input is also told what the startup file (`startup`, the model's own
helpers, kept with the project) did: confined, the kernel runs it first and says which names it
defined, or its traceback; unconfined, it would run unasked with the person's permissions, so
the model is told to run it as an input of its own, which the loop then puts to the person.
Every failure it knows of comes back as the input's text, never as an exception out of `run`: a
worker that died, an answer it can't read (the worker is replaced), a worker the jail won't
start again (the next input tries again).

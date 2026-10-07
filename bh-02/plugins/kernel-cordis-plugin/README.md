# kernel-cordis-plugin

A persistent Python namespace in a process of its own, started by whatever jail the
composition names, and the model's one tool, `python(code)`, which runs an input in it. Also
`approval`: the one place that decides whether the model's code runs unasked.

| Row | Binds | Consumes |
|---|---|---|
| `kernel:kernel` | `kernel`: `spec` (`python(code)`), `instructions()`, `run(code) -> str`, `confined`, `report()`, `notice()` and `reads()` (its jail's), `release()`, `touched()`; config: `root` (default `.`), `grace` (seconds an interrupted input gets), `startup` (the project's file a new kernel runs first, default `.bh-02/kernel.py`) | `jail` |
| `kernel:approval` | `approval`: `confined` (whether the jail confines what runs in it), `approve(request) -> bool` (async: yes at once when confined, else the person's answer through `output.confirm`, no with nobody to ask) | `jail` (`report`), `output` (`confirm`) |
| `kernel:release` | (nothing: registers `/release`) | `kernel` (`release`), `commands` (`register`) |
| `kernel:unjailed` | `jail`: the worker as a plain subprocess, every axis reported `unenforced` | |
| `kernel:shell_hints` | adds `ShellHints` to `memory` | `memory` (`add`), `transcript` (its lifetime only) |

`python.py` is the tool, pure: its spec and `instructions_for(confined, startup, reads)`, what the
model is told: that `python` is the CodeAct tool bh-02 ships, a Python REPL of its own that lasts as
long as this run of bh-02 (a /model switch keeps it; a start, a resume, /clear or a dead worker
empties it), and that helpers worth keeping go in the startup file; how to use it (work in
Python, not through a shell, shown by an input that searches and keeps what it found and a later
one that edits with it; build up state and re-read what changed, print what matters, run
programs with `subprocess.run(..., capture_output=True, text=True, timeout=...)` and treat what
they print as data, since one not captured never reaches the input, no stdin, the person sees
every input); and where its code runs, and under a jail that reads by allowlist (Linux) the
trees it reads (`reads`, the kernel's `reads()`) and that nothing else, the home directory
included, is there. A model trained on shell tools tends to use the REPL as
one, an input a single `cat`, `sed` or `ls`: `programs(code)` is what an input runs (read with
`ast`, each command of a shell line), `shelled(code)` the part of it Python does itself (reading,
editing, writing, listing and moving files; searching with `grep` or `rg` is not one, nor are
tests, git and builds), and `shell_note` what such an input is told after its output, by
`ShellHints`, the `memory` function the `kernel:shell_hints` row adds: once for each kind of work
a conversation (the row depends on `transcript`, so `/clear` starts it afresh), so it corrects a
habit without nagging.
`scripts/model-friction` reads transcripts with the same two. `confined` is what the model is
told (`instructions_for`) and whether the startup file runs unasked: the kernel itself never
asks, so it depends on its jail alone and a new ui or model keeps the namespace.

`approval.py` is the rule, written once: `is_confined(report)` (the jail enforces `fs_write` and
`network`), and `Approval`, the `approval` value over a jail and an `output`. The loop asks it
about every input (`{"name": "python", "input": {"code"}}`) and the extensions row about every
extension it loads; the kernel's own `confined` is `is_confined` over the same jail. Its row,
`kernel:approval`, depends on `jail` and `output`, not `kernel`, so `/clear` (a new kernel)
leaves it up, and the extensions row that depends on it. It is a capability, bound by one row:
two rows' answers could not be combined, so it is not a broker. It runs in bh-02's own process,
so only a layer replaces it; an extension has no way to bind or reach it. It answers about code
bh-02 is about to hand to the jail, not about each effect a component yields (that is cordis's
planned policy seam, not this).

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
shown, and `print` is the observation channel. An audit hook (`sys.addaudithook`) hears each
file the input's own code opens with `open` or `pathlib` (an `open` event whose mode is a
string), read or written, under the directory the worker started in (the project root, where
the jail starts it), and the `done` names them (`touched`, absolute, each once, at most 1,000,
and only the project's count towards those). Not heard: an `os.open` (its event has no
`dir_fd`, so the names `shutil.rmtree`, `os.fwalk` and a `TemporaryDirectory`'s cleanup open
relative to a directory would read as the project's; `Path.touch` is one too), a directory
listed, a file the import system opens (one of its frames is on the stack), a file opened while
the input's own code is not running (its traceback's formatting reads each frame's source), and
what a program the input runs opens, which happens in another process. It is Claude Code's
Read, Write and Edit for one tool that carries code, and has the same blind spot: a shell
command's own reads. Every audited operation calls the hook (`id()` is one, so `copy.deepcopy`
calls it once per object), so it compares the event with `open` before anything else, and is a
plain function: a bound method cost three times as much per call (CPython looks up a hook's
`__cantrace__` each time, which on a bound method raises and clears an AttributeError). An open
calls it at most twice, at any depth: the import system's frames are told by their globals
(`f_globals`, `f_back`), which raise no audit event, where a frame's `f_code` raises one.

`client.py`'s `Kernel` is the host end: entering starts the worker through the jail (its
socket in a short `/tmp` directory, since a socket path must fit in ~100 bytes), leaving stops
it. Cancelling `run` interrupts the input and waits `grace` seconds for it to end; a worker that
won't, or that died, is started again on the next input, which is told its variables are gone,
and why when its jail ended it (`started.ended()`: a Linux `brig:jail` ends itself when the host
undoes one of its mounts). A worker that died between inputs is noticed before the next input
is sent, so that input runs in the new one. After each input, `touched()` is the files under `root` it opened (what the loop gives
`memory`'s functions). A new kernel's first input is also told what the startup file (`startup`, the model's own
helpers, kept with the project) did: confined, the kernel runs it first and says which names it
defined, or its traceback; unconfined, it would run unasked with the person's permissions, so
the model is told to run it as an input of its own, which the loop then puts to the person.
Every failure it knows of comes back as the input's text, never as an exception out of `run`: a
worker that died, an answer it can't read (the worker is replaced), a worker the jail won't
start again (the next input tries again).

`release()` (`/release`, the `kernel:release` row) ends the worker now, and the jail it ran
in, then asks the jail what that freed on the host: on Linux, `brig:jail` holds where bh-02
looks for its credential with an empty directory while it runs, and this is how the person
adds one mid-session (the brig plugin's README). The next input starts a new worker, told its
variables are gone. An input that is running is left alone, and the answer says to stop the
reply first. `kernel:unjailed` holds nothing, so there it only stops the worker.

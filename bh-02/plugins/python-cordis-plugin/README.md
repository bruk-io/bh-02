# python-cordis-plugin

The python tool: a persistent Python namespace in a process of its own (the Python process),
started by whatever runner the composition names, and the `python(code)` tool, which runs an
input in it: the python row registers it with `tools` (`agent:tools`, a broker), tells the model
about it in the system prompt's `python` section, and registers the process's stop with the
runner for `/release`. It binds no key. Whether an input runs unasked is the `approval` rule's
(`runner:approval`, the runner plugin's), and asking the person is the loop's.

| Row | Binds | Consumes |
|---|---|---|
| `python:tool` | nothing: registers `python` with `tools` (`PYTHON`, its call the `Kernel`'s `call(input) -> {"content", "touched"}`, shown as its code, `shown_call`), adds the `system` section `python` (`instructions()`), and registers `stopped()` with the runner (`/release`); config: `root` (default `.`), `grace` (seconds an interrupted input gets), `startup` (the files a new Python process runs first, in order: default the person's `$XDG_CONFIG_HOME/bh-02/kernel.py`, then the project's `.bh-02/kernel.py`) | `runner` (`start`, and of the process it starts `report()`, `notice()`, `reads()` and `writes()`, the last where the person's startup file is not read on the host; `report()` before any; `on_release`: its stop), `approval` (`confined`), `tools` (`register`: `python`), `system` (`add`: `python`), `access` (`asking`, `refusal`: before an input opens a project file) |

`Kernel` (`client.py`) is the value the row enters (given `tools` too, the `Calls` it offers
an input: `specs()`, `call(name, input)`): `call(input)`, `instructions()`, `run(code) -> str`, `confined` (the `approval` rule's), `report()`, `notice()` and `reads()` (its own start's:
the process it last started, never another program the runner started), `stopped()`,
`touched()`.

`python.py` is the tool, pure: its spec (`PYTHON`), how a call is put to the person
(`shown_call`: its code, whole) and `instructions_for(confined, startup, reads, theirs=,
elsewhere=)`, what the model is told: that `python` is the CodeAct tool bh-02 ships, a Python REPL of its own that lasts as
long as this run of bh-02 (a /model switch keeps it; a start, a resume, /clear or a Python process
that died empties it), and that helpers worth keeping go in the project's startup file (`startup`), the
only one that is its to edit, the person's own (`theirs`), which comes first, being theirs; how to use it (work in
Python, not through a shell, shown by an input that searches and keeps what it found and a later
one that edits with it; build up state and re-read what changed, print what matters, run
programs with `subprocess.run(..., capture_output=True, text=True, timeout=...)` and treat what
they print as data, since one not captured never reaches the input, no stdin, the person sees
every input); and where its code runs, and under a jail that reads by allowlist (Linux) the
trees it reads (`reads`, its start's `reads()`) and that nothing else, the home directory
included, is there. `confined` is what the model is
told (`instructions_for`) and whether the startup files run unasked, and it is the `approval`
rule's (`approval.confined`, read each time), so what the model is told and what the loop does
agree. The python row itself never asks, so it depends on nothing a new ui or model replaces
(the runner, the rule and three brokers), and they keep the namespace. The rule, and why it is
one row's, is in the runner plugin's README.

`worker.py` is the process: standard library only (the gate's `worker-stdlib-only`), run by
path as `python -I worker.py SOCKET`, so nothing of the host crosses into a jail with it. Its
one channel is the Unix socket: newline-delimited JSON (`hello`, then `exec` in and `done` out
per input; a `done`'s output and error are capped at 20,000 characters each, so a line stays
under the host's 1 MiB read limit: a longer one keeps its first 6,000 and last 14,000, since a
test run's summary and an error's message come last, and is saved whole to a file in the
Python process's temporary directory, which the cut names). Each input is compiled as `<input N>`, its
source registered with `linecache`, so a traceback shows each frame's line and the input it is
in, a function defined three inputs back included. A `NameError` for a name the namespace has
never held says the REPL is new and what empties one, since that is the usual cause after a
resume. The namespace holds only what inputs put there: an input reads and writes files and
runs programs itself, with plain Python, and the jail decides what it may touch. Inputs run on
the Python process's main thread, so SIGINT lands as `KeyboardInterrupt` in the running input and the
namespace survives; with no input running, SIGINT is ignored. An input's last expression is
shown, and `print` is the observation channel. An audit hook (`sys.addaudithook`) hears each
file the input's own code opens with `open` or `pathlib` (an `open` event whose mode is a
string), read or written, under the directory the Python process started in (the project root, where
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

`client.py`'s `Kernel` is the host end: entering starts the Python process through the runner
(its socket in a short `/tmp` directory, since a socket path must fit in ~100 bytes), leaving
stops it. Cancelling `run` interrupts the input and waits `grace` seconds for it to end; a
process that won't, or that died, is started again on the next input, which is told its variables are gone,
and why when its jail ended it (`started.ended()`: a Linux `runner:confined` jail ends itself
when the host undoes one of its mounts). A process that died between inputs is noticed before the next input
is sent, so that input runs in the new one. After each input, `touched()` is the files under
`root` it opened, which `call` answers with (what the loop gives `notes`' functions).

Before the input's own Python opens one of those files, the same audit hook can ask bh-02 about
it (`access`, `agent:access`): each input's `exec` names the kinds some row asks about
(`"ask": ["write"]`, say), and for an open of that kind the Python process sends `{"op": "ask", "id",
"kind", "path"}` and waits for `{"op": "answer", "id", "refuse"}`, once per file and kind an
input (any thread may ask; the answer goes to the one waiting). A `refuse` that is text raises a
PermissionError at the open, so the file is never opened, and the traceback ends at the input's
own line (`worker.py`'s frames are left out); the `done` carries every refusal (`refused`), which
ends the input's text in brackets, so the model hears of it even when the code caught the error.
What it does not see: a program an input runs (`subprocess`), an `os.open`, a rename, a replace
or a delete, a file outside the project. It tells the model something before a file changes; the
jail is what stops what must never happen.

A new Python process's first input is also told what the startup files did (`startup`, helpers kept
across sessions, in order): the person's own, `$XDG_CONFIG_HOME/bh-02/kernel.py` (else
`~/.config/bh-02/kernel.py`), for the helpers they want in every project, then the project's,
`.bh-02/kernel.py`, the model's own. A name starting `$XDG_CONFIG_HOME/` is in the person's
config directory (that variable's value, else `~/.config`, as for the models file), one
starting `~/` in their home, any other from `root`; a single string is one file, and anything
but a name or a list of names is the row's config error. Confined, the process runs each that is
there as an input of its own and says which names it defined (each its code binds at the top,
as the compiler reads it, so one bound again to the object it held counts, and any new or
changed after it; on a line of their own, after whatever the file printed), or its traceback;
one failing doesn't stop the next, and one that isn't there is passed over. A UTF-8 byte order
mark is no part of either file, as `python file.py` has it. One that ends the Python
process (`os._exit`, a crash) would end every new one: the input it cut short says which file it was,
after what the opening had to tell by then (that the REPL was started again, and why, which is
told nowhere else, and the files before it), and the Python processes after it pass that file
over, saying so, until `/restart python`. Ctrl-C while one runs stops it, and that process never
runs the files again (a hanging file would hang every input); the next input says what was cut
short, after what the opening had to tell by then, and one that would not stop at all (its
process is replaced) is passed over too. Unconfined, they would run unasked with the person's
permissions, so the model is told to run them as an input of its own, which the loop then puts
to the person: there every input is (the code shown), so nothing is read on the host for the
model, and nothing needs keeping from it. Where each is read is the point:
- The project's is read by the Python process, in the jail, which decides what it may open: the model
  can write it, and a link there to a file the jail hides would otherwise hand that file over.
- The person's is outside the project, and a Linux jail reads by allowlist, with no home
  directory in it, so the Python process can't see it: the host expands its name, reads it and sends
  its source in the input (registered with `linecache`, so a traceback shows its lines). It
  runs in the model's REPL, so whatever it holds the model can read. In a Linux jail the file
  itself is not there: its helpers run and `inspect.getsource` shows them (through
  `linecache`), but `open` on its path finds nothing, a helper that reads a file beside it
  finds nothing either, and `__file__` is not set (nor for the project's: each runs as an
  input). The model is told how to see one (`inspect.getsource(helper)`).
- But only when reading it goes nowhere an input may write (`host_paths.walked`, the walk the
  models file and memory files outside the project are held to: each directory and link on the
  way, as named and as resolved): the
  project, or another root the Python process's jail lets an input write (its `writes()`: a `write`
  the person added to `runner:confined`). A person's file there (bh-02 run from the home directory) or whose way
  passes through one (a config directory linked into a dotfiles repository being worked on) is
  read as the project's is: the model could have written it, or chosen where it leads, so the
  Python process reads it, at its resolved place when that is in such a root. If that fails (the jail
  can't see where it leads), the note says why bh-02 did not read it.
- Across sessions, the walk can't know what an earlier session's jail let its inputs write, so
  the jail itself keeps them out: `runner:confined` denies writing bh-02's config directory wherever
  it is under a writable root (`host.trusted`, the runner plugin's README). A session run from
  the home directory can't make the person's file a link to a key for the next session to read.

Each file runs once, at its first place in the list. Whose a file is goes by how it is named, not
by where it is read: one named from the root is the project's, one named from the person's config
directory, their home or `/` is theirs. `instructions_for` tells the model that only the
project's startup file is its to edit, and names the person's, which comes before it, as theirs.

Every failure it knows of comes back as the input's text, never as an exception out of `run`: a
Python process that died, an answer it can't read (the process is replaced), one the runner won't
start again (the next input tries again).

`stopped()` is the row's part of `/release` (`runner:release`): the row registers it with the
runner (`runner.on_release`), which asks each owner to stop its own program and never stops one
itself. It ends the Python process now, and the jail it ran in, and says so: `The Python process is
stopped; the next input starts it again, without the earlier variables.` ("" when none ran).
The runner then lets go of what its jails held on the host: on Linux, `runner:confined` holds
where bh-02 looks for its credential with an empty directory while a jail runs, and this is how
the person adds one mid-session (the runner plugin's README). The next input starts a new
Python process, told its variables are gone, and that start ends the release, so the extensions load
again too. What the model is told of the Python process's jail (`reads()`) stays the stopped one's
until then. An input that is running is left alone, nothing ends, and the answer says `An input
is running: stop the reply (Ctrl-C), then /release again.` Under `runner:unconfined` nothing is
held, so `/release` only stops the Python process.

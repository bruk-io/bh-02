# python-cordis-plugin

The python tool: a persistent Python namespace in a process of its own (the Python process),
started by whatever runner the composition names, and the `python(code)` tool, which runs an
input in it: the python row registers it with `tools` (`agent:tools`, a broker), tells the model
about it in the system prompt's `python` section, and registers the process's stop with the
runner for `/release`. It binds no key. Whether an input runs unasked is the `approval` rule's
(`runner:approval`, the runner plugin's), and asking the person is the loop's.

| Row | Binds | Consumes |
|---|---|---|
| `python:tool` | nothing: registers `python` with `tools` (`PYTHON`, its call the `PythonProcess`'s `call(input) -> {"content", "touched"}`, shown as its code, `shown_call`), adds the `system` section `python` (`instructions()`), and registers `stopped()` with the runner (`/release`); config: `root` (default `.`), `grace` (seconds an interrupted input gets), `startup` (the files a new Python process runs first, in order: default the person's `$XDG_CONFIG_HOME/bh-02/startup.py`, then the project's `.bh-02/startup.py`), `mypy_cache` (where mypy keeps its cache for the type check of those files: default `.bh-02/mypy_cache`, from `root`) | `runner` (`start`, and of the process it starts `report()`, `notice()`, `reads()` and `writes()`, the last where the person's startup file is not read on the host; `report()` before any; `on_release`: its stop), `approval` (`confined`), `tools` (`register`: `python`), `system` (`add`: `python`), `access` (`asking`, `refusal`: before an input opens a project file), `carried` (`add`: `carried()`, what `/compact` says of the namespace) |

`PythonProcess` (`client.py`) is the value the row enters (given `tools` too, the `Calls` it offers
an input: `specs()`, `call(name, input)`): `call(input)`, `instructions()`, `run(code) -> str`, `confined` (the `approval` rule's), `report()`, `notice()` and `reads()` (its own start's:
the process it last started, never another program the runner started), `stopped()`,
`touched()`, `carried()`.

`python.py` is the tool, pure: its spec (`PYTHON`), how a call is put to the person
(`shown_call`: its code, whole) and `instructions_for(confined, startup, reads, theirs=,
elsewhere=)`, what the model is told: that `python` is the CodeAct tool bh-02 ships, a Python REPL of its own that lasts as
long as this run of bh-02 (a /model switch keeps it; a start, a resume, /clear or a Python process
that died empties it), and that functions worth keeping go in the project's startup file (`startup`), the
only one that is its to edit, the person's own (`theirs`), which comes first, being theirs, which of a startup
file's functions are told to it and what each costs in context (confined only: unconfined nothing is
listed) and the docstring convention for the file it writes; how to use it (work in
Python, not through a shell, shown by an input that searches and keeps what it found and a later
one that edits with it; build up state and re-read what changed, print what matters, run
programs with `subprocess.run(..., capture_output=True, text=True, timeout=...)` and treat what
they print as data, since one not captured never reaches the input, no stdin, the person sees
every input); and where its code runs, and under a jail that reads by allowlist (Linux) the
trees it reads (`reads`, its start's `reads()`) and that nothing else, the home directory
included, is there, and, confined, where it may write (`elsewhere`: the project, and what its
start's `writes()` names outside it, the auto memory directory among them). `confined` is what
the model is
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

`client.py`'s `PythonProcess` is the host end: entering starts the Python process through the runner
(its socket in a short `/tmp` directory, since a socket path must fit in ~100 bytes), leaving
stops it. Cancelling `run` interrupts the input and waits `grace` seconds for it to end; a
process that won't, or that died, is started again on the next input, which is told its variables are gone,
and why when its jail ended it (`started.ended()`: a Linux `runner:confined` jail ends itself
when the host undoes one of its mounts). A process that died between inputs is noticed before the next input
is sent, so that input runs in the new one. After each input, `touched()` is the files under
`root` it opened, which `call` answers with (what the loop gives `asides`' functions).

**The namespace, told after `/compact`.** Every `done` carries the namespace as it stands: `names`,
`[[name, description], ...]` in namespace order, and `unlisted`, how many names it left out. A
description is the type's name; for a `list`, `tuple`, `dict`, `set`, `frozenset`, `str` or `bytes`
(an exact type check, so no `__len__` of the model's runs) its length (`list, 42 items`, `str,
1,204 chars`); for a function or class its type's name and `str(inspect.signature(...))` (`function
(path, old, new)`), cut at 160 characters; `module` for a module. Never a `repr`, and nothing
that runs the model's code on a user object (no `__len__`, `__repr__`, property or
`__class__`; a signature's formatting is the one place Python formats a default). Names with a
leading underscore (`__builtins__` and the dunders among them) and `tools` (bh-02's view) are
left out, as is a name that is no identifier or is longer than 100 characters; at most 200 are
listed, the rest counted in `unlisted`, so a `done` stays far inside the 1 MiB line. The host keeps
the latest listing as data (name to description, cleaned and cut as it reads it) and never adds
it to an input's output. `carried()` words it for `/compact` on demand, reading what it holds and
asking the worker nothing: `the python REPL holds: hits (list, 42 items), edit(path, old, new)
(function), ...`, in order up to 3,000 characters and then `, and N more not listed`, leaving out
the functions the startup files told (the host knows which). It is "" with no Python process
running, and when the namespace holds no names. The row adds it to `carried`
(`agent:carried`), a broker that depends on nothing, so the conversation row reads it without
either reloading the other; `/clear` restarts the row (the listing starts empty), `/compact`
keeps it.

**What an input changed, told with its output.** The host compares the listing before an input
with the one after it (`changed`, pure) and, when they differ, puts one line before the input's
output, right after the aside about bh-02's tools: `(namespace: + hits (list, 42 items), edit(path,
old, new) (function); ~ config (dict, 7 keys); - tmp)`. `+` is a name added, `~` one whose
description changed, `-` one removed; a callable is worded as `carried()` words it (`_phrase`). It
is capped at 600 characters of names (removals count), and what is past it is counted
(`, and 5 more`). The listing it starts from is the one after the previous input in the same
worker, and for the first input the one after the opening's startup files ran, so a startup file's
functions are never reported as added (the opening's own asides told them). It reports bindings
and the size of the built-in containers: a list that grew in place (`list, 42 items` to `list, 43
items`) shows as `~`, but an object changed in place in any other way, or a name rebound to another
object of the same description (`x = 1`, then `x = 2`), is not seen, as only descriptions are
compared (never a `repr`). An input that changes nothing adds nothing, and when either listing was
cut at 200 names no line is told, since a name past the cut would look removed. After a worker
died or was stopped, the new one's first input is also told which names the dead one last held,
apart from the startup files' (`(the earlier REPL's names are gone: hits, edit, config)`, same cap),
once, in the same parenthesis as the aside that the REPL was started again, after it. A new
session or a resume has no earlier listing and adds nothing. The python section of the system
prompt has one sentence saying the line exists.

Before the input's own Python opens one of those files, the same audit hook can ask bh-02 about
it (`access`, `agent:access`): each input's `exec` names the kinds some row asks about
(`"ask": ["write"]`, say), and for an open of that kind the Python process sends `{"op": "ask", "id",
"kind", "path"}` and waits for `{"op": "answer", "id", "refuse"}`, once per file and kind an
input (any thread may ask; the answer goes to the one waiting). A `refuse` that is text raises a
PermissionError at the open, so the file is never opened, and the traceback ends at the input's
own line (`worker.py`'s frames are left out); the `done` carries every refusal (`refused`), which
ends the input's text in brackets (`(bh-02 refused to let this input write PATH: ...)`), so the
model hears of it even when the code caught the error.
What it does not see: a program an input runs (`subprocess`), an `os.open`, a rename, a replace
or a delete, a file outside the project. It tells the model something before a file changes; the
jail is what stops what must never happen.

Every other tool there is is a function in each input's namespace, `tools.NAME(arg=...)`,
rebuilt before each input from `tools.specs()` (sent with its `exec`; `help(tools.NAME)` says
what one takes). A call goes back to bh-02 (`{"op": "call", "id", "name", "input"}`, answered
`{"op": "answer", "id", "content", "failed"}`) and to `tools.call`, so it runs as the model's
own call to that tool would: put to the `approval` rule, then to `asides`, whose asides go with the
result of the input that made it. It returns the tool's `content`, and raises `tools.Error` with
it when the call did not run or failed. What changed in them since the model was last told is
told before the input's own output. An input that binds `tools` itself keeps its own: the
namespace's is a view of the registry, never where a tool is registered.

A new Python process's first input is also told what the startup files did (`startup`, functions kept
across sessions, in order): the person's own, `$XDG_CONFIG_HOME/bh-02/startup.py` (else
`~/.config/bh-02/startup.py`), for the functions they want in every project, then the project's,
`.bh-02/startup.py`, the model's own. A name starting `$XDG_CONFIG_HOME/` is in the person's
config directory (that variable's value, else `~/.config`, as for the models file), one
starting `~/` in their home, any other from `root`; a single string is one file, and anything
but a name or a list of names is the row's config error. Confined, the process runs each that is
there as an input of its own and says which of its functions are told to the model, by signature
up to a budget and then by name (below), or its traceback; one failing doesn't stop the
next, and one that isn't there is passed over. A UTF-8 byte order
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
  itself is not there: its functions run and `inspect.getsource` shows them (through
  `linecache`), but `open` on its path finds nothing, a function that reads a file beside it
  finds nothing either, and `__file__` is not set (nor for the project's: each runs as an
  input). The model is told how to see one (`inspect.getsource(NAME)`, NAME a function as the startup line lists it).
- But only when reading it goes nowhere an input may write (`host_paths.walked`, the walk the
  models file and memory files outside the project are held to: each directory and link on the
  way, as named and as resolved): the
  project, or another root the Python process's jail lets an input write (its `writes()`: a `write`
  the person added to `runner:confined`). A person's file there (bh-02 run from the home directory) or whose way
  passes through one (a config directory linked into a dotfiles repository being worked on) is
  read as the project's is: the model could have written it, or chosen where it leads, so the
  Python process reads it, at its resolved place when that is in such a root. If that fails (the jail
  can't see where it leads), the aside says why bh-02 did not read it.
- Across sessions, the walk can't know what an earlier session's jail let its inputs write, so
  the jail itself keeps them out: `runner:confined` denies writing bh-02's config directory wherever
  it is under a writable root (`host.trusted`, the runner plugin's README). A session run from
  the home directory can't make the person's file a link to a key for the next session to read.

Each file runs once, at its first place in the list. Whose a file is goes by how it is named, not
by where it is read: one named from the root is the project's, one named from the person's config
directory, their home or `/` is theirs. `instructions_for` tells the model that only the
project's startup file is its to edit, and names the person's, which comes before it, as theirs.

Which functions the model is told of is decision-0006's point 1, and the Python process decides it,
where the objects are. Confined, a startup file's input prints, last and on a line of its own, one
line of JSON (`client._startup_input`): `{"told": [[name, signature], ...]}`, each name with
`str(inspect.signature(...))` (null when that fails: a builtin without a signature, a default
whose `repr` raises), at most 640 characters of it. A name is told when it has no leading
underscore and its value is a function, method or class that is `callable`, was not an object the
namespace held before the file ran, and has the namespace's `__name__` as its `__module__`: a def,
a class or a lambda the file's code made. An import is not one (its `__module__` is another
module's), nor is `partial(...)` of one; a name bound to what an earlier file made (the project's
`display = show` for the person's `show`) is not told again; an instance, a callable one too, is
data, not a function or a class; a value that raises when asked is left alone, and the file does not
fail for it. When the file binds `__all__` (a list or a tuple that is a new object after the file
ran: one an earlier file left is that file's), the told names are exactly the callables it names,
imported ones and underscored ones included, in its order; a name it lists that the file never bound
is nothing to tell, and so is an entry that is no name. Everything else the file bound works as it
does and is not told, nor counted. That line is the Python process's, so the host reads it as data
and words it in pure functions (`client.startup_ran`, `client.signed`): control and format
characters (C0, DEL, C1, bidi overrides, zero-width) are stripped, a name that is not an
identifier (a file can bind any string through `globals()`) is left out, each signature is cut at
160 characters and ends in `…`, one that could not be read is `name(...)`, and a last line that is
not that shape is said not to be a listing and never quoted.

The signatures are told up to 600 characters across the REPL's startup files (`client._BUDGET`),
the person's file first, counted as the model reads them (`name(signature)`, after the cleaning
and the cut, not the separators). The first function that does not fit ends the signatures, and
it and every function after it, in that file and in the files that run after it, is told by name
only, so nothing is left out. The budget is threaded through the opening's loop as a value
(`startup_ran(name, when, line, left)` returns the aside and what is left), not kept on
`PythonProcess`. The first input is told `(PATH ran first: functions run_tests(path='.', *,
quiet=True), changed(); by name only: more, other)`; a file that tells none, `PATH ran next: no
public functions`. `help(name)` shows a function's docstring and `inspect.getsource(name)` its
source, as for any function: both are pulled, and cost nothing until the model asks. `_keep` says
all this once, in the `python` section, which stays fixed for a conversation (which functions are
told, what they cost, and the docstring convention for a file the model writes); the signatures
arrive with the first input's output, never in the prompt. They are told at startup only: a REPL
started again runs the files and tells them again, a function an input defines later is not
announced, and after `/compact` they live only in the model's summary (the listing `/compact` is given leaves them out, since the model was told them). Unconfined, nothing is
listed (the model runs the file as an input of its own, which the person is asked about), so the
section does not say it is, though it says the docstring convention. There is no decorator and
nothing of bh-02's in a startup file: it runs unchanged outside bh-02, and one that still marks its
functions with decision-0004's decorator fails at start with a `NameError` (the name is no longer
bound), reported on the startup line like any failing file. The line is bounded by the Python
process's output cap (20,000 characters): a file with so many functions that it passes that is said
not to be listable.

Each file that told something is then checked against the docstring convention and for types
(decision-0006's point 7), in the jail and after the file, by a second input (`client._check_input`)
that runs `startup_check.py` as a program: `python -I startup_check.py --ruff --mypy --cache-dir=DIR
--json NAME` (the project's file, which the jail reads) or `... --name NAME -` with the text on stdin
(the person's, which the host handed in), under the Python process's own interpreter
(`sys.executable`, whose environment every jail reads), with a timeout (120 s of the input; mypy gets
90 of them, cold on a file that imports textual it takes 13). Ruff runs as `sys.executable -m ruff` with bh-02's flags only
(`startup_check.RUFF_FLAGS`: `--isolated --no-fix --select D101,D103,D205,D415,D419`, `--output-format
json`, `--stdin-filename NAME`), so no configuration the model could write loosens it. The program's
pure core reads the text and executes none of it: `examples` is bh-02's own rule (`ast` and
`doctest.DocTestParser`: for each function and class the file tells, an example, a doctest block or a
`::` literal block that has a blank line before it, code `example`; doctest blocks that parse, each
with a blank line before it, code `doctest`), and `ruff_findings` keeps ruff's findings that are on a
told definition (its line for `D101`/`D103`, its docstring's lines for the rest) and drops a private
function's, a method's and the module's. `mypy_findings` gives each error in mypy's `--output json`
(one object a line, with the code) to the told function or class its line is in, a decorator's and a
method's included, else to `ELSEWHERE` (`<file>`, no function's name): an import, a statement, a
private function. The code is mypy's when `MYPY_CODES` has it (written out, its 78 names compared with
`mypy.errorcodes.error_codes` by a test, so a mypy that adds one fails there), else `mypy`, so what
reaches the host is always a name from the closed set `CODES`. Which functions are told is decided again there, from the
syntax (the public ones the file defines, or the ones its literal `__all__`, `=` or `+=`, names; the
last definition of a name), and the host takes the names the live listing also told. The program
prints one line, `{"misses": [[name, [code, ...]], ...]}`, codes only; the host reads it as data like
the listing (`client.startup_checked`): a name the file did not tell, or a code outside
`startup_check.CODES`, is dropped or makes the line not the report, a message is never said, and
the aside is `PATH findings: a D103, example, no-untyped-def; b doctest; elsewhere in the file:
import-not-found`, in the order the file told its functions, codes in `CODES` order (ruff's, bh-02's,
mypy's), the file's own last, or nothing when nothing misses. A check that did not run
(the program failed, timed out, or printed something else) is `PATH docstrings and types could not be
checked`; a finding stops no file and hides no function. A file that failed, or told nothing, is
not checked. A function with no docstring has no example, so it breaks `example` beside ruff's
`D103`; ruff calls a name with a leading underscore private even when `__all__` names it (no `D103`),
and reads a set or a string `__all__` as naming nothing public, so those miss `example` alone.

**mypy** runs as `sys.executable -I -m mypy --strict --config-file= --output json
--cache-dir=DIR` (`startup_check.MYPY_FLAGS`; bh-02's flags only: no configuration file, since a
project's can name plugins mypy imports and the model writes it), in `_mypied`, over a copy of the
text named `bh_startup.py` alone in a directory under `$TMPDIR` (the jail's scratch; removed after),
with that directory as its working directory and every `MYPY*` variable taken out of its environment
(`MYPY_CACHE_DIR` beats `--cache-dir`, `MYPYPATH` adds modules to find, `MYPY_NUM_WORKERS`: a startup
file runs in the Python process, which starts the check with its environment). What it can import is
what the REPL can: the REPL is `python -I`, so its path is the interpreter's (the standard library,
site-packages, the editable installs' `.pth` entries) and neither the working directory nor the
file's own, and mypy is the same interpreter with `-I`, so `pyinfo` reads the same path and keeps
its first entry; mypy adds the working directory and the file's directory itself, which is why the
copy is alone in its directory and the program runs there. A module beside the startup file or in
the project is an `import-not-found` (tested against the real REPL); a package bh-02 depends on is
found; an installed package with no types is `import-untyped`, a strict finding; a `sys.path.insert`
in the file is invisible to mypy (`# type: ignore[import-not-found]`). A name the REPL provides
(`tools`, or one an earlier startup file made: each file is checked alone) is declared with a bare
annotation, `tools: Any`, which binds nothing when the file runs (the worker only rebuilds `tools`
unless an input bound its own) and satisfies mypy; the python section tells the model so.

The cache is the python row's `mypy_cache`, `.bh-02/mypy_cache` under the root by default (or
absolute): the writable roots of a jail are the project, its scratch (new at every start, so cold at
every start: 3.3 s against 0.3 s warm for one file, measured in a real bubblewrap jail on the pinned
mypy) and the model's auto memory (its notes). mypy puts a `.gitignore` of `*` and a `CACHEDIR.TAG`
in its cache directory, so git ignores it with no line in the project's own, and the project's own
`.mypy_cache` is a different directory. The cache is sqlite shards in this mypy; several starts at
once share one (four cold runs at once on one cache all reported, by hand), and a cache that is damaged or a directory that can't be written makes mypy
exit 2 with an internal error, so the program tries again with no cache (`--cache-dir=/dev/null`):
cold, correct, and never deleting anything (delete the directory if it keeps doing that).

mypy is a runtime dependency of this plugin, at the root's pin: a git commit of mypy 2.4.0-dev, the
first that types PEP 661 sentinels, which `uv.lock` holds once. Move both to `mypy>=2.4` from PyPI
when it is released (and the plugin's `[tool.uv.sources]` entry goes).

`startup_check.py` is a program of its own, standard library only (the gate's `worker-stdlib-only`),
run by path and never imported by the Python process or the app's command line, because importing
this package imports cordis. `bh-02 check-examples FILE...` (the app's `cli.py`) finds it by the
plugin's name, with no import (`importlib.util.find_spec`), and runs `startup_check.py FILE...` under
its own interpreter: the example rule alone, one line a finding, exit status 1 on a finding, 0 on
none, 2 for a usage error or a file it can't check (unreadable, not UTF-8, not Python). It needs no
session or model, and is for the person, a pre-commit hook and CI, beside ruff's line:

```sh
ruff check --isolated --no-fix --select D101,D103,D205,D415,D419 .bh-02/startup.py
bh-02 check-examples .bh-02/startup.py
mypy --strict --config-file= .bh-02/startup.py
```

mypy's line is run in the project, which mypy also searches (the working directory and the file's
own), so a startup file that imports a module beside it passes there and is an `import-not-found` at
a REPL start. Pin the mypy version CI installs, as the ruff one: the codes are its rules.

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: startup-ruff
        name: startup file docstrings (ruff)
        entry: ruff check --isolated --no-fix --select D101,D103,D205,D415,D419
        language: system
        files: (^|/)startup\.py$
      - id: startup-examples
        name: startup file docstring examples (bh-02)
        entry: bh-02 check-examples
        language: system
        files: (^|/)startup\.py$
      - id: startup-mypy
        name: startup file types (mypy)
        entry: mypy --strict --config-file=
        language: system
        files: (^|/)startup\.py$
```

```yaml
# a CI step
- name: Startup file docstrings and types
  run: |
    ruff check --isolated --no-fix --select D101,D103,D205,D415,D419 .bh-02/startup.py
    bh-02 check-examples .bh-02/startup.py
    mypy --strict --config-file= .bh-02/startup.py
```

`_keep` says what the check is in the `python` section: confined, that the startup files are checked
at REPL start, for a docstring and for types strictly, what the startup line's codes mean (and
`elsewhere in the file`), that a finding stops and hides nothing, and the three commands to run in an
input for the detail (`python -m ruff check ...`, `python -m python_cordis_plugin.startup_check FILE`,
`python -m mypy --strict --config-file= FILE`, `python` being `sys.executable`; the second imports
this package, which works in the model's REPL and costs a moment). Unconfined nothing is listed or
checked, so it is given the three commands to check the file it writes. Either way, for a project
startup file, it is told in one sentence to declare a name the REPL provides with a bare annotation
(`tools: Any`). ruff is a runtime dependency of this plugin (so the app's), at the version the codes
were measured on or later; mypy at the pin above.

The namespace's `__name__` is `__kernel__`: a startup file may test it, and renaming it would
break that silently.

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

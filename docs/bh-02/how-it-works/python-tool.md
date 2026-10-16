# The python tool

The tool bh-02 ships is `python(code)`, and it carries code. This is CodeAct: the model acts by
writing Python, and only what that Python prints reaches the model. The python row registers it
with `tools`, beside whatever tools other rows register, and tells the model about it in a
section of the system prompt. To the model the tool is a
Python REPL of its own that persists for the run.

## What an input can do

Each call is an input to one Python process, the one the runner started. It is plain Python, not
IPython, and nothing of bh-02's is in its namespace but `tools` (below). An input:

- reads and edits files with `open` or `pathlib`;
- runs programs (`git`, a test runner, `python`) with `subprocess`, in the project directory;
- keeps what it defines: variables, functions and imports stay for later inputs.

The model is told to work in Python rather than through a shell, to capture a program's output
(output that isn't captured never reaches it), and to give a program a timeout.

What comes back is what the input printed, and the value of its last expression. Each of output
and error is capped at 20,000 characters: a longer one keeps its first 6,000 and last 14,000,
and the whole is saved to a file the cut names. A traceback names each line as `<input N>`, so the
model sees the line that failed, even in a function it defined inputs ago.

## bh-02's other tools, from an input

Every other tool bh-02 offers the model (a layer row's, an extension's) is also a function in the
namespace: `tools.NAME(arg=...)`. A call goes back to bh-02 and runs as the model's own call to
that tool would: put to the approval rule (and so to you, when it is unjailed or runs in bh-02's
own process), run by the tool, then given to `asides`, whose asides reach the model with the
result of the input that made the call. It returns the tool's result as text, and raises `tools.Error`
when the call did not run or failed. `help(tools.NAME)` shows what one takes. Each input is
sent the tools as they are, and the first input that sees a change says so before its output, so
a tool added mid-conversation can be called from code at once, even where the model's own list
of tools stays as the conversation began (TASK-0057's `fixed` providers). The namespace is a
view of the registry, never where a tool is registered.

A function the model defines in an input, a function a startup file defines and a registered tool differ in what holds them:

| | A function defined in an input | A function a startup file defines | A registered tool |
|---|---|---|---|
| Where it lives | the Python process's namespace | the Python process's namespace, put there by its startup file | `tools`, the registry a row (or an extension) registers into |
| How long | until the process ends (`/clear`, a restart, a resume) | as long as its startup file: a new REPL runs the file again (with `--no-jail`, once the model runs it) | as long as its row: an extension's lasts as long as its file, across sessions |
| Who can call it | later inputs | later inputs | the model directly, and inputs as `tools.NAME(...)` |
| Asked about, told asides | no: the input that calls it was | no: the input that calls it was | each call, as any tool call |
| Where it runs | in the Python process | in the Python process, with an input's limits | where its row says: an extension's in the extensions process, a layer row's in bh-02 |

A function worth keeping between sessions goes in the project's startup file, where a new REPL
tells the model of it; a capability the model should have as a tool, or that should run
outside the Python process, is an extension's tool.

## How long the namespace lasts

The namespace lasts the run. A `/model` switch and `/compact` keep it. A new Python process starts
empty: at launch and on a resume, after `/clear`, `/release` or `/restart python`, and when the
last one died or its jail ended. The first input in a new one is told its variables are gone, and
why when it knows. The transcript is the record; the namespace is a cache.

`Ctrl+C` interrupts the running input, and the namespace survives it.

## Startup files

A new Python process can run setup code before the first input, when it is jailed:

1. yours: `~/.config/bh-02/startup.py` (`$XDG_CONFIG_HOME/bh-02/startup.py` when that is set), for
   functions you want in every project;
2. the project's: `.bh-02/startup.py`, the only one the model is told it may edit.

The first input is told what each made for the model, or its traceback, and which of its functions miss the docstring convention ([below](#checking-the-docstrings)). One failing doesn't stop
the other. Without the jail they don't run unasked: the model is told to run them as inputs, which
you are asked about like any other, and nothing is listed.

### Startup functions

The model is told of a startup file's public functions: the functions and classes the file defines
under a name with no leading underscore. When the file sets `__all__`, exactly the callables it
names instead, imported ones included. An import is not a function the file defines, and a name
with a leading underscore works but is not told; nothing is marked, so the file runs unchanged
outside bh-02. The first input is told each by name and signature, in the order the file made them:

```text
(.bh-02/startup.py ran first: functions run_tests(path='.', *, quiet=True), changed())
```

That costs the model context in every session, so it is bounded: the first 600 characters of
signatures across your file and the project's, in the order they run, then the rest by name only,
so nothing is left out:

```text
(.bh-02/startup.py ran next: functions fast(x); by name only: slow, slower)
```

A file that tells none says `no public functions`. Keep public only what is worth telling every
session, with a short signature. The docstring and the source cost nothing until the model asks:
`help(name)` shows a function's docstring, `inspect.getsource(name)` its source. The model is told
the docstring convention for the file it writes: a summary line; what the signature doesn't say, in
the project's own field style (Google's when it has none), never the types again; then examples in
reST, a doctest block (`>>>` calls with their output) when the output is fixed, a `::` block when it
isn't. Control and format characters are stripped from a signature, one over 160 characters is cut
there, and one Python can't read is `name(...)`; a name that is not an identifier is left out.

The model is told this once, at startup: a new REPL runs the files and tells them again, a function
the model defines in a later input is not announced, and after `/compact` the signatures live only
in the model's summary. A file that still marks its functions with the old decorator fails at start
with a `NameError`, reported on the startup line as any failing file is.

bh-02 reads your file itself and sends its text in, since a Linux jail has no home directory in
it. So whatever your file holds, the model can read. The project's file is read inside the jail.

### Checking the docstrings

A tool, not the model, says whether a told function follows the convention above. At every REPL
start, after a startup file runs, two checks run on it inside the jail, as programs under bh-02's
own interpreter, over the file's text (yours is the text bh-02 handed in; the jail can't read the
file). Neither runs any of the file's code.

- **ruff**, with bh-02's flags only, so no ruff configuration the project holds (which the model can
  write) loosens it: a docstring on each public function and class (`D101`, `D103`), a summary line
  (`D205`, `D415`) and none empty (`D419`).
- **bh-02's example rule**, for what ruff has no rule for: an example in the docstring (a doctest
  block or a `::` literal block, code `example`), and doctest blocks that parse and have a blank
  line before them (code `doctest`). The blank line after one can't be checked: `doctest` reads
  everything up to it as the expected output.

The startup line then names each told function that misses and the codes it breaks, never a tool's
message, which would quote the file:

```text
(.bh-02/startup.py ran first: functions run_tests(path='.', *, quiet=True), changed(). .bh-02/startup.py docstring findings: run_tests D415, example; changed doctest)
```

A file with no findings adds nothing. A finding is advice: it never stops a file running or hides a
function, and a function that is not told (a private one, a method) is not in it. A check that
could not run is said so (`docstrings could not be checked`). The model sees the detail by
running the tool in an input, which its prompt tells it how to do; your file's findings are yours,
since the model can't edit it. Ruff calls a name with a leading underscore private even when
`__all__` names it, so there such a function misses `example` alone.

With `--no-jail` nothing runs unasked, so neither check does: the model is given the two commands
below to run as inputs of its own after it writes a function.

The same checks run without a session or a model, for you, a pre-commit hook and CI. ruff's line
is bh-02's flags to ruff's own command (pin the ruff version CI installs: the codes are its
rules). The example rule is a bh-02 command, [`bh-02
check-examples`](../reference/command-line.md#bh-02-check-examples). Each exits 1 on a finding:

```sh
ruff check --isolated --no-fix --select D101,D103,D205,D415,D419 .bh-02/startup.py
bh-02 check-examples .bh-02/startup.py
```

A pre-commit hook (`.pre-commit-config.yaml`), which passes the changed startup files to both:

```yaml
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
```

A CI step (GitHub Actions) with the same two lines:

```yaml
- name: Startup file docstrings
  run: |
    ruff check --isolated --no-fix --select D101,D103,D205,D415,D419 .bh-02/startup.py
    bh-02 check-examples .bh-02/startup.py
```

Ruff checks every docstring in the file, a private function's and a method's too, where the
session's check names only the told functions. `ruff` and `bh-02` have to be on the `PATH` of the
hook or the job; with `uv tool install ./bh-02/app` bh-02 is, and `uvx ruff` or `pipx run ruff` runs
ruff.

## What an input touched

The Python process hears each file an input's own code opens under the project, with an audit
hook. The tool answers each call with that list (its `touched()`), and the loop hands it to the rows that add asides,
which is how a subdirectory's `CLAUDE.md` arrives when the model first opens a file there. Files a
program the input runs opens are not heard, since that happens in another process.

## The process itself

The Python process is `worker.py`, run as `python -I worker.py SOCKET` inside the jail. It uses
the standard library only, so nothing of bh-02's own crosses into the jail with it. Its one
channel is a Unix socket that carries an input in and its output back. The `python` row
(`python:tool`) is bh-02's end of it: it starts the process through the runner, sends each input,
starts a new process when the last one died, and stops its own process on `/release`. It binds
no key: it reaches the loop through `tools` and the model through `system`.

The python plugin's README has the details: [python-cordis-plugin](../reference/plugins/python.md).

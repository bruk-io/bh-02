# The python tool

The tool bh-02 ships is `python(code)`, and it carries code. This is CodeAct: the model acts by
writing Python, and only what that Python prints reaches the model. The python row registers it
with `tools`, beside whatever tools other rows register, and tells the model about it in a
section of the system prompt. To the model the tool is a
Python REPL of its own that persists for the run.

## What an input can do

Each call is an input to one Python process, the one the runner started. It is plain Python, not
IPython, and nothing of bh-02's is in its namespace. An input:

- reads and edits files with `open` or `pathlib`;
- runs programs (`git`, a test runner, `python`) with `subprocess`, in the project directory;
- keeps what it defines: variables, functions and imports stay for later inputs.

The model is told to work in Python rather than through a shell, to capture a program's output
(output that isn't captured never reaches it), and to give a program a timeout.

What comes back is what the input printed, and the value of its last expression. Each of output
and error is capped at 20,000 characters: a longer one keeps its first 6,000 and last 14,000,
and the whole is saved to a file the cut names. A traceback names each line as `<input N>`, so the
model sees the line that failed, even in a function it defined inputs ago.

## How long the namespace lasts

The namespace lasts the run. A `/model` switch and `/compact` keep it. A new Python process starts
empty: at launch and on a resume, after `/clear`, `/release` or `/restart python`, and when the
last one died or its jail ended. The first input in a new one is told its variables are gone, and
why when it knows. The transcript is the record; the namespace is a cache.

`Ctrl+C` interrupts the running input, and the namespace survives it.

## Startup files

A new Python process can run setup code before the first input, when it is jailed:

1. yours: `~/.config/bh-02/kernel.py` (`$XDG_CONFIG_HOME/bh-02/kernel.py` when that is set), for
   helpers you want in every project;
2. the project's: `.bh-02/kernel.py`, the only one the model is told it may edit.

The first input is told which names each defined, or its traceback. One failing doesn't stop the
other. Without the jail they don't run unasked: the model is told to run them as inputs, which you
are asked about like any other.

bh-02 reads your file itself and sends its text in, since a Linux jail has no home directory in
it. So whatever your file holds, the model can read. The project's file is read inside the jail.

## What an input touched

The Python process hears each file an input's own code opens under the project, with an audit
hook. The tool answers each call with that list (its `touched()`), and the loop hands it to the rows that add notes,
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

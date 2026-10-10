"""The kernel's own process: one persistent Python namespace behind a Unix socket.

Run by path (``python -I worker.py SOCKET``), usually inside a jail. It imports the standard
library and nothing else, so nothing of the host crosses into the jail with it. The namespace
holds only what inputs put there: an input is plain Python, and the jail decides what it may touch.

Wire: newline-delimited JSON. The host sends ``{"op": "hello"}`` once (a readiness probe
connects and closes without a word, so the worker keeps accepting until one speaks), then
``{"op": "exec", "code", "ask"}`` per input, and the worker ends every input with
``{"op": "done", "output", "error", "touched", "refused"}``: `touched` the files under the
directory the worker started in (the project root) that the input's own code opened with
`open()` or `pathlib`, read or written, each once by its absolute path (an audit hook,
`_Kernel.heard`: what Python opens, not what a program it runs does, nor an `os.open`). `ask`
names the kinds (`read`, `write`) the host wants to be asked about: before the input's own code
opens such a file to one of them, the worker sends ``{"op": "ask", "id", "kind", "path"}`` and
waits for ``{"op": "answer", "id", "refuse"}``, once per file and kind per input; a `refuse` that
is text stops the open with a PermissionError carrying it, and `refused` is every such refusal,
so the model is told of it even when the input's code caught the error. `tools` (each input's) are
bh-02's tools other than `python`, as their specs: the namespace's `tools` is rebuilt from them
(`_Offered`), each a function that sends ``{"op": "call", "id", "name", "input"}`` and waits for
``{"op": "answer", "id", "content", "failed"}``, the host running it as the model's own call runs
(asked about, noted), and returns `content`, or raises `tools.Error` with it when `failed`. A
worker nobody says hello to
(its host was killed while starting it) exits once its parent is gone, or after `_HELLO_S` (a
second argument overrides it), rather than wait in `accept` for ever; one whose host disconnects
exits too, even mid-input.

Inputs run on the main thread, because only the main thread receives signals: SIGINT raises
`KeyboardInterrupt` in the running input and leaves the namespace as it was. With no input
running, SIGINT is ignored.
"""

import ast
import contextlib
import errno
import inspect
import io
import json
import linecache
import os
import queue
import signal
import socket
import tempfile
import threading
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from sys import _getframe, addaudithook, modules
from types import FrameType
from typing import Any

__all__ = ["input_traceback", "main", "split_last_expression"]

_MAX_OUTPUT = 20_000
_HEAD = 6_000  # of an output cut to `_MAX_OUTPUT`, how much is its start; the rest is its end
_INPUT = "<input"  # how every input's file name starts: the third input is `<input 3>`
# the project's files one input's `touched` names at most: a walk of a big tree stays one line
_TOUCHED = 1_000
_HELLO_S = 60.0  # the host says hello within milliseconds of the worker listening
_READ, _WRITE = "read", "write"  # the kinds of opening the host may ask to be asked about
_LOOK_S = 0.5  # how often a worker waiting for its hello checks that its parent is still there
_TOOLS = "tools"  # the name an input calls bh-02's other tools by: `tools.NAME(...)`


class ToolError(Exception):
    """A call to one of bh-02's tools that did not run (declined, unknown, its arguments wrong)
    or failed: why, as bh-02 says it. `tools.Error` in an input."""


def _function(
    spec: Mapping[str, Any], ask: Callable[[Mapping[str, Any]], dict[str, Any]]
) -> Callable[..., str]:
    """One of bh-02's tools as a function of its arguments (keyword arguments, as its spec names
    them): the host runs the call, and its result is returned as text, or raised as a ToolError
    when it did not run or failed."""
    name = str(spec.get("name"))
    properties: Mapping[str, Any] = {}
    required: list[Any] = []
    match spec.get("parameters"):
        case {"properties": Mapping() as given, "required": list() as named}:
            properties, required = given, named
        case {"properties": Mapping() as given}:
            properties = given

    def call(**arguments: Any) -> str:
        answer = ask({"op": "call", "name": name, "input": arguments})
        content = str(answer.get("content", ""))
        if answer.get("failed"):
            raise ToolError(content)
        return content

    call.__name__ = call.__qualname__ = name
    wanted = [
        f"  {key} ({(each or {}).get('type', 'any') if isinstance(each, Mapping) else 'any'}"
        f"{', required' if key in required else ''})"
        for key, each in properties.items()
    ]
    call.__doc__ = "\n".join(
        [str(spec.get("description", "")), *(["", "Arguments:", *wanted] if wanted else [])]
    )
    call.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [
            inspect.Parameter(
                str(key),
                inspect.Parameter.KEYWORD_ONLY,
                default=inspect.Parameter.empty if key in required else None,
            )
            for key in properties
            if str(key).isidentifier()
        ]
    )
    return call


class _Offered:
    """`tools` in an input's namespace: bh-02's tools other than `python`, each a function
    (`tools.NAME(arg=...)`, `help(tools.NAME)`); `tools.Error` is what one raises when its call
    did not run or failed. A view of bh-02's tools, rebuilt before each input: never where a tool
    is made."""

    Error = ToolError

    def __init__(self, functions: Mapping[str, Callable[..., str]]) -> None:
        self._functions = dict(functions)

    def __getattr__(self, name: str) -> Callable[..., str]:
        try:
            return self._functions[name]
        except KeyError:
            listed = ", ".join(sorted(self._functions)) or "none"
            raise AttributeError(f"bh-02 has no tool {name!r} now; its tools here: {listed}") from None

    def __dir__(self) -> list[str]:
        return sorted(self._functions)

    def __repr__(self) -> str:
        listed = ", ".join(sorted(self._functions)) or "none"
        return (
            f"<bh-02's tools: {listed}; tools.NAME(arg=...) calls one, help(tools.NAME) says what it takes>"
        )


def split_last_expression(code: str, name: str = "<input>") -> tuple[ast.Module, ast.Expression | None]:
    """The input's statements, and its last line when that is an expression (shown, notebook
    style). `name` is the input's file name, which a syntax error names."""
    tree = ast.parse(code, name, "exec")
    last = tree.body[-1] if tree.body else None
    if isinstance(last, ast.Expr):
        tree.body.pop()
        return tree, ast.Expression(last.value)
    return tree, None


def input_traceback(exc: BaseException) -> str:
    """Format a failed input's exception from its first input frame (`<input 3>`) on: the worker's
    own frames (the `exec` that ran the input) say nothing about the input. Keep every frame if
    none is an input's. Nor do the worker's frames below the input's say anything: an open the
    host refused is raised from the audit hook (`_Kernel._asked`), so the traceback ends at the
    input's own line, as a PermissionError from the file system would."""
    tb = exc.__traceback__
    while tb is not None and not tb.tb_frame.f_code.co_filename.startswith(_INPUT):
        tb = tb.tb_next
    shown = traceback.TracebackException(type(exc), exc, tb or exc.__traceback__)
    if any(frame.filename != __file__ for frame in shown.stack):
        shown.stack = traceback.StackSummary.from_list([f for f in shown.stack if f.filename != __file__])
    return "".join(shown.format()).rstrip()


class _Channel:
    """The socket: a reader thread feeding a queue, and the answers to the worker's questions
    (`ask`) to the thread waiting for each. Any thread may write: an input's own threads ask too."""

    def __init__(self, conn: socket.socket, file: io.TextIOWrapper) -> None:
        self._conn = conn
        self._file = file  # the one reader of this connection: a second would lose what the first buffered
        self.inbox: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._sending = threading.Lock()  # one message on the socket at a time, whole
        self._asked = 0  # the last question's number
        self._waiting: dict[
            int, queue.Queue[dict[str, Any]]
        ] = {}  # a question's number: where its answer goes
        threading.Thread(target=self._read, name="kernel-reader", daemon=True).start()

    def _read(self) -> None:
        for line in self._file:
            if line.strip():
                message = json.loads(line)
                waiting = self._waiting.get(message.get("id")) if message.get("op") == "answer" else None
                (waiting or self.inbox).put(message)
        # The host is gone. An input may be spinning on the main thread and never look at the
        # inbox again, so the worker ends here rather than outliving the program that ran it.
        os._exit(0)

    def send(self, message: Mapping[str, Any]) -> None:
        line = (json.dumps(message) + "\n").encode("utf-8")
        with self._sending:
            self._conn.sendall(line)

    def ask(self, question: Mapping[str, Any]) -> dict[str, Any]:
        """Send `question` and wait for the host's answer to it. The wait is the open's, on the
        thread that opens: SIGINT still interrupts it on the main thread."""
        with self._sending:
            self._asked += 1
            number = self._asked
        answer: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._waiting[number] = answer
        try:
            self.send({**question, "id": number})
            return answer.get()
        finally:
            self._waiting.pop(number, None)


class _Kernel:
    """The namespace and the input loop. `root` is the directory the worker started in, the
    project's (a jail starts it there): the files `touched` names are under it."""

    def __init__(self, channel: _Channel, root: str) -> None:
        self._channel = channel
        self._namespace: dict[str, Any] = {"__name__": "__kernel__"}
        self.running = False  # an input is running, parsed or failing included: SIGINT interrupts it
        self._hearing = False  # the input's own code is running: what it opens is heard
        self._inputs = 0
        self._had: set[str] = set()  # every name the namespace has held since the worker started
        self._saved: str | None = None  # where a cut output is kept whole: made at the first cut
        self._under = os.path.join(root, "")  # the root, ending in a separator
        # The globals the import system's own code runs with: the frozen importlib modules'.
        self._importlib = (vars(modules["_frozen_importlib"]), vars(modules["_frozen_importlib_external"]))
        self._touched: dict[str, None] = {}  # the project's files the running input opened, in order
        self._asking: frozenset[str] = frozenset()  # the kinds of opening the host asks about now
        self._answered: dict[tuple[str, str], str | None] = {}  # this input's answers, by (kind, path)
        self._refused: list[str] = []  # what this input was refused, as the model is told it

    def heard(self, args: tuple[Any, ...]) -> None:
        """An `open` audit event's arguments (`path, mode, flags`): a file the input's own code
        opened with `open`, `io.open` or `pathlib`, read or written. Kept when it is under the
        root, and not opened by the import system (a module imported is not a file worked on),
        until `_TOUCHED` are kept; a file outside the project never counts towards that. And,
        when the host asks about the kind of opening (`_asking`: read, write, both for `+`),
        asked about first (`_asked`), which may stop it.

        Only an event whose mode is a string, which is an `open()` of a file. `os.open` raises
        it with mode None and without its `dir_fd`: `shutil.rmtree`, `os.fwalk` and a
        `TemporaryDirectory`'s cleanup open each name relative to a directory's descriptor, and
        the bare name would be resolved against the working directory (removing a temporary
        `src/db` would name the project's `src` and `db`). So an `os.open` is not heard, nor
        `Path.touch`, which is one. Nor is a file opened by number, a directory listed, or a
        file opened while the input's own code is not running (`_own`): a failed input's
        traceback reads the source file of each of its frames."""
        if not self._hearing or len(args) < 2 or not isinstance(args[1], str):
            return
        name = args[0]
        if not isinstance(name, str | bytes | os.PathLike):
            return
        path = os.path.abspath(os.fsdecode(name))
        if not path.startswith(self._under):
            return
        kinds = [kind for kind in _kinds(args[1]) if kind in self._asking]
        if not kinds and (path in self._touched or len(self._touched) >= _TOUCHED):
            return  # nothing to keep and nothing to ask: no walk of the stack (`_importing`)
        if _importing(*self._importlib):
            return
        if path not in self._touched and len(self._touched) < _TOUCHED:
            self._touched[path] = None
        for kind in kinds:
            self._asked(kind, path)

    def _asked(self, kind: str, path: str) -> None:
        """Ask the host whether the input may open `path` to `kind`, once an input: a refusal is
        kept, told with the input's result (`refused`), and raised here as a PermissionError, so
        the open never happens."""
        if (kind, path) not in self._answered:
            answer = self._channel.ask({"op": "ask", "kind": kind, "path": path}).get("refuse")
            refused = str(answer) if answer else None
            self._answered[(kind, path)] = refused
            if refused:
                self._refused.append(f"bh-02 refused to let this input {kind} {path}: {refused}")
        if (refused := self._answered[(kind, path)]) is not None:
            raise PermissionError(
                errno.EACCES, f"bh-02 refused to let this input {kind} this file: {refused}", path
            )

    def serve(self) -> None:
        while (message := self._channel.inbox.get()) is not None:
            if message.get("op") == "exec":
                asked = message.get("ask")
                self._asking = (
                    frozenset(str(kind) for kind in asked) if isinstance(asked, list) else frozenset()
                )
                self._offer(message.get("tools"))
                self._channel.send(self._run(str(message.get("code", ""))))

    def _offer(self, specs: object) -> None:
        """Rebuild the namespace's `tools` from the specs the host sent with the input (none: no
        `tools` at all, so the namespace holds only what inputs put there), unless an input bound
        `tools` to something of its own, which is left as it is."""
        if not isinstance(self._namespace.get(_TOOLS, _Offered({})), _Offered):
            return
        given = specs if isinstance(specs, list) else []
        if not given:
            self._namespace.pop(_TOOLS, None)
            return
        self._namespace[_TOOLS] = _Offered(
            {
                str(spec["name"]): _function(spec, self._channel.ask)
                for spec in given
                if isinstance(spec, Mapping)
                and isinstance(spec.get("name"), str)
                and spec["name"].isidentifier()
            }
        )

    def _run(self, code: str) -> dict[str, Any]:
        out = io.StringIO()
        error: str | None = None
        self._inputs += 1
        name = f"{_INPUT} {self._inputs}>"
        # The input's source where a traceback looks for it (no modification time, so it is never
        # dropped as stale), kept for later inputs: a function defined here and failing there
        # shows its own line, and which input it came from.
        linecache.cache[name] = (len(code), None, code.splitlines(keepends=True), name)
        self._touched, self._answered, self._refused = {}, {}, []
        self.running = True
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                shown = self._own(*split_last_expression(code, name), name)
                if shown is not None:
                    print(shown)
        except KeyboardInterrupt:
            error = "KeyboardInterrupt: the input was interrupted; the REPL holds what it held"
        except SyntaxError as exc:
            error = f"SyntaxError: {exc}"
        except NameError as exc:
            error = input_traceback(exc)
            if exc.name is not None and exc.name not in self._had:
                error += (
                    f"\n({exc.name!r} has not been defined in this REPL, which has run "
                    f"{self._inputs} input{'s' if self._inputs != 1 else ''} since it started. If an "
                    "earlier input defined it before then (in an earlier session, or before /clear "
                    "or a restart), define it again.)"
                )
        except BaseException as exc:
            error = input_traceback(exc)
        finally:
            self.running = False
            self._had.update(self._namespace)
        output = self._capped(out.getvalue(), "")
        return {
            "op": "done",
            "output": output,
            "error": error and self._capped(error, "-error"),
            "touched": list(self._touched),
            "refused": list(self._refused),
        }

    def _own(self, body: ast.Module, last: ast.Expression | None, name: str) -> str | None:
        """Run the input's own code: its statements, then its last expression, whose repr is
        returned when it is not None. Only while this runs is what the input opens heard."""
        self._hearing = True
        try:
            exec(compile(body, name, "exec"), self._namespace)
            value = None if last is None else eval(compile(last, name, "eval"), self._namespace)
            return None if value is None else repr(value)
        finally:
            self._hearing = False

    def _capped(self, text: str, kind: str) -> str:
        """At most `_MAX_OUTPUT` characters of `text`: the host reads one line per message, so
        neither what an input printed nor its traceback may be unbounded. A longer one keeps its
        start and its end (where a test run's summary and a traceback's error are), says how
        much was cut, and is saved whole to a file the next input can read."""
        if len(text) <= _MAX_OUTPUT:
            return text
        try:
            self._saved = self._saved or tempfile.mkdtemp(prefix="bh-02-inputs-")
            path = os.path.join(self._saved, f"input-{self._inputs}{kind}.txt")
            with open(path, "w", encoding="utf-8") as whole:
                whole.write(text)
            where = f"; all of it is in {path}"
        except OSError:
            where = ""
        cut = len(text) - _MAX_OUTPUT
        return f"{text[:_HEAD]}\n... [{cut} characters cut here{where}] ...\n{text[-(_MAX_OUTPUT - _HEAD) :]}"


def _hook(heard: Callable[[tuple[Any, ...]], None]) -> Callable[[str, tuple[Any, ...]], None]:
    """The audit hook (`sys.addaudithook`): `heard(args)` for each `open` event, and for any
    other event nothing but the comparison. Every audited operation calls it, `id()` among them
    (a `copy.deepcopy` calls it once per object), so it is a plain function, not the bound
    `heard`: CPython looks up a hook's `__cantrace__` before each call, and on a bound method that
    lookup raises and clears an AttributeError, which made each call cost three times as much."""

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event == "open":
            heard(args)

    return hook


def _kinds(mode: str) -> tuple[str, ...]:
    """What opening a file in `mode` (an `open()` mode string) does to it: reads it (`r`, or `+`),
    writes it (`w`, `a`, `x`, or `+`), or both."""
    reads = "r" in mode or "+" in mode
    writes = any(letter in mode for letter in "wax+")
    return (*((_READ,) if reads else ()), *((_WRITE,) if writes else ()))


def _importing(bootstrap: dict[str, Any], external: dict[str, Any]) -> bool:
    """Whether the import system is what is opening a file now: a frame of its own is on the
    stack, one whose globals are `bootstrap` or `external` (the frozen importlib modules').

    Told by identity, which raises no audit event (`f_globals` and `f_back` raise none; reading
    a frame's `f_code` raises one, so a check by file name called the hook once per frame) and
    runs none of the input's code (a dict an input `exec`s in may override `get`). Not by their
    `__name__`, which `import importlib` changes to `importlib._bootstrap` and
    `importlib._bootstrap_external`. `_getframe` raises one event, so an open is at most two
    calls of the hook, at any depth. The walk starts at the caller, `heard`, which is always
    there: an `open` called from C with no Python frame (`_thread.start_new_thread(open, ...)`)
    has nothing above the hook's own frames, and is not the import system's."""
    frame: FrameType | None = _getframe(1)
    while frame is not None:
        if frame.f_globals is bootstrap or frame.f_globals is external:
            return True
        frame = frame.f_back
    return False


def main(argv: Sequence[str]) -> None:
    """Listen on the socket at `argv[0]`, wait for the host to say hello (for `argv[1]`
    seconds at most, `_HELLO_S` by default, and only while the parent lives), then serve inputs."""
    root = os.getcwd()  # the project's (a jail starts the worker there), taken before an input can move
    parent = os.getppid()
    deadline = time.monotonic() + (float(argv[1]) if len(argv) > 1 else _HELLO_S)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(argv[0])
    server.listen(1)
    server.settimeout(_LOOK_S)
    while True:
        try:
            conn, _ = server.accept()
        except TimeoutError:
            if os.getppid() == parent and time.monotonic() <= deadline:
                continue
            # the host that started this worker is gone (init adopted the worker), or never came
            os._exit(0)
        conn.settimeout(None)
        file = conn.makefile("r", encoding="utf-8")
        if file.readline().strip():
            break
        conn.close()  # a readiness probe: connected, said nothing, left
    kernel = _Kernel(_Channel(conn, file), root)
    addaudithook(_hook(kernel.heard))

    def interrupt(signum: int, frame: object) -> None:
        if kernel.running:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupt)
    kernel.serve()


if __name__ == "__main__":
    from sys import argv

    main(argv[1:])

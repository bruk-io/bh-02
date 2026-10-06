"""The kernel's own process: one persistent Python namespace behind a Unix socket.

Run by path (``python -I worker.py SOCKET``), usually inside a jail. It imports the standard
library and nothing else, so nothing of the host crosses into the jail with it. The namespace
holds only what inputs put there: an input is plain Python, and the jail decides what it may touch.

Wire: newline-delimited JSON. The host sends ``{"op": "hello"}`` once (a readiness probe
connects and closes without a word, so the worker keeps accepting until one speaks), then
``{"op": "exec", "code"}`` per input, and the worker ends every input with
``{"op": "done", "output", "error"}``. A worker nobody says hello to (its host was killed while
starting it) exits once its parent is gone, or after `_HELLO_S` (a second argument overrides
it), rather than wait in `accept` for ever; one whose host disconnects exits too, even mid-input.

Inputs run on the main thread, because only the main thread receives signals: SIGINT raises
`KeyboardInterrupt` in the running input and leaves the namespace as it was. With no input
running, SIGINT is ignored.
"""

import ast
import contextlib
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
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["input_traceback", "main", "split_last_expression"]

_MAX_OUTPUT = 20_000
_HEAD = 6_000  # of an output cut to `_MAX_OUTPUT`, how much is its start; the rest is its end
_INPUT = "<input"  # how every input's file name starts: the third input is `<input 3>`
_HELLO_S = 60.0  # the host says hello within milliseconds of the worker listening
_LOOK_S = 0.5  # how often a worker waiting for its hello checks that its parent is still there


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
    none is an input's."""
    tb = exc.__traceback__
    while tb is not None and not tb.tb_frame.f_code.co_filename.startswith(_INPUT):
        tb = tb.tb_next
    return "".join(traceback.format_exception(type(exc), exc, tb or exc.__traceback__)).rstrip()


class _Channel:
    """The socket: a reader thread feeding a queue. Only the main thread's input loop writes."""

    def __init__(self, conn: socket.socket, file: io.TextIOWrapper) -> None:
        self._conn = conn
        self._file = file  # the one reader of this connection: a second would lose what the first buffered
        self.inbox: queue.Queue[dict[str, Any] | None] = queue.Queue()
        threading.Thread(target=self._read, name="kernel-reader", daemon=True).start()

    def _read(self) -> None:
        for line in self._file:
            if line.strip():
                self.inbox.put(json.loads(line))
        # The host is gone. An input may be spinning on the main thread and never look at the
        # inbox again, so the worker ends here rather than outliving the program that ran it.
        os._exit(0)

    def send(self, message: Mapping[str, Any]) -> None:
        self._conn.sendall((json.dumps(message) + "\n").encode("utf-8"))


class _Kernel:
    """The namespace and the input loop."""

    def __init__(self, channel: _Channel) -> None:
        self._channel = channel
        self._namespace: dict[str, Any] = {"__name__": "__kernel__"}
        self.running = False
        self._inputs = 0
        self._had: set[str] = set()  # every name the namespace has held since the worker started
        self._saved: str | None = None  # where a cut output is kept whole: made at the first cut

    def serve(self) -> None:
        while (message := self._channel.inbox.get()) is not None:
            if message.get("op") == "exec":
                self._channel.send(self._run(str(message.get("code", ""))))

    def _run(self, code: str) -> dict[str, Any]:
        out = io.StringIO()
        error: str | None = None
        self._inputs += 1
        name = f"{_INPUT} {self._inputs}>"
        # The input's source where a traceback looks for it (no modification time, so it is never
        # dropped as stale), kept for later inputs: a function defined here and failing there
        # shows its own line, and which input it came from.
        linecache.cache[name] = (len(code), None, code.splitlines(keepends=True), name)
        self.running = True
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                body, last = split_last_expression(code, name)
                exec(compile(body, name, "exec"), self._namespace)
                if last is not None:
                    value = eval(compile(last, name, "eval"), self._namespace)
                    if value is not None:
                        print(repr(value))
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
        return {"op": "done", "output": output, "error": error and self._capped(error, "-error")}

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


def main(argv: Sequence[str]) -> None:
    """Listen on the socket at `argv[0]`, wait for the host to say hello (for `argv[1]`
    seconds at most, `_HELLO_S` by default, and only while the parent lives), then serve inputs."""
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
    kernel = _Kernel(_Channel(conn, file))

    def interrupt(signum: int, frame: object) -> None:
        if kernel.running:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupt)
    kernel.serve()


if __name__ == "__main__":
    from sys import argv

    main(argv[1:])

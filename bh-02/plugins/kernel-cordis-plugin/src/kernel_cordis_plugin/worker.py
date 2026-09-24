"""The kernel's own process: one persistent Python namespace behind a Unix socket.

Run by path (``python -I worker.py SOCKET``), usually inside a jail. It imports the standard
library and nothing else, so nothing of the host crosses into the jail with it. The namespace
holds only what cells put there: a cell is plain Python, and the jail decides what it may touch.

Wire: newline-delimited JSON. The host sends ``{"op": "hello"}`` once (a readiness probe
connects and closes without a word, so the worker keeps accepting until one speaks), then
``{"op": "exec", "code"}`` per cell, and the worker ends every cell with
``{"op": "done", "output", "error"}``. A worker nobody says hello to (its host was killed while
starting it) exits once its parent is gone, or after `_HELLO_S` (a second argument overrides
it), rather than wait in `accept` for ever; one whose host disconnects exits too, even mid-cell.

Cells run on the main thread, because only the main thread receives signals: SIGINT raises
`KeyboardInterrupt` in the running cell and leaves the namespace as it was. With no cell
running, SIGINT is ignored.
"""

import ast
import contextlib
import io
import json
import os
import queue
import signal
import socket
import threading
import time
import traceback
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["cell_traceback", "main", "split_last_expression"]

_MAX_OUTPUT = 20_000
_HELLO_S = 60.0  # the host says hello within milliseconds of the worker listening
_LOOK_S = 0.5  # how often a worker waiting for its hello checks that its parent is still there


def split_last_expression(code: str) -> tuple[ast.Module, ast.Expression | None]:
    """The cell's statements, and its last line when that is an expression (shown, notebook style)."""
    tree = ast.parse(code, "<cell>", "exec")
    last = tree.body[-1] if tree.body else None
    if isinstance(last, ast.Expr):
        tree.body.pop()
        return tree, ast.Expression(last.value)
    return tree, None


def cell_traceback(exc: BaseException) -> str:
    """Format a failed cell's exception from its first `<cell>` frame on: the worker's own
    frames (the `exec` that ran the cell) say nothing about the cell. Keep every frame if none
    is the cell's."""
    tb = exc.__traceback__
    while tb is not None and tb.tb_frame.f_code.co_filename != "<cell>":
        tb = tb.tb_next
    return "".join(traceback.format_exception(type(exc), exc, tb or exc.__traceback__)).rstrip()


class _Channel:
    """The socket: a reader thread feeding a queue. Only the main thread's cell loop writes."""

    def __init__(self, conn: socket.socket, file: io.TextIOWrapper) -> None:
        self._conn = conn
        self._file = file  # the one reader of this connection: a second would lose what the first buffered
        self.inbox: queue.Queue[dict[str, Any] | None] = queue.Queue()
        threading.Thread(target=self._read, name="kernel-reader", daemon=True).start()

    def _read(self) -> None:
        for line in self._file:
            if line.strip():
                self.inbox.put(json.loads(line))
        # The host is gone. A cell may be spinning on the main thread and never look at the
        # inbox again, so the worker ends here rather than outliving the program that ran it.
        os._exit(0)

    def send(self, message: Mapping[str, Any]) -> None:
        self._conn.sendall((json.dumps(message) + "\n").encode("utf-8"))


class _Kernel:
    """The namespace and the cell loop."""

    def __init__(self, channel: _Channel) -> None:
        self._channel = channel
        self._namespace: dict[str, Any] = {"__name__": "__kernel__"}
        self.running = False

    def serve(self) -> None:
        while (message := self._channel.inbox.get()) is not None:
            if message.get("op") == "exec":
                self._channel.send(self._cell(str(message.get("code", ""))))

    def _cell(self, code: str) -> dict[str, Any]:
        out = io.StringIO()
        error: str | None = None
        self.running = True
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                body, last = split_last_expression(code)
                exec(compile(body, "<cell>", "exec"), self._namespace)
                if last is not None:
                    value = eval(compile(last, "<cell>", "eval"), self._namespace)
                    if value is not None:
                        print(repr(value))
        except KeyboardInterrupt:
            error = "KeyboardInterrupt: the cell was interrupted; the namespace is as it was left"
        except SyntaxError as exc:
            error = f"SyntaxError: {exc}"
        except BaseException as exc:
            error = cell_traceback(exc)
        finally:
            self.running = False
        return {"op": "done", "output": _capped(out.getvalue()), "error": error and _capped(error)}


def _capped(text: str) -> str:
    """At most `_MAX_OUTPUT` characters of `text`, and how many more there were: the host reads
    one line per message, so neither what a cell printed nor its traceback may be unbounded."""
    if len(text) <= _MAX_OUTPUT:
        return text
    return text[:_MAX_OUTPUT] + f"\n... [{len(text) - _MAX_OUTPUT} more chars]"


def main(argv: Sequence[str]) -> None:
    """Listen on the socket at `argv[0]`, wait for the host to say hello (for `argv[1]`
    seconds at most, `_HELLO_S` by default, and only while the parent lives), then serve cells."""
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

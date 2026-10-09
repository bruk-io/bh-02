"""The `access` value: the functions asked before a file is read or written, a broker (paper 6.2).

A row with something to say about a file before it is opened `acquire`s
`access.before_read(fn)` or `access.before_write(fn)`; each `fn(path) -> str | None` answers
None to let it go ahead, or the text that refuses it. A tool asks (`refusal(kind, path)`) before
it opens a file for a call: the python tool from its Python process, before an input's own code
opens a file in the project. The model reads nothing while a call runs, so a question asked
there only matters because it can stop the open: what a refusal says reaches the model with the
call's result.

What it hears is what the tools report, no more: the python tool hears Python's own `open()`,
not a program an input runs (`sed -i`, `git apply`), nor `os.open`, a rename or a delete, and a
tool whose author asks nothing is never stopped. So it is a way to say something before a file
is touched, not a wall: the jail is the wall.
"""

from collections.abc import Callable

from cordis_helpers import Hooks

__all__ = ["READ", "WRITE", "Access"]

type Guard = Callable[[str], str | None]

READ = "read"
WRITE = "write"


class Access:
    """Implements `access` (CONTRACTS.md: access)."""

    def __init__(self) -> None:
        self._guards: dict[str, Hooks[Guard]] = {READ: Hooks(), WRITE: Hooks()}

    def before_read(self, fn: Guard) -> Callable[[], None]:
        """Ask `fn(path)` before a file is read; returns its remover."""
        return self._guards[READ].add(fn)

    def before_write(self, fn: Guard) -> Callable[[], None]:
        """Ask `fn(path)` before a file is written; returns its remover."""
        return self._guards[WRITE].add(fn)

    def asking(self) -> tuple[str, ...]:
        """The kinds some function is asked about (`read`, `write`): a tool need not ask about
        the others, which nothing would refuse."""
        return tuple(kind for kind, guards in self._guards.items() if any(True for _ in guards))

    def refusal(self, kind: str, path: str) -> str | None:
        """Why `path` may not be opened to `kind` (`read` or `write`): every refusal the
        functions asked give, sorted, so the order rows added them in means nothing; None when
        all let it go ahead. A function that raises refuses, saying so: a check that could not
        be made is not a yes. Called off the event loop: a function may read files."""
        if kind not in self._guards:
            raise ValueError(f"a file is opened to {READ!r} or {WRITE!r}, not {kind!r}")
        said: list[str] = []
        for fn in self._guards[kind]:
            try:
                answer = fn(path)
                if answer is not None and not isinstance(answer, str):
                    raise TypeError(f"it answered with a {type(answer).__name__}, not text or None")
            except Exception as error:  # one row's check failing must not let the open through unasked
                named = getattr(fn, "__qualname__", type(fn).__qualname__)
                answer = (
                    f"bh-02 could not check it ({getattr(fn, '__module__', '?')}:{named} failed: {error}); "
                    "tell the person"
                )
            if answer and answer.strip():
                said.append(answer.strip())
        return "\n\n".join(sorted(said)) if said else None

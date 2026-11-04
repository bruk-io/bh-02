"""The grants broker (decision-0012 items 2 and 7): the one value that holds what the person granted,
asks for what a row needs, and answers `BrigJail` at each start what to apply. A plain value: the
row that binds it is `runner:grants` (`wiring.grants`), and nothing here imports cordis.

What it holds, and for how long:
- the project's always-grants, in the store (`store`), read fresh at each `granted()` so an
  `always` or a revoke from another process counts at the next start;
- the session's answers (`once` and `no`), in memory: a `once` is applied while it is pinned (an
  `ask` answered once) or some row holds a `need` for it, and the answer is remembered after the
  row leaves, so a remounted row is not asked again; a `no` is remembered and not asked again.

It asks through the prompt `serve` was given, one question at a time, and a grant asked for twice
at once is one question. With no prompt served, nothing is asked: `ask` answers `no`, and a held
need waits for one. Whether a request is already inside the current policy is not decided here:
`standing` means the grant is already granted.
"""

import asyncio
import hashlib
from collections import deque
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from runner_cordis_plugin import store
from runner_cordis_plugin.grants import (
    NO_GRANTS,
    Answer,
    Asker,
    Grant,
    Grants,
    Kind,
    Request,
    Source,
    need_request,
)

__all__ = ["Broker", "Entry", "Outcome", "Prompt", "Scope", "Unknown"]

#: What serves a question: the person's answer to `request`, or None when they withdrew it (Ctrl-C).
type Prompt = Callable[[Request], Awaitable[Answer | None]]


class Outcome(StrEnum):
    """What `Broker.ask` answers: the person's answer, or `STANDING` when the grant was already
    granted (nobody was asked)."""

    ONCE = "once"
    ALWAYS = "always"
    NO = "no"
    STANDING = "standing"


class Scope(StrEnum):
    """How long a listed grant lasts: this `SESSION` or this `PROJECT` (the store)."""

    SESSION = "session"
    PROJECT = "project"


class Unknown(LookupError):
    """`revoke` named an id no grant has; the message lists the ids there are."""


@dataclass(frozen=True, slots=True)
class Entry:
    """One line of `list()`: the grant's short stable `id`, who asked and why (`request`), the
    `answer` (`once`, `always` or `no`) and its `scope`."""

    id: str
    request: Request
    answer: Answer
    scope: Scope

    def __str__(self) -> str:
        grant = self.request.grant
        target = f"{grant.target}:{grant.port}" if grant.port else grant.target
        asked = f"{self.request.asker}: {self.request.reason}"
        return f"{self.id}  {grant.kind} {target}  {self.answer} ({self.scope})  {asked}"


def _identifier(grant: Grant) -> str:
    """The first 8 hex digits of the SHA-256 of the grant's text: the same in every process, so
    `/grants` and `bh-02 grants` agree."""
    return hashlib.sha256(str(grant).encode()).hexdigest()[:8]


def _with(directory: Path, request: Request) -> None:
    """Add `request` to the store in `directory`, read fresh first.

    Raises:
        store.Refused: the store can't be read or written.
    """
    store.write(directory, [*store.read(directory), request])


def _without(directory: Path, grant: Grant) -> None:
    """Remove `grant` from the store in `directory`, read fresh first.

    Raises:
        store.Refused: the store can't be read or written.
    """
    store.write(directory, [request for request in store.read(directory) if request.grant != grant])


def _distinct(requests: Iterable[Request]) -> tuple[Request, ...]:
    """`requests`, the first for each grant."""
    seen: dict[Grant, Request] = {}
    for request in requests:
        seen.setdefault(request.grant, request)
    return tuple(seen.values())


class Broker:
    """The grants a session holds. `directory` is the project's grants store (`host.grants`), or
    None for a broker with no store: it then keeps only the session's."""

    def __init__(self, directory: Path | None) -> None:
        self._directory = directory
        self._problem = ""
        self._answers: dict[Grant, tuple[Request, Answer]] = {}  # the session's once and no
        self._pinned: set[Grant] = set()  # answered once through `ask`: applied whoever holds a need
        self._needs: dict[int, Request] = {}
        self._next = 0
        self._prompt: Prompt | None = None
        self._one = asyncio.Lock()  # one question at a time
        self._asking: dict[Grant, asyncio.Task[Outcome]] = {}
        self._background: set[asyncio.Task[None]] = set()
        self._listeners: dict[int, Callable[[], None]] = {}
        self._told: deque[str] = deque(maxlen=64)
        self._generation = 0
        self._applied: frozenset[Grant] = frozenset()  # the session's path and variable grants, as last seen

    def need(self, request: Request) -> Callable[[], None]:
        """Hold `request` as a standing need, for `acquire`: asked once, as soon as a prompt is
        served (now, when one is), and applied while held. The release withdraws only this hold."""
        key = self._next
        self._next += 1
        self._needs[key] = request
        self._changed()
        self._settle()

        def release() -> None:
            if self._needs.pop(key, None) is not None:
                self._changed()

        return release

    def needing(self, spec: Mapping[str, object], source: str, name: str) -> Callable[[], None]:
        """`need` of the request a layer's `spec` writes (`{kind, target, port?, reason}`), asked as
        `source` (`row` or `agent`) `name`: for a row that cannot import `Request`, since no plugin
        imports another.

        Raises:
            Invalid: `spec` is not a need (the message says what to write instead).
            ValueError: `source` is not a kind of asker.
        """
        return self.need(need_request(spec, Asker(Source(source), name)))

    async def asking(self, spec: Mapping[str, object], source: str, name: str) -> Outcome:
        """`ask` of the request a requester's `spec` writes (`{kind, target, port?, reason}`) as
        `source` (`extension`) `name`: for a host that cannot import `Request`, since no plugin imports
        another.

        Raises:
            Invalid: `spec` is not a request (the message says what to write instead).
            ValueError: `source` is not a kind of asker.
        """
        return await self.ask(need_request(spec, Asker(Source(source), name)))

    async def ask(self, request: Request) -> Outcome:
        """The answer to `request`: `standing` when it is already granted, `no` when the session
        answered no, or when no prompt is served, or when the person withdrew the question
        (nothing is recorded then); else the prompt's answer. Two asks for one grant share one
        question. `always` goes to the store and stays; `once` holds for the session."""
        grant = request.grant
        if grant in {each.grant for each in await self._kept()}:
            return Outcome.STANDING
        if (recorded := self._answers.get(grant)) is not None:
            if recorded[1] is Answer.NO:
                return Outcome.NO
            self._pin(grant)
            return Outcome.STANDING
        if self._prompt is None:
            return Outcome.NO
        outcome = await asyncio.shield(self._question(request))
        if outcome is Outcome.ONCE:
            self._pin(grant)
        return outcome

    def generation(self) -> int:
        """A number that differs whenever what the next start applies of the program's read, write and
        environment grants may differ from what a program started before it was given: an answer that
        applies, a revoke, a need held or released, an always-grant kept or taken back. A destination
        never changes it, since a destination is applied to a running program. A program records it as
        it starts and compares it before it takes an input: a different number is the cue to start
        again first (a path or variable is fixed when the jail is created)."""
        return self._generation

    async def ready(self) -> None:
        """Return once every need a row holds has an answer (the person's, or one the session or the
        project already had), so a program started next starts with it: a standing need costs no
        restart, since it is answered before the process exists. At once when no prompt is served (a
        need waits for one, and a program started meanwhile restarts when it is answered); a question
        withdrawn (Ctrl-C, the prompt released) counts as answered, with no answer recorded."""
        if self._prompt is not None:
            await self._ask_held()

    async def granted(self) -> Grants:
        """What the next start applies: the store, read now, then the session's once-answers that
        are pinned or held by a need. A store that can't be used grants nothing (`problem()`)."""
        kept = [each.grant for each in await self._kept()]
        held = {need.grant for need in self._needs.values()}
        session = [
            grant
            for grant, (_, answer) in self._answers.items()
            if answer is Answer.ONCE and (grant in self._pinned or grant in held)
        ]
        return Grants((*kept, *session)) if kept or session else NO_GRANTS

    def problem(self) -> str:
        """Why the store grants nothing, as the last `granted()`, `ask`, `list` or `revoke` read it
        (words that say what to fix), or ''."""
        return self._problem

    def on_change(self, fn: Callable[[], None]) -> Callable[[], None]:
        """Call `fn()` whenever what is granted may have changed (an answer, a need held or
        released, a revoke). The release stops it."""
        key = self._next
        self._next += 1
        self._listeners[key] = fn

        def release() -> None:
            self._listeners.pop(key, None)

        return release

    def tell(self, text: str) -> None:
        """Queue a line for the model that nobody was asked about (a refusal there is nothing to
        grant for); `told` takes it. At most the last 64 are kept."""
        self._told.append(text)

    def told(self) -> tuple[str, ...]:
        """The lines queued by `tell` since the last call, oldest first; taking them empties it."""
        lines = tuple(self._told)
        self._told.clear()
        return lines

    def serve(self, prompt: Prompt) -> Callable[[], None]:
        """Put `prompt` in front of the person, and ask what rows already need. One prompt at a
        time. The release withdraws it: a question under way is dropped, and its asker answers no.

        Raises:
            RuntimeError: a prompt is already served; release it first (a layer has two rows that
                serve one).
        """
        if self._prompt is not None:
            raise RuntimeError(
                "a grants prompt is already served; a second row can't serve another. Disable the "
                "row that serves it (`runner:grant_prompt`) or drop this one"
            )
        self._prompt = prompt
        self._settle()

        def release() -> None:
            if self._prompt is prompt:
                self._prompt = None
                for task in list(self._asking.values()):
                    task.cancel()

        return release

    async def list(self) -> tuple[Entry, ...]:
        """Every grant the session knows, the project's first: id, request, answer, scope."""
        project = [Entry(_identifier(r.grant), r, Answer.ALWAYS, Scope.PROJECT) for r in await self._kept()]
        session = [
            Entry(_identifier(grant), request, answer, Scope.SESSION)
            for grant, (request, answer) in self._answers.items()
        ]
        return (*project, *session)

    async def revoke(self, id: str) -> Entry:
        """Take back the grant `id` names (`list()`): a session grant leaves the session, an
        always-grant is removed from the store. Returns what was revoked. A session answer that a
        row's need still holds is asked again once a prompt is served, so the row is not left
        silently without it.

        Raises:
            Unknown: no grant has that id (the message lists the ids there are).
            store.Refused: the store can't be used, so nothing can be removed from it.
        """
        entries = await self.list()
        found = [entry for entry in entries if entry.id == id]
        if not found:
            there = ", ".join(entry.id for entry in entries) or "none"
            unread = f"; the store can't be read: {self._problem}" if self._problem else ""
            raise Unknown(
                f"no grant has id {id!r}; the ids there are: {there} (`/grants` lists them){unread}"
            )
        stored: list[Grant] = []
        for entry in found:
            grant = entry.request.grant
            if entry.scope is Scope.SESSION:
                self._answers.pop(grant, None)
                self._pinned.discard(grant)
            else:
                await self._remove(grant)
                stored.append(grant)
        self._changed(*stored)
        held = {need.grant for need in self._needs.values()}
        if any(entry.scope is Scope.SESSION and entry.request.grant in held for entry in found):
            self._settle()  # a row still holds what the person took back: it is asked again
        return found[0]

    async def _kept(self) -> tuple[Request, ...]:
        """The store's requests, read now off the event loop; none, with `problem()` set, when it
        is refused."""
        if self._directory is None:
            return ()
        try:
            kept = await asyncio.to_thread(store.read, self._directory)
        except store.Refused as error:
            self._problem = str(error)
            return ()
        self._problem = ""
        return kept

    async def _remove(self, grant: Grant) -> None:
        """Take `grant` out of the store, read fresh and written whole (a lost update from another
        process is possible and accepted: the next write reads again)."""
        assert self._directory is not None  # a project entry came from the store
        await asyncio.to_thread(_without, self._directory, grant)

    async def _keep(self, request: Request) -> bool:
        """Add `request` to the store, read fresh first so another process's writes are kept.
        False, with `problem()` set, when the store is refused: it is never written over."""
        if self._directory is None:
            return False
        try:
            await asyncio.to_thread(_with, self._directory, request)
        except store.Refused as error:
            self._problem = str(error)
            return False
        self._problem = ""
        return True

    def _pin(self, grant: Grant) -> None:
        if grant not in self._pinned:
            self._pinned.add(grant)
            self._changed()

    def _question(self, request: Request) -> asyncio.Task[Outcome]:
        """The one question for `request.grant`, started if none is under way."""
        grant = request.grant
        if (task := self._asking.get(grant)) is None:
            task = asyncio.get_running_loop().create_task(self._asked(request))
            self._asking[grant] = task
            task.add_done_callback(lambda _: self._asking.pop(grant, None))
        return task

    async def _asked(self, request: Request) -> Outcome:
        """Put `request` to the prompt, once nothing else is being asked; record the answer."""
        async with self._one:
            grant = request.grant
            if grant in {each.grant for each in await self._kept()}:
                return Outcome.STANDING
            if (recorded := self._answers.get(grant)) is not None:
                return Outcome.NO if recorded[1] is Answer.NO else Outcome.STANDING
            prompt = self._prompt
            if prompt is None:
                return Outcome.NO
            try:
                answer = await prompt(request)
            except asyncio.CancelledError:
                if self._prompt is None:  # the prompt was released: the question is withdrawn
                    return Outcome.NO
                raise
            if answer is None:
                return Outcome.NO
            if answer is Answer.ALWAYS and not await self._keep(request):
                answer = Answer.ONCE  # the store can't hold it: this session still has it
            if answer is not Answer.ALWAYS:
                self._answers[grant] = (request, answer)
            self._changed(*([grant] if answer is Answer.ALWAYS else []))
            return Outcome(answer.value)

    def _settle(self) -> None:
        """Ask what is held and not yet answered, in the background, when a prompt is served."""
        if self._prompt is None or not self._needs:
            return
        task = asyncio.get_running_loop().create_task(self._ask_held())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _ask_held(self) -> None:
        for request in _distinct(self._needs.values()):
            if self._prompt is None:
                return
            if request.grant in {need.grant for need in self._needs.values()}:  # still held
                await asyncio.shield(self._question(request))  # a caller leaving leaves the question

    def _session(self) -> frozenset[Grant]:
        """The session's once-answers a start would apply that are not destinations: pinned or held."""
        held = {need.grant for need in self._needs.values()}
        return frozenset(
            grant
            for grant, (_, answer) in self._answers.items()
            if answer is Answer.ONCE
            and grant.kind is not Kind.NET
            and (grant in self._pinned or grant in held)
        )

    def _changed(self, *stored: Grant) -> None:
        """What is granted may have changed: `generation` moves when the session's applied path and
        variable grants differ from last time, or `stored` (the project's grants just kept or taken
        back) names one; then every listener is told."""
        applied = self._session()
        if applied != self._applied or any(grant.kind is not Kind.NET for grant in stored):
            self._applied = applied
            self._generation += 1
        for fn in list(self._listeners.values()):
            fn()

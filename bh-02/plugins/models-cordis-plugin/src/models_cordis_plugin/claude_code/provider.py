"""Claude Code, through the Claude Agent SDK, as a `model`: one model step per call.

bh-02's own `agent:loop` runs the loop (CONTRACTS.md: model): it classifies each step,
nudges, runs every call as a cell in the kernel (which asks the person when unjailed) and keeps the
transcript. Claude Code is the subscription's sanctioned way to the model, and nothing else: it
runs no built-in tool, loads no settings, CLAUDE.md or connector, and the tools it knows are only
declared to it (`declared.py`). Each call to `complete` streams exactly one model step:

- a new user line starts a query (`Send`);
- a step that asks for tools ends at its `message_stop` with the query left open: Claude Code
  then calls the declared tool, which parks until the loop's next request brings the results
  (`Deliver`), and the query carries on with the next step;
- an answered step (`end_turn` with text) is read to the query's result;
- any other end (the output limit, nothing said, a refusal, a call that did not decode) is
  interrupted at once, so that the loop's classification and nudges decide, not Claude Code's
  own recovery (which, left alone, continued a truncated step three times, measured);
- closing the step mid-stream (the person stopped the reply) interrupts Claude Code and reads
  it to its result, so nothing runs on; closing an answered or cut step on its last chunks, once
  it has settled, interrupts nothing (Claude Code is idle) and records it as stopped, as the loop
  does; closing a tool step there interrupts Claude Code, whose calls the loop will not answer,
  and the next request rebuilds;
- a step Claude Code could not stream (a stream that failed before a block completed, which it
  asks for again without streaming) comes as one whole `AssistantMessage` with no stream
  events, and is folded as the step; one that comes after text or a call of it was streamed
  can't be shown without saying that part twice, so it fails as a restarted stream does;
- a stream that stalls or drops before it is done, Claude Code may close where it is (the open
  block, then `message_stop` with no `message_delta`, so no stop reason) and stream again
  from the start (CLI 2.1.282: before any text or call began, and on a dropped connection
  before any block was complete): the close is not the step's end, and the stream that
  follows is the step; its thinking shown so far stays shown, but once text or a call was
  shown it fails as a restarted stream does (a call the close cut off, its arguments
  incomplete, was never shown: `Step` holds such a call until a stop reason says the step
  made it);
- a call Claude Code answers itself (one that is not declared, which the permission callback
  denies) lets it start the next model step on its own answer, before the loop's results reach
  it: that step is dropped unseen, and Claude Code is rebuilt from the loop's transcript and
  asked again, so every step the loop sees was built on what the loop sent;
- stopping the process interrupts it before answering its parked calls `closed`, so it can't
  start another model request on that answer.

One Claude Code process holds the conversation, started on the first step with the request's
system message as its system prompt and the offered tools; a changed system prompt or tool set
restarts it (resuming its own session) before the next user line, never while calls are parked.
What its session holds is checked against every request (`reconcile.py`); when the two differ,
the transcript is written as a new Claude Code session and that is resumed (`records.py`). The
session id and what it holds are saved in the row's `state` directory, so `bh-02 --resume`
continues Claude Code's own session when nothing changed.
"""

import asyncio
import contextlib
import json
import os
import shutil
import sysconfig
import tempfile
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Final, Protocol

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    Message,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from models_cordis_plugin.claude_code.credential import TOKEN_VARIABLE, child_env
from models_cordis_plugin.claude_code.declared import Parking, permission_for, server_for
from models_cordis_plugin.claude_code.reconcile import (
    CLEAN,
    CUT,
    FAILED,
    OPEN,
    RUNNING,
    STOPPED,
    STRAYED,
    Deliver,
    Held,
    Rebuild,
    Send,
    digest,
    reconcile,
)
from models_cordis_plugin.claude_code.records import session_file, write_session
from models_cordis_plugin.claude_code.stream import SERVER, Step, visible
from models_cordis_plugin.local_env import ENV_FILE, token_file

__all__ = [
    "ClaudeCodeModel",
    "ClaudeCodeConfig",
    "ClaudeCodeError",
    "Session",
    "failure_of",
    "model_id",
]

type Json = Mapping[str, Any]

_DETACHED: Final = "claude-code-detached"  # this plugin's console script (detach.py)
_MAX_TURNS: Final = 100_000  # one query runs a whole reply's steps; the loop decides when it ends
_DRAIN_S: Final = 15.0  # how long an interrupted query gets to reach its result
_FINAL: Final = frozenset({"end_turn", "stop_sequence"})
_CLOSED: Final = "closed: bh-02 ended this conversation's Claude Code process before this call ran"
# What an alias resolves to, for a rebuilt session written before this process has seen the
# model answer (measured, CLI 2.1.280); the model's own answer replaces it once there is one.
_ALIASES: Final[Mapping[str, str]] = {
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-5-5",
    "haiku": "claude-haiku-4-5-20251001",
}
_MAKE_ONE: Final = f"Make a token with `claude setup-token`, put `{TOKEN_VARIABLE}=<the token>` in"
_ERRORS: Final[Mapping[str, str]] = {
    "authentication_failed": (
        f"Claude refused the credential ({TOKEN_VARIABLE} in {ENV_FILE}): it may have expired or "
        f"been revoked. Make a new one with `claude setup-token`, put it in {ENV_FILE}, and send the "
        "message again."
    ),
    "billing_error": (
        "Claude reported a billing problem with this account. Check the subscription at "
        "claude.ai (Settings, Billing), then send the message again."
    ),
    "rate_limit": "You've reached your Claude usage limit for now. Try again later, or /model another model.",
    "invalid_request": (
        "Claude rejected the request. Send the message again; if it is rejected again, /clear "
        "starts a fresh conversation."
    ),
    "server_error": "Claude had a server error. Try again in a moment.",
}


class ClaudeCodeError(Exception):
    """A failure the person at the keyboard should see: the `model` contract's recoverable error."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True, slots=True)
class ClaudeCodeConfig:
    """`model`: `sonnet` (the default), `opus`, `haiku` or a model id: anything the subscription
    reaches through Claude Code (`/model` and `--model` set it). `state`: the directory this
    conversation's Claude Code state lives in (its `CLAUDE_CONFIG_DIR`, the saved session, the
    CLI's stderr); a session's layer points it into the session's directory, and without one a
    temporary directory is used and removed. `env_file`: where the credential is (the
    workspace's `local.env`, found above the install, when unset). `cwd`: the project Claude Code
    is told it works in (bh-02's working directory when unset)."""

    model: str = "sonnet"
    state: str | None = None
    env_file: str | None = None
    cwd: str | None = None


class Session(Protocol):
    """What this provider needs of a Claude Code session: the SDK's `ClaudeSDKClient`."""

    async def connect(self) -> None: ...
    async def query(self, prompt: str | AsyncIterable[dict[str, Any]]) -> None: ...
    async def interrupt(self) -> None: ...
    def receive_messages(self) -> AsyncIterator[Message]: ...
    async def disconnect(self) -> None: ...


type Opener = Callable[[ClaudeAgentOptions], Session]


def model_id(name: str, seen: str | None = None) -> str:
    """The model id a rebuilt session's records name: the one the model last answered with, when
    this process has seen it answer, else what `name` resolves to."""
    return seen or _ALIASES.get(name, name)


def failure_of(error: str | None, detail: str) -> ClaudeCodeError:
    """The readable, recoverable error for a step Claude Code reported failed: its error kind
    (`AssistantMessage.error`), and what it said about it."""
    kind = error or "result_error"
    message = _ERRORS.get(kind, "Claude couldn't finish the step. Send the message again.")
    if kind == "authentication_failed":
        return ClaudeCodeError(kind, message)  # Claude Code's own advice (`/login`) is not bh-02's
    return ClaudeCodeError(kind, f"{message} ({detail})" if detail else message)


def _no_token(path: Path | None, *, exists: bool) -> str:
    """What to do when there is no credential: `path` is the file looked in (None when no
    `local.env` was found above the install), `exists` whether it is there. Never a value."""
    if path is None:
        return (
            f"No Claude credential: there is no {ENV_FILE} at the repository root. {_MAKE_ONE} "
            f"{ENV_FILE} there (git-ignored), then send the message again."
        )
    if not exists:
        return (
            f"No Claude credential: {path}, the file the row's env_file names, does not exist. "
            f"{_MAKE_ONE} that file, or point env_file at the file that has it, then send the "
            "message again."
        )
    return (
        f"No Claude credential: {TOKEN_VARIABLE} is not in {path}. {_MAKE_ONE} {path}, then "
        "send the message again."
    )


def _unnamed(cwd: str) -> str:
    """Why a conversation can't be handed to Claude Code from `cwd`, and what to do."""
    return (
        f"bh-02 can't hand this conversation to Claude Code: the working directory's path ({len(cwd)} "
        "characters) is too long for bh-02 to name Claude Code's session directory for it, so the "
        "model would lose everything said so far. Run bh-02 from a shorter path, or /clear "
        "to start a fresh conversation here."
    )


class _Astray(ClaudeCodeError):
    """Claude Code started a step on a call it answered itself (module docstring)."""

    def __init__(self) -> None:
        super().__init__(
            "strayed",
            "Claude Code answered a tool call itself and carried on without bh-02's results, twice "
            "in a row. Send the message again; if it happens again, /clear starts a fresh "
            "conversation.",
        )


def _text_of(message: AssistantMessage) -> str:
    return " ".join(b.text for b in message.content if isinstance(b, TextBlock)).strip()[:400]


def _whole(message: AssistantMessage) -> dict[str, Any] | None:
    """A message Claude Code handed over whole, as the Messages API returns one; None when it
    holds a block this provider can't write back as it came."""
    blocks: list[dict[str, Any]] = []
    for block in message.content:
        match block:
            case TextBlock(text=text):
                blocks.append({"type": "text", "text": text})
            case ThinkingBlock(thinking=thinking, signature=signature):
                blocks.append({"type": "thinking", "thinking": thinking, "signature": signature})
            case ToolUseBlock():
                blocks.append({"type": "tool_use", **asdict(block)})  # id, name, input
            case _:
                return None
    return {
        "id": message.message_id,
        "model": message.model,
        "content": blocks,
        "stop_reason": message.stop_reason,
        "usage": message.usage or {},
    }


def _detached_cli() -> str | None:
    """This plugin's `claude-code-detached` script, installed beside the interpreter."""
    script = Path(sysconfig.get_path("scripts")) / _DETACHED
    return str(script) if script.is_file() else None


def _appender(path: Path) -> Callable[[str], None]:
    """The CLI's stderr, as the SDK hands it over line by line, appended to `path` (bh-02's TUI
    owns the terminal). Opened per line, so nothing is held open past the process."""

    def append(line: str) -> None:
        with path.open("a", encoding="utf-8") as log:
            log.write(line if line.endswith("\n") else f"{line}\n")

    return append


async def _only(message: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    yield message


class ClaudeCodeModel:
    """The `model` value (the claude-code provider): one Claude Code process per conversation
    (module docstring).

    An async context manager: leaving it answers any parked call, interrupts what runs, and ends
    the process. `open` builds the session from its options (the SDK's client; a test's fake).
    """

    def __init__(self, config: ClaudeCodeConfig, open: Opener | None = None) -> None:
        self._config = config
        self._open: Opener = open or ClaudeSDKClient
        self._client: Session | None = None
        self._running: tuple[str, list[dict[str, Any]]] | None = (
            None  # the system prompt and tools it started with
        )
        self._parking = Parking()
        self._strayed = False
        self._held = Held()
        self._session: str | None = None  # Claude Code's session id
        self._seen: str | None = None  # the model id the model last answered with
        self._loaded = False
        self._temporary: str | None = None

    @property
    def parked(self) -> tuple[str, ...]:
        """The tool_use ids of the calls Claude Code is waiting on now."""
        return self._parking.waiting

    async def __aenter__(self) -> ClaudeCodeModel:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -- where its state lives -----------------------------------------------------------

    def _dir(self) -> Path:
        if self._config.state is not None:
            root = Path(self._config.state)
        else:
            self._temporary = self._temporary or tempfile.mkdtemp(prefix="bh-02-claude-code-")
            root = Path(self._temporary)
        (root / "config").mkdir(parents=True, exist_ok=True)
        return root

    def _cwd(self) -> str:
        return os.path.realpath(self._config.cwd or os.getcwd())

    def _load(self) -> None:
        """Read the saved session once: what Claude Code's session held when this conversation
        last ran (a `--resume`). One whose file is gone reads as failed: a rebuild."""
        if self._loaded:
            return
        self._loaded = True
        path = self._dir() / "state.json"
        try:
            saved = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except OSError, ValueError:
            saved = {}
        if not isinstance(saved, dict) or not isinstance(saved.get("held"), dict):
            return
        self._session = saved.get("session") if isinstance(saved.get("session"), str) else None
        if saved.get("alias") == self._config.model and isinstance(saved.get("model"), str):
            self._seen = saved["model"]
        held = Held.from_json(saved["held"])
        if self._session is None or session_file(self._dir() / "config", self._session) is None:
            held = replace(held, ended=FAILED)
        self._held = held

    def _save(self) -> None:
        state = {
            "session": self._session,
            "alias": self._config.model,
            "model": self._seen,
            "held": self._held.to_json(),
        }
        (self._dir() / "state.json").write_text(json.dumps(state) + "\n", encoding="utf-8")

    # -- the process ---------------------------------------------------------------------

    async def _start(self, system: str, specs: list[dict[str, Any]], resume: str | None) -> None:
        """Start Claude Code for this conversation: `resume` is the session to continue."""
        root = self._dir()
        path = token_file(self._config.env_file)
        env = child_env(path, str(root / "config"))
        if env is None:
            raise ClaudeCodeError(
                "authentication_failed", _no_token(path, exists=path is not None and path.is_file())
            )
        cli = _detached_cli()
        if cli is None:
            raise ClaudeCodeError(
                "connection", f"bh-02's `{_DETACHED}` script is not installed; run `uv sync --all-packages`"
            )
        self._parking = Parking()
        self._strayed = False
        options = ClaudeAgentOptions(
            model=self._config.model,
            system_prompt=system,
            tools=[],  # no built-in tool
            setting_sources=[],  # no settings file, no CLAUDE.md
            strict_mcp_config=True,  # only the server given here: the account's connectors stay out
            include_partial_messages=True,  # the raw stream events, which `Step` folds
            max_turns=_MAX_TURNS,
            mcp_servers={SERVER: server_for(specs, self._parking)},
            can_use_tool=permission_for(frozenset(str(spec["name"]) for spec in specs)),
            cli_path=cli,
            env=env,
            stderr=_appender(root / "stderr.log"),
            cwd=self._cwd(),
            resume=resume,
        )
        client = self._open(options)
        try:
            await client.connect()
        except ClaudeSDKError as error:
            problem = f"{type(error).__name__}: {error}"
        else:
            self._client = client
            self._running = (system, specs)
            return
        raise ClaudeCodeError(
            "connection", f"Couldn't start Claude Code ({problem}); its log is {root / 'stderr.log'}"
        ) from None

    async def _drain(self, *, interrupt: bool) -> bool:
        """Read the query to its result, interrupting it first if asked (and if a new step
        starts that nobody asked for). An interrupt lands before any parked call is answered
        `closed`, so Claude Code can't start another model request on the answer. False when
        it would not end: the process is ended."""
        client = self._client
        if client is None:
            return True
        try:
            async with asyncio.timeout(_DRAIN_S):
                if interrupt:
                    await client.interrupt()
                    self._parking.release(_CLOSED)
                async with _closing(client.receive_messages()) as incoming:
                    async for message in incoming:
                        self._note(message)
                        if isinstance(message, ResultMessage):
                            return True
                        if not interrupt and _starts_step(message):
                            self._strayed = interrupt = True  # Claude Code carried on by itself
                            await client.interrupt()
                            self._parking.release(_CLOSED)
        except TimeoutError, ClaudeSDKError:
            pass
        await self._end()
        return False

    async def _end(self) -> None:
        """End the process, answering whatever it waits on first."""
        self._parking.release(_CLOSED)
        client, self._client, self._running = self._client, None, None
        if client is not None:
            with contextlib.suppress(Exception):
                await client.disconnect()

    async def _stop(self) -> None:
        """Stop the process at the first point where nothing is lost: interrupt an open query,
        answer its parked calls, read it to its result, then end it."""
        if self._client is not None and self._held.ended in (OPEN, RUNNING):
            await self._drain(interrupt=True)
        await self._end()

    async def close(self) -> None:
        """Leave the conversation: a query left with calls open no longer matches the transcript
        (its calls were answered `closed`), so the saved state says to rebuild it."""
        await self._stop()  # while the held state still says a query is open, so it is interrupted
        if self._held.ended in (OPEN, RUNNING):
            self._held = replace(self._held, ended=FAILED)
        if self._loaded:
            with contextlib.suppress(OSError):
                self._save()
        if self._temporary is not None:
            shutil.rmtree(self._temporary, ignore_errors=True)
            self._temporary = None

    def _note(self, message: Message) -> None:
        """What a message says about the session: its id, and whether Claude Code answered a
        call itself (a result for a call that never reached the server: a denied one, or one
        it rejected before calling)."""
        match message:
            case SystemMessage(subtype="init", data=data) if isinstance(data.get("session_id"), str):
                self._session = data["session_id"]
            case ResultMessage(session_id=session) if session:
                self._session = session
            case UserMessage(content=list() as blocks):
                if any(
                    isinstance(b, ToolResultBlock) and b.tool_use_id not in self._parking.called
                    for b in blocks
                ):
                    self._strayed = True

    # -- one step --------------------------------------------------------------------------

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        """Stream one model step's chunks (CONTRACTS.md: chunk). Closing this generator (a reply
        the person stopped) interrupts Claude Code and waits for it to stop."""
        system = "\n\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
        rest = [m for m in messages if m.get("role") != "system"]
        specs = [dict(t) for t in tools]
        self._load()
        said: list[str] = []
        closed = True
        asked = False  # whether this call's step was asked for (a stop before that stops nothing)
        try:
            for again in (False, True):
                asked = False
                decision = reconcile(self._held, rest)
                if isinstance(decision, Rebuild):
                    await self._stop()
                    self._session = self._rebuilt(rest[: decision.prefix])
                    decision = Send(decision.send)
                if self._client is None or (
                    not isinstance(decision, Deliver) and (system, specs) != self._running
                ):
                    await self._stop()
                    await self._start(system, specs, self._resumable(rest))
                assert self._client is not None
                await self._ask(self._client, decision)
                self._held = Held(len(rest), digest(rest), ended=RUNNING)
                self._save()
                asked = True
                try:
                    async for chunk in self._step(said):
                        yield chunk
                    break
                except _Astray:
                    if again:
                        raise
                    # nothing was streamed; Claude Code is ended and the held state says to
                    # rebuild, which the second pass does
            closed = False
        except ClaudeCodeError:
            closed = False
            raise
        finally:
            closed = closed and asked
            if closed and self._held.ended == RUNNING:
                # stopped mid-step (the reply closed or its task cancelled): stop Claude Code too
                self._held = replace(self._held, said="".join(said), ended=STOPPED)
                if not await self._drain(interrupt=True):
                    self._held = replace(self._held, ended=FAILED)
                self._save()
            elif closed and self._held.ended in (CLEAN, CUT):
                # stopped on the settled step's last chunks: Claude Code is already idle, so
                # there is nothing to interrupt; the loop records the step as stopped
                self._held = replace(self._held, ended=STOPPED)
                self._save()
            elif closed and self._held.ended in (OPEN, STRAYED):
                # stopped on a tool step's last chunks: the loop records it as stopped and will
                # never answer its calls, so Claude Code is interrupted now rather than left
                # waiting on them until the next request, which rebuilds from the transcript
                await self._drain(interrupt=True)
                self._held = replace(self._held, ended=FAILED)
                self._save()

    def _rebuilt(self, prefix: Sequence[Json]) -> str | None:
        """Write `prefix` as a new Claude Code session; its id (None for an empty prefix)."""
        session = None
        if prefix:
            cwd = self._cwd()
            model = model_id(self._config.model, self._seen)
            session = write_session(self._dir() / "config", cwd, prefix, model)
            if session is None:
                raise ClaudeCodeError("path_too_long", _unnamed(cwd))
        self._held = Held(len(prefix), digest(prefix))
        return session

    def _resumable(self, rest: Sequence[Json]) -> str | None:
        """The session a new process continues: this conversation's, if Claude Code has it, else
        (a conversation it never saw) one written from the transcript."""
        if self._session is not None and session_file(self._dir() / "config", self._session) is not None:
            return self._session
        return self._rebuilt(rest[: self._held.count]) if self._held.count else None

    async def _ask(self, client: Session, decision: Send | Deliver) -> None:
        try:
            match decision:
                case Send(text=text):
                    await client.query(text)
                case Deliver(results=results, steer=steer):
                    if steer is not None:
                        # a line typed after a stop mid-call: read with the results, not after them
                        await client.query(_only(_user(steer) | {"priority": "next"}))
                    for call_id, result in results:
                        self._parking.deliver(call_id, result)
        except ClaudeSDKError as error:
            self._held = replace(self._held, ended=FAILED)
            await self._end()
            raise ClaudeCodeError(
                "connection", f"Lost Claude Code ({type(error).__name__}: {error})."
            ) from None

    async def _step(self, said: list[str]) -> AsyncIterator[Json]:
        """The step's chunks as its raw events arrive, then how it ended (module docstring)."""
        assert self._client is not None
        step = Step()
        failure: AssistantMessage | None = None
        started = astray = retried = shown = False
        try:
            async with _closing(self._client.receive_messages()) as incoming:
                async for message in incoming:
                    self._note(message)
                    if self._strayed and not started:
                        astray = True  # the step coming is built on Claude Code's own answer
                        break
                    match message:
                        case StreamEvent(event=event, parent_tool_use_id=None):
                            if started and event.get("type") == "message_start":
                                retried = True  # Claude Code restarted the stream mid-step
                                break
                            started = started or event.get("type") == "message_start"
                            for chunk in step.take(event):
                                if chunk["type"] == "text":
                                    said.append(chunk["text"])
                                shown = shown or chunk["type"] in ("text", "tool_call")
                                yield chunk
                            if step.ended and step.stop is None:
                                # no `message_delta`: Claude Code closed a stalled or dropped
                                # stream to stream it again (module docstring)
                                if shown:
                                    retried = True  # its text is shown already: not said twice
                                    break
                                step, started = Step(), False
                            elif step.ended:
                                break
                        case AssistantMessage(error=error) if error is not None:
                            failure = message
                        case AssistantMessage(parent_tool_use_id=None, stop_reason=str()) if (
                            message.message_id != step.id and (whole := _whole(message)) is not None
                        ):
                            # the step came whole, not streamed (module docstring); a message
                            # streamed block by block has the stream's id and no stop reason yet
                            if shown:
                                retried = True  # part of its text is shown already: not said twice
                                break
                            for chunk in step.whole(whole):
                                if chunk["type"] == "text":
                                    said.append(chunk["text"])
                                yield chunk
                            break
                        case ResultMessage(is_error=is_error, errors=errors, result=result):
                            # the query ended before the step did: Claude Code gave up on it
                            self._held = replace(self._held, ended=FAILED)
                            detail = (
                                _text_of(failure) if failure else "; ".join(errors or []) or (result or "")
                            )
                            if not is_error and failure is None:
                                detail = detail or "it ended the query without a step"
                            raise failure_of(failure.error if failure else None, detail)
        except ClaudeSDKError as error:
            self._held = replace(self._held, ended=FAILED)
            await self._end()
            raise ClaudeCodeError(
                "connection", f"Lost Claude Code mid-step ({type(error).__name__}: {error}). Send it again."
            ) from None
        if astray:
            await self._stop()  # interrupts the step it started, answers what is parked, ends it
            self._held = replace(self._held, ended=STRAYED)
            self._save()
            raise _Astray
        if retried:
            self._held = replace(self._held, ended=FAILED)
            await self._end()
            raise ClaudeCodeError(
                "stream_retried",
                "Claude Code restarted its reply mid-step, so bh-02 can't tell which half to keep. "
                "Send the message again.",
            )
        if not step.ended:
            self._held = replace(self._held, ended=FAILED)
            await self._end()
            raise ClaudeCodeError("connection", "Claude Code stopped mid-step. Send the message again.")
        ended = await self._settle(step)
        if step.model:
            self._seen = step.model
        calls = tuple(step.calls) if ended == OPEN else ()
        self._held = replace(self._held, emitted=step.message, said="".join(said), ended=ended, calls=calls)
        self._save()
        for chunk in step.finish():
            yield chunk

    async def _settle(self, step: Step) -> str:
        """How a finished step leaves the query: open on its calls, read to its result, or
        interrupted so the loop decides."""
        if step.stop == "tool_use" and step.calls and not step.undecodable:
            return STRAYED if self._strayed else OPEN
        if step.stop in _FINAL and visible(step.message):
            ended = CLEAN if await self._drain(interrupt=False) else FAILED
        else:
            ended = CUT if await self._drain(interrupt=True) else FAILED
        return STRAYED if self._strayed and ended != FAILED else ended


@contextlib.asynccontextmanager
async def _closing(messages: AsyncIterator[Message]) -> AsyncIterator[AsyncIterator[Message]]:
    """`messages`, closed on the way out: a step reads its own iterator over the session's one
    stream, which a cancelled read would otherwise leave finished for the next step."""
    try:
        yield messages
    finally:
        if isinstance(messages, AsyncGenerator):
            await messages.aclose()


def _starts_step(message: Message) -> bool:
    return isinstance(message, StreamEvent) and message.event.get("type") == "message_start"


def _user(text: str) -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": text}, "parent_tool_use_id": None}

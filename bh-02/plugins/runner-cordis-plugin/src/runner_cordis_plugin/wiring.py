"""The rows: a confined runner (brig) or an unconfined one, bound under `runner`; the rule for
what runs unasked, under `approval`; the grants broker, under `grants`, and `/grants`; and
`/release`."""

import asyncio
import os
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, acquire, bind, component
from runner_cordis_plugin import allowlist, requesting
from runner_cordis_plugin.approval import Approval, Graded
from runner_cordis_plugin.broker import Broker, Outcome, Prompt
from runner_cordis_plugin.commands import Listing, grants_command
from runner_cordis_plugin.grants import Answer, Grant, Request
from runner_cordis_plugin.jail import BrigJail, Granting, Host
from runner_cordis_plugin.policy import SOCKET_PLACES, BrigConfig
from runner_cordis_plugin.prompting import answer_of, decided, question
from runner_cordis_plugin.runner import ArgvFor, Runner, Started
from runner_cordis_plugin.unconfined import Unjailed

__all__ = [
    "GrantToolConfig",
    "approval",
    "confined",
    "grant_prompt",
    "grant_tool",
    "grants",
    "release",
    "unconfined",
]


@runtime_checkable
class _Releasing(Protocol):
    """What `/release` needs of the `runner` value (CONTRACTS.md: runner)."""

    async def release(self) -> str: ...


@runtime_checkable
class _Registrar(Protocol):
    """What a row that offers commands needs of the `commands` value (CONTRACTS.md: commands)."""

    def register(
        self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]
    ) -> Callable[[], None]: ...


@runtime_checkable
class _KeyReaders(Protocol):
    """What the confined runner needs of the `models` value (CONTRACTS.md: models): `key_envs()`,
    each variable an endpoint the model row can reach reads as its key, to those endpoints, read
    fresh."""

    def key_envs(self) -> Mapping[str, Sequence[str]]: ...


@runtime_checkable
class _Asking(Protocol):
    """What the grant tool needs of the `grants` value (CONTRACTS.md: grants): `ask`."""

    async def ask(self, request: Request) -> Outcome: ...


@runtime_checkable
class _Serving(Listing, Protocol):
    """What the prompt needs of the `grants` value (CONTRACTS.md: grants): `serve`, and what
    `/grants` lists and revokes."""

    def serve(self, prompt: Prompt) -> Callable[[], None]: ...
    def told(self) -> tuple[str, ...]: ...


@runtime_checkable
class _Choosing(Protocol):
    """What the prompt needs of the `output` value (CONTRACTS.md: output): the person's choice."""

    async def choose(self, question: Mapping[str, Any]) -> str: ...


@runtime_checkable
class _Registering(Protocol):
    """What the grant tool needs of the `tools` value (CONTRACTS.md: tools): a tool registered."""

    def register(
        self,
        spec: Mapping[str, Any],
        run: Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]],
        *,
        runs: str = ...,
    ) -> Callable[[], None]: ...


@runtime_checkable
class _Sections(Protocol):
    """What the grant tool needs of the `system` value (CONTRACTS.md: system): a section added."""

    def add(self, name: str, section: Callable[[], str]) -> Callable[[], None]: ...


@runtime_checkable
class _Refusing(Protocol):
    """What the grant tool needs of the `runner` value (CONTRACTS.md: runner): why a grant is never
    granted to what it starts."""

    def refusal(self, grant: Grant) -> str: ...


@runtime_checkable
class _Confining(Protocol):
    """What the grant tool needs of the `approval` value (CONTRACTS.md: approval): whether the runner
    confines what runs in it, so there is a jail to grant to."""

    @property
    def confined(self) -> bool: ...


@runtime_checkable
class _Telling(Protocol):
    """What the prompt needs of the `asides` value (CONTRACTS.md: asides)."""

    def add(self, fn: Callable[[Mapping[str, Any]], str]) -> Callable[[], None]: ...


class _Rechecked:
    """The jail, which first asks `refuse` at each start: the variables the model row's keys read
    change with the layers (another models file, an endpoint added), and the row does not
    reload for that, so a list that was fine when the row came up is checked again."""

    def __init__(self, jail: BrigJail, refuse: Callable[[], None]) -> None:
        self._jail = jail
        self._refuse = refuse

    def report(self) -> Mapping[str, str]:
        return self._jail.report()

    def notice(self) -> str:
        return self._jail.notice()

    async def release(self) -> str:
        return await self._jail.release()

    def refusal(self, grant: Grant) -> str:
        return self._jail.refusal(grant)

    async def start(self, argv_for: ArgvFor, *, cwd: str, owner: str, agent: str = "") -> Started:
        self._refuse()
        return await self._jail.start(argv_for, cwd=cwd, owner=owner, agent=agent)


@component(provides=("runner",))
async def confined(*, config: BrigConfig, host: Host, models: _KeyReaders, grants: Granting) -> Effects:
    """Fills a `runner` row: `use = "runner:confined"`. A brig jail for each program it starts:
    writes confined to the project, no network, credentials unreadable, graded honestly. Depends
    on `host` so a program can never write the files the running composition is read from, and on
    `grants`, whose value (not its binding) changes with what is granted, so a grant never reloads
    the row: each start reads `grants.granted()`. The
    variables its programs see are the baseline, the names in the person's `runner.toml` and the
    layer's `env` when it sets one (`allowlist`); a list that names a variable a key reads
    (`models.key_envs()`: every endpoint the model row can reach, asked again at each start) is
    refused (`allowlist.Refused`), the row before a jail exists and a start before its jail does.

    Raises:
        Refused: `runner.toml` can't be used, or the list holds a variable a key reads."""
    file = allowlist.location(os.environ, Path.home())
    standing = await asyncio.to_thread(allowlist.read, file, Path.cwd())

    def refuse() -> None:
        allowlist.effective(config, standing, file=file, readers=models.key_envs())

    jailed, note = allowlist.effective(config, standing, file=file, readers=models.key_envs())
    jail = BrigJail(jailed, host, note=note, key_envs=models.key_envs, grants=grants)
    yield bind("runner", Runner(_Rechecked(jail, refuse)))


@component(provides=("runner",))
async def unconfined() -> Effects:
    """Fills a `runner` row with no confinement: `use = "runner:unconfined"` (`--no-jail`). Every
    input, and every extension to load, is then put to the person."""
    yield bind("runner", Runner(Unjailed()))


@component(provides=("grants",))
async def grants(*, host: Host) -> Effects:
    """Fills a `grants` row: `use = "runner:grants"`. The broker of what the person granted the
    jail: a row's `need`, a requester's `ask`, `granted()` (what each start applies), `list` and
    `revoke`. It depends on `host` alone, which the shell pins, so the row never reloads: a grant
    changes the value it bound and not the binding, and so reloads neither `approval` (which
    depends on neither this row nor a requester) nor `runner:confined`."""
    yield bind("grants", Broker(Path(host.grants) if host.grants else None))


@component
async def grant_prompt(
    *, grants: _Serving, output: _Choosing, asides: _Telling, commands: _Registrar
) -> Effects:
    """Fills a `grant-prompt` row: `use = "runner:grant_prompt"`. Puts what the broker asks to the
    person through `output.choose` (once, always or no: the words are `prompting.question`), tells
    the model on the next call's result each answer decided since the last, and registers
    `/grants`, which lists what is granted (id, kind, target, answer, scope, who asked and why)
    and, as `/grants revoke ID`, takes one back, for the session or, for an always-grant, the
    project: the next start no longer applies it. A question under way when the row reloads or
    leaves is withdrawn: its asker is answered no and nothing is recorded.

    There is one per session: the broker serves one prompt, and a sub-agent's realm reads the
    broker from the parent's, so a child's `grant_tool` asks through this prompt and does not mount
    a second. The `grant` tool is `grant_tool`'s."""
    told: deque[str] = deque()  # the answers decided since the last call, as lines for the model

    async def prompt(request: Request) -> Answer | None:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
        asked = question(request, places=SOCKET_PLACES, runtime_dir=runtime_dir)
        answer = answer_of(await output.choose(asked))
        if answer is not None:
            told.append(decided(request, answer))
        return answer

    def aside(call: Mapping[str, Any]) -> str:
        lines: list[str] = []
        while told:
            lines.append(told.popleft())
        lines.extend(grants.told())
        return "\n".join(lines)

    spec = {
        "name": "grants",
        "help": "list what is granted to the jail, or `revoke ID` to take one back",
        "usage": "[revoke ID]",
    }
    yield acquire(grants.serve, prompt)
    yield acquire(asides.add, aside)
    yield acquire(commands.register, spec, partial(grants_command, grants))


@dataclass(frozen=True, slots=True)
class GrantToolConfig:
    """The `grant` row's config. `agent`: the label of the sub-agent whose tool it is (the agents row
    writes it, as it does the python row's), else empty: the session's own."""

    agent: str = ""


@component
async def grant_tool(
    *,
    grants: _Asking,
    tools: _Registering,
    system: _Sections,
    runner: _Refusing,
    approval: _Confining,
    config: GrantToolConfig,
) -> Effects:
    """Fills a `grant` row: `use = "runner:grant_tool"`. Registers the `grant` tool (`requesting`,
    `runs="harness"`, so `approval` asks nothing more of it than of any tool in the jail: its only
    effect is a question to the person, put by the broker) and tells the model of it in the `system`
    section `grants`. A call is a request from the python tool's input or, with config `agent`, from
    that sub-agent by its label. A request the floor refuses (`runner.refusal`) is answered, with
    why, before anyone is asked, and under `--no-jail` (`approval.confined` false) it says there is
    nothing to grant and asks nothing. A grant applies to the whole session. The row only asks, so
    a sub-agent's realm can mount it, while the prompt (`grant_prompt`) is the session's alone. It
    depends on `runner` and `approval`, so it reloads with them."""
    asker = requesting.asker(config.agent)

    async def grant(call: Mapping[str, Any]) -> dict[str, Any]:
        if not approval.confined:
            return {"content": requesting.NOTHING}
        made = requesting.requested(call, asker, lambda path: str(Path(path).resolve()))
        if isinstance(made, str):
            return {"content": made}
        if why := runner.refusal(made.grant):
            return {"content": requesting.refused(made, why)}
        return {"content": requesting.answered(made, await grants.ask(made))}

    yield acquire(tools.register, requesting.GRANT, grant, runs="harness")
    yield acquire(system.add, "grants", lambda: requesting.section(approval.confined))


@component(provides=("approval",))
async def approval(*, runner: Graded) -> Effects:
    """Fills an `approval` row: `use = "runner:approval"`. The rule for what runs unasked: what
    runs in the runner, when the runner confines it. Asking the person is the asker's (the loop,
    the extensions row), through `output.confirm`. Depends on the runner alone, so `/clear` (a new
    Python process) leaves it up. It runs in bh-02's own process: only a layer replaces it."""
    yield bind("approval", Approval(runner))


@component
async def release(*, runner: _Releasing, commands: _Registrar) -> Effects:
    """Fills a `release` row: `use = "runner:release"`. `/release` asks each row that started a
    program in the runner to stop its own (the Python process, the extensions process), then has
    the runner let go of what it holds on the host (on Linux, the empty directories it keeps in place
    of write-denied paths that do not exist yet, such as `.envrc`) until the next start: the way to
    create one of those mid-session."""

    async def run(args: str) -> str:
        return await runner.release() or "Nothing runs in the runner, and it holds nothing."

    spec = {
        "name": "release",
        "help": "stop what runs in the runner until the next input (to create a path the jail holds)",
        "usage": "",
    }
    yield acquire(commands.register, spec, run)

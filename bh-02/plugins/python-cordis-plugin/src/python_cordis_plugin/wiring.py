"""The row: the python tool, a persistent Python process the runner starts and the `python(code)`
tool that sends it inputs, registered with `tools`, with what the model is told about it added to
`system`, and the process's stop registered for `/release`."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, acquire, component, enter
from python_cordis_plugin.client import Access, Calls, Kernel, KernelConfig, Rule, Runner
from python_cordis_plugin.python import PYTHON, shown_call

__all__ = ["tool"]


@runtime_checkable
class _Releases(Protocol):
    """What the python row needs of the `runner` value besides a start (CONTRACTS.md: runner): its
    stop asked on `/release`, and its remover back."""

    def on_release(self, stop: Callable[[], Awaitable[str]]) -> Callable[[], None]: ...


@runtime_checkable
class _Runs(Runner, _Releases, Protocol):
    """The `runner` value as the python row uses it: a start, the grades, and `/release`."""


@runtime_checkable
class _Tools(Calls, Protocol):
    """What the python row needs of the `tools` value (CONTRACTS.md: tools): a tool registered,
    and its remover back; and the other tools, offered to an input as functions (`Calls`)."""

    def register(
        self,
        spec: Mapping[str, Any],
        run: Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]],
        *,
        runs: str = ...,
        show: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = ...,
    ) -> Callable[[], None]: ...


@runtime_checkable
class _Sections(Protocol):
    """What the python row needs of the `system` value (CONTRACTS.md: system): a named section
    added, and its remover back."""

    def add(self, name: str, section: Callable[[], str]) -> Callable[[], None]: ...


@component
async def tool(
    *, runner: _Runs, approval: Rule, tools: _Tools, system: _Sections, access: Access, config: KernelConfig
) -> Effects:
    """Fills a `python` row: `use = "python:tool"`. Starts a persistent Python process in the
    runner and registers the `python(code)` tool with `tools` (each call runs as an input in it;
    the loop asks the `approval` rule first, shown as its code), and adds what the model is told
    about it, its REPL and where it runs, as the `system` section `python`, read each time the
    prompt is. bh-02's other tools are functions in the namespace (`tools.NAME(...)`), each call
    one makes run as the model's own are (`tools.call`). Before an input's own Python opens a
    file in the project, the worker asks `access` about it, when a row is asking about that kind
    of opening (read, write), and a refusal stops the open. On `/release` the row stops its own
    process (`runner.on_release`); the next input starts it again.

    Depends on the runner, the rule and the three brokers, none of which reload, so swapping the
    model or the ui keeps the namespace, and so does a reload of the loop; swapping the runner
    starts a new process, which is the honest thing for a new runner to mean. A restart
    (`/clear`) registers the same tool again, so the loop reloads with nothing."""
    started = yield enter(Kernel(runner, config, access, rule=approval, tools=tools))
    yield acquire(runner.on_release, started.stopped)
    yield acquire(tools.register, PYTHON, started.call, show=shown_call)
    yield acquire(system.add, "python", started.instructions)

"""The one decorator: what it derives, what it refuses, and what a scan finds."""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import pytest

import cordis.loader
from cordis import Effects, Inspection, Runtime, State, bind, component, configure, scan
from cordis.authoring import lookup
from cordis.component import derive


@runtime_checkable
class Clock(Protocol):
    def now(self) -> str: ...


@dataclass(frozen=True, slots=True)
class Cfg:
    n: int = 1


# -- derivation ------------------------------------------------------------------------


def test_the_decorator_returns_the_function_unchanged() -> None:
    @component
    async def thing() -> Effects:
        yield bind("thing", 1)

    assert thing.__name__ == "thing"
    assert hasattr(thing(), "asend")  # callable directly: it attached, it did not wrap


def test_the_name_is_the_key_and_a_class_annotation_is_the_contract() -> None:
    @component
    async def consumer(*, clock: Clock, cache: Any) -> Effects:
        yield bind("consumer", (clock, cache))

    derived = derive(consumer)
    assert derived.inject == {"clock", "cache"}
    assert derived.params == (("clock", "clock"), ("cache", "cache"))
    assert derived.contracts == (("clock", Clock),)  # the bare name constrains nothing


def test_config_is_not_a_key() -> None:
    @component
    async def configured(*, config: Cfg, clock: Clock) -> Effects:
        yield bind("configured", config)

    derived = derive(configured)
    assert derived.inject == {"clock"}
    assert derived.wants_config and derived.config_type is Cfg


def test_a_function_that_does_not_yield_is_not_a_component() -> None:
    with pytest.raises(TypeError, match="is not a component"):

        @component
        async def plain(*, clock: Clock) -> str:  # type: ignore[misc]
            return clock.now()


def test_positional_parameters_are_refused_with_the_fix_in_the_message() -> None:
    with pytest.raises(TypeError) as raised:

        @component
        async def tool(msg: str, *, clock: Clock) -> Effects:  # type: ignore[misc]
            yield bind("tool", msg)

    assert "keyword-only" in str(raised.value)
    assert "yield bind(name, partial(fn, **deps))" in str(raised.value)


def test_configure_treats_only_a_dataclass_as_a_schema() -> None:
    assert configure({"n": 7}, Cfg, "c") == Cfg(7)
    assert configure(None, Cfg, "c") == Cfg()
    assert configure(Cfg(3), Cfg, "c") == Cfg(3)
    assert configure({"anything": 1}, None, "c") == {"anything": 1}
    assert configure("passed through", dict, "c") == "passed through"
    with pytest.raises(TypeError, match="invalid config for Cfg"):
        configure({"m": 1}, Cfg, "c")


async def test_bad_config_fails_the_fiber_before_any_effect_is_performed() -> None:
    @component
    async def configured(*, config: Cfg) -> Effects:
        yield bind("landed", True)

    rt = Runtime()
    f = rt.mount(configured, config={"m": 1})
    await rt.settle()
    assert f.state is State.FAILED
    assert "invalid config for Cfg" in str(f.error)
    assert Inspection(rt).bindings == {}


# -- scanning --------------------------------------------------------------------------


def test_a_scan_finds_a_packages_components(plugin: Any) -> None:
    found = scan(plugin)
    assert set(found) == {"subprocess", "git", "git_tools"}
    assert found["git"].inject == {"subprocess"}
    assert found["git_tools"].inject == {"git"}


def test_two_scans_of_one_package_are_independent_registries(plugin: Any) -> None:
    first, second = scan(plugin), scan(plugin)
    assert first is not second and set(first) == set(second)


def test_an_unknown_component_name_lists_what_the_package_has() -> None:
    with pytest.raises(LookupError, match="this package has loader"):
        lookup(scan(cordis.loader), "nope")


# -- a plugin end to end -------------------------------------------------------------------


async def test_the_plugin_composes_and_its_callables_are_bound(plugin: Any) -> None:
    rt = Runtime()
    rt.mount(plugin.subprocess, config={"reply": " M README.md\n"})
    rt.mount(plugin.git, config=plugin.GitConfig(binary="/usr/bin/git"))
    rt.mount(plugin.git_tools)
    await rt.settle()

    bindings = Inspection(rt).bindings
    assert set(bindings) == {"subprocess", "git", "git_status"}
    assert await bindings["git_status"].value() == " M README.md\n"
    assert bindings["subprocess"].value.calls == [("/usr/bin/git", "status", ".")]


async def test_a_callable_is_a_plain_function_tested_with_a_fake(plugin: Any) -> None:
    client = plugin.GitClient("git", plugin.FakeSubprocess("clean\n"))
    assert await plugin.git_status(git=client) == "clean\n"


async def test_replacing_the_seam_reloads_the_client_and_the_callables(plugin: Any) -> None:
    rt = Runtime()
    seam = rt.mount(plugin.subprocess, config={"reply": "first\n"})
    rt.mount(plugin.git)
    rt.mount(plugin.git_tools)
    await rt.settle()
    client = Inspection(rt).bindings["git"].value
    assert await Inspection(rt).bindings["git_status"].value() == "first\n"

    await seam.retire()  # the whole chain unloads, and the client is closed
    await rt.settle()
    assert client.closed and Inspection(rt).bindings == {}

    rt.mount(plugin.subprocess, config={"reply": "second\n"})
    await rt.settle()
    assert await Inspection(rt).bindings["git_status"].value() == "second\n"
    assert Inspection(rt).bindings["git"].value is not client

# Writing a plugin

A plugin is a Python package that ships cordis components. A layer names one of its components
for a row, and bh-02 runs it like any of its own: the shipped rows are plugins too. Write one to
add a part to bh-02, or to replace one.

## The shape of a plugin

In this repository a plugin is a workspace member under `bh-02/plugins/`, named
`<name>-cordis-plugin`, with its import package `<name>_cordis_plugin`:

```text
bh-02/plugins/hello-cordis-plugin/
├── pyproject.toml
├── README.md
├── src/hello_cordis_plugin/
│   ├── __init__.py      re-exports the package's names
│   ├── py.typed
│   └── wiring.py        the components
└── tests/
```

Its `pyproject.toml` declares the entry point cordis finds it by, and the libraries it uses:

```toml
[project]
name = "hello-cordis-plugin"
version = "0.1.0"
requires-python = ">=3.15"
dependencies = ["cordis"]

[project.entry-points."cordis.plugins"]
hello = "hello_cordis_plugin"

[tool.uv.sources]
cordis = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/hello_cordis_plugin"]
```

Nothing else needs registering: the workspace's members, tests, type checks and architecture
gates find a new directory by its place. Run `uv sync --all-packages`, since cordis reads entry
points from what is installed. Until then a layer naming the plugin shows an unresolved row.

## A component

A component declares the keys it needs as keyword-only parameters, each annotated with a Protocol
of its own that says what it needs of the value. It imports neither the plugin that provides the
key nor the broker it registers into.

This one adds a slash command, `/hello`, to the `commands` broker:

```python
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, acquire, component


@runtime_checkable
class Commands(Protocol):
    def register(
        self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[str]]
    ) -> Callable[[], None]: ...


async def greet(args: str) -> str:
    return f"hello, {args or 'there'}"


@component
async def hello(*, commands: Commands) -> Effects:
    spec = {"name": "hello", "help": "Say hello", "usage": "/hello [NAME]"}
    yield acquire(commands.register, spec, greet)
```

`acquire` keeps the remover `register` returns and calls it when the row goes, so the command
leaves with the row and nothing else reloads. cordis checks the value bound under `commands`
against the Protocol before the component starts; bind the wrong thing there and the row fails
with a message naming what is missing.

Then name it in a layer and start bh-02 with it:

```toml
[[plugin]]
id = "hello"
use = "hello:hello"
```

```sh
bh-02 --patch hello.toml
```

## Two halves

bh-02's own plugins keep two halves apart:

- **the value**: a plain library that doesn't import cordis (`loop.py`, `client.py`, `jail.py`),
  which you can test on its own;
- **the wiring**: `wiring.py`, the components that bind a value under a key or register into a
  broker.

The architecture gates hold every plugin in the repository to this, and to more: no plugin
imports another, and only the public parts of cordis are used ([Working on the code](../../contributing/index.md)).

## Agreeing with other plugins

Plugins agree on keys and the shapes of the values under them, and on nothing else. The keys
bh-02's rows wire, and what each value has, are in [Contracts](../reference/contracts.md). A
provider just has the methods; a consumer declares the part it reads. Data crosses as plain dicts.

To change a shipped part, bind the same key with the same shape from your own component, and put
your component in that row's `use`. The rows that depend on the key reload against yours.

## Shipping it with bh-02

A plugin the shipped layer names also goes in the app's own dependencies
(`bh-02/app/pyproject.toml`), so `uv tool install ./bh-02/app` installs it.

Each shipped plugin's README is the best guide to its shape:
[agent](../reference/plugins/agent.md), [runner](../reference/plugins/runner.md),
[chat](../reference/plugins/chat.md), [commands](../reference/plugins/commands.md),
[extensions](../reference/plugins/extensions.md), [python](../reference/plugins/python.md),
[memory](../reference/plugins/memory.md), [models](../reference/plugins/models.md),
[tui](../reference/plugins/tui.md). cordis's design doc explains components and effects:
[cordis](../../cordis/index.md#how-authors-add).

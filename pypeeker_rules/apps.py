"""The workspace's custom pypeeker rules: what spans packages, for any app built on cordis.

No rule here names a member. A gate's *units* are the packages under the `src/` paths its own
`[tool.pypeeker].src` lists (which `scripts/arch-check` writes from the globs in
`[tool.arch-check]`), so a new plugin is policed the moment its directory exists. What varies
by gate (which modules may touch the terminal, which shell modules may know cordis) is that
rule's own option table.

- `plugin-layering`: a unit imports itself and the libraries, never another unit; units agree on
  names and shapes in their family's CONTRACTS.md instead.
- `cordis-in-wiring-only`: only a unit's `wiring` modules and the `shell` modules know cordis; a
  plugin's value half is a plain library.
- `cordis-public-api`: outside cordis, import cordis only through its public surface (`cordis`,
  `cordis.loader`, `cordis.composition`, `cordis.testing`).
- `terminal-io`, `print-input`: only the `allowed` modules touch the terminal, so the interface
  stays swappable.
- `init-reexport-only`: a package `__init__.py` defines nothing; it re-exports.
- `worker-stdlib-only`: the named modules (a program run inside a jail) import only the stdlib.
- `brig-one-adapter`: only the `adapter` package imports brig.
"""

import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pypeeker.dsl import (
    DslRule,
    Selection,
    all_of,
    any_of,
    not_,
    references,
    register_dsl_rule,
    row,
    symbols,
)
from pypeeker.models import SymbolKind

# Modules that read from or write to a terminal.
_TERMINAL_MODULES = (
    "sys",
    "readline",
    "termios",
    "tty",
    "getpass",
    "curses",
    "click",
    "prompt_toolkit",
    "rich",
    "textual",
)

# Names in a terminal module that are not terminal I/O: the interpreter's path, the process's
# arguments, where it imports from (its environment's prefix and the base interpreter's), and
# what it runs on. Imported by name (`from sys import executable`), never the module.
_NOT_TERMINAL = (
    "sys.argv",
    "sys.base_prefix",
    "sys.executable",
    "sys.modules",
    "sys.path",
    "sys.platform",
    "sys.prefix",
)

# What every unit may import besides itself.
_LIBRARIES = ("cordis", "cordis_helpers")


def units() -> tuple[str, ...]:
    """The packages this gate polices: every package directly under one of its `src` paths.

    Read from the gate's own pyproject (the working directory `scripts/arch-check` runs it in),
    so the rules and the index always agree on what the gate covers.
    """
    config = tomllib.loads(Path("pyproject.toml").read_text())
    found = []
    for entry in config["tool"]["pypeeker"].get("src", []):
        root = Path(entry)
        if root.name != "src" or not root.is_dir():
            continue
        found += [pkg.name for pkg in root.iterdir() if (pkg / "__init__.py").is_file()]
    return tuple(sorted(found))


def _in_units(names: Sequence[str]) -> Any:
    return any_of(*(row.module.is_within(name) for name in names)) if names else row.module.eq("")


def _imports_any(names: Sequence[str]) -> Any:
    return any_of(*(any_of(row.imported_from.eq(n), row.imported_from.matches(f"{n}.*")) for n in names))


def _list(options: Mapping[str, Any], key: str) -> list[str]:
    return [str(v) for v in options.get(key, [])]


def _terminal_io(options: Mapping[str, Any]) -> Selection | None:
    return symbols().where(
        all_of(
            row.kind.eq(SymbolKind.IMPORT),
            _in_units(units()),
            *(not_(row.module.is_within(m)) for m in _list(options, "allowed")),
            _imports_any(_TERMINAL_MODULES),
            *(not_(row.imported_from.eq(name)) for name in _NOT_TERMINAL),
        )
    )


register_dsl_rule(
    DslRule(
        rule_id="terminal-io",
        build=_terminal_io,
        message=(
            "'{imported_from}' is terminal I/O; only the modules this gate's terminal-io `allowed` "
            "names may use it, so the interface stays swappable. Put it behind the ui port instead"
        ),
    )
)


def _print_input(options: Mapping[str, Any]) -> Selection | None:
    return references().where(
        all_of(
            _in_units(units()),
            *(not_(row.module.is_within(m)) for m in _list(options, "allowed")),
            # builtins resolve to `<builtins>.<name>` symbol ids; binding_name is only set for locals
            any_of(row.symbol_id.eq("<builtins>.print"), row.symbol_id.eq("<builtins>.input")),
        )
    )


register_dsl_rule(
    DslRule(
        rule_id="print-input",
        build=_print_input,
        message=(
            "'{symbol_id}' is terminal I/O; only the modules this gate's print-input `allowed` names "
            "may use it, so the interface stays swappable. Put it behind the ui port instead"
        ),
    )
)


def _crosses(unit: str, others: Sequence[str]) -> Any:
    return all_of(
        row.module.is_within(unit),
        any_of(*(row.imported_from.is_within(other) for other in others if other != unit)),
    )


def _plugin_layering(options: Mapping[str, Any]) -> Selection | None:
    found = units()
    if len(found) < 2:
        return None
    return symbols().where(
        all_of(row.kind.eq(SymbolKind.IMPORT), any_of(*(_crosses(unit, found) for unit in found)))
    )


register_dsl_rule(
    DslRule(
        rule_id="plugin-layering",
        build=_plugin_layering,
        message=(
            "'{module}' may not import '{imported_from}': a package imports only the libraries "
            f"({', '.join(_LIBRARIES)}, brig through its one adapter), never another package; agree "
            "on a name and a shape in the family's CONTRACTS.md instead"
        ),
    )
)


def _cordis_in_wiring_only(options: Mapping[str, Any]) -> Selection | None:
    return symbols().where(
        all_of(
            row.kind.eq(SymbolKind.IMPORT),
            _in_units(units()),
            not_(row.module.matches("*.wiring")),
            *(not_(row.module.is_within(m)) for m in _list(options, "shell")),
            any_of(row.imported_from.eq("cordis"), row.imported_from.matches("cordis.*")),
        )
    )


register_dsl_rule(
    DslRule(
        rule_id="cordis-in-wiring-only",
        build=_cordis_in_wiring_only,
        message=(
            "'{module}' imports cordis; only a plugin's wiring.py and an app's shell modules know "
            "the framework. Keep the value a plain library and bind it from the wiring"
        ),
    )
)

register_dsl_rule(
    DslRule(
        rule_id="init-reexport-only",
        build=lambda options: symbols().where(
            all_of(
                row.file_path.matches("*__init__.py"),
                row.is_module_level.is_true(),
                row.kind.is_in(SymbolKind.CLASS, SymbolKind.FUNCTION, SymbolKind.VARIABLE),
                not_(row.name.eq("__all__")),
            )
        ),
        message=(
            "'{name}' is defined in a package __init__.py, which only re-exports; define it in a "
            "module and re-export it here"
        ),
    )
)

register_dsl_rule(
    DslRule(
        rule_id="cordis-public-api",
        build=lambda options: symbols().where(
            all_of(
                row.kind.eq(SymbolKind.IMPORT),
                not_(row.module.is_within("cordis")),
                # `from cordis.x import Y` is imported_from "cordis.x.Y": a second dot is a deep import
                row.imported_from.matches("cordis.*.*"),
                not_(row.imported_from.matches("cordis.loader.*")),
                not_(row.imported_from.matches("cordis.composition.*")),
                not_(row.imported_from.matches("cordis.testing.*")),
            )
        ),
        message=(
            "import '{name}' from 'cordis' (or cordis.loader, cordis.composition, cordis.testing), "
            "not from its internal module ('{imported_from}')"
        ),
    )
)


def _worker_stdlib_only(options: Mapping[str, Any]) -> Selection | None:
    workers = _list(options, "modules")
    if not workers:
        return None
    return symbols().where(
        all_of(
            row.kind.eq(SymbolKind.IMPORT),
            any_of(*(row.module.is_within(m) for m in workers)),
            *(not_(row.imported_from.is_within(name)) for name in sorted(sys.stdlib_module_names)),
        )
    )


register_dsl_rule(
    DslRule(
        rule_id="worker-stdlib-only",
        build=_worker_stdlib_only,
        message=(
            "'{module}' imports '{imported_from}'; it runs inside a jail and imports only the "
            "standard library. A cell is plain Python, and what it may touch is the jail's "
            "decision: use the standard library, or do the work in bh-02 outside the kernel"
        ),
    )
)


def _brig_one_adapter(options: Mapping[str, Any]) -> Selection | None:
    adapter = str(options.get("adapter", ""))
    if not adapter:
        return None
    return symbols().where(
        all_of(
            row.kind.eq(SymbolKind.IMPORT),
            any_of(row.imported_from.eq("brig"), row.imported_from.matches("brig.*")),
            not_(row.module.is_within(adapter)),
        )
    )


register_dsl_rule(
    DslRule(
        rule_id="brig-one-adapter",
        build=_brig_one_adapter,
        message=(
            "'{module}' imports '{imported_from}'; only one adapter package imports brig. Depend on "
            "the `jail` key (CONTRACTS.md) instead, and let the layer file choose brig:jail"
        ),
    )
)

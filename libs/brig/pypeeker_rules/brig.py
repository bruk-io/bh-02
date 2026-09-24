"""brig's own gate rules for pypeeker: its layer DAG, and that it stands alone.

`brig-layers`: an import inside brig crosses only an edge `[tool.pypeeker.brig-layers.allow]`
draws (SPEC.md section 13). A layer always reaches itself; a module under brig that is not in
a declared layer fails, so a new layer must write down what it may import.

`brig-standalone`: brig imports only the standard library and itself. It knows nothing of
what embeds it, so nothing an embedder ships can reach into it by accident.

Run from this directory (`scripts/arch-check` does): pypeeker reads `[tool.pypeeker]` from
the nearest pyproject.toml and imports these rules from beside it.
"""

import sys
from collections.abc import Mapping
from typing import Any

from pypeeker.dsl import (
    DslRule,
    MultiPartRule,
    RulePart,
    Selection,
    all_of,
    any_of,
    not_,
    register_dsl_rule,
    row,
    symbols,
)
from pypeeker.models import SymbolKind

_PACKAGE = "brig"


def _forbidden_edges(allow: Mapping[str, list[str]]) -> list[Any]:
    """One clause per layer: it imports a declared layer the table gives it no edge to."""
    layers = tuple(allow)
    clauses = []
    for layer in layers:
        denied = [other for other in layers if other != layer and other not in allow[layer]]
        if denied:
            clauses.append(
                all_of(
                    row.module.is_within(f"{_PACKAGE}.{layer}"),
                    any_of(
                        *(row.imported_from.is_within(f"{_PACKAGE}.{other}") for other in denied)
                    ),
                )
            )
    return clauses


def _allow(options: Mapping[str, Any]) -> Mapping[str, list[str]]:
    return options.get("allow") or {}


def _crossings(options: Mapping[str, Any]) -> Selection | None:
    """Imports along an edge the table does not draw."""
    allow = _allow(options)
    if not allow:
        return None
    return symbols().where(all_of(row.kind.eq(SymbolKind.IMPORT), any_of(*_forbidden_edges(allow))))


def _undeclared(options: Mapping[str, Any]) -> Selection | None:
    """Modules under brig that belong to no declared layer."""
    allow = _allow(options)
    if not allow or not options.get("strict"):
        return None
    return symbols().where(
        all_of(
            row.kind.is_in(SymbolKind.MODULE, SymbolKind.PACKAGE),
            row.module.is_within(_PACKAGE),
            not_(row.module.eq(_PACKAGE)),
            *(not_(row.module.is_within(f"{_PACKAGE}.{layer}")) for layer in allow),
        )
    )


register_dsl_rule(
    MultiPartRule(
        rule_id="brig-layers",
        parts=(
            RulePart(
                build=_crossings,
                message=(
                    "'{module}' may not import '{imported_from}': brig's layer table draws no such "
                    "edge. If the layering in SPEC.md section 13 really changed, add the edge to "
                    "[tool.pypeeker.brig-layers.allow] with the reason"
                ),
            ),
            RulePart(
                build=_undeclared,
                message=(
                    "'{module}' is in no declared layer; a new layer gets a row in "
                    "[tool.pypeeker.brig-layers.allow] saying what it may import"
                ),
            ),
        ),
    )
)

register_dsl_rule(
    DslRule(
        rule_id="brig-standalone",
        build=lambda options: symbols().where(
            all_of(
                row.kind.eq(SymbolKind.IMPORT),
                row.module.is_within(_PACKAGE),
                not_(row.imported_from.is_within(_PACKAGE)),
                *(
                    not_(row.imported_from.is_within(name))
                    for name in sorted(sys.stdlib_module_names)
                ),
            )
        ),
        message=(
            "'{module}' imports '{imported_from}'; brig imports only the standard library and "
            "itself. An adapter to anything else belongs in the code that embeds brig"
        ),
    )
)

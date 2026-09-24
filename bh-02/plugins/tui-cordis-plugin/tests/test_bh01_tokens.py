"""bh-01's tokens into Textual themes: the generator (pure), and the committed theme matching it.

The drift test is hermetic: it regenerates from the snapshot beside `src/` (what
`scripts/sync-tokens` copied from bh-01) and compares with the committed module.
"""

from pathlib import Path

import pytest
from textual.color import Color

from tui_cordis_plugin import bh01_theme
from tui_cordis_plugin.tokens import THEME_FIELDS, custom_properties, module_source, semantic_colours

_SNAPSHOT = Path(__file__).resolve().parent.parent / "bh-01-tokens"

_PALETTE = """
:root {
  /* Accents */
  --bh-color-mandarin: #FF6B35;
  --bh-color-cod: #0D0C0A;
  --bh-color-alabaster: #F0ECE4;
}
"""


def _theme(light: str, dark: str) -> str:
    return (
        "@import '../tokens/index.css';\n\n"
        f":root,\n[data-theme='light'] {{\n{light}\n}}\n\n[data-theme='dark'] {{\n{dark}\n}}\n"
    )


_ROLES = "\n".join(f"  --bh-color-{role}: var(--bh-color-mandarin);" for role in set(THEME_FIELDS.values()))


def test_the_committed_theme_is_what_sync_tokens_would_write() -> None:
    colors, default = (_SNAPSHOT / "colors.css").read_text(), (_SNAPSHOT / "default.css").read_text()
    committed = Path(bh01_theme.__file__).read_text()
    assert module_source(colors, default) == committed, (
        "bh01_theme.py differs from what its snapshot generates: run scripts/sync-tokens "
        "(never edit bh01_theme.py by hand)"
    )


def test_custom_properties_reads_each_rule_and_ignores_comments_and_imports() -> None:
    rules = custom_properties(_theme("  --bh-color-bg: #fff; /* a note */", "  --bh-color-bg: #000;"))
    assert rules == {
        ":root, [data-theme='light']": {"--bh-color-bg": "#fff"},
        "[data-theme='dark']": {"--bh-color-bg": "#000"},
    }


def test_roles_resolve_var_chains_and_fallbacks_and_the_dark_block_layers_over_the_light() -> None:
    light, dark, skipped = semantic_colours(
        _PALETTE,
        _theme(
            "  --bh-color-bg: var(--bh-color-alabaster);\n"
            "  --bh-color-ring: var(--bh-color-primary);\n"
            "  --bh-color-primary: var(--bh-color-mandarin);\n"
            "  --bh-color-link: var(--bh-color-nowhere, #5DAFD6);\n"
            "  --bh-shadow-inset: inset 0 1px 3px rgba(0, 0, 0, 0.08);",
            "  --bh-color-bg: var(--bh-color-cod);",
        ),
    )
    assert light == {"bg": "#F0ECE4", "ring": "#FF6B35", "primary": "#FF6B35", "link": "#5DAFD6"}
    assert dark == {**light, "bg": "#0D0C0A"}  # the dark block names only what differs
    assert skipped == []  # shadows are never read, so never skipped


def test_rgba_becomes_hex_with_alpha_and_what_is_no_colour_is_skipped_by_name() -> None:
    light, _, skipped = semantic_colours(
        _PALETTE,
        _theme(
            "  --bh-color-primary-glow: rgba(255, 107, 53, 0.15);\n"
            "  --bh-color-sheen: linear-gradient(red, blue);",
            "",
        ),
    )
    assert light == {"primary-glow": "#FF6B3526"}
    assert Color.parse(light["primary-glow"]).a == pytest.approx(0.15, abs=0.01)
    assert skipped == ["sheen"]


def test_a_loop_in_the_tokens_says_where_it_is() -> None:
    with pytest.raises(ValueError, match=r"--bh-color-a -> --bh-color-b -> --bh-color-a"):
        semantic_colours(
            _PALETTE, _theme("  --bh-color-a: var(--bh-color-b);\n  --bh-color-b: var(--bh-color-a);", "")
        )


def test_renamed_theme_selectors_say_what_to_update() -> None:
    with pytest.raises(ValueError, match="update tokens.py"):
        semantic_colours(_PALETTE, ":root { --bh-color-bg: #fff; }")


def test_a_theme_field_without_its_role_says_how_to_remap_it() -> None:
    with pytest.raises(ValueError, match="THEME_FIELDS"):
        module_source(_PALETTE, _theme("  --bh-color-bg: #fff;", ""))


def test_a_generated_module_names_both_themes_and_every_role_as_a_variable() -> None:
    source = module_source(_PALETTE, _theme(_ROLES, "  --bh-color-bg: var(--bh-color-cod);"))
    namespace: dict[str, object] = {}
    exec(compile(source, "bh01_theme", "exec"), namespace)
    dark, light = namespace["dark"](), namespace["light"]()  # type: ignore[operator]
    assert (dark.name, dark.dark, light.name, light.dark) == ("bh-01-dark", True, "bh-01-light", False)
    assert dark.background == "#0D0C0A" and light.background == "#FF6B35"
    assert set(dark.variables) == {f"bh-{role}" for role in THEME_FIELDS.values()}


def test_a_var_to_nothing_is_an_error_naming_the_block_the_property_and_the_target() -> None:
    colors, default = (_SNAPSHOT / "colors.css").read_text(), (_SNAPSHOT / "default.css").read_text()
    dark_start = default.index("[data-theme='dark']")
    broken = default[:dark_start] + default[dark_start:].replace(
        "--bh-color-text-muted: var(--bh-color-boulder)", "--bh-color-text-muted: var(--bh-color-typo)"
    )
    assert broken != default
    with pytest.raises(ValueError, match=r"dark block: --bh-color-text-muted -> var\(--bh-color-typo\)"):
        module_source(colors, broken)


def test_a_dark_role_pointing_nowhere_is_not_skipped_as_not_a_colour() -> None:
    with pytest.raises(
        ValueError, match=r"dark block: --bh-color-bg -> var\(--bh-color-nowhere\).*bh-01's CSS"
    ):
        semantic_colours(
            _PALETTE,
            _theme(
                "  --bh-color-bg: var(--bh-color-alabaster);", "  --bh-color-bg: var(--bh-color-nowhere);"
            ),
        )


def test_a_fallback_is_resolved_like_any_value_and_a_fallback_to_nothing_is_an_error() -> None:
    light, _, skipped = semantic_colours(
        _PALETTE, _theme("  --bh-color-link: var(--bh-color-nowhere, var(--bh-color-mandarin));", "")
    )
    assert light == {"link": "#FF6B35"} and skipped == []
    with pytest.raises(ValueError, match=r"light block: --bh-color-link -> var\(--bh-color-gone\)"):
        semantic_colours(
            _PALETTE, _theme("  --bh-color-link: var(--bh-color-nowhere, var(--bh-color-gone));", "")
        )


def test_a_role_that_is_a_colour_in_one_theme_only_is_an_error() -> None:
    with pytest.raises(ValueError, match=r"`--bh-color-sheen` \(light only\)"):
        semantic_colours(
            _PALETTE,
            _theme(
                "  --bh-color-sheen: var(--bh-color-cod);", "  --bh-color-sheen: linear-gradient(red, blue);"
            ),
        )

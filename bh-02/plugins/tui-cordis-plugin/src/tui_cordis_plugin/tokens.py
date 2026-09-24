"""bh-01's design tokens as Textual themes: read its CSS, write the source of `bh01_theme`.

Pure text in, text out; `scripts/sync-tokens` does the file work. The inputs are bh-01's
palette (`dist/tokens/colors.css`, one `:root` block of `--bh-color-<name>: #hex`) and its
semantic theme (`dist/themes/default.css`: a light block on `:root, [data-theme='light']` and a
dark block on `[data-theme='dark']`, each `--bh-color-<role>: var(--bh-color-<name>)`). Every
`--bh-color-*` role becomes a variable `$bh-<role>` in both themes, its `var()` chain resolved
and its value written as hex (`#RRGGBB`, or `#RRGGBBAA` for bh-01's `rgba()` glows), which tcss
parses. A role whose value is not a colour Textual parses (a gradient, say) is left out of both
themes and listed in the module. A broken token is an error, never a role left out: a `var()`
naming a property nothing defines (with no fallback), a loop, or a role that is a colour in one
theme and not in the other (a stylesheet naming it would fail under that theme). Shadows
(`--bh-shadow-*`) are not colours and are never read.
"""

import re
from collections.abc import Mapping

from textual.color import Color, ColorParseError

__all__ = ["THEME_FIELDS", "custom_properties", "module_source", "semantic_colours"]

_PREFIX = "--bh-color-"
_LIGHT = ":root, [data-theme='light']"
_DARK = "[data-theme='dark']"
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_AT_STATEMENT = re.compile(r"@[\w-]+[^;{}]*;")
_BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}")
_DECLARATION = re.compile(r"(--[\w-]+)\s*:\s*([^;]+?)\s*(?:;|$)")
_VAR = re.compile(r"^var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)$")

# Textual's theme fields, each from a bh-01 role. Mandarin (`primary`, `accent`) is for what
# can be acted on or is selected; sky (`accent-secondary`) is Textual's `secondary`.
THEME_FIELDS: Mapping[str, str] = {
    "primary": "primary",
    "secondary": "accent-secondary",
    "accent": "accent",
    "warning": "warning",
    "error": "danger",
    "success": "success",
    "foreground": "text",
    "background": "bg",
    "surface": "surface",
    "panel": "surface-raised",
}


def custom_properties(css: str) -> dict[str, dict[str, str]]:
    """Return every rule's custom properties, keyed by its selector list (`a, b`, normalised).

    Comments and `@import`-style statements are dropped; a selector seen twice merges, the
    later declaration winning, as in CSS.
    """
    text = _AT_STATEMENT.sub("", _COMMENT.sub("", css))
    rules: dict[str, dict[str, str]] = {}
    for selector, body in _BLOCK.findall(text):
        key = ", ".join(part.strip() for part in selector.split(",") if part.strip())
        found = {name: value for name, value in _DECLARATION.findall(body)}
        rules[key] = {**rules.get(key, {}), **found}
    return rules


def semantic_colours(colors_css: str, default_css: str) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Return the light and dark roles (`role -> #hex`) and the roles skipped as not colours.

    The dark block applies over the light one, as `[data-theme='dark']` does over `:root`.
    """
    palette = custom_properties(colors_css).get(":root", {})
    rules = custom_properties(default_css)
    if _LIGHT not in rules or _DARK not in rules:
        raise ValueError(
            f"bh-01's default.css has no `{_LIGHT}` or no `{_DARK}` block; the rules it has are "
            f"{sorted(rules)}. If bh-01 renamed its theme selectors, update tokens.py to match."
        )
    light_scope = {**palette, **rules[_LIGHT]}
    dark_scope = {**light_scope, **rules[_DARK]}
    light, skipped = _roles(rules[_LIGHT], light_scope, "light")
    dark, skipped_dark = _roles({**rules[_LIGHT], **rules[_DARK]}, dark_scope, "dark")
    one_sided = sorted(set(light) ^ set(dark))
    if one_sided:
        where = ", ".join(f"`{_PREFIX}{r}` ({'light' if r in light else 'dark'} only)" for r in one_sided)
        raise ValueError(
            f"bh-01's roles are colours in one theme and not the other: {where}; a stylesheet naming "
            "one would fail under the other theme. Make each a colour in both blocks in bh-01's CSS."
        )
    return light, dark, sorted({*skipped, *skipped_dark})


def module_source(colors_css: str, default_css: str) -> str:
    """Return the source text of `bh01_theme`: two Themes and their `$bh-*` variables."""
    light, dark, skipped = semantic_colours(colors_css, default_css)
    for role in THEME_FIELDS.values():
        if role not in light or role not in dark:
            raise ValueError(
                f"bh-01 has no colour for the role `{_PREFIX}{role}` in both themes, and a Textual "
                "theme field is made from it; map the field to another role in tokens.THEME_FIELDS."
            )
    skipped_note = (
        "\n\nLeft out, as not colours Textual parses: " + ", ".join(f"`{_PREFIX}{r}`" for r in skipped) + "."
        if skipped
        else ""
    )
    return (
        '"""bh-01\'s design tokens as Textual themes. Generated by scripts/sync-tokens; do not edit.\n'
        "\n"
        "From bh-01's `dist/tokens/colors.css` and `dist/themes/default.css`, snapshotted in\n"
        "`bh-02/plugins/tui-cordis-plugin/bh-01-tokens/`. Every `--bh-color-<role>` is the variable\n"
        f"`$bh-<role>` in both themes.{skipped_note}\n"
        '"""\n'
        "\n"
        "from textual.theme import Theme\n"
        "\n"
        '__all__ = ["DARK", "DARK_VARIABLES", "LIGHT", "LIGHT_VARIABLES", "dark", "light"]\n'
        "\n"
        'DARK = "bh-01-dark"\n'
        'LIGHT = "bh-01-light"\n'
        "\n"
        f"{_variables('DARK_VARIABLES', dark)}\n"
        "\n"
        f"{_variables('LIGHT_VARIABLES', light)}\n"
        "\n"
        f"{_theme_function('dark', 'DARK', dark, is_dark=True)}\n"
        "\n"
        f"{_theme_function('light', 'LIGHT', light, is_dark=False)}"
    )


def _roles(
    names: Mapping[str, str], scope: Mapping[str, str], block: str
) -> tuple[dict[str, str], list[str]]:
    """Resolve each `--bh-color-*` property a theme block names (`names`) to hex, in `scope`;
    return the roles, and those whose value is not a colour Textual parses. `block` (light or
    dark) is what an error names.

    Only the theme's own roles become variables, not the palette they are drawn from, so a
    widget names a role (`$bh-text-muted`), never a colour (`mandarin`).
    """
    roles: dict[str, str] = {}
    skipped: list[str] = []
    for name in names:
        if not name.startswith(_PREFIX):
            continue
        role = name.removeprefix(_PREFIX)
        value = _resolve(name, scope, (), block)
        try:
            roles[role] = Color.parse(value).hex
        except ColorParseError:
            skipped.append(role)
    return roles, skipped


def _resolve(name: str, scope: Mapping[str, str], seen: tuple[str, ...], block: str) -> str:
    """Follow `name`'s `var()` chain to a literal value (in the `block` theme, for errors)."""
    if name in seen:
        raise ValueError(f"bh-01's tokens loop: {' -> '.join((*seen, name))}; fix the chain in bh-01's CSS")
    return _value(scope[name], scope, (*seen, name), block)


def _value(value: str, scope: Mapping[str, str], seen: tuple[str, ...], block: str) -> str:
    """`value` as a literal: a `var()` followed to its target, or else to its fallback (itself
    resolved the same way), the last name in `seen` being the property it is the value of."""
    match = _VAR.match(value)
    if match is None:
        return value
    target, fallback = match.groups()
    if target in scope:
        return _resolve(target, scope, seen, block)
    if fallback is not None:
        return _value(fallback.strip(), scope, seen, block)
    raise ValueError(
        f"bh-01's {block} block: {' -> '.join(seen)} -> var({target}), which neither bh-01's palette nor its "
        "theme defines; fix it in bh-01's CSS"
    )


def _variables(constant: str, roles: Mapping[str, str]) -> str:
    """A dict constant of `bh-<role>` variables, one per line (the shape ruff formats it to)."""
    lines = "".join(f'    "bh-{role}": "{value}",\n' for role, value in roles.items())
    return f"{constant}: dict[str, str] = {{\n{lines}}}\n"


def _theme_function(function: str, constant: str, roles: Mapping[str, str], *, is_dark: bool) -> str:
    """A function returning the Theme, its fields from `THEME_FIELDS`, its variables the constant."""
    fields = "".join(f'        {field}="{roles[role]}",\n' for field, role in THEME_FIELDS.items())
    return (
        f"def {function}() -> Theme:\n"
        f'    """Return bh-01\'s {function} theme."""\n'
        "    return Theme(\n"
        f"        name={constant},\n"
        f"{fields}"
        f"        dark={is_dark},\n"
        f"        variables=dict({constant}_VARIABLES),\n"
        "    )\n"
    )

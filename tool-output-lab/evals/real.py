"""Real files as eval payloads, with every answer computed from the file.

Python by `ast`; Rust by ast-grep pattern queries (a separate code path from the fold's own tree
building); XML by ElementTree; JSON by `json`. Each function takes the file's text and returns
plain data, so the truth for a task is computed the same way every time.
"""

import ast
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from ast_grep_py import SgNode, SgRoot

from compressors.tree import lenient_xml

STDLIB = Path("/usr/local/lib/python3.13")
CARGO = Path("/root/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f")
ISO_3166_2 = Path("/usr/share/xml/iso-codes/iso_3166-2.xml")
PYPI_CLICK = Path(__file__).resolve().parent.parent / "corpus/real/pypi-click.json"

# --- Python -------------------------------------------------------------------------------------


def py_class(src: str, name: str) -> ast.ClassDef:
    return next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef) and n.name == name)


def py_names(src: str) -> frozenset[str]:
    """Every function, method and class name in the file: what an answer could name."""
    kinds = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    return frozenset(n.name for n in ast.walk(ast.parse(src)) if isinstance(n, kinds))


def py_methods(src: str, cls: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in py_class(src, cls).body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def py_async_methods(src: str, cls: str) -> frozenset[str]:
    return frozenset(n.name for n in py_methods(src, cls) if isinstance(n, ast.AsyncFunctionDef))


def py_method_line(src: str, cls: str, method: str) -> int:
    return next(n.lineno for n in py_methods(src, cls) if n.name == method)


def py_both_platforms(src: str, cls: str = "Popen") -> frozenset[str]:
    """Methods defined in both branches of the class's `if _mswindows:` check."""

    def defs(body: list[ast.stmt]) -> set[str]:
        return {n.name for n in body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}

    names: set[str] = set()
    for n in py_class(src, cls).body:
        if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "_mswindows":
            names |= defs(n.body) & defs(n.orelse)
    return frozenset(names)


def py_subclasses(src: str, base: str) -> frozenset[str]:
    return frozenset(
        c.name
        for c in ast.walk(ast.parse(src))
        if isinstance(c, ast.ClassDef) and any(isinstance(b, ast.Name) and b.id == base for b in c.bases)
    )


# --- Rust ---------------------------------------------------------------------------------------


def _rust_impl(src: str, type_name: str) -> SgNode:
    root = SgRoot(src, "rust").root()
    for im in root.find_all(kind="impl_item"):
        ty = im.field("type")
        if ty is not None and ty.text().split("<")[0] == type_name and im.field("trait") is None:
            return im
    raise LookupError(f"no inherent `impl {type_name}` in this file")


def rust_impl_fns(src: str, type_name: str) -> list[tuple[str, int]]:
    """(name, 1-based line) of every function directly in the first inherent `impl type_name`."""
    im = _rust_impl(src, type_name)
    body = im.field("body")
    assert body is not None
    out = []
    for child in body.children():
        if child.kind() == "function_item":
            name = child.field("name")
            assert name is not None
            out.append((name.text(), child.range().start.line + 1))
    return out


def rust_names(src: str) -> frozenset[str]:
    root = SgRoot(src, "rust").root()
    names = set()
    for kind in ("function_item", "struct_item", "enum_item", "trait_item"):
        for n in root.find_all(kind=kind):
            name = n.field("name")
            if name is not None:
                names.add(name.text())
    return frozenset(names)


# --- XML ----------------------------------------------------------------------------------------


def iso_entries(src: str, country: str) -> list[tuple[str, str]]:
    """(code, name) of every subdivision of a country in iso_3166-2.xml.

    Raises:
        LookupError: the file has no such country.
    """
    root = ET.fromstring(lenient_xml(src).encode("utf-8"))
    for c in root.iter("iso_3166_country"):
        if c.get("code") == country:
            return [(e.get("code", ""), e.get("name", "")) for e in c.iter("iso_3166_2_entry")]
    raise LookupError(f"no country {country!r} in the file")


def iso_codes(src: str) -> frozenset[str]:
    entries = ET.fromstring(lenient_xml(src).encode("utf-8")).iter("iso_3166_2_entry")
    return frozenset(e.get("code", "") for e in entries)


# --- JSON ---------------------------------------------------------------------------------------


def pypi_versions(src: str) -> list[str]:
    return list(json.loads(src)["releases"])


def pypi_upload_year(src: str, version: str) -> str | None:
    files = json.loads(src)["releases"][version]
    return files[0]["upload_time"][:4] if files else None


def pypi_released_in(src: str, year: str) -> frozenset[str]:
    return frozenset(v for v in pypi_versions(src) if pypi_upload_year(src, v) == year)


def pypi_sha256(src: str, version: str) -> str:
    files = json.loads(src)["releases"][version]
    wheel = next((f for f in files if f["packagetype"] == "bdist_wheel"), files[0])
    return str(wheel["digests"]["sha256"])

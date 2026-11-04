"""Real files as eval payloads, with every answer computed from the file.

Python by `ast`; Rust by ast-grep pattern queries (a separate code path from the fold's own tree
building); XML by ElementTree; JSON by `json`. Each function takes the file's text and returns
plain data, so the truth for a task is computed the same way every time. Edits are checked the same
way: by `ast`, against the original, so formatting never matters and any other change does.
"""

import ast
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass
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


# --- edits (Python) ---------------------------------------------------------------------------------


def _parse(edited: str) -> ast.Module | str:
    try:
        return ast.parse(edited)
    except SyntaxError as e:
        return f"the edited file does not parse: {e.msg} on line {e.lineno}"


def _method(tree: ast.Module, cls: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    found = [
        d
        for c in ast.walk(tree)
        if isinstance(c, ast.ClassDef) and c.name == cls
        for d in c.body
        if isinstance(d, ast.FunctionDef | ast.AsyncFunctionDef) and d.name == name
    ]
    return found[0] if len(found) == 1 else None


def added_keyword_only(cls: str, method: str, param: str, default: str) -> Callable[[str, str], str | None]:
    """A check that `cls.method` gained the keyword-only parameter `param=default`, and that taking it
    away again gives the original exactly."""

    def check(original: str, edited: str) -> str | None:
        tree = _parse(edited)
        if isinstance(tree, str):
            return tree
        target = _method(tree, cls, method)
        if target is None:
            return f"{cls}.{method} is missing, or defined more than once"
        names = [a.arg for a in target.args.kwonlyargs]
        if param not in names:
            where = "a positional parameter" if param in [a.arg for a in target.args.args] else "absent"
            return f"{param} is not keyword-only in {cls}.{method} (it is {where})"
        i = names.index(param)
        given = target.args.kw_defaults[i]
        if given is None or ast.unparse(given) != default:
            return f"{param} defaults to {ast.unparse(given) if given else 'nothing'}, not {default}"
        del target.args.kwonlyargs[i], target.args.kw_defaults[i]
        if ast.dump(tree) != ast.dump(ast.parse(original)):
            return f"something besides {param} changed"
        return None

    return check


def renamed(old: str, new: str) -> Callable[[str, str], str | None]:
    """A check that every use of the name `old` (a definition, an attribute, a name) became `new`, and
    that renaming back gives the original exactly. Strings are renamed back too, so a docstring that
    mentions the method may keep the old name or take the new one."""

    def check(original: str, edited: str) -> str | None:
        tree = _parse(edited)
        if isinstance(tree, str):
            return tree
        left = sorted(
            {n.lineno for n in ast.walk(tree) if isinstance(n, ast.stmt | ast.expr) and _named(n) == old}
        )
        if left:
            return (
                f"{old} is still used on line{'s' if len(left) > 1 else ''} {', '.join(map(str, left[:5]))}"
            )
        for n in ast.walk(tree):
            if _named(n) == new:
                _rename(n, old)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                n.value = re.sub(rf"\b{re.escape(new)}\b", old, n.value)
        if ast.dump(tree) != ast.dump(ast.parse(original)):
            return f"something besides the rename changed (or {new} now names something that was not {old})"
        return None

    return check


def _named(node: ast.AST) -> str | None:
    match node:
        case ast.FunctionDef(name=n) | ast.AsyncFunctionDef(name=n) | ast.ClassDef(name=n):
            return n
        case ast.Attribute(attr=n) | ast.Name(id=n):
            return n
        case _:
            return None


def _rename(node: ast.AST, to: str) -> None:
    match node:
        case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
            node.name = to
        case ast.Attribute():
            node.attr = to
        case ast.Name():
            node.id = to


# --- HDFS logs (Loghub's HDFS_v1, `./lab fetch hdfs`) ---------------------------------------------

HDFS_BLOCKS = Path(__file__).resolve().parent.parent / "corpus/real/hdfs/blocks.jsonl"
_ALLOCATED = re.compile(r"NameSystem\.allocateBlock: (\S+)\. (blk_-?\d+)$")
_IDS = re.compile(r"blk_-?\d+")
_ADDRESSES = re.compile(r"/?\d+(?:\.\d+){3}(?::\d+)?")
_NUMBERS = re.compile(r"\d+")


@dataclass(frozen=True)
class HdfsBlock:
    """One HDFS block's lines, in the log's order, and whether the cluster's operators marked it
    anomalous (the dataset's label: the truth, set by people, not by this lab)."""

    block: str
    anomalous: bool
    lines: tuple[tuple[int, str], ...]  # (line number in the original log, the line)


def hdfs_blocks(text: str) -> tuple[HdfsBlock, ...]:
    out = []
    for line in text.splitlines():
        if line.strip():
            r = json.loads(line)
            out.append(HdfsBlock(r["block"], bool(r["anomaly"]), tuple((n, s) for n, s in r["lines"])))
    return tuple(out)


def hdfs_log(blocks: Iterable[HdfsBlock]) -> str:
    """The blocks' lines merged in the original log's order: the log filtered to those blocks."""
    return "\n".join(s for _, s in sorted(x for b in blocks for x in b.lines)) + "\n"


def hdfs_template(line: str) -> str:
    """A line's message with its block ids, addresses and numbers blanked: the kind of event it is."""
    message = line.split(": ", 1)[1] if ": " in line else line
    return _NUMBERS.sub("<n>", _ADDRESSES.sub("<ip>", _IDS.sub("<blk>", message)))


def hdfs_rare_templates(blocks: Iterable[HdfsBlock], share: float = 0.01) -> frozenset[str]:
    """The kinds of line at most `share` of the normal blocks have."""
    normal = [b for b in blocks if not b.anomalous]
    held: dict[str, int] = {}
    for b in normal:
        for t in {hdfs_template(s) for _, s in b.lines}:
            held[t] = held.get(t, 0) + 1
    every = {hdfs_template(s) for b in blocks for _, s in b.lines}
    return frozenset(t for t in every if held.get(t, 0) <= share * len(normal))


def hdfs_allocated(b: HdfsBlock) -> str | None:
    """The file the block was allocated for, from its allocateBlock line."""
    for _, s in b.lines:
        if (m := _ALLOCATED.search(s)) and m[2] == b.block:
            return m[1]
    return None

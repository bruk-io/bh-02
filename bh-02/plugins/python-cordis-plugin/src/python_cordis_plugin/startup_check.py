"""A startup file's docstrings against decision-0006's convention: the program that checks them.

Run by path (``python -I startup_check.py [--ruff] [--json] [--name NAME] FILE...``), never imported
by the Python process or by the command line: importing ``python_cordis_plugin`` runs its
``__init__``, which imports cordis, and this file imports the standard library and nothing else, so
the same text runs in a jail and under ``bh-02 check-examples`` without either importing the
package. It reads the text it is given and executes none of it.

The pure core takes the text of a file and returns findings (`Finding`). It looks only at the
functions and classes the file tells (decision-0006's point 1, decided here from the syntax: the
public ones the file defines, or exactly the ones its literal ``__all__`` names; the Python process
decides it from the live objects, and the host takes the names both agree on):

- `examples` is bh-02's own rule, for what ruff has none for: an example in the docstring (a doctest
  block or a ``::`` literal block, code `example`), and doctest blocks that parse and have a blank
  line before them (code `doctest`). The blank line after one can't be checked: `doctest` reads
  everything up to it as the expected output.
- `ruff_findings` reads ruff's JSON report for the rules ruff does have (`RUFF_CODES`: a docstring on a
  public function and class, a summary line, none empty) and keeps those that are about a told name.

The shell runs them. With no flag it runs the example rule, prints one line per finding to stdout, and
exits 1 on a finding, 0 on none, and 2 when a file could not be checked (a usage error, a file that is
not readable or not Python). ``--ruff`` also runs ruff, as ``sys.executable -m ruff`` with bh-02's flags
only (`RUFF_FLAGS`), over the file's text on stdin, so no ruff configuration the model could write
loosens it. ``--json`` prints one line, ``{"misses": [[name, [code, ...]], ...]}`` (a code, never a
message), for the host to read as data. A FILE of ``-`` is the text on stdin, named by ``--name`` (the
person's startup file, which a jail can't read, is handed in that way).
"""

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = ["CODES", "RUFF_CODES", "RUFF_FLAGS", "Finding", "examples", "main", "ruff_findings", "summary"]

# What ruff checks (decision-0006 point 7): a docstring on each public function and class, a summary
# line, none empty. ruff calls public what point 1 tells: no leading underscore, and only the names in
# `__all__` when the file has one.
RUFF_CODES = ("D101", "D103", "D205", "D415", "D419")
# bh-02's rule's own codes, after ruff's: the order a finding's codes are told in
CODES = (*RUFF_CODES, "example", "doctest")
# bh-02's flags only: --isolated ignores every configuration file, which the model can write
RUFF_FLAGS = ("--isolated", "--no-fix", "--select", ",".join(RUFF_CODES))
_RUFF_S = 20.0  # how long ruff gets: it takes milliseconds, and a hang must not hold up a REPL
_NO_EXAMPLE = "no example: add a doctest block (>>> calls) or a :: literal block to the docstring"

type _Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


@dataclass(frozen=True, slots=True)
class Finding:
    """A told function or class that breaks the convention: its `name`, the `line` of the finding
    (the definition's, or the docstring's), the rule `code` (one of `CODES`) and `message`, what
    to do, which quotes the file at most for a doctest block that does not parse."""

    name: str
    line: int
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class _Docstring:
    """What a docstring has of examples: whether it has `example`s (a doctest block or a literal
    block), and `problem`, what is wrong with its doctest blocks, or "" when nothing is."""

    example: bool
    problem: str = ""


def _definitions(node: ast.AST) -> Iterator[_Definition]:
    """The functions and classes defined at `node`'s level, in source order: its own statements and
    those of the `if`, `try`, `with`, `for`, `while` and `match` blocks in it (a definition under
    `if TYPE_CHECKING` or `try` binds a module-level name), but not those inside another function
    or class."""
    for child in ast.iter_child_nodes(node):
        match child:
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                yield child
            case ast.stmt() | ast.ExceptHandler() | ast.match_case():
                yield from _definitions(child)
            case _:
                pass


def _is_all(target: ast.expr) -> bool:
    """Whether `target` is the name `__all__`."""
    return isinstance(target, ast.Name) and target.id == "__all__"


def _listed(value: ast.expr | None) -> tuple[str, ...] | None:
    """The strings in a list or tuple literal; None for anything else (a call, a name, a set),
    which says nothing of what `__all__` lists."""
    match value:
        case ast.List(elts=items) | ast.Tuple(elts=items):
            return tuple(
                item.value for item in items if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
        case _:
            return None


def _exported(module: ast.Module) -> tuple[str, ...] | None:
    """The names the module's own statements put in `__all__` (``=``, ``:`` and ``+=`` of a list
    or tuple literal), in order; None when it has none. Computed lists are not read: ruff doesn't
    read them either, and a file whose `__all__` is one is told as a file with none."""
    found: tuple[str, ...] | None = None
    for node in module.body:
        match node:
            case ast.Assign(targets=targets, value=value) if any(_is_all(each) for each in targets):
                listed = _listed(value)
            case ast.AnnAssign(target=target, value=value) if _is_all(target):
                listed = _listed(value)
            case ast.AugAssign(target=target, op=ast.Add(), value=value) if _is_all(target):
                listed = _listed(value)
            case _:
                continue
        if listed is not None:
            found = (*(found or ()), *listed)
    return found


def _told(module: ast.Module) -> dict[str, _Definition]:
    """The functions and classes the file tells, by name: the public ones it defines (no leading
    underscore), or exactly those of its `__all__` it defines (an imported name has no source here
    to judge). The last definition of a name is the one the namespace holds."""
    defined = {each.name: each for each in _definitions(module)}
    exported = _exported(module)
    if exported is None:
        return {name: each for name, each in defined.items() if not name.startswith("_")}
    return {name: defined[name] for name in dict.fromkeys(exported) if name in defined}


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _literal_block(lines: Sequence[str]) -> bool:
    """Whether a paragraph ends in ``::`` and an indented block follows it, after a blank line."""
    for index, line in enumerate(lines):
        text = line.strip()
        if not text.endswith("::") or text.startswith(".."):
            continue
        after = lines[index + 1 :]
        if after and not after[0].strip():
            block = next((each for each in after if each.strip()), None)
            if block is not None and _indent(block) > _indent(line):
                return True
    return False


def _spaced(spans: Sequence[tuple[int, int]], lines: Sequence[str]) -> int | None:
    """The line, from 1, of the first doctest block that has no blank line before it, or None.
    `spans` are the doctest examples, each its first line (from 0) and how many lines it has, its
    expected output included: an example that starts where the one before it ends is part of the
    same block, and only a block's first example needs the blank line."""
    ended = None
    for start, length in spans:
        if start != ended and start > 0 and lines[start - 1].strip():
            return start + 1
        ended = start + length
    return None


def _inspected(text: str | None) -> _Docstring:
    """What the docstring `text` (cleaned, None for none) has of examples and what is wrong with them."""
    if text is None:
        return _Docstring(False)
    lines = text.split("\n")
    literal = _literal_block(lines)
    if ">>>" not in text:  # the parser finds nothing without it, and importing doctest is slow
        return _Docstring(literal)
    import doctest  # here, not at the top: it imports pdb and unittest, and most files need no parse

    try:
        found = doctest.DocTestParser().get_examples(text)
    except ValueError as error:  # the parser says which line, and why
        return _Docstring(True, str(error))
    bare = _spaced([(each.lineno, each.source.count("\n") + each.want.count("\n")) for each in found], lines)
    problem = f"the doctest block at line {bare} of the docstring has no blank line before it" if bare else ""
    return _Docstring(literal or bool(found), problem)


def examples(source: str) -> tuple[Finding, ...]:
    """bh-02's example rule over the text of a startup file: for each function and class it tells, an
    example in its docstring (a doctest block, or a ``::`` literal block) and doctest blocks that
    parse, each with a blank line before it. A function with no docstring has no example. Nothing
    of `source` is executed.

    Raises:
        SyntaxError: `source` is not Python.
    """
    found: list[Finding] = []
    for name, node in _told(ast.parse(source)).items():
        seen = _inspected(ast.get_docstring(node))
        if not seen.example:
            found.append(Finding(name, node.lineno, "example", _NO_EXAMPLE))
        if seen.problem:
            found.append(Finding(name, node.lineno, "doctest", seen.problem))
    return tuple(found)


def _rows(code: str, node: _Definition) -> range:
    """The lines a ruff finding of `code` about `node` is on: the definition's own line for a missing
    docstring, the docstring's lines for any other."""
    if code in {"D101", "D103"}:
        return range(node.lineno, node.lineno + 1)
    first = node.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return range(first.lineno, (first.end_lineno or first.lineno) + 1)
    return range(0)


def ruff_findings(source: str, report: str) -> tuple[Finding, ...]:
    """The findings in ruff's JSON `report` of `source` (`--output-format json`) about a function or
    class the file tells, and only those: a private function's, a method's and the module's docstring
    are not in the convention. Found by line, since ruff names none.

    Raises:
        SyntaxError: `source` is not Python.
        ValueError: `report` is not a JSON list.
    """
    told = _told(ast.parse(source))
    reported = json.loads(report)
    if not isinstance(reported, list):
        raise ValueError("ruff's report is not a list of findings")
    found: list[Finding] = []
    for each in reported:
        match each:
            case {"code": str() as code, "location": {"row": int() as row}, "message": str() as message}:
                found += [
                    Finding(name, row, code, message)
                    for name, node in told.items()
                    if code in RUFF_CODES and row in _rows(code, node)
                ]
            case _:
                pass
    return tuple(found)


def summary(findings: Iterable[Finding]) -> str:
    """The one line ``--json`` prints: each name that misses and its codes in `CODES` order, a
    name once, in the order its first finding came. Codes only: a message may quote the file."""
    codes: dict[str, set[str]] = {}
    for each in findings:
        codes.setdefault(each.name, set()).add(each.code)
    misses = [[name, [code for code in CODES if code in these]] for name, these in codes.items()]
    return json.dumps({"misses": misses})


def _read(name: str) -> str:
    """The text of FILE (``-`` is stdin), without a UTF-8 byte order mark, as Python reads a file."""
    if name == "-":
        return sys.stdin.buffer.read().decode("utf-8-sig")
    return Path(name).read_text(encoding="utf-8-sig")


def _ruffed(source: str, name: str) -> tuple[Finding, ...]:
    """Ruff over `source` with bh-02's flags only, on stdin, under the name `name` (which only
    ruff's own naming rules look at, not a file).

    Raises:
        RuntimeError: ruff did not run, or did not report.
    """
    ran = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *RUFF_FLAGS, "--output-format", "json"]
        + [f"--stdin-filename={name}", "-"],
        input=source,
        capture_output=True,
        encoding="utf-8",
        timeout=_RUFF_S,
        check=False,
    )
    if ran.returncode not in {0, 1}:  # 1 is findings; 2 is ruff's own failure
        raise RuntimeError("ruff did not run")
    return ruff_findings(source, ran.stdout)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="startup_check",
        description="Check the docstrings of the functions and classes a startup file tells: an example, "
        "and doctest blocks that parse with a blank line before them. Runs none of the file's code. "
        "Exits 1 on a finding, 0 on none, 2 when a file could not be checked.",
    )
    parser.add_argument("files", nargs="+", metavar="FILE", help="a startup file, or - for its text on stdin")
    parser.add_argument("--ruff", action="store_true", help="also run ruff with bh-02's flags only")
    parser.add_argument("--json", action="store_true", help="print one line of JSON, codes only (one FILE)")
    parser.add_argument("--name", help="the name of the text on stdin")
    return parser


def main(argv: Sequence[str]) -> int:
    """Check the files `argv` names (see the module's docstring) and return the exit status:
    2 if any could not be checked, else 1 if any has a finding, else 0."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.json and len(args.files) != 1:
        parser.error("--json takes one FILE")
    status = 0
    for name in args.files:
        shown = args.name or name
        try:
            source = _read(name)
            found = (*examples(source), *(_ruffed(source, shown) if args.ruff else ()))
        except (
            OSError,
            UnicodeDecodeError,
            SyntaxError,
            ValueError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as error:
            print(f"{shown}: could not be checked ({type(error).__name__}: {error})", file=sys.stderr)
            status = 2
            continue
        if args.json:
            print(summary(found))
        else:
            ordered = sorted(found, key=lambda each: (each.line, CODES.index(each.code)))
            for each in ordered:
                print(f"{shown}:{each.line}: {each.code} {each.name}: {each.message}")
        if found and status == 0:
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

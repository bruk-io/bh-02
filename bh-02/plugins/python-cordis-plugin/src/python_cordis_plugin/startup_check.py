"""A startup file's docstrings and types against decision-0006's convention: the program that checks them.

Run by path (``python -I startup_check.py [--ruff] [--mypy] [--cache-dir DIR] [--json] [--name NAME]
FILE...``), never imported by the Python process or by the command line: importing
``python_cordis_plugin`` runs its ``__init__``, which imports cordis, and this file imports the standard
library and nothing else, so the same text runs in a jail and under ``bh-02 check-examples`` without
either importing the package. It reads the text it is given and executes none of it.

The pure core takes the text of a file and returns findings (`Finding`). It looks at the functions and
classes the file tells (decision-0006's point 1, decided here from the syntax: the public ones the file
defines, or exactly the ones its literal ``__all__`` names; the Python process decides it from the live
objects, and the host takes the names both agree on):

- `examples` is bh-02's own rule, for what ruff has none for: an example in the docstring (a doctest
  block or a ``::`` literal block, code `example`), and doctest blocks that parse and have a blank
  line before them (code `doctest`). The blank line after one can't be checked: `doctest` reads
  everything up to it as the expected output.
- `ruff_findings` reads ruff's JSON report for the rules ruff does have (`RUFF_CODES`: a docstring on a
  public function and class, a summary line, none empty) and keeps those that are about a told name.
- `mypy_findings` reads mypy's JSON report of the whole file (``--strict``: every function annotated, and
  the file type-checks) and gives each error to the told function or class it is in, by line; one outside
  every told definition (an import, a statement, a private function) is `ELSEWHERE`'s.

The shell runs them. With no flag it runs the example rule, prints one line per finding to stdout, and
exits 1 on a finding, 0 on none, and 2 when a file could not be checked (a usage error, a file that is
not readable or not Python). ``--ruff`` also runs ruff, as ``sys.executable -m ruff`` with bh-02's flags
only (`RUFF_FLAGS`), over the file's text on stdin, so no ruff configuration the model could write
loosens it. ``--mypy`` also runs mypy, as ``sys.executable -I -m mypy`` with bh-02's flags only
(`MYPY_FLAGS`: ``--strict`` and no configuration file, which could name plugins mypy imports), over a
copy of the text in a directory of its own under the temporary directory (the jail's scratch), run in
that directory with no ``MYPY*`` variable in its environment: so mypy finds exactly the modules the Python
process can import (its ``-I`` leaves out the working directory and the file's own), and nothing the
project holds. ``--cache-dir`` is where mypy keeps its cache, which makes a repeat cheap (about 0.2 s
against several seconds); without it, or when mypy can't use it, mypy runs with no cache. ``--json``
prints one line, ``{"misses": [[name, [code, ...]], ...]}`` (a code, never a message), for the host to
read as data. A FILE of ``-`` is the text on stdin, named by ``--name`` (the person's startup file, which a
jail can't read, is handed in that way).
"""

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CODES",
    "ELSEWHERE",
    "MYPY_CODES",
    "MYPY_FLAGS",
    "RUFF_CODES",
    "RUFF_FLAGS",
    "Finding",
    "examples",
    "main",
    "mypy_findings",
    "ruff_findings",
    "summary",
]

# What ruff checks (decision-0006 point 7): a docstring on each public function and class, a summary
# line, none empty. ruff calls public what point 1 tells: no leading underscore, and only the names in
# `__all__` when the file has one.
RUFF_CODES = ("D101", "D103", "D205", "D415", "D419")
# mypy's error codes (`mypy.errorcodes.error_codes`, on the mypy pyproject.toml pins; a test compares the two,
# so a mypy that adds one fails there). Closed, as every code the host is told is: a code is a name from a
# list, never a message, which quotes the file. An error with a code not here, or with none, is `mypy`.
MYPY_CODES = tuple(
    """
    abstract annotation-unchecked arg-type assert-type assignment attr-defined await-not-async call-arg
    call-overload comparison-overlap deprecated dict-item empty-body exhaustive-match exit-return
    explicit-any explicit-override func-returns-value has-type ignore-without-code import
    import-not-found import-untyped index list-item literal-required maybe-unrecognized-str-typeform
    metaclass method-assign misc mutable-override name-defined name-match narrowed-type-not-subtype
    no-any-return no-any-unimported no-overload-impl no-redef no-untyped-call no-untyped-def
    nonetype-type operator overload-cannot-match overload-overlap override possibly-undefined
    prop-decorator redundant-cast redundant-expr redundant-self return return-value safe-super
    str-bytes-safe str-format str-unpack syntax top-level-await truthy-bool truthy-function
    truthy-iterable type-abstract type-arg type-var typeddict-item typeddict-readonly-mutated
    typeddict-unknown-key unimported-reveal union-attr unreachable untyped-decorator unused-awaitable
    unused-coroutine unused-ignore used-before-def valid-newtype valid-type var-annotated
    """.split()  # noqa: SIM905 (78 names a line each, as a list, is noise)
)
_MYPY_OTHER = "mypy"  # the code of an error whose own is not in `MYPY_CODES`
# bh-02's rule's own codes after ruff's, then mypy's: the order a finding's codes are told in
CODES = (*RUFF_CODES, "example", "doctest", *MYPY_CODES, _MYPY_OTHER)
# The name of what is not a told function or class: an import, a statement, a private function. No
# function can have it, so it is no told name.
ELSEWHERE = "<file>"
# bh-02's flags only: --isolated ignores every configuration file, which the model can write
RUFF_FLAGS = ("--isolated", "--no-fix", "--select", ",".join(RUFF_CODES))
# bh-02's flags only: --strict is the checks, and --config-file= (empty) reads no configuration file: not the
# project's, not the person's (``~/.mypy.ini``, ``$XDG_CONFIG_HOME/mypy/config``), which can name plugins
# mypy imports. This is the line to run by hand, in CI and in a pre-commit hook.
MYPY_FLAGS = ("--strict", "--config-file=")
_MYPY_REPORT = ("--output", "json")  # one JSON object a line, with the error code: nothing to parse
_RUFF_S = 20.0  # how long ruff gets: it takes milliseconds, and a hang must not hold up a REPL
_MYPY_S = 90.0  # mypy, cold, on a file that imports a big typed library (textual) takes 13 s; warm, 0.3 s
_COPY = "bh_startup.py"  # the file mypy checks: a copy of the text, alone in a directory of its own
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


def _span(node: _Definition) -> range:
    """The lines of a definition, its decorators' first: an error mypy reports on a decorated function
    can be on a decorator."""
    first = min((each.lineno for each in node.decorator_list), default=node.lineno)
    return range(min(first, node.lineno), (node.end_lineno or node.lineno) + 1)


def mypy_findings(source: str, report: str, file: str) -> tuple[Finding, ...]:
    """The errors in mypy's `--output json` `report` (one JSON object a line) of the file `file`, whose
    text is `source`: each is the finding of the function or class the file tells that its line is in (a
    method's is its class's), else of `ELSEWHERE`, an import, a statement or a private function being no
    told name. A note, an error in another file and a line that is not an error are not findings. The
    code is mypy's when `MYPY_CODES` has it, else `mypy` (an error with no code of its own, or a mypy
    that has more codes than this knows), so no text of the file or of mypy's reaches the host as a code.

    Raises:
        SyntaxError: `source` is not Python.
        ValueError: a line of `report` is not JSON.
    """
    told = _told(ast.parse(source))
    found: list[Finding] = []
    for text in report.splitlines():
        if not text.strip():
            continue
        match json.loads(text):
            case {
                "file": str() as where,
                "line": int() as line,
                "severity": "error",
                "message": str() as message,
                "code": str() | None as code,
            } if where == file:
                owner = next((name for name, node in told.items() if line in _span(node)), ELSEWHERE)
                found.append(Finding(owner, line, code if code in MYPY_CODES else _MYPY_OTHER, message))
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


def _caches(cache: str | None) -> tuple[str, ...]:
    """The cache directories mypy is tried with, in order: `cache` (absolute) when there is one, then none
    (`os.devnull` is how mypy is told to keep no cache). A cache mypy can't use (a file in it damaged, a
    directory it can't write) makes it crash, and with none it still checks, cold."""
    return (cache, os.devnull) if cache else (os.devnull,)


def _scrubbed(environ: Mapping[str, str]) -> dict[str, str]:
    """`environ` without the variables that change what mypy checks or where it keeps its cache
    (``MYPYPATH``, ``MYPY_CACHE_DIR``, ``MYPY_NUM_WORKERS``): a startup file runs in the Python process, and
    can set them before this runs."""
    return {name: value for name, value in environ.items() if not name.startswith("MYPY")}


def _mypied(source: str, cache: str | None) -> tuple[Finding, ...]:
    """Mypy over `source` with bh-02's flags only (`MYPY_FLAGS`): a copy of the text alone in a directory
    of its own (under ``$TMPDIR``, the jail's scratch, and removed after), mypy run there, as
    ``sys.executable -I -m mypy`` and without the working directory or the file's own on its path, and
    with no ``MYPY*`` variable. It searches the interpreter's ``sys.path``, which is what the Python
    process (``-I``, the same interpreter) imports from: a module beside the startup file or in the
    project is not found, as the Python process can't import it. `cache` is mypy's cache directory.

    Raises:
        RuntimeError: mypy did not run, with a cache or without one.
    """
    with tempfile.TemporaryDirectory(prefix="bh-mypy-") as scratch:
        Path(scratch, _COPY).write_text(source, encoding="utf-8")
        for where in _caches(os.path.abspath(cache) if cache else None):
            ran = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "mypy",
                    *MYPY_FLAGS,
                    *_MYPY_REPORT,
                    f"--cache-dir={where}",
                    _COPY,
                ],
                cwd=scratch,
                env=_scrubbed(os.environ),
                capture_output=True,
                encoding="utf-8",
                timeout=_MYPY_S,
                check=False,
            )
            if ran.returncode in {0, 1}:  # 1 is findings; 2 is mypy's own failure
                return mypy_findings(source, ran.stdout, _COPY)
    raise RuntimeError("mypy did not run")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="startup_check",
        description="Check the docstrings of the functions and classes a startup file tells: an example, "
        "and doctest blocks that parse with a blank line before them; with --ruff and --mypy, ruff's "
        "docstring rules and mypy --strict too. Runs none of the file's code. "
        "Exits 1 on a finding, 0 on none, 2 when a file could not be checked.",
    )
    parser.add_argument("files", nargs="+", metavar="FILE", help="a startup file, or - for its text on stdin")
    parser.add_argument("--ruff", action="store_true", help="also run ruff with bh-02's flags only")
    parser.add_argument("--mypy", action="store_true", help="also run mypy --strict with bh-02's flags only")
    parser.add_argument("--cache-dir", help="where mypy keeps its cache (default: none)")
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
            found = (
                *examples(source),
                *(_ruffed(source, shown) if args.ruff else ()),
                *(_mypied(source, args.cache_dir) if args.mypy else ()),
            )
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

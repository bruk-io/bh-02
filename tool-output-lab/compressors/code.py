"""Source code as a tree of line ranges, through ast-grep, for `compressors.tree.fold_tree`.

A node is anything with a body: a class, function or method, and the compound blocks inside them
(if, for, while, try, with, match, and their else and except clauses), plus literals that span
many lines (objects, arrays, dicts). Its header runs from its first line, decorators included, to
where its body starts, or through that line when the body opens on it (`function f() {`); a
Python docstring's first line stays in the header. Nothing here is language-specific beyond the
names of body-like node kinds, so every language ast-grep parses works the same way.
"""

from collections.abc import Iterator
from pathlib import Path

from ast_grep_py import SgNode, SgRoot

from compressors.common import split_lines
from compressors.tree import Node, TreeFold, fold_tree

_BODY_KINDS = frozenset(
    {
        "block",  # python, rust (fn bodies), go
        "statement_block",  # javascript, typescript
        "class_body",  # javascript, typescript, java
        "declaration_list",  # rust impl/mod, c#
        "field_declaration_list",  # rust struct, c/c++ struct
        "compound_statement",  # c, c++
        "enum_body",
        "enum_variant_list",
        "interface_body",
        "object_type",
        "switch_body",
        "match_block",
        "body_statement",  # ruby
        "do_block",
        "literal_value",  # go composite literals
    }
)
_LITERAL_KINDS = frozenset(
    {"object", "array", "dictionary", "list", "set", "tuple", "jsx_element", "string", "template_string"}
)
_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".mts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".swift": "swift",
    ".php": "php",
    ".scala": "scala",
    ".lua": "lua",
}


def language_for(path: str) -> str | None:
    return _LANGUAGES.get(Path(path).suffix.lower())


def _body_of(node: SgNode) -> SgNode | None:
    for child in node.children():
        if child.is_named() and child.kind() in _BODY_KINDS:
            return child
    return None


def _header_end(node: SgNode, body: SgNode, lines: list[str]) -> int:
    start = body.range().start
    text_before = lines[start.line][: start.column] if start.line < len(lines) else ""
    end = start.line if text_before.strip() else start.line - 1
    end = max(end, node.range().start.line)
    first = next((c for c in body.children() if c.is_named()), None)
    if first is not None and first.kind() == "expression_statement":
        inner = next((c for c in first.children() if c.is_named()), None)
        if inner is not None and inner.kind() == "string":
            end = max(end, first.range().start.line)
    return end


def _named(node: SgNode) -> Iterator[SgNode]:
    return (c for c in node.children() if c.is_named())


def _nodes(root: SgNode, lines: list[str]) -> list[Node]:
    """The foldable nodes among `root`'s descendants, nearest first.

    A syntax node with a body (a function, a class, a block) or a multi-line literal is a node, its
    own foldable descendants its children; any other multi-line syntax node is looked through.
    Iterative, since an `else if` chain nests one level per branch and generated code has hundreds.
    """
    top: list[Node] = []
    # a frame: the syntax children left to visit, where their nodes go, and the node they become
    # children of when the frame closes (None when they belong to the frame below, looked through)
    stack: list[tuple[Iterator[SgNode], list[Node], tuple[int, int, int, list[Node]] | None]] = [
        (_named(root), top, None)
    ]
    while stack:
        pending, collected, parent = stack[-1]
        node = next(pending, None)
        if node is None:
            stack.pop()
            if parent is not None:
                first, head_end, last, dest = parent
                dest.append(Node(first, head_end, last, tuple(collected)))
            continue
        r = node.range()
        if r.end.line == r.start.line:
            continue
        target = node
        if node.kind() == "decorated_definition":  # python: the decorators belong to the header
            inner = node.field("definition")
            target = inner if inner is not None else node
        body = _body_of(target)
        if body is not None:
            head = (r.start.line, _header_end(target, body, lines), r.end.line, collected)
            stack.append((_named(target), [], head))
        elif node.kind() in _LITERAL_KINDS:
            stack.append((_named(node), [], (r.start.line, r.start.line, r.end.line, collected)))
        else:
            stack.append((_named(node), collected, None))
    return top


def _parse(source: str, language: str) -> SgRoot:
    """ast-grep's syntax tree.

    Raises:
        ValueError: ast-grep has no grammar for `language` (it panics, and a pyo3 panic is not an
            Exception, so nothing upstream would catch it).
    """
    try:
        return SgRoot(source, language)
    except BaseException as e:  # only the one panic is translated; the rest re-raise
        if type(e).__module__ != "pyo3_runtime" or "LanguageNotSupported" not in str(e):
            raise
        known = ", ".join(sorted(set(_LANGUAGES.values())))
        raise ValueError(
            f"--lang {language}: ast-grep has no grammar by that name; use one of {known}, "
            "or another language ast-grep supports"
        ) from None


def code_tree(source: str, language: str) -> tuple[Node, ...]:
    """The source's foldable nodes: definitions, blocks and multi-line literals, nested. A language
    ast-grep has no grammar for raises ValueError, from `_parse`."""
    return tuple(_nodes(_parse(source, language).root(), split_lines(source)))


def fold_code(
    source: str, language: str, budget_tokens: int, terms: frozenset[str] = frozenset()
) -> TreeFold:
    """The outline of a source file, opened as far as the budget allows, with real line numbers;
    definitions that hold a query term (few others do) open first. A language ast-grep has no
    grammar for raises ValueError, from `_parse`."""
    lines = split_lines(source)
    text, opened, folded = fold_tree(
        lines, code_tree(source, language), budget_tokens, numbered=True, terms=terms
    )
    return TreeFold(text, source, opened, folded)

"""Print a file's outline with its real line numbers: the fold as a tool Claude can call.

    ./lab outline FILE [--budget 4000]

Source code goes through ast-grep (every class, function and block header, opened as far as the
budget allows), XML through its element tree, indentation outlines through their nesting. Each
`[... lines A-B folded]` marker names lines left out, for `Read` with offset A and limit B-A+1.
The probes found Claude already builds outlines like this with grep; this is the version that
handles multi-line signatures, docstrings, nesting and every language ast-grep parses.
"""

import argparse
import sys
from pathlib import Path

from compressors.code import fold_code, language_for
from compressors.common import estimate_tokens
from compressors.tree import fold_outline, fold_tree, fold_xml, looks_like_outline, looks_like_xml


def outline(path: str, text: str, budget: int) -> str:
    """The outline of one file's text; the whole text when it already fits the budget."""
    if estimate_tokens(text) <= budget:
        lines = text.splitlines()
        return fold_tree(lines, (), budget)[0]  # numbered, nothing to fold
    language = language_for(path)
    if language is not None:
        return fold_code(text, language, budget).text
    if looks_like_xml(text):
        fold = fold_xml(text, budget)
        if fold is not None:
            note = "" if fold.source == text else "(pretty-printed: line numbers refer to the pretty text)\n"
            return note + fold.text
    if looks_like_outline(text.splitlines()):
        return fold_outline(text, budget).text
    raise ValueError(f"{path}: no outline for this kind of file; read it in pages with Read offset and limit")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("file")
    parser.add_argument("--budget", type=int, default=4000, help="tokens (default 4000)")
    ns = parser.parse_args(argv)
    try:
        print(outline(ns.file, Path(ns.file).read_text(encoding="utf-8", errors="replace"), ns.budget))
    except (OSError, ValueError) as e:
        print(f"outline: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

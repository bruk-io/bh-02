"""fold: show the shape of a large text in a token budget, and say where the rest is.

    ./lab fold FILE [--budget 2000] [--query WORDS] [--as FORMAT] [--lang LANG] [--save PATH]
    COMMAND | ./lab fold [-] ...

Source code (by extension, or --lang for stdin) folds through ast-grep: every class, function and
block header with its real line number, opened as far as the budget allows. Other text folds by
what it is: JSON (long arrays keep head, tail and the items that stand out), XML (by element,
pretty-printed first when packed), indentation outlines such as accessibility snapshots (by
nesting), HTML (to text), logs (repeated lines collapsed, head, tail and windows around error
words) or plain text (head and tail). Each marker says what it hides: a JSON path, or a line or
character range, so `jq`, `sed -n 'A,Bp'` or Read with offset and limit fetch exactly that.

Text that already fits the budget is printed unchanged. --query keeps in view the array items,
siblings and log lines that hold those words (words that most items share are ignored). When the
line numbers refer to a pretty-printed copy rather than the input (packed XML), --save writes
that copy, and the header says so. The first line of output is a header, unless --quiet.
"""

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from compressors.code import fold_code, language_for
from compressors.common import estimate_tokens, query_words, read_text
from compressors.route import fold

FORMATS = ("auto", "code", "json", "xml", "html", "outline", "lines", "text")


@dataclass(frozen=True)
class Result:
    text: str  # the folded view, header included unless quiet; the input itself when it passed through
    source: str | None  # the text the line numbers refer to, when it is not the input
    branch: str | None  # what folded it: code, json, xml, html, outline, lines or text; None if nothing did
    language: str | None = None  # the language, when the branch is code


def fold_text(
    text: str,
    *,
    budget: int,
    path: str = "",
    fmt: str = "auto",
    lang: str | None = None,
    query: str = "",
    quiet: bool = False,
) -> Result:
    """The folded view of `text`; pure, so the CLI's behaviour is testable without files.

    Text within the budget passes through. Text over it folds by its structure; when that saves
    under 10%, it is cut by characters; when even that saves under 10%, it is shown whole, since
    hiding a tenth would cost more to recover than it saves (`branch` is None, as for text that fits).

    Raises:
        ValueError: `fmt` is "code" but no language is known from --lang or the path; `fmt` names a
            format the text cannot take (JSON that does not parse, XML that is not well formed).
    """
    raw_tokens = estimate_tokens(text)
    if raw_tokens <= budget:
        return Result(text, None, None)
    terms = query_words(query)
    language = lang or (language_for(path) if path else None)
    if fmt == "code" and language is None:
        raise ValueError("--as code needs a language: pass --lang python (or typescript, rust, go, ...)")
    if fmt in ("auto", "code") and language is not None:
        tree = fold_code(text, language, budget, terms)
        body, branch, source = tree.text, "code", None
    else:
        folded = fold(text, budget_tokens=budget, terms=terms, force=None if fmt == "auto" else fmt)
        if folded is None:  # the structured fold saved too little: cut by characters instead
            folded = fold(text, budget_tokens=budget, terms=terms, force="text")
        if folded is None:
            return Result(text, None, None)
        body, branch, source = folded.body, folded.branch, folded.source
    result = Result(body, source, branch, language if branch == "code" else None)
    if quiet:
        return result
    where = (
        "line numbers refer to the pretty-printed copy"
        if source is not None
        else "line numbers refer to the input"
    )
    kind = f"code ({language})" if branch == "code" else branch
    header = f"[fold: {kind}, ~{raw_tokens} -> ~{estimate_tokens(body)} tokens; {where}]"
    return replace(result, text=f"{header}\n{body}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fold", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("file", nargs="?", default="-", help="a file, or - (the default) for stdin")
    parser.add_argument("--budget", type=int, default=2000, help="tokens to fold into (default 2000)")
    parser.add_argument("--query", default="", help="words whose items, siblings or lines to keep in view")
    parser.add_argument(
        "--as", dest="fmt", choices=FORMATS, default="auto", help="the format, when detection guesses wrong"
    )
    parser.add_argument(
        "--lang", help="the source language for code read from stdin (python, typescript, ...)"
    )
    parser.add_argument(
        "--save", type=Path, help="where to write the pretty-printed copy the line numbers refer to"
    )
    parser.add_argument("--quiet", action="store_true", help="no header line")
    ns = parser.parse_args(argv)
    try:
        if ns.file == "-":  # bytes, decoded: no newline translation, so line numbers match sed's
            text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        else:
            text = read_text(ns.file)
        result = fold_text(
            text,
            budget=ns.budget,
            path="" if ns.file == "-" else ns.file,
            fmt=ns.fmt,
            lang=ns.lang,
            query=ns.query,
            quiet=ns.quiet,
        )
        if result.source is not None and ns.save is not None:
            ns.save.write_text(result.source, encoding="utf-8")
        print(result.text)
    except (OSError, ValueError) as e:
        print(f"fold: {e}", file=sys.stderr)
        return 1
    except BrokenPipeError:  # `fold x | head` closed the pipe early: not an error
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

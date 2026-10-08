"""MkDocs hooks for the documentation site (`mkdocs.yml` names this file).

- `on_config`: the branch and short commit the site is built from, for the status bar
  (`config.extra["git"]`), read from git; empty when git can't say.
- `on_page_markdown`: the READMEs a page includes link to repository files. Once the include
  plugin has made each link relative to the page, a link to a file a page includes goes to that
  page, and any other link out of `docs/` goes to the file on GitHub. Two GitHub habits are
  made to read the same under Python-Markdown: a list straight after a paragraph's last line
  (GitHub starts the list; Python-Markdown would fold it into the paragraph) gets a blank line
  before it, and a pipe in a table cell's code, escaped for GitHub (`\\|`), loses its backslash
  (Python-Markdown never splits a cell inside code, and would show it).
"""

import os
import re
import subprocess
from collections.abc import Mapping, Set
from pathlib import Path, PurePosixPath

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

_INCLUDE = re.compile(r'\{%\s*include-markdown\s+"([^"]+)"')
_FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.M | re.S)
_LINK = re.compile(r"(\]\()([^)\s]+)(\))")
_TABLE_ROW = re.compile(r"^\|.*$", re.M)
_ITEM = re.compile(r"(?:[-*+]|\d+[.)]) ")  # a list item's marker
_INTERRUPTS = re.compile(r"(?:[-*+]|1[.)]) ")  # one that may start a list inside a paragraph
_CODE = re.compile(r"`[^`\n]*`")


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    root = Path(config.config_file_path).parent
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    commit = _git(root, "rev-parse", "--short", "HEAD")
    config.extra["git"] = {"branch": branch, "commit": commit}
    return config


def on_page_markdown(markdown: str, *, page: Page, config: MkDocsConfig, files: Files) -> str:
    root = Path(config.config_file_path).parent
    docs = Path(config.docs_dir).resolve().relative_to(root.resolve()).as_posix()
    src = page.file.src_uri
    pages = _included({f.src_uri: f.content_string for f in files.documentation_pages()}, docs)
    targets = (_repo_path(src, match[2], docs) for match in _LINK.finditer(markdown))
    folders = {target for target in targets if (root / target).is_dir()}
    return _rewritten(markdown, src, docs, pages, (config.repo_url or "").rstrip("/"), folders)


def _included(sources: Mapping[str, str], docs: str) -> dict[str, str]:
    """Each repository file a page includes (`include-markdown`), relative to the repository's
    root, mapped to the first page under `docs` that includes it (`sources`: each page's
    path under `docs` and its text)."""
    pages: dict[str, str] = {}
    for src, text in sources.items():
        for name in _INCLUDE.findall(text):
            pages.setdefault(_normal(PurePosixPath(docs, src).parent / name), src)
    return pages


def _repo_path(src: str, target: str, docs: str) -> str:
    """A link's target, relative to the repository's root, from the page `src` under `docs`."""
    return _normal(PurePosixPath(docs, src).parent / target.partition("#")[0])


def _rewritten(
    markdown: str, src: str, docs: str, pages: Mapping[str, str], repo: str, folders: Set[str]
) -> str:
    """`markdown` with each relative link that leaves `docs` pointed at the page that includes
    its file (or a folder's README.md), else at the file on GitHub under `repo` (`folders` are
    the targets that are directories); a list after a paragraph's line set apart from it, and a
    table cell's code without GitHub's escaped pipes. Fenced code is left as it is."""

    def link(match: re.Match[str]) -> str:
        path, _, fragment = match[2].partition("#")
        if not path or "://" in path or path.startswith(("/", "mailto:")):
            return match[0]
        target = _repo_path(src, path, docs)
        if target == docs or target.startswith((f"{docs}/", "../")):
            return match[0]
        anchor = f"#{fragment}" if fragment else ""
        page = pages.get(target) or pages.get(f"{target}/README.md")
        if page is not None:
            return f"]({os.path.relpath(page, PurePosixPath(src).parent)}{anchor})"
        kind = "tree" if target in folders else "blob"
        return f"]({repo}/{kind}/main/{target}{anchor})"

    def unescaped(code: re.Match[str]) -> str:
        return code[0].replace("\\|", "|")

    def prose(text: str) -> str:
        text = _TABLE_ROW.sub(lambda row: _CODE.sub(unescaped, row[0]), _lists_apart(text))
        return _LINK.sub(link, text)

    pieces, at = [], 0
    for fence in _FENCE.finditer(markdown):
        pieces += [prose(markdown[at : fence.start()]), fence[0]]
        at = fence.end()
    return "".join([*pieces, prose(markdown[at:])])


def _lists_apart(text: str) -> str:
    """A blank line before each list that starts on the line after a paragraph's (one that is not
    part of a list item already), where GitHub starts a list and Python-Markdown would not."""
    lines: list[str] = []
    in_item = False  # whether the block since the last blank line began as a list item
    for line in text.split("\n"):
        if not lines or not lines[-1].strip():
            in_item = bool(_ITEM.match(line.lstrip()))
        elif _INTERRUPTS.match(line) and not in_item and not lines[-1].startswith("|"):
            lines.append("")
            in_item = True
        lines.append(line)
    return "\n".join(lines)


def _normal(path: PurePosixPath) -> str:
    return os.path.normpath(path).replace(os.sep, "/")


def _git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=10
        )
    except OSError, subprocess.SubprocessError:
        return ""
    return done.stdout.strip()

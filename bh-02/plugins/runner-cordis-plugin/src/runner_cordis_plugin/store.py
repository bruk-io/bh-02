"""The always-grants of a project (decision-0012 item 3): `grants.toml` in the project's grants
directory (`host.grants`, `$XDG_STATE_HOME/bh-02/projects/<project>/grants/`, made at 0700 by the
command line before any jail starts and masked from every jail by `spec_for`).

The file holds the requests the person answered `always`, nothing else: `once` and `no` live in
memory, for the session. It is read and written only through `host_paths` (`read_beneath`,
`write_beneath`: through no link, whole or not at all, 0600), because a jail may share a parent with
it and a link there must never lead bh-02 anywhere. A file that is not what is described here is
refused (`Refused`) and nothing is granted from it: a typo must not quietly widen or drop what the
person approved. What the file holds is shape-checked only; whether a grant is on the floor
(`grants.refusal`) is for whoever applies it, who has the floor.

```toml
[[grant]]
kind = "net"            # read, write, env or net
target = "example.com"  # a path, a variable name, or a host
port = 443              # net only
source = "row"          # who asked: row, input, extension or agent
name = "python"
reason = "fetch packages"
```
"""

import tomllib
from collections.abc import Sequence
from pathlib import Path

from host_paths import Link, read_beneath, write_beneath
from runner_cordis_plugin.grants import Asker, Grant, Invalid, Kind, Request, Source

__all__ = ["FILE", "Refused", "parsed", "read", "rendered", "write"]

FILE = "grants.toml"
_CAP = 1_000_000
_KEYS = frozenset({"kind", "target", "port", "source", "name", "reason"})


class Refused(ValueError):
    """The store can't be used as it is; the message says what to fix. Nothing is granted from it."""


def rendered(requests: Sequence[Request]) -> str:
    """`requests` as the text of `grants.toml`, each once (the first of equal grants), in order."""
    seen: dict[Grant, Request] = {}
    for request in requests:
        seen.setdefault(request.grant, request)
    blocks = []
    for request in seen.values():
        grant, asker = request.grant, request.asker
        lines = ["[[grant]]", f"kind = {_quoted(grant.kind)}", f"target = {_quoted(grant.target)}"]
        if grant.kind is Kind.NET:
            lines.append(f"port = {grant.port}")
        lines += [
            f"source = {_quoted(asker.source)}",
            f"name = {_quoted(asker.name)}",
            f"reason = {_quoted(request.reason)}",
        ]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _quoted(text: str) -> str:
    """`text` as a TOML basic string: quotes, backslashes and control characters escaped."""
    out = ['"']
    for char in str(text):
        if char in '"\\':
            out.append("\\" + char)
        elif char < " " or char == "\x7f":
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    return "".join(out) + '"'


def parsed(text: str, source: str) -> tuple[Request, ...]:
    """The requests `text` (the file at `source`) holds, each once, in order.

    Raises:
        Refused: it is not TOML, or an entry is not a valid grant with who asked and why.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise Refused(
            f"{source} is not TOML ({error}); fix it, or remove it to forget every always-grant"
        ) from None
    entries = data.get("grant", [])
    if set(data) - {"grant"} or not isinstance(entries, list):
        raise Refused(f"{source} holds `[[grant]]` tables alone; fix it, or remove it")
    found: dict[Grant, Request] = {}
    for number, entry in enumerate(entries, start=1):
        request = _request(entry, f"{source}, grant {number}")
        found.setdefault(request.grant, request)
    return tuple(found.values())


def _request(entry: object, where: str) -> Request:
    if not isinstance(entry, dict) or set(entry) - _KEYS:
        raise Refused(f"{where} must be a table of {', '.join(sorted(_KEYS))}; fix it, or remove the entry")
    try:
        grant = Grant(Kind(_text(entry, "kind")), _text(entry, "target"), _port(entry))
        asker = Asker(Source(_text(entry, "source")), _text(entry, "name"))
        return Request(grant, asker, _text(entry, "reason"))
    except (Invalid, ValueError) as error:
        raise Refused(f"{where}: {error}; fix it, or remove the entry") from None


def _text(entry: dict[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str):
        raise Invalid(f"`{key}` must be text")
    return value


def _port(entry: dict[str, object]) -> int:
    value = entry.get("port", 0)
    if type(value) is not int:
        raise Invalid("`port` must be a whole number")
    return value


def read(directory: Path) -> tuple[Request, ...]:
    """The always-grants kept in `directory`: none when there is no file yet.

    Raises:
        Refused: the file is a link, is not a regular file, is too large, can't be read, or
            `parsed` refuses it.
    """
    where = str(directory / FILE)
    try:
        found = read_beneath(directory, [FILE], cap=_CAP)
    except FileNotFoundError:
        if directory.is_dir():
            return ()
        raise Refused(
            f"the grants directory {directory} is not there; bh-02 makes it at start, so run bh-02 again"
        ) from None
    except OSError as error:
        raise Refused(f"can't read {where} ({error}); fix it, or remove it") from None
    if isinstance(found, Link):
        raise Refused(f"{where} is a link (to {found.target}), which is not followed; replace it with a file")
    try:
        text = found.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused(f"{where} is not UTF-8 text; fix it, or remove it") from None
    return parsed(text, where)


def write(directory: Path, requests: Sequence[Request]) -> None:
    """Keep `requests` (the always-grants, all of them) in `directory`, whole or not at all, 0600,
    through no link.

    Raises:
        Refused: the file is a link or not a regular file, or can't be written.
    """
    try:
        write_beneath(directory, [FILE], rendered(requests).encode("utf-8", errors="replace"))
    except OSError as error:
        raise Refused(f"can't write {directory / FILE} ({error}); fix it, or remove it") from None

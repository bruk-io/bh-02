"""What an OpenAI-compatible endpoint's `GET <base_url>/models` says, as the models `ENDPOINT/ID`
can name. Everything here is pure: the URL asked, the reply read (`read_listing`), the filter an
endpoint's `include` makes (`matching`), and the lines that say what the list leaves out
(`notes`). `discovery.py` asks the server and keeps what it said.

An id is the server's text, so it is held to what a name can be before it is listed: control
characters are stripped, and what remains must be 1 to 200 printable ASCII characters without a
space (`usable`). A space can't be typed in `/model NAME`, one word; and a character outside the
Basic Multilingual Plane would make a layer file invalid TOML when `/model` writes the name into it
(cordis's `format_layer` writes it as a surrogate-pair escape, which TOML does not allow). An id
that is none of that is counted, never listed, and so is an entry that has no id: one line says how
many entries were not listed. An id is only ever a name and the `model` of a
request's body: never a path, never an argument.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Final, assert_never

__all__ = [
    "BODY_LIMIT",
    "KEPT",
    "SHOWN",
    "Down",
    "Listed",
    "Reply",
    "Unlisted",
    "cleaned",
    "matching",
    "models_url",
    "notes",
    "read_listing",
    "usable",
]

SHOWN: Final = 200  # how many of an endpoint's models `/model` lists
KEPT: Final = 2000  # how many of its ids are kept: the rest of a longer list are not
BODY_LIMIT: Final = 1024 * 1024  # how much of a reply is read: a model list is far smaller
_LONGEST: Final = 200
_CONTROL: Final = re.compile(r"[\x00-\x1f\x7f-\x9f]")  # C0, DEL, C1: what a terminal would act on


@dataclass(frozen=True, slots=True)
class Reply:
    """A server's answer: its HTTP status and the body (at most `BODY_LIMIT` bytes)."""

    status: int
    body: bytes


@dataclass(frozen=True, slots=True)
class Down:
    """No answer: `why`, one phrase for the person (the server isn't there, took too long, sent
    more than a list is)."""

    why: str


@dataclass(frozen=True, slots=True)
class Listed:
    """What a server listed: `ids`, the usable ones sorted and each once, at most `KEPT`;
    `skipped`, how many entries of its list gave none (no id at all, or one `usable` refuses: it
    counts entries, not ids); `cut`, how many usable ids past `KEPT`."""

    ids: tuple[str, ...]
    skipped: int = 0
    cut: int = 0


@dataclass(frozen=True, slots=True)
class Unlisted:
    """No list: `why`, one phrase for the person."""

    why: str


def models_url(base_url: str) -> str:
    """Where an endpoint lists its models: its `base_url`, then `/models`."""
    return base_url.rstrip("/") + "/models"


def cleaned(text: str) -> str:
    """`text` without control characters (C0, DEL, C1), as every line shown from a server is."""
    return _CONTROL.sub("", text)


def usable(raw: str) -> str | None:
    """The id `raw` as a name can carry it: its control characters stripped, then kept only when
    1 to 200 printable ASCII characters without a space remain; None otherwise."""
    text = cleaned(raw)
    if not 0 < len(text) <= _LONGEST or not all("!" <= char <= "~" for char in text):
        return None
    return text


def read_listing(got: Reply | Down) -> Listed | Unlisted:
    """The models a server's answer lists, or why it lists none. The OpenAI shape: JSON
    `{"data": [{"id": ...}, ...]}` under a 2xx status. A server's body is never quoted."""
    if isinstance(got, Down):
        return Unlisted(got.why)
    if got.status in (401, 403):
        return Unlisted(
            f"HTTP {got.status}: it wants a key, or refused the one named (`key` names a line of local.env)"
        )
    if got.status == 404:
        return Unlisted("HTTP 404: it has no /models; name its models in tables of their own")
    if 300 <= got.status < 400:
        return Unlisted(
            f"HTTP {got.status}: a redirect, which is not followed (a key never leaves its base_url); "
            "point base_url at where it ends"
        )
    if not 200 <= got.status < 300:
        return Unlisted(f"HTTP {got.status}")
    try:
        data = json.loads(got.body).get("data")
    except ValueError, AttributeError:
        data = None
    if not isinstance(data, list):
        return Unlisted("its answer is not an OpenAI model list (JSON with a `data` list)")
    ids = [item["id"] for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)]
    named = [name for raw in ids if (name := usable(raw)) is not None]
    kept = sorted(set(named))
    return Listed(tuple(kept[:KEPT]), skipped=len(data) - len(named), cut=len(kept[KEPT:]))


def matching(ids: Sequence[str], include: Sequence[str]) -> tuple[str, ...]:
    """The ids an endpoint's `include` lists: those matching any of its patterns (fnmatch's `*`,
    `?` and `[abc]`, case-sensitive, tried on the id, not on `ENDPOINT/ID`); all of them when the
    endpoint has no `include`."""
    if not include:
        return tuple(ids)
    return tuple(name for name in ids if any(fnmatchcase(name, pattern) for pattern in include))


def notes(url: str, found: Listed | Unlisted | None, include: Sequence[str]) -> tuple[str, ...]:
    """What `/model` says of an endpoint besides its models, one line each: why it has none, or
    what its list leaves out (more than `SHOWN`, entries with no id a name can carry, a list cut at `KEPT`, an
    `include` that matches nothing). None when it was never asked."""
    match found:
        case None:
            return ()
        case Unlisted(why):
            return (f"no list from {url} ({why}); its models are not listed",)
        case Listed(ids, skipped, cut):
            shown = matching(ids, include)
            out: list[str] = []
            if not ids and not skipped:
                out.append("its server lists no models")
            elif not shown and ids:
                out.append(f"none of its {len(ids)} models matches include = {list(include)!r}")
            if len(shown) > SHOWN:
                out.append(f'{len(shown) - SHOWN} more not shown; narrow them with include = ["qwen*"]')
            if skipped:
                noun = "entry" if skipped == 1 else "entries"
                out.append(
                    f"{skipped} {noun} not listed: a model here needs an id of printable ASCII without "
                    f"a space, at most {_LONGEST} characters"
                )
            if cut:
                out.append(f"{cut} more ids not kept: only the first {KEPT} of a list are")
            return tuple(out)
        case _ as unreachable:
            assert_never(unreachable)

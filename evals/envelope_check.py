"""Layer 1's check of an envelope: every claim its parts make, against the data and in its text.

Both checks stand apart from the producers' code. Each claim is recomputed from the input with
`evals.schema_check`'s jq-path walker, and a command is run with `jq` itself: a count, the values
a field holds, a row's note, that a list of rows is complete, a sample's text, what a command
prints. And each claim is said in the text of the level that makes it, on one line: a claim the
text does not show is one the model never reads. A shape is also read back line by line
(`schema_check.shape_claims`), for what its field lines say beyond the claims (ranges, medians,
uniqueness).

An envelope of lines (a log, a tree, code, a document) is checked against its source text, the text
its line numbers refer to (`text_problems`), with this module's own line split, template rule and
reading of the clip marker, and its grep commands run with `grep` itself.
"""

import json
import re
import shlex
import shutil
import subprocess
from collections import Counter
from typing import Any

from compressors.config import DEFAULT, SchemaKnobs
from compressors.envelope import (
    ROLES,
    Alike,
    Breaks,
    Claim,
    Count,
    Envelope,
    Fetches,
    Lists,
    Prints,
    Role,
    Shows,
    Total,
    Values,
    Verbatim,
)
from evals.schema_check import MISSING, get, note_claims, shape_claims, walk

_COMMAND = re.compile(r"^jq(?P<slurp> -s)? '(?P<prog>.+)' FILE$")


def said(claim: Claim) -> tuple[tuple[str, ...], ...]:
    """What the level's text must hold for the claim to be said there: each tuple, on one line.

    Raises:
        AssertionError: a kind of claim with no said form (one added without it).
    """
    match claim:
        case Count(at=at, n=n):
            return ((at or ".", str(n)),)
        case Values(field=field, counts=((v, n),)):  # "(all N)", or "N" where other rows hold objects
            return ((field or "(each)", v, str(n)),)
        case Values(field=field, counts=counts):
            return ((field or "(each)", *(f"{v} {n}" for v, n in counts)),)
        case Breaks(row=row, note=note):
            return ((row, note),)
        case Lists():
            return ()  # the rows it names are each a Breaks of their own
        case Verbatim(at=at, text=text):
            return ((at, text),)
        case Fetches(command=command) | Prints(command=command):
            return ((command,),)
        case Shows(first=first, lines=lines):
            return tuple((f"{first + k}: {text}",) for k, text in enumerate(lines))
        case Total(lines=lines, templates=templates):
            return ((f"{lines} line", f"{templates} line template"),)  # "1 line template", "2 line templates"
        case Alike(template=tmpl, n=n, slot=0):  # a template is shown without its indentation
            return ((tmpl.strip(), str(n)),)
        case Alike(template=tmpl, n=n, slot=slot, value=value):
            return ((tmpl.strip(), f"<*>{slot}", value, str(n)),)
        case _ as unreachable:
            raise AssertionError(f"no said form for {unreachable!r}")


def unsaid(env: Envelope) -> list[str]:
    """Each claim no line of its level's text holds."""
    problems = []
    for role in ROLES:
        level = env.level(role)
        lines = [level.head, *level.body]
        for c in level.claims:
            if any(not any(all(w in line for w in want) for line in lines) for want in said(c)):
                problems.append(f"{role}: claims {c!r}, and no line of it says so")
    return problems


def _compact(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def _rows(value: Any, at: str) -> list[Any]:
    return walk(value, f"{at}[]")


def _addresses(value: Any, at: str) -> list[set[str]]:
    """Each row's jq paths (an object keyed by its rows' names is reached either way)."""
    base = walk(value, at)
    if not base:
        return []
    if isinstance(base[0], dict):
        return [{f"{at}[{json.dumps(k)}]", f"{at}.{k}"} for k in base[0]]
    return [{f"{at}[{i}]"} for i in range(len(base[0]))] if isinstance(base[0], list) else []


def _fetches(raw: str, value: Any, c: Fetches, knobs: SchemaKnobs, run_jq: bool) -> list[str]:
    rows = _rows(value, c.at)
    usual = json.loads(c.usual)
    held = sum(1 for r in rows if get(r, c.field) == usual)
    if not rows or held / len(rows) < knobs.dominant:
        return [
            f"{c.command}: selects against {c.usual}, which {held} of {len(rows)} rows hold, not the dominant"
        ]
    m = _COMMAND.match(c.command)
    if m is None:
        return [f"cannot read the command {c.command!r}"]
    if not run_jq or shutil.which("jq") is None:
        return []
    flags = ["-r", "-s"] if m["slurp"] else ["-r"]
    proc = subprocess.run(
        ["jq", *flags, m["prog"]], input=raw, capture_output=True, text=True, timeout=60, check=False
    )
    if proc.returncode != 0:
        return [f"jq rejects {c.command!r}: {proc.stderr.strip()[:200]}"]
    want: list[Any] = [get(r, c.pick) if c.pick else r for r in rows if get(r, c.field) != usual]
    if c.pick:  # one name a line (jq -r)
        got: list[Any] = proc.stdout.splitlines()
        want = [w if isinstance(w, str) else json.dumps(w) for w in want]
    else:  # whole rows, each pretty-printed over many lines: read them back as JSON values
        got = _values(proc.stdout)
    return [] if got == want else [f"{c.command}: prints {len(got)} rows, {len(want)} break {c.usual}"]


def _values(text: str) -> list[Any]:
    """The JSON values in a stream of them, as jq prints them."""
    decoder, out, pos = json.JSONDecoder(), [], 0
    while (pos := len(text) - len(text[pos:].lstrip())) < len(text):
        value, pos = decoder.raw_decode(text, pos)
        out.append(value)
    return out


def wrong(
    raw: str, value: Any, claim: Claim, knobs: SchemaKnobs = DEFAULT.schema, run_jq: bool = True
) -> list[str]:
    """What the data says against one claim (nothing when it holds).

    Raises:
        AssertionError: a kind of claim with no check (one added without it).
    """
    match claim:
        case Count(at=at, n=n):
            has = len(_rows(value, at))
            return [] if has == n else [f"{at or '.'}: says {n} rows, it has {has}"]
        case Values(at=at, field=field, counts=counts):
            held = Counter(
                _json(v)
                for v in (get(r, field) for r in _rows(value, at))
                if v is not MISSING and not isinstance(v, list | dict)
            )
            problems = [f"{at} {field}: says {v} {n}, it is {held[v]}" for v, n in counts if held[v] != n]
            if extra := set(held) - {v for v, _ in counts}:
                problems.append(f"{at} {field}: holds {', '.join(sorted(extra))[:120]} too")
            return problems
        case Breaks(row=row, note=note):
            got = walk(value, row)
            return note_claims(row, got[0], note)[0] if got else [f"{row}: no such row"]
        case Lists(at=at, field=field, usual=usual, rows=listed):
            if "[]" in at:
                return []
            missing = [
                sorted(names)[0]
                for names, r in zip(_addresses(value, at), _rows(value, at), strict=False)
                if (v := get(r, field)) is not MISSING and _json(v) != usual and not names & set(listed)
            ]
            return [f"{at}: {p} holds {field} other than {usual} and is not listed" for p in missing[:5]]
        case Verbatim(at=at, text=text, whole=whole):
            got = walk(value, at)
            if not got:
                return [f"{at}: no such item"]
            full = _compact(got[0])
            ok = full == text if whole else full.startswith(text)
            return [] if ok else [f"{at}: the sample is not the item's text"]
        case Fetches() as c:
            return _fetches(raw, value, c, knobs, run_jq)
        case Shows() | Total() | Alike() | Prints():
            return [f"{claim!r}: a claim about lines, in an envelope of JSON"]
        case _ as unreachable:
            raise AssertionError(f"no check for {unreachable!r}")


def _json(v: Any) -> str:
    """A scalar as JSON text, as the schema module encodes values."""
    return json.dumps(v, ensure_ascii=False)


def problems(
    raw: str, value: Any, env: Envelope, knobs: SchemaKnobs = DEFAULT.schema, run_jq: bool = True
) -> list[str]:
    """Every way the envelope's text or claims fail the data (`run_jq` False: commands not run)."""
    out = unsaid(env)
    for claim in env.claims():
        out += wrong(raw, value, claim, knobs, run_jq)
    out += shape_claims(value, "\n".join(env.level(Role.SHAPE).body))
    return out


# --- envelopes of lines ---------------------------------------------------------------------------------

_WORD = re.compile(r"[A-Za-z0-9_-]+")
_QUOTED_OR_WORD = re.compile(r'"[^"\n]*"|[A-Za-z0-9_-]+')
_CLIP = re.compile(r"\.\.\.\[\+(\d+) chars\]$")


def _lines(source: str) -> list[str]:
    """Lines as sed and grep number them, a trailing carriage return dropped."""
    out = source.split("\n")
    if source.endswith("\n"):
        out = out[:-1]
    return [line.removesuffix("\r") for line in out] if source else []


def _hexy(word: str) -> bool:
    return all(ch in "0123456789abcdefABCDEF" for ch in word)


def _holes(line: str, quoted: bool) -> tuple[str, list[str]]:
    """The line's template, and what its holes hold: each token of letters, digits, `_` and `-` with a
    digit in it or a part of six or more hex digits, and each quoted string when `quoted`."""
    held: list[str] = []

    def hole(m: re.Match[str]) -> str:
        w = m.group()
        parts = w.replace("_", "-").split("-")
        if (
            w.startswith('"')
            or any(ch in "0123456789" for ch in w)
            or any(len(x) >= 6 and _hexy(x) for x in parts)
        ):
            held.append(w)
            return "<*>"
        return w

    return (_QUOTED_OR_WORD if quoted else _WORD).sub(hole, line.rstrip()), held


def _shown(text: str, line: str) -> bool:
    """Whether `text` is the line, or the line cut short by the clip marker."""
    if text == line:
        return True
    m = _CLIP.search(text)
    return m is not None and line.startswith(text[: m.start()]) and len(line) - m.start() == int(m[1])


def _grep(source: str, lines: list[str], command: str, run_tools: bool) -> tuple[list[int] | None, str]:
    """The line numbers a `grep -nF` or `grep -nE` command prints, by grep when there is one and
    run_tools, else by reading the lines; None, and why, when the command is not one of those."""
    try:
        argv = shlex.split(command)
    except ValueError as e:
        return None, f"cannot read the command {command!r}: {e}"
    if len(argv) != 4 or argv[0] != "grep" or argv[1] not in ("-nF", "-nE") or argv[3] != "FILE":
        return None, f"cannot read the command {command!r}"
    if run_tools and shutil.which("grep") is not None:
        proc = subprocess.run(argv[:3], input=source, capture_output=True, text=True, timeout=60, check=False)
        if proc.returncode > 1:
            return None, f"grep rejects {command!r}: {proc.stderr.strip()[:200]}"
        return [int(out.split(":", 1)[0]) for out in proc.stdout.splitlines()], ""
    if argv[1] == "-nF":
        return [i + 1 for i, line in enumerate(lines) if argv[2] in line], ""
    pattern = re.compile(argv[2])
    return [i + 1 for i, line in enumerate(lines) if pattern.search(line)], ""


def wrong_lines(source: str, lines: list[str], claim: Claim, run_tools: bool = True) -> list[str]:
    """What the source says against one claim about its lines (nothing when it holds).

    Raises:
        AssertionError: a kind of claim with no check (one added without it).
    """
    match claim:
        case Shows(first=first, lines=shown):
            if first < 1 or first - 1 + len(shown) > len(lines):
                return [f"line {first}: the source has {len(lines)} lines"]
            return [
                f"line {first + k}: shown as {text[:60]!r}, it is {lines[first - 1 + k][:60]!r}"
                for k, text in enumerate(shown)
                if not _shown(text, lines[first - 1 + k])
            ]
        case Total(lines=n, templates=k, quoted=quoted):
            has = len({_holes(line, quoted)[0] for line in lines if line.strip()})
            out = [] if n == len(lines) else [f"says {n} lines, the source has {len(lines)}"]
            return out + ([] if k == has else [f"says {k} line templates, the source has {has}"])
        case Alike(template=tmpl, n=n, first=first, last=last, quoted=quoted, slot=slot, value=value):
            held = 0
            for line in lines[first - 1 : last]:
                got, holes = _holes(line, quoted)
                if got == tmpl and (not slot or (len(holes) >= slot and holes[slot - 1] == value)):
                    held += 1
            where = f" with <*>{slot} = {value}" if slot else ""
            return (
                []
                if held == n
                else [f"lines {first}-{last}: {held} lines{where} like {tmpl[:80]!r}, not {n}"]
            )
        case Prints(command=command, lines=want):
            printed, why = _grep(source, lines, command, run_tools)
            if printed is None:
                return [why]
            if printed == list(want):
                return []
            return [f"{command}: prints lines {printed[:8]}, not {list(want)[:8]}"]
        case Count() | Values() | Breaks() | Lists() | Verbatim() | Fetches():
            return [f"{claim!r}: a claim about JSON, in an envelope of lines"]
        case _ as unreachable:
            raise AssertionError(f"no check for {unreachable!r}")


def text_problems(source: str, env: Envelope, run_tools: bool = True) -> list[str]:
    """Every way an envelope of lines fails its source (`run_tools` False: grep not run)."""
    lines = _lines(source)
    out = unsaid(env)
    for claim in env.claims():
        out += wrong_lines(source, lines, claim, run_tools)
    return out

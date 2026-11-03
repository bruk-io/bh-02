"""The eval tasks: format x kind x size band, synthetic and real, each with a computed truth.

Size bands, against the default budget of 2,000 tokens and Claude Code's MCP spill threshold of
50,000 characters (~12,500 tokens): S under the budget, M between the two, L over the threshold.
`tasks()` builds the whole registry; payloads load lazily, since some are large.
"""

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from compressors.common import estimate_tokens, read_text
from evals import real, synthetic
from evals.truth import ANSWER_INSTRUCTION, Absent, Exact, Items, Location, Needle, Number, Truth

BUDGET = 2000
SPILL_TOKENS = 50_000 // 4
FORMATS = ("json", "log", "a11y", "figma", "python", "rust", "xml", "pypi")
KINDS = ("spot", "absent", "lookup", "enumerate", "count", "locate")


@dataclass(frozen=True)
class Task:
    task_id: str
    fmt: str
    kind: str
    band: str  # S | M | L
    path: str  # the file the payload is (code is detected by its extension), or "" for tool output
    prompt: str  # for layer 2: what Claude is asked
    truth: Truth
    query: str  # the words a tool call would carry, if any; layer 1 folds with and without
    load: Callable[[], str]

    def payload(self) -> str:
        return self.load()


def band_of(tokens: int) -> str:
    return "S" if tokens <= BUDGET else "M" if tokens <= SPILL_TOKENS else "L"


# --- synthetic ----------------------------------------------------------------------------------

_SIZES = {
    "json": {"S": 20, "M": 100, "L": 500},
    "log": {"S": 60, "M": 300, "L": 2000},
    "a11y": {"S": 30, "M": 150, "L": 500},
    "figma": {"S": 20, "M": 100, "L": 500},
}
_MAKE = {"json": synthetic.pods, "log": synthetic.logs, "a11y": synthetic.snapshot, "figma": synthetic.figma}
_TOOL = {"json": "list_pods", "log": "get_logs", "a11y": "browser_snapshot", "figma": "get_figma_metadata"}
_ASK = {
    "json": {
        "spot": "Is any pod unhealthy or different from the rest? Name it. If none is, say so.",
        "count": "How many pods are not Running?",
        "enumerate": "List every pod that is not Running.",
        "lookup": "What is the IP address of pod {subject}?",
    },
    "log": {
        "spot": "Did any payment fail? Name the order. If none did, say so.",
        "count": "How many payments failed?",
        "enumerate": "List every order whose payment failed.",
        "lookup": "Which user made request {subject}?",
    },
    "a11y": {
        "spot": "Is any invoice's Pay button disabled? Name the invoice. If none is, say so.",
        "count": "How many invoices have a disabled Pay button?",
        "enumerate": "List every invoice whose Pay button is disabled.",
        "lookup": "What is the ref of the Pay button for invoice {subject}?",
    },
    "figma": {
        "spot": "Is any product card hidden? Name it. If none is, say so.",
        "count": "How many product cards are hidden?",
        "enumerate": "List every hidden product card.",
        "lookup": "What is the node id of the product card named {subject}?",
    },
}


@cache
def _payload(fmt: str, size: int, planted: frozenset[int], seed: str) -> synthetic.Payload:
    return _MAKE[fmt](size, planted, seed)


def _prompt(fmt: str, kind: str, subject: str = "") -> str:
    ask = _ASK[fmt]["spot" if kind == "absent" else kind].format(subject=subject)
    return f"Use the {_TOOL[fmt]} tool. {ask} {ANSWER_INSTRUCTION[kind]}."


def _count(fmt: str, p: synthetic.Payload) -> Number:
    """A count's truth: the planted items, and for JSON the summary entry that states the count."""
    k = len(p.planted)
    stated = (json.dumps({json.dumps("CrashLoopBackOff"): k})[1:-1],) if fmt == "json" else ()
    return Number(k, frozenset(p.planted), stated)


def _synthetic(fmt: str, band: str) -> list[Task]:
    size = _SIZES[fmt][band]
    out: list[Task] = []

    def add(kind: str, tag: str, planted: frozenset[int], truth_of, subject: int | None = None) -> None:
        seed = f"{fmt}/{band}/{kind}/{tag}"
        p = _payload(fmt, size, planted, seed)
        name, value = p.lookups[subject] if subject is not None else ("", "")
        out.append(
            Task(
                task_id=f"{fmt}-{band}-{kind}-{tag}",
                fmt=fmt,
                kind=kind,
                band=band,
                path="",
                prompt=_prompt(fmt, kind, name),
                truth=truth_of(p) if subject is None else Exact(value),
                query=name,
                load=lambda fmt=fmt, size=size, planted=planted, seed=seed: (
                    _payload(fmt, size, planted, seed).raw
                ),
            )
        )

    def at(fraction: float) -> int:
        return min(size - 1, round(fraction * (size - 1)))

    for fraction in (0.1, 0.5, 0.9):
        add("spot", f"at{int(fraction * 100)}", frozenset({at(fraction)}), lambda p: Needle(p.planted[0]))
    add("absent", "none", frozenset(), lambda p: Absent(frozenset(p.names)))
    for k in (3, 7):
        picks = frozenset(random.Random(f"{fmt}/{band}/count/{k}").sample(range(size), min(k, size)))
        add("count", f"k{k}", picks, lambda p, fmt=fmt: _count(fmt, p))
    picks = frozenset(random.Random(f"{fmt}/{band}/enumerate").sample(range(size), min(4, size)))
    add("enumerate", "k4", picks, lambda p: Items(frozenset(p.planted), frozenset(p.names)))
    for fraction in (0.5, 0.9):
        add(
            "lookup",
            f"at{int(fraction * 100)}",
            frozenset(),
            lambda p: Absent(frozenset()),
            subject=at(fraction),
        )
    return out


# --- real files -------------------------------------------------------------------------------------


@cache
def _read(path: Path) -> str:
    return read_text(str(path))


def _file_task(
    task_id: str, fmt: str, kind: str, path: Path, prompt: str, truth: Truth, query: str = ""
) -> Task:
    text = _read(path)
    return Task(
        task_id=task_id,
        fmt=fmt,
        kind=kind,
        band=band_of(estimate_tokens(text)),
        path=str(path),
        prompt=f"{prompt.format(path=path)} {ANSWER_INSTRUCTION[kind]}.",
        truth=truth,
        query=query,
        load=lambda path=path: _read(path),
    )


def _python() -> list[Task]:
    be, sp, ap = (
        real.STDLIB / "asyncio/base_events.py",
        real.STDLIB / "subprocess.py",
        real.STDLIB / "argparse.py",
    )
    dec, bis = real.STDLIB / "json/decoder.py", real.STDLIB / "bisect.py"
    src = {p: _read(p) for p in (be, sp, ap, dec, bis)}
    out = [
        _file_task(
            "python-L-enumerate-async",
            "python",
            "enumerate",
            be,
            "In {path}, which methods of the class BaseEventLoop itself are coroutines (defined with "
            "`async def`), private ones included? List every name.",
            Items(real.py_async_methods(src[be], "BaseEventLoop"), real.py_names(src[be])),
        ),
        _file_task(
            "python-L-enumerate-platforms",
            "python",
            "enumerate",
            sp,
            "In {path}, which methods does class Popen define in both branches of its `if _mswindows:` "
            "check? List every name.",
            Items(real.py_both_platforms(src[sp]), real.py_names(src[sp])),
        ),
        _file_task(
            "python-L-enumerate-actions",
            "python",
            "enumerate",
            ap,
            "In {path}, which classes subclass Action directly? List every name.",
            Items(real.py_subclasses(src[ap], "Action"), real.py_names(src[ap])),
        ),
    ]
    for path, cls in ((be, "Server"), (ap, "ArgumentParser"), (dec, "JSONDecoder")):
        n = len(real.py_methods(src[path], cls))
        out.append(
            _file_task(
                f"python-{band_of(estimate_tokens(src[path]))}-count-{cls}",
                "python",
                "count",
                path,
                f"In {{path}}, how many methods does class {cls} define directly in its body?",
                Number(n, frozenset(f"def {m.name}" for m in real.py_methods(src[path], cls))),
            )
        )
    for path, cls, method in (
        (be, "BaseEventLoop", "create_server"),
        (sp, "Popen", "communicate"),
        (ap, "ArgumentParser", "parse_known_args"),
        (dec, "JSONDecoder", "raw_decode"),
    ):
        line = real.py_method_line(src[path], cls, method)
        out.append(
            _file_task(
                f"python-{band_of(estimate_tokens(src[path]))}-locate-{method}",
                "python",
                "locate",
                path,
                f"In {{path}}, on which line is {cls}.{method} defined?",
                Location(line, f"def {method}"),
            )
        )
    names = real.py_names(src[bis])
    out.append(
        _file_task(
            "python-S-enumerate-functions",
            "python",
            "enumerate",
            bis,
            "In {path}, which functions are defined? List every name.",
            Items(names, names),
        )
    )
    return out


def _rust() -> list[Task]:
    compiler = real.CARGO / "regex-automata-0.4.13/src/nfa/thompson/compiler.rs"
    dfa = real.CARGO / "regex-automata-0.4.13/src/hybrid/dfa.rs"
    out = []
    for path, ty in ((compiler, "Compiler"), (dfa, "Lazy")):
        src = _read(path)
        fns = real.rust_impl_fns(src, ty)
        band = band_of(estimate_tokens(src))
        out += [
            _file_task(
                f"rust-{band}-enumerate-{ty}",
                "rust",
                "enumerate",
                path,
                f"In {{path}}, which functions are defined directly in the first `impl {ty}` block (not a "
                "trait impl)? List every name.",
                Items(frozenset(n for n, _ in fns), real.rust_names(src)),
            ),
            _file_task(
                f"rust-{band}-count-{ty}",
                "rust",
                "count",
                path,
                f"In {{path}}, how many functions does the first `impl {ty}` block (not a trait impl) "
                "define?",
                Number(len(fns), frozenset(f"fn {n}" for n, _ in fns)),
            ),
        ]
        name, line = fns[len(fns) // 2]
        out.append(
            _file_task(
                f"rust-{band}-locate-{ty}-{name}",
                "rust",
                "locate",
                path,
                f"In {{path}}, on which line is the function {name} of the first `impl {ty}` block defined?",
                Location(line, f"fn {name}"),
            )
        )
    return out


def _xml() -> list[Task]:
    src = _read(real.ISO_3166_2)
    codes = real.iso_codes(src)
    andorra = real.iso_entries(src, "AD")
    japan = dict(real.iso_entries(src, "JP"))
    netherlands = real.iso_entries(src, "NL")
    return [
        _file_task(
            "xml-L-enumerate-AD",
            "xml",
            "enumerate",
            real.ISO_3166_2,
            "In {path}, list the codes of every subdivision of Andorra (country code AD).",
            Items(frozenset(c for c, _ in andorra), codes),
            query="AD",
        ),
        _file_task(
            "xml-L-count-NL",
            "xml",
            "count",
            real.ISO_3166_2,
            "In {path}, how many subdivision entries does the Netherlands (country code NL) have?",
            Number(len(netherlands), frozenset(c for c, _ in netherlands)),
            query="NL",
        ),
        _file_task(
            "xml-L-lookup-JP-13",
            "xml",
            "lookup",
            real.ISO_3166_2,
            "In {path}, what is the name of the subdivision with code JP-13?",
            Exact(japan["JP-13"]),
            query="JP-13",
        ),
    ]


def _pypi() -> list[Task]:
    if not real.PYPI_CLICK.is_file():
        return []
    src = _read(real.PYPI_CLICK)
    versions = frozenset(real.pypi_versions(src))
    return [
        _file_task(
            "pypi-L-count-releases",
            "pypi",
            "count",
            real.PYPI_CLICK,
            "{path} is PyPI's JSON for the package click. How many releases does it list?",
            Number(len(versions), versions, (f"of {len(versions)} keys of $.releases",)),
        ),
        _file_task(
            "pypi-L-enumerate-2023",
            "pypi",
            "enumerate",
            real.PYPI_CLICK,
            "{path} is PyPI's JSON for the package click. Which versions were first uploaded in 2023?",
            Items(real.pypi_released_in(src, "2023"), versions),
            query="2023",
        ),
        _file_task(
            "pypi-L-lookup-sha",
            "pypi",
            "lookup",
            real.PYPI_CLICK,
            "{path} is PyPI's JSON for the package click. What is the sha256 digest of the wheel of "
            "version 8.1.7?",
            Exact(real.pypi_sha256(src, "8.1.7")),
            query="8.1.7",
        ),
    ]


def tasks() -> list[Task]:
    out: list[Task] = []
    for fmt in _SIZES:
        for band in ("S", "M", "L"):
            out += _synthetic(fmt, band)
    return out + _python() + _rust() + _xml() + _pypi()

"""The eval tasks: format x kind x size band, synthetic and real, each with a computed truth.

Size bands, against the default budget of 2,000 tokens and Claude Code's MCP spill threshold of
50,000 characters (~12,500 tokens): S under the budget, M between the two, L over the threshold.
XL and XXL are 4 and 16 times L (about 75k to 660k tokens): synthetic only, for how a fold behaves
as outputs grow, and built only when asked for, by `tasks(BANDS)` or `task(id)`. `tasks()` builds
the usual registry, S to L. Real files are read when the registry is built, since their truths are
computed from them; a source
whose files are missing on this host (the Python 3.13 stdlib, the cargo registry, iso-codes, the
saved PyPI JSON in the untracked corpus/) is left out, and `skipped()` says which and why.
"""

import json
import random
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache, partial
from pathlib import Path

from compressors.common import estimate_tokens, read_text
from evals import real, synthetic
from evals.truth import ANSWER_INSTRUCTION, Absent, Edited, Exact, Items, Location, Needle, Number, Truth

BUDGET = 2000
SPILL_TOKENS = 50_000 // 4
FORMATS = ("json", "log", "a11y", "figma", "python", "rust", "xml", "pypi")
KINDS = ("spot", "absent", "lookup", "enumerate", "count", "locate", "edit")


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
    question: str = ""  # a synthetic task's question without the tool, for another channel's prompt

    def payload(self) -> str:
        return self.load()


BANDS = ("S", "M", "L", "XL", "XXL")  # smallest first, the order reports list them in
_USUAL = BANDS[:3]  # what `tasks()` builds; real files fall in these by their size


def band_of(tokens: int) -> str:
    return "S" if tokens <= BUDGET else "M" if tokens <= SPILL_TOKENS else "L"


def size_order(band: str) -> int:
    """A band's place among BANDS, for sorting rows smallest first (an unknown band goes last)."""
    return BANDS.index(band) if band in BANDS else len(BANDS)


# --- synthetic ----------------------------------------------------------------------------------

_SIZES = {
    "json": {"S": 20, "M": 100, "L": 500, "XL": 2000, "XXL": 8000},
    "log": {"S": 60, "M": 300, "L": 2000, "XL": 8000, "XXL": 32000},
    "a11y": {"S": 30, "M": 150, "L": 500, "XL": 2000, "XXL": 8000},
    "figma": {"S": 20, "M": 100, "L": 500, "XL": 2000, "XXL": 8000},
}
_MAKE = {"json": synthetic.pods, "log": synthetic.logs, "a11y": synthetic.snapshot, "figma": synthetic.figma}
TOOLS = {"json": "list_pods", "log": "get_logs", "a11y": "browser_snapshot", "figma": "get_figma_metadata"}
_ASK = {
    "json": {
        "spot": "Does any pod look wrong or unusual? Name it, or say none.",
        "count": "How many pods are not Running?",
        "enumerate": "List every pod that is not Running.",
        "lookup": "What is the IP address of pod {subject}?",
    },
    "log": {
        "spot": (
            "Does anything in the log look wrong or unusual? If so, give the id of the order or request it "
            "concerns; if not, say none."
        ),
        "count": "How many payments failed?",
        "enumerate": "List every order whose payment failed.",
        "lookup": "Which user made request {subject}?",
    },
    "a11y": {
        "spot": "Does anything on the page look wrong or unusual? Name the invoice, or say none.",
        "count": "How many invoices have a disabled Pay button?",
        "enumerate": "List every invoice whose Pay button is disabled.",
        "lookup": "What is the ref of the Pay button for invoice {subject}?",
    },
    "figma": {
        "spot": "Does any product card look wrong or unusual? Name it, or say none.",
        "count": "How many product cards are hidden?",
        "enumerate": "List every hidden product card.",
        "lookup": "What is the node id of the product card named {subject}?",
    },
}


def _raw(fmt: str, size: int, planted: frozenset[int], seed: str, quiet: bool) -> str:
    return _payload(fmt, size, planted, seed, quiet).raw


@cache
def _payload(
    fmt: str, size: int, planted: frozenset[int], seed: str, quiet: bool = False
) -> synthetic.Payload:
    return _MAKE[fmt](size, planted, seed, quiet)


def _question(fmt: str, kind: str, subject: str = "") -> str:
    ask = _ASK[fmt]["spot" if kind == "absent" else kind].format(subject=subject)
    return f"{ask} {ANSWER_INSTRUCTION[kind]}."


def _prompt(fmt: str, kind: str, subject: str = "") -> str:
    return f"Use the {TOOLS[fmt]} tool. {_question(fmt, kind, subject)}"


# What each synthetic format's command prints, for the bash channel (the MCP tools' descriptions).
_COMMAND_SAYS = {
    "json": "it lists the pods in a Kubernetes namespace, with their status",
    "log": "it prints the recent log lines of a service",
    "a11y": "it prints an accessibility snapshot of the current browser page",
    "figma": "it prints the layer tree of a Figma node as XML: ids, names, types, positions and sizes",
}


def bash_prompt(t: Task) -> str:
    """A synthetic task asked on the bash channel: its payload comes from `./<tool>` in the session's
    folder instead of an MCP tool, and the question is the same."""
    return f"Run `./{TOOLS[t.fmt]}` in the current directory; {_COMMAND_SAYS[t.fmt]}. {t.question}"


def _count(fmt: str, p: synthetic.Payload) -> Number:
    """A count's truth: the planted items, and for JSON where a view states the count: the sample
    view's summary entry, or the schema view's value count."""
    k = len(p.planted)
    sample = json.dumps({json.dumps("CrashLoopBackOff"): k})[1:-1]
    stated = (sample, f'"CrashLoopBackOff" {k}') if fmt == "json" else ()
    return Number(k, frozenset(p.planted), stated)


_LOG_IDS = re.compile(r"\b(?:ORD|req)-[0-9a-f]+\b")


def _needle(p: synthetic.Payload, *, fmt: str) -> Needle:
    """The planted item. On a log line it may also be named by the line's other id: the question
    asks for "the order or request it concerns", and a payment failure names both (never the user,
    who may have made other requests)."""
    token = p.planted[0]
    if fmt != "log":
        return Needle(token)
    line = next(x for x in p.raw.splitlines() if token in x)
    return Needle(token, frozenset(_LOG_IDS.findall(line)) - {token})


def _at(size: int, fraction: float) -> int:
    return min(size - 1, round(fraction * (size - 1)))


def _picked(fmt: str, band: str, tag: str, k: int) -> frozenset[int]:
    size = _SIZES[fmt][band]
    return frozenset(random.Random(f"{fmt}/{band}/{tag}").sample(range(size), min(k, size)))


def _synthetic(fmt: str, band: str) -> list[Task]:
    """Spot (a rule-kind anomaly at three positions, and a quiet one the fold has no rule for),
    absent, count and enumerate (k under and, from M up, over the stand-out cap of 10), lookup."""
    size = _SIZES[fmt][band]
    out: list[Task] = []

    def add(
        kind: str,
        tag: str,
        planted: frozenset[int],
        truth_of: Callable[[synthetic.Payload], Truth] | None,
        subject: int | None = None,  # the item whose unique value is the answer (a lookup)
        quiet: bool = False,
    ) -> None:
        seed = f"{fmt}/{band}/{kind}/{tag}"
        p = _payload(fmt, size, planted, seed, quiet)
        if subject is not None:
            name, value = p.lookups[subject]
            truth: Truth = Exact(value)
        else:
            assert truth_of is not None, "a task with no lookup subject computes its truth with truth_of"
            name, truth = "", truth_of(p)
        out.append(
            Task(
                task_id=f"{fmt}-{band}-{kind}-{tag}",
                fmt=fmt,
                kind=kind,
                band=band,
                path="",
                prompt=_prompt(fmt, kind, name),
                truth=truth,
                query=name,
                load=partial(_raw, fmt, size, planted, seed, quiet),
                question=_question(fmt, kind, name),
            )
        )

    def at(fraction: float) -> int:
        return _at(size, fraction)

    def pick(tag: str, k: int) -> frozenset[int]:
        return _picked(fmt, band, tag, k)

    for fraction in (0.1, 0.5, 0.9):
        add("spot", f"at{int(fraction * 100)}", frozenset({at(fraction)}), partial(_needle, fmt=fmt))
    add("spot", "quiet-at50", frozenset({at(0.5)}), partial(_needle, fmt=fmt), quiet=True)
    add("absent", "none", frozenset(), lambda p: Absent(frozenset(p.names)))
    over_cap = (12, 20) if band != "S" else ()
    for k in (3, 7, *over_cap):
        add("count", f"k{k}", pick(f"count/{k}", k), lambda p: _count(fmt, p))
    for k in (4, *over_cap[:1]):
        add(
            "enumerate",
            f"k{k}",
            pick(f"enumerate/{k}", k),
            lambda p: Items(frozenset(p.planted), frozenset(p.names)),
        )
    for fraction in (0.5, 0.9):
        add("lookup", f"at{int(fraction * 100)}", frozenset(), None, subject=at(fraction))
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
        load=partial(_read, path),
    )


_PYTHON_FILES = tuple(
    real.STDLIB / p
    for p in ("asyncio/base_events.py", "subprocess.py", "argparse.py", "json/decoder.py", "bisect.py")
)
_RUST_FILES = tuple(
    real.CARGO / p
    for p in ("regex-automata-0.4.13/src/nfa/thompson/compiler.rs", "regex-automata-0.4.13/src/hybrid/dfa.rs")
)


def _python() -> list[Task]:
    be, sp, ap, dec, bis = _PYTHON_FILES
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
    compiler, dfa = _RUST_FILES
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


def task(task_id: str) -> Task:
    """One task by id. A synthetic id builds its own format and band alone, so a session's fixture
    generates one payload, not the registry's.

    Raises:
        KeyError: no task has this id; the message lists a few that do.
    """
    fmt, band, *_ = [*task_id.split("-", 2), "", ""]
    pool = _synthetic(fmt, band) if fmt in _SIZES and band in BANDS else tasks()
    found = {t.task_id: t for t in pool}
    if task_id not in found:
        raise KeyError(f"no eval task {task_id!r}; ids look like {', '.join(list(found)[:3])}")
    return found[task_id]


def _edit_task(task_id: str, path: Path, instruction: str, truth: Edited) -> Task:
    """An edit of a copy of `path` (layer 2 puts the copy in the session's folder; the prompt names
    it by its bare name, so the original is never the one edited)."""
    text = _read(path)
    return Task(
        task_id=task_id,
        fmt="python",
        kind="edit",
        band=band_of(estimate_tokens(text)),
        path=str(path),
        prompt=(
            f"./{path.name} is a copy of the standard library's {path.name}. In it, {instruction} "
            f"Change nothing else. {ANSWER_INSTRUCTION['edit']}."
        ),
        truth=truth,
        query="",
        load=partial(_read, path),
    )


def _edits() -> list[Task]:
    be, sp, ap, _, _ = _PYTHON_FILES
    return [
        _edit_task(
            "python-L-edit-create_server-timeout",
            be,
            "add a keyword-only parameter `timeout` to BaseEventLoop.create_server, defaulting to None.",
            Edited(
                "def create_server",
                real.added_keyword_only("BaseEventLoop", "create_server", "timeout", "None"),
            ),
        ),
        _edit_task(
            "python-L-edit-Popen-nice",
            sp,
            "add a keyword-only parameter `nice` to Popen.__init__, defaulting to None.",
            Edited("def __init__(self, args", real.added_keyword_only("Popen", "__init__", "nice", "None")),
        ),
        _edit_task(
            "python-L-edit-HelpFormatter-color",
            ap,
            "add a keyword-only parameter `color` to HelpFormatter.__init__, defaulting to False.",
            Edited(
                "class HelpFormatter", real.added_keyword_only("HelpFormatter", "__init__", "color", "False")
            ),
        ),
        _edit_task(
            "python-L-edit-rename-check_closed",
            be,
            "rename BaseEventLoop's method `_check_closed` to `_ensure_open`, and update every use of it.",
            Edited("def _check_closed", real.renamed("_check_closed", "_ensure_open")),
        ),
        _edit_task(
            "python-L-edit-rename-communicate",
            sp,
            "rename Popen's method `_communicate` to `_exchange`, and update every use of it.",
            Edited("def _communicate", real.renamed("_communicate", "_exchange")),
        ),
    ]


# Each real source: the files its tasks are built from, and the function that builds them.
_REAL: dict[str, tuple[tuple[Path, ...], Callable[[], list[Task]]]] = {
    "python": (_PYTHON_FILES, _python),
    "python-edit": (_PYTHON_FILES, _edits),
    "rust": (_RUST_FILES, _rust),
    "xml": ((real.ISO_3166_2,), _xml),
    "pypi": ((real.PYPI_CLICK,), _pypi),
}


def skipped() -> dict[str, str]:
    """The real sources left out on this host, and why: their files are missing."""
    out = {}
    for source, (paths, _) in _REAL.items():
        if missing := [str(p) for p in paths if not p.is_file()]:
            out[source] = f"missing {', '.join(missing)}"
    return out


# --- conversations ------------------------------------------------------------------------------

_FOLLOW_UPS = (0.2, 0.4, 0.6, 0.8)  # where the looked-up items sit, as a share of the payload


@dataclass(frozen=True)
class Conversation:
    """Questions about one tool result, asked in turn in one session. The first turn is a count task
    of the registry: its prompt names the tool, and the fixture serves its payload. The others follow
    up on the same payload without naming the tool: every planted item, then items looked up across
    it, so a session that holds only a fold must fetch again where one holding the raw need not."""

    conv_id: str  # the first turn's task id
    turns: tuple[Task, ...]


def _conversation(fmt: str, band: str, k: int) -> Conversation:
    first = task(f"{fmt}-{band}-count-k{k}")
    size = _SIZES[fmt][band]
    p = _payload(fmt, size, _picked(fmt, band, f"count/{k}", k), f"{fmt}/{band}/count/k{k}")

    def follow(kind: str, tag: str, truth: Truth, subject: str = "") -> Task:
        return Task(
            task_id=f"{first.task_id}+{kind}-{tag}",
            fmt=fmt,
            kind=kind,
            band=band,
            path="",
            prompt=_question(fmt, kind, subject),
            truth=truth,
            query=subject,
            load=first.load,
            question=_question(fmt, kind, subject),
        )

    looked_up = [p.lookups[_at(size, f)] for f in _FOLLOW_UPS]
    return Conversation(
        first.task_id,
        (
            first,
            follow("enumerate", "all", Items(frozenset(p.planted), frozenset(p.names))),
            *(
                follow("lookup", f"at{int(f * 100)}", Exact(v), n)
                for f, (n, v) in zip(_FOLLOW_UPS, looked_up, strict=True)
            ),
        ),
    )


def conversations(bands: Iterable[str], formats: Iterable[str] = tuple(_SIZES)) -> list[Conversation]:
    """A conversation on each count task's payload (k of 3 and 7, and from M up 12 and 20), for each
    synthetic format and band asked for.

    Raises:
        ValueError: a band or format with no synthetic tasks.
    """
    want_b, want_f = set(bands), set(formats)
    if unknown := (want_b - set(BANDS)) | (want_f - set(_SIZES)):
        raise ValueError(
            f"no synthetic {', '.join(sorted(unknown))}: the bands are {', '.join(BANDS)} and the formats "
            f"{', '.join(_SIZES)}"
        )
    return [
        _conversation(fmt, band, k)
        for band in BANDS
        if band in want_b
        for fmt in _SIZES
        if fmt in want_f
        for k in ((3, 7) if band == "S" else (3, 7, 12, 20))
    ]


def tasks(bands: Iterable[str] = _USUAL) -> list[Task]:
    """Every task in these bands (S, M and L by default; XL and XXL hold synthetic tasks alone).

    Raises:
        ValueError: a band that is none of BANDS.
    """
    want = set(bands)
    if unknown := want - set(BANDS):
        raise ValueError(f"no size band {', '.join(sorted(unknown))}: the bands are {', '.join(BANDS)}")
    out: list[Task] = []
    for fmt in _SIZES:
        for band in (b for b in BANDS if b in want):
            out += _synthetic(fmt, band)
    gone = skipped()
    for source, (_, build) in _REAL.items():
        if source not in gone and want & set(_USUAL):
            out += [t for t in build() if t.band in want]
    return out

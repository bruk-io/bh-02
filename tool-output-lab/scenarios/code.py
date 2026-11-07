"""The code-and-tests family: a generated Python package with tests and a git history, one commit of
which quietly breaks some tests.

A world is a value (`world(seed, size)`): rule functions that apply a rate from a threshold, such as
`pricing.discount_for_total`; composite functions in other modules that call them; tests with cases
below, at and above each threshold; and a history in which modules arrive commit by commit, with
harmless docstring changes, and one commit brings in the regression. A boundary regression (`>=` to
`>`) fails the case at the threshold; a rate regression fails every case above it, which makes a long
test report. The truths are worked out from the rules (`failing`, `callers`), and `build` writes the
repository with fixed dates and authors, so a seed gives the same commit shas every time, then runs
the tests and refuses a world whose report disagrees with its truth.

The tools are the real ones, through Bash: `./run-tests` (pytest, pinned, through uv), `git` and
`grep`. SCENARIOS.md has the design.
"""

import ast
import os
import random
import re
import subprocess
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from evals.truth import Edited, Exact, Items, Needle, Truth

PYTEST = "pytest==8.4.2"
_MODULES = (
    "pricing",
    "shipping",
    "loyalty",
    "tax",
    "returns",
    "billing",
    "coupons",
    "deposits",
    "fees",
    "credit",
)
_NOUNS = (
    "discount",
    "surcharge",
    "fee",
    "credit",
    "rebate",
    "levy",
    "bonus",
    "deposit",
    "allowance",
    "markup",
)
_PARAMS = (
    ("total", "cents"),
    ("weight", "grams"),
    ("quantity", "items"),
    ("distance", "metres"),
    ("points", "points"),
)
_COMPOSITES = ("orders", "checkout", "invoices", "carts")
_KINDS = ("", "early_", "late_", "bulk_", "member_", "seasonal_", "express_", "weekend_", "regional_")
_AUTHORS = (
    ("Ada Okafor", "ada@shop.example"),
    ("Lin Park", "lin@shop.example"),
    ("Sam Rivera", "sam@shop.example"),
)
# modules, rules per module, cases per rule, big modules, and how many times more rules a big one has
_SIZES = {"M": (5, 8, 4, 1, 6), "L": (8, 12, 6, 2, 6)}


@dataclass(frozen=True)
class Rule:
    module: str
    name: str
    noun: str
    param: str
    unit: str
    threshold: int
    rate: int  # percent

    def apply(self, value: int, boundary: bool = False, rate: int | None = None) -> int:
        """What the function returns; `boundary` and `rate` give the regressed function instead."""
        hit = value > self.threshold if boundary else value >= self.threshold
        return value * (self.rate if rate is None else rate) // 100 if hit else 0


@dataclass(frozen=True)
class Composite:
    module: str
    name: str
    calls: tuple[Rule, ...]  # one argument per rule, in order


@dataclass(frozen=True)
class Regression:
    rule: Rule
    kind: str  # boundary | rate
    rate: int  # the regressed rate (the rule's own for a boundary regression)
    at: int  # the commit that brings it in (an index into the history)


@dataclass(frozen=True)
class Commit:
    message: str
    author: tuple[str, str]
    date: str
    files: tuple[tuple[str, str], ...]  # the paths and texts it writes


@dataclass(frozen=True)
class World:
    seed: int
    size: str
    rules: tuple[Rule, ...]
    composites: tuple[Composite, ...]
    cases: tuple[tuple[Rule, tuple[int, ...]], ...]  # each rule's test inputs
    regression: Regression
    history: tuple[Commit, ...]
    big: tuple[str, ...] = ()  # the modules with many rules: the large file views


# --- the world -----------------------------------------------------------------------------------


def _rules(rng: random.Random, counts: tuple[tuple[str, int], ...]) -> tuple[Rule, ...]:
    out, seen = [], set()
    for m, n in counts:
        for _ in range(n):
            while True:
                noun, (param, unit), kind = rng.choice(_NOUNS), rng.choice(_PARAMS), rng.choice(_KINDS)
                name = f"{kind}{noun}_for_{param}"
                if (m, name) not in seen:
                    break
            seen.add((m, name))
            threshold = rng.choice((10, 25, 50, 100, 250, 500)) * rng.choice((1, 10, 100))
            out.append(Rule(m, name, noun, param, unit, threshold, rng.choice((2, 3, 5, 8, 10, 12, 15, 20))))
    return tuple(out)


def _cases(rng: random.Random, rule: Rule, n: int) -> tuple[int, ...]:
    """Inputs below, at and above the threshold, then others spread around it."""
    t = rule.threshold
    fixed = [t - 1, t, t + 1, t * 2]
    spread = {rng.randrange(max(1, t // 3), t * 4) for _ in range(n * 3)} - set(fixed)
    return tuple(sorted(fixed + sorted(spread)[: max(0, n - len(fixed))]))


def failing(world: World) -> frozenset[str]:
    """The test ids that fail once the regression is in, worked out from the rules."""
    reg = world.regression
    out = set()
    for rule, values in world.cases:
        if rule != reg.rule:
            continue
        for v in values:
            if rule.apply(v) != rule.apply(v, boundary=reg.kind == "boundary", rate=reg.rate):
                out.add(f"tests/test_{rule.module}.py::test_{rule.name}[{v}-{rule.apply(v)}]")
    for c in world.composites:
        if reg.rule in c.calls:
            args = tuple(r.threshold for r in c.calls)  # each composite test calls at the thresholds
            good = sum(r.apply(a) for r, a in zip(c.calls, args, strict=True))
            bad = sum(
                r.apply(a, r == reg.rule and reg.kind == "boundary", reg.rate if r == reg.rule else None)
                for r, a in zip(c.calls, args, strict=True)
            )
            if good != bad:
                out.add(f"tests/test_{c.module}.py::test_{c.name}")
    return frozenset(out)


def every_test(world: World) -> frozenset[str]:
    ids = {
        f"tests/test_{rule.module}.py::test_{rule.name}[{v}-{rule.apply(v)}]"
        for rule, values in world.cases
        for v in values
    }
    return frozenset(ids | {f"tests/test_{c.module}.py::test_{c.name}" for c in world.composites})


def callers(world: World, rule: Rule) -> frozenset[str]:
    """The package's functions (not its tests) that call `rule`, as module.function."""
    return frozenset(f"{c.module}.{c.name}" for c in world.composites if rule in c.calls)


def world(seed: int, size: str = "M") -> World:
    """The world a seed builds: the same seed, the same world, history and all.

    Raises:
        ValueError: `size` names no size (M or L).
    """
    if size not in _SIZES:
        raise ValueError(f"no size {size!r}: use one of {', '.join(_SIZES)}")
    n_modules, per, n_cases, n_big, factor = _SIZES[size]
    rng = random.Random(f"code/{size}/{seed}")
    modules = tuple(rng.sample(_MODULES, n_modules))
    big = modules[:n_big]
    rules = _rules(rng, tuple((m, per * factor if m in big else per) for m in modules))
    cases = tuple((r, _cases(rng, r, n_cases)) for r in rules)
    composites = []
    for i, m in enumerate(rng.sample(_COMPOSITES, min(len(_COMPOSITES), 2 + n_modules // 3))):
        for j in range(2 + n_modules // 4):
            calls = tuple(rng.sample(rules, rng.choice((2, 3))))
            composites.append(Composite(m, f"{m.rstrip('s')}_total_{i}{j}", calls))
    target = rng.choice([r for r in rules if any(r in c.calls for c in composites)] or list(rules))
    kind = rng.choice(("boundary", "rate"))
    rate = target.rate if kind == "boundary" else target.rate + rng.choice((-1, 1)) * rng.choice((1, 2, 5))
    draft = World(seed, size, rules, tuple(composites), cases, Regression(target, kind, rate, -1), (), big)
    history, at = _history(rng, draft)
    return World(
        seed, size, rules, tuple(composites), cases, Regression(target, kind, rate, at), history, big
    )


# --- the files -----------------------------------------------------------------------------------


def _constant(rule: Rule) -> str:
    return rule.name.upper() + "_FROM"


def _rule_source(rule: Rule, reg: Regression | None, noted: bool) -> str:
    op, rate = ">=", rule.rate
    if reg is not None and reg.rule == rule:
        op, rate = (">" if reg.kind == "boundary" else ">="), reg.rate
    note = f"\n\n    Zero below the threshold, so small {rule.param}s pay nothing." if noted else ""
    return (
        f"def {rule.name}({rule.param}: int) -> int:\n"
        f'    """The {rule.noun} on a {rule.param} of `{rule.param}` {rule.unit}: {rule.rate}% from'
        f' {_constant(rule)} up.{note}\n    """\n'
        f"    if {rule.param} {op} {_constant(rule)}:\n"
        f"        return {rule.param} * {rate} // 100\n"
        f"    return 0\n"
    )


def _module(module: str, rules: tuple[Rule, ...], reg: Regression | None, noted: frozenset[str]) -> str:
    mine = [r for r in rules if r.module == module]
    consts = "".join(f"{_constant(r)} = {r.threshold}  # {r.unit}\n" for r in mine)
    funcs = "\n\n".join(_rule_source(r, reg, r.name in noted) for r in mine)
    return f'"""The {module} rules of the shop: amounts in cents."""\n\n{consts}\n\n{funcs}'


def _composite_module(module: str, comps: list[Composite]) -> str:
    used = sorted({r.module for c in comps for r in c.calls})
    out = [
        f'"""The {module} totals: the sum of the rules each applies."""\n',
        f"from shop import {', '.join(used)}\n",
    ]
    for c in comps:
        params = [f"{r.param}_{k}" for k, r in enumerate(c.calls)]
        terms = " + ".join(f"{r.module}.{r.name}({p})" for r, p in zip(c.calls, params, strict=True))
        sig = ", ".join(f"{p}: int" for p in params)
        out.append(
            f"\ndef {c.name}({sig}) -> int:\n"
            f'    """The {module} total for one order."""\n    return {terms}\n'
        )
    return "\n".join(out)


def _rule_tests(module: str, w: World) -> str:
    out = [
        "import pytest\n",
        f"from shop.{module} import " + ", ".join(r.name for r in w.rules if r.module == module) + "\n",
    ]
    for rule, values in w.cases:
        if rule.module != module:
            continue
        pairs = ", ".join(f"({v}, {rule.apply(v)})" for v in values)
        out.append(
            f'\n@pytest.mark.parametrize(("{rule.param}", "expected"), [{pairs}])\n'
            f"def test_{rule.name}({rule.param}, expected):\n"
            f"    assert {rule.name}({rule.param}) == expected\n"
        )
    return "".join(out)


def _composite_tests(module: str, comps: list[Composite]) -> str:
    out = [f"from shop.{module} import " + ", ".join(c.name for c in comps) + "\n"]
    for c in comps:
        args = ", ".join(str(r.threshold) for r in c.calls)
        expected = sum(r.apply(r.threshold) for r in c.calls)
        out.append(f"\n\ndef test_{c.name}():\n    assert {c.name}({args}) == {expected}\n")
    return "".join(out)


_RUN_TESTS = f"""#!/usr/bin/env sh
# The shop's tests: pytest, pinned, through uv. Pass pytest's own options, such as -q or -x.
exec uv run --quiet --no-project --python 3.13 --with {PYTEST} python -m pytest -p no:cacheprovider "$@"
"""


def _history(rng: random.Random, w: World) -> tuple[tuple[Commit, ...], int]:
    """The commits: the package's start, the rule modules one at a time with their tests, then the
    totals, with harmless docstring notes between; then the regression; then a few harmless commits.
    Every test passes at every commit before the regression and its own failures start there, so the
    commit that broke them has one answer."""
    modules = list(dict.fromkeys(r.module for r in w.rules))
    by_comp: dict[str, list[Composite]] = {}
    for c in w.composites:
        by_comp.setdefault(c.module, []).append(c)
    steps: list[tuple[str, list[str]]] = [(f"Add the {m} rules", [f"rule:{m}"]) for m in modules[1:]]
    steps += [(f"Add the {m} totals", [f"comp:{m}"]) for m in by_comp]
    for _ in range(len(modules)):
        steps.insert(rng.randrange(1, len(steps) + 1), ("Document the zero below a threshold", ["note"]))
    steps.insert(0, ("Start the shop package", ["base", f"rule:{modules[0]}"]))
    target = w.regression.rule
    at = len(steps)
    steps.append(
        (
            rng.choice(
                (
                    f"Simplify {target.name}",
                    f"Tidy the {target.module} rules",
                    f"Use one comparison in {target.module}",
                )
            ),
            ["regress"],
        )
    )
    steps += [
        ("Document the zero below a threshold", ["note"])
        if rng.random() < 0.5
        else ("Bump the version", ["bump"])
        for _ in range(rng.choice((1, 2, 3)))
    ]
    commits = []
    have: list[str] = []
    noted: set[str] = set()
    regressed, version = False, 1
    for i, (msg, parts) in enumerate(steps):
        files: dict[str, str] = {}
        for part in parts:
            if part == "base":
                files["run-tests"] = _RUN_TESTS
                files["shop/__init__.py"] = (
                    '"""A small shop: its pricing rules and the totals built from them."""\n'
                )
                files["tests/__init__.py"] = ""
            elif part.startswith("rule:"):
                have.append(part[5:])
                files[f"tests/test_{part[5:]}.py"] = _rule_tests(part[5:], w)
            elif part.startswith("comp:"):
                m = part[5:]
                files[f"shop/{m}.py"] = _composite_module(m, by_comp[m])
                files[f"tests/test_{m}.py"] = _composite_tests(m, by_comp[m])
            elif part == "note":
                noted.add(rng.choice([r.name for r in w.rules if r.module in have and r.name not in noted]))
            elif part == "regress":
                regressed = True
            elif part == "bump":
                version += 1
        files["pyproject.toml"] = (
            f'[project]\nname = "shop"\nversion = "0.1.{version}"\nrequires-python = ">=3.13"\n'
        )
        reg = w.regression if regressed else None
        for m in have:
            files[f"shop/{m}.py"] = _module(m, w.rules, reg, frozenset(noted))
        author = rng.choice(_AUTHORS)
        day = f"2026-{9 + i // 28:02d}-{1 + i % 28:02d}"
        date = f"{day}T{rng.randrange(9, 18):02d}:{rng.randrange(60):02d}:00+00:00"
        commits.append(Commit(msg, author, date, tuple(sorted(files.items()))))
    return tuple(commits), at


# --- building it ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Built:
    root: Path
    shas: tuple[str, ...]  # one per commit, in order


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, env=env
    ).stdout


def build(w: World, root: Path) -> Built:
    """Write the world's repository into `root` (empty or absent), commit by commit, then run its tests.

    Raises:
        ValueError: `root` is not empty, or the tests' report disagrees with the world's truth.
    """
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"{root} is not empty: build a world into a new directory")
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    shas = []
    for c in w.history:
        for path, text in c.files:
            p = root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            if path == "run-tests":
                p.chmod(0o755)
        name, email = c.author
        env = {
            **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_AUTHOR_DATE": c.date,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
            "GIT_COMMITTER_DATE": c.date,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        _git(root, "add", "-A", env=env)
        _git(root, "commit", "-q", "-m", c.message, env=env)
        shas.append(_git(root, "rev-parse", "HEAD").strip())
    report = subprocess.run(
        ["./run-tests", "-q", "--tb=no", "-rf"], cwd=root, capture_output=True, text=True, check=False
    ).stdout
    failed = frozenset(re.findall(r"^FAILED (\S+)", report, re.MULTILINE))
    if failed != failing(w):
        raise ValueError(
            f"the tests disagree with the world's truth for seed {w.seed}:"
            f" they fail {sorted(failed - failing(w))}"
            f" beyond it and pass {sorted(failing(w) - failed)} it expects to fail"
        )
    return Built(root, tuple(shas))


# --- the tasks -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """A task in a built world: the prompt, its truth, and the commands its answer usually needs
    (`probes`), whose outputs layer 1 folds and checks without a model."""

    task_id: str
    kind: str  # enumerate | spot
    prompt: str
    truth: Truth
    probes: tuple[str, ...]
    query: str = ""
    path: str = ""  # for an edit, the file it is made in
    prefix: str = ""  # a prefix an answer may put before each name ("shop." before orders.order_total_20)


def _is_doc(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _defs(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _rest(tree: ast.Module) -> list[str]:
    return [ast.dump(n) for n in tree.body if not isinstance(n, ast.FunctionDef)]


def _body(fn: ast.FunctionDef) -> list[str]:
    return [ast.dump(s) for s in fn.body if not _is_doc(s)]


def edit_problem(original: str, edited: str, func: str, param: str, default: str) -> str | None:
    """What is wrong with an edit that should add `param: str = default` to `func` as keyword-only
    and change nothing else (its docstring may say more), or None when it is right."""
    try:
        new = ast.parse(edited)
    except SyntaxError as e:
        return f"the edited file does not parse: {e}"
    old = ast.parse(original)
    o, n = _defs(old), _defs(new)
    if set(o) != set(n):
        return "functions were added or removed"
    if _rest(old) != _rest(new):
        return "the module's constants or imports changed"
    if changed := [name for name in o if name != func and ast.dump(o[name]) != ast.dump(n[name])]:
        return f"{', '.join(changed)} changed too"
    f = n[func]
    kw = [a.arg for a in f.args.kwonlyargs]
    if param not in kw:
        return f"{func} has no keyword-only parameter {param}"
    d = f.args.kw_defaults[kw.index(param)]
    if not (isinstance(d, ast.Constant) and d.value == default):
        return f"{param} does not default to {default!r}"
    if _body(o[func]) != _body(f) or [a.arg for a in o[func].args.args] != [a.arg for a in f.args.args]:
        return f"{func}'s body or its other parameters changed"
    return None


def tasks(w: World, built: Built) -> tuple[Task, ...]:
    reg = w.regression
    sha = built.shas[reg.at]
    msg = w.history[reg.at].message
    failing_ids = failing(w)
    prefix = f"code-{w.size}-{w.seed}"
    other = random.Random(f"{prefix}/other").choice(
        [r for r in w.rules if r != reg.rule and r.module in w.big]
    )
    return (
        Task(
            f"{prefix}-failing",
            "enumerate",
            "The shop's test suite fails. Run it with ./run-tests and list every failing test"
            " by its pytest id.",
            Items(failing_ids, every_test(w)),
            ("./run-tests", "./run-tests -v"),
        ),
        Task(
            f"{prefix}-commit",
            "spot",
            "These tests passed a while ago and fail now: "
            + ", ".join(sorted(failing_ids)[:3])
            + ". Find the commit that broke them, and give its hash.",
            Needle(sha[:7], frozenset({sha[:n] for n in range(8, 41)} | {msg})),
            ("git log", "git log -p", "git log --stat"),
            query=reg.rule.name,
        ),
        Task(
            f"{prefix}-callers",
            "enumerate",
            f"Which functions in the shop package, not its tests, call {reg.rule.module}.{reg.rule.name}?"
            " List them as module.function.",
            Items(callers(w, reg.rule), frozenset(f"{c.module}.{c.name}" for c in w.composites)),
            (f"grep -rn {reg.rule.name} shop", f"grep -rn {reg.rule.name} ."),
            query=reg.rule.name,
            prefix="shop.",
        ),
        Task(
            f"{prefix}-lookup",
            "lookup",
            f"What threshold does {other.module}.{other.name} use, in {other.unit}? Read it from the code.",
            Exact(str(other.threshold)),
            (f"cat shop/{other.module}.py", f"sed -n '1,400p' shop/{other.module}.py"),
            query=other.name,
        ),
        Task(
            f"{prefix}-edit",
            "edit",
            f'In shop/{other.module}.py, add a keyword-only parameter currency: str = "CAD" to {other.name}.'
            " Do not use it yet, and change nothing else.",
            Edited(
                f"def {other.name}", partial(edit_problem, func=other.name, param="currency", default="CAD")
            ),
            (f"cat shop/{other.module}.py",),
            query=other.name,
            path=f"shop/{other.module}.py",
        ),
    )

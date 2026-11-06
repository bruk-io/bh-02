"""The code-and-tests family's worlds, worked out without building them, and the hook's reading of
a Bash command that prints a whole file."""

import ast

from claude_code.hook import viewed_file
from compressors.route import fold
from scenarios.code import World, callers, edit_problem, every_test, failing, world


def _final(w: World, path: str) -> str:
    return dict(w.history[-1].files)[path]


def test_a_seed_builds_the_same_world_and_another_seed_another():
    assert world(3) == world(3)
    assert world(3).rules != world(4).rules


def test_a_boundary_regression_fails_only_the_case_at_the_threshold():
    w = next(w for w in (world(s) for s in range(20)) if w.regression.kind == "boundary")
    rule = w.regression.rule
    own = {t for t in failing(w) if f"::test_{rule.name}[" in t and f"test_{rule.module}.py" in t}
    assert own == {
        f"tests/test_{rule.module}.py::test_{rule.name}[{rule.threshold}-{rule.apply(rule.threshold)}]"
    }


def test_a_rate_regression_fails_cases_at_and_above_the_threshold_only():
    w = next(w for w in (world(s) for s in range(20)) if w.regression.kind == "rate")
    rule = w.regression.rule
    values = dict(w.cases)[rule]
    own = {t for t in failing(w) if f"::test_{rule.name}[" in t and f"test_{rule.module}.py" in t}
    assert own and all(int(t.split("[")[1].split("-")[0]) >= rule.threshold for t in own)
    assert len(own) <= sum(v >= rule.threshold for v in values)


def test_every_failing_test_is_a_test_and_every_caller_calls_the_rule():
    w = world(1)
    assert failing(w) <= every_test(w)
    rule = w.regression.rule
    by_name = {f"{c.module}.{c.name}": c for c in w.composites}
    assert callers(w, rule) and all(rule in by_name[name].calls for name in callers(w, rule))


def test_the_rule_reads_right_before_the_regression_and_wrong_from_it_on():
    w = world(2)
    reg, path = w.regression, f"shop/{w.regression.rule.module}.py"
    good = f"if {reg.rule.param} >= {reg.rule.name.upper()}_FROM:"
    for i, c in enumerate(w.history):
        text = dict(c.files).get(path)
        if text is None:
            continue
        body = text.split(f"def {reg.rule.name}(", 1)[1].split("\ndef ", 1)[0]
        right = good in body and f"* {reg.rule.rate} //" in body
        assert right == (i < reg.at), f"commit {i}: {c.message}"


def _with_currency(source: str, func: str, default: str = "CAD") -> str:
    tree = ast.parse(source)
    f = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == func)
    f.args.kwonlyargs.append(ast.arg("currency", ast.Name("str")))
    f.args.kw_defaults.append(ast.Constant(default))
    return ast.unparse(tree)


def test_an_edit_that_adds_only_the_parameter_is_right_however_it_is_formatted():
    w = world(0)
    rule = next(r for r in w.rules if r.module in w.big)
    source = _final(w, f"shop/{rule.module}.py")
    assert edit_problem(source, _with_currency(source, rule.name), rule.name, "currency", "CAD") is None


def test_an_edit_with_the_wrong_default_or_another_change_is_named_for_what_it_got_wrong():
    w = world(0)
    rule, other = [r for r in w.rules if r.module in w.big][:2]
    source = _final(w, f"shop/{rule.module}.py")
    assert edit_problem(source, _with_currency(source, rule.name, "USD"), rule.name, "currency", "CAD") == (
        "currency does not default to 'CAD'"
    )
    both = _with_currency(_with_currency(source, rule.name), other.name)
    assert edit_problem(source, both, rule.name, "currency", "CAD") == f"{other.name} changed too"
    assert (
        edit_problem(source, source, rule.name, "currency", "CAD")
        == f"{rule.name} has no keyword-only parameter currency"
    )


def test_a_command_that_prints_a_whole_file_from_its_first_line_names_the_file():
    for command in (
        "cat shop/pricing.py",
        "head -n 80 shop/pricing.py",
        "sed -n '1,400p' shop/pricing.py",
        "cd /repo && cat shop/pricing.py",
    ):
        assert viewed_file(command) == "shop/pricing.py", command


def test_a_view_that_starts_further_in_or_does_more_than_print_names_no_file():
    for command in (
        "tail shop/pricing.py",
        "sed -n '120,200p' shop/pricing.py",
        "cat shop/a.py shop/b.py",
        "cat shop/pricing.py | grep FROM",
        "grep -n FROM shop/pricing.py",
    ):
        assert viewed_file(command) is None, command


def test_source_code_with_its_language_folds_by_its_definitions():
    w = world(0)
    source = _final(w, f"shop/{w.big[0]}.py")
    folded = fold(source, language="python")
    assert folded is not None and folded.branch == "code"
    assert f"def {next(r for r in w.rules if r.module == w.big[0]).name}" in folded.body

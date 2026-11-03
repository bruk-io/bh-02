"""Real eval sources are read from this host; a missing one is left out, not a crash (review R23)."""

import ast
from pathlib import Path

from evals import real
from evals.tasks import skipped, tasks


def test_a_source_whose_file_is_missing_is_left_out_and_named_with_the_reason(monkeypatch):
    is_file = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda self: self != real.ISO_3166_2 and is_file(self))
    assert skipped()["xml"] == f"missing {real.ISO_3166_2}"
    assert not any(t.fmt == "xml" for t in tasks())  # and the rest are built as usual
    assert any(t.fmt == "figma" for t in tasks())


def test_every_source_this_host_has_is_in_the_registry():
    built = {t.fmt for t in tasks()}
    assert {"python", "rust", "xml", "pypi"} - built == set(skipped())


def test_a_planted_log_line_is_named_by_its_order_or_its_request_not_its_user():
    by_id = {t.task_id: t for t in tasks()}
    payment, quiet = by_id["log-M-spot-at50"].truth, by_id["log-M-spot-quiet-at50"].truth
    assert payment.token.startswith("ORD-") and len(payment.also) == 1
    assert next(iter(payment.also)).startswith("req-")
    assert quiet.token.startswith("req-") and quiet.also == frozenset()  # the pool line names no order
    assert by_id["json-M-spot-at50"].truth.also == frozenset()


def _scripted(task, original: str) -> str:
    """A correct edit made through ast (then unparsed, so every line is reformatted: the check must
    not care), standing in for a model's."""
    tree = ast.parse(original)
    if "rename" in task.task_id:
        old, new = {
            "check_closed": ("_check_closed", "_ensure_open"),
            "communicate": ("_communicate", "_exchange"),
        }[task.task_id.rsplit("-", 1)[1]]
        for n in ast.walk(tree):
            for field in ("name", "attr", "id"):
                if getattr(n, field, None) == old and not isinstance(n, ast.alias):
                    setattr(n, field, new)
        return ast.unparse(tree)
    cls, method, param, default = {
        "timeout": ("BaseEventLoop", "create_server", "timeout", None),
        "nice": ("Popen", "__init__", "nice", None),
        "color": ("HelpFormatter", "__init__", "color", False),
    }[task.task_id.rsplit("-", 1)[1]]
    target = next(
        d
        for c in ast.walk(tree)
        if isinstance(c, ast.ClassDef) and c.name == cls
        for d in c.body
        if isinstance(d, ast.FunctionDef | ast.AsyncFunctionDef) and d.name == method
    )
    target.args.kwonlyargs.append(ast.arg(param))
    target.args.kw_defaults.append(ast.Constant(default))
    return ast.unparse(tree)


def test_every_edit_task_fails_unedited_and_passes_a_correct_edit_of_the_real_file():
    edits = [t for t in tasks() if t.kind == "edit"]
    assert len(edits) == 5 or "python-edit" in skipped()
    for t in edits:
        original = t.payload()
        assert t.truth.check(original, original) is not None, t.task_id
        assert t.truth.check(original, _scripted(t, original)) is None, t.task_id

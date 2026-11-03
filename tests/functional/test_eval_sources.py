"""Real eval sources are read from this host; a missing one is left out, not a crash (review R23)."""

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

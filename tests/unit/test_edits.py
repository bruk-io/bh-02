"""The edit checks: the asked change made, and nothing else changed, judged by ast."""

from evals.real import added_keyword_only, renamed

_SRC = '''class Loop:
    def _check_closed(self):
        """Raise if closed (_check_closed is the old name)."""
        if self.closed:
            raise RuntimeError("closed")

    def serve(self, host, port=None, *, backlog=100):
        self._check_closed()
        return host, port, backlog


def helper(loop):
    loop._check_closed()
'''

_ADD = added_keyword_only("Loop", "serve", "timeout", "None")


def test_a_keyword_only_parameter_added_anywhere_after_the_star_passes_however_formatted():
    edited = _SRC.replace("*, backlog=100):", "*,\n              backlog=100,\n              timeout=None):")
    assert _ADD(_SRC, edited) is None
    assert _ADD(_SRC, _SRC.replace("*, backlog=100):", "*, timeout=None, backlog=100):")) is None


def test_a_keyword_only_parameter_that_is_positional_defaults_wrongly_or_brings_other_changes_fails():
    assert "not keyword-only" in _ADD(_SRC, _SRC.replace("port=None, *", "port=None, timeout=None, *"))
    assert "defaults to 5" in _ADD(_SRC, _SRC.replace("backlog=100):", "backlog=100, timeout=5):"))
    also = _SRC.replace("backlog=100):", "backlog=100, timeout=None):").replace(
        "return host,", "return None,"
    )
    assert _ADD(_SRC, also) == "something besides timeout changed"
    assert "does not parse" in _ADD(_SRC, _SRC.replace("def serve", "def serve("))
    assert "missing" in _ADD(_SRC, _SRC.replace("def serve", "def serve_all"))


_RENAME = renamed("_check_closed", "_ensure_open")


def test_a_rename_of_every_use_passes_and_a_docstring_may_keep_the_old_name_or_take_the_new():
    edited = _SRC.replace("def _check_closed", "def _ensure_open").replace(
        "._check_closed()", "._ensure_open()"
    )
    assert "_check_closed is the old name" in edited and _RENAME(_SRC, edited) is None
    assert _RENAME(_SRC, _SRC.replace("_check_closed", "_ensure_open")) is None  # what P3's smoke runs did


def test_a_rename_that_misses_a_use_or_changes_more_fails_and_says_where():
    missed = _SRC.replace("def _check_closed", "def _ensure_open").replace(
        "        self._check_closed()", "        self._ensure_open()"
    )
    assert _RENAME(_SRC, missed) == "_check_closed is still used on line 13"  # helper's call
    more = _SRC.replace("_check_closed", "_ensure_open").replace("RuntimeError", "ValueError")
    assert _RENAME(_SRC, more).startswith("something besides the rename changed")

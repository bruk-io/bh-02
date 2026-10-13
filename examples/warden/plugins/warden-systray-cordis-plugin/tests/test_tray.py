"""menu_labels on its own: the only pure, AppKit-free piece of this plugin."""

import pytest

# rumps installs only on darwin; the package imports it, so without it these tests skip by name.
pytest.importorskip("rumps")

from warden_systray_cordis_plugin import menu_labels  # noqa: E402


def test_names_come_back_sorted() -> None:
    assert menu_labels(["worker", "example"]) == ["example", "worker"]


def test_no_names_is_a_placeholder_label() -> None:
    assert menu_labels([]) == ["(no processes)"]

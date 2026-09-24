"""menu_labels on its own: the only pure, AppKit-free piece of this plugin."""

from warden_systray_cordis_plugin import menu_labels


def test_names_come_back_sorted() -> None:
    assert menu_labels(["worker", "example"]) == ["example", "worker"]


def test_no_names_is_a_placeholder_label() -> None:
    assert menu_labels([]) == ["(no processes)"]

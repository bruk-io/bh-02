"""The registry value on its own: entries by name, each its own remover."""

import pytest

from warden_cordis_plugin import Process, Processes


def test_each_registration_is_its_own_entry_and_its_remover_takes_only_that() -> None:
    processes = Processes()
    remove_web = processes.register("web", Process(pid=1))
    processes.register("worker", Process(pid=2))
    assert sorted(processes.names) == ["web", "worker"]
    remove_web()
    assert processes.names == ["worker"]
    remove_web()  # idempotent: removing twice takes nothing else
    assert processes.get("web") is None
    assert processes.get("worker") == Process(pid=2)


def test_two_processes_cannot_share_a_name() -> None:
    processes = Processes()
    processes.register("web", Process(pid=1))
    with pytest.raises(ValueError, match="already registered"):
        processes.register("web", Process(pid=2))

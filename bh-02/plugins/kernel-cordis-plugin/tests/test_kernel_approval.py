"""`approval`: the one rule for whether the model's code runs unasked, and its row."""

from collections.abc import Mapping
from typing import Any

from cordis.loader import resolve
from cordis.testing import drive
from kernel_cordis_plugin import UNENFORCED, Approval, approval, is_confined

_CONFINED = {**UNENFORCED, "fs_write": "enforced", "network": "enforced"}
_REQUEST = {"name": "python", "input": {"code": "print(1)"}}


class _Jail:
    """A `jail` that reports the grades it is given, and starts nothing."""

    def __init__(self, report: Mapping[str, str]) -> None:
        self.grades = report

    def report(self) -> Mapping[str, str]:
        return self.grades


class _Person:
    """An `output` whose person answers `answer` and keeps every question."""

    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.asked: list[Mapping[str, Any]] = []

    async def confirm(self, request: Mapping[str, Any]) -> bool:
        self.asked.append(request)
        return self.answer


def test_confined_means_writes_and_network_are_enforced() -> None:
    assert is_confined({"fs_write": "enforced", "network": "enforced", "fs_read": "unenforced"})
    assert not is_confined({"fs_write": "enforced", "network": "best_effort"})
    assert not is_confined(UNENFORCED)
    assert not is_confined({})


async def test_confined_code_runs_at_once_and_nobody_is_asked() -> None:
    person = _Person(False)
    granted = Approval(_Jail(_CONFINED), person)
    assert granted.confined
    assert await granted.approve(_REQUEST)
    assert person.asked == []


async def test_unconfined_code_runs_on_the_person_s_answer_to_the_request_as_it_came() -> None:
    yes, no = _Person(True), _Person(False)
    assert await Approval(_Jail(UNENFORCED), yes).approve(_REQUEST)
    assert not await Approval(_Jail(UNENFORCED), no).approve(_REQUEST)
    assert yes.asked == [_REQUEST] and no.asked == [_REQUEST]
    assert not Approval(_Jail(UNENFORCED), yes).confined


async def test_with_nobody_to_ask_unconfined_code_never_runs() -> None:
    assert not await Approval(_Jail(UNENFORCED)).approve(_REQUEST)
    assert await Approval(_Jail(_CONFINED)).approve(_REQUEST)  # confined: nobody needed


async def test_confined_is_read_from_the_jail_each_time() -> None:
    jail, person = _Jail(_CONFINED), _Person(False)
    granted = Approval(jail, person)
    assert await granted.approve(_REQUEST)
    jail.grades = {**_CONFINED, "network": "best_effort"}
    assert not granted.confined and not await granted.approve(_REQUEST)
    assert person.asked == [_REQUEST]


async def test_the_row_binds_approval_over_the_jail_and_the_output() -> None:
    jail, person = _Jail(UNENFORCED), _Person(True)
    effects = await drive(approval(jail=jail, output=person))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "approval")]
    assert effects[0].args[1] == Approval(jail, person)


def test_the_row_depends_on_the_jail_and_the_output_not_the_kernel() -> None:
    """`/clear` restarts the kernel: the approval row, and the loop's and the extensions' hold on
    it, stay up."""
    row = resolve("kernel:approval")
    assert row.inject == {"jail", "output"} and row.provides == {"approval"}

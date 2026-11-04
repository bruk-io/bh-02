"""The grants broker (`Broker`): what it asks, remembers, applies and revokes (decision-0012 item 7)."""

import asyncio
import hashlib
from pathlib import Path

import pytest

from runner_cordis_plugin import Broker, Entry, Outcome, Scope, Unknown
from runner_cordis_plugin.grants import Answer, Asker, Grant, Kind, Request, Source
from runner_cordis_plugin.store import FILE, Refused, read, write

NET = Request(Grant(Kind.NET, "example.com", 443), Asker(Source.ROW, "python"), "fetch packages")
DATA = Request(Grant(Kind.READ, "/data/in"), Asker(Source.INPUT, "python"), "reads the data")


class _Prompt:
    """A prompt that answers from a script, and says what it was asked."""

    def __init__(self, *answers: Answer | None) -> None:
        self.answers = list(answers)
        self.asked: list[Request] = []

    async def __call__(self, request: Request) -> Answer | None:
        self.asked.append(request)
        return self.answers.pop(0)


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    made = tmp_path / "grants"
    made.mkdir(mode=0o700)
    return made


async def _settled() -> None:
    """Let what the broker does in the background (a store read on a thread, a question) finish."""
    await asyncio.sleep(0.2)


async def test_an_ask_with_no_prompt_served_is_a_no_and_records_nothing(directory: Path) -> None:
    broker = Broker(directory)
    assert await broker.ask(NET) is Outcome.NO
    assert await broker.list() == ()
    assert len(await broker.granted()) == 0


async def test_once_is_applied_for_the_session_and_not_asked_again(directory: Path) -> None:
    broker = Broker(directory)
    prompt = _Prompt(Answer.ONCE)
    broker.serve(prompt)
    assert await broker.ask(NET) is Outcome.ONCE
    assert await broker.ask(NET) is Outcome.STANDING
    assert (await broker.granted()).items == (NET.grant,)
    assert prompt.asked == [NET]
    assert read(directory) == ()  # once never reaches the store


async def test_always_goes_to_the_store_and_a_second_broker_reads_it(directory: Path) -> None:
    broker = Broker(directory)
    broker.serve(_Prompt(Answer.ALWAYS))
    assert await broker.ask(NET) is Outcome.ALWAYS
    assert read(directory) == (NET,)
    other = Broker(directory)  # another process: no session, the same project
    assert (await other.granted()).items == (NET.grant,)
    assert await other.ask(NET) is Outcome.STANDING


async def test_no_is_remembered_and_not_asked_again(directory: Path) -> None:
    broker = Broker(directory)
    prompt = _Prompt(Answer.NO)
    broker.serve(prompt)
    assert await broker.ask(NET) is Outcome.NO
    assert await broker.ask(NET) is Outcome.NO
    assert len(prompt.asked) == 1 and len(await broker.granted()) == 0


async def test_a_withdrawn_question_records_nothing_and_is_asked_again(directory: Path) -> None:
    broker = Broker(directory)
    prompt = _Prompt(None, Answer.ONCE)
    broker.serve(prompt)
    assert await broker.ask(NET) is Outcome.NO
    assert await broker.list() == ()
    assert await broker.ask(NET) is Outcome.ONCE
    assert len(prompt.asked) == 2


async def test_two_asks_for_one_grant_at_once_are_one_question(directory: Path) -> None:
    broker = Broker(directory)
    gate = asyncio.Event()
    asked: list[Request] = []

    async def prompt(request: Request) -> Answer | None:
        asked.append(request)
        await gate.wait()
        return Answer.ONCE

    broker.serve(prompt)
    first = asyncio.ensure_future(broker.ask(NET))
    second = asyncio.ensure_future(broker.ask(NET))
    await _settled()
    gate.set()
    assert await first is Outcome.ONCE and await second is Outcome.ONCE
    assert len(asked) == 1


async def test_questions_are_asked_one_at_a_time(directory: Path) -> None:
    broker = Broker(directory)
    gate = asyncio.Event()
    open_now = 0
    most = 0

    async def prompt(request: Request) -> Answer | None:
        nonlocal open_now, most
        open_now += 1
        most = max(most, open_now)
        await gate.wait()
        open_now -= 1
        return Answer.ONCE

    broker.serve(prompt)
    asks = [asyncio.ensure_future(broker.ask(each)) for each in (NET, DATA)]
    await _settled()
    gate.set()
    await asyncio.gather(*asks)
    assert most == 1


async def test_a_need_is_asked_once_when_a_prompt_is_served_applied_while_held_and_remembered(
    directory: Path,
) -> None:
    broker = Broker(directory)
    prompt = _Prompt(Answer.ONCE)
    release_one = broker.need(NET)
    release_two = broker.need(NET)  # two rows, one grant: one question
    assert prompt.asked == [] and len(await broker.granted()) == 0  # nothing to ask until served
    broker.serve(prompt)
    await _settled()
    assert prompt.asked == [NET]
    assert (await broker.granted()).items == (NET.grant,)
    release_one()
    assert len(await broker.granted()) == 1  # the other row still holds it
    release_two()
    assert len(await broker.granted()) == 0  # applied only while some row holds it
    broker.need(NET)  # the row remounts: remembered, not asked again
    await _settled()
    assert prompt.asked == [NET]
    assert (await broker.granted()).items == (NET.grant,)


async def test_a_need_that_is_already_granted_is_not_asked(directory: Path) -> None:
    write(directory, [NET])
    broker = Broker(directory)
    prompt = _Prompt()
    broker.serve(prompt)
    broker.need(NET)
    await _settled()
    assert prompt.asked == []


async def test_a_need_answered_always_stays_after_its_row_leaves(directory: Path) -> None:
    broker = Broker(directory)
    broker.serve(_Prompt(Answer.ALWAYS))
    release = broker.need(NET)
    await _settled()
    release()
    assert (await broker.granted()).items == (NET.grant,)


async def test_a_need_answered_no_is_not_applied_and_not_asked_again(directory: Path) -> None:
    broker = Broker(directory)
    prompt = _Prompt(Answer.NO)
    broker.need(NET)
    broker.serve(prompt)
    await _settled()
    assert len(await broker.granted()) == 0
    assert await broker.ask(NET) is Outcome.NO
    assert len(prompt.asked) == 1


async def test_a_need_held_when_a_prompt_is_already_served_is_asked_at_once(directory: Path) -> None:
    broker = Broker(directory)
    prompt = _Prompt(Answer.ONCE)
    broker.serve(prompt)
    broker.need(DATA)
    await _settled()
    assert prompt.asked == [DATA]


async def test_a_second_prompt_is_refused_and_a_released_one_can_be_replaced(directory: Path) -> None:
    broker = Broker(directory)
    release = broker.serve(_Prompt())
    with pytest.raises(RuntimeError, match="already served"):
        broker.serve(_Prompt())
    release()
    broker.serve(_Prompt())


async def test_releasing_the_prompt_withdraws_a_question_under_way(directory: Path) -> None:
    broker = Broker(directory)
    gate = asyncio.Event()

    async def prompt(request: Request) -> Answer | None:
        await gate.wait()
        return Answer.ONCE

    release = broker.serve(prompt)
    asking = asyncio.ensure_future(broker.ask(NET))
    await _settled()
    release()
    assert await asking is Outcome.NO
    assert await broker.list() == ()


async def test_ids_are_short_and_stable_and_list_says_who_asked(directory: Path) -> None:
    broker = Broker(directory)
    broker.serve(_Prompt(Answer.ALWAYS, Answer.ONCE))
    await broker.ask(NET)
    await broker.ask(DATA)
    listed = await broker.list()
    assert [entry.scope for entry in listed] == [Scope.PROJECT, Scope.SESSION]
    assert [entry.answer for entry in listed] == [Answer.ALWAYS, Answer.ONCE]
    ids = [entry.id for entry in listed]
    assert all(len(each) == 8 and int(each, 16) >= 0 for each in ids) and ids[0] != ids[1]
    assert ids[0] == hashlib.sha256(b"net: example.com:443").hexdigest()[:8]
    assert [entry.id for entry in await Broker(directory).list()] == ids[:1]
    line = str(listed[0])
    for part in (ids[0], "net example.com:443", "always (project)", "row python", "fetch packages"):
        assert part in line


async def test_revoking_a_session_grant_leaves_the_session(directory: Path) -> None:
    broker = Broker(directory)
    broker.serve(_Prompt(Answer.ONCE, Answer.ONCE))
    await broker.ask(NET)
    (entry,) = await broker.list()
    assert (await broker.revoke(entry.id)).request == NET
    assert await broker.list() == () and len(await broker.granted()) == 0
    assert await broker.ask(NET) is Outcome.ONCE  # asked afresh


async def test_revoking_an_always_grant_removes_it_from_the_store_for_every_reader(directory: Path) -> None:
    write(directory, [NET, DATA])
    broker = Broker(directory)
    entry = next(each for each in await broker.list() if each.request == NET)
    await broker.revoke(entry.id)
    assert read(directory) == (DATA,)
    assert (await Broker(directory).granted()).items == (DATA.grant,)


async def test_an_unknown_id_is_refused_naming_the_ids_there_are(directory: Path) -> None:
    write(directory, [NET])
    broker = Broker(directory)
    (entry,) = await broker.list()
    with pytest.raises(Unknown, match=entry.id):
        await broker.revoke("deadbeef")


async def test_the_store_is_read_at_each_call_so_another_process_counts(directory: Path) -> None:
    broker = Broker(directory)
    assert len(await broker.granted()) == 0
    write(directory, [NET])
    assert (await broker.granted()).items == (NET.grant,)
    write(directory, [])
    assert len(await broker.granted()) == 0


async def test_a_refused_store_grants_nothing_says_so_and_is_never_written_over(directory: Path) -> None:
    (directory / FILE).write_text("this is not toml = = =")
    broker = Broker(directory)
    prompt = _Prompt(Answer.ALWAYS)
    broker.serve(prompt)
    assert len(await broker.granted()) == 0
    assert "not TOML" in broker.problem()
    assert await broker.ask(NET) is Outcome.ONCE  # kept for the session: the store can't hold it
    assert (directory / FILE).read_text() == "this is not toml = = ="
    with pytest.raises(Refused):
        read(directory)
    (directory / FILE).unlink()
    await broker.granted()
    assert broker.problem() == ""


async def test_on_change_hears_answers_needs_and_revokes_until_released(directory: Path) -> None:
    broker = Broker(directory)
    heard: list[None] = []
    stop = broker.on_change(lambda: heard.append(None))
    broker.serve(_Prompt(Answer.ONCE))
    release = broker.need(NET)
    await _settled()
    after_need = len(heard)
    assert after_need >= 2  # the hold and the answer
    release()
    assert len(heard) == after_need + 1
    (entry,) = await broker.list()
    await broker.revoke(entry.id)
    assert len(heard) == after_need + 2
    stop()
    release_again = broker.need(NET)
    release_again()
    assert len(heard) == after_need + 2


async def test_a_broker_with_no_store_keeps_only_the_session(tmp_path: Path) -> None:
    broker = Broker(None)
    broker.serve(_Prompt(Answer.ALWAYS))
    assert await broker.ask(NET) is Outcome.ONCE
    assert (await broker.granted()).items == (NET.grant,)


def test_an_entry_is_a_value() -> None:
    entry = Entry("abcd1234", NET, Answer.NO, Scope.SESSION)
    assert entry == Entry("abcd1234", NET, Answer.NO, Scope.SESSION)

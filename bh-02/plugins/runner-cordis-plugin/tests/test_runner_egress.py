"""A running jail's egress over a fake wire (decision-0012 items 4 and 6): what is granted reaches the
proxy while the program runs, a refusal is asked or told, and nothing outlives the jail. The real
jail's are in `test_runner_live_egress.py`."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from runner_cordis_plugin.broker import Broker
from runner_cordis_plugin.egress import Egress, Ended, asked_as
from runner_cordis_plugin.grants import Answer, Asker, Grant, Kind, Request, Source

PERIOD = 0.01
SVC = Grant(Kind.NET, "svc.test", 443)


@dataclass(frozen=True)
class _Named:
    host: str
    port: int


@dataclass(frozen=True)
class _Decision:
    verdict: str
    destination: _Named
    reason: str
    address: str = ""


def _refused(host: str, reason: str = "not-granted", address: str = "", port: int = 443) -> _Decision:
    return _Decision("refused", _Named(host, port), reason, address)


@dataclass
class _Wire:
    queued: list[_Decision] = field(default_factory=list)
    allowed: list[Grant] = field(default_factory=list)
    revoked: list[Grant] = field(default_factory=list)
    gone: bool = False
    over: bool = False  # the proxy has ended: a change raises

    def allow(self, grant: Grant) -> None:
        if self.over:
            raise Ended("the jail's egress proxy has ended")
        self.allowed.append(grant)

    def revoke(self, grant: Grant) -> None:
        if self.over:
            raise Ended("the jail's egress proxy has ended")
        self.revoked.append(grant)

    def decisions(self) -> list[_Decision]:
        taken, self.queued = self.queued, []
        return taken

    def ended(self) -> bool:
        return self.gone


class _Person:
    """The prompt: answers `answer`, keeps each request, and can hold the question open."""

    def __init__(self, answer: Answer | None = Answer.ONCE, *, holding: bool = False) -> None:
        self.answer = answer
        self.asked: list[Request] = []
        self.release = asyncio.Event()
        self.holding = holding

    async def __call__(self, request: Request) -> Answer | None:
        self.asked.append(request)
        if self.holding:
            await self.release.wait()
        return self.answer


async def _until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(5):
        while not condition():
            await asyncio.sleep(0.005)


async def _running(wire: _Wire, broker: Broker, held: tuple[Grant, ...] = (), *, agent: str = "") -> Egress:
    running = Egress(wire, broker, asker=asked_as("python", agent), held=held, period=PERIOD)
    running.begin()
    return running


async def test_a_grant_made_while_the_jail_runs_is_allowed_and_a_revoke_is_revoked() -> None:
    broker = Broker(None)
    person = _Person()
    broker.serve(person)
    wire = _Wire()
    running = await _running(wire, broker)
    try:
        assert await broker.ask(Request(SVC, Asker(Source.ROW, "requester"), "it fetches")) == "once"
        await _until(lambda: wire.allowed == [SVC])
        (entry,) = await broker.list()
        await broker.revoke(entry.id)
        await _until(lambda: wire.revoked == [SVC])
    finally:
        await running.end()
    assert wire.allowed == [SVC]


async def test_what_the_start_already_held_is_not_allowed_again_and_is_revoked_when_taken_back() -> None:
    broker = Broker(None)
    broker.serve(_Person())
    await broker.ask(Request(SVC, Asker(Source.ROW, "requester"), "it fetches"))
    wire = _Wire()
    running = await _running(wire, broker, held=(SVC,))
    try:
        (entry,) = await broker.list()
        await broker.revoke(entry.id)
        await _until(lambda: wire.revoked == [SVC])
    finally:
        await running.end()
    assert wire.allowed == []


async def test_a_jail_whose_proxy_has_ended_is_skipped_and_nothing_is_told() -> None:
    broker = Broker(None)
    broker.serve(_Person())
    wire = _Wire(over=True)
    running = await _running(wire, broker)
    try:
        await broker.ask(Request(SVC, Asker(Source.ROW, "requester"), "it fetches"))
        await asyncio.sleep(0.1)
    finally:
        await running.end()
    assert wire.allowed == [] and broker.told() == ()


async def test_a_destination_that_was_not_granted_is_asked_as_the_programs_input_then_allowed_on_yes() -> (
    None
):
    broker = Broker(None)
    person = _Person()
    broker.serve(person)
    wire = _Wire(queued=[_refused("svc.test")])
    running = await _running(wire, broker)
    try:
        await _until(lambda: wire.allowed == [SVC])
    finally:
        await running.end()
    (request,) = person.asked
    assert request.grant == SVC
    assert request.asker == Asker(Source.INPUT, "python")
    assert "svc.test:443" in request.reason and "refused" in request.reason


async def test_a_private_address_is_asked_as_the_ip_literal_alone_never_the_name_or_a_wildcard() -> None:
    broker = Broker(None)
    person = _Person()
    broker.serve(person)
    wire = _Wire(queued=[_refused("svc.test", "private-address", "10.0.0.5")])
    running = await _running(wire, broker)
    try:
        await _until(lambda: wire.allowed == [Grant(Kind.NET, "10.0.0.5", 443)])
    finally:
        await running.end()
    assert [request.grant for request in person.asked] == [Grant(Kind.NET, "10.0.0.5", 443)]
    assert "10.0.0.5" in person.asked[0].reason


async def test_a_refusal_with_nothing_to_grant_is_told_never_asked_and_told_once() -> None:
    broker = Broker(None)
    person = _Person()
    broker.serve(person)
    wire = _Wire(
        queued=[
            _refused("nowhere.test", "unresolved"),
            _refused("nowhere.test", "unresolved"),
            _refused("odd.test", "address-unparseable"),
            _refused("odd.test", "authority-unparseable"),
        ]
    )
    running = await _running(wire, broker)
    try:
        await _until(lambda: wire.queued == [])
        await asyncio.sleep(0.1)
    finally:
        await running.end()
    assert person.asked == []
    told = broker.told()
    assert len(told) == 3
    assert "nowhere.test:443" in told[0] and "did not resolve" in told[0]
    assert broker.told() == ()  # taking them empties it


async def test_the_repeats_of_a_refusal_under_question_are_one_question() -> None:
    broker = Broker(None)
    person = _Person(holding=True)
    broker.serve(person)
    wire = _Wire(queued=[_refused("svc.test")] * 3)
    running = await _running(wire, broker)
    try:
        await _until(lambda: person.asked != [])
        wire.queued = [_refused("svc.test")] * 3
        await _until(lambda: wire.queued == [])
        await asyncio.sleep(0.05)
        person.release.set()
        await _until(lambda: wire.allowed == [SVC])
    finally:
        await running.end()
    assert len(person.asked) == 1


async def test_a_declined_destination_is_not_asked_again() -> None:
    broker = Broker(None)
    person = _Person(Answer.NO)
    broker.serve(person)
    wire = _Wire(queued=[_refused("svc.test")])
    running = await _running(wire, broker)
    try:
        await _until(lambda: len(person.asked) == 1)
        await asyncio.sleep(0.1)
        wire.queued = [_refused("svc.test")]
        await _until(lambda: wire.queued == [])
        await asyncio.sleep(0.1)
    finally:
        await running.end()
    assert len(person.asked) == 1 and wire.allowed == []


async def test_the_poller_ends_with_the_jail_and_end_leaves_no_task_and_no_listener() -> None:
    before = asyncio.all_tasks()
    broker = Broker(None)
    person = _Person(holding=True)
    broker.serve(person)
    wire = _Wire(queued=[_refused("svc.test")])
    running = await _running(wire, broker)
    await _until(lambda: person.asked != [])
    wire.gone = True
    await asyncio.sleep(0.1)  # the poller ended by itself
    await running.end()
    person.release.set()
    await asyncio.sleep(0.05)
    assert {task for task in asyncio.all_tasks() - before if not task.done()} == set()


async def test_a_sub_agent_s_program_s_refusal_is_asked_as_the_agent_by_its_label() -> None:
    broker = Broker(None)
    person = _Person()
    broker.serve(person)
    wire = _Wire(queued=[_refused("svc.test")])
    running = await _running(wire, broker, agent="scout-1 (explore)")
    try:
        await _until(lambda: wire.allowed == [SVC])
    finally:
        await running.end()
    (request,) = person.asked
    assert request.asker == Asker(Source.AGENT, "scout-1 (explore)")
    assert str(request.asker) == "agent scout-1 (explore)"  # the person sees which agent asks
    assert asked_as("python", "") == Asker(Source.INPUT, "python")

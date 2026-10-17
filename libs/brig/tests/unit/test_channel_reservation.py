"""The channel directory and reserve-then-start (decision-184, TASK-0079.05).

`Jail.channel(name)` reserves a socket in the runtime's channel directory,
`<jail_dir>/chan`, for a channel the `Spec` declares; `jail.start(argv,
channel=reservation)` binds the process to it. Driven through
`brig.runtime.fake`, which reserves, refuses and resolves the way
`HostRuntime` does but hands out a relay endpoint apart from the bound path,
so a caller that dials the wrong one is caught. The mechanisms' half (bwrap
binds the directory, seatbelt grants its subpath) is pinned here by their
renders; seatbelt's by its RENDERED PROFILE only, since no darwin host runs
this suite.
"""

import dataclasses
import json

import pytest

from brig.core import Channel, ChannelKind, FsPolicy, ReadModel, Spec
from brig.core.runtime import RuntimeKind
from brig.mech import CompileCtx
from brig.mech.bwrap import ChannelInsideWriteDeny, bwrap
from brig.mech.seatbelt import ChannelInsideWriteDeny as SeatbeltChannelInsideWriteDeny
from brig.mech.seatbelt import render_sbpl
from brig.run import Jail, Reservation, ReservationRefused, UnknownChannel, WaitReadyTimeout
from brig.run.runtime import reservation_refusal
from brig.runtime.fake import FakeRuntime
from brig.stack import Stack

pytestmark = pytest.mark.unit

_JAIL_DIR = "/run/brig/jail0"
_CHAN = f"{_JAIL_DIR}/chan"
_TOKEN = "0123456789abcdef"


def _spec(*, channels: bool = True) -> Spec:
    declared = (Channel(name="ctl", kind=ChannelKind.LISTEN),)
    return Spec(channels=declared if channels else ())


def _create(runtime: FakeRuntime, spec: Spec | None = None) -> Jail:
    return Jail.create(
        Stack([]).compile(_spec() if spec is None else spec),
        runtime=runtime,
        cwd="/work",
        jail_id="fake-jail",
        jail_dir=_JAIL_DIR,
    )


def _started(runtime: FakeRuntime) -> list[str]:
    return [call.method for call in runtime.calls if call.method == "start"]


# ---------------------------------------------------------------------------
# Only a declared channel can be reserved or started on.
# ---------------------------------------------------------------------------


def test_an_undeclared_channel_is_refused_saying_what_to_declare() -> None:
    runtime = FakeRuntime()
    jail = _create(runtime)
    with pytest.raises(UnknownChannel) as refusal:
        jail.channel("other")
    message = str(refusal.value)
    assert refusal.value.channel == "other"
    assert "Jail.channel" in message and "Channel(name='other'" in message, message
    assert "reserve" not in [call.method for call in runtime.calls]


def test_a_start_on_an_undeclared_channel_is_refused_and_starts_nothing() -> None:
    runtime = FakeRuntime()
    jail = _create(runtime)
    reservation = dataclasses.replace(jail.channel("ctl"), channel="other")
    with pytest.raises(UnknownChannel, match="Jail.start"):
        jail.start(["w", reservation.bound_path], channel=reservation)
    assert _started(runtime) == []


# ---------------------------------------------------------------------------
# A reservation is a fresh socket in the channel directory, and the process
# carries it.
# ---------------------------------------------------------------------------


def test_a_reservation_is_a_fresh_socket_in_the_channel_directory() -> None:
    jail = _create(FakeRuntime())
    first, second = jail.channel("ctl"), jail.channel("ctl")
    assert first.channel == second.channel == "ctl"
    assert first.bound_path != second.bound_path
    for reservation in (first, second):
        assert reservation.bound_path.rsplit("/", 1)[0] == _CHAN
        # The fake hands out a relay path, as a runtime sharing no socket would.
        assert reservation.endpoint != reservation.bound_path


def test_a_process_carries_its_channel_bound_path_and_endpoint_across_to_dict() -> None:
    runtime = FakeRuntime()
    jail = _create(runtime)
    reservation = jail.channel("ctl")
    process = jail.start(["w", reservation.bound_path], channel=reservation)
    plain = jail.start(["v"])

    assert (process.channel, process.bound_path, process.endpoint) == (
        "ctl",
        reservation.bound_path,
        reservation.endpoint,
    )
    assert (plain.channel, plain.bound_path, plain.endpoint) == (None, None, None)

    d = json.loads(json.dumps(jail.to_dict()))
    assert d["version"] == 10
    assert [(p["channel"], p["bound_path"]) for p in d["processes"]] == [
        ("ctl", reservation.bound_path),
        (None, None),
    ]
    again = Jail.from_dict(d, runtimes={RuntimeKind.FAKE: runtime})
    assert [(p.channel, p.bound_path, p.endpoint) for p in again.processes()] == [
        ("ctl", reservation.bound_path, reservation.endpoint),
        (None, None, None),
    ]


# ---------------------------------------------------------------------------
# A reservation can't name a path outside chan/, or be used twice.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bound_path",
    [
        f"{_JAIL_DIR}/procs/{_TOKEN}.sock",
        f"{_JAIL_DIR}/{_TOKEN}.sock",
        f"{_CHAN}/../procs/{_TOKEN}.sock",
        f"{_CHAN}/sub/{_TOKEN}.sock",
        f"/elsewhere/chan/{_TOKEN}.sock",
        f"{_CHAN}/jail.json",
        f"{_CHAN}/{_TOKEN}.sock/x",
    ],
)
def test_a_reservation_cannot_name_a_path_outside_the_channel_directory(bound_path: str) -> None:
    """The start refuses before anything is made; the control is the same
    reservation, unforged, which starts."""
    runtime = FakeRuntime()
    jail = _create(runtime)
    reservation = jail.channel("ctl")
    forged = dataclasses.replace(reservation, bound_path=bound_path)
    with pytest.raises(ReservationRefused, match="not this jail's"):
        jail.start(["w", bound_path], channel=forged)
    assert _started(runtime) == []

    jail.start(["w", reservation.bound_path], channel=reservation)
    assert _started(runtime) == ["start"]


def test_a_forged_endpoint_is_refused() -> None:
    runtime = FakeRuntime()
    jail = _create(runtime)
    forged = dataclasses.replace(jail.channel("ctl"), endpoint="/elsewhere/ctl.sock")
    with pytest.raises(ReservationRefused, match="endpoint"):
        jail.start(["w"], channel=forged)
    assert _started(runtime) == []


def test_a_reservation_binds_one_process_only() -> None:
    runtime = FakeRuntime()
    jail = _create(runtime)
    reservation = jail.channel("ctl")
    jail.start(["w"], channel=reservation)
    with pytest.raises(ReservationRefused, match="already binds"):
        jail.start(["w"], channel=reservation)
    assert _started(runtime) == ["start"]


def test_the_refusal_is_pure_and_names_each_reason() -> None:
    good = Reservation(channel="ctl", bound_path=f"{_CHAN}/{_TOKEN}.sock", endpoint="e")
    assert reservation_refusal(good, chan=_CHAN, endpoint="e", taken=frozenset()) is None
    cases = {
        "not directly in": dataclasses.replace(good, bound_path=f"{_JAIL_DIR}/{_TOKEN}.sock"),
        "socket name": dataclasses.replace(good, bound_path=f"{_CHAN}/x.sock"),
        "endpoint": dataclasses.replace(good, endpoint="f"),
    }
    for reason, reservation in cases.items():
        refusal = reservation_refusal(reservation, chan=_CHAN, endpoint="e", taken=frozenset())
        assert refusal is not None and reason in refusal, refusal
    taken = frozenset({good.bound_path})
    refusal = reservation_refusal(good, chan=_CHAN, endpoint="e", taken=taken)
    assert refusal is not None and "already binds" in refusal


# ---------------------------------------------------------------------------
# Readiness is the runtime's.
# ---------------------------------------------------------------------------


def test_wait_ready_asks_the_runtime_and_times_out_by_name() -> None:
    runtime = FakeRuntime()
    jail = _create(runtime)
    reservation = jail.channel("ctl")
    process = jail.start(["w"], channel=reservation)
    process.wait_ready(timeout=1.0)
    assert any(call.method == "ready" for call in runtime.calls)

    runtime.listening = False
    with pytest.raises(WaitReadyTimeout) as timeout:
        process.wait_ready(timeout=0.05)
    assert (timeout.value.channel, timeout.value.endpoint) == ("ctl", reservation.endpoint)


def test_wait_ready_on_a_process_with_no_channel_says_how_to_start_one() -> None:
    process = _create(FakeRuntime()).start(["w"])
    with pytest.raises(ValueError, match=r"channel=jail\.channel"):
        process.wait_ready(timeout=0.05)


# ---------------------------------------------------------------------------
# The mechanisms grant the channel directory once, when a channel is declared.
# ---------------------------------------------------------------------------

_CHAN_BIND = ("--bind", _CHAN, _CHAN)


def _bwrap_spec(*, channels: bool = True, write_denies: tuple[str, ...] = ()) -> Spec:
    return Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/usr",),
            write_allows=("/srv/ws",),
            write_denies=write_denies,
        ),
        channels=_spec(channels=channels).channels,
    )


def _bwrap_ctx(*paths: str) -> CompileCtx:
    every = ("/usr", "/srv/ws", *paths)
    return CompileCtx(
        jail_dir=_JAIL_DIR,
        platform="linux",
        resolved_paths={path: path for path in every},
        path_exists={path: False for path in every},
    )


def _runs(argv: tuple[str, ...], run: tuple[str, ...]) -> int:
    return sum(argv[i : i + len(run)] == run for i in range(len(argv)))


def test_bwrap_binds_the_channel_directory_once_only_when_a_channel_is_declared() -> None:
    assert bwrap.compile(_bwrap_spec(), _bwrap_ctx()).wrap(()).count(_CHAN) == 2
    assert _runs(bwrap.compile(_bwrap_spec(), _bwrap_ctx()).wrap(()), _CHAN_BIND) == 1
    assert _CHAN not in bwrap.compile(_bwrap_spec(channels=False), _bwrap_ctx()).wrap(())
    assert CompileCtx(jail_dir=_JAIL_DIR, platform="linux").channel_dir == _CHAN


def test_bwrap_binds_the_channel_directory_once_for_every_channel() -> None:
    """decision-186: two declared channels are one grant, the channel
    directory, where each start's socket is reserved."""
    spec = Spec(
        fs=FsPolicy(read_model=ReadModel.ALLOW_LIST, read_allows=("/usr",)),
        channels=(
            Channel(name="ctl", kind=ChannelKind.LISTEN),
            Channel(name="aux", kind=ChannelKind.LISTEN),
        ),
    )
    argv = bwrap.compile(spec, _bwrap_ctx()).wrap(())
    assert _runs(argv, _CHAN_BIND) == 1, argv


def test_bwrap_mounts_a_carve_out_under_the_channel_directory_after_it() -> None:
    deny = f"{_CHAN}/held"
    argv = bwrap.compile(_bwrap_spec(write_denies=(deny,)), _bwrap_ctx(deny)).wrap(())
    carve_out = ("--tmpfs", deny, "--remount-ro", deny)
    assert _runs(argv, carve_out) == 1, argv
    bind_at = next(i for i in range(len(argv)) if argv[i : i + 3] == _CHAN_BIND)
    assert argv.index("--tmpfs") > bind_at


@pytest.mark.parametrize("deny", [_CHAN, _JAIL_DIR])
def test_a_write_deny_at_or_above_the_channel_directory_is_refused(deny: str) -> None:
    """In both mechanisms: no channel could be bound there. seatbelt's half
    is its rendered profile only."""
    with pytest.raises(ChannelInsideWriteDeny, match="channel directory"):
        bwrap.compile(_bwrap_spec(write_denies=(deny,)), _bwrap_ctx(deny))
    sb_spec = Spec(fs=FsPolicy(write_denies=(deny,)), channels=_spec().channels)
    with pytest.raises(SeatbeltChannelInsideWriteDeny, match="channel directory"):
        render_sbpl(sb_spec, resolved={deny: deny}, jail_dir=_JAIL_DIR)
    # The control: without a channel, the same deny compiles in both.
    bwrap.compile(_bwrap_spec(channels=False, write_denies=(deny,)), _bwrap_ctx(deny))
    render_sbpl(Spec(fs=FsPolicy(write_denies=(deny,))), resolved={deny: deny}, jail_dir=_JAIL_DIR)


def test_seatbelt_grants_the_channel_directory_before_the_carve_outs() -> None:
    """Rendered profile only (no darwin host here): the subpath allow comes
    before a write deny under it, so the deny wins; none without a channel."""
    deny = f"{_CHAN}/held"
    spec = Spec(fs=FsPolicy(write_denies=(deny,)), channels=_spec().channels)
    lines = render_sbpl(spec, resolved={deny: deny}, jail_dir=_JAIL_DIR).splitlines()
    grant = f'(allow file-write* (subpath "{_CHAN}"))'
    assert lines.index(grant) < lines.index(f'(deny file-write* (subpath "{deny}"))')
    plain = render_sbpl(Spec(), resolved={}, jail_dir=_JAIL_DIR)
    assert grant not in plain

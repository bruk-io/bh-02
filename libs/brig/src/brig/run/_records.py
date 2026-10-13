"""Per-process records: `<jail_dir>/procs/<id>/`, one directory per start.

SPEC.md section 9, "The Jail and its processes" (decision-181). A start makes
`<jail_dir>/procs/<id>/` before it spawns, and the process's stdio files go
there. Once the spawn returns, the host writes `record.json` beside them,
whole, to a temporary name renamed into place. The process's own exit wrapper
writes `exit` there (`brig/run/_exit_status.py`). This replaced a
registration file per exec sibling, deleted by its `wait`, and one exit file
per jail directory (deleted by decision-183), which settles decision-162
for good: a status belongs to one process id and can't be read as another's.

**The id** is 16 lowercase hex characters from `secrets` (64 bits), fresh per
start: never a pid, never reused. Read back, a name is an id only when it is
exactly that (`is_id`), so a planted name can't traverse (`..`, `/`), and a
record's own `id` must be its directory's name.

**A record outlives its process's `wait`.** Nothing here deletes one but
`clear_for_create`, which removes a gone jail's records, all or none.

**Records are kill authority.** The jail never writes one: the host writes
`record.json`, and the exit wrapper is a host-side program outside the jail's
`wrap`. A channel's one grant is the channel directory, a sibling of `procs/`
(decision-186), and bwrap and seatbelt seal the jail directory against every write root (decision-173). A
stack with no `fs_write` mechanism seals nothing, which is why every reader
here treats what it finds as data to check, never as a fact.
"""

import contextlib
import dataclasses
import json
import os
import re
import secrets
import shutil
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Final, assert_never

from brig.core.runtime import PROCS_DIRNAME
from brig.run._identity import UNKNOWN

#: A process's record, written by the host once its spawn returns.
RECORD_FILENAME: Final = "record.json"

#: A process's exit record, written by its exit wrapper (decision-156).
EXIT_FILENAME: Final = "exit"

_PARTIAL: Final = ".partial"

#: The jail's own record, at the top of its jail directory: whether `create`
#: tethered it (decision-181, TASK-0079.26). Sealed from the jail as the rest
#: of the jail directory is (decision-173).
JAIL_RECORD_FILENAME: Final = "jail.json"

#: The names a process's stdio may not take: they are its records' own.
RESERVED_NAMES: Final = frozenset(
    {RECORD_FILENAME, RECORD_FILENAME + _PARTIAL, EXIT_FILENAME, EXIT_FILENAME + _PARTIAL}
)

_ID: Final = re.compile(r"[0-9a-f]{16}")

#: A process id the kernel can hand out is above 1 (0 names the caller's own
#: group to `killpg`, 1 is init) and below 2**31 (`pid_t` is 32 bits signed).
#: A record naming anything else is not one brig wrote.
_PID_LIMIT: Final = 2**31

_KEYS: Final = (
    "id",
    "order",
    "pid",
    "pgid",
    "start_time",
    "argv",
    "stdout_path",
    "stderr_path",
    "channel",
    "bound_path",
)


@dataclass(frozen=True, slots=True)
class ProcessRecord:
    """One process in a jail, as its runtime identifies it.

    `id` names its records directory (`<jail_dir>/procs/<id>/`); `order` is
    when its start began (nanoseconds since the epoch), which sorts a jail's
    processes in start order, ties broken by `id`. `pid` and `start_time` are
    an identity, not a number: nothing acts on a pid whose current occupant
    started at another time, and an unknown stamp (`brig/run/_identity.py`'s
    `UNKNOWN`) is acted on by nothing (decision-155, decision-172). `pid` is
    the process's exit wrapper, which leads `pgid`. `argv` is what was
    spawned inside the wrapper (the jail's wrap included); `stdout_path` and
    `stderr_path` are where `IoPolicy` sent its output, in its records
    directory. `channel` is the declared channel it was started on and
    `bound_path` the socket reserved for it, the path it binds inside the
    jail (decision-184); both `None` for a process started with none."""

    id: str
    order: int
    pid: int
    pgid: int
    start_time: str
    argv: tuple[str, ...]
    stdout_path: str
    stderr_path: str
    channel: str | None = None
    bound_path: str | None = None


def is_id(name: str) -> bool:
    """Whether `name` is a records directory's name brig could have made."""
    return _ID.fullmatch(name) is not None


def new_id() -> str:
    """A fresh id: 16 lowercase hex characters, never a pid, never reused."""
    return secrets.token_hex(8)


def procs_dir(jail_dir: str) -> str:
    """Where a jail's per-process records live."""
    return os.path.join(jail_dir, PROCS_DIRNAME)


def process_dir(jail_dir: str, process_id: str) -> str:
    """The records directory of process `process_id`.

    Raises:
        ValueError: `process_id` is not an id brig makes.
    """
    if not is_id(process_id):
        raise ValueError(f"{process_id!r} is not a process id brig makes (16 lowercase hex)")
    return os.path.join(procs_dir(jail_dir), process_id)


def exit_path(jail_dir: str, process_id: str) -> str:
    """Where process `process_id`'s exit wrapper writes its status.

    Raises:
        ValueError: `process_id` is not an id brig makes.
    """
    return os.path.join(process_dir(jail_dir, process_id), EXIT_FILENAME)


def make_dir(jail_dir: str, process_id: str) -> str:
    """Make process `process_id`'s records directory (mode 0700), and `procs/`
    if it is not there yet. Returns the directory's path.

    Raises:
        ValueError: `process_id` is not an id brig makes.
        FileExistsError: the directory is already there (an id is never reused).
        OSError: it could not be made.
    """
    os.makedirs(procs_dir(jail_dir), mode=0o700, exist_ok=True)
    directory = process_dir(jail_dir, process_id)
    os.mkdir(directory, 0o700)
    return directory


def to_json(record: ProcessRecord) -> dict[str, Any]:
    """`record` as JSON-native data: what `record.json` holds, and each entry
    of a jail's dict's `processes` (decision-181)."""
    return {
        "id": record.id,
        "order": record.order,
        "pid": record.pid,
        "pgid": record.pgid,
        "start_time": record.start_time,
        "argv": list(record.argv),
        "stdout_path": record.stdout_path,
        "stderr_path": record.stderr_path,
        "channel": record.channel,
        "bound_path": record.bound_path,
    }


def write(jail_dir: str, record: ProcessRecord) -> str:
    """Write `record` as `record.json` in its records directory, whole: one
    `os.write` to a fresh `.partial` file, renamed into place, so a reader
    sees a whole record or none. Returns the record's path.

    Raises:
        ValueError: `record.id` is not an id brig makes.
        OSError: the record could not be written.
    """
    path = os.path.join(process_dir(jail_dir, record.id), RECORD_FILENAME)
    tmp = path + _PARTIAL
    encoded = json.dumps(to_json(record)).encode("utf-8")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, encoded)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    return path


def _is_process_id(value: object) -> bool:
    """Whether `value` is an int a process or group id can hold (2 up to 2**31)."""
    return type(value) is int and 1 < value < _PID_LIMIT


def parse(text: str, expected_id: str) -> ProcessRecord | str:
    """The record `text` holds, or the reason it is not one brig wrote for the
    directory named `expected_id`. Pure."""
    try:
        raw = json.loads(text)
    except ValueError as error:
        return f"is not JSON ({error})"
    return from_json(raw, expected_id)


def from_json(raw: object, expected_id: str) -> ProcessRecord | str:
    """The record `raw` (decoded JSON) holds, or the reason it is not one brig
    wrote for the directory named `expected_id`. Pure. `parse` reads a
    `record.json` through it, and `Jail.from_dict` each entry of `processes`."""
    if type(raw) is not dict:
        return f"holds a JSON {type(raw).__name__}, not an object"
    missing = [key for key in _KEYS if key not in raw]
    if missing:
        return f"is missing key(s) {', '.join(missing)}"
    unknown = sorted(set(raw) - set(_KEYS))
    if unknown:
        return f"has unknown key(s) {', '.join(unknown)}"
    if raw["id"] != expected_id:
        return f"names id {raw['id']!r}, not its directory's {expected_id!r}"
    pid, pgid = raw["pid"], raw["pgid"]
    if not (_is_process_id(pid) and _is_process_id(pgid)):
        return f"'pid'/'pgid' must both be ints from 2 to {_PID_LIMIT - 1}, got {pid!r}/{pgid!r}"
    order = raw["order"]
    if type(order) is not int or order < 0:
        return f"'order' must be a non-negative int, got {order!r}"
    texts = ("start_time", "stdout_path", "stderr_path")
    if any(type(raw[key]) is not str for key in texts):
        return "'start_time', 'stdout_path' and 'stderr_path' must be strs, got " + ", ".join(
            repr(raw[key]) for key in texts
        )
    argv = raw["argv"]
    if type(argv) is not list or any(type(arg) is not str for arg in argv):
        return f"'argv' must be a list of strs, got {argv!r}"
    channel, bound_path = raw["channel"], raw["bound_path"]
    if not (
        (channel is None and bound_path is None)
        or (type(channel) is str and channel and type(bound_path) is str and bound_path)
    ):
        return (
            "'channel' and 'bound_path' must both be null or both non-empty strs, got "
            f"{channel!r}/{bound_path!r}"
        )
    return ProcessRecord(
        id=expected_id,
        order=order,
        pid=pid,
        pgid=pgid,
        start_time=raw["start_time"],
        argv=tuple(argv),
        stdout_path=raw["stdout_path"],
        stderr_path=raw["stderr_path"],
        channel=channel,
        bound_path=bound_path,
    )


@dataclass(frozen=True, slots=True)
class Unreadable:
    """An entry under `procs/` that is not a record brig can read: a link, a
    file, a name that is no id, a directory with no readable `record.json`.
    `reason` says what was wrong with it, for whoever has to inspect it."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class Scan:
    """What `procs/` holds: the readable records in start order, and every
    entry that is not one, in name order."""

    records: tuple[ProcessRecord, ...]
    unreadable: tuple[Unreadable, ...]


def _read_record(directory: str, name: str) -> ProcessRecord | str:
    """The record in `<directory>/<name>/record.json`, read without following a
    link, or why it can't be read."""
    path = os.path.join(directory, name, RECORD_FILENAME)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return f"has no {RECORD_FILENAME}"
    except OSError as error:
        return f"has a {RECORD_FILENAME} that cannot be opened ({error})"
    try:
        with os.fdopen(fd, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        return f"has a {RECORD_FILENAME} that cannot be read ({error})"
    parsed = parse(text, name)
    return parsed if isinstance(parsed, ProcessRecord) else f"has a {RECORD_FILENAME} that {parsed}"


def scan(jail_dir: str) -> Scan:
    """Read every record under `<jail_dir>/procs`, never raising on an entry
    that is not one: it is returned in `Scan.unreadable` for the caller to
    report or refuse on.

    No `procs/` at all is an empty scan: a jail that started nothing, or a
    directory swept since. A `procs` that is a link or not a directory is one
    unreadable entry, and nothing beneath it is read. An entry that vanishes
    between the listing and the read is skipped, as gone."""
    directory = procs_dir(jail_dir)
    try:
        status = os.lstat(directory)
    except FileNotFoundError:
        return Scan((), ())
    except OSError as error:
        return Scan((), (Unreadable(directory, f"cannot be examined ({error})"),))
    if not stat.S_ISDIR(status.st_mode):
        return Scan((), (Unreadable(directory, "is not a directory brig made (a link or a file)"),))
    try:
        names = sorted(os.listdir(directory))
    except OSError as error:
        return Scan((), (Unreadable(directory, f"cannot be listed ({error})"),))

    records: list[ProcessRecord] = []
    unreadable: list[Unreadable] = []
    for name in names:
        path = os.path.join(directory, name)
        try:
            entry = os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as error:
            unreadable.append(Unreadable(path, f"cannot be examined ({error})"))
            continue
        if not stat.S_ISDIR(entry.st_mode):
            unreadable.append(Unreadable(path, "is not a directory brig made (a link or a file)"))
            continue
        if not is_id(name):
            unreadable.append(Unreadable(path, "is not named by a process id brig makes"))
            continue
        read = _read_record(directory, name)
        if isinstance(read, str):
            unreadable.append(Unreadable(path, read))
        else:
            records.append(read)
    records.sort(key=lambda record: (record.order, record.id))
    return Scan(tuple(records), tuple(unreadable))


def disagrees(held: ProcessRecord, on_disk: ProcessRecord) -> bool:
    """Whether a record on disk for a process the caller holds says something
    else about it: any field but `order`, which only sorts. Pure. A disk copy that
    disagrees is never used in place of the held record (decision-181)."""
    return dataclasses.replace(on_disk, order=held.order) != held


def write_jail_record(jail_dir: str, *, jail_id: str, tethered: bool) -> str:
    """Write the jail's own record, `<jail_dir>/jail.json`, whole (a fresh
    `.partial` renamed into place, opened without following a link): its id
    and whether `create` tethered it. Returns its path.

    Raises:
        OSError: it could not be written.
    """
    path = os.path.join(jail_dir, JAIL_RECORD_FILENAME)
    tmp = path + _PARTIAL
    encoded = json.dumps({"jail_id": jail_id, "tethered": tethered}).encode("utf-8")
    with contextlib.suppress(FileNotFoundError):
        os.unlink(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, encoded)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    return path


def tethered_from_json(text: str, jail_id: str) -> bool | None:
    """Whether the jail record `text` says jail `jail_id` was created
    tethered, or `None` when it is not a record brig wrote for that jail.
    Pure."""
    try:
        raw = json.loads(text)
    except ValueError:
        return None
    if type(raw) is not dict or set(raw) != {"jail_id", "tethered"}:
        return None
    if raw["jail_id"] != jail_id or type(raw["tethered"]) is not bool:
        return None
    tethered: bool = raw["tethered"]
    return tethered


def read_tethered(jail_dir: str, jail_id: str) -> bool | None:
    """Whether `<jail_dir>/jail.json` says jail `jail_id` was created
    tethered, read without following a link; `None` when it is missing,
    can't be read, or is not a record brig wrote for that jail."""
    try:
        fd = os.open(os.path.join(jail_dir, JAIL_RECORD_FILENAME), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        with os.fdopen(fd, encoding="utf-8") as recorded:
            text = recorded.read()
    except OSError, UnicodeDecodeError:
        return None
    return tethered_from_json(text, jail_id)


class Standing(Enum):
    """What `create` makes of one record an earlier jail left (decision-181)."""

    #: Its leader holds its identity, or its leader is gone and its group has
    #: a live member: something it names runs.
    RUNS = auto()
    #: Nothing it names runs: its leader is gone and its group empty, or its
    #: leader's pid now names another process, which means an empty group.
    GONE = auto()
    #: Its stamp is unknown: nothing shows what it names is the jail's.
    UNKNOWN_STAMP = auto()


def standing(
    record: ProcessRecord, *, current_stamp: str, leader_zombie: bool, group_live: bool
) -> Standing:
    """Whether `record` still holds anything, from what the host reads now, the
    stamp before the group (decision-181). Pure.

    `current_stamp` is the start stamp of `record.pid`'s occupant now
    (`_identity.UNKNOWN` when there is none); `leader_zombie` whether that
    occupant has exited unreaped; `group_live` whether `record.pgid` has a
    member that is not a zombie. A recycled leader means an empty group: the
    kernel hands a pid out again only once no group of that number has a
    member, and a leader's pid is its group's pgid."""
    if record.start_time == UNKNOWN:
        return Standing.UNKNOWN_STAMP
    if current_stamp == record.start_time and not leader_zombie:
        return Standing.RUNS
    if current_stamp not in (UNKNOWN, record.start_time):
        return Standing.GONE
    return Standing.RUNS if group_live else Standing.GONE


class JailDirInUse(RuntimeError):
    """`create` was asked to use a jail directory whose records an earlier
    jail left, and something they name runs, or brig can't tell
    (decision-181). Nothing was removed. `held` names each record or entry
    and why it holds the directory."""

    def __init__(self, jail_dir: str, held: tuple[Unreadable, ...]) -> None:
        self.jail_dir = jail_dir
        self.held = held
        reasons = "; ".join(f"{item.path} {item.reason}" for item in held)
        super().__init__(
            f"jail directory {jail_dir!r} holds the records of an earlier jail that is not "
            f"known to be gone: {reasons}. Destroy that jail (`Jail.destroy()`, or end "
            "what those records name), or choose another directory. If the process it names "
            "has already been waited for in another process (an exit record exists), it is "
            "still leaving: wait a moment and retry; nothing was removed"
        )


def held_by(
    jail_dir: str,
    scanned: Scan,
    *,
    stamps: Mapping[int, str],
    zombies: frozenset[int],
    live_groups: frozenset[int] | None,
) -> tuple[Unreadable, ...]:
    """Every entry of `scanned` (the records under `jail_dir`) that holds the
    directory: an unreadable one, a record whose stamp is unknown, and a record
    that still runs (`standing`). Pure. `stamps` and `zombies` are what the
    host reads now for each record's pid; `live_groups` the groups with a
    member that is not a zombie, `None` when the process table could not be
    read, and then every record holds (refuse on any doubt)."""
    held: list[Unreadable] = list(scanned.unreadable)
    for record in scanned.records:
        where = process_dir(jail_dir, record.id)
        if live_groups is None:
            held.append(
                Unreadable(where, f"names pid {record.pid}, and the process table can't be read")
            )
            continue
        verdict = standing(
            record,
            current_stamp=stamps.get(record.pid, UNKNOWN),
            leader_zombie=record.pid in zombies,
            group_live=record.pgid in live_groups,
        )
        match verdict:
            case Standing.GONE:
                pass
            case Standing.RUNS:
                held.append(
                    Unreadable(
                        where,
                        f"names pid {record.pid} and process group {record.pgid}, which still runs",
                    )
                )
            case Standing.UNKNOWN_STAMP:
                held.append(
                    Unreadable(
                        where,
                        f"names pid {record.pid} with no start time, so nothing shows it is gone",
                    )
                )
            case _ as unreachable:
                assert_never(unreachable)
    return tuple(held)


def remove_procs(jail_dir: str) -> None:
    """Remove `<jail_dir>/procs` and everything beneath it, following no link:
    `procs` itself must not be a link (`shutil.rmtree` refuses one), and
    `rmtree` removes beneath it through directory file descriptors, opening
    nothing through a symlink, so a link the jail made under `procs/` is
    removed, never followed (decision-181). A platform whose `rmtree` can't
    promise that is refused rather than trusted. No `procs` is not an error.

    Raises:
        OSError: the records could not be removed, or this platform's
            `rmtree` would follow links.
    """
    if not shutil.rmtree.avoids_symlink_attacks:
        raise OSError(
            f"cannot remove {procs_dir(jail_dir)!r} on this platform without following links"
        )
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(procs_dir(jail_dir))


def read_exit(jail_dir: str, process_id: str) -> int | None:
    """Process `process_id`'s recorded exit status, or `None` when there is
    no exit record (still running, `SIGKILL`ed, swept) or no such id. Read
    without following a link.

    Raises:
        ValueError: the exit record does not hold an integer.
    """
    if not is_id(process_id):
        return None
    path = exit_path(jail_dir, process_id)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(fd, encoding="utf-8", errors="replace") as recorded:
        text = recorded.read()
    try:
        return int(text.strip())
    except ValueError as exc:
        raise ValueError(f"exit record {path!r} does not hold an integer: {text!r}") from exc

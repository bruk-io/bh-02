"""What a runtime does to a jail directory before its first start (SPEC.md section 8,
decision-181, decision-184): make the channel directory, and clear the records an earlier jail
left under `procs/`. `HostRuntime` and `OciRuntime` (decision-203) both do it, so it is here and
not in either.
"""

import errno
import os
import stat
import subprocess
from collections.abc import Callable

from brig.core.runtime import channel_dir
from brig.run import _identity, _records
from brig.run.teardown import UnreadableProcessTable, live_groups, read_process_table


def make_channel_dir(jail_dir: str) -> None:
    """Make the jail's channel directory, `<jail_dir>/chan` (decision-184),
    mode 0700, or keep the directory an earlier jail made there. Every
    mechanism that grants it binds or allows it by path, and a bind follows a
    link, so anything there that is not a directory (a link, a file) is
    refused rather than used.

    Raises:
        FileExistsError: `chan` is there and is not a directory.
        OSError: it could not be made or examined.
    """
    path = channel_dir(jail_dir)
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        if not stat.S_ISDIR(os.lstat(path).st_mode):
            raise FileExistsError(
                errno.EEXIST,
                "the jail's channel directory is there and is not a directory brig made "
                "(a link or a file), so granting it would grant whatever it names; remove "
                "it, or choose another jail directory",
                path,
            ) from None


def clear_earlier_records(
    jail_dir: str, *, read_table: Callable[[], str] = read_process_table
) -> None:
    """Remove the records an earlier jail left under `<jail_dir>/procs`, once
    nothing they name runs; on any doubt remove nothing and refuse
    (decision-181). Per record, the stamp before the group
    (`_records.standing`): a leader that holds its identity runs; one whose pid
    now names another process holds no group; one that is gone runs while its
    group has a live member. An unreadable record, an unknown stamp, a link or
    a file under `procs/`, or a process table that can't be read is a doubt.
    `read_table` is the process table's seam, as `group_alive`'s.

    Raises:
        _records.JailDirInUse: something a record names runs, or is in doubt.
        OSError: the records could not be removed.
    """
    scanned = _records.scan(jail_dir)
    if not scanned.records and not scanned.unreadable:
        return
    try:
        live: frozenset[int] | None = live_groups(read_table())
    except OSError, subprocess.CalledProcessError, UnreadableProcessTable:
        live = None
    pids = {record.pid for record in scanned.records}
    held = _records.held_by(
        jail_dir,
        scanned,
        stamps={pid: _identity.start_stamp(pid) for pid in pids},
        zombies=frozenset(pid for pid in pids if _identity.is_zombie(pid)),
        live_groups=live,
    )
    if held:
        raise _records.JailDirInUse(jail_dir, held)
    _records.remove_procs(jail_dir)

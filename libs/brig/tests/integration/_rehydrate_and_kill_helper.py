"""Subprocess entry point for tests/integration/test_handle_rehydration.py's
cross-process rehydration proof (task-023).

Not a test module (no `test_` prefix, no `pytest` import) -- invoked as its
own OS process via `subprocess.run([sys.executable, __file__, json_path,
...])`, never imported by the test module or by pytest's collector. This is
what makes the rehydration genuinely cross-process rather than an
in-process `Handle.from_dict(handle.to_dict())` call wearing a subprocess
costume (that in-process round trip is already covered by
`test_launcher.py`'s AC #8; this file exists to prove the SEPARATE-PROCESS
case task-023 is chartered to close).

argv: json_path [--no-kill | --wait]

`json_path` -- a file holding exactly `Handle.to_dict()`'s JSON, and
nothing else -- is this process's SOLE input. No pid, no pgid, and no
in-memory object reaches this process by any other route: not argv (which
carries only the path, plus the optional `--no-kill` mode flag below -- a
behavior switch, not identity data), not an environment variable, not a
shared object. `Handle.from_dict` is what reconstructs identity (pid, pgid,
and everything else `kill()` needs) purely from the file's bytes.

Modes:
  default    -- rehydrate, then call `handle.kill()` (THE CLAIM).
  --no-kill  -- rehydrate, then call `handle.alive()` and report it, WITHOUT
                calling `kill()` (THE CONTROL, AC #6) -- isolates the
                rehydrated `kill()` call as the cause of the tree's death,
                rather than the helper process exiting or elapsed time.
  --wait     -- rehydrate, then call `handle.wait()` and report the status,
                or the name of the exception it refused with (decision-156).
                This process never parented the workload and holds no
                in-memory record of it, so an answer can only have come off
                disk -- which is the whole claim.

Prints exactly one JSON line to stdout:
  {"pid": <this process's os.getpid()>,
   "to_dict": <the rehydrated handle's own to_dict(), for AC #4's
               round-trip-fidelity check>,
   "kill_report": {...}}   # default mode only
   "alive": <bool>}        # --no-kill mode only
   "exit_status": <int>    # --wait mode, when a status was readable
   "exit_error": <str>}    # --wait mode, the refusal's exception class name
"""

from __future__ import annotations

import json
import os
import sys

from brig.run.handle import ExitStatusUnobservable, Handle
from brig.run.teardown import KillReport


def _kill_report_to_dict(report: KillReport) -> dict[str, object]:
    """`KillReport` has no `to_dict` of its own (task-020/027 never added
    one) -- this is this helper's private serialization of it, mirroring
    `brig/run/handle.py`'s own `_report_to_dict` idiom for
    `EnforcementReport`."""
    return {
        "items": [
            {
                "kind": item.kind,
                "identity": item.identity,
                "outcome": item.outcome.value,
                "detail": item.detail,
            }
            for item in report.items
        ]
    }


def main() -> None:
    json_path = sys.argv[1]
    flags = sys.argv[2:]
    no_kill = "--no-kill" in flags
    wait = "--wait" in flags

    with open(json_path) as f:
        d = json.load(f)

    handle = Handle.from_dict(d)

    result: dict[str, object] = {
        "pid": os.getpid(),
        "to_dict": handle.to_dict(),
    }

    if wait:
        try:
            result["exit_status"] = handle.wait(timeout=20.0)
        except ExitStatusUnobservable:
            result["exit_error"] = "ExitStatusUnobservable"
    elif no_kill:
        result["alive"] = handle.alive()
    else:
        result["kill_report"] = _kill_report_to_dict(handle.kill())

    print(json.dumps(result))


if __name__ == "__main__":
    main()

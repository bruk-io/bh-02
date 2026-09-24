"""`run`: launching, teardown, readiness, and the sensor records that come
back with a jail.

Per SPEC.md §13, `run` may import `core`, `mech`, and `stack`.

`Event` and `EventKind` live in `brig/core/events.py` (decision-052,
confirmed by decision-060). This module re-exports them, plus `EVENT_VERSION`
and `DataValue`, so every existing `brig.run.Event`-style import keeps
resolving and `brig.run.Event is brig.core.Event` holds -- see
`brig/core/events.py`'s docstring.

**There is no event stream** (decision-152, 2026-09-08). `EventLog`, the
per-jail `events.jsonl` file it appended to, and the `SPAWN`/`EXEC`/
`EXEC_END`/`KILL`/`EXIT` lifecycle records are deleted. What `run` does with
a mechanism's sensor feed instead is STAMP it -- `brig/run/events.py`'s
`stamp`/`stamp_all` supply the `ts` and `jail_id` only this layer may supply
-- and hand the records to the embedder: `Handle.compile_events` for
`EventSource.known_at_compile()`, `Handle.exit_events()` for
`EventSource.classify_exit()`. An embedder that wants them durable writes
them into its own log, which is where a durable record belongs; brig was
otherwise shipping a second, worse log beside every embedder's real one.

`wait_ready` and `exec_in_jail` are private delegates (`readiness.py`,
`exec_.py`); they are intentionally NOT re-exported here --
`Handle.wait_ready`/`.exec` are the public surface, per SPEC.md §9.

`kill_jail` (`teardown.py`, task-020) and its full report vocabulary --
`KillReport`, `KillItem`, `KillOutcome`, `KILL_ITEM_KINDS` -- ARE re-exported
here (task-072, decision-131): SPEC.md §9 makes `Handle.kill()` a public
method that RETURNS a `KillReport`, so the vocabulary a caller needs in order
to name that return value is exposed at this module's own surface -- a public
method whose return type callers cannot name is the "true-as-tested but
weaker than it reads" incompleteness this library refuses.

**The egress proxy's decisions are read here too** (decision-157,
2026-09-08). `connect_proxy`'s filter is a separate process that may not
import brig, so its live allow/deny decisions cannot travel through
`EventSource`; it writes them itself and `brig/run/egress.py` --
`read_egress_decisions`, returning stamped `Event`s and a cursor -- is the
`run`-layer reader that both that module and the proxy's own docstring had
been promising since M6. It is a free function rather than a `Handle`
method because the feed is CURSORED: resuming where the last read stopped
is caller state, and a frozen `Handle` has nowhere to keep it.

task-059 adds `build_compile_ctx` (`compile_ctx.py`): the one helper that
resolves a `Spec` + `jail_dir` into a real `CompileCtx`, performing the two
realpath resolutions `mech.compile()` itself may never perform (SPEC.md
§6, decision-115) -- see that module's own docstring.
"""

from brig.core import EVENT_VERSION as EVENT_VERSION
from brig.core import DataValue as DataValue
from brig.core import Event as Event
from brig.core import EventKind as EventKind
from brig.run._waiters import ExitRecord as ExitRecord
from brig.run.compile_ctx import build_compile_ctx as build_compile_ctx
from brig.run.egress import EgressRead as EgressRead
from brig.run.egress import decisions_path as decisions_path
from brig.run.egress import read_egress_decisions as read_egress_decisions
from brig.run.events import stamp as stamp
from brig.run.events import stamp_all as stamp_all
from brig.run.handle import HANDLE_VERSION as HANDLE_VERSION
from brig.run.handle import ExitStatusUnobservable as ExitStatusUnobservable
from brig.run.handle import Handle as Handle
from brig.run.handle import JailStat as JailStat
from brig.run.launcher import IoPolicy as IoPolicy
from brig.run.launcher import LaunchRefused as LaunchRefused
from brig.run.launcher import SubprocessLauncher as SubprocessLauncher
from brig.run.teardown import KILL_ITEM_KINDS as KILL_ITEM_KINDS
from brig.run.teardown import KillItem as KillItem
from brig.run.teardown import KillOutcome as KillOutcome
from brig.run.teardown import KillReport as KillReport
from brig.run.teardown import kill_jail as kill_jail

__all__ = (  # noqa: RUF022
    "DataValue",
    "EgressRead",
    "ExitRecord",
    "ExitStatusUnobservable",
    "EVENT_VERSION",
    "Event",
    "EventKind",
    "HANDLE_VERSION",
    "Handle",
    "IoPolicy",
    "JailStat",
    "KILL_ITEM_KINDS",
    "KillItem",
    "KillOutcome",
    "KillReport",
    "LaunchRefused",
    "SubprocessLauncher",
    "build_compile_ctx",
    "decisions_path",
    "kill_jail",
    "read_egress_decisions",
    "stamp",
    "stamp_all",
)

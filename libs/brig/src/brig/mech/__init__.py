"""`mech`: the mechanism layer - the contract every mechanism implements, and the mechanisms.

The contract (`Mechanism`, `Step`, `CompileCtx`, `EventSource`, ...) lives in
`brig.mech.contract`, a sibling each mechanism imports directly, so no mechanism imports
this package's `__init__` back (that shape is an import cycle, and brig's gate runs
`no-import-cycles`). This module only re-exports: the contract, then the mechanisms.
"""

from brig.mech.bwrap import Bwrap, bwrap
from brig.mech.contract import (
    DETACH,
    JAIL_LIFETIME,
    LAUNCH_SCOPED,
    NEW_PROCESS_GROUP,
    PTY,
    ArgvTransformer,
    CompileCtx,
    EventPayload,
    EventSource,
    ExitOutcome,
    Helper,
    HelperLifetime,
    LaunchFeature,
    Mechanism,
    StagedFile,
    Step,
)
from brig.mech.env_scrub import EnvScrub, env_scrub
from brig.mech.rlimits import Rlimits, rlimits
from brig.mech.seatbelt import Seatbelt, seatbelt

__all__ = (  # noqa: RUF022
    "ArgvTransformer",
    "Bwrap",
    "CompileCtx",
    "DETACH",
    "EnvScrub",
    "EventPayload",
    "EventSource",
    "ExitOutcome",
    "Helper",
    "HelperLifetime",
    "JAIL_LIFETIME",
    "LAUNCH_SCOPED",
    "LaunchFeature",
    "Mechanism",
    "NEW_PROCESS_GROUP",
    "PTY",
    "Rlimits",
    "Seatbelt",
    "StagedFile",
    "Step",
    "bwrap",
    "env_scrub",
    "rlimits",
    "seatbelt",
)

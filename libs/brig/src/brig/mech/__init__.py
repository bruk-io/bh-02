"""`mech`: the mechanism layer - the contract every mechanism implements, and the mechanisms.

The contract (`Mechanism`, `Step`, `CompileCtx`, `EventSource`, ...) lives in
`brig.mech.contract`, a sibling each mechanism imports directly, so no mechanism imports
this package's `__init__` back (that shape is an import cycle, and brig's gate runs
`no-import-cycles`). This module only re-exports: the contract, then the mechanisms.
"""

from brig.mech.bwrap import Bwrap, bwrap
from brig.mech.contract import (
    JAIL_LIFETIME,
    LAUNCH_SCOPED,
    ArgvTransformer,
    CompileCtx,
    EventPayload,
    EventSource,
    ExitOutcome,
    Helper,
    HelperLifetime,
    Mechanism,
    StagedFile,
    Step,
)
from brig.mech.env_scrub import EnvScrub, env_scrub
from brig.mech.oci import Oci
from brig.mech.rlimits import Rlimits, rlimits
from brig.mech.seatbelt import Seatbelt, seatbelt

__all__ = (  # noqa: RUF022
    "ArgvTransformer",
    "Bwrap",
    "CompileCtx",
    "EnvScrub",
    "EventPayload",
    "EventSource",
    "ExitOutcome",
    "Helper",
    "HelperLifetime",
    "JAIL_LIFETIME",
    "LAUNCH_SCOPED",
    "Mechanism",
    "Oci",
    "Rlimits",
    "Seatbelt",
    "StagedFile",
    "Step",
    "bwrap",
    "env_scrub",
    "rlimits",
    "seatbelt",
)

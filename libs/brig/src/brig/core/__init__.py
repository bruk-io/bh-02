"""`core`: the pure model — Spec, axes, grades, report, subset algebra, threat lists, serialization.

Pure means pure: no I/O, no clock, no randomness, no subprocess. The layer
gate enforces the import side of that; the rest is convention this docstring
exists to state. `core` is complete per SPEC.md §4-§5 as of M1.

Frames (SPEC.md §10, §13: length-prefix framing for channels) are the one §13
item deliberately NOT in M1. They arrive with the communication mechanism that
needs them. This is stated explicitly so a reader comparing the layer table to
the code does not conclude `core` is silently incomplete.
"""

from typing import Final

from brig.core.events import EVENT_VERSION as EVENT_VERSION
from brig.core.events import DataValue as DataValue
from brig.core.events import Event as Event
from brig.core.events import EventKind as EventKind
from brig.core.grades import AXES as AXES
from brig.core.grades import GRADES_ORDERED as GRADES_ORDERED
from brig.core.grades import Axis as Axis
from brig.core.grades import Grade as Grade
from brig.core.probes import Battery as Battery
from brig.core.probes import ProbeOutcome as ProbeOutcome
from brig.core.probes import ProbeReport as ProbeReport
from brig.core.probes import ProbeShape as ProbeShape
from brig.core.probes import Verdict as Verdict
from brig.core.report import EnforcementReport as EnforcementReport
from brig.core.report import Floors as Floors
from brig.core.report import FloorViolation as FloorViolation
from brig.core.report import Graded as Graded
from brig.core.report import Shortfall as Shortfall
from brig.core.report import require as require
from brig.core.report import unenforced_report as unenforced_report
from brig.core.signatures import AxisClaim as AxisClaim
from brig.core.signatures import SignatureBook as SignatureBook
from brig.core.signatures import denial_subject as denial_subject
from brig.core.spec import SPEC_VERSION as SPEC_VERSION
from brig.core.spec import Channel as Channel
from brig.core.spec import ChannelKind as ChannelKind
from brig.core.spec import EnvMode as EnvMode
from brig.core.spec import EnvPolicy as EnvPolicy
from brig.core.spec import FsPolicy as FsPolicy
from brig.core.spec import IncomparableSpecs as IncomparableSpecs
from brig.core.spec import Limits as Limits
from brig.core.spec import NetworkPolicy as NetworkPolicy
from brig.core.spec import Provisioning as Provisioning
from brig.core.spec import ReadModel as ReadModel
from brig.core.spec import Spec as Spec
from brig.core.spec import UnsupportedSpecVersion as UnsupportedSpecVersion
from brig.core.threats import BARE_REPO_TOPLEVEL as BARE_REPO_TOPLEVEL
from brig.core.threats import (
    CREDENTIAL_READ_DENIES_HOME_RELATIVE as CREDENTIAL_READ_DENIES_HOME_RELATIVE,
)
from brig.core.threats import SELF_MODIFY_WORKSPACE_RELATIVE as SELF_MODIFY_WORKSPACE_RELATIVE

#: Enforcement grades, ordered weakest-first. SPEC.md section 4 defines them;
#: they live here from day zero because every later module names them.
#: These are module-level names bound to Grade enum members for backward
#: compatibility and ergonomics.
UNENFORCED: Final = Grade.UNENFORCED
COOPERATIVE: Final = Grade.COOPERATIVE
BEST_EFFORT: Final = Grade.BEST_EFFORT
ENFORCED: Final = Grade.ENFORCED

__all__ = (  # noqa: RUF022
    "AXES",
    "Axis",
    "AxisClaim",
    "BARE_REPO_TOPLEVEL",
    "BEST_EFFORT",
    "Battery",
    "COOPERATIVE",
    "CREDENTIAL_READ_DENIES_HOME_RELATIVE",
    "Channel",
    "ChannelKind",
    "DataValue",
    "ENFORCED",
    "EVENT_VERSION",
    "EnforcementReport",
    "EnvMode",
    "EnvPolicy",
    "Event",
    "EventKind",
    "FloorViolation",
    "Floors",
    "FsPolicy",
    "GRADES_ORDERED",
    "Grade",
    "Graded",
    "IncomparableSpecs",
    "Limits",
    "NetworkPolicy",
    "ProbeOutcome",
    "ProbeReport",
    "ProbeShape",
    "Provisioning",
    "ReadModel",
    "SELF_MODIFY_WORKSPACE_RELATIVE",
    "SPEC_VERSION",
    "Shortfall",
    "SignatureBook",
    "Spec",
    "UNENFORCED",
    "UnsupportedSpecVersion",
    "Verdict",
    "denial_subject",
    "require",
    "unenforced_report",
)

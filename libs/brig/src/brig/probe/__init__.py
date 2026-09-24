"""`probe`: canned violation-attempt batteries and verdict classification
(SPEC.md §12). Per SPEC.md §13's layer table, `probe` may import `core`,
`run`, and `observe`.

This package re-exports the three names a battery author or an embedder
needs: `Probe` and `Battery` (`brig.probe.battery`) and `classify`
(`brig.probe.verdict`). `Expectation` stays reachable from
`brig.probe.battery` directly rather than re-exported here -- this task's
own Deliverable names exactly `Probe`, `Battery`, `classify`.

`Battery.run` is deliberately absent from this milestone's `Battery`
(SPEC.md §9: an unimplemented capability is absent from the surface, never a
raising stub) -- a later task supplies it. Concrete batteries (env, limits,
fs, network) live one module per battery under `brig.probe.batteries`, each
imported by its own path rather than re-exported through one shared barrel,
so later tasks never touch one shared file.
"""

from brig.probe.battery import Battery as Battery
from brig.probe.battery import Probe as Probe
from brig.probe.verdict import classify as classify

__all__ = (
    "Battery",
    "Probe",
    "classify",
)

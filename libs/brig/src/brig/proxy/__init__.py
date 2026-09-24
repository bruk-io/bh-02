"""The filtering egress proxy, as a standalone process.

`connect_proxy` (SPEC.md §7) is the only mechanism whose enforcement is a
*process* rather than a kernel configuration, and that process runs
TRUSTED-SIDE, outside the jail it filters for. This package is therefore
deliberately outside the layer DAG's flow: its row in the `brig-layers`
allow table is empty, so the gate refuses any import of `brig.core`,
`brig.mech`, `brig.run` or anything else in the library from here.

That is a real constraint, not tidiness. This code is what a jailed,
possibly hostile workload talks to on every connection it makes; the
smaller its import graph, the smaller both its startup cost (it is spawned
per jail) and the surface a jail can reach through it. Anything it needs to
share with the library crosses as argv or as a line in a file, never as a
shared object.
"""

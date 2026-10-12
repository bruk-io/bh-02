"""`runtime`: runtimes that are not `run`'s own (SPEC.md section 13, decision-178).

`run` defines the `Runtime` and `Agent` protocols and never imports a module
here: an embedder picks a runtime by importing it. `fake` is the one today, a
second implementation of both protocols for tests. `HostRuntime` stays in `run`
until decision-0001 step 3.
"""

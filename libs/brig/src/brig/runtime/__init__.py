"""`runtime`: runtimes that are not `run`'s own (SPEC.md section 13, decision-178).

`run` defines the `Runtime` and `Supervisor` protocols and never imports a module
here: an embedder picks a runtime by importing it. `fake` is a second implementation
of both protocols for tests, and `oci` (decision-202) is a container, created and ended
through the Docker daemon. `HostRuntime` stays in `run`
until decision-0001 step 3.
"""
